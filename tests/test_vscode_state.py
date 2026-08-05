from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pixelpet.status import Status
from pixelpet.vscode_state import VscodeStateReader

NOW_MS = 1_780_000_000_000


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def event(event_type: str, data: dict[str, Any], ms: int) -> dict[str, Any]:
    return {"type": event_type, "data": data, "timestamp": iso(ms)}


def turn_start(ms: int, turn_id: str = "1") -> dict[str, Any]:
    return event("assistant.turn_start", {"turnId": turn_id}, ms)


def turn_end(ms: int, turn_id: str = "1") -> dict[str, Any]:
    return event("assistant.turn_end", {"turnId": turn_id}, ms)


def tool_start(tool_name: str, call_id: str, arguments: dict[str, Any], ms: int) -> dict[str, Any]:
    return event(
        "tool.execution_start",
        {"toolCallId": call_id, "toolName": tool_name, "arguments": arguments},
        ms,
    )


def tool_complete(call_id: str, ms: int, success: bool = True) -> dict[str, Any]:
    return event("tool.execution_complete", {"toolCallId": call_id, "success": success}, ms)


def user_message(ms: int) -> dict[str, Any]:
    return event("user.message", {"content": "hello"}, ms)


class Fixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.transcripts = (
            root / "User" / "workspaceStorage" / "ws1" / "GitHub.copilot-chat" / "transcripts"
        )
        self.transcripts.mkdir(parents=True)

    def session(self, session_id: str, events: list[dict[str, Any]]) -> None:
        path = self.transcripts / f"{session_id}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for entry in events:
                handle.write(json.dumps(entry) + "\n")

    def session_store(self, rows: list[tuple[str, str, str, str, str]]) -> None:
        db_dir = self.root / "User" / "globalStorage" / "github.copilot-chat"
        db_dir.mkdir(parents=True)
        connection = sqlite3.connect(db_dir / "session-store.db")
        connection.execute(
            "create table sessions (id text, cwd text, agent_name text, summary text, updated_at text)"
        )
        connection.executemany("insert into sessions values (?,?,?,?,?)", rows)
        connection.commit()
        connection.close()

    def empty_window(self, session_id: str, ops: list[dict[str, Any]]) -> None:
        path = self.root / "User" / "globalStorage" / "emptyWindowChatSessions" / f"{session_id}.jsonl"
        path.parent.mkdir(parents=True)
        with path.open("w", encoding="utf-8") as handle:
            for op in ops:
                handle.write(json.dumps(op) + "\n")

    def mutation_log(self, session_id: str, ops: list[dict[str, Any]]) -> None:
        path = self.root / "User" / "workspaceStorage" / "ws2" / "chatSessions" / f"{session_id}.jsonl"
        path.parent.mkdir(parents=True)
        with path.open("w", encoding="utf-8") as handle:
            for op in ops:
                handle.write(json.dumps(op) + "\n")

    def reader(self) -> VscodeStateReader:
        return VscodeStateReader(user_dir=self.root, now_ms=lambda: NOW_MS)

    def __enter__(self) -> "Fixture":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def fixture() -> Fixture:
    return Fixture(Path(tempfile.mkdtemp()))


