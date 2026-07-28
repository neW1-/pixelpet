# PixelPet Ideas

## Implemented Now

- Better activity labels.
- Configurable rotate separator and per-source character limits.
- Visual notification patterns.
- Hot config reload.
- Assistant backend selection with `codex_desktop` and `opencode_cli`.
- Passive OpenCode CLI status reading from the local OpenCode SQLite database.
- Startup script health check that removes stale PID files and prints the failed launch log output.

These improve the amount of useful assistant detail shown on the 32x32 display without changing the display protocol or requiring new pet artwork.

## Backlog

- Privacy controls for marquee text: redact URLs, file paths, prompt-like long titles, and secrets-looking values before rendering.
- Service management commands: add `pixelpet service install/start/stop/status` around the macOS LaunchAgent.
- Preview tooling: generate a local GIF or contact sheet for a status/source combination before sending to hardware.
- Per-status pet variants: allow different pet packs or animations for selected statuses.
- Backend filtering: allow OpenCode to track only configured directories, projects, agents, or session title patterns instead of all sessions.
- Backend diagnostics: add `pixelpet status --verbose` to show which backend, database, session, and reason produced the current state.
- OpenCode schema guardrails: detect unsupported database schema changes and print a targeted upgrade/fallback message.

## Proposed

- Multi-display support: send status to multiple BLE displays simultaneously.
- CI/checks integration: lint, typecheck, and test runner pipeline for CI.
- Menu bar app: macOS tray indicator showing current status without display hardware.
- Pet rotation schedules: cycle active pet by time-of-day, day-of-week, or session context.
- LED simulator: local GUI window previewing what the display would render.
- Status alerts: notify (macOS notification) when `permission_required` or `failed_offline` exceeds a threshold.
- Custom fonts: selectable marquee fonts beyond built-in 3x5 bitmap.
- Config profiles: named presets (`work`/`personal`) switchable via CLI flag.

### Reliability / Ops

- Reconnection backoff: exponential backoff on BLE disconnect to avoid thrash.
- Graceful shutdown: SIGTERM/SIGHUP handler to disconnect display cleanly.
- Cache eviction: LRU or size-limit eviction for `.pixelpet/render-cache/`.
- Display watchdog: detect frozen stream playback and auto-recover.
- Config schema validation: type-check TOML values at load, fail fast on bad types.

### Developer Experience

- Logging framework: replace bare `print()` with `logging` — levels, file output, structured.
- `__main__.py`: add `python -m pixelpet` entry point.
- CI pipeline: GitHub Actions for lint (ruff), typecheck (mypy), tests.
- Pre-commit hooks: ruff + mypy on commit.

### Display / Marquee

- Day/night brightness schedule: auto-dim display based on time.
- Per-status brightness: different brightness per status (bright for `permission_required`, dim for `idle`).
- Screen dimmer: blank display after N idle minutes.
- Color themes: configurable marquee/badge colors.
- State transition animations: crossfade or wipe between status GIFs.

### Integration

- HTTP status endpoint: query current daemon status via local HTTP.
- Webhook on status change: POST to URL when status flips.
- GitHub Actions status source: watch GitHub checks as a direct backend.
- MQTT bridge: publish status to MQTT topic.

### Testing

- Integration test for full pipeline: state reader → render → display.
- Marquee render snapshot tests: compare output GIF against reference.
- Property-based/fuzz tests: random event sequences for state readers.

### Pet System

- Multi-GIF per status: cycle/random pick from several GIFs per status.
- GIF speed multiplier: configurable playback speed per pet.
- AI pet generator: `pixelpet pets generate dino "sleeping dinosaur"` — calls image gen API.

### CLI Polish

- Shell completions: bash/zsh completion generation.
- `--json` flag: machine-readable output on `status` and `pixelpet list`.
- `pixelpet config validate`: check TOML correctness.
- `pixelpet doctor`: diagnostic command — check DB paths, display connectivity, Pillow.
