# feat: vscode_copilot assistant backend

Add a third assistant state backend to PixelPet that watches VS Code Copilot
agent-mode sessions (the `copilot-agent` JSONL transcripts). It reflects the
same architecture as `opencode_state.py` / `codex_state.py`: a `StatusReader`
that returns one `StatusSnapshot` per poll.

## Data source

VS Code changed where it stores Copilot sessions, so the reader opens all three:

- **Primary (legacy):** Copilot agent transcripts, per-workspace JSONL files:
  `<User>/workspaceStorage/<hash>/GitHub.copilot-chat/transcripts/<sessionId>.jsonl`
  (glob `*/GitHub.copilot-chat/transcripts/*.jsonl` under `<User>/workspaceStorage`).
- **Mutation log (current):** `<User>/workspaceStorage/<hash>/chatSessions/<sessionId>.jsonl`,
  a `{"kind":N,"k":[...],"v":...}` op log; `read_copilot_session_state` replays
  the ops into a session snapshot. Kinds `0/1/2` set a snapshot / scalar / array.
- **Empty-window snapshots:** `<User>/globalStorage/emptyWindowChatSessions/<sessionId>.jsonl`
  - a single `{"kind":0,"v":{...}}` session snapshot.
- **Metadata enrichment:** `<User>/globalStorage/github.copilot-chat/session-store.db`
  `sessions` table (id, cwd, repository, agent_name, summary, updated_at) keyed by
  session id == file stem. Yields real titles, workspaces, and agent names.
- Files are deduped by session id, newest mtime wins; `snapshot_events` maps the
  state's `requests` / `toolInvocationSerialized` / `modelState.completedAt` into the
  same event shape the legacy parser emits.
- `<User>` resolution: `VSCODE_USER_DIR` env -> `--vscode-user-dir` -> platform
  default (`~/Library/Application Support/Code`, `~/.config/Code`,
  `%APPDATA%\Code`) with `Code - Insiders` / `VSCodium` fallbacks.

### Transcript event schema (verified on real data, `producer: "copilot-agent"`)

```
session.start          { data: { sessionId, version, producer, startTime, context{cwd} } }
user.message           { data: { content } }
assistant.turn_start   { data: { turnId } }
assistant.message      { data: { messageId, content, toolRequests[ {toolCallId,name,arguments} ] } }
tool.execution_start   { data: { toolCallId, toolName, arguments } }
tool.execution_complete{ data: { toolCallId, success, result } }
assistant.turn_end     { data: { turnId } }
```

Every entry has `id`, ISO `timestamp`, `parentId`.

### Session-state schema (chatSessions / emptyWindowChatSessions)

A snapshot `v` holds `requests[]`; each request carries `timestamp`,
`responseTimestamp`, `message.text`, a `response[]` of text values and
`toolInvocationSerialized` items (`toolCallId`, `toolId`,
`isComplete`), and `modelState.completedAt`. Work is `in progress` while any
tool lacks `isComplete` or the latest request has no `completedAt`; a request
with `completedAt` maps to a closed turn (`DONE`). Non-empty `pendingRequests`
signal queued agent work (`WORKING`).

## Status inference

- **Open turn:** last `assistant.turn_start` has no matching `assistant.turn_end`.
- **Open tool:** a `tool.execution_start` without a matching `tool.execution_complete`
  (matched by `toolCallId`).
- Within `active_window_seconds`, open turn or open tool -> `WORKING`.
  Activity mapping (reuses `codex_state.activity_for_command`):
  - `run_in_terminal` / `bash` -> `activity_for_command(arguments)`
  - `apply_patch` / `create_file` / `edit_file` / `write_file` / `delete_file` -> PATCHING
  - `read_file` / `list_dir` / `file_search` / `grep_search` -> READING FILES
  - `web_search` / `fetch_webpage` -> SEARCHING WEB
  - `github-*` (MCP) -> CHECKING GITHUB
  - anything else -> USING TOOL
- Latest turn closed within `done_timeout_seconds` -> `DONE`.
- No open/recent work -> `IDLE`.
- State dir unreadable / no transcripts dir -> `FAILED_OFFLINE`.

Sessions are ordered by latest activity (max of file mtime / newest event /
session-store `updated_at`); the most recent active session wins.

## Known limitation

No VS Code data source carries a pending-approval / waiting-input marker
(checked: transcripts, `session-store.db`, and `~/.copilot/session-state/`).
The `vscode_copilot` backend therefore emits `working`, `done`, `idle`,
`failed_offline` only - no `permission_required` / `needs_input`.

## Files

| File | Change |
|---|---|
| `src/pixelpet/vscode_state.py` | NEW - reader + session model + summarize + parsers |
| `src/pixelpet/config.py` | backend registry, aliases, `vscode_user_dir`, `[vscode]` table |
| `src/pixelpet/daemon.py` | `state_reader_for_config`, `reader_signature` |
| `src/pixelpet/cli.py` | `--vscode-user-dir` on `run` / `status` |
| `README.md` | backend docs |
| `tests/test_vscode_state.py` | NEW - fixture-driven reader tests |
| `tests/test_config.py`, `tests/test_cli.py` | backend + flag wiring |

## Config shape

```toml
[assistant]
backend = "vscode_copilot"   # aliases: vscode, vscode-copilot, copilot

[vscode]
user_dir = "/Users/martin/Library/Application Support/Code"
```

## Verification

```bash
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m pixelpet.cli status --assistant-backend vscode_copilot --dry-run
```
