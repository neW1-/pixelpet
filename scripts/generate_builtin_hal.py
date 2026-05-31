from __future__ import annotations

from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError as exc:
    raise SystemExit("Pillow is required: python -m pip install Pillow") from exc

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "pets" / "hal" / "gifs"
SIZE = 32

BLACK = (0, 0, 0)
BODY = (18, 20, 24)
BODY_2 = (34, 38, 45)
EDGE = (72, 78, 88)
SHADOW = (8, 10, 14)
RED_DARK = (92, 8, 12)
RED = (218, 24, 28)
RED_HOT = (255, 92, 50)
AMBER = (255, 166, 35)
WHITE = (235, 238, 232)
DIM = (72, 78, 88)
BLUE = (44, 144, 255)
CYAN = (52, 214, 235)
ORANGE = (255, 145, 35)
GREEN = (74, 220, 106)
BADGE_DARK = (2, 4, 8)

PATTERNS = {
    "!": ["1", "1", "1", "0", "1"],
    "?": ["111", "001", "111", "000", "010"],
    "X": ["101", "010", "010", "010", "101"],
    "CHECK": ["0001", "0010", "1010", "0100"],
}


def canvas() -> Image.Image:
    return Image.new("RGB", (SIZE, SIZE), BLACK)


def px(draw: ImageDraw.ImageDraw, x: int, y: int, color: tuple[int, int, int]) -> None:
    if 0 <= x < SIZE and 0 <= y < SIZE:
        draw.point((x, y), fill=color)


