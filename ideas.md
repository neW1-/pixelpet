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
