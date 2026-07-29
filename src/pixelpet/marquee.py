from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .assistant_state import SessionUsage
from .config import MarqueeConfig
from .status import Status

LANE_X = 10
LANE_Y = 0
LANE_WIDTH = 22
LANE_HEIGHT = 10
TEXT_Y = 2
FONT_WIDTH = 3
FONT_HEIGHT = 5
CHAR_SPACING = 1
SCROLL_GAP = 6
TEXT_COLOR = (178, 224, 255)
COST_X = 0
COST_Y_LINE1 = 10
COST_Y_LINE2 = 16
COST_COLOR = (130, 180, 220)
TRAILING_CLEAR_FRAMES = 6
BADGE_PATTERN_VERSION = "badge-v4"
BADGE_BG = (2, 4, 8)
BADGE_BLACK = (0, 0, 0)
BADGE_DIM = (34, 40, 50)
BADGE_BLUE = (44, 144, 255)
BADGE_BLUE_DIM = (12, 42, 82)
BADGE_CYAN = (52, 214, 235)
BADGE_ORANGE = (255, 145, 35)
BADGE_ORANGE_DIM = (72, 34, 10)
BADGE_RED = (226, 20, 32)
BADGE_RED_DIM = (72, 6, 10)
BADGE_GREEN = (74, 220, 106)
BADGE_GREEN_DIM = (22, 74, 34)

BADGE_SYMBOLS = {
    "!": ("010", "010", "010", "000", "010"),
    "?": ("110", "001", "010", "000", "010"),
    "X": ("101", "101", "010", "101", "101"),
    "CHECK": ("0001", "0010", "1010", "0100"),
}

STATUS_LABELS: dict[Status, str] = {
    Status.IDLE: "IDLE",
    Status.WORKING: "WORK",
    Status.NEEDS_INPUT: "INPUT",
    Status.PERMISSION_REQUIRED: "APPROVE",
    Status.DONE: "DONE",
    Status.FAILED_OFFLINE: "FAIL",
}

FONT_3X5 = {
    "A": ("010", "101", "111", "101", "101"),
    "B": ("110", "101", "110", "101", "110"),
    "C": ("011", "100", "100", "100", "011"),
    "D": ("110", "101", "101", "101", "110"),
    "E": ("111", "100", "110", "100", "111"),
    "F": ("111", "100", "110", "100", "100"),
    "G": ("011", "100", "101", "101", "011"),
    "H": ("101", "101", "111", "101", "101"),
    "I": ("111", "010", "010", "010", "111"),
    "J": ("001", "001", "001", "101", "010"),
    "K": ("101", "101", "110", "101", "101"),
    "L": ("100", "100", "100", "100", "111"),
    "M": ("101", "111", "111", "101", "101"),
    "N": ("101", "111", "111", "111", "101"),
    "O": ("010", "101", "101", "101", "010"),
    "P": ("110", "101", "110", "100", "100"),
    "Q": ("010", "101", "101", "111", "011"),
    "R": ("110", "101", "110", "101", "101"),
    "S": ("011", "100", "010", "001", "110"),
    "T": ("111", "010", "010", "010", "010"),
    "U": ("101", "101", "101", "101", "111"),
    "V": ("101", "101", "101", "101", "010"),
    "W": ("101", "101", "111", "111", "101"),
    "X": ("101", "101", "010", "101", "101"),
    "Y": ("101", "101", "010", "010", "010"),
    "Z": ("111", "001", "010", "100", "111"),
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("110", "001", "010", "100", "111"),
    "3": ("110", "001", "010", "001", "110"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "110", "001", "110"),
    "6": ("011", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "110"),
    "!": ("010", "010", "010", "000", "010"),
    "?": ("110", "001", "010", "000", "010"),
    ".": ("000", "000", "000", "000", "010"),
    "-": ("000", "000", "111", "000", "000"),
    ":": ("000", "010", "000", "010", "000"),
    "/": ("001", "001", "010", "100", "100"),
    "#": ("101", "111", "101", "111", "101"),
    "&": ("010", "101", "010", "101", "011"),
    " ": ("000", "000", "000", "000", "000"),
}


@dataclass(frozen=True)
class RenderedGif:
    path: Path
    key: str
    message: str
    duration_seconds: float


