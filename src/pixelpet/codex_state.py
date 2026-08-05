from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .assistant_state import SessionUsage, StatusSnapshot
from .config import default_codex_home
from .status import Status, status_priority

DEFAULT_TAIL_BYTES = 512 * 1024
DEFAULT_MAX_LINES = 700


@dataclass(frozen=True)
class ThreadRow:
    id: str
    rollout_path: str | None = None
    cwd: str | None = None
    title: str | None = None
    preview: str | None = None
    source: str | None = None
    thread_source: str | None = None
    agent_nickname: str | None = None
    cli_version: str | None = None
    git_branch: str | None = None
    updated_at: float | None = None
    updated_at_ms: float | None = None
    tokens_used: int | None = None


@dataclass(frozen=True)
class PendingCall:
    call_id: str
    name: str
    timestamp_ms: int
    arguments: dict[str, Any]


@dataclass(frozen=True)
class TurnLifecycle:
    turn_id: str | None = None
    started_at_ms: int | None = None
    completed_at_ms: int | None = None
    duration_ms: float | None = None
    terminal: str | None = None
    terminal_reason: str | None = None


class CodexStateReader:
    def __init__(
        self,
        codex_home: Path | None = None,
        state_db_path: Path | None = None,
        done_timeout_seconds: float = 300.0,
        active_window_seconds: float = 300.0,
        now_ms: Callable[[], int] | None = None,
    ) -> None:
        self.codex_home = codex_home or default_codex_home()
        self.state_db_path = state_db_path or self.codex_home / "state_5.sqlite"
        self.done_timeout_ms = int(done_timeout_seconds * 1000)
        self.active_window_ms = int(active_window_seconds * 1000)
        self._now_ms = now_ms or _now_ms

    def current_status(self, limit: int = 12) -> StatusSnapshot:
        try:
            rows = self._read_rows(max(limit * 2, limit))
        except Exception as exc:
            return StatusSnapshot(
                Status.FAILED_OFFLINE,
                f"Codex state unavailable: {exc}",
                activity="FAILED",
                backend="codex",
            )

        now = self._now_ms()
        snapshots: list[StatusSnapshot] = []
        for row in [row for row in rows if is_desktop_row(row)][:limit]:
            events = read_jsonl_tail(row.rollout_path)
            snapshots.append(summarize_thread(row, events, now, self.done_timeout_ms, self.active_window_ms))

        if not snapshots:
            return StatusSnapshot(
                Status.IDLE,
                "No Codex Desktop threads found.",
                activity="IDLE",
                backend="codex",
            )

        return replace(
            max(snapshots, key=status_sort_key),
            backend="codex",
        )

    def _read_rows(self, limit: int) -> list[ThreadRow]:
        db_path = self.state_db_path.expanduser()
        if not db_path.exists():
            raise FileNotFoundError(db_path)

        uri = f"file:{db_path}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            connection.row_factory = sqlite3.Row
            available = {
                row["name"]
                for row in connection.execute("pragma table_info(threads)").fetchall()
            }
            if not available:
                raise RuntimeError("threads table not found")

            columns = [
                "id",
                "rollout_path",
                "cwd",
                "title",
                "preview",
                "source",
                "thread_source",
                "agent_nickname",
                "cli_version",
                "git_branch",
                "updated_at",
                "updated_at_ms",
                "tokens_used",
            ]
            select_columns = [
                column if column in available else f"null as {column}"
                for column in columns
            ]
            where = "where archived = 0" if "archived" in available else ""
            order_column = "updated_at_ms" if "updated_at_ms" in available else "updated_at"
            order = f"order by {order_column} desc" if order_column in available else ""
            sql = f"select {', '.join(select_columns)} from threads {where} {order} limit ?"

            rows = connection.execute(sql, (max(1, min(100, int(limit))),)).fetchall()
            return [ThreadRow(**dict(row)) for row in rows if row["id"]]
        finally:
            connection.close()


