from __future__ import annotations

import argparse
import asyncio
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pixelpet.cli import file_stamp, reload_config_if_changed
from pixelpet.config import RuntimeConfig, load_config
from pixelpet.daemon import PixelPetDaemon, state_reader_for_config
from pixelpet.opencode_state import OpencodeStateReader
from pixelpet.pet_pack import create_pet_pack, load_pet
from pixelpet.status import REQUIRED_STATUSES


class HotReloadTest(unittest.TestCase):
    def test_reconfigure_updates_pet_and_state_reader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets_dir = root / "pets"
            write_pet_pack(assets_dir, "one")
            write_pet_pack(assets_dir, "two")
            pet = load_pet("one", assets_dir)
            config = RuntimeConfig(
                dry_run=True,
                pet_id="one",
                assets_dir=assets_dir,
                assistant_backends=("codex_desktop",),
                codex_home=root / "codex-one",
            )
            display = FakeDisplay()
            daemon = PixelPetDaemon(config, pet, state_reader_for_config(config), display)

            next_config = RuntimeConfig(
                dry_run=True,
                pet_id="two",
                assets_dir=assets_dir,
                assistant_backends=("codex_desktop",),
                codex_home=root / "codex-two",
            )
            asyncio.run(daemon.reconfigure(next_config, load_pet("two", assets_dir)))

            self.assertEqual(daemon.pet.pet_id, "two")
            self.assertEqual(daemon.state_reader.codex_home, root / "codex-two")
            self.assertIs(daemon.display, display)

    def test_state_reader_factory_uses_opencode_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "opencode.db"
            config = RuntimeConfig(
                assistant_backends=("opencode_cli",),
                opencode_db_path=db_path,
            )

            reader = state_reader_for_config(config)

            self.assertIsInstance(reader, OpencodeStateReader)
            self.assertEqual(reader.db_path, db_path)

    def test_reconfigure_updates_reader_when_backend_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets_dir = root / "pets"
            write_pet_pack(assets_dir, "one")
            pet = load_pet("one", assets_dir)
            config = RuntimeConfig(
                dry_run=True,
                pet_id="one",
                assets_dir=assets_dir,
                codex_home=root / "codex",
            )
            display = FakeDisplay()
            daemon = PixelPetDaemon(config, pet, state_reader_for_config(config), display)

            next_config = RuntimeConfig(
                dry_run=True,
                pet_id="one",
                assets_dir=assets_dir,
                assistant_backends=("opencode_cli",),
                opencode_db_path=root / "opencode.db",
            )
            asyncio.run(daemon.reconfigure(next_config, pet))

            self.assertIsInstance(daemon.state_reader, OpencodeStateReader)
            self.assertEqual(daemon.state_reader.db_path, root / "opencode.db")
            self.assertIs(daemon.display, display)

    def test_reload_config_if_changed_applies_new_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets_dir = root / "pets"
            write_pet_pack(assets_dir, "one")
            write_pet_pack(assets_dir, "two")
            config_path = root / "config.toml"
            write_config(config_path, assets_dir, "one", "thread_title")

            config = load_config(config_path)
            daemon = PixelPetDaemon(
                config,
                load_pet(config.pet_id, config.assets_dir),
                state_reader_for_config(config),
                FakeDisplay(),
            )
            stamp = file_stamp(config_path)
            write_config(config_path, assets_dir, "two", "status")

            next_stamp = asyncio.run(
                reload_config_if_changed(args_for_config(config_path), daemon, config_path, stamp)
            )

            self.assertEqual(next_stamp, file_stamp(config_path))
            self.assertEqual(daemon.pet.pet_id, "two")
            self.assertEqual(daemon.config.pet_id, "two")
            self.assertEqual(daemon.config.marquee.source, "status")


class FakeDisplay:
    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def show_gif(self, path: Path) -> None:
        return None


def args_for_config(config_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        config=config_path,
        address=None,
        brightness=None,
        pet_id=None,
        assets_dir=None,
        assistant_backend=None,
        codex_home=None,
        opencode_db_path=None,
        poll_seconds=None,
        done_timeout_seconds=None,
        dry_run=False,
        no_hot_reload=False,
    )


def write_config(config_path: Path, assets_dir: Path, pet_id: str, source: str) -> None:
    config_path.write_text(
        f"""
        [pet]
        id = "{pet_id}"
        assets_dir = "{assets_dir}"

        [daemon]
        dry_run = true
        hot_reload = true

        [marquee]
        source = "{source}"
        """,
        encoding="utf-8",
    )


def write_pet_pack(assets_dir: Path, pet_id: str) -> None:
    root = create_pet_pack(pet_id, assets_dir=assets_dir)
    for status in REQUIRED_STATUSES:
        create_base_gif(root / "gifs" / f"{status.value}.gif")


def create_base_gif(path: Path) -> None:
    frames = [Image.new("RGB", (32, 32), (20, 20, 20))]
    frames[0].save(path, save_all=True, duration=50, loop=0)


if __name__ == "__main__":
    unittest.main()
