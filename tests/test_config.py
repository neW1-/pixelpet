from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pixelpet.config import ASSISTANT_BACKENDS, ConfigError, default_opencode_db_path, load_config


class ConfigTest(unittest.TestCase):
    def test_default_assistant_backends_is_opencode_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(Path(tmp) / "missing.toml")

            self.assertEqual(config.assistant_backends, ("opencode_cli",))
            self.assertEqual(config.opencode_db_path, default_opencode_db_path())

    def test_loads_marquee_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(
                """
                [daemon]
                hot_reload = false
                replay_gifs = false

                [display]
                playback = "stream"
                stream_frame_ms = 180
                save_slot = 1

                [marquee]
                enabled = false
                badge_patterns = false
                source = "rotate"
                sources = ["status", "activity", "thread_title"]
                separator = " | "
                per_source_max_chars = 10
                font = "3x5"
                max_chars = 12
                frame_ms = 80
                scroll_step_px = 3
                max_frames = 48
                cache_dir = "/tmp/pixelpet-render-cache"
                """,
                encoding="utf-8",
            )

            config = load_config(path)

            self.assertFalse(config.hot_reload)
            self.assertFalse(config.replay_gifs)
            self.assertEqual(config.playback, "stream")
            self.assertEqual(config.stream_frame_ms, 180)
            self.assertEqual(config.save_slot, 1)
            self.assertFalse(config.marquee.enabled)
            self.assertFalse(config.marquee.badge_patterns)
            self.assertEqual(config.marquee.source, "rotate")
            self.assertEqual(config.marquee.sources, ("status", "activity", "thread_title"))
            self.assertEqual(config.marquee.separator, " | ")
            self.assertEqual(config.marquee.per_source_max_chars, 10)
            self.assertEqual(config.marquee.font, "3x5")
            self.assertEqual(config.marquee.max_chars, 12)
            self.assertEqual(config.marquee.frame_ms, 80)
            self.assertEqual(config.marquee.scroll_step_px, 3)
            self.assertEqual(config.marquee.max_frames, 48)
            self.assertEqual(config.marquee.cache_dir, Path("/tmp/pixelpet-render-cache"))

    def test_loads_assistant_backend_config_scalar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(
                """
                [assistant]
                backend = "opencode_cli"

                [opencode]
                db_path = "/tmp/opencode.db"

                [codex]
                home = "/tmp/codex-home"
                """,
                encoding="utf-8",
            )

            config = load_config(path)

            self.assertEqual(config.assistant_backends, ("opencode_cli",))
            self.assertEqual(config.opencode_db_path, Path("/tmp/opencode.db"))
            self.assertEqual(config.codex_home, Path("/tmp/codex-home"))

    def test_loads_assistant_backends_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(
                """
                [assistant]
                backends = ["opencode_cli", "codex_desktop"]
                """,
                encoding="utf-8",
            )

            config = load_config(path)

            self.assertEqual(config.assistant_backends, ("opencode_cli", "codex_desktop"))

    def test_assistant_backends_list_accepts_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(
                """
                [assistant]
                backends = ["opencode", "codex"]
                """,
                encoding="utf-8",
            )

            config = load_config(path)

            self.assertEqual(config.assistant_backends, ("opencode_cli", "codex_desktop"))

    def test_unknown_assistant_backend_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(
                """
                [assistant]
                backend = "unknown"
                """,
                encoding="utf-8",
            )

            with self.assertRaises(ConfigError):
                load_config(path)

    def test_unknown_assistant_backend_in_list_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(
                """
                [assistant]
                backends = ["opencode_cli", "unknown"]
                """,
                encoding="utf-8",
            )

            with self.assertRaises(ConfigError):
                load_config(path)

    def test_invalid_toml_is_config_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(
                """
                [assistant]
                backend = opencode
                """,
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "Invalid TOML"):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
