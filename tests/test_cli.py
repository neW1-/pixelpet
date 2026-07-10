from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from pixelpet.cli import build_parser, main
from pixelpet.cli import _config_from_args as config_from_args


class CliConfigTest(unittest.TestCase):
    def test_run_accepts_assistant_backend_overrides(self) -> None:
        args = build_parser().parse_args(
            [
                "run",
                "--assistant-backend",
                "opencode_cli",
                "--opencode-db-path",
                "/tmp/opencode.db",
            ]
        )

        config = config_from_args(args)

        self.assertEqual(config.assistant_backend, "opencode_cli")
        self.assertEqual(config.opencode_db_path, Path("/tmp/opencode.db"))

    def test_status_uses_selected_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_db = Path(tmp) / "missing.db"
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                code = main(
                    [
                        "status",
                        "--assistant-backend",
                        "opencode_cli",
                        "--opencode-db-path",
                        str(missing_db),
                    ]
                )

            self.assertEqual(code, 0)
            self.assertIn("failed_offline: OpenCode state unavailable", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
