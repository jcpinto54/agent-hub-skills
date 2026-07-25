---
name: create-agent-hub-issue
description: Create central Agent Hub issues, follow-ups, decisions, open questions, and handoffs. Use when a user asks to add, file, create, record, split, or sequence durable work items in an Agent Hub.
---

# Create Agent Hub Issue

For repo work, the central hub's `issues/<issue-id>.md` is the canonical durable record. Use deterministic commands for writes.

## Workflow

1. Use the v3 CLI or a compatibility script.
2. Draft durable content with context, scope, out of scope, observable done criteria, verification strategy, dependencies, and first next step.
3. Set obvious dependencies through deterministic dependency commands when ordering is clear.
4. Create the item and fetch/read it back to verify metadata and body.
5. Do not hand-edit hub frontmatter, dependency links, status, claim state, or layout. If no deterministic command exists for the needed mutation, report the missing backend surface.

For central hub creation, use:

```bash
python3 <repo>/skills/manage-agent-hub-issues/scripts/agent_hub.py issue create \
  --title '<title>' \
  --id '<issue-id>' \
  --type Feature \
  --priority P2
```

When the unified v3 CLI is unavailable, use the compatibility script only for the creation behavior it supports:

```bash
python3 <skill-dir>/scripts/create_file_issue.py '<title>' --id '<issue-id>' --type Feature --priority P2
```

## Defaults

- `Status`: `Not Started`
- `Owner`: `Unassigned`
- `Priority`: `P2` unless urgency is clear
- `Type`: choose from the schema; use `Decision`, `Open Question`, or `Handoff` when appropriate
- `Blockers`: empty unless the blocker is external to the hub
- `Depends On`: prerequisite hub issues, not generic blockers
- `Dependency Notes`: rationale for any dependency, parallel work allowed, or explicit override

## Durable Body Template

```md
## Context

## Scope

## Out Of Scope

## Done Criteria

- [ ]

## Verification Strategy

### Regression Target

### Test Plan

- [ ] Unit:
- [ ] Integration:
- [ ] E2E / Playwright:
- [ ] Manual / inspection:

### First Test

Path:
Expected initial result:
Reason this proves the regression or requirement:

### Final Verification

Commands:
Expected result:

### Untestable Surface

## Dependencies

## Evidence / Links

## Activity Log

### Created
Date:
Agent:
Reason:
Next step:
```

For follow-ups created during review, link the source issue and set `Depends On` or `Blocks` so downstream tracking reflects the sequencing.
