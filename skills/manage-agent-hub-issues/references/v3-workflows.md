# Agent Hub v3 Workflows

Use these workflows after loading `v3-router-policy.md` when the user asks for a
specific Agent Hub action.

## Init

1. Identify the target repo and project name.
2. Prefer `agent-hub --repo <repo> init --project-name <name>`.
3. Verify the reported central hub layout exists: `config.yml`, `state.yml`,
   `project/`, `changes/`, `issues/`, `decisions/`, `reports/`, `artifacts/`,
   and `.gitignore`.
4. Run `agent-hub state refresh` when available.
5. If the v3 CLI is unavailable, use the current init compatibility script only
   for the layout it supports and report any missing v3 paths as assumptions.
6. Keep repo work in the central hub; external notes and legacy `.hub/` files are context only.

## Create Or Link Work

Use deterministic commands for every structure or frontmatter mutation:

```bash
agent-hub change create
agent-hub issue create
agent-hub change link-issue
agent-hub change archive
agent-hub issue add-dependency
agent-hub issue remove-dependency
```

For implementation issues, ensure the body has:

- context
- scope
- out of scope
- observable done criteria
- verification strategy
- regression target or explicit automated-test exception
- first test path, expected initial failure, and final verification commands
- dependencies and open questions

If the request is vague, run `spec-agent-hub-issue` before creating claimable
work. If the work has multiple independent done states, split it into child
issues and link dependencies.

## Claim

Use:

```bash
agent-hub claim acquire
agent-hub claim check
agent-hub claim renew
agent-hub claim release
```

Claim only ready work. Refuse or send back issues with unresolved dependencies,
external blockers, unclear verification strategy, active claims, or missing
regression plan.

For repo-changing work, the successful claim must be followed by branch/worktree
setup before files are edited. Record base branch, branch, and worktree path
through the deterministic command surface.

## Work And Update

Delegate substantive implementation, research, QA, audit, or docs drafting to a
bounded subagent. The handoff must include required files, permitted edits,
validation, evidence, and stop conditions.

For implementation:

1. Create or identify the failing regression test/eval first.
2. Run it and capture the initial failing result.
3. Implement the smallest scoped fix.
4. Run focused verification, then broader checks appropriate to risk.
5. Append activity and evidence with deterministic commands:

```bash
agent-hub issue append-activity
agent-hub issue add-evidence
```

Do not rewrite the full issue file to record progress. Append through the command
surface or a compatibility append script.

## Submit For Review

Before `In Progress -> In Review`, require:

- completed done criteria
- final verification result
- commit SHA
- pushed branch
- PR URL
- preview URL when CI produced a PR preview, or a note that no preview was
  available
- regression evidence or explicit exception
- risks and skipped checks

Use:

```bash
agent-hub issue set-status
agent-hub claim release
```

Prefer release mode semantics that atomically clear the work claim and preserve
review evidence.

For user-facing web changes, when a CI-created preview URL is available for a
PR, spawn a preview-verification subagent using `$verify-agent-hub-pr-preview`
before independent review. The preview-verification agent should check the
deployed preview website against the issue done criteria, record durable
evidence, and report a blocker when the preview is inaccessible, stale, or fails
a criterion. If no preview URL is available, record a no-preview rationale.

## Review

Claim review first. Review the durable issue/change record, PR, commit, linked
artifacts, and command output rather than chat memory.

Pass only when evidence covers:

- done criteria
- scope and out-of-scope boundaries
- dependency state
- regression/TDD requirement or exception
- final verification
- preview-verification evidence or a recorded no-preview rationale for
  user-facing web changes
- repo metadata for repo-changing work

Fail or send back when evidence is missing, criteria are unmet, dependencies are
unresolved, preview evidence is missing when a preview exists, or skipped checks
are not justified. Use deterministic commands to append review findings, set
status, and release the review claim.

## Merged PR Sync

If an implementation PR is merged outside the Agent Hub review flow while its
issue remains `In Review`, sync GitHub merge state before dependency analysis:

```bash
agent-hub state sync-merged-prs --change <change-slug>
```

The command inspects `In Review` issues with GitHub `PR URL` metadata. It uses
`gh pr view` first and falls back to `GITHUB_TOKEN` or `GH_TOKEN` for the GitHub
REST API. Only confirmed merged PRs move to `Completed`; open, closed-unmerged,
inaccessible, malformed, or missing PR URLs are left unchanged and reported as
diagnostics.

## Audit And Analyze

Use audit for workspace and issue health:

```bash
agent-hub audit hub
agent-hub audit issue <issue-id>
```

Audit should flag missing required files, malformed frontmatter, stale claims,
dangling dependencies, vague issues, blocked work, missing evidence, review-ready
work without PR/commit/test data, missing TDD strategy, and malformed runtime
claims. Reports go to `reports/latest-audit.json` and
`reports/latest-audit.md` in the central hub.

Use analyze for change packets:

```bash
agent-hub analyze change <change-slug>
```

Analyze should check proposal/design/tasks alignment, task-to-issue coverage,
issue-to-change links, independent claimability, checklist completion, evidence
coverage, and review risks. Reports go to `reports/latest-analysis.json`
and `reports/latest-analysis.md` in the central hub.

Diagnostics should have stable codes, severities, targets, messages, and
recommendations so tests and evals can match them.

## Iterate And Delegate

Use `iterate-agent-hub-work` for one subagent-first iteration.

1. List ready work through the deterministic listing/readiness command.
2. Cap the batch, normally at 10 or fewer issues.
3. Spawn one bounded subagent per issue.
4. Each subagent claims its own issue. The parent does not claim on their behalf.
5. Do not reinterpret readiness after the command returns rows; send unclear work
   back to spec/audit instead.
6. Return spawned agent IDs, issue IDs, and expected evidence. Do not wait unless
   the user explicitly asked for a synchronous iteration.

Use `run-agent-hub-loop` when the user asks to keep operating on one change
packet until blocked, complete, or budget exhausted. The loop skill repeatedly
analyzes the packet, lists ready implementation work, spawns implementation
subagents, waits for the wave, spawns `$verify-agent-hub-pr-preview` subagents
for PR-backed issues when CI-created previews are available, records no-preview
rationales when previews are not available, lists ready review work, spawns
independent review subagents, waits for review, refreshes state, and stops on
budget or blocking diagnostics.
