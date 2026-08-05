from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .assistant_state import StatusSnapshot
from .codex_state import activity_for_command, read_jsonl_tail
from .config import default_vscode_user_dir
from .status import Status, status_priority

TRANSCRIPTS_GLOB = "*/GitHub.copilot-chat/transcripts/*.jsonl"
CHAT_SESSIONS_GLOB = "*/chatSessions/*.jsonl"
EMPTY_WINDOW_GLOB = "globalStorage/emptyWindowChatSessions/*.jsonl"
SESSION_STORE_DB = Path("globalStorage") / "github.copilot-chat" / "session-store.db"


@dataclass(frozen=True)
class VscodeSession:
    id: str
    transcript_path: Path | None = None
    title: str | None = None
    cwd: str | None = None
    agent_name: str | None = None
    updated_at_ms: int = 0
    events: list[dict[str, Any]] = ()

    def with_events(self, events: list[dict[str, Any]]) -> "VscodeSession":
        return VscodeSession(
            id=self.id,
            transcript_path=self.transcript_path,
            title=self.title,
            cwd=self.cwd,
            agent_name=self.agent_name,
            updated_at_ms=self.updated_at_ms,
            events=events,
        )


class VscodeStateReader:
    def __init__(
        self,
        user_dir: Path | None = None,
        done_timeout_seconds: float = 300.0,
        active_window_seconds: float = 300.0,
        now_ms: Callable[[], int] | None = None,
    ) -> None:
        self.user_dir = Path(user_dir or default_vscode_user_dir()).expanduser()
        self.done_timeout_ms = int(done_timeout_seconds * 1000)
        self.active_window_ms = int(active_window_seconds * 1000)
        self._now_ms = now_ms or now_ms_monotonic

    def current_status(self, limit: int = 12) -> StatusSnapshot:
        try:
            sessions = self._read_sessions(max(1, min(100, limit)))
        except Exception as exc:
            return StatusSnapshot(
                Status.FAILED_OFFLINE,
                f"VS Code state unavailable: {exc}",
                activity="FAILED",
                backend="vscode",
            )

        if not sessions:
            return StatusSnapshot(Status.IDLE, "No VS Code agent sessions found.", activity="IDLE", backend="vscode")

        now = self._now_ms()
        snapshots = [
            summarize_session(
                session,
                now,
                self.done_timeout_ms,
                self.active_window_ms,
            )
            for session in sessions
        ]
        return replace(
            max(snapshots, key=vscode_status_sort_key),
            backend="vscode",
        )

    def _read_sessions(self, limit: int) -> list[VscodeSession]:
        user_dir = self.user_dir / "User"
        transcripts_root = user_dir / "workspaceStorage"
        if not transcripts_root.exists():
            raise FileNotFoundError(transcripts_root)

        files = self._session_paths(transcripts_root, user_dir)
        files.sort(key=_file_mtime_ms, reverse=True)

        metadata = read_session_store(user_dir / SESSION_STORE_DB)

        sessions: list[VscodeSession] = []
        seen: set[str] = set()
        for path in files:
            session_id = path.stem
            if session_id in seen:
                continue
            seen.add(session_id)
            events = self._session_events(path)
            meta = metadata.get(session_id, {})
            updated_at_ms = max(
                _file_mtime_ms(path),
                latest_event_ms(events),
                parse_time_ms(meta.get("updated_at")),
            )
            sessions.append(
                VscodeSession(
                    id=session_id,
                    transcript_path=path,
                    title=string_or_none(meta.get("summary")),
                    cwd=string_or_none(meta.get("cwd")),
                    agent_name=string_or_none(meta.get("agent_name")),
                    updated_at_ms=updated_at_ms,
                ).with_events(events)
            )
            if len(sessions) >= limit:
                break
        return sessions

    def _session_paths(self, transcripts_root: Path, user_dir: Path) -> list[Path]:
        paths = list(transcripts_root.glob(TRANSCRIPTS_GLOB))
        paths.extend(transcripts_root.glob(CHAT_SESSIONS_GLOB))
        for path in user_dir.glob(EMPTY_WINDOW_GLOB):
            paths.append(path)
        return paths

    def _session_events(self, path: Path) -> list[dict[str, Any]]:
        if _is_transcript_path(path):
            return read_jsonl_tail(path)
        return snapshot_events(read_copilot_session_state(path))