class VscodeStateReaderTest(unittest.TestCase):
    def test_no_sessions_is_idle(self) -> None:
        with fixture() as fx:
            status = fx.reader().current_status()

            self.assertEqual(status.status, Status.IDLE)
            self.assertEqual(status.activity, "IDLE")

    def test_missing_user_dir_is_failed_offline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reader = VscodeStateReader(
                user_dir=Path(tmp) / "missing",
                now_ms=lambda: NOW_MS,
            )

            status = reader.current_status()

            self.assertEqual(status.status, Status.FAILED_OFFLINE)
            self.assertIn("VS Code state unavailable", status.reason)

    def test_open_terminal_tool_is_working_with_activity(self) -> None:
        with fixture() as fx:
            fx.session(
                "s1",
                [
                    user_message(NOW_MS - 60_000),
                    turn_start(NOW_MS - 60_000),
                    tool_start(
                        "run_in_terminal",
                        "call_1",
                        {"command": "python -m unittest discover -s tests"},
                        NOW_MS - 60_000,
                    ),
                ],
            )

            status = fx.reader().current_status()

            self.assertEqual(status.status, Status.WORKING)
            self.assertEqual(status.activity, "RUNNING TESTS")
            self.assertIn("run_in_terminal", status.reason)

    def test_open_apply_patch_is_patching(self) -> None:
        with fixture() as fx:
            fx.session(
                "s1",
                [
                    turn_start(NOW_MS - 30_000),
                    tool_start(
                        "apply_patch",
                        "call_2",
                        {"explanation": "Fix the config"},
                        NOW_MS - 30_000,
                    ),
                ],
            )

            status = fx.reader().current_status()

            self.assertEqual(status.status, Status.WORKING)
            self.assertEqual(status.activity, "PATCHING")
            self.assertIn("Fix the config", status.reason)

    def test_open_turn_without_tools_is_thinking(self) -> None:
        with fixture() as fx:
            fx.session("s1", [user_message(NOW_MS - 10_000), turn_start(NOW_MS - 10_000)])

            status = fx.reader().current_status()

            self.assertEqual(status.status, Status.WORKING)
            self.assertEqual(status.activity, "THINKING")

    def test_open_turn_with_pending_tool_request_maps_activity(self) -> None:
        with fixture() as fx:
            fx.session(
                "s1",
                [
                    user_message(NOW_MS - 10_000),
                    turn_start(NOW_MS - 10_000),
                    event(
                        "assistant.message",
                        {
                            "messageId": "m1",
                            "content": "checking",
                            "toolRequests": [
                                {
                                    "toolCallId": "call_3",
                                    "name": "read_file",
                                    "arguments": {"filePath": "/tmp/x.py"},
                                }
                            ],
                        },
                        NOW_MS - 10_000,
                    ),
                ],
            )

            status = fx.reader().current_status()

            self.assertEqual(status.status, Status.WORKING)
            self.assertEqual(status.activity, "READING FILES")

    def test_recent_completed_turn_is_done(self) -> None:
        with fixture() as fx:
            fx.session(
                "s1",
                [
                    user_message(NOW_MS - 5_000),
                    turn_start(NOW_MS - 5_000),
                    tool_start("read_file", "call_4", {"filePath": "/tmp/a.py"}, NOW_MS - 5_000),
                    tool_complete("call_4", NOW_MS - 4_000),
                    turn_end(NOW_MS - 4_000),
                ],
            )

            status = fx.reader().current_status()

            self.assertEqual(status.status, Status.DONE)

    def test_finished_turn_with_placeholder_next_round_is_done(self) -> None:
        with fixture() as fx:
            fx.session(
                "s1",
                [
                    user_message(NOW_MS - 10_000),
                    turn_start(NOW_MS - 10_000, turn_id="0"),
                    tool_start("run_in_terminal", "call_x", {"command": "ls"}, NOW_MS - 10_000),
                    tool_complete("call_x", NOW_MS - 9_000),
                    turn_end(NOW_MS - 9_000, turn_id="0"),
                    turn_start(NOW_MS - 9_000, turn_id="1"),
                ],
            )

            status = fx.reader().current_status()

            self.assertEqual(status.status, Status.DONE)
            self.assertEqual(status.activity, "DONE")

    def test_working_placeholder_is_not_mistaken_for_done(self) -> None:
        with fixture() as fx:
            fx.session(
                "s1",
                [
                    turn_start(NOW_MS - 20_000, turn_id="0"),
                    tool_start("run_in_terminal", "call_y", {"command": "terraform plan"}, NOW_MS - 20_000),
                ],
            )

            status = fx.reader().current_status()

            self.assertEqual(status.status, Status.WORKING)

    def test_stale_session_is_idle(self) -> None:
        with fixture() as fx:
            fx.session(
                "s1",
                [
                    user_message(NOW_MS - 1_000_000),
                    turn_start(NOW_MS - 1_000_000),
                    tool_start("read_file", "call_5", {"filePath": "/tmp/a.py"}, NOW_MS - 1_000_000),
                    tool_complete("call_5", NOW_MS - 999_000),
                    turn_end(NOW_MS - 999_000),
                ],
            )

            status = fx.reader().current_status()

            self.assertEqual(status.status, Status.IDLE)

    def test_most_recent_active_session_wins(self) -> None:
        with fixture() as fx:
            fx.session(
                "old",
                [
                    turn_start(NOW_MS - 120_000),
                    tool_start("apply_patch", "call_6", {}, NOW_MS - 120_000),
                ],
            )
            fx.session(
                "new",
                [
                    user_message(NOW_MS - 10_000),
                    turn_start(NOW_MS - 10_000),
                    tool_start("run_in_terminal", "call_7", {"command": "terraform plan"}, NOW_MS - 10_000),
                ],
            )

            status = fx.reader().current_status()

            self.assertEqual(status.thread_id, "new")
            self.assertEqual(status.status, Status.WORKING)

    def test_session_store_metadata_enriches_title(self) -> None:
        with fixture() as fx:
            fx.session(
                "s1",
                [
                    user_message(NOW_MS - 10_000),
                    turn_start(NOW_MS - 10_000),
                    tool_start("run_in_terminal", "call_8", {"command": "ls"}, NOW_MS - 10_000),
                ],
            )
            fx.session_store(
                [
                    ("s1", "/tmp/project", "GitHub Copilot Chat", "Fix the terraform drift", iso(NOW_MS)),
                ]
            )

            status = fx.reader().current_status()

            self.assertEqual(status.title, "Fix the terraform drift")
            self.assertEqual(status.status, Status.WORKING)

    def test_missing_session_store_still_works(self) -> None:
        with fixture() as fx:
            fx.session(
                "s1",
                [
                    turn_start(NOW_MS - 10_000),
                    tool_start("run_in_terminal", "call_9", {"command": "ls"}, NOW_MS - 10_000),
                ],
            )

            status = fx.reader().current_status()

            self.assertEqual(status.status, Status.WORKING)
            self.assertEqual(status.title, "s1")

    def test_completed_open_tool_pair_is_not_working(self) -> None:
        with fixture() as fx:
            fx.session(
                "s1",
                [
                    user_message(NOW_MS - 400_000),
                    turn_start(NOW_MS - 400_000),
                    tool_start("run_in_terminal", "call_10", {"command": "ls"}, NOW_MS - 400_000),
                    tool_complete("call_10", NOW_MS - 399_000),
                    turn_end(NOW_MS - 399_000),
                ],
            )

            status = fx.reader().current_status()

            self.assertEqual(status.status, Status.IDLE)

    def test_empty_window_snapshot_with_open_tool_is_working(self) -> None:
        with fixture() as fx:
            fx.empty_window(
                "ew1",
                [
                    {
                        "kind": 0,
                        "v": {
                            "sessionId": "ew1",
                            "requests": [
                                {
                                    "requestId": "req_1",
                                    "timestamp": NOW_MS - 30_000,
                                    "responseTimestamp": NOW_MS - 30_000,
                                    "modelState": {},
                                    "message": {"text": "grill me"},
                                    "response": [
                                        {"value": "I'll start grilling."},
                                        {
                                            "kind": "toolInvocationSerialized",
                                            "toolCallId": "call_open",
                                            "toolId": "run_in_terminal",
                                            "isComplete": False,
                                        },
                                    ],
                                }
                            ],
                        },
                    },
                ],
            )

            status = fx.reader().current_status()

            self.assertEqual(status.status, Status.WORKING)
            self.assertIn("run_in_terminal", status.reason)

    def test_empty_window_snapshot_completed_turn_is_done(self) -> None:
        with fixture() as fx:
            fx.empty_window(
                "ew2",
                [
                    {
                        "kind": 0,
                        "v": {
                            "sessionId": "ew2",
                            "requests": [
                                {
                                    "requestId": "req_2",
                                    "timestamp": NOW_MS - 60_000,
                                    "responseTimestamp": NOW_MS - 60_000,
                                    "modelState": {"completedAt": NOW_MS - 60_000},
                                    "message": {"text": "hi"},
                                    "response": [
                                        {
                                            "kind": "toolInvocationSerialized",
                                            "toolCallId": "call_done",
                                            "toolId": "read_file",
                                            "isComplete": True,
                                        }
                                    ],
                                }
                            ],
                        },
                    },
                ],
            )

            status = fx.reader().current_status()

            self.assertEqual(status.status, Status.DONE)

    def test_mutation_log_session_detected(self) -> None:
        with fixture() as fx:
            fx.mutation_log(
                "ml1",
                [
                    {"kind": 0, "v": {"sessionId": "ml1", "requests": []}},
                    {"kind": 2, "k": ["requests"], "v": [{"requestId": "req_3", "timestamp": NOW_MS - 20_000}]},
                    {"kind": 2, "k": ["pendingRequests"], "v": [{"id": "p1"}]},
                ],
            )

            status = fx.reader().current_status()

            self.assertEqual(status.status, Status.WORKING)


if __name__ == "__main__":
    unittest.main()
