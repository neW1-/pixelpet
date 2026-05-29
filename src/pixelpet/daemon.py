from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .codex_state import CodexStateReader, StatusSnapshot
from .config import RuntimeConfig
from .led_driver import DryRunDisplay, PixelDisplay
from .pet_pack import PetPack
from .status import Status


class Display(Protocol):
    async def connect(self) -> None:
        ...

    async def disconnect(self) -> None:
        ...

    async def show_gif(self, path: Path) -> None:
        ...


@dataclass
class PixelPetDaemon:
    config: RuntimeConfig
    pet: PetPack
    state_reader: CodexStateReader
    display: Display
    last_status: Status | None = None

    @classmethod
    def from_config(cls, config: RuntimeConfig, pet: PetPack) -> "PixelPetDaemon":
        reader = CodexStateReader(
            codex_home=config.codex_home,
            done_timeout_seconds=config.done_timeout_seconds,
            active_window_seconds=config.active_window_seconds,
        )
        if config.dry_run:
            display: Display = DryRunDisplay()
        else:
            if not config.address:
                raise ValueError("Display address is required unless --dry-run is set.")
            display = PixelDisplay(config.address, brightness=config.brightness)
        return cls(config=config, pet=pet, state_reader=reader, display=display)

    async def run_forever(self) -> None:
        await self.display.connect()
        try:
            while True:
                await self.tick()
                await asyncio.sleep(self.config.poll_seconds)
        finally:
            await self.display.disconnect()

    async def run_once(self) -> StatusSnapshot:
        await self.display.connect()
        try:
            return await self.tick()
        finally:
            await self.display.disconnect()

    async def tick(self) -> StatusSnapshot:
        snapshot = self.state_reader.current_status()
        if snapshot.status != self.last_status:
            gif_path = self.pet.gif_for(snapshot.status)
            await self.display.show_gif(gif_path)
            self.last_status = snapshot.status
            print(status_line(snapshot, gif_path))
        return snapshot


def status_line(snapshot: StatusSnapshot, gif_path: Path) -> str:
    thread = f" thread={snapshot.thread_id[:8]}" if snapshot.thread_id else ""
    return f"status={snapshot.status.value}{thread} gif={gif_path}"
