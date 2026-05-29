from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any


class DisplayError(RuntimeError):
    pass


class PixelDisplay:
    def __init__(
        self,
        address: str,
        brightness: int | None = 20,
        allow_non_32: bool = False,
    ) -> None:
        self.address = address
        self.brightness = brightness
        self.allow_non_32 = allow_non_32
        self._client: Any | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if self._client is not None:
            return
        try:
            from pypixelcolor import AsyncClient
        except ImportError as exc:
            raise DisplayError("pypixelcolor is not installed. Run `pip install -e .`.") from exc

        client = AsyncClient(self.address)
        try:
            await client.connect()
        except Exception as exc:
            raise DisplayError(f"Could not connect to display {self.address}: {exc}") from exc
        info = client.get_device_info()
        width = int(getattr(info, "width", 0) or 0)
        height = int(getattr(info, "height", 0) or 0)
        if not self.allow_non_32 and (width, height) != (32, 32):
            await client.disconnect()
            raise DisplayError(f"Expected a 32x32 display, got {width}x{height}.")
        if self.brightness is not None:
            await client.set_brightness(int(self.brightness))
        self._client = client

    async def disconnect(self) -> None:
        if self._client is None:
            return
        await self._client.disconnect()
        self._client = None

    async def show_gif(self, path: Path) -> None:
        if self._client is None:
            await self.connect()
        if self._client is None:
            raise DisplayError("Display client is not connected.")
        async with self._lock:
            try:
                await self._client.send_image(str(path), resize_method="fit")
            except Exception as exc:
                raise DisplayError(f"Could not send GIF to display: {path}: {exc}") from exc


class DryRunDisplay:
    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def show_gif(self, path: Path) -> None:
        print(f"dry-run display: {path}")
