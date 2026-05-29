from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pixelpet.codex_state import CodexStateReader
from pixelpet.status import Status

NOW_MS = 1_700_000_000_000


class CodexStateReaderTest(unittest.TestCase):
    def test_permission_required_beats_working(self) -> None:
        with fixture() as fx:
            rollout = fx.rollout(
                event("event_msg", {"type": "task_started"}, NOW_MS - 5_000),
                event(
                    "response_item",
                    {
                        "type": "function_call",
                        "call_id": "call-1",
                        "name": "exec_command",
                        "arguments": json.dumps(
                            {
                                "cmd": "git pull",
                                "sandbox_permissions": "require_escalated",
                                "justification": "Allow network pull?",
                            }
                        ),
                    },
                    NOW_MS - 3_000,
                ),
            )
            fx.thread("t1", rollout)

            status = fx.reader().current_status()

            self.assertEqual(status.status, Status.PERMISSION_REQUIRED)
            self.assertIn("Allow network pull", status.reason)

    def test_needs_input_for_request_user_input(self) -> None:
        with fixture() as fx:
            rollout = fx.rollout(
                event(
                    "response_item",
                    {
                        "type": "function_call",
                        "call_id": "call-2",
                        "name": "request_user_input",
                        "arguments": {
                            "questions": [
                                {"question": "Which pet should be active?"}
                            ]
                        },
                    },
                    NOW_MS - 2_000,
                ),
            )
            fx.thread("t1", rollout)

            status = fx.reader().current_status()

            self.assertEqual(status.status, Status.NEEDS_INPUT)
            self.assertIn("Which pet", status.reason)

    def test_done_clears_after_timeout(self) -> None:
        with fixture() as fx:
            recent = fx.rollout(
                event("event_msg", {"type": "task_started"}, NOW_MS - 260_000),
                event("event_msg", {"type": "task_complete"}, NOW_MS - 240_000),
            )
            fx.thread("recent", recent, updated_at_ms=NOW_MS - 240_000)

            self.assertEqual(fx.reader().current_status().status, Status.DONE)

        with fixture() as fx:
            old = fx.rollout(
                event("event_msg", {"type": "task_started"}, NOW_MS - 400_000),
                event("event_msg", {"type": "task_complete"}, NOW_MS - 360_000),
            )
            fx.thread("old", old, updated_at_ms=NOW_MS - 360_000)

            self.assertEqual(fx.reader().current_status().status, Status.IDLE)

    def test_aborted_turn_is_failed(self) -> None:
        with fixture() as fx:
            rollout = fx.rollout(
                event("event_msg", {"type": "task_started"}, NOW_MS - 5_000),
                event("event_msg", {"type": "turn_aborted", "reason": "interrupted"}, NOW_MS - 1_000),
            )
            fx.thread("t1", rollout)

            status = fx.reader().current_status()

            self.assertEqual(status.status, Status.FAILED_OFFLINE)
            self.assertIn("interrupted", status.reason)

    def test_cli_thread_is_ignored(self) -> None:
        with fixture() as fx:
            rollout = fx.rollout(
                event(
                    "response_item",
                    {
                        "type": "function_call",
                        "call_id": "call-cli",
                        "name": "exec_command",
                        "arguments": {"sandbox_permissions": "require_escalated"},
                    },
                    NOW_MS - 2_000,
                )
            )
            fx.thread("cli", rollout, source="cli", thread_source="cli")

            self.assertEqual(fx.reader().current_status().status, Status.IDLE)

    def test_missing_db_is_failed_offline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reader = CodexStateReader(
                codex_home=Path(tmp),
                state_db_path=Path(tmp) / "missing.sqlite",
                now_ms=lambda: NOW_MS,
            )

            self.assertEqual(reader.current_status().status, Status.FAILED_OFFLINE)


class Fixture:
    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "state_5.sqlite"
        self._setup_db()

    def __enter__(self) -> "Fixture":
        return self

    def __exit__(self, *args: object) -> None:
        self.tmp.cleanup()

    def _setup_db(self) -> None:
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                """
                create table threads (
                  id text,
                  rollout_path text,
                  cwd text,
                  title text,
                  preview text,
                  source text,
                  thread_source text,
                  agent_nickname text,
                  cli_version text,
                  git_branch text,
                  updated_at integer,
                  updated_at_ms integer,
                  archived integer
                )
                """
            )

    def rollout(self, *events: dict[str, object]) -> Path:
        path = self.root / f"rollout-{len(list(self.root.glob('rollout-*')))}.jsonl"
        path.write_text("\n".join(json.dumps(item) for item in events) + "\n", encoding="utf-8")
        return path

    def thread(
        self,
        thread_id: str,
        rollout_path: Path,
        source: str = "vscode",
        thread_source: str = "user",
        updated_at_ms: int = NOW_MS - 1_000,
    ) -> None:
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                """
                insert into threads values (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    thread_id,
                    str(rollout_path),
                    str(self.root),
                    "Test thread",
                    "Preview",
                    source,
                    thread_source,
                    None,
                    "test",
                    "main",
                    updated_at_ms // 1000,
                    updated_at_ms,
                    0,
                ),
            )

    def reader(self) -> CodexStateReader:
        return CodexStateReader(
            codex_home=self.root,
            state_db_path=self.db,
            done_timeout_seconds=300,
            active_window_seconds=300,
            now_ms=lambda: NOW_MS,
        )


def fixture() -> Fixture:
    return Fixture()


def event(event_type: str, payload: dict[str, object], timestamp_ms: int) -> dict[str, object]:
    timestamp = datetime.fromtimestamp(timestamp_ms / 1000, timezone.utc).isoformat().replace("+00:00", "Z")
    return {"timestamp": timestamp, "type": event_type, "payload": payload}


if __name__ == "__main__":
    unittest.main()

