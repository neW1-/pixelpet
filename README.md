# PixelPet

PixelPet is a small Python daemon that shows Codex Desktop status on a 32x32 iPixel/MT LED display.

It reads local Codex Desktop state from `~/.codex/state_5.sqlite`, selects a status, and sends the matching pet GIF to the display with `pypixelcolor`.

The default config lives at `config.toml` next to `pyproject.toml`.

## Quick Start

Generate the built-in Dino assets:

```bash
python scripts/generate_builtin_dino.py
```

Generate the built-in HAL assets:

```bash
python scripts/generate_builtin_hal.py
```

Run without hardware:

```bash
PYTHONPATH=src python -m pixelpet.cli run --dry-run
```

Validate a pet pack:

```bash
PYTHONPATH=src python -m pixelpet.cli pets validate dino
```

Run against a display:

```bash
PYTHONPATH=src python -m pixelpet.cli run --address AA:BB:CC:DD:EE:FF --pet dino
```

Send one status GIF and exit:

```bash
PYTHONPATH=src python -m pixelpet.cli run --address AA:BB:CC:DD:EE:FF --pet dino --once
```

Force a specific status for display testing:

```bash
PYTHONPATH=src python -m pixelpet.cli show needs_input --address AA:BB:CC:DD:EE:FF --pet dino
```

Force a status with a marquee message:

```bash
PYTHONPATH=src python -m pixelpet.cli show working --message "BUILDING HAL MARQUEE" --dry-run
```

The daemon hot-reloads `config.toml` by default while `pixelpet run` is active.
Use `hot_reload = false` under `[daemon]` or pass `--no-hot-reload` to disable it.
The recommended playback mode is `playback = "gif"`. PixelPet keeps marquee
GIFs small with `scroll_step_px` and `max_frames`, because very long GIFs can be
slow or unreliable on the display. Generated GIFs also end with a few clean
marquee-lane frames, so hardware that holds the final frame does not freeze on
partial text. `replay_gifs = true` re-sends an unchanged GIF after that GIF's own
duration elapses. `playback = "stream"` is available as a debugging fallback,
but it sends a full PNG per frame over BLE and is slow.

Marquee sources in `config.toml`:

```toml
source = "thread_title" # active Codex thread title
source = "reason"       # status reason, such as approval/input text
source = "activity"     # compact activity, such as RUNNING TESTS or PATCHING
source = "status"       # short labels like WORK, INPUT, APPROVE
source = "thread_id"    # short active thread id

source = "rotate"
sources = ["status", "activity", "thread_title"]
separator = " / "
per_source_max_chars = 16
scroll_step_px = 2
max_frames = 72
badge_patterns = true
```

`max_chars` still controls a single-source marquee. When `source = "rotate"`,
`per_source_max_chars` caps each configured source before they are joined with
`separator`.

With `badge_patterns = true`, PixelPet redraws the upper-left badge at runtime:
orange blinks for approval, blue pulses for input, red flashes for failed/offline,
and working uses the original rotating cyan dots.

See [plan.md](/Users/martin/Documents/PixelPet/plan.md) for the design details.
