---
name: manage-agent-hub-issues
description: Primary resolver and shared policy for Agent Hub v3 central-state orchestration, deterministic writes, subagent-first execution, and TDD/regression-first implementation. Use when a user asks to initialize, create, plan, spec, classify, list, claim, update, release, submit, review, audit, analyze, iterate, delegate, or coordinate Agent Hub issues, or when the right specialized Agent Hub skill is unclear.
---

# Manage Agent Hub Issues

Use this skill as the primary resolver. For repo work, the central Agent Hub store under `~/.agents-hub/` (or `AGENT_HUB_HOME`) is the only durable source of truth. Treat external notes and legacy repo-local `.hub/` files as stale unless the central hub record agrees.

## Hard Rules

- Deterministic commands own hub mutations. Do not hand-edit frontmatter, layout, claim state, dependency links, status, reports, or archives.
- Agents may draft bounded Markdown content, then pass it to the deterministic command or compatibility script that owns the write.
- Prefer `agent-hub` or `skills/manage-agent-hub-issues/scripts/agent_hub.py` when available. Use older leaf scripts only as compatibility wrappers for supported operations.
- If no deterministic command exists for the requested `.hub` mutation, stop and report the missing backend surface.
- Substantive work belongs in bounded subagents. The parent agent routes, hands off, runs deterministic commands, collects evidence, and reports.
- Implementation work is TDD/regression-first: identify the first failing test, fixture eval, or scenario eval before coding, or record an explicit automated-test exception.
- Review cannot pass without durable evidence for done criteria, regression coverage or exception, verification results, and PR/commit data for repo-changing work.

## Load References

Load only the relevant one-level reference:

- `references/v3-router-policy.md`: command policy, source-of-truth rules, TDD gates, subagent handoff contract, and readiness/review invariants.
- `references/v3-workflows.md`: compact workflows for init, create, claim, work/update, review, audit/analyze, and iterate/delegate.

## Route

Use the specialized skill or reference that matches the action:

- Initialize a central hub for a repo clone: `init-agent-hub`.
- Create issue, decision, open question, follow-up, handoff, change, or dependency link: `create-agent-hub-issue` plus `references/v3-workflows.md`.
- Tighten vague or oversized work: `spec-agent-hub-issue`.
- List or inspect ready work: `list-agent-hub-issues`; for health checks, audit commands.
- Claim, check, renew, or release ownership: `claim-agent-hub-issue`.
- Record progress, blockers, handoff, evidence, or review submission: `update-agent-hub-issue`.
- Browser-check a PR preview and record preview evidence: `verify-agent-hub-pr-preview`.
- Review `In Review` work: `review-agent-hub-issue`.
- Audit/analyze workspace health or change consistency: `review-agent-hub-workspace` plus `references/v3-workflows.md`.
- Start one subagent-first iteration: `iterate-agent-hub-work`.
- Run a budget-capped change-packet loop until blocked, complete, or budget
  exhausted: `run-agent-hub-loop`.
