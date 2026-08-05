# Dual-backend support plan

## Goal
`RuntimeConfig` accepts 1+ backends. Daemon polls both each tick, picks highest-priority / most-recent snapshot.

## Changes

### 1. `StatusSnapshot` — add `source` field
- `source: str = ""` in `assistant_state.py:10`
- Composite reader stamps it with `"codex_desktop"` / `"opencode_cli"`

### 2. New `CompositeStatusReader`
- Wraps `list[tuple[str, StatusReader]]` (source_name, reader)
- `current_status()` calls each, catches errors, returns `max(snapshots, key=lambda s: (s.status.priority, s.updated_at_ms or 0))`
- If all fail → `Status(IDLE, reason="all readers failed")`

### 3. `RuntimeConfig` — pluralize backend field (`config.py:80`)
- Replace `assistant_backend: str = "codex_desktop"` with `assistant_backends: tuple[str, ...] = ("codex_desktop",)`
- `merge_overrides()` accepts `assistant_backends` (handles `None`, `str`, `list`, `tuple`)
- `reader_signature()` uses the tuple

### 4. `_assistant_backends()` parser (`config.py:239`)
- Handles both scalar `backend = "opencode_cli"` (backward compat) and list `backends = ["opencode_cli", "codex_desktop"]`
- Validates each entry through alias map, same rejection logic
- If both absent → default `("codex_desktop",)`

### 5. `state_reader_for_config()` (`daemon.py:200`)
- Single backend → existing behavior (direct reader, no composite)
- 2+ backends → `CompositeStatusReader` with one reader per backend

### 6. CLI — `--assistant-backend` repeatable (`cli.py:52,65`)
- Change to `action='append'` with `choices=ASSISTANT_BACKENDS`
- `_config_from_args()` passes list as `assistant_backends` to `merge_overrides`
- Backward compat: single use works identically

### 7. `print_status` (`cli.py:173`)
- Composite reader returns single snapshot with source field → print includes source
- `status=thinking source=opencode_cli: thinking about tests`

### 8. Tests to update
- `test_config.py` — test `backends = ["opencode_cli", "codex_desktop"]` parsing, mixed aliases, backward compat with `backend`, error case for invalid backend in list
- `test_daemon.py` — test `CompositeStatusReader` picks highest priority across backends, one reader failing, tie-breaking by recency
- `test_cli.py` — test `--assistant-backend` repeatable, single use still works
- `test_hot_reload.py` — test backend list change triggers reader reconfigure

## What does NOT change
- `PetPack`, `PetConfig`, `pet.json` format — no new required frame sets
- Display layer — no new labels/badges (source in status line only)
- `Status` enum — priorities unchanged
- Config file sections `[codex]` / `[opencode]` — both always present, individual readers use their own
- Backward compat with `backend = "opencode_cli"` in existing configs

## Config TOML examples
```toml
# Single backend (same as before)
[assistant]
backend = "opencode_cli"

# Dual backend
[assistant]
backends = ["opencode_cli", "codex_desktop"]
```

## Design note
`CompositeStatusReader` is stateless (like individual readers). It doesn't cache or alternate — polls both every tick, returns most active snapshot. "Cycling" emerges naturally: if Codex is thinking and OpenCode is idle, you see Codex; when Codex finishes and OpenCode starts thinking, display switches.
