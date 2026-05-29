from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def default_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()


def project_root() -> Path:
    starts = [Path.cwd(), Path(__file__).resolve()]
    for start in starts:
        directory = start if start.is_dir() else start.parent
        for candidate in (directory, *directory.parents):
            if (candidate / "pyproject.toml").exists():
                return candidate
    return Path(__file__).resolve().parents[2]


def default_config_path() -> Path:
    return project_root() / "config.toml"


def default_assets_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "assets" / "pets"


@dataclass(frozen=True)
class RuntimeConfig:
    address: str | None = None
    brightness: int | None = 20
    pet_id: str = "dino"
    assets_dir: Path = default_assets_dir()
    codex_home: Path = default_codex_home()
    poll_seconds: float = 3.0
    done_timeout_seconds: float = 300.0
    active_window_seconds: float = 300.0
    dry_run: bool = False


def load_config(path: Path | None = None) -> RuntimeConfig:
    config_path = path or default_config_path()
    if not config_path.exists():
        return RuntimeConfig()

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    display = _table(data.get("display"))
    pet = _table(data.get("pet"))
    daemon = _table(data.get("daemon"))
    codex = _table(data.get("codex"))

    return RuntimeConfig(
        address=_optional_str(display.get("address")),
        brightness=_optional_int(display.get("brightness"), default=20),
        pet_id=_optional_str(pet.get("id")) or "dino",
        assets_dir=_path(pet.get("assets_dir"), default_assets_dir()),
        codex_home=_path(codex.get("home"), default_codex_home()),
        poll_seconds=_optional_float(daemon.get("poll_seconds"), default=3.0),
        done_timeout_seconds=_optional_float(daemon.get("done_timeout_seconds"), default=300.0),
        active_window_seconds=_optional_float(daemon.get("active_window_seconds"), default=300.0),
        dry_run=bool(daemon.get("dry_run", False)),
    )


def merge_overrides(config: RuntimeConfig, **overrides: Any) -> RuntimeConfig:
    values = {
        "address": config.address,
        "brightness": config.brightness,
        "pet_id": config.pet_id,
        "assets_dir": config.assets_dir,
        "codex_home": config.codex_home,
        "poll_seconds": config.poll_seconds,
        "done_timeout_seconds": config.done_timeout_seconds,
        "active_window_seconds": config.active_window_seconds,
        "dry_run": config.dry_run,
    }
    for key, value in overrides.items():
        if value is not None:
            values[key] = value
    return RuntimeConfig(**values)


def _table(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _optional_int(value: object, default: int | None = None) -> int | None:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        return int(value)
    return default


def _optional_float(value: object, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        return float(value)
    return default


def _path(value: object, default: Path) -> Path:
    text = _optional_str(value)
    return Path(text).expanduser() if text else default
