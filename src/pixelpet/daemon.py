from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Protocol

from .assistant_state import StatusReader, StatusSnapshot
from .codex_state import CodexStateReader
from .config import DEFAULT_MARQUEE_SOURCES, MarqueeConfig, RuntimeConfig
from .led_driver import DryRunDisplay, PixelDisplay
from .marquee import STATUS_LABELS, RenderedGif, normalize_message, render_status_gif
from .opencode_state import OpencodeStateReader
from .pet_pack import PetPack
from .playback import FrameSequence, gif_frame_sequence
from .status import Status


class Display(Protocol):
    async def connect(self) -> None:
        ...

    async def disconnect(self) -> None:
        ...

    async def show_gif(self, path: Path) -> None:
        ...

    async def show_image(self, path: Path) -> None:
        ...


@dataclass
class PixelPetDaemon:
    config: RuntimeConfig
    pet: PetPack
    state_reader: StatusReader
    display: Display
    last_status: Status | None = None
    last_render_key: str | None = None
    last_sent_at: float | None = None
    now: Callable[[], float] = field(default=time.monotonic, repr=False)
    current_snapshot: StatusSnapshot | None = None
    current_rendered: RenderedGif | None = None
    last_poll_at: float | None = None
    stream_sequence: FrameSequence | None = None
    stream_render_key: str | None = None
    stream_frame_index: int = 0

    @classmethod
    def from_config(cls, config: RuntimeConfig, pet: PetPack) -> "PixelPetDaemon":
        return cls(
            config=config,
            pet=pet,
            state_reader=state_reader_for_config(config),
            display=display_for_config(config),
        )

    async def run_forever(self) -> None:
        await self.display.connect()
        try:
            while True:
                await self.tick()
                await asyncio.sleep(self.sleep_seconds())
        finally:
            await self.display.disconnect()

    async def run_once(self) -> StatusSnapshot:
        await self.display.connect()
        try:
            return await self.tick()
        finally:
            await self.display.disconnect()

    async def reconfigure(self, config: RuntimeConfig, pet: PetPack) -> None:
        display_changed = display_signature(config) != display_signature(self.config)
        reader_changed = reader_signature(config) != reader_signature(self.config)
        playback_changed = config.playback != self.config.playback
        next_display = self.display
        next_reader = self.state_reader

        if reader_changed:
            next_reader = state_reader_for_config(config)

        if display_changed:
            old_display = self.display
            next_display = display_for_config(config)
            await old_display.disconnect()
            try:
                await next_display.connect()
            except Exception:
                await old_display.connect()
                raise

        self.config = config
        self.pet = pet
        self.state_reader = next_reader
        self.display = next_display
        self.current_rendered = None
        if display_changed or playback_changed:
            self.last_render_key = None
            self.last_sent_at = None
            self.stream_sequence = None
            self.stream_render_key = None
            self.stream_frame_index = 0

    async def tick(self) -> StatusSnapshot:
        snapshot, rendered = self.current_render()
        if self.config.playback == "stream":
            await self.stream_frame(snapshot, rendered)
            return snapshot

        now = self.now()
        render_changed = rendered.key != self.last_render_key
        if self.should_send(rendered, now):
            await self.display.show_gif(rendered.path)
            self.last_status = snapshot.status
            self.last_render_key = rendered.key
            self.last_sent_at = self.now()
            if render_changed:
                print(status_line(snapshot, rendered.path), flush=True)
        return snapshot

    def current_render(self) -> tuple[StatusSnapshot, RenderedGif]:
        now = self.now()
        if self.config.playback != "stream" or self.should_poll(now):
            self.current_snapshot = self.state_reader.current_status()
            self.current_rendered = self.render(self.current_snapshot)
            self.last_poll_at = now

        if self.current_snapshot is None or self.current_rendered is None:
            self.current_snapshot = self.state_reader.current_status()
            self.current_rendered = self.render(self.current_snapshot)
            self.last_poll_at = now

        return self.current_snapshot, self.current_rendered

    def should_poll(self, now: float) -> bool:
        if self.last_poll_at is None:
            return True
        return now - self.last_poll_at >= self.config.poll_seconds

    def should_send(self, rendered: RenderedGif, now: float) -> bool:
        if rendered.key != self.last_render_key:
            return True
        if not self.config.replay_gifs:
            return False
        if self.last_sent_at is None:
            return True
        return now - self.last_sent_at >= rendered.duration_seconds

    async def stream_frame(self, snapshot: StatusSnapshot, rendered: RenderedGif) -> None:
        render_changed = rendered.key != self.last_render_key
        if self.stream_sequence is None or self.stream_render_key != rendered.key:
            self.stream_sequence = gif_frame_sequence(rendered.path, rendered.key, self.config.marquee.cache_dir)
            self.stream_render_key = rendered.key
            self.stream_frame_index = 0

        frame = self.stream_sequence.frames[self.stream_frame_index % len(self.stream_sequence.frames)]
        await self.display.show_image(frame)
        self.stream_frame_index += 1
        self.last_status = snapshot.status
        self.last_render_key = rendered.key
        self.last_sent_at = self.now()
        if render_changed:
            print(status_line(snapshot, rendered.path), flush=True)

    def sleep_seconds(self) -> float:
        if self.config.playback == "stream":
            return max(0.05, self.config.stream_frame_ms / 1000)
        return self.config.poll_seconds

    def render(self, snapshot: StatusSnapshot) -> RenderedGif:
        marquee_config = effective_marquee_config(self.config.marquee)
        message = marquee_message(
            snapshot,
            self.config.marquee.source,
            self.config.marquee.sources,
            self.config.marquee.per_source_max_chars or self.config.marquee.max_chars,
            self.config.marquee.separator,
        )
        return render_status_gif(
            self.pet.gif_for(snapshot.status),
            self.pet.pet_id,
            snapshot.status,
            message,
            marquee_config,
        )


