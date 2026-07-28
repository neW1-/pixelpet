# OpenCode Cost Display for Hal9000

## Goal
Show the current OpenCode session cost (in dollars, no `$` sign) on the 32×32
pixel LED display, positioned to the left of the Hal9000 outline, below the
status badge.

## Layout (pixel coordinates)

```
┌────────────┬──────────────────────┐
│ Status     │  Scrolling           │
│ Badge      │  marquee text        │  y=0..9
│ (0..9)     │  (10..31)            │
├────┬───────┼──────────────────────┤
│cost│       │                      │
│line1│      │  HAL9000 body        │  y=10..14 (5px font, row 1)
│    │       │  (8..31)             │
│cost│       │                      │
│line2│      │                      │  y=16..20 (5px font, row 2)
│    │       │                      │
└────┴───────┴──────────────────────┘
x=0  x=8                           x=31
```

- **Cost line 1**: `(x=0, y=10)` — integer/dollars part, below the status badge
- **Cost line 2**: `(x=0, y=16)` — fractional/cents part, below line 1
- Each line uses the existing `FONT_3X5` bitmap (3px wide + 1px spacing = 4px/char)
- 8px width → max **2 characters per row**
- Example: cost `0.42` → line 1: `0`, line 2: `42`; cost `1.23` → line 1: `1`, line 2: `23`

## Files to modify

| # | File | Change |
|---|------|--------|
| 1 | `src/pixelpet/assistant_state.py` | Add `cost: float \| None = None` to `StatusSnapshot` |
| 2 | `src/pixelpet/opencode_state.py` | Read `session.cost` from DB (cumulative). Fall back to `data.usage.cost` for legacy. Add `cost` to `OpencodeSession`. |
| 3 | `src/pixelpet/codex_state.py` | Same: extract cost from rollout events data and pass to `StatusSnapshot` |
| 4 | `src/pixelpet/marquee.py` | Add `draw_cost()` function + `draw_text_unclipped()`. Add `cost` param to `compose_marquee_gif()` and `render_status_gif()`. Include cost in cache key. |
| 5 | `src/pixelpet/daemon.py` | Pass `snapshot.cost` through `render()` to the marquee pipeline. |
| 6 | `tests/test_opencode_state.py` | Add `cost` column to test DB schema. Test session-level cost + legacy fallback. |

## Drawing details (marquee.py)

New constants:
```python
COST_X = 0
COST_Y_LINE1 = 10
COST_Y_LINE2 = 16
```

New function `draw_text_unclipped()` — same as `draw_text()` but without
`_inside_lane` clipping (so it can draw outside the marquee lane).

New function `draw_cost()` — splits float into dollars/cents, draws two lines.

`render_key()` includes formatted cost so different costs produce different
cached GIFs.

## Cost data source

OpenCode DB stores cumulative cost on the **session** table (`session.cost`),
not per-message. Each assistant message also has its own `data.cost`, but that
is per-turn, not cumulative.

```python
# Primary: cumulative session cost (what the console shows)
session_cost = session_row["cost"]  # e.g. 1.15

# Fallback: per-message cost (legacy, not cumulative)
message_cost = latest_assistant.data.get("usage", {}).get("cost")
```

In `summarize_session()` (`opencode_state.py`), prefer `session.cost`. Fall back
to per-message cost only when session cost is 0/missing (backward compat with
older DB schemas).

`OpencodeSession` dataclass now includes `cost: float = 0.0`.
`_read_state()` reads `cost` from the session table query.

## Rendering pipeline update

`daemon.py` `render()` method passes cost through:
```
StatusSnapshot.cost → render_status_gif(…, cost=cost) → compose_marquee_gif(…, cost=cost)
```

## Edge cases
- **Very small costs** (e.g. 0.0042): multiplied by 100, so shows `0` / `42`
- **Costs > $99.99**: truncates to 2 chars per row
- **Costs < $0.01**: shows `0` / `01` after rounding to cents
- **No cost data**: cost is `None`, nothing is drawn
