---
name: init-agent-hub
description: Create a reusable Agent Hub for a software project in the central Agent Hub state store with deterministic file-backed orchestration. Use when a user asks to initialize or set up an agent coordination hub, shared task board, AI agent issue tracker, or workspace for multi-agent ownership, dependency, review, and handoff workflows.
---

# Init Agent Hub

Create an Agent Hub v3 central hub. The central hub under `~/.agents-hub/` (or `AGENT_HUB_HOME`) is the only durable source of truth for repo work.

## Central Store Workflow

1. Determine the target repository root.
2. If a legacy repo-local `.hub/config.yml` already exists, use the migration command instead of initializing a second empty hub.
3. Prefer the unified v3 CLI:

```bash
python3 <repo>/skills/manage-agent-hub-issues/scripts/agent_hub.py --repo '<repo-path>' init --project-name '<Project Name>'
```

4. If the unified CLI is unavailable, use the compatibility init script:

```bash
python3 <skill-dir>/scripts/init_file_hub.py --repo '<repo-path>' --project-name '<Project Name>'
```

5. Verify the reported central hub path exists with `config.yml`, `state.yml`,
   `project/`, `changes/`, `issues/`, `decisions/`, `reports/`, `artifacts/`,
   and `.gitignore` containing `runtime/`.
6. If the user gave an initial task, create the first issue through the deterministic v3 command surface or `create-agent-hub-issue`.
7. Report the central hub path and remind the user that external notes and legacy `.hub` files are context only.

## Central Layout

```text
~/.agents-hub/projects/<project-id>/
|-- project.json
`-- hub/
    |-- config.yml
    |-- state.yml
    |-- .gitignore
    |-- project/
    |-- changes/
    |-- issues/
    |-- decisions/
    |-- reports/
    |-- artifacts/
    `-- runtime/      # active locks and local viewer state
```

`config.yml` should set `version: 3`, `source_of_truth: file`, deterministic
strict writes, subagent-first behavior, and read-only dashboard defaults.
