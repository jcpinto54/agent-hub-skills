---
name: run-agent-hub-app
description: Start or refresh the local read-only Agent Hub viewer app for central Agent Hub projects. Use when a user asks to run, open, launch, serve, refresh, or get a link to the Agent Hub app, dashboard, Kanban viewer, or hub UI for a repository or change packet.
---

# Run Agent Hub App

Use the bundled runner to export a fresh dashboard snapshot and serve the
dependency-free viewer from `list-agent-hub-issues`.

## Workflow

1. Choose the target repository. Default to the current working directory unless
   the user names another repo.
2. Run:

```bash
python3 <skill-dir>/scripts/run_agent_hub_app.py --repo '<target-repo>'
```

3. For a change-filtered dashboard, add `--change`:

```bash
python3 <skill-dir>/scripts/run_agent_hub_app.py --repo '<target-repo>' --change '<change-slug>'
```

4. Report the returned `url` to the user. If the script reused an existing
   server, the snapshot was still refreshed before reuse.

## Options

- Use `--port 8766` to request a different starting port. If the requested port
  is held by an unrelated service, the runner picks the next free local port.
- Use `--host 127.0.0.1` by default. Do not bind to public interfaces unless the
  user explicitly asks for that.
- Use `--foreground` only when the user wants to keep the server attached to the
  current terminal.
- Use `--hub-root <path>` only for explicit legacy or test hub overrides.

## Behavior

- Exports `hub-state.json` through the Agent Hub v3 `dashboard export` command.
- Serves the existing static viewer directory at `http://<host>:<port>`.
- Reuses a live viewer server on the selected port instead of starting a
  duplicate.
- Writes server logs and PID metadata under the central hub's `runtime/`,
  which is local runtime state shared by linked worktrees.

## Safety

- Treat the viewer as read-only. It should not mutate hub files.
- Do not use this skill for issue claiming, status changes, or agent loops.
- If dashboard export fails, report the error and do not serve stale state as if
  it were fresh.
