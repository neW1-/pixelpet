from __future__ import annotations

from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError as exc:
    raise SystemExit("Pillow is required: python -m pip install Pillow") from exc

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "pets" / "dino" / "gifs"
SIZE = 32
BLACK = (0, 0, 0)
OUTLINE = (18, 46, 33)
GREEN = (74, 196, 93)
DARK_GREEN = (36, 118, 59)
LIGHT_GREEN = (142, 238, 126)
WHITE = (238, 244, 218)
BLUE = (46, 142, 255)
ORANGE = (255, 145, 35)
RED = (230, 45, 55)

PATTERNS = {
    "!": ["1", "1", "1", "0", "1"],
    "?": ["111", "001", "111", "000", "010"],
    "Z": ["111", "001", "010", "100", "111"],
    "X": ["101", "010", "010", "010", "101"],
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


def draw_bubble(draw: ImageDraw.ImageDraw, x: int, y: int, color: tuple[int, int, int], symbol: str) -> None:
    rect(draw, x, y, x + 9, y + 9, color)
    rect(draw, x + 1, y + 1, x + 8, y + 8, BLACK)
    px(draw, x + 8, y + 9, color)
    sx = x + 4 if symbol == "!" else x + 3
    draw_pattern(draw, symbol, sx, y + 2, color)


def draw_check(draw: ImageDraw.ImageDraw) -> None:
    for offset in range(2):
        px(draw, 22 + offset, 8 + offset, WHITE)
        px(draw, 23 + offset, 9 + offset, WHITE)
        px(draw, 24 + offset, 10 + offset, WHITE)
        px(draw, 25 + offset, 9 - offset, WHITE)
        px(draw, 26 + offset, 8 - offset, WHITE)
        px(draw, 27 + offset, 7 - offset, WHITE)


def draw_dino(
    draw: ImageDraw.ImageDraw,
    dx: int = 0,
    body_y: int = 18,
    arm_up: bool = False,
    sleep: bool = False,
    sad: bool = False,
) -> None:
    x = 8 + dx
    y = body_y

    draw.polygon([(x, y + 4), (x - 4, y + 6), (x, y + 8)], fill=OUTLINE)
    draw.polygon([(x + 1, y + 4), (x - 3, y + 6), (x + 1, y + 7)], fill=DARK_GREEN)
    rect(draw, x, y + 2, x + 12, y + 9, OUTLINE)
    rect(draw, x + 1, y + 3, x + 11, y + 8, GREEN)
    rect(draw, x + 11, y - 5, x + 19, y + 2, OUTLINE)
    rect(draw, x + 12, y - 4, x + 18, y + 1, GREEN)
    rect(draw, x + 18, y - 2, x + 20, y + 1, OUTLINE)
    rect(draw, x + 18, y - 1, x + 19, y, GREEN)
    px(draw, x + 14, y - 2, BLACK if not sleep else DARK_GREEN)
    if sad:
        px(draw, x + 13, y - 1, BLACK)
        px(draw, x + 15, y - 3, BLACK)
        px(draw, x + 17, y + 1, BLACK)
    else:
        rect(draw, x + 15, y + 1, x + 17, y + 1, BLACK)
    px(draw, x + 4, y + 1, LIGHT_GREEN)
    px(draw, x + 7, y + 1, LIGHT_GREEN)
    px(draw, x + 10, y + 1, LIGHT_GREEN)

    if arm_up:
        rect(draw, x + 13, y + 4, x + 14, y + 4, OUTLINE)
        rect(draw, x + 15, y + 2, x + 15, y + 4, OUTLINE)
        px(draw, x + 15, y + 1, GREEN)
    else:
        rect(draw, x + 13, y + 5, x + 16, y + 6, OUTLINE)
        rect(draw, x + 13, y + 5, x + 15, y + 5, GREEN)

    rect(draw, x + 2, y + 9, x + 4, y + 12, OUTLINE)
    rect(draw, x + 3, y + 9, x + 4, y + 11, GREEN)
    rect(draw, x + 9, y + 9, x + 11, y + 12, OUTLINE)
    rect(draw, x + 9, y + 9, x + 10, y + 11, GREEN)


def frame_idle(step: int) -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)
    draw_dino(draw, body_y=19 + (step % 2), sleep=True)
    draw_pattern(draw, "Z", 22, 4 - (step % 2), BLUE)
    if step % 2 == 0:
        draw_pattern(draw, "Z", 26, 1, BLUE)
    return image


def frame_working(step: int) -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)
    offsets = [-2, -1, 0, 1, 2, 1, 0, -1]
    draw_dino(draw, dx=offsets[step % len(offsets)], body_y=18 + (step % 2))
    px(draw, 3, 26, DARK_GREEN)
    px(draw, 5, 27, DARK_GREEN)
    px(draw, 29, 26, DARK_GREEN)
    return image


def frame_needs_input(step: int) -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)
    draw_dino(draw, body_y=18, arm_up=step % 2 == 0)
    draw_bubble(draw, 2, 2, BLUE, "!")
    return image


def frame_permission(step: int) -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)
    draw_dino(draw, body_y=18 + (step % 2), arm_up=False)
    draw_bubble(draw, 2, 2, ORANGE, "?")
    return image


def frame_done(step: int) -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)
    draw_dino(draw, body_y=18, arm_up=step % 2 == 0)
    draw_check(draw)
    return image


def frame_failed(step: int) -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)
    draw_dino(draw, body_y=19, sad=True)
    draw_pattern(draw, "X", 3, 3, RED)
    if step % 2 == 0:
        px(draw, 7, 3, RED)
        px(draw, 7, 7, RED)
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
    save_gif("idle", [frame_idle(i) for i in range(4)], 360)
    save_gif("working", [frame_working(i) for i in range(8)], 150)
    save_gif("needs_input", [frame_needs_input(i) for i in range(4)], 220)
    save_gif("permission_required", [frame_permission(i) for i in range(4)], 220)
    save_gif("done", [frame_done(i) for i in range(4)], 220)
    save_gif("failed_offline", [frame_failed(i) for i in range(4)], 300)


if __name__ == "__main__":
    main()

