---
name: verify-agent-hub-pr-preview
description: Verify deployed PR preview websites for central Agent Hub issues after implementation submits a PR and before independent review. Use when Codex needs to discover or open a CI-created preview URL, browser-check user-facing web changes against done criteria, record preview evidence, or document a no-preview rationale.
---

# Verify Agent Hub PR Preview

Use this skill for PR-backed, user-facing web work that may have a deployed
preview. The goal is browser QA evidence for the review record, not a review
decision.

## Required Inputs

- Change packet slug.
- Issue ID or issue path.
- PR URL when known.
- Preview URL when known.
- Done criteria, verification strategy, and prior implementation evidence from
  the durable issue record.

## Workflow

1. Read the issue, change packet, PR summary, done criteria, prior checks, and
   recorded evidence. Do not rely on chat memory.
2. If `Preview URL` is missing, inspect durable issue evidence, related links,
   PR checks, deployments, comments, or deployment metadata for a CI-created
   preview URL.
3. If no preview URL is available, record a durable no-preview rationale with
   `$update-agent-hub-issue`, then report that normal review may continue using
   the recorded rationale.
4. Open the preview URL with a browser-capable tool. If the preview is
   inaccessible, stale, unauthenticated, or clearly not the PR under review,
   record the blocker and evidence with `$update-agent-hub-issue`.
5. Exercise the changed user-facing workflow against the issue done criteria.
   Check relevant responsive states, console errors, and obvious network failures.
   Capture screenshots when they clarify the evidence.
6. Record durable evidence with `$update-agent-hub-issue`: preview URL, browser
   steps, observations, screenshots or artifact paths when useful, failures,
   skipped checks, and rationale.
7. Report the preview outcome to the orchestrator as `verified`, `failed`,
   `blocked`, or `no-preview-rationale-recorded`.

## Boundaries

- Do not implement code.
- Do not mark review pass/fail.
- Do not complete, send back, or release review claims.
- Do not treat preview verification as a replacement for normal
  `$review-agent-hub-issue` review.
