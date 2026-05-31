from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from pixelpet.led_driver import PixelDisplay


class LedDriverTest(unittest.TestCase):
    def test_save_slot_upload_shows_slot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.gif"
            path.write_bytes(b"GIF89a")
            client = FakeClient()
            display = PixelDisplay("test-address", save_slot=1)
            display._client = client

            asyncio.run(display.show_gif(path))

            self.assertEqual(client.sent, [(str(path), "fit", 1)])
            self.assertEqual(client.shown, [1])

    def test_frame_upload_ignores_save_slot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frame.png"
            path.write_bytes(b"PNG")
            client = FakeClient()
            display = PixelDisplay("test-address", save_slot=1)
            display._client = client

            asyncio.run(display.show_image(path))

            self.assertEqual(client.sent, [(str(path), "fit", None)])
            self.assertEqual(client.shown, [])

    def test_temp_upload_does_not_show_slot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.gif"
            path.write_bytes(b"GIF89a")
            client = FakeClient()
            display = PixelDisplay("test-address")
            display._client = client

            asyncio.run(display.show_gif(path))

            self.assertEqual(client.sent, [(str(path), "fit", None)])
            self.assertEqual(client.shown, [])


class FakeClient:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, int | None]] = []
        self.shown: list[int] = []

    async def send_image(self, path: str, resize_method: str, save_slot: int | None = None) -> None:
        self.sent.append((path, resize_method, save_slot))

    async def show_slot(self, slot: int) -> None:
        self.shown.append(slot)


if __name__ == "__main__":
    unittest.main()
