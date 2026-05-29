from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import default_assets_dir
from .status import REQUIRED_STATUSES, Status


class PetPackError(ValueError):
    pass


@dataclass(frozen=True)
class PetPack:
    root: Path
    pet_id: str
    display_name: str
    states: dict[Status, Path]
    size: tuple[int, int] = (32, 32)

    @classmethod
    def load(cls, root: Path) -> "PetPack":
        manifest_path = root / "pet.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise PetPackError(f"Cannot read {manifest_path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise PetPackError(f"Invalid JSON in {manifest_path}: {exc}") from exc

        states_raw = manifest.get("states")
        if not isinstance(states_raw, dict):
            raise PetPackError(f"{manifest_path} must contain a states object")

        states: dict[Status, Path] = {}
        for status in REQUIRED_STATUSES:
            value = states_raw.get(status.value)
            if isinstance(value, str) and value:
                states[status] = root / value

        size_raw = manifest.get("size", [32, 32])
        size = _parse_size(size_raw)
        return cls(
            root=root,
            pet_id=_required_str(manifest.get("id"), "id"),
            display_name=_required_str(manifest.get("display_name"), "display_name"),
            states=states,
            size=size,
        )

    def gif_for(self, status: Status) -> Path:
        try:
            return self.states[status]
        except KeyError as exc:
            raise PetPackError(f"Pet {self.pet_id} has no GIF for {status.value}") from exc

    def validate(self, check_images: bool = True) -> list[str]:
        errors: list[str] = []
        if self.size != (32, 32):
            errors.append(f"size must be [32, 32], got {list(self.size)}")

        for status in REQUIRED_STATUSES:
            path = self.states.get(status)
            if path is None:
                errors.append(f"missing state {status.value}")
                continue
            if not path.exists():
                errors.append(f"missing GIF for {status.value}: {path}")
                continue
            if path.suffix.lower() != ".gif":
                errors.append(f"{status.value} must point to a .gif file: {path}")
                continue
            if check_images:
                errors.extend(_validate_gif(path, status))
        return errors

    def validate_or_raise(self, check_images: bool = True) -> None:
        errors = self.validate(check_images=check_images)
        if errors:
            raise PetPackError("; ".join(errors))


def load_pet(pet_id: str, assets_dir: Path | None = None) -> PetPack:
    root = (assets_dir or default_assets_dir()).expanduser() / pet_id
    return PetPack.load(root)


def list_pets(assets_dir: Path | None = None) -> list[PetPack]:
    root = (assets_dir or default_assets_dir()).expanduser()
    if not root.exists():
        return []
    packs: list[PetPack] = []
    for child in sorted(path for path in root.iterdir() if path.is_dir()):
        try:
            packs.append(PetPack.load(child))
        except PetPackError:
            continue
    return packs


def create_pet_pack(
    pet_id: str,
    display_name: str | None = None,
    assets_dir: Path | None = None,
    overwrite: bool = False,
) -> Path:
    root = (assets_dir or default_assets_dir()).expanduser() / pet_id
    if root.exists() and not overwrite:
        raise PetPackError(f"Pet pack already exists: {root}")

    (root / "gifs").mkdir(parents=True, exist_ok=True)
    (root / "prompts").mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema": 1,
        "id": pet_id,
        "display_name": display_name or pet_id.replace("-", " ").replace("_", " ").title(),
        "size": [32, 32],
        "states": {status.value: f"gifs/{status.value}.gif" for status in REQUIRED_STATUSES},
    }
    (root / "pet.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (root / "prompts" / "README.md").write_text(_prompt_readme(pet_id), encoding="utf-8")
    return root


def _validate_gif(path: Path, status: Status) -> list[str]:
    try:
        from PIL import Image
    except ImportError:
        return []

    errors: list[str] = []
    try:
        with Image.open(path) as image:
            if image.format != "GIF":
                errors.append(f"{status.value} is not a GIF: {path}")
            if image.size != (32, 32):
                errors.append(f"{status.value} must be 32x32, got {image.size}: {path}")
    except Exception as exc:
        errors.append(f"cannot read {status.value} GIF {path}: {exc}")
    return errors


def _required_str(value: object, name: str) -> str:
    if isinstance(value, str) and value:
        return value
    raise PetPackError(f"pet.json missing required string field: {name}")


def _parse_size(value: object) -> tuple[int, int]:
    if (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], int)
        and isinstance(value[1], int)
    ):
        return value[0], value[1]
    return 32, 32


def _prompt_readme(pet_id: str) -> str:
    return f"""# {pet_id} LED Pet Prompts

Create six 32x32 pixel-art GIFs on a black background:

- idle: sleeping or calm.
- working: walking, pacing, typing, or thinking.
- needs_input: blue exclamation bubble.
- permission_required: orange question bubble.
- done: happy with a check mark.
- failed_offline: sad with a red X or disconnected cue.

Keep the silhouette stable across states so the pet is recognizable at LED scale.
"""

