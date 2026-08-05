# PixelPet

PixelPet is a small Python daemon that shows assistant status on a 32x32 iPixel/MT LED display.

It reads local Codex Desktop or OpenCode CLI state, selects a status, and sends the matching pet GIF to the display with `pypixelcolor`.

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

Print the current inferred assistant status once:

```bash
PYTHONPATH=src python -m pixelpet.cli status
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

Start or stop the background daemon with the project script:

```bash
scripts/start_pixelpet.sh
scripts/stop_pixelpet.sh
```

`start_pixelpet.sh` writes logs and the PID under `.pixelpet/`. If the daemon
exits during startup, the script removes the stale PID file and prints the log
output from that failed launch.

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
source = "thread_title" # active assistant thread/session title
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

## Assistant Backends

PixelPet supports three assistant state backends:

- `codex_desktop`: reads Codex Desktop state from `state_5.sqlite` under the configured Codex home.
- `opencode_cli`: reads the local OpenCode SQLite database directly, across all unarchived OpenCode sessions.
- `vscode_copilot`: reads VS Code Copilot agent-mode transcripts
  (`workspaceStorage/<hash>/GitHub.copilot-chat/transcripts/*.jsonl`) under the
  VS Code user data directory, enriched with session metadata from
  `globalStorage/github.copilot-chat/session-store.db`.

Select the backend in `config.toml`. `backend` accepts one name or a list to
watch several at once (the most recently active session wins):

```toml
[assistant]
backend = "codex_desktop"   # single: codex_desktop | opencode_cli | vscode_copilot
# or watch several backends at once:
backend = ["codex_desktop", "opencode_cli", "vscode_copilot"]

[codex]
home = "/Users/martin/.codex"

[opencode]
db_path = "/Users/martin/.local/share/opencode/opencode.db"

[vscode]
user_dir = "/Users/martin/Library/Application Support/Code"
```

TOML string values must be quoted. Use `backend = "opencode_cli"`, not
`backend = opencode_cli`.

`vscode_copilot` uses the platform VS Code user data dir by default (`Code`,
`Code - Insiders`, or `VSCodium`), which `[vscode] user_dir` overrides. Status
mapping: an open agent turn or tool execution means `working`, a recently
completed turn is `done`, and stale or missing sessions are `idle`. The
transcripts record no pending-approval or waiting-input marker, so
`vscode_copilot` never emits `permission_required` or `needs_input`.

`codex_desktop` remains the default for existing configs. `opencode_cli`
passively reads OpenCode state without launching `opencode` or requiring
`opencode serve`. `pixelpet run` and `pixelpet status` also accept
`--assistant-backend` (repeatable for multiple backends), `--opencode-db-path`,
and `--vscode-user-dir` for temporary overrides.

OpenCode status mapping uses the existing PixelPet states:

- pending OpenCode tool approval -> `permission_required`
- running assistant or tool activity -> `working`
- recently completed assistant message -> `done`
- assistant error or abort -> `failed_offline`
- no active or recent session -> `idle`

See [plan.md](/Users/martin/Documents/PixelPet/plan.md) for the design details.