def rect(draw: ImageDraw.ImageDraw, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
    draw.rectangle((x0, y0, x1, y1), fill=color)


def draw_pattern(draw: ImageDraw.ImageDraw, pattern: str, x: int, y: int, color: tuple[int, int, int]) -> None:
    rows = PATTERNS[pattern]
    for yy, row in enumerate(rows):
        for xx, cell in enumerate(row):
            if cell == "1":
                px(draw, x + xx, y + yy, color)


def draw_status_badge(draw: ImageDraw.ImageDraw, status: str, step: int) -> None:
    rect(draw, 0, 0, 9, 9, BADGE_DARK)
    if status == "idle":
        color = DIM if step % 2 else (42, 48, 56)
        rect(draw, 3, 3, 5, 5, color)
        px(draw, 2, 4, color)
        px(draw, 6, 4, color)
    elif status == "working":
        points = [(4, 1), (7, 4), (4, 7), (1, 4)]
        for idx, point in enumerate(points):
            color = CYAN if idx == step % 4 else (18, 70, 88)
            rect(draw, point[0], point[1], point[0] + 1, point[1] + 1, color)
        rect(draw, 4, 4, 5, 5, BLUE)
    elif status == "needs_input":
        rect(draw, 0, 0, 9, 9, BLUE)
        rect(draw, 1, 1, 8, 8, BLACK)
        draw_pattern(draw, "!", 4, 2, BLUE)
    elif status == "permission_required":
        rect(draw, 0, 0, 9, 9, ORANGE)
        rect(draw, 1, 1, 8, 8, BLACK)
        draw_pattern(draw, "?", 3, 2, ORANGE)
    elif status == "done":
        rect(draw, 0, 0, 9, 9, GREEN)
        rect(draw, 1, 1, 8, 8, BLACK)
        draw_pattern(draw, "CHECK", 3, 3, GREEN)
    elif status == "failed_offline":
        rect(draw, 0, 0, 9, 9, RED)
        rect(draw, 1, 1, 8, 8, BLACK)
        draw_pattern(draw, "X", 3, 2, RED)


def draw_body(draw: ImageDraw.ImageDraw, offset_x: int = 1, offset_y: int = 0) -> None:
    x = offset_x
    y = offset_y
    rect(draw, 7 + x, 10 + y, 30 + x, 31 + y, EDGE)
    px(draw, 7 + x, 10 + y, BLACK)
    px(draw, 30 + x, 10 + y, BLACK)
    px(draw, 7 + x, 31 + y, BLACK)
    px(draw, 30 + x, 31 + y, BLACK)

    rect(draw, 8 + x, 11 + y, 29 + x, 30 + y, EDGE)
    rect(draw, 9 + x, 12 + y, 28 + x, 29 + y, BODY)
    rect(draw, 10 + x, 13 + y, 27 + x, 28 + y, SHADOW)
    rect(draw, 11 + x, 14 + y, 26 + x, 27 + y, BODY_2)

    for xx in range(11 + x, 27 + x):
        if xx % 3 == 0:
            px(draw, xx, 13 + y, DIM)
            px(draw, xx, 28 + y, DIM)


def draw_lens(
    draw: ImageDraw.ImageDraw,
    cx: int = 20,
    cy: int = 20,
    pulse: int = 0,
    dim: bool = False,
    shutter: int = 0,
) -> None:
    ring = RED_DARK if dim else RED
    hot = (120, 18, 18) if dim else RED_HOT
    core = (80, 12, 12) if dim else WHITE
    radius = 6 + pulse

    draw.ellipse((cx - radius - 1, cy - radius, cx + radius, cy + radius), fill=(36, 8, 12))
    draw.ellipse((cx - 5, cy - 5, cx + 4, cy + 5), fill=ring)
    draw.ellipse((cx - 3, cy - 3, cx + 2, cy + 3), fill=hot)
    rect(draw, cx - 1, cy - 1, cx, cy + 1, core)

    px(draw, cx - 3, cy - 4, AMBER if not dim else RED_DARK)
    px(draw, cx + 2, cy + 4, RED_HOT if not dim else RED_DARK)

    if shutter:
        rect(draw, cx - 7, cy - shutter, cx + 6, cy + shutter, (24, 6, 8))
        rect(draw, cx - 4, cy - max(0, shutter - 1), cx + 3, cy + max(0, shutter - 1), ring)


def draw_scan(draw: ImageDraw.ImageDraw, step: int, color: tuple[int, int, int] = CYAN) -> None:
    x = [12, 14, 16, 18, 21, 23, 25, 27][step % 8]
    for y in range(13, 28):
        px(draw, x, y, color if y % 2 == 0 else (16, 70, 78))


def draw_tick_marks(draw: ImageDraw.ImageDraw, step: int, color: tuple[int, int, int]) -> None:
    for x, y in ((15, 13), (24, 13), (27, 20), (24, 28), (15, 28), (12, 20)):
        px(draw, x, y, color)


def frame(status: str, step: int) -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)

    if status == "idle":
        draw_body(draw)
        draw_lens(draw, pulse=step % 2, dim=False, shutter=1 if step == 3 else 0)
        draw_tick_marks(draw, step, RED_DARK)
    elif status == "working":
        draw_body(draw)
        draw_lens(draw, cx=19 + (step % 3), pulse=step % 2)
        draw_scan(draw, step)
        draw_tick_marks(draw, step, CYAN)
    elif status == "needs_input":
        draw_body(draw)
        draw_lens(draw, pulse=1 if step % 2 == 0 else 0)
        draw_tick_marks(draw, step, BLUE)
    elif status == "permission_required":
        draw_body(draw)
        pulse = 1 if step % 2 == 0 else 0
        draw_lens(draw, pulse=pulse)
        tick_color = ORANGE if step % 2 == 0 else (120, 62, 12)
        draw_tick_marks(draw, step, tick_color)
        if step % 4 in {0, 1}:
            px(draw, 12, 14, ORANGE)
            px(draw, 27, 27, ORANGE)
        else:
            px(draw, 27, 14, ORANGE)
            px(draw, 12, 27, ORANGE)
    elif status == "done":
        draw_body(draw)
        draw_lens(draw, pulse=1 if step % 2 == 0 else 0)
        draw_tick_marks(draw, step, GREEN if step % 2 == 0 else (28, 120, 54))
        if step % 4 in {0, 1}:
            px(draw, 14, 14, GREEN)
            px(draw, 25, 14, GREEN)
        if step % 4 in {2, 3}:
            px(draw, 14, 27, GREEN)
            px(draw, 25, 27, GREEN)
    elif status == "failed_offline":
        draw_body(draw)
        draw_lens(draw, pulse=0, dim=True, shutter=1 if step % 2 else 0)
        if step % 2 == 0:
            rect(draw, 12, 26, 26, 26, RED_DARK)

    draw_status_badge(draw, status, step)
    return image


def save_gif(name: str, frames: list[Image.Image], duration: int = 220) -> None:
    path = OUT / f"{name}.gif"
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=0,
        disposal=2,
    )
    print(path)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    save_gif("idle", [frame("idle", i) for i in range(6)], 260)
    save_gif("working", [frame("working", i) for i in range(8)], 140)
    save_gif("needs_input", [frame("needs_input", i) for i in range(4)], 220)
    save_gif("permission_required", [frame("permission_required", i) for i in range(4)], 220)
    save_gif("done", [frame("done", i) for i in range(4)], 220)
    save_gif("failed_offline", [frame("failed_offline", i) for i in range(4)], 260)


if __name__ == "__main__":
    main()
