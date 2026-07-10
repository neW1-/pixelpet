from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ASSISTANT_BACKENDS: tuple[str, ...] = ("codex_desktop", "opencode_cli")


class ConfigError(ValueError):
    pass


def default_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()


def default_opencode_db_path() -> Path:
    configured = os.environ.get("OPENCODE_DB_PATH")
    if configured:
        return Path(configured).expanduser()
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return (data_home / "opencode" / "opencode.db").expanduser()


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


def default_render_cache_dir() -> Path:
    return project_root() / ".pixelpet" / "render-cache"


DEFAULT_MARQUEE_SOURCES: tuple[str, ...] = ("status", "activity", "thread_title")


@dataclass(frozen=True)
class MarqueeConfig:
    enabled: bool = True
    badge_patterns: bool = True
    source: str = "thread_title"
    sources: tuple[str, ...] = DEFAULT_MARQUEE_SOURCES
    separator: str = " / "
    per_source_max_chars: int | None = 16
    font: str = "3x5"
    max_chars: int = 24
    frame_ms: int = 120
    scroll_step_px: int = 2
    max_frames: int = 72
    cache_dir: Path = field(default_factory=default_render_cache_dir)


@dataclass(frozen=True)
class RuntimeConfig:
    address: str | None = None
    brightness: int | None = 20
    save_slot: int | None = None
    playback: str = "gif"
    stream_frame_ms: int = 220
    pet_id: str = "dino"
    assets_dir: Path = default_assets_dir()
    assistant_backend: str = "codex_desktop"
    codex_home: Path = default_codex_home()
    opencode_db_path: Path = default_opencode_db_path()
    poll_seconds: float = 3.0
    done_timeout_seconds: float = 300.0
    active_window_seconds: float = 300.0
    hot_reload: bool = True
    replay_gifs: bool = True
    dry_run: bool = False
    marquee: MarqueeConfig = field(default_factory=MarqueeConfig)


def load_config(path: Path | None = None) -> RuntimeConfig:
    config_path = path or default_config_path()
    if not config_path.exists():
        return RuntimeConfig()

    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {config_path}: {exc}") from exc
    display = _table(data.get("display"))
    pet = _table(data.get("pet"))
    daemon = _table(data.get("daemon"))
    assistant = _table(data.get("assistant"))
    codex = _table(data.get("codex"))
    opencode = _table(data.get("opencode"))
    marquee = _table(data.get("marquee"))

    return RuntimeConfig(
        address=_optional_str(display.get("address")),
        brightness=_optional_int(display.get("brightness"), default=20),
        save_slot=_optional_int(display.get("save_slot"), default=None),
        playback=_playback_mode(display.get("playback")),
        stream_frame_ms=_optional_int(display.get("stream_frame_ms"), default=220) or 220,
        pet_id=_optional_str(pet.get("id")) or "dino",
        assets_dir=_path(pet.get("assets_dir"), default_assets_dir()),
        assistant_backend=_assistant_backend(assistant.get("backend")),
        codex_home=_path(codex.get("home"), default_codex_home()),
        opencode_db_path=_path(opencode.get("db_path"), default_opencode_db_path()),
        poll_seconds=_optional_float(daemon.get("poll_seconds"), default=3.0),
        done_timeout_seconds=_optional_float(daemon.get("done_timeout_seconds"), default=300.0),
        active_window_seconds=_optional_float(daemon.get("active_window_seconds"), default=300.0),
        hot_reload=_optional_bool(daemon.get("hot_reload"), default=True),
        replay_gifs=_optional_bool(daemon.get("replay_gifs"), default=True),
        dry_run=bool(daemon.get("dry_run", False)),
        marquee=MarqueeConfig(
            enabled=_optional_bool(marquee.get("enabled"), default=True),
            badge_patterns=_optional_bool(marquee.get("badge_patterns"), default=True),
            source=_optional_str(marquee.get("source")) or "thread_title",
            sources=_optional_str_tuple(marquee.get("sources"), DEFAULT_MARQUEE_SOURCES),
            separator=_optional_raw_str(marquee.get("separator")) or " / ",
            per_source_max_chars=_optional_int(marquee.get("per_source_max_chars"), default=16),
            font=_optional_str(marquee.get("font")) or "3x5",
            max_chars=_optional_int(marquee.get("max_chars"), default=24) or 24,
            frame_ms=_optional_int(marquee.get("frame_ms"), default=120) or 120,
            scroll_step_px=_optional_int(marquee.get("scroll_step_px"), default=2) or 2,
            max_frames=_optional_int(marquee.get("max_frames"), default=72) or 72,
            cache_dir=_path(marquee.get("cache_dir"), default_render_cache_dir()),
        ),
    )


def merge_overrides(config: RuntimeConfig, **overrides: Any) -> RuntimeConfig:
    values = {
        "address": config.address,
        "brightness": config.brightness,
        "save_slot": config.save_slot,
        "playback": config.playback,
        "stream_frame_ms": config.stream_frame_ms,
        "pet_id": config.pet_id,
        "assets_dir": config.assets_dir,
        "assistant_backend": config.assistant_backend,
        "codex_home": config.codex_home,
        "opencode_db_path": config.opencode_db_path,
        "poll_seconds": config.poll_seconds,
        "done_timeout_seconds": config.done_timeout_seconds,
        "active_window_seconds": config.active_window_seconds,
        "hot_reload": config.hot_reload,
        "replay_gifs": config.replay_gifs,
        "dry_run": config.dry_run,
        "marquee": config.marquee,
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


def _optional_raw_str(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _optional_str_tuple(value: object, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
    elif isinstance(value, list | tuple):
        items = [item.strip() for item in value if isinstance(item, str)]
    else:
        return default
    return tuple(item for item in items if item) or default


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


def _optional_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _playback_mode(value: object) -> str:
    mode = (_optional_str(value) or "gif").lower()
    if mode not in {"gif", "stream"}:
        return "gif"
    return mode


def _assistant_backend(value: object) -> str:
    backend = (_optional_str(value) or "codex_desktop").lower()
    aliases = {
        "codex": "codex_desktop",
        "codex-desktop": "codex_desktop",
        "opencode": "opencode_cli",
        "opencode-cli": "opencode_cli",
    }
    backend = aliases.get(backend, backend)
    if backend not in ASSISTANT_BACKENDS:
        allowed = ", ".join(ASSISTANT_BACKENDS)
        raise ConfigError(f"Unknown assistant backend {backend!r}; expected one of: {allowed}")
    return backend


def _path(value: object, default: Path) -> Path:
    text = _optional_str(value)
    return Path(text).expanduser() if text else default