def summarize_thread(
    row: ThreadRow,
    events: list[dict[str, Any]],
    now_ms: int,
    done_timeout_ms: int,
    active_window_ms: int,
) -> StatusSnapshot:
    pending = pending_calls(events)
    updated_at_ms = max(row_time_ms(row), latest_event_ms(events))
    title = row.agent_nickname or row.title or row.preview or row.id[:8]

    usage = None
    if row.tokens_used is not None:
        usage = SessionUsage(value=int(row.tokens_used), display_kind="tokens")
    cost = _extract_codex_cost(events)

    permission = next((call for call in pending if is_permission_call(call)), None)
    if permission:
        return StatusSnapshot(
            Status.PERMISSION_REQUIRED,
            approval_reason(permission),
            row.id,
            title,
            updated_at_ms,
            "NEEDS APPROVAL",
            cost=cost,
            usage=usage,
        )

    needs_input = next((call for call in pending if is_input_call(call)), None)
    if needs_input:
        return StatusSnapshot(
            Status.NEEDS_INPUT,
            input_reason(needs_input),
            row.id,
            title,
            updated_at_ms,
            "WAITING INPUT",
            cost=cost,
            usage=usage,
        )

    lifecycle = latest_turn_lifecycle(events)
    if lifecycle.terminal == "aborted":
        return StatusSnapshot(
            Status.FAILED_OFFLINE,
            lifecycle.terminal_reason or "Latest Codex turn was aborted.",
            row.id,
            title,
            lifecycle.completed_at_ms or updated_at_ms,
            "FAILED",
            cost=cost,
            usage=usage,
        )

    if lifecycle.completed_at_ms and now_ms - lifecycle.completed_at_ms <= done_timeout_ms:
        return StatusSnapshot(
            Status.DONE,
            "Latest Codex turn completed recently.",
            row.id,
            title,
            lifecycle.completed_at_ms,
            "DONE",
            cost=cost,
            usage=usage,
        )

    has_recent_activity = updated_at_ms > 0 and now_ms - updated_at_ms <= active_window_ms
    running = lifecycle.started_at_ms is not None and lifecycle.terminal is None and has_recent_activity
    if running or (pending and has_recent_activity):
        return StatusSnapshot(
            Status.WORKING,
            "Codex turn is running.",
            row.id,
            title,
            updated_at_ms,
            activity_for_call(pending[-1]) if pending else "THINKING",
            cost=cost,
            usage=usage,
        )

    return StatusSnapshot(Status.IDLE, "No active Codex work.", row.id, title, updated_at_ms, "IDLE", cost=cost, usage=usage)


def status_sort_key(snapshot: StatusSnapshot) -> tuple[int, int, int]:
    updated_at_ms = snapshot.updated_at_ms or 0
    if snapshot.status in {Status.PERMISSION_REQUIRED, Status.NEEDS_INPUT}:
        return 3, status_priority(snapshot.status), updated_at_ms
    return 2, updated_at_ms, status_priority(snapshot.status)


def is_desktop_row(row: ThreadRow) -> bool:
    source = row.source or ""
    thread_source = row.thread_source or ""
    if source == "cli" or thread_source == "cli":
        return False
    if not source and not thread_source:
        return True
    return (
        source in {"vscode", "desktop"}
        or thread_source in {"user", "subagent"}
        or "subagent" in source
    )


def read_jsonl_tail(file_path: str | os.PathLike[str] | None) -> list[dict[str, Any]]:
    if not file_path:
        return []
    path = Path(file_path).expanduser()
    try:
        size = path.stat().st_size
        length = min(size, DEFAULT_TAIL_BYTES)
        start = max(0, size - length)
        with path.open("rb") as handle:
            handle.seek(start)
            raw = handle.read(length).decode("utf-8", errors="replace")
        if start > 0:
            raw = raw.partition("\n")[2]
        lines = [line for line in raw.splitlines() if line.strip()][-DEFAULT_MAX_LINES:]
        return [event for line in lines if (event := parse_event(line)) is not None]
    except OSError:
        return []


