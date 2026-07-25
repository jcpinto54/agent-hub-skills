# Agent Hub Usage Guide

This guide maps common Agent Hub plugin intents to the Codex skill you should
invoke. When in doubt, ask for `manage-agent-hub-issues`: it is the primary
resolver and will route to the right specialized workflow.

Use the leaf skills directly when your intent is already clear. They are useful
shortcuts for repeatable operations such as listing ready work, running the
viewer, claiming one issue, or operating a packet loop.

## Quick Decision Table

| I want to... | Use this skill | Typical prompt |
|---|---|---|
| Let the agent choose the right Agent Hub workflow | `manage-agent-hub-issues` | "Use Agent Hub to coordinate this request." |
| Run the packet loop until blocked, complete, or budget exhausted | `run-agent-hub-loop` | "Run the Agent Hub loop for change `checkout-retry`." |
| Check the current hub state or ready work | `list-agent-hub-issues` | "List ready Agent Hub issues for this repo." |
| Audit hub health, stale claims, vague issues, or review risks | `review-agent-hub-workspace` | "Audit the Agent Hub and tell me what needs attention." |
| Open the local read-only hub UI | `run-agent-hub-app` | "Run the Agent Hub app for this repo." |
| Work on one issue I choose | `claim-agent-hub-issue`, then `update-agent-hub-issue` | "Work on Agent Hub issue `hub-123`." |
| Turn a rough idea into claimable work | `spec-agent-hub-issue`, then `create-agent-hub-issue` | "Spec this idea into Agent Hub issues." |
| Split oversized or overlapping work | `dry-mece`, then `spec-agent-hub-issue` | "Decompose this into clean Agent Hub issues." |
| Create a new issue, decision, follow-up, or handoff | `create-agent-hub-issue` | "Create an Agent Hub issue for..." |
| Browser-check a PR preview before review | `verify-agent-hub-pr-preview` | "Verify the PR preview for Agent Hub issue `hub-123`." |
| Review an `In Review` issue | `review-agent-hub-issue` | "Review Agent Hub issue `hub-123`." |
| Record progress, blockers, evidence, or a handoff | `update-agent-hub-issue` | "Update `hub-123` with this progress..." |
| Initialize Agent Hub in a repo | `init-agent-hub` | "Initialize Agent Hub in this repository." |
| Sync installed local skills back to this repo | `sync-agent-hub-skills` | "Sync the Agent Hub skills into the backing repo." |

## Use Cases

### Run The Loop

Use `run-agent-hub-loop` when you want Codex to keep operating on one change
packet through implementation and independent review waves.

Best for:

- a change packet with several ready issues
- multi-agent implementation work
- automatic preview website verification when PR CI creates preview deployments
- automatic review waves after implementation waves
- a bounded "keep going until blocked or budget is used" run

Example prompts:

```text
Use $run-agent-hub-loop for change `hub-viewer-live-updates`.
```

```text
Run the Agent Hub loop for `readonly-issue-viewer` with at most 3 waves and 4
agents per wave.
```

What it does:

1. Analyzes the change packet.
2. Lists ready implementation issues.
3. Spawns implementation subagents.
4. Audits and analyzes again.
5. Spawns `$verify-agent-hub-pr-preview` subagents for PRs with CI-created preview URLs, or records no-preview rationales.
6. Lists ready review issues.
7. Spawns independent review subagents.
8. Refreshes hub state and repeats until a stop condition is reached.

Use `iterate-agent-hub-work` instead when you only want one wave of delegated
work and do not want the parent agent to wait for completion.

### Check The State Of The Hub

Use `list-agent-hub-issues` for read-only state checks and ready-work views.

Best for:

- "What can be worked on next?"
- "What is in review?"
- "What is blocked?"
- "Show me issues for this change packet."
- JSON or Markdown exports of current hub state

Example prompts:

```text
Use $list-agent-hub-issues to show ready work in this repo.
```

```text
List Agent Hub issues for change `checkout-retry`, grouped by readiness.
```

For deeper diagnosis, use `review-agent-hub-workspace`. Listing answers what
the hub says right now; auditing answers what might be unhealthy or missing.

### Run The App To View State

Use `run-agent-hub-app` when you want the local read-only dashboard.

Best for:

- opening the Kanban-style viewer
- refreshing `hub-state.json`
- inspecting a whole repo hub visually
- focusing the dashboard on one change packet

Example prompts:

```text
Use $run-agent-hub-app for this repo.
```

```text
Run the Agent Hub app for change `hub-viewer-live-updates`.
```

The app is read-only. It exports a fresh dashboard snapshot, starts or reuses a
local server, and returns the URL. Use other skills for claiming, updating,
reviewing, or changing issue state.

### Work On A Single Issue Of My Choice

Use `claim-agent-hub-issue` first, then the normal implementation or review
workflow. For most user prompts, `manage-agent-hub-issues` can coordinate this
for you.

