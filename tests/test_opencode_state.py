from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pixelpet.opencode_state import OpencodeStateReader
from pixelpet.status import Status

NOW_MS = 1_780_000_000_000


class OpencodeStateReaderTest(unittest.TestCase):
    def test_no_sessions_is_idle(self) -> None:
        with fixture() as fx:
            status = fx.reader().current_status()

            self.assertEqual(status.status, Status.IDLE)
            self.assertEqual(status.activity, "IDLE")

    def test_missing_db_is_failed_offline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reader = OpencodeStateReader(
                db_path=Path(tmp) / "missing.db",
                now_ms=lambda: NOW_MS,
            )

            status = reader.current_status()

            self.assertEqual(status.status, Status.FAILED_OFFLINE)
            self.assertIn("OpenCode state unavailable", status.reason)

    def test_pending_tool_is_permission_required(self) -> None:
        with fixture() as fx:
            fx.session("s1")
            fx.message("s1", assistant_message(completed=False))
            fx.part(
                "s1",
                tool_part(
                    "bash",
                    "pending",
                    {"command": "git push"},
                    title="Run git push",
                ),
            )

            status = fx.reader().current_status()

            self.assertEqual(status.status, Status.PERMISSION_REQUIRED)
            self.assertEqual(status.activity, "NEEDS APPROVAL")
            self.assertIn("Run git push", status.reason)

    def test_running_tool_sets_working_activity(self) -> None:
        with fixture() as fx:
            fx.session("s1")
            fx.message("s1", assistant_message(completed=False))
            fx.part(
                "s1",
                tool_part(
                    "bash",
                    "running",
                    {"command": "python -m unittest discover -s tests"},
                    title="Run tests",
                ),
            )

            status = fx.reader().current_status()

            self.assertEqual(status.status, Status.WORKING)
            self.assertEqual(status.activity, "RUNNING TESTS")

    def test_recent_completed_assistant_is_done(self) -> None:
        with fixture() as fx:
            fx.session("s1", updated_at=NOW_MS - 1_000)
            fx.message("s1", assistant_message(completed=True, completed_at=NOW_MS - 1_000))

            status = fx.reader().current_status()

            self.assertEqual(status.status, Status.DONE)
            self.assertEqual(status.activity, "DONE")

    def test_stale_completed_assistant_is_idle(self) -> None:
        with fixture() as fx:
            fx.session("s1", updated_at=NOW_MS - 400_000)
            fx.message(
                "s1",
                assistant_message(
                    completed=True,
                    created_at=NOW_MS - 420_000,
                    completed_at=NOW_MS - 400_000,
                ),
                created_at=NOW_MS - 420_000,
                updated_at=NOW_MS - 400_000,
            )

            status = fx.reader().current_status()

            self.assertEqual(status.status, Status.IDLE)

    def test_assistant_error_is_failed(self) -> None:
        with fixture() as fx:
            fx.session("s1")
            fx.message(
                "s1",
                assistant_message(
                    completed=True,
                    error={"name": "MessageAbortedError", "data": {"message": "Aborted"}},
                ),
            )

            status = fx.reader().current_status()

            self.assertEqual(status.status, Status.FAILED_OFFLINE)
            self.assertEqual(status.activity, "FAILED")
            self.assertIn("Aborted", status.reason)


class Fixture:
    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "opencode.db"
        self._message_count = 0
        self._part_count = 0
        self._setup_db()

    def __enter__(self) -> "Fixture":
        return self

    def __exit__(self, *args: object) -> None:
        self.tmp.cleanup()

    def _setup_db(self) -> None:
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                """
                create table session (
                  id text,
                  title text,
                  directory text,
                  time_updated integer,
                  time_archived integer
                )
                """
            )
            connection.execute(
                """
                create table message (
                  id text,
                  session_id text,
                  time_created integer,
                  time_updated integer,
                  data text
                )
                """
            )
            connection.execute(
                """
                create table part (
                  id text,
                  session_id text,
                  message_id text,
                  time_created integer,
                  time_updated integer,
                  data text
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

    def session(self, session_id: str, updated_at: int = NOW_MS - 1_000) -> None:
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                "insert into session values (?, ?, ?, ?, ?)",
                (session_id, "Test OpenCode session", str(self.root), updated_at, None),
            )
            connection.commit()
        finally:
            connection.close()

    def message(
        self,
        session_id: str,
        data: dict[str, object],
        created_at: int = NOW_MS - 2_000,
        updated_at: int = NOW_MS - 1_000,
    ) -> str:
        self._message_count += 1
        message_id = f"msg-{self._message_count}"
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                "insert into message values (?, ?, ?, ?, ?)",
                (message_id, session_id, created_at, updated_at, json.dumps(data)),
            )
            connection.commit()
        finally:
            connection.close()
        return message_id

    def part(
        self,
        session_id: str,
        data: dict[str, object],
        message_id: str = "msg-1",
        created_at: int = NOW_MS - 1_500,
        updated_at: int = NOW_MS - 1_000,
    ) -> str:
        self._part_count += 1
        part_id = f"part-{self._part_count}"
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                "insert into part values (?, ?, ?, ?, ?, ?)",
                (part_id, session_id, message_id, created_at, updated_at, json.dumps(data)),
            )
            connection.commit()
        finally:
            connection.close()
        return part_id

    def reader(self) -> OpencodeStateReader:
        return OpencodeStateReader(db_path=self.db, now_ms=lambda: NOW_MS)


def fixture() -> Fixture:
    return Fixture()


def assistant_message(
    completed: bool,
    created_at: int = NOW_MS - 2_000,
    completed_at: int = NOW_MS - 1_000,
    error: dict[str, object] | None = None,
) -> dict[str, object]:
    data: dict[str, object] = {
        "role": "assistant",
        "time": {"created": created_at},
        "finish": "stop",
    }
    if completed:
        data["time"] = {"created": created_at, "completed": completed_at}
    if error is not None:
        data["error"] = error
    return data


def tool_part(
    tool: str,
    status: str,
    tool_input: dict[str, object],
    title: str | None = None,
) -> dict[str, object]:
    state: dict[str, object] = {"status": status, "input": tool_input}
    if title is not None:
        state["title"] = title
    return {
        "type": "tool",
        "tool": tool,
        "callID": "call-1",
        "state": state,
    }


if __name__ == "__main__":
    unittest.main()
