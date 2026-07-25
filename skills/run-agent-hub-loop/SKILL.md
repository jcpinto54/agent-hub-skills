---
name: run-agent-hub-loop
description: Run a budget-capped Agent Hub packet operator loop. Use when a user asks to run, operate, continue, or iterate agents on a central Agent Hub change packet until blocked, complete, or budget exhausted, with implementation and independent review handled by subagents.
---

# Run Agent Hub Loop

Use this skill for packet-scoped Agent Hub execution loops. This is the
higher-level operator; `iterate-agent-hub-work` remains the one-wave primitive.

## Defaults

- Scope: one change packet.
- Max waves: 5.
- Max agents per wave: 5.
- Max elapsed time: 120 minutes.
- Review: enabled.

If the user does not provide a change slug, infer it only when exactly one
active non-archived change packet exists. Otherwise ask for the slug.

## Responsibilities

- Parent agent is the orchestrator only.
- Deterministic commands own central hub reads and writes.
- Implementation agents claim, code, test, commit, push, open PRs, record
  evidence, and submit to review.
- Preview-verification agents check CI-created PR preview deployments before
  normal review when previews exist.
- When a CI-created preview URL is available for a PR, spawn a preview-verification subagent using `$verify-agent-hub-pr-preview` before independent review.
- Preview-verification agents check the deployed preview website against the issue done criteria and record durable evidence.
- Normal review should treat preview evidence as durable input.
- Review agents claim review and make completion/send-back decisions.
- The parent never claims, implements, reviews its own work, or bypasses
  readiness.

Implementation agents claim, code, test, commit, push, open PRs, record evidence, and submit to review.
The parent never claims, implements, reviews its own work, or bypasses readiness.

## Commands

Use the repo-local script when `agent-hub` is not installed:

```bash
python3 skills/manage-agent-hub-issues/scripts/agent_hub.py analyze change <slug>
python3 skills/manage-agent-hub-issues/scripts/agent_hub.py audit hub
python3 skills/manage-agent-hub-issues/scripts/agent_hub.py state refresh
python3 skills/list-agent-hub-issues/scripts/agent_hub_list.py \
  --backend file \
  --change <slug> \
  --status 'Not Started' \
  --readiness Ready \
  --format json \
  --limit <max-agents>
python3 skills/list-agent-hub-issues/scripts/agent_hub_list.py \
  --backend file \
  --change <slug> \
  --status 'In Review' \
  --readiness Ready \
  --format json \
  --limit <max-agents>
```

## Loop

Repeat until a stop condition is reached:

1. Run `state refresh` so hub summaries and runtime-derived readiness are
   current. Report but do not hide diagnostics.
2. Run `analyze change <slug>`. Stop on error diagnostics.
3. List ready implementation issues for the packet.
4. Spawn one implementation subagent per row, capped by remaining budget.
5. Wait for the implementation wave to finish.
6. Run `audit hub`, `state refresh`, and `analyze change <slug>`. Stop on
   blocking errors.
7. For each PR-backed issue that has entered review, inspect recorded PR,
   deployment, CI, or related-link evidence for a preview URL. When a CI-created
   preview URL is available for a PR, spawn a preview-verification subagent
   using `$verify-agent-hub-pr-preview` before independent review. If no preview
   URL exists, use `$verify-agent-hub-pr-preview` to record a no-preview
   rationale and continue.
8. Wait for the preview-verification wave to finish.
9. List ready review issues for the packet.
10. Spawn one independent review subagent per row.
11. Wait for the review wave to finish.
12. Run `state refresh`.
13. Continue with the next wave.

Stop when there is no ready implementation, preview verification, or review
work, max waves are used, max elapsed time is reached, all spawned agents fail
or refuse claims,
`audit`/`analyze` reports blocking errors, or the user interrupts.

## Implementation Handoff

Use this prompt shape for each implementation subagent:

```text
Use the Agent Hub skills to implement this issue end to end.

Change packet: <slug>
Issue:
- ID: <id>
- Title: <title>
- URL/path: <url>
- Status: <status>
- Priority: <priority>

Rules:
- Read the issue file and change packet before working.
- Use $claim-agent-hub-issue first; do not work without a successful claim.
- Claim purpose is work.
- If the issue is too vague or missing verification, stop and report that it
  needs $spec-agent-hub-issue.
- Create or confirm the first failing test before implementation.
- Use an isolated branch/worktree for repo-changing work.
- Run focused verification and broader checks appropriate to risk.
- Use $update-agent-hub-issue to record progress, evidence, commit SHA, PR URL,
  blockers, or handoff notes.
- Commit, push, open a normal PR, submit to review, and release the claim with
  the proper mode.
- If the claim is refused, stop and report the refusal reason.
```

## Preview Verification Handoff

Use this prompt shape for each preview-verification subagent:

```text
Use $verify-agent-hub-pr-preview to verify this PR preview website.

Change packet: <slug>
Issue:
- ID: <id>
- Title: <title>
- URL/path: <url>
- Status: <status>
- Priority: <priority>
- PR URL: <pr-url>
- Preview URL: <preview-url>

Rules:
- Follow `$verify-agent-hub-pr-preview` exactly.
- Do not implement code, mark review pass/fail, complete the issue, or send the
  issue back.
- Record preview evidence or a no-preview rationale before normal review runs.
```

## Review Handoff

Use this prompt shape for each review subagent:

```text
Use the Agent Hub skills to independently review this issue.

Change packet: <slug>
Issue:
- ID: <id>
- Title: <title>
- URL/path: <url>
- Status: <status>
- Priority: <priority>

Rules:
- Use $claim-agent-hub-issue first; claim purpose is review.
- Never review your own implementation work.
- Read the issue, change packet, evidence, commit, PR, and verification output.
- Read preview-verification evidence when a PR preview was available; normal
  review should treat preview evidence as durable input.
- Verify done criteria, scope boundaries, TDD evidence, final verification, and
  repo metadata.
- Use $review-agent-hub-issue for completion or send-back decisions.
- Use deterministic commands to append findings, set status, and release claim.
- If the claim is refused, stop and report the refusal reason.
```

## Reporting

After the loop stops, report:

- change slug
- stop reason
- waves run
- implementation agents spawned
- review agents spawned
- completed issues
- still blocked or not ready issues
- failed or refused claims
- validation commands or evidence recorded

Do not hide budget exhaustion. If the packet still has ready work when the budget
ends, say so and provide the next loop command.
