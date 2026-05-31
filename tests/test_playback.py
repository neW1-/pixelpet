from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pixelpet.playback import gif_frame_sequence


class PlaybackTest(unittest.TestCase):
    def test_frame_sequence_cache_key_changes_when_gif_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gif = root / "status.gif"
            cache = root / "cache"

            write_single_frame_gif(gif, (44, 144, 255))
            first = gif_frame_sequence(gif, "same-render-key", cache)

            write_single_frame_gif(gif, (255, 145, 35))
            second = gif_frame_sequence(gif, "same-render-key", cache)

            self.assertNotEqual(first.key, second.key)
            with Image.open(second.frames[0]) as image:
                self.assertEqual(image.convert("RGB").getpixel((0, 0)), (255, 145, 35))


def write_single_frame_gif(path: Path, color: tuple[int, int, int]) -> None:
    image = Image.new("RGB", (32, 32), color)
    image.save(path, save_all=True, duration=50, loop=0)


if __name__ == "__main__":
    unittest.main()
