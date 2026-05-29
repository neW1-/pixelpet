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

See [plan.md](/Users/martin/Documents/PixelPet/plan.md) for the design details.
