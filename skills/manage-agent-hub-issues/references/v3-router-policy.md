# Agent Hub v3 Router Policy

## Source Of Truth

- Use the central Agent Hub store under `~/.agents-hub/` or `AGENT_HUB_HOME` as the only durable source of truth for repo work.
- Use the central hub before trusting external notes, mirrors, or legacy repo-local `.hub/` directories.
- Keep `runtime/` in the central hub local. Runtime claims are live state, not durable project history.

## Deterministic Write Policy

Agents do not own hub structure. Deterministic commands own:

- layout initialization
- frontmatter parsing and writing
- issue/change linking
- dependency add/remove
- status transitions
- claim acquire/check/renew/release
- activity and evidence appends
- state refresh
- audit/analyze report generation
- archive moves

Agents may draft Markdown content for proposals, specs, design notes, done criteria,
verification strategy, evidence summaries, and review findings. Pass that content
to the deterministic command or compatibility script that owns the write.

Prefer the v3 command surface:

```bash
agent-hub init
agent-hub state refresh
agent-hub change create
agent-hub change link-issue
agent-hub change archive
agent-hub issue create
agent-hub issue add-dependency
agent-hub issue remove-dependency
agent-hub issue set-status
agent-hub issue append-activity
agent-hub issue add-evidence
agent-hub claim acquire
agent-hub claim check
agent-hub claim renew
agent-hub claim release
agent-hub audit hub
agent-hub audit issue <issue-id>
agent-hub analyze change <change-slug>
```

During development, the same behavior may be exposed as
`python3 skills/manage-agent-hub-issues/scripts/agent_hub.py ...`. Existing leaf
scripts are compatibility wrappers only. If neither v3 CLI nor a wrapper exists,
stop and report the missing mutation command instead of hand-editing frontmatter,
claims, dependencies, status, reports, or structure.

## Subagent-First Rule

The parent agent is an orchestrator. Delegate substantive work to bounded
subagents, including implementation, research, review, audit, analysis,
documentation drafting, QA, and skill critique.

Every handoff should include:

- objective
- scope
- out of scope
- required files to read
- permitted files to edit
- deterministic commands to use
- validation commands
- evidence requirements
- expected output
- stop conditions

Implementation handoffs must also name the first failing test, fixture eval, or
scenario eval to satisfy, or state that the subagent must create one before
implementation.

## TDD And Regression Gate

Implementation work must define verification before coding.

- Bug fixes and behavior changes need a regression test or eval first.
- The activity log should record the initial failing result, or an explicit
  automated-test exception with rationale.
- UI/user-facing workflows should include browser automation smoke checks when
  feasible.
- For PR-backed web work, if CI creates a preview deployment, the orchestrator
  should delegate `$verify-agent-hub-pr-preview` to a separate subagent before
  normal review. If no preview URL is available, record a no-preview rationale.
- Review fails when regression evidence, done-criteria coverage, final
  verification, or repo evidence is missing.

## Readiness And Review Invariants

Do not claim implementation work unless:

- status is `Not Started`
- owner is empty or `Unassigned`
- blockers are empty
- dependencies are completed or explicitly waived by durable notes
- no unexpired claim exists
- scope, out of scope, done criteria, and verification strategy are clear

Do not submit repo work to review unless:

- work happened in an isolated branch/worktree
- commit and push exist
- normal PR exists
- `Commit SHA` and `PR URL` are recorded
- tests/evals/checks or skipped-check rationale are recorded
- preview verification evidence is recorded when a CI-created PR preview exists
  for user-facing web work, or a no-preview rationale is recorded when no
  preview URL can be found

Completion is a review decision. Use a deterministic release/status command or
the review skill; do not manually clear claims or set `Completed`.
