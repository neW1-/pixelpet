from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .assistant_state import StatusSnapshot
from .codex_state import activity_for_command
from .config import default_opencode_db_path
from .status import Status, status_priority


@dataclass(frozen=True)
class OpencodeSession:
    id: str
    title: str | None
    directory: str | None
    time_updated: int


@dataclass(frozen=True)
class OpencodeMessage:
    id: str
    session_id: str
    time_created: int
    time_updated: int
    data: dict[str, Any]


@dataclass(frozen=True)
class OpencodePart:
    id: str
    session_id: str
    message_id: str
    time_created: int
    time_updated: int
    data: dict[str, Any]


class OpencodeStateReader:
    def __init__(
        self,
        db_path: Path | None = None,
        done_timeout_seconds: float = 300.0,
        active_window_seconds: float = 300.0,
        now_ms: Callable[[], int] | None = None,
    ) -> None:
        self.db_path = db_path or default_opencode_db_path()
        self.done_timeout_ms = int(done_timeout_seconds * 1000)
        self.active_window_ms = int(active_window_seconds * 1000)
        self._now_ms = now_ms or now_ms_monotonic

    def current_status(self, limit: int = 12) -> StatusSnapshot:
        try:
            sessions, messages, parts = self._read_state(max(1, min(100, limit)))
        except Exception as exc:
            return StatusSnapshot(
                Status.FAILED_OFFLINE,
                f"OpenCode state unavailable: {exc}",
                activity="FAILED",
            )

        if not sessions:
            return StatusSnapshot(Status.IDLE, "No OpenCode sessions found.", activity="IDLE")

        now = self._now_ms()
        snapshots = [
            summarize_session(
                session,
                messages.get(session.id, []),
                parts.get(session.id, []),
                now,
                self.done_timeout_ms,
                self.active_window_ms,
            )
            for session in sessions
        ]
        return max(snapshots, key=opencode_status_sort_key)

    def _read_state(
        self,
        limit: int,
    ) -> tuple[list[OpencodeSession], dict[str, list[OpencodeMessage]], dict[str, list[OpencodePart]]]:
        db_path = self.db_path.expanduser()
        if not db_path.exists():
            raise FileNotFoundError(db_path)

        uri = f"file:{db_path}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            connection.row_factory = sqlite3.Row
            session_rows = connection.execute(
                """
                select id, title, directory, time_updated
                from session
                where time_archived is null
                order by time_updated desc
                limit ?
                """,
                (limit,),
            ).fetchall()
            sessions = [
                OpencodeSession(
                    id=string_or_none(row["id"]) or "",
                    title=string_or_none(row["title"]),
                    directory=string_or_none(row["directory"]),
                    time_updated=int_value(row["time_updated"]) or 0,
                )
                for row in session_rows
                if row["id"]
            ]
            session_ids = [session.id for session in sessions]
            return sessions, read_messages(connection, session_ids), read_parts(connection, session_ids)
        finally:
            connection.close()


def read_messages(connection: sqlite3.Connection, session_ids: list[str]) -> dict[str, list[OpencodeMessage]]:
    messages: dict[str, list[OpencodeMessage]] = {session_id: [] for session_id in session_ids}
    if not session_ids:
        return messages
    placeholders = ",".join("?" for _ in session_ids)
    rows = connection.execute(
        f"""
        select id, session_id, time_created, time_updated, data
        from message
        where session_id in ({placeholders})
        order by time_created asc, id asc
        """,
        session_ids,
    ).fetchall()
    for row in rows:
        session_id = string_or_none(row["session_id"])
        if not session_id:
            continue
        messages.setdefault(session_id, []).append(
            OpencodeMessage(
                id=string_or_none(row["id"]) or "",
                session_id=session_id,
                time_created=int_value(row["time_created"]) or 0,
                time_updated=int_value(row["time_updated"]) or 0,
                data=parse_json_object(row["data"]),
            )
        )
    return messages


def read_parts(connection: sqlite3.Connection, session_ids: list[str]) -> dict[str, list[OpencodePart]]:
    parts: dict[str, list[OpencodePart]] = {session_id: [] for session_id in session_ids}
    if not session_ids:
        return parts
    placeholders = ",".join("?" for _ in session_ids)
    rows = connection.execute(
        f"""
        select id, session_id, message_id, time_created, time_updated, data
        from part
        where session_id in ({placeholders})
        order by time_created asc, id asc
        """,
        session_ids,
    ).fetchall()
    for row in rows:
        session_id = string_or_none(row["session_id"])
        if not session_id:
            continue
        parts.setdefault(session_id, []).append(
            OpencodePart(
                id=string_or_none(row["id"]) or "",
                session_id=session_id,
                message_id=string_or_none(row["message_id"]) or "",
                time_created=int_value(row["time_created"]) or 0,
                time_updated=int_value(row["time_updated"]) or 0,
                data=parse_json_object(row["data"]),
            )
        )
    return parts