Best for:

- "Work on issue `hub-123`."
- "Pick up this exact bug."
- "Review this exact `In Review` issue."
- "Continue the issue in its recorded worktree."

Example prompts:

```text
Use Agent Hub to work on issue `hub-123` end to end.
```

```text
Use $claim-agent-hub-issue for `hub-123`, then implement it with TDD and update
the issue evidence.
```

Expected flow:

1. Read the issue and check readiness.
2. Claim work or review ownership.
3. Create or verify the isolated branch/worktree.
4. For implementation, write or identify the first failing test before coding.
5. Make the smallest scoped change.
6. Run focused verification.
7. Use `update-agent-hub-issue` to record progress, evidence, branch, commit,
   PR, blockers, or handoff notes.
8. Submit for review or release the claim using the correct claim mode.

If the issue is vague, missing done criteria, or missing verification strategy,
use `spec-agent-hub-issue` before trying to claim it.

### Create Or Refine Work

Use `spec-agent-hub-issue` when the idea is rough, broad, or ambiguous. Use
`create-agent-hub-issue` when the work is already clear enough to become a
durable issue, decision, open question, follow-up, or handoff.
Use `dry-mece` before creating child issues when the work is oversized,
overlapping, or likely to produce multiple independent done states.

Example prompts:

```text
Use $spec-agent-hub-issue to turn this idea into agent-ready issues: ...
```

```text
Create Agent Hub issues for this plan and link the dependencies.
```

Good specs include scope, out of scope, binary done criteria, verification
steps, dependencies, and a first next action. Implementation issues should also
name the regression target or explain why automated testing is not practical.

### Review Completed Work

Use `review-agent-hub-issue` for an issue that is already `In Review`.

Example prompts:

```text
Use $review-agent-hub-issue to review `hub-123`.
```

The reviewer should claim review ownership, inspect the issue record, PR,
commit, evidence, and verification output, then pass or send back the issue.
Completion is a review decision, not a manual status edit.

### Audit And Clean Up The Hub

Use `review-agent-hub-workspace` when you want a health report instead of a
work wave.

Example prompts:

```text
Audit this Agent Hub for stale claims, vague issues, and review risks.
```

```text
Check whether any blocked issues should really be dependencies.
```

The audit should report findings and recommended fixes. Ask for a follow-up
mutation explicitly if you want it to rewrite dependencies, release stale
claims, or create cleanup issues.

### Initialize A Hub

Use `init-agent-hub` for new central Agent Hub setup.

Example prompts:

```text
Initialize Agent Hub in this repo.
```

The central hub under `~/.agents-hub/` or `AGENT_HUB_HOME` is the source of
truth for repository work. Linked worktrees of the same clone share that state.
Legacy repo-local `.hub/` directories are migration input and context only.

### Sync The Plugin Skills

Use `sync-agent-hub-skills` when installed local Agent Hub skills need to be
copied back to this repository, validated, committed, and pushed.

Example prompt:

```text
Sync my installed Agent Hub skills back to the backing repo without pushing.
```

Do not use this for normal hub work. It is maintenance for the skill/plugin
repository itself.

## Recommended Prompt Patterns

For broad coordination:

```text
Use $manage-agent-hub-issues to coordinate this in Agent Hub. Prefer the
central hub selected by `--repo`, deterministic writes, subagents for
substantive work, and TDD for code changes.
```

For packet execution:

```text
Use $run-agent-hub-loop for change `<change-slug>`. Stop on blockers, failed
claims, audit/analyze errors, or budget exhaustion, and report spawned agents and
remaining work.
```

For one issue:

```text
Use Agent Hub to work issue `<issue-id>` end to end. Claim first, use an isolated
worktree, create the failing test before implementation, record evidence, and
submit for review when ready.
```

For state only:

```text
Use $list-agent-hub-issues only. Do not claim or mutate anything.
```

For the dashboard:

```text
Use $run-agent-hub-app for `<repo>` and return the local URL.
```

## Choosing Between Similar Skills

- `manage-agent-hub-issues` is the resolver. Use it when the next action is not
  obvious or the request spans several workflow steps.
- `list-agent-hub-issues` is read-only state. It does not fix or mutate issues.
- `review-agent-hub-workspace` is diagnostic audit. It recommends repairs but
  should not rewrite state unless you explicitly ask.
- `iterate-agent-hub-work` starts one delegated wave and returns agent IDs.
- `run-agent-hub-loop` keeps operating a change packet across implementation and
  review waves until a stop condition.
- `claim-agent-hub-issue` owns leases. It does not create branches or do the
  implementation by itself.
- `update-agent-hub-issue` records progress, blockers, handoffs, evidence, and
  submissions after work has started.
- `review-agent-hub-issue` is the completion gate for `In Review` work.
