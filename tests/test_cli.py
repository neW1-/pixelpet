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

        self.assertEqual(config.assistant_backends, ("opencode_cli",))
        self.assertEqual(config.opencode_db_path, Path("/tmp/opencode.db"))

    def test_run_accepts_multiple_backend_flags(self) -> None:
        args = build_parser().parse_args(
            [
                "run",
                "--assistant-backend",
                "codex_desktop",
                "--assistant-backend",
                "vscode_copilot",
            ]
        )

        config = config_from_args(args)

        self.assertEqual(config.assistant_backends, ("codex_desktop", "vscode_copilot"))

    def test_run_accepts_vscode_backend_override(self) -> None:
        args = build_parser().parse_args(
            [
                "run",
                "--assistant-backend",
                "vscode_copilot",
                "--vscode-user-dir",
                "/tmp/vscode-code",
            ]
        )

        config = config_from_args(args)

        self.assertEqual(config.assistant_backends, ("vscode_copilot",))
        self.assertEqual(config.vscode_user_dir, Path("/tmp/vscode-code"))

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