def normalize_message(text: str | None, status: Status, max_chars: int) -> str:
    candidate = (text or "").upper()
    candidate = "".join(char if char in FONT_3X5 else " " for char in candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip()
    if not candidate:
        candidate = STATUS_LABELS[status]
    return candidate[:max(1, max_chars)].strip() or STATUS_LABELS[status]


def render_status_gif(
    base_gif: Path,
    pet_id: str,
    status: Status,
    message: str | None,
    config: MarqueeConfig,
    cost: float | None = None,
    usage: SessionUsage | None = None,
) -> RenderedGif:
    normalized = normalize_message(message, status, config.max_chars)
    if not config.enabled and not config.badge_patterns:
        return RenderedGif(
            base_gif,
            f"base:{pet_id}:{status.value}",
            normalized,
            gif_duration_seconds(base_gif),
        )

    render_message = normalized if config.enabled else STATUS_LABELS[status]
    key = render_key(base_gif, pet_id, status, render_message, config, cost=cost, usage=usage)
    output = config.cache_dir.expanduser() / f"{key}.gif"
    duration_seconds = marquee_duration_seconds(
        render_message,
        config.frame_ms,
        config.scroll_step_px,
        config.max_frames,
    )
    if not output.exists():
        compose_marquee_gif(
            base_gif,
            output,
            status,
            render_message,
            config.frame_ms,
            scroll_step_px=config.scroll_step_px,
            max_frames=config.max_frames,
            show_message=config.enabled,
            draw_badge=config.badge_patterns,
            show_cost=config.show_cost,
            cost=cost,
            usage=usage,
        )
    return RenderedGif(output, key, render_message, duration_seconds)


def render_key(
    base_gif: Path,
    pet_id: str,
    status: Status,
    message: str,
    config: MarqueeConfig,
    cost: float | None = None,
    usage: SessionUsage | None = None,
) -> str:
    stat = base_gif.stat()
    cost_part = f"{cost:.4f}" if cost is not None else "no-cost"
    usage_part = f"tokens={usage.value}" if usage is not None else "no-usage"
    payload = "|".join(
        [
            pet_id,
            status.value,
            message,
            config.font,
            str(config.max_chars),
            str(config.frame_ms),
            str(config.scroll_step_px),
            str(config.max_frames),
            str(config.enabled),
            str(config.badge_patterns),
            str(config.show_cost),
            BADGE_PATTERN_VERSION,
            str(stat.st_mtime_ns),
            str(stat.st_size),
            cost_part,
            usage_part,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def compose_marquee_gif(
    base_gif: Path,
    output: Path,
    status: Status,
    message: str,
    frame_ms: int,
    scroll_step_px: int = 2,
    max_frames: int | None = 72,
    show_message: bool = True,
    draw_badge: bool = True,
    show_cost: bool = True,
    cost: float | None = None,
    usage: SessionUsage | None = None,
) -> None:
    try:
        from PIL import Image, ImageDraw, ImageSequence
    except ImportError as exc:
        raise RuntimeError("Pillow is required to render marquee GIFs.") from exc

    output.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(base_gif) as source:
        base_frames = [frame.convert("RGB") for frame in ImageSequence.Iterator(source)]

    if not base_frames:
        raise RuntimeError(f"{base_gif} contains no frames.")

    positions = scroll_positions(message, scroll_step_px, max_frames)
    frames = []
    for index, offset in enumerate(positions):
        frame = base_frames[index % len(base_frames)].copy()
        draw = ImageDraw.Draw(frame)
        if draw_badge:
            draw_status_badge(draw, status, index)
        if show_message:
            draw_text(draw, message, LANE_X + offset, TEXT_Y)
        if show_cost:
            draw_usage(draw, usage, cost, COST_X, COST_Y_LINE1, COST_Y_LINE2)
        frames.append(frame)

    for tail_index in range(TRAILING_CLEAR_FRAMES):
        index = len(positions) + tail_index
        frame = base_frames[index % len(base_frames)].copy()
        draw = ImageDraw.Draw(frame)
        if draw_badge:
            draw_status_badge(draw, status, index)
        if show_cost:
            draw_usage(draw, usage, cost, COST_X, COST_Y_LINE1, COST_Y_LINE2)
        frames.append(frame)

    frames[0].save(
        output,
        save_all=True,
        append_images=frames[1:],
        duration=max(20, int(frame_ms)),
        loop=0,
        disposal=2,
    )


def marquee_duration_seconds(
    message: str,
    frame_ms: int,
    scroll_step_px: int = 2,
    max_frames: int | None = 72,
) -> float:
    return (
        len(scroll_positions(message, scroll_step_px, max_frames)) + TRAILING_CLEAR_FRAMES
    ) * max(20, int(frame_ms)) / 1000


def scroll_positions(message: str, scroll_step_px: int = 2, max_frames: int | None = 72) -> tuple[int, ...]:
    text_width = measure_text(message)
    step = max(1, int(scroll_step_px))
    positions = tuple(range(LANE_WIDTH, -(text_width + SCROLL_GAP), -step))
    if not positions:
        return (LANE_WIDTH,)
    if max_frames is not None and max_frames > 0 and len(positions) > max_frames:
        thinning_step = (len(positions) + max_frames - 1) // max_frames
        positions = positions[::thinning_step]
    return positions


def gif_duration_seconds(path: Path) -> float:
    try:
        from PIL import Image, ImageSequence
    except ImportError as exc:
        raise RuntimeError("Pillow is required to inspect GIF durations.") from exc

    with Image.open(path) as image:
        duration_ms = sum(
            int(frame.info.get("duration", image.info.get("duration", 100)) or 100)
            for frame in ImageSequence.Iterator(image)
        )
    return max(0.02, duration_ms / 1000)


def measure_text(text: str) -> int:
    if not text:
        return 0
    return len(text) * (FONT_WIDTH + CHAR_SPACING) - CHAR_SPACING


def draw_status_badge(draw: object, status: Status, frame_index: int) -> None:
    if status == Status.PERMISSION_REQUIRED:
        bright = (frame_index // 3) % 2 == 0
        color = BADGE_ORANGE if bright else BADGE_ORANGE_DIM
        draw_badge_shell(draw, color, icon="?")
    elif status == Status.NEEDS_INPUT:
        color = pulse_color(BADGE_BLUE, BADGE_BLUE_DIM, frame_index)
        draw_badge_shell(draw, color, icon="!")
    elif status == Status.FAILED_OFFLINE:
        bright = frame_index % 8 in {0, 1}
        color = BADGE_RED if bright else BADGE_RED_DIM
        draw_badge_shell(draw, color, icon="X", fill=bright)
    elif status == Status.WORKING:
        draw_working_badge(draw, frame_index)
    elif status == Status.DONE:
        draw_badge_shell(draw, BADGE_GREEN, icon="CHECK")
    else:
        draw_idle_badge(draw, frame_index)


def draw_badge_shell(
    draw: object,
    color: tuple[int, int, int],
    icon: str,
    fill: bool = False,
) -> None:
    fill_rect(draw, 0, 0, 9, 9, color if fill else BADGE_BG)
    fill_rect(draw, 0, 0, 9, 0, color)
    fill_rect(draw, 0, 9, 9, 9, color)
    fill_rect(draw, 0, 0, 0, 9, color)
    fill_rect(draw, 9, 0, 9, 9, color)
    fill_rect(draw, 1, 1, 8, 8, BADGE_BLACK)
    draw_badge_symbol(draw, icon, color)


def draw_badge_symbol(draw: object, icon: str, color: tuple[int, int, int]) -> None:
    pattern = BADGE_SYMBOLS[icon]
    x = 4 if icon == "!" else 3
    y = 2 if icon != "CHECK" else 3
    for yy, row in enumerate(pattern):
        for xx, cell in enumerate(row):
            if cell == "1":
                draw_point(draw, x + xx, y + yy, color)


def draw_working_badge(draw: object, frame_index: int) -> None:
    fill_rect(draw, 0, 0, 9, 9, BADGE_BG)
    points = ((4, 1), (7, 4), (4, 7), (1, 4))
    for index, (x, y) in enumerate(points):
        color = BADGE_CYAN if index == frame_index % len(points) else (18, 70, 88)
        fill_rect(draw, x, y, x + 1, y + 1, color)
    fill_rect(draw, 4, 4, 5, 5, BADGE_BLUE)


def draw_idle_badge(draw: object, frame_index: int) -> None:
    fill_rect(draw, 0, 0, 9, 9, BADGE_BG)
    color = BADGE_DIM if frame_index % 2 else (42, 48, 56)
    fill_rect(draw, 3, 3, 5, 5, color)
    draw_point(draw, 2, 4, color)
    draw_point(draw, 6, 4, color)


def pulse_color(
    high: tuple[int, int, int],
    low: tuple[int, int, int],
    frame_index: int,
    steps: tuple[float, ...] = (0.35, 0.55, 0.8, 1.0, 0.8, 0.55),
) -> tuple[int, int, int]:
    amount = steps[frame_index % len(steps)]
    return tuple(
        round(low[channel] + (high[channel] - low[channel]) * amount)
        for channel in range(3)
    )


def scale_color(color: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, round(channel * amount))) for channel in color)


def fill_rect(draw: object, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
    draw.rectangle((x0, y0, x1, y1), fill=color)


def draw_point(draw: object, x: int, y: int, color: tuple[int, int, int]) -> None:
    draw.point((x, y), fill=color)


def draw_text(draw: object, text: str, x: int, y: int) -> None:
    cursor = x
    for char in text:
        draw_char(draw, char, cursor, y)
        cursor += FONT_WIDTH + CHAR_SPACING


def draw_char(draw: object, char: str, x: int, y: int) -> None:
    pattern = FONT_3X5.get(char, FONT_3X5[" "])
    for yy, row in enumerate(pattern):
        for xx, cell in enumerate(row):
            target_x = x + xx
            target_y = y + yy
            if cell == "1" and _inside_lane(target_x, target_y):
                draw.point((target_x, target_y), fill=TEXT_COLOR)


def _inside_lane(x: int, y: int) -> bool:
    return LANE_X <= x < LANE_X + LANE_WIDTH and LANE_Y <= y < LANE_Y + LANE_HEIGHT


def draw_text_unclipped(draw: object, text: str, x: int, y: int, color: tuple[int, int, int] = TEXT_COLOR) -> None:
    cursor = x
    for char in text:
        _draw_char_unclipped(draw, char, cursor, y, color)
        cursor += FONT_WIDTH + CHAR_SPACING


def _draw_char_unclipped(draw: object, char: str, x: int, y: int, color: tuple[int, int, int]) -> None:
    pattern = FONT_3X5.get(char, FONT_3X5[" "])
    for yy, row in enumerate(pattern):
        for xx, cell in enumerate(row):
            if cell == "1":
                target_x = x + xx
                target_y = y + yy
                if 0 <= target_x < 32 and 0 <= target_y < 32:
                    draw.point((target_x, target_y), fill=color)


def draw_cost(draw: object, cost: float | None, x: int, y1: int, y2: int) -> None:
    if cost is None:
        return
    dollars = int(cost)
    cents = round((cost - dollars) * 100)
    draw_text_unclipped(draw, str(dollars), x, y1, COST_COLOR)
    draw_text_unclipped(draw, f"{cents:02d}", x, y2, COST_COLOR)


def draw_usage(
    draw: object,
    usage: SessionUsage | None,
    cost: float | None,
    x: int,
    y1: int,
    y2: int,
) -> None:
    if usage is not None and usage.display_kind == "tokens":
        draw_token_usage(draw, usage.value, x, y1, y2)
    else:
        draw_cost(draw, cost, x, y1, y2)


def draw_token_usage(draw: object, tokens: int, x: int, y1: int, y2: int) -> None:
    if tokens < 1000:
        line1 = str(tokens)
        line2 = " "
    elif tokens < 10_000:
        value = tokens / 1000
        line1 = f"{value:.1f}"
        line2 = "K"
    elif tokens < 1_000_000:
        line1 = str(tokens // 1000)
        line2 = "K"
    elif tokens < 10_000_000:
        value = tokens / 1_000_000
        line1 = f"{value:.1f}"
        line2 = "M"
    else:
        line1 = str(tokens // 1_000_000)
        line2 = "M"
    draw_text_unclipped(draw, line1, x, y1, COST_COLOR)
    draw_text_unclipped(draw, line2, x, y2, COST_COLOR)
