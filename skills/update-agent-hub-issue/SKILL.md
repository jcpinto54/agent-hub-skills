---
name: update-agent-hub-issue
description: Update Agent Hub issue progress, blockers, handoffs, repo metadata, work claim releases, and In Progress to In Review submissions in central Agent Hub issues. Use when a user asks to report progress, pause, block, hand off, release, submit for review, attach a PR, or move an Agent Hub issue after work has started.
---

# Update Agent Hub Issue

For central hubs, append durable entries to `issues/<issue-id>.md`. Use `claim-agent-hub-issue`'s script for claim checks, renewals, and releases.

## Required Claim Check

Before writing progress on an `In Progress` issue, verify the current agent has the matching work claim:

```bash
python3 <claim-skill-dir>/scripts/agent_hub_claim.py check --page-id '<issue>' --claim-id '<claim-id>'
```

If the claim is missing, expired, or mismatched, do not continue without explicit user direction.

## Progress Updates

Append a durable activity-log entry. Include:

- Scope completed since the last update
- Files, systems, PRs, commands, screenshots, or logs touched
- Decisions and rationale
- Verification run and results
- Risks, skipped checks, or unknowns
- Exact next step

For central hubs, use the append script when a structured progress entry is enough:

```bash
python3 <skill-dir>/scripts/append_file_activity.py \
  --issue '<issue-id>' \
  --heading Progress \
  --agent '<agent-name>' \
  --summary '<what changed>' \
  --evidence '<files, commands, PRs, logs, or links>' \
  --verification '<checks and results>' \
  --risks '<risks or skipped checks>' \
  --next-step '<next action>'
```

## Blocked Or Handoff

For external blockers, update `Blockers` and append:

```md
### Blocked
Date:
Agent:
Blocker:
Evidence:
Attempted:
Needed to unblock:
Recommended next step:
```

Then release or renew the work claim based on the user's instruction. Use release mode `blocked` to release the lease while preserving `In Progress`.

For handoff, preserve branch/worktree/PR metadata, append the handoff record, and release with mode `handoff`.

## Submit To Review

Before `In Progress -> In Review`, repo-tracked changes must have:

- Isolated branch/worktree
- Commit
- Push
- Normal PR, not only local diff
- `Commit SHA`
- `PR URL`
- Relevant checks or explicit skipped-check rationale

Append:

```md
### Status change: In Progress -> In Review
Date:
Agent:
Implemented:
Touched:
Checks run:
Artifacts:
Findings:
Risks / skipped checks:
Reviewer should verify:
```

Then release with:

```bash
python3 <claim-skill-dir>/scripts/agent_hub_claim.py release \
  --page-id '<issue>' \
  --claim-id '<claim-id>' \
  --mode submitted \
  --pr-url '<pr-url>' \
  --commit-sha '<commit-sha>'
```

After release, fetch the issue and verify `Status = In Review`, claim fields are empty, and PR evidence remains.