def summarize_session(
    session: OpencodeSession,
    messages: list[OpencodeMessage],
    parts: list[OpencodePart],
    now_ms: int,
    done_timeout_ms: int,
    active_window_ms: int,
) -> StatusSnapshot:
    updated_at_ms = max(
        [
            session.time_updated,
            *(message_time(message) for message in messages),
            *(part.time_updated for part in parts),
        ]
    )
    title = session.title or session.directory or session.id[:8]
    permission = latest_tool_part(parts, {"pending"})
    if permission:
        return StatusSnapshot(
            Status.PERMISSION_REQUIRED,
            permission_reason(permission),
            session.id,
            title,
            updated_at_ms,
            "NEEDS APPROVAL",
        )

    latest_assistant = latest_assistant_message(messages)
    if latest_assistant and (error := assistant_error(latest_assistant)):
        return StatusSnapshot(Status.FAILED_OFFLINE, error, session.id, title, updated_at_ms, "FAILED")

    running_tool = latest_tool_part(parts, {"running"})
    has_recent_activity = updated_at_ms > 0 and now_ms - updated_at_ms <= active_window_ms
    if running_tool and has_recent_activity:
        return StatusSnapshot(
            Status.WORKING,
            working_reason(running_tool),
            session.id,
            title,
            updated_at_ms,
            activity_for_tool(running_tool),
        )

    if latest_assistant and assistant_is_running(latest_assistant) and has_recent_activity:
        return StatusSnapshot(
            Status.WORKING,
            "OpenCode turn is running.",
            session.id,
            title,
            updated_at_ms,
            "THINKING",
        )

    if latest_assistant:
        completed_at = assistant_completed_at(latest_assistant)
        finish = string_or_none(latest_assistant.data.get("finish"))
        if completed_at and finish == "tool-calls" and has_recent_activity:
            return StatusSnapshot(
                Status.WORKING,
                "OpenCode turn is running tools.",
                session.id,
                title,
                completed_at,
                "USING TOOL",
            )
        if completed_at and now_ms - completed_at <= done_timeout_ms:
            return StatusSnapshot(
                Status.DONE,
                "Latest OpenCode turn completed recently.",
                session.id,
                title,
                completed_at,
                "DONE",
            )

    return StatusSnapshot(Status.IDLE, "No active OpenCode work.", session.id, title, updated_at_ms, "IDLE")


def latest_assistant_message(messages: list[OpencodeMessage]) -> OpencodeMessage | None:
    assistant_messages = [message for message in messages if message.data.get("role") == "assistant"]
    if not assistant_messages:
        return None
    return max(assistant_messages, key=message_time)


def latest_tool_part(parts: list[OpencodePart], statuses: set[str]) -> OpencodePart | None:
    tool_parts = [
        part
        for part in parts
        if part.data.get("type") == "tool" and tool_state_status(part) in statuses
    ]
    if not tool_parts:
        return None
    return max(tool_parts, key=lambda part: part.time_updated)


def permission_reason(part: OpencodePart) -> str:
    state = as_dict(part.data.get("state"))
    title = string_or_none(state.get("title"))
    tool = string_or_none(part.data.get("tool"))
    if title:
        return f"OpenCode is waiting for approval: {title}"
    if tool:
        return f"OpenCode is waiting for approval to run {tool}."
    return "OpenCode is waiting for approval."


def working_reason(part: OpencodePart) -> str:
    state = as_dict(part.data.get("state"))
    title = string_or_none(state.get("title"))
    tool = string_or_none(part.data.get("tool"))
    if title:
        return f"OpenCode is running: {title}"
    if tool:
        return f"OpenCode is running {tool}."
    return "OpenCode is working."


def activity_for_tool(part: OpencodePart) -> str:
    tool = string_or_none(part.data.get("tool")).lower()
    state = as_dict(part.data.get("state"))
    command = command_for_tool_state(state)
    if command:
        return activity_for_command({"cmd": command})
    if any(term in tool for term in ("bash", "shell", "terminal")):
        return "RUNNING CMD"
    if any(term in tool for term in ("edit", "write", "patch")):
        return "PATCHING"
    if any(term in tool for term in ("read", "file", "grep", "glob", "list")):
        return "READING FILES"
    if any(term in tool for term in ("search", "web", "fetch")):
        return "SEARCHING WEB"
    if "todo" in tool:
        return "PLANNING"
    return "USING TOOL"


def command_for_tool_state(state: dict[str, Any]) -> str:
    tool_input = as_dict(state.get("input"))
    return (
        string_value(tool_input.get("cmd"))
        or string_value(tool_input.get("command"))
        or string_value(tool_input.get("description"))
    )


def assistant_error(message: OpencodeMessage) -> str | None:
    error = as_dict(message.data.get("error"))
    if not error:
        return None
    data = as_dict(error.get("data"))
    detail = string_or_none(data.get("message")) or string_or_none(error.get("name"))
    return detail or "Latest OpenCode turn failed."


def assistant_is_running(message: OpencodeMessage) -> bool:
    return message.data.get("role") == "assistant" and assistant_completed_at(message) is None and not assistant_error(message)


def assistant_completed_at(message: OpencodeMessage) -> int | None:
    time_data = as_dict(message.data.get("time"))
    return int_value(time_data.get("completed"))


def message_time(message: OpencodeMessage) -> int:
    completed = assistant_completed_at(message)
    created = int_value(as_dict(message.data.get("time")).get("created"))
    return max(message.time_updated, completed or 0, created or 0)


def tool_state_status(part: OpencodePart) -> str:
    return string_value(as_dict(part.data.get("state")).get("status")).lower()


def opencode_status_sort_key(snapshot: StatusSnapshot) -> tuple[int, int, int]:
    updated_at_ms = snapshot.updated_at_ms or 0
    if snapshot.status in {Status.PERMISSION_REQUIRED, Status.NEEDS_INPUT}:
        return 3, status_priority(snapshot.status), updated_at_ms
    return 2, updated_at_ms, status_priority(snapshot.status)


def parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def string_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def int_value(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return None
    return None


def now_ms_monotonic() -> int:
    import time

    return int(time.time() * 1000)
