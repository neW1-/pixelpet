# PixelPet Agent Notes

## High-value commands
- Run from source with imports working: `PYTHONPATH=src python -m pixelpet.cli <subcommand>`.
- Tests use `unittest` discovery (not `pytest`): `PYTHONPATH=src python -m unittest discover -s tests`.
- Focused test runs: `PYTHONPATH=src python -m unittest tests.test_opencode_state` or `... tests.test_opencode_state.OpencodeStateReaderTest.test_running_tool_sets_working_activity`.

## Architecture that affects edits
- Single package: `src/pixelpet`; console entrypoint is `pixelpet.cli:main` in `pyproject.toml`.
- Runtime flow: `src/pixelpet/cli.py` -> `src/pixelpet/daemon.py` -> backend reader (`codex_state.py` / `opencode_state.py`) -> display driver.
- Pet packs are runtime data, not docs: `assets/pets/<pet_id>/pet.json` must map every required status to real GIF files.

## Backend/config traps
- CLI `--assistant-backend` only accepts `codex_desktop` or `opencode_cli`.
- Config parser accepts aliases (`opencode` / `codex`) and normalizes them; CLI does not.
- Default config path is repo-root `config.toml`; missing file falls back to `RuntimeConfig` defaults.
- TOML strings must be quoted (`backend = "opencode_cli"`); unquoted values fail parsing.

## Playback/hot-reload quirks
- `pixelpet run` hot-reloads config by default; disable with `--no-hot-reload` or `[daemon].hot_reload = false`.
- `playback` modes are `gif` and `stream`; code default is `gif`.
- `stream` mode extracts/caches PNG frames under `.pixelpet/render-cache/frames` and requires Pillow.
- `replay_gifs` only impacts GIF playback: unchanged GIFs can be resent after their own duration.

## Scripts and assets
- `scripts/start_pixelpet.sh` expects `.venv/bin/pixelpet` (editable install), not `PYTHONPATH` execution.
- Start/stop scripts own PID/log lifecycle under `.pixelpet/` and clear stale PID files.
- Built-in asset generation rewrites `assets/pets/dino/gifs` and `assets/pets/hal/gifs` via `scripts/generate_builtin_dino.py` and `scripts/generate_builtin_hal.py`.
