# Codex per-session token usage display

## Goal
Show `tokens_used` from active Codex thread in cost slot (2-line area at left edge), analogous to OpenCode dollar cost display.

## Format — Option B (split abbreviation)

```
Line 1 (y=10): 1.5  (mantissa)
Line 2 (y=16): M    (unit suffix)
```

Abbreviation table:

| tokens_used | Line 1 | Line 2 |
|-------------|--------|--------|
| 0–999       | `###`  | ` `    |
| 1,000–9,999 | `#.#`  | `K`    |
| 10K–999K    | `###`  | `K`    |
| 1,000K–9,999K | `#.#` | `M` |
| 10M+        | `###`  | `M`    |

OpenCode cost display unchanged (dollars/cents).

## Changes

### 1. `assistant_state.py` — new dataclass + snapshot field

```python
@dataclass(frozen=True)
class SessionUsage:
    value: int
    display_kind: str  # "tokens"

@dataclass(frozen=True)
class StatusSnapshot:
    ...
    usage: SessionUsage | None = None
```

### 2. `codex_state.py` — extract tokens_used

Add `"tokens_used"` to column list. Add field to `ThreadRow`. In `summarize_thread()`, build `SessionUsage(value=row.tokens_used, display_kind="tokens")` and pass into `StatusSnapshot`. Handle missing column gracefully.

### 3. `daemon.py` — pass usage through pipeline

`render()` passes `snapshot.usage` as new param through `render_status_gif()` → `compose_marquee_gif()`. `render_key()` includes usage in cache hash.

### 4. `marquee.py` — new drawing function

Replace `draw_cost()` call with `draw_usage()` that dispatches:

```python
def draw_usage(draw, usage, cost, x, y1, y2):
    if usage is not None and usage.display_kind == "tokens":
        draw_token_usage(draw, usage.value, x, y1, y2)
    elif cost is not None:
        draw_cost(draw, cost, x, y1, y2)
```

`draw_token_usage()` implements abbreviation + two-line render.

### 5. Tests

- `test_codex_state.py` — token extraction, SessionUsage building, missing column
- `test_marquee.py` — token rendering vs cost rendering
- Cache key test

## What does NOT change
- OpenCode cost display
- Config format, pet packs, display protocol
- Dual-backend composite reader
- Single-backend behavior
