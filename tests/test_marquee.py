from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageSequence

from pixelpet.assistant_state import SessionUsage, StatusSnapshot
from pixelpet.config import MarqueeConfig, RuntimeConfig
from pixelpet.daemon import PixelPetDaemon, effective_marquee_config, marquee_message
from pixelpet.marquee import normalize_message, render_status_gif, scroll_positions
from pixelpet.pet_pack import PetPack
from pixelpet.status import REQUIRED_STATUSES, Status


class MarqueeTest(unittest.TestCase):
    def test_normalize_message_collapses_and_truncates(self) -> None:
        result = normalize_message(" hello\tworld 🚀 again ", Status.WORKING, 12)

        self.assertEqual(result, "HELLO WORLD")

    def test_normalize_message_falls_back_to_status_label(self) -> None:
        self.assertEqual(normalize_message("🚀🚀", Status.PERMISSION_REQUIRED, 24), "APPROVE")
        self.assertEqual(normalize_message(None, Status.FAILED_OFFLINE, 24), "FAIL")

    def test_rendered_gif_is_32x32_and_pulses_input_badge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.gif"
            create_base_gif(base)

            rendered = render_status_gif(
                base,
                "test",
                Status.NEEDS_INPUT,
                "waiting on review",
                MarqueeConfig(cache_dir=root / "cache", frame_ms=40),
            )

            with Image.open(rendered.path) as image:
                frames = gif_frames(image)

            self.assertEqual(frames[0].size, (32, 32))
            first = frames[0].getpixel((0, 0))
            second = frames[1].getpixel((0, 0))
            self.assertGreater(first[2], first[0])
            self.assertGreater(first[2], first[1])
            self.assertNotEqual(first, second)

    def test_rendered_gif_ends_with_clear_marquee_lane(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.gif"
            create_black_gif(base)

            rendered = render_status_gif(
                base,
                "test",
                Status.DONE,
                "DONE",
                MarqueeConfig(cache_dir=root / "cache", frame_ms=40),
            )

            with Image.open(rendered.path) as image:
                last = gif_frames(image)[-1]

            lit_pixels = [
                last.getpixel((x, y))
                for x in range(10, 32)
                for y in range(0, 10)
                if last.getpixel((x, y)) != (0, 0, 0)
            ]
            self.assertEqual(lit_pixels, [])

    def test_badge_patterns_match_status_animation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.gif"
            create_base_gif(base)
            config = MarqueeConfig(cache_dir=root / "cache", frame_ms=40)

            approval = render_status_gif(base, "test", Status.PERMISSION_REQUIRED, "approval", config)
            failed = render_status_gif(base, "test", Status.FAILED_OFFLINE, "failed", config)
            working = render_status_gif(base, "test", Status.WORKING, "working", config)

            with Image.open(approval.path) as image:
                approval_frames = gif_frames(image)
            with Image.open(failed.path) as image:
                failed_frames = gif_frames(image)
            with Image.open(working.path) as image:
                working_frames = gif_frames(image)

            approval_bright = approval_frames[0].getpixel((0, 0))
            approval_dim = approval_frames[3].getpixel((0, 0))
            self.assertGreater(approval_bright[0], 200)
            self.assertLess(approval_dim[0], 100)

            failed_bright = failed_frames[0].getpixel((0, 0))
            failed_dim = failed_frames[2].getpixel((0, 0))
            self.assertGreater(failed_bright[0], 200)
            self.assertLess(failed_dim[0], 100)

            first_point_active = working_frames[0].getpixel((4, 1))
            first_point_dim = working_frames[1].getpixel((4, 1))
            second_point_active = working_frames[1].getpixel((7, 4))
            self.assertGreater(sum(first_point_active), sum(first_point_dim))
            self.assertGreater(sum(second_point_active), sum(first_point_dim))
            self.assertEqual(working_frames[0].getpixel((4, 4)), (44, 144, 255))
            self.assertEqual(working_frames[0].getpixel((5, 5)), (44, 144, 255))

    def test_idle_badge_uses_original_compact_icon(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.gif"
            create_base_gif(base)
            rendered = render_status_gif(
                base,
                "test",
                Status.IDLE,
                "idle",
                MarqueeConfig(cache_dir=root / "cache", frame_ms=40),
            )

            with Image.open(rendered.path) as image:
                frames = gif_frames(image)

            self.assertEqual(frames[0].getpixel((3, 3)), (42, 48, 56))
            self.assertEqual(frames[0].getpixel((5, 5)), (42, 48, 56))
            self.assertEqual(frames[0].getpixel((6, 4)), (42, 48, 56))
            self.assertEqual(frames[0].getpixel((6, 5)), (2, 4, 8))

    def test_badge_patterns_can_render_without_marquee_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.gif"
            create_base_gif(base)
            config = MarqueeConfig(
                enabled=False,
                badge_patterns=True,
                cache_dir=root / "cache",
                frame_ms=40,
            )

            first = render_status_gif(base, "test", Status.PERMISSION_REQUIRED, "first message", config)
            second = render_status_gif(base, "test", Status.PERMISSION_REQUIRED, "second message", config)

            self.assertEqual(first.key, second.key)
            self.assertNotEqual(first.path, base)
            with Image.open(first.path) as image:
                frames = gif_frames(image)

            pixel = frames[0].getpixel((0, 0))
            self.assertGreater(pixel[0], 200)

    def test_daemon_uploads_when_message_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.gif"
            create_base_gif(base)
            pet = PetPack(
                root=root,
                pet_id="test",
                display_name="Test",
                states={status: base for status in REQUIRED_STATUSES},
            )
            display = FakeDisplay()
            reader = FakeReader(
                [
                    StatusSnapshot(Status.WORKING, "running", "t1", "FIRST TITLE", 1),
                    StatusSnapshot(Status.WORKING, "running", "t1", "FIRST TITLE", 2),
                    StatusSnapshot(Status.WORKING, "running", "t1", "SECOND TITLE", 3),
                ]
            )
            config = RuntimeConfig(
                dry_run=True,
                marquee=MarqueeConfig(cache_dir=root / "cache", frame_ms=40),
            )
            daemon = PixelPetDaemon(config, pet, reader, display)

            asyncio.run(daemon.tick())
            asyncio.run(daemon.tick())
            asyncio.run(daemon.tick())

            self.assertEqual(len(display.paths), 2)

    def test_daemon_replays_same_gif_after_duration_elapses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.gif"
            create_base_gif(base)
            pet = PetPack(
                root=root,
                pet_id="test",
                display_name="Test",
                states={status: base for status in REQUIRED_STATUSES},
            )
            display = FakeDisplay()
            reader = FakeReader(
                [
                    StatusSnapshot(Status.IDLE, "idle", None, None, 1),
                    StatusSnapshot(Status.IDLE, "idle", None, None, 2),
                    StatusSnapshot(Status.IDLE, "idle", None, None, 3),
                ]
            )
            clock = FakeClock()
            config = RuntimeConfig(
                dry_run=True,
                marquee=MarqueeConfig(source="status", cache_dir=root / "cache", frame_ms=40),
            )
            daemon = PixelPetDaemon(config, pet, reader, display, now=clock.now)

            asyncio.run(daemon.tick())
            clock.advance(0.1)
            asyncio.run(daemon.tick())
            clock.advance(2)
            asyncio.run(daemon.tick())

            self.assertEqual(len(display.paths), 2)

    def test_daemon_can_disable_replaying_same_gif(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.gif"
            create_base_gif(base)
            pet = PetPack(
                root=root,
                pet_id="test",
                display_name="Test",
                states={status: base for status in REQUIRED_STATUSES},
            )
            display = FakeDisplay()
            reader = FakeReader(
                [
                    StatusSnapshot(Status.IDLE, "idle", None, None, 1),
                    StatusSnapshot(Status.IDLE, "idle", None, None, 2),
                ]
            )
            clock = FakeClock()
            config = RuntimeConfig(
                dry_run=True,
                replay_gifs=False,
                marquee=MarqueeConfig(source="status", cache_dir=root / "cache", frame_ms=40),
            )
            daemon = PixelPetDaemon(config, pet, reader, display, now=clock.now)

            asyncio.run(daemon.tick())
            clock.advance(100)
            asyncio.run(daemon.tick())

            self.assertEqual(len(display.paths), 1)

    def test_stream_playback_sends_frames_between_status_polls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.gif"
            create_base_gif(base)
            pet = PetPack(
                root=root,
                pet_id="test",
                display_name="Test",
                states={status: base for status in REQUIRED_STATUSES},
            )
            display = FakeDisplay()
            reader = FakeReader(
                [
                    StatusSnapshot(Status.IDLE, "idle", "t1", "First", 1),
                    StatusSnapshot(Status.IDLE, "idle", "t1", "Second", 2),
                ]
            )
            clock = FakeClock()
            config = RuntimeConfig(
                dry_run=True,
                playback="stream",
                stream_frame_ms=40,
                poll_seconds=3,
                marquee=MarqueeConfig(cache_dir=root / "cache", frame_ms=40),
            )
            daemon = PixelPetDaemon(config, pet, reader, display, now=clock.now)

            asyncio.run(daemon.tick())
            clock.advance(0.04)
            asyncio.run(daemon.tick())
            clock.advance(3)
            asyncio.run(daemon.tick())

            self.assertEqual(len(display.images), 3)
            self.assertEqual(len(display.paths), 0)
            self.assertEqual(reader.index, 2)

    def test_marquee_message_sources(self) -> None:
        snapshot = StatusSnapshot(
            Status.PERMISSION_REQUIRED,
            "Allow network access?",
            "abcdef123456",
            "Install dependencies",
            1,
            "NEEDS APPROVAL",
        )

        self.assertEqual(marquee_message(snapshot, "thread_title"), "Install dependencies")
        self.assertEqual(marquee_message(snapshot, "title"), "Install dependencies")
        self.assertEqual(marquee_message(snapshot, "reason"), "Allow network access?")
        self.assertEqual(marquee_message(snapshot, "activity"), "NEEDS APPROVAL")
        self.assertEqual(marquee_message(snapshot, "status"), "APPROVE")
        self.assertEqual(marquee_message(snapshot, "status_label"), "APPROVE")
        self.assertEqual(marquee_message(snapshot, "thread_id"), "abcdef12")
        self.assertEqual(marquee_message(snapshot, "unknown"), "APPROVE")

    def test_rotate_source_combines_configured_sources(self) -> None:
        snapshot = StatusSnapshot(
            Status.WORKING,
            "Codex turn is running.",
            "abcdef123456",
            "Build PixelPet",
            1,
            "TESTING",
        )

        self.assertEqual(
            marquee_message(snapshot, "rotate", ("status", "activity", "thread_title")),
            "WORK / TESTING / Build PixelPet",
        )
        self.assertEqual(
            marquee_message(snapshot, "rotate", ("status", "activity", "thread_title"), 8, " | "),
            "WORK | TESTING | BUILD PI",
        )
        self.assertEqual(
            marquee_message(snapshot, "rotate", ("status", "activity", "thread_title"), 6),
            "WORK / TESTIN / BUILD",
        )

    def test_rotate_source_expands_render_character_limit(self) -> None:
        config = MarqueeConfig(
            source="rotate",
            separator=" | ",
            per_source_max_chars=10,
            max_chars=12,
        )

        self.assertEqual(effective_marquee_config(config).max_chars, 36)

    def test_scroll_positions_obey_frame_cap(self) -> None:
        positions = scroll_positions("THIS IS A LONG MESSAGE FOR A TINY DISPLAY", scroll_step_px=1, max_frames=12)

        self.assertLessEqual(len(positions), 12)
        self.assertEqual(positions[0], 22)

    def test_daemon_activity_source_uploads_when_activity_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.gif"
            create_base_gif(base)
            pet = PetPack(
                root=root,
                pet_id="test",
                display_name="Test",
                states={status: base for status in REQUIRED_STATUSES},
            )
            display = FakeDisplay()
            reader = FakeReader(
                [
                    StatusSnapshot(Status.WORKING, "running", "t1", "Same title", 1, "RUNNING TESTS"),
                    StatusSnapshot(Status.WORKING, "running", "t1", "Same title", 2, "PATCHING"),
                ]
            )
            config = RuntimeConfig(
                dry_run=True,
                marquee=MarqueeConfig(source="activity", cache_dir=root / "cache", frame_ms=40),
            )
            daemon = PixelPetDaemon(config, pet, reader, display)

            asyncio.run(daemon.tick())
            asyncio.run(daemon.tick())

            self.assertEqual(len(display.paths), 2)

    def _cost_area_pixels(self, frame: Image.Image) -> list:
        """Return non-background pixels in the cost area (y=10..21, x=0..9)."""
        pixels = []
        for y in range(10, 22):
            for x in range(3):
                p = frame.getpixel((x, y))
                if p != (20, 20, 20):
                    pixels.append((x, y, p))
        return pixels

    def test_token_usage_draws_in_cost_slot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.gif"
            create_base_gif(base)
            usage = SessionUsage(value=1250000, display_kind="tokens")

            rendered = render_status_gif(
                base,
                "test",
                Status.WORKING,
                "working",
                MarqueeConfig(cache_dir=root / "cache", frame_ms=40),
                usage=usage,
            )

            with Image.open(rendered.path) as image:
                frames = gif_frames(image)
            pixels = self._cost_area_pixels(frames[0])
            self.assertTrue(len(pixels) > 0, "No token usage pixels rendered")
            # All painted pixels should have COST_COLOR blue tint
            for x, y, p in pixels:
                self.assertGreater(p[2], p[0], f"pixel ({x},{y}) lacks blue tint: {p}")

    def test_token_usage_abbreviation_small_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.gif"
            create_base_gif(base)

            rendered = render_status_gif(
                base, "test", Status.WORKING, "working",
                MarqueeConfig(cache_dir=root / "cache", frame_ms=40),
                usage=SessionUsage(value=500, display_kind="tokens"),
            )
            with Image.open(rendered.path) as image:
                frames = gif_frames(image)
            pixels = self._cost_area_pixels(frames[0])
            self.assertTrue(len(pixels) > 0, "No small token value pixels rendered")

    def test_token_usage_wraps_digits_and_suffix_to_lower_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.gif"
            create_base_gif(base)

            rendered = render_status_gif(
                base,
                "test",
                Status.WORKING,
                "working",
                MarqueeConfig(cache_dir=root / "cache", frame_ms=40),
                usage=SessionUsage(value=5432, display_kind="tokens"),
            )
            with Image.open(rendered.path) as image:
                frames = gif_frames(image)
            frame = frames[0]

            def painted(x: int, y: int) -> bool:
                p = frame.getpixel((x, y))
                return p[2] > p[0] and p != (20, 20, 20)

            self.assertTrue(painted(0, 10), "digit 1 not on row1")
            self.assertTrue(painted(5, 14), "decimal point not on row1")
            self.assertTrue(painted(0, 16), "digit 3 not on row2")
            self.assertFalse(painted(8, 10), "digit 3 leaked to row1 right of frame")
            self.assertTrue(painted(0, 22), "K suffix not on row3")

    def test_token_usage_without_usage_falls_back_to_cost(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.gif"
            create_base_gif(base)

            rendered = render_status_gif(
                base, "test", Status.DONE, "done",
                MarqueeConfig(cache_dir=root / "cache", frame_ms=40),
                cost=12.34,
            )

            with Image.open(rendered.path) as image:
                frames = gif_frames(image)
            pixels = self._cost_area_pixels(frames[0])
            self.assertTrue(len(pixels) > 0, "No cost pixels rendered")

    def test_daemon_reason_source_uploads_when_reason_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.gif"
            create_base_gif(base)
            pet = PetPack(
                root=root,
                pet_id="test",
                display_name="Test",
                states={status: base for status in REQUIRED_STATUSES},
            )
            display = FakeDisplay()
            reader = FakeReader(
                [
                    StatusSnapshot(Status.NEEDS_INPUT, "Question one", "t1", "Same title", 1),
                    StatusSnapshot(Status.NEEDS_INPUT, "Question two", "t1", "Same title", 2),
                ]
            )
            config = RuntimeConfig(
                dry_run=True,
                marquee=MarqueeConfig(source="reason", cache_dir=root / "cache", frame_ms=40),
            )
            daemon = PixelPetDaemon(config, pet, reader, display)

            asyncio.run(daemon.tick())
            asyncio.run(daemon.tick())

            self.assertEqual(len(display.paths), 2)


class FakeDisplay:
    def __init__(self) -> None:
        self.paths: list[Path] = []
        self.images: list[Path] = []

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def show_gif(self, path: Path) -> None:
        self.paths.append(path)

    async def show_image(self, path: Path) -> None:
        self.images.append(path)


class FakeReader:
    def __init__(self, snapshots: list[StatusSnapshot]) -> None:
        self.snapshots = snapshots
        self.index = 0

    def current_status(self) -> StatusSnapshot:
        snapshot = self.snapshots[min(self.index, len(self.snapshots) - 1)]
        self.index += 1
        return snapshot


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def now(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def create_base_gif(path: Path) -> None:
    frames = []
    for color in [(20, 20, 20), (30, 30, 30)]:
        image = Image.new("RGB", (32, 32), color)
        for x in range(10):
            for y in range(10):
                image.putpixel((x, y), (0, 0, 255))
        frames.append(image)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=50, loop=0)


def create_black_gif(path: Path) -> None:
    frame = Image.new("RGB", (32, 32), (0, 0, 0))
    frame.save(path, save_all=True, duration=50, loop=0)


def gif_frames(image: Image.Image) -> list[Image.Image]:
    return [frame.convert("RGB") for frame in ImageSequence.Iterator(image)]


if __name__ == "__main__":
    unittest.main()
