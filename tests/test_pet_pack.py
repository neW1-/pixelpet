from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pixelpet.pet_pack import create_pet_pack, load_pet
from pixelpet.status import REQUIRED_STATUSES


class PetPackTest(unittest.TestCase):
    def test_create_pet_pack_writes_selectable_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = create_pet_pack("robot", assets_dir=Path(tmp))
            manifest = json.loads((root / "pet.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["id"], "robot")
            self.assertEqual(set(manifest["states"]), {status.value for status in REQUIRED_STATUSES})

    def test_validation_reports_missing_gifs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            create_pet_pack("robot", assets_dir=Path(tmp))
            pet = load_pet("robot", Path(tmp))

            errors = pet.validate(check_images=False)

            self.assertTrue(any("missing GIF" in error for error in errors))

    def test_validation_accepts_complete_pack_without_image_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = create_pet_pack("robot", assets_dir=Path(tmp))
            for status in REQUIRED_STATUSES:
                (root / "gifs" / f"{status.value}.gif").write_bytes(b"placeholder")
            pet = load_pet("robot", Path(tmp))

            self.assertEqual(pet.validate(check_images=False), [])


if __name__ == "__main__":
    unittest.main()

