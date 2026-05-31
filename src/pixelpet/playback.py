from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

FRAME_SEQUENCE_VERSION = "frames-v2"


@dataclass(frozen=True)
class FrameSequence:
    key: str
    frames: tuple[Path, ...]


def gif_frame_sequence(gif_path: Path, render_key: str, cache_dir: Path) -> FrameSequence:
    try:
        from PIL import Image, ImageSequence
    except ImportError as exc:
        raise RuntimeError("Pillow is required to stream GIF frames.") from exc

    stat = gif_path.stat()
    payload = "|".join(
        [
            FRAME_SEQUENCE_VERSION,
            render_key,
            str(gif_path),
            str(stat.st_mtime_ns),
            str(stat.st_size),
        ]
    )
    sequence_key = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    output_dir = cache_dir.expanduser() / "frames" / sequence_key
    existing = tuple(sorted(output_dir.glob("*.png")))
    if existing:
        return FrameSequence(sequence_key, existing)

    output_dir.mkdir(parents=True, exist_ok=True)
    frame_paths: list[Path] = []
    with Image.open(gif_path) as image:
        for index, frame in enumerate(ImageSequence.Iterator(image)):
            frame_path = output_dir / f"{index:04d}.png"
            frame.convert("RGB").save(frame_path)
            frame_paths.append(frame_path)

    if not frame_paths:
        raise RuntimeError(f"{gif_path} contains no frames.")
    return FrameSequence(sequence_key, tuple(frame_paths))