def parse_event(line: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(line)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def pending_calls(events: list[dict[str, Any]]) -> list[PendingCall]:
    calls: dict[str, PendingCall] = {}
    for event in events:
        if event.get("type") != "response_item":
            continue
        payload = as_dict(event.get("payload"))
        payload_type = payload.get("type")
        call_id = string_value(payload.get("call_id"))
        if payload_type == "function_call" and call_id:
            calls[call_id] = PendingCall(
                call_id=call_id,
                name=string_value(payload.get("name")),
                timestamp_ms=event_time_ms(event),
                arguments=parse_arguments(payload.get("arguments")),
            )
        elif payload_type == "function_call_output" and call_id:
            calls.pop(call_id, None)
    return list(calls.values())


def is_input_call(call: PendingCall) -> bool:
    normalized = call.name.replace(".", "_").lower()
    return normalized.endswith("request_user_input") or normalized.endswith("requestuserinput")


def is_permission_call(call: PendingCall) -> bool:
    return (
        call.arguments.get("sandbox_permissions") == "require_escalated"
        or bool(call.arguments.get("justification"))
    )


def approval_reason(call: PendingCall) -> str:
    justification = string_value(call.arguments.get("justification"))
    command = string_value(call.arguments.get("cmd")) or string_value(call.arguments.get("command"))
    if justification and command:
        return f"{justification} ({command})"
    return justification or command or "Codex is waiting for approval."


def input_reason(call: PendingCall) -> str:
    questions = call.arguments.get("questions")
    if isinstance(questions, list) and questions:
        first = as_dict(questions[0])
        return string_value(first.get("question")) or "Codex is waiting for your input."
    return "Codex is waiting for your input."


def activity_for_call(call: PendingCall) -> str:
    if is_permission_call(call):
        return "NEEDS APPROVAL"
    if is_input_call(call):
        return "WAITING INPUT"

    name = call.name.lower()
    nested_activity = activity_for_nested_tool(call)
    if nested_activity:
        return nested_activity

    if name.endswith("exec_command") or name.endswith("shell_command"):
        return activity_for_command(call.arguments)
    if name.endswith("apply_patch"):
        return "PATCHING"
    if any(part in name for part in ("read", "open", "find", "list", "grep", "sed", "cat", "rg", "nl", "view")):
        return "READING FILES"
    if any(part in name for part in ("search", "query", "web", "browser", "curl")):
        return "SEARCHING WEB"
    if "image" in name:
        return "MAKING IMAGE"
    if "automation" in name:
        return "AUTOMATION"
    return "USING TOOL"


def activity_for_nested_tool(call: PendingCall) -> str | None:
    tool_uses = call.arguments.get("tool_uses")
    if not isinstance(tool_uses, list):
        return None

    for item in reversed(tool_uses):
        tool = as_dict(item)
        name = string_value(tool.get("recipient_name")) or string_value(tool.get("name"))
        if not name:
            continue
        nested = PendingCall(
            call_id=call.call_id,
            name=name,
            timestamp_ms=call.timestamp_ms,
            arguments=as_dict(tool.get("parameters")),
        )
        return activity_for_call(nested)
    return "RUNNING TOOLS"


def activity_for_command(arguments: dict[str, Any]) -> str:
    command = string_value(arguments.get("cmd")) or string_value(arguments.get("command"))
    normalized = command.lower()
    first_word = normalized.split(maxsplit=1)[0] if normalized.split() else ""
    if "pixelpet pets validate" in normalized:
        return "VALIDATING PET"
    if "pixelpet show" in normalized or "pixelpet run" in normalized:
        return "TESTING DISPLAY"
    if any(term in normalized for term in ("pytest", "unittest", "go test", "cargo test", "npm test", "pnpm test", "yarn test")):
        return "RUNNING TESTS"
    if " test" in normalized or normalized.startswith("test "):
        return "RUNNING TESTS"
    if any(term in normalized for term in ("ruff", "mypy", "lint", "compileall", "validate")):
        return "CHECKING CODE"
    if any(term in normalized for term in ("npm run build", "pnpm build", "yarn build", "cargo build", "make ")):
        return "BUILDING"
    if any(term in normalized for term in ("pip install", "npm install", "pnpm install", "uv sync")):
        return "INSTALLING"
    if normalized.startswith("gh run"):
        return "CHECKING CI"
    if normalized.startswith("gh pr create"):
        return "CREATING PR"
    if normalized.startswith("gh "):
        return "CHECKING GITHUB"
    if normalized.startswith("git status") or normalized.startswith("git diff") or normalized.startswith("git log") or normalized.startswith("git show"):
        return "CHECKING GIT"
    if normalized.startswith("git "):
        return "UPDATING GIT"
    if first_word in {"rg", "grep", "sed", "cat", "nl", "ls", "find", "wc"}:
        return "READING FILES"
    if first_word in {"curl", "wget"}:
        return "FETCHING WEB"
    if normalized.startswith("npm start") or "npm run dev" in normalized or "pnpm dev" in normalized or "yarn dev" in normalized:
        return "RUNNING APP"
    return "RUNNING CMD"


def latest_turn_lifecycle(events: list[dict[str, Any]]) -> TurnLifecycle:
    lifecycle = TurnLifecycle()
    for event in events:
        payload = as_dict(event.get("payload"))
        event_type = event.get("type")
        payload_type = payload.get("type")

        if event_type == "turn_context":
            lifecycle = TurnLifecycle(
                turn_id=string_or_none(payload.get("turn_id")) or lifecycle.turn_id,
                started_at_ms=event_time_ms(event) or lifecycle.started_at_ms,
            )
            continue

        if event_type != "event_msg":
            continue

        if payload_type == "task_started":
            lifecycle = TurnLifecycle(
                turn_id=string_or_none(payload.get("turn_id")) or lifecycle.turn_id,
                started_at_ms=event_time_ms(event) or parse_time_ms(payload.get("started_at")),
            )
        elif payload_type == "task_complete":
            lifecycle = TurnLifecycle(
                turn_id=string_or_none(payload.get("turn_id")) or lifecycle.turn_id,
                started_at_ms=lifecycle.started_at_ms,
                completed_at_ms=parse_time_ms(payload.get("completed_at")) or event_time_ms(event),
                duration_ms=float_value(payload.get("duration_ms")),
                terminal="completed",
            )
        elif payload_type == "turn_aborted":
            lifecycle = TurnLifecycle(
                turn_id=string_or_none(payload.get("turn_id")) or lifecycle.turn_id,
                started_at_ms=lifecycle.started_at_ms,
                completed_at_ms=event_time_ms(event),
                duration_ms=float_value(payload.get("duration_ms")),
                terminal="aborted",
                terminal_reason=string_or_none(payload.get("reason")) or "Codex turn aborted.",
            )
    return lifecycle


def parse_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def latest_event_ms(events: list[dict[str, Any]]) -> int:
    for event in reversed(events):
        timestamp = event_time_ms(event)
        if timestamp:
            return timestamp
    return 0


def row_time_ms(row: ThreadRow) -> int:
    if row.updated_at_ms:
        return int(row.updated_at_ms)
    if row.updated_at:
        value = float(row.updated_at)
        return int(value if value > 10_000_000_000 else value * 1000)
    return 0


def event_time_ms(event: dict[str, Any]) -> int:
    timestamp = event.get("timestamp")
    if not isinstance(timestamp, str) or not timestamp:
        return 0
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return int(parsed.timestamp() * 1000)


def parse_time_ms(value: Any) -> int | None:
    if isinstance(value, int | float):
        return int(value if value > 10_000_000_000 else value * 1000)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int(parsed.timestamp() * 1000)


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def string_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def float_value(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def _extract_codex_cost(events: list[dict[str, Any]]) -> float | None:
    for event in reversed(events):
        payload = as_dict(event.get("payload"))
        if payload.get("type") == "content":
            usage = as_dict(payload.get("usage"))
            cost = float_value(usage.get("cost"))
            if cost is not None:
                return cost
        metadata = as_dict(event.get("metadata"))
        cost = float_value(metadata.get("cost"))
        if cost is not None:
            return cost
    return None
