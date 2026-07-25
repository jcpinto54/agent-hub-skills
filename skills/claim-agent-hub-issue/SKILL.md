---
name: claim-agent-hub-issue
description: Claim, check, renew, or release Agent Hub ownership leases for implementation work or review work in central Agent Hub issues. Use when a user asks to claim ready work, claim review, renew a claim, release abandoned or submitted work, or clear passed/failed review ownership in an Agent Hub.
---

# Claim Agent Hub Issue

Use the bundled script for ownership leases. It operates on the central Agent Hub selected by the current repo/worktree.

The script writes durable issue frontmatter/activity entries and uses the central hub's `runtime/claims.json` as the active-lock source.

Important: the script does not create git branches or worktrees. After a successful claim, the agent must create or verify the required worktree before touching repo files.

Before claiming, ensure the repo has been initialized or migrated into the central store. Use `--hub-root` only for one-off legacy or test overrides.

## Claim Work

Run:

```bash
python3 <skill-dir>/scripts/agent_hub_claim.py claim \
  --backend file \
  --purpose work \
  --page-id '<issue-id>' \
  --owner '<agent-name>' \
  --base-branch '<base>' \
  --branch '<branch>' \
  --worktree-path '<path>'
```

The script refuses the claim unless:

- `Status = Not Started`
- `Owner` is empty, `Unassigned`, or equivalent
- `Blockers` is empty
- all `Depends On` issues are `Completed`
- no unexpired claim exists

After the script succeeds, create or reuse the worktree before touching repo files:

```bash
git fetch origin '<base>'
git worktree add -B '<branch>' '<path>' 'origin/<base>'
git -C '<path>' status --short --branch
```

If the issue branch already exists remotely, use the remote branch instead of resetting from the base:

```bash
git fetch origin '<branch>'
git worktree add '<path>' 'origin/<branch>'
git -C '<path>' status --short --branch
```

If the worktree path already exists, verify it matches the intended issue branch before using it:

```bash
git -C '<path>' branch --show-current
git -C '<path>' status --short --branch
```

Record any missing branch/worktree metadata through `update-agent-hub-issue`, especially when the hub database lacks `Base Branch`, `Branch`, or `Worktree Path` properties.

## Claim Review

Run:

```bash
python3 <skill-dir>/scripts/agent_hub_claim.py claim \
  --backend file \
  --purpose review \
  --page-id '<issue-id>' \
  --owner '<reviewer-name>'
```

The script refuses review unless:

- `Status = In Review`
- no unexpired claim exists
- dependencies are completed or explicitly waived in `Dependency Notes`
- the issue has durable artifact evidence in `PR URL`, `Commit SHA`, or `Related Links`

Use `--allow-missing-artifacts` only when the issue type is intentionally non-repo/non-artifact and the page body itself is sufficient.

After a successful review claim for repo-backed work, create a clean sibling review worktree from the PR head branch before reviewing. Fetch the PR evidence from `PR URL`, `Commit SHA`, `Related Links`, or the page body, then run:

```bash
git fetch origin '<pr-head-branch>'
git worktree add '<review-worktree-path>' 'origin/<pr-head-branch>'
git -C '<review-worktree-path>' status --short --branch
```

Review from that worktree, not from the caller's current dirty workspace. If the review worktree already exists, verify its current branch and status before using it.

## Check Or Renew

```bash
python3 <skill-dir>/scripts/agent_hub_claim.py check --page-id '<issue>' --claim-id '<claim-id>'
python3 <skill-dir>/scripts/agent_hub_claim.py renew --page-id '<issue>' --claim-id '<claim-id>' --ttl-minutes 120
```

## Release Modes

```bash
python3 <skill-dir>/scripts/agent_hub_claim.py release --page-id '<issue>' --claim-id '<claim-id>' --mode submitted --pr-url '<url>' --commit-sha '<sha>'
python3 <skill-dir>/scripts/agent_hub_claim.py release --page-id '<issue>' --claim-id '<claim-id>' --mode review-pass
python3 <skill-dir>/scripts/agent_hub_claim.py release --page-id '<issue>' --claim-id '<claim-id>' --mode review-fail
```

Supported modes:

- `abandon`: release work claim; return to `Not Started` only when no repo metadata exists.
- `handoff`: release work claim; keep `In Progress`; owner defaults to `Unassigned`.
- `blocked`: release work claim and optionally write `Blockers`.
- `submitted`: release work claim after PR exists; set `In Review`.
- `review-pass`: release review claim after moving to `Completed`.
- `review-fail`: release review claim after moving back to `In Progress`.
- `review-abandon`: release review claim and leave `In Review`.

## Optimistic Locking

Every claim writes a unique `Claim ID`, immediately refetches the page, and succeeds only if the claim ID still matches. If verification fails, stop and inspect the issue manually.