def status_line(snapshot: StatusSnapshot, gif_path: Path) -> str:
    activity = f" activity={snapshot.activity}" if snapshot.activity else ""
    thread = f" thread={snapshot.thread_id[:8]}" if snapshot.thread_id else ""
    return f"status={snapshot.status.value}{activity}{thread} gif={gif_path}"


def state_reader_for_config(config: RuntimeConfig) -> StatusReader:
    if config.assistant_backend == "codex_desktop":
        return CodexStateReader(
            codex_home=config.codex_home,
            done_timeout_seconds=config.done_timeout_seconds,
            active_window_seconds=config.active_window_seconds,
        )
    if config.assistant_backend == "opencode_cli":
        return OpencodeStateReader(
            db_path=config.opencode_db_path,
            done_timeout_seconds=config.done_timeout_seconds,
            active_window_seconds=config.active_window_seconds,
        )
    raise ValueError(f"Unknown assistant backend: {config.assistant_backend}")


def display_for_config(config: RuntimeConfig) -> Display:
    if config.dry_run:
        return DryRunDisplay()
    if not config.address:
        raise ValueError("Display address is required unless --dry-run is set.")
    return PixelDisplay(config.address, brightness=config.brightness, save_slot=config.save_slot)


def display_signature(config: RuntimeConfig) -> tuple[bool, str | None, int | None, int | None]:
    return (config.dry_run, config.address, config.brightness, config.save_slot)


def reader_signature(config: RuntimeConfig) -> tuple[str, Path, Path, float, float]:
    return (
        config.assistant_backend,
        config.codex_home,
        config.opencode_db_path,
        config.done_timeout_seconds,
        config.active_window_seconds,
    )


def effective_marquee_config(config: MarqueeConfig) -> MarqueeConfig:
    if config.source.strip().lower() != "rotate":
        return config

    source_count = len([source for source in config.sources if source.strip().lower() != "rotate"])
    source_count = max(1, source_count)
    source_limit = max(1, config.per_source_max_chars or config.max_chars)
    rotate_max_chars = source_limit * source_count + len(config.separator) * (source_count - 1)
    return replace(config, max_chars=max(config.max_chars, rotate_max_chars))


def marquee_message(
    snapshot: StatusSnapshot,
    source: str,
    sources: tuple[str, ...] | None = None,
    max_chars: int | None = None,
    separator: str = " / ",
) -> str | None:
    normalized = source.strip().lower()
    if normalized == "rotate":
        return rotated_marquee_message(snapshot, sources or DEFAULT_MARQUEE_SOURCES, max_chars, separator)
    if normalized in {"thread_title", "title"}:
        return snapshot.title
    if normalized == "reason":
        return snapshot.reason
    if normalized == "activity":
        return snapshot.activity
    if normalized in {"status", "status_label"}:
        return STATUS_LABELS[snapshot.status]
    if normalized == "thread_id":
        return snapshot.thread_id[:8] if snapshot.thread_id else None
    return STATUS_LABELS[snapshot.status]


def rotated_marquee_message(
    snapshot: StatusSnapshot,
    sources: tuple[str, ...],
    max_chars: int | None,
    separator: str,
) -> str:
    messages: list[str] = []
    seen: set[str] = set()
    for source in sources:
        if source.strip().lower() == "rotate":
            continue
        message = marquee_message(snapshot, source)
        if not message:
            continue
        if max_chars is not None:
            message = normalize_message(message, snapshot.status, max_chars)
        key = " ".join(message.split()).lower()
        if not key or key in seen:
            continue
        messages.append(message)
        seen.add(key)
    return separator.join(messages) or STATUS_LABELS[snapshot.status]