def summarize_session(
    session: VscodeSession,
    now_ms: int,
    done_timeout_ms: int,
    active_window_ms: int,
) -> StatusSnapshot:
    title = session.title or session.agent_name or session.cwd or session.id[:8]
    has_recent_activity = session.updated_at_ms > 0 and now_ms - session.updated_at_ms <= active_window_ms

    open_tool = latest_open_tool(session.events)
    if open_tool and has_recent_activity:
        return StatusSnapshot(
            Status.WORKING,
            working_reason(open_tool),
            session.id,
            title,
            open_tool["timestamp_at_ms"],
            activity_for_tool(open_tool["tool_name"], open_tool["arguments"]),
        )

    active_at_ms = in_progress_round_ms(session.events)
    if active_at_ms and has_recent_activity:
        station = latest_tool_request(session.events)
        activity = activity_for_tool_request(station) if station else "THINKING"
        return StatusSnapshot(
            Status.WORKING,
            "VS Code agent turn is running.",
            session.id,
            title,
            active_at_ms,
            activity,
        )

    completed_at = latest_turn_end_ms(session.events)
    if completed_at and now_ms - completed_at <= done_timeout_ms:
        return StatusSnapshot(
            Status.DONE,
            "Latest VS Code turn completed recently.",
            session.id,
            title,
            completed_at,
            "DONE",
        )

    return StatusSnapshot(Status.IDLE, "No active VS Code agent work.", session.id, title, session.updated_at_ms, "IDLE")


