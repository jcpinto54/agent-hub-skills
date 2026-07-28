---
name: orchestrate-codex-ticket-queue
description: Set up or continue a Codex Desktop heartbeat that runs a dependency-aware GitHub issue implementation queue with bounded parallelism, review-remediation, commits, pushes, and human-decision stops.
---

# Orchestrate Codex Ticket Queue

Use this skill when the user asks to set up, operate, continue, or monitor a
Codex Desktop automation that implements GitHub issues in dependency order.
This is a GitHub-and-Codex workflow, not an Agent Hub change-packet workflow.

Use `run-agent-hub-loop` instead when the target repository has an Agent Hub
packet and the user wants its file-backed packet operator.

## Required Inputs

Discover these from the user, the repository, and existing Codex tasks. Ask
only for a missing value that would materially change execution; otherwise state
the safe inference in the activation summary.

- target Codex project and repository;
- GitHub issue dependency graph, including the initial ready issue or issues;
- issue completion definition and any protected approval gates;
- implementation model and reasoning effort when the user specifies them;
- maximum simultaneous implementation tasks (default: 2);
- whether review-remediation is enabled (default: enabled);
- whether each task must commit and push (default: yes);
- any explicitly authorized external actions.

When the graph is unclear, read the issue bodies, labels, comments, native
GitHub issue dependencies, and existing task handoffs. Do not infer a
dependency merely because issue numbers are adjacent.

## Discovery Before Activation

Perform these read-only checks first:

1. Read the target repository's `AGENTS.md` and the relevant issue-tracker
   guidance.
2. Inspect the GitHub issues, their labels, comments, dependency state, and
   current branches/commits.
3. List existing Codex tasks and automations. Reuse a task or automation that
   already corresponds to the same issue and role; never create duplicates.
4. Check whether an implementation task, review-remediation task, or its
   dependency is active, completed, blocked, or awaiting user input.
5. Identify a safe local or preview environment that a reviewer can use for
   running-app verification. Never require production credentials or real data.

Present the intended graph, concurrency, completion rule, review setting, and
external-action boundaries before creating or materially changing the
automation. Start or update it only after the user has explicitly asked to
activate or continue the queue.

## Queue Contract

Create or update exactly one Codex heartbeat automation for the queue. Its
heartbeat must:

1. Inspect active and recently completed implementation and review-remediation
   tasks.
2. Treat an implementation as complete only after it reports completion,
   focused checks pass, and its branch was committed and pushed when those are
   required.
3. When review-remediation is enabled, start exactly one independent,
   fresh review-remediation task after each implementation. It must begin from
   the implementation branch/commit and be distinct from its implementer.
4. Treat the issue as complete only after the review-remediation task reports
   no unresolved engineering blocker. Successors must begin from the latest
   remediation commit, not the pre-review implementation commit.
5. Start only dependency-ready successor issues. Respect the implementation
   concurrency cap, preferring explicitly named parallel branches in the graph.
6. Never silently create duplicate implementation or review-remediation tasks.
7. Stop and report the exact blocker when a task fails, is incomplete, requires
   unavailable access, or awaits user input. An ordinary test failure is work to
   diagnose and remediate, not completion.

When all engineering issues are complete, delete the obsolete heartbeat
automation and report that the queue has finished. Do not leave a stale
automation polling completed work.

## Implementation Handoff

Launch each implementation in a fresh project worktree from the latest approved
dependency branch. Include the GitHub issue number, branch/commit base, and
these requirements:

- read repository instructions and the complete GitHub issue;
- use failing-first TDD for behavior changes and record why TDD is unsuitable
  for a non-behavioral change;
- keep changes issue-scoped and run focused checks;
- use configured implementation review subagents when the repository requires
  them;
- commit the completed work and push its branch to `origin` before reporting
  completion;
- report branch, commit, focused checks, and exact blockers;
- do not merge, deploy, open a pull request, or approve protected gates unless
  separately authorized.

## Review-Remediation Handoff

When enabled, launch the reviewer in an isolated worktree from the
implementation branch. The reviewer must independently inspect the GitHub issue
and implementation; it is not a reporting-only task.

Require it to:

- review scope, done criteria, TDD evidence, tests, configuration, and the
  implementation diff independently;
- fix every safely actionable finding directly supported by the issue using
  failing-first TDD;
- run focused checks and verify the running application in a safe local or
  preview environment when one is available;
- record why running-app verification was unavailable when it cannot be run;
- commit and push any remediation branch to `origin` before approval;
- report branch, commit, browser/application evidence, checks, and unresolved
  blockers.

The reviewer may change code, tests, configuration, or documentation when the
correction is directly supported by the issue and needs no new product decision.
It must not widen scope, deploy, merge, open a PR, or approve protected gates.

## Human-Decision Stop

If implementation or review finds a high-impact, non-obvious product or
architecture decision, do not guess. On the GitHub issue, record:

```text
decisionOwner: user
requiredEvidence: <decision or evidence needed>
resumptionCondition: <exact condition that unblocks the queue>
```

Add `needs-info` and `ready-for-human` labels when they exist or can safely be
created under the repository's label policy. Report the same decision in the
coordination task, pause dependent work, and leave the heartbeat active only if
it can wait for that decision without creating new tasks. Otherwise stop and
delete the automation as stale.

## Safety Boundaries

- Use only synthetic loopback or explicitly authorized non-production data.
- Never deploy, merge, push to a protected branch, open a pull request, or
  mutate production systems unless the user separately authorizes that action.
- Never self-approve clinical, provider-authentication, deployment, or
  production-smoke gates; require genuine responsible human or system evidence.
- Do not create or change GitHub issues, labels, comments, or assignments except
  for the explicitly authorized queue coordination and human-decision stop.
- Do not expose tokens, credentials, private production data, or real accounts
  in task prompts or evidence.

## Reporting

Each heartbeat update should be brief and evidence-based. Report only material
state changes: launched tasks, completed/remediated issues, commits and pushes,
new blockers, the next dependency-ready issues, or final completion. Do not
spam unchanged polling results.

On queue completion or a real external block, provide:

- completed issues and their latest remediation commits;
- active or blocked issue and exact reason;
- any required human decision in the structured form above;
- the next action and whether the heartbeat was deleted or remains active.
