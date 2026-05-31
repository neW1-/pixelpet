from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pixelpet.config import load_config


class ConfigTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