def latest_open_tool(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    started: dict[str, dict[str, Any]] = {}
    for event in events:
        event_type = event.get("type")
        data = as_dict(event.get("data"))
        tool_call_id = string_value(data.get("toolCallId"))
        if not tool_call_id:
            continue
        if event_type == "tool.execution_start":
            started[tool_call_id] = {
                "tool_call_id": tool_call_id,
                "tool_name": string_value(data.get("toolName")) or "tool",
                "arguments": as_dict(data.get("arguments")),
                "timestamp_at_ms": event_time_ms(event),
            }
        elif event_type == "tool.execution_complete":
            started.pop(tool_call_id, None)
    if not started:
        return None
    return max(started.values(), key=lambda item: item["timestamp_at_ms"])


def in_progress_round_ms(events: list[dict[str, Any]]) -> int | None:
    last_turn_end_idx = -1
    last_message_idx = -1
    last_message_ms = 0
    last_user_idx = -1
    last_user_ms = 0
    for index, event in enumerate(events):
        event_type = event.get("type")
        if event_type == "assistant.turn_end":
            last_turn_end_idx = index
        elif event_type == "assistant.message":
            last_message_idx = index
            last_message_ms = event_time_ms(event)
        elif event_type == "user.message":
            last_user_idx = index
            last_user_ms = event_time_ms(event)
    if last_message_idx > last_turn_end_idx:
        return last_message_ms
    if last_user_idx > last_turn_end_idx:
        return last_user_ms
    return None


def latest_tool_request(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    latest: dict[str, Any] | None = None
    for event in events:
        event_type = event.get("type")
        data = as_dict(event.get("data"))
        if event_type != "assistant.message":
            continue
        requests = data.get("toolRequests")
        if not isinstance(requests, list) or not requests:
            continue
        for request in requests:
            request = as_dict(request)
            name = string_value(request.get("name"))
            if not name:
                continue
            latest = {
                "tool_name": name,
                "arguments": as_dict(request.get("arguments")),
                "timestamp_at_ms": event_time_ms(event),
            }
    return latest


def latest_turn_end_ms(events: list[dict[str, Any]]) -> int | None:
    for event in reversed(events):
        if event.get("type") == "assistant.turn_end":
            return event_time_ms(event)
    return None


def working_reason(tool: dict[str, Any]) -> str:
    explanation = string_value(tool["arguments"].get("explanation"))
    tool_name = tool["tool_name"]
    if explanation:
        return f"VS Code agent is {tool_name}: {explanation}"
    return f"VS Code agent is running {tool_name}."


def activity_for_tool(tool_name: str, arguments: dict[str, Any]) -> str:
    name = tool_name.lower()
    if any(term in name for term in ("terminal", "bash", "shell", "exec_command", "shell_command")):
        return activity_for_command(arguments)
    if any(term in name for term in ("apply_patch", "create_file", "edit_file", "write_file", "delete_file", "rename")):
        return "PATCHING"
    if any(term in name for term in ("read_file", "list_dir", "file_search", "grep_search", "grep", "glob", "find")):
        return "READING FILES"
    if any(term in name for term in ("web_search", "fetch_webpage", "browser", "http")):
        return "SEARCHING WEB"
    if "github" in name or "pull_request" in name:
        return "CHECKING GITHUB"
    return "USING TOOL"


def activity_for_tool_request(request: dict[str, Any]) -> str:
    return activity_for_tool(request["tool_name"], request["arguments"])


def read_session_store(db_path: Path) -> dict[str, dict[str, Any]]:
    if not db_path.exists():
        return {}
    uri = f"file:{db_path}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=5)
    except sqlite3.Error:
        return {}
    try:
        connection.row_factory = sqlite3.Row
        available = {row["name"] for row in connection.execute("pragma table_info(sessions)")}
        columns = [column for column in ("id", "cwd", "agent_name", "summary", "updated_at") if column in available]
        if "id" not in columns:
            return {}
        rows = connection.execute(f"select {', '.join(columns)} from sessions").fetchall()
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            entry = {column: row[column] for column in columns}
            session_id = string_or_none(entry.get("id"))
            if session_id:
                result[session_id] = entry
        return result
    except sqlite3.Error:
        return {}
    finally:
        connection.close()


def vscode_status_sort_key(snapshot: StatusSnapshot) -> tuple[int, int, int]:
    updated_at_ms = snapshot.updated_at_ms or 0
    return 2, updated_at_ms, status_priority(snapshot.status)


def latest_event_ms(events: list[dict[str, Any]]) -> int:
    for event in reversed(events):
        timestamp = event_time_ms(event)
        if timestamp:
            return timestamp
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


def parse_time_ms(value: Any) -> int:
    if not isinstance(value, str) or not value:
        return 0
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return int(parsed.timestamp() * 1000)


def _file_mtime_ms(path: Path) -> int:
    try:
        return int(path.stat().st_mtime * 1000)
    except OSError:
        return 0


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def string_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _is_transcript_path(path: Path) -> bool:
    parts = path.parts
    return "GitHub.copilot-chat" in parts and "transcripts" in parts


def read_copilot_session_state(file_path: Path) -> dict[str, Any]:
    ops = read_jsonl_tail(file_path)
    state: dict[str, Any] = {}
    for op in ops:
        kind = op.get("kind")
        value = op.get("v")
        keys = op.get("k")
        if kind == 0 and isinstance(value, dict):
            state = value
        elif kind in (1, 2) and isinstance(keys, list) and keys:
            _set_path(state, keys, value)
    return state


def _set_path(state: dict[str, Any], keys: list[Any], value: Any) -> None:
    if not keys:
        return
    node = state
    for key in keys[:-1]:
        if isinstance(key, str):
            child = node.get(key)
            if not isinstance(child, dict):
                child = {}
                node[key] = child
            node = child
        elif isinstance(key, int) and isinstance(node, list):
            while len(node) <= key:
                node.append({})
            node = node[key]
        else:
            return
    node[keys[-1]] = value


def snapshot_events(state: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    requests = _as_list(state.get("requests"))
    for request in requests:
        request = as_dict(request)
        ts = _as_int(request.get("timestamp"))
        response_ts = _as_int(request.get("responseTimestamp")) or ts
        if not ts:
            continue
        events.append(_mk_event("user.message", ts, {"content": _message_text(request)}))
        response = _as_list(request.get("response"))
        assistant_text = "".join(
            item.get("value")
            for item in response
            if isinstance(item, dict) and isinstance(item.get("value"), str)
        )
        events.append(_mk_event("assistant.message", response_ts, {"content": assistant_text}))
        for item in response:
            item = as_dict(item)
            if item.get("kind") != "toolInvocationSerialized":
                continue
            call_id = string_value(item.get("toolCallId"))
            tool_name = string_value(item.get("toolId")) or "tool"
            if not call_id:
                continue
            events.append(
                _mk_event(
                    "tool.execution_start",
                    response_ts,
                    {"toolCallId": call_id, "toolName": tool_name, "arguments": {}},
                )
            )
            if item.get("isComplete"):
                events.append(_mk_event("tool.execution_complete", response_ts, {"toolCallId": call_id}))
        completed_at = _as_int(as_dict(request.get("modelState")).get("completedAt"))
        if completed_at:
            events.append(_mk_event("assistant.turn_end", completed_at, {"turnId": "turn"}))
    if requests and _as_list(state.get("pendingRequests")):
        last_ts = _as_int(as_dict(requests[-1]).get("responseTimestamp"))
        if not last_ts:
            last_ts = _as_int(as_dict(requests[-1]).get("timestamp"))
        events.append(_mk_event("assistant.message", last_ts, {"content": "queued"}))
    return events


def _mk_event(event_type: str, ms: int, data: dict[str, Any]) -> dict[str, Any]:
    return {"type": event_type, "data": data, "timestamp": iso_from_ms(ms)}


def iso_from_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def _message_text(request: dict[str, Any]) -> str:
    message = as_dict(request.get("message"))
    return string_value(message.get("text"))


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _as_int(value: Any) -> int:
    return value if isinstance(value, int) else 0


def now_ms_monotonic() -> int:
    import time

    return int(time.time() * 1000)