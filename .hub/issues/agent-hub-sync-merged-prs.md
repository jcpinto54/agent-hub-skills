---
id: "agent-hub-sync-merged-prs"
title: "Sync merged GitHub PRs into Agent Hub issue completion"
status: "In Review"
type: "Feature"
priority: "P1"
owner: "Unassigned"
area: ""
summary: ""
blockers: ""
dependency_notes: ""
change: ""
depends_on: []
blocks: []
claim: {}
base_branch: "codex/agent-hub-v3-repo-native"
branch: "codex/agent-hub-sync-merged-prs"
worktree_path: "/Users/jcpinto/git/notion-agent-hub-skills-agent-hub-sync-merged-prs"
commit_sha: "3e8501d35b4b562b728b2a04d02703b57e04dc51"
pr_url: "https://github.com/jcpinto54/notion-agent-hub-skills/pull/4"
related_links: ""
external_url: ""
---
## Context

Agent Hub currently treats PR merge state and issue completion as separate
manual steps. An implementation agent can submit an issue to `In Review`, open a
PR, and have that PR merged, while the repo-native issue remains `In Review`.
That blocks dependent Agent Hub work until someone manually records completion.

The packet loop should be able to recover from this common state by syncing
merged GitHub PRs back into `.hub/issues/*.md` through a deterministic command.

## Scope

- Add a deterministic repo-native command, or extend `state refresh`, to inspect
  `In Review` issues with `pr_url` metadata and detect whether the referenced
  GitHub PR has been merged.
- When a PR is confirmed merged, append durable completion evidence to the
  issue activity log, set status to `Completed`, clear claim state, and record
  merge metadata such as merge commit SHA and merged timestamp when available.
- Support authentication through existing developer environments, preferably
  `gh` CLI auth first, with a documented `GITHUB_TOKEN` or equivalent fallback.
- Keep unauthenticated behavior safe: report a clear diagnostic or skipped-sync
  reason instead of failing unrelated hub refreshes.
- Ensure packet loops can call the sync before dependency analysis so completed
  upstream work unblocks downstream ready issues.

## Out Of Scope

- No automatic merging or GitHub PR mutation.
- No bypass of Agent Hub review rules for unmerged or unverifiable PRs.
- No reliance on browser automation for GitHub state.
- No alternate backend implementation; this issue targets repo-native `.hub`.

## Done Criteria

- [ ] A merged PR linked from an `In Review` issue is detected and marks the
      issue `Completed` through a deterministic command.
- [ ] Completion activity records PR URL, merge commit or merged SHA when
      available, merged timestamp when available, and the sync command used.
- [ ] Unmerged, closed-unmerged, inaccessible, malformed, or missing PR URLs do
      not mark issues complete and produce actionable diagnostics.
- [ ] Auth expectations are documented for `gh` CLI and token fallback.
- [ ] Packet dependency analysis sees the synced issue as completed after the
      command runs.

## Verification Strategy

### Regression Target

An issue submitted to review with a PR that has since been merged must not
remain stuck in `In Review` and block dependent packet work.

### Test Plan

- [ ] Unit: parse supported GitHub PR URLs and classify merged, open,
      closed-unmerged, inaccessible, and malformed states through a mockable
      provider boundary.
- [ ] Integration: run the sync command against fixture `.hub` issues and a
      mocked GitHub response provider, then assert issue status/activity and
      dependency readiness.
- [ ] E2E / Playwright: not applicable.
- [ ] Manual / inspection: with authenticated `gh`, run the command against a
      real merged PR issue and inspect the resulting issue activity log.

### First Test

Path: tests/test_agent_hub_v3.py::AgentHubV3Tests.test_sync_merged_pr_marks_in_review_issue_completed
Expected initial result: fails because no command currently syncs merged PR
state into issue completion.
Reason this proves the regression or requirement: it captures the exact stuck
state where a merged implementation PR remains `In Review` in Agent Hub and
continues blocking dependent work.

### Final Verification

Commands: python3 -m unittest tests.test_agent_hub_v3 tests.test_file_hub_backend
Expected result: Agent Hub v3 and file backend tests pass, including merged PR
sync coverage and unchanged behavior for unmerged or inaccessible PRs.

### Untestable Surface

- Live GitHub API availability and credentials vary by developer machine. Cover
  API behavior through a mockable provider, and document one authenticated manual
  smoke when credentials are present.

## Assumptions

- Private repositories require authentication to query PR merge state reliably.
- `gh pr view --json state,mergedAt,mergeCommit,url,baseRefName,headRefName` is
  acceptable when `gh` is installed and authenticated.
- A token fallback can use GitHub's REST or GraphQL API with read-only repo
  permissions.

## Dependencies

- None.

## Open Questions

- Should `state refresh` perform this sync automatically, or should packet loops
  call an explicit `state sync-merged-prs` command before analysis?
- Should auto-completion require final verification evidence on the issue, or is
  a merged PR plus existing review policy sufficient?

## Activity Log

### Created
Date: 2026-06-29T06:49:46Z
Agent: Codex
Reason: Follow-up from packet-loop blockage where a merged PR left an Agent Hub
issue in `In Review`, preventing dependent work from becoming ready.
Next step: Implement deterministic GitHub PR merge sync with authenticated and
safe unauthenticated paths.

### Claimed for work
Date: 2026-07-03T16:18:55.843290Z
Agent: Codex
Claim ID: codex-sync-merged-prs-20260703
Branch: codex/agent-hub-sync-merged-prs
Worktree Path: /Users/jcpinto/git/notion-agent-hub-skills-agent-hub-sync-merged-prs

### Progress
Date: 2026-07-03T16:35:00Z
Agent: Codex
Summary: Added deterministic state sync-merged-prs command with packet scoping, GitHub PR merge detection through gh plus token fallback, completion activity logging, claim cleanup, and diagnostics for skipped PRs.
TDD: First test tests.test_agent_hub_v3.AgentHubV3Tests.test_sync_merged_pr_marks_in_review_issue_completed failed because sync_merged_prs was missing; packet-scope test failed because change filtering was missing.
Touched: skills/manage-agent-hub-issues/lib/file_hub_common.py; skills/manage-agent-hub-issues/scripts/agent_hub.py; tests/test_agent_hub_v3.py; tests/test_file_hub_backend.py; README.md; skills/manage-agent-hub-issues/references/v3-workflows.md; run-agent-hub-loop installed/source skill instructions.
Verification: python3 -m unittest tests.test_agent_hub_v3 tests.test_file_hub_backend passed; python3 -m unittest discover -s tests passed; python3 skills/manage-agent-hub-issues/scripts/agent_hub.py state sync-merged-prs --change agent-hub-sync-merged-prs returned ok with no completions.
Risks: Live GitHub API behavior depends on gh, GITHUB_TOKEN, or GH_TOKEN credentials; covered through provider injection and safe diagnostics, not live network fixtures.
Next step: PR https://github.com/jcpinto54/notion-agent-hub-skills/pull/4 is open for review.

### Released claim (submitted)
Date: 2026-07-03T16:31:09.383788Z
Claim ID: codex-sync-merged-prs-20260703
Mode: submitted
Status: In Review
Owner: Unassigned
