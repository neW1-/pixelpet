# PixelPet Plan

## Goal

Build a small Codex status pet for a 32x32 iPixel/MT LED matrix. The first version should run as a Python CLI daemon, infer Codex Desktop status from local Codex state, and upload simple GIF animations to the display through `pypixelcolor`.

## Locked V1 Decisions

- Display target: 32x32 LED matrix.
- Runtime: Python CLI daemon.
- Display library: `lucagoc/pypixelcolor`, using `AsyncClient`, `connect()`, `set_brightness()`, and `send_image()` for GIFs.
- Animation format: GIFs for all states.
- Asset model: configurable LED pet packs, separate from Codex Desktop's full-size pet atlas.
- Built-in starter pet: `dino`.
- Config chooses the active pet by id.
- Brightness: fixed configurable value.
- Upload strategy: upload a GIF only when the status changes.
- Codex scope: Codex Desktop threads only; CLI sessions are ignored for v1.
- Read receipt model: no reliable local read receipt was found, so `done` clears by timeout.
- Default done timeout: 5 minutes.

## V1 Status Set

The display has limited resolution, so V1 uses six clear states:

| Status | Meaning | Dino visual |
| --- | --- | --- |
| `idle` | Nothing active or attention-worthy | Sleeping/snoozing Dino |
| `working` | Codex is actively running a turn | Dino pacing |
| `needs_input` | Codex is waiting for a user response | Dino with blue `!` bubble |
| `permission_required` | Codex is waiting for approval | Dino with orange `?` bubble |
| `done` | Codex recently completed a turn | Happy Dino with check mark |
| `failed_offline` | Codex state/display failed, or latest turn aborted | Sad Dino with red X |

Priority order:

1. `permission_required`
2. `needs_input`
3. `failed_offline`
4. `working`
5. `done`
6. `idle`

## Codex Status Detection

The daemon reads local Codex Desktop state without sending data elsewhere.

Primary sources:

- `~/.codex/state_5.sqlite`, opened read-only.
- Each thread's `rollout_path` JSONL transcript, read as a tail only.

Detection rules:

- Ignore rows with `source = cli` or `thread_source = cli`.
- Treat pending `response_item` entries with `payload.type = function_call` as active calls until a matching `function_call_output` arrives.
- `permission_required` when a pending call has `sandbox_permissions = require_escalated` or a `justification`.
- `needs_input` when a pending call name is `request_user_input` or `requestUserInput`.
- `working` when the latest turn has started, has not reached a terminal event, and has recent activity.
- `done` when the latest turn has `task_complete` within the configured done timeout.
- `failed_offline` when the state DB cannot be read, a rollout cannot be parsed in a critical path, or the latest turn was aborted.
- `idle` when no Desktop thread is active, waiting, recently done, or failed.

Privacy constraints:

- Do not render transcript text on the display.
- Do not log prompt content by default.
- Only use structural events and tool-call metadata needed for status.

## Pet Pack Format

Each pet pack is a folder under `assets/pets/<pet_id>` or another configured assets root.

Required files:

```text
assets/pets/dino/
  pet.json
  gifs/
    idle.gif
    working.gif
    needs_input.gif
    permission_required.gif
    done.gif
    failed_offline.gif
  prompts/
    README.md
```

Manifest shape:

```json
{
  "schema": 1,
  "id": "dino",
  "display_name": "Dino",
  "size": [32, 32],
  "states": {
    "idle": "gifs/idle.gif",
    "working": "gifs/working.gif",
    "needs_input": "gifs/needs_input.gif",
    "permission_required": "gifs/permission_required.gif",
    "done": "gifs/done.gif",
    "failed_offline": "gifs/failed_offline.gif"
  }
}
```

Adding a new pet:

1. Run `pixelpet pets create <pet_id>`.
2. Replace the generated placeholder GIFs or create new 32x32 GIFs in the pack.
3. Run `pixelpet pets validate <pet_id>`.
4. Select it with config or `pixelpet run --pet <pet_id>`.

The first implementation includes a deterministic Dino pixel-art generator so the pipeline can be tested without waiting on external image generation. Later, image-generated source art can be cleaned and quantized into the same pack format.

## Configuration

Expected config path:

```text
/Users/martin/Documents/PixelPet/config.toml
```

Example:

```toml
[display]
address = "AA:BB:CC:DD:EE:FF"
brightness = 20

[pet]
id = "dino"
assets_dir = "/Users/martin/Documents/PixelPet/assets/pets"

[daemon]
poll_seconds = 3
done_timeout_seconds = 300

[codex]
home = "/Users/martin/.codex"
```

Every config field can be overridden by CLI flags.

## Implementation Milestones

1. Write this `plan.md`.
2. Scaffold the Python package and CLI.
3. Implement Codex Desktop status detection with tests.
4. Implement pet-pack discovery, creation, validation, and selection.
5. Implement the `pypixelcolor` display adapter and daemon loop.
6. Generate and validate the built-in Dino GIF pack.
7. Run local verification:
   - Unit tests with `unittest`.
   - Pet-pack validation.
   - Dry-run daemon status output.

## Non-goals For V1

- No direct reuse of full Codex pet atlases at runtime.
- No streaming individual pixels.
- No corner-dot overlay compositing in the first version.
- No CLI-session support.
- No automatic daemon installation or launch agent.
- No multi-display support.
