---
id: "hub-viewer-live-serve-api"
title: "Add read-only dashboard serve API"
status: "In Progress"
type: "Feature"
priority: "P1"
owner: "Unassigned"
area: ""
summary: ""
blockers: ""
dependency_notes: ""
change: "hub-viewer-live-updates"
depends_on: ["hub-viewer-live-snapshot-cache"]
blocks: ["hub-viewer-live-client", "hub-viewer-live-regression-docs"]
claim: {}
base_branch: "codex/agent-hub-v3-repo-native"
branch: "codex/hub-viewer-live-serve-api"
worktree_path: "/Users/jcpinto/git/agent-hub-skills-hub-viewer-live-serve-api"
commit_sha: "180b32cc7767c11f0d6b3b93483acee297b0a24e"
pr_url: "https://github.com/jcpinto54/notion-agent-hub-skills/pull/3"
related_links: ""
external_url: ""
---
## Context

After backend live snapshot helpers exist, Agent Hub needs a local command that serves the existing viewer and current dashboard state without requiring repeated dashboard export commands.

## Scope

- Add agent-hub dashboard serve to the CLI with local bind defaults of 127.0.0.1 and a configurable port.
- Serve existing static viewer files from skills/list-agent-hub-issues/viewer/.
- Expose GET /api/state with dashboard schema version 3, live revision metadata, and Cache-Control: no-store.
- Expose GET /api/events using server-sent events for revision notifications.
- Expose GET /healthz for smoke checks.
- Reject POST, PUT, PATCH, and DELETE requests with 405.
- Keep the server implementation dependency-free with Python stdlib only.

## Out Of Scope

- No viewer live-mode client changes in this issue.
- No browser write APIs or mutation endpoints.
- No WebSocket, Node, Vite, React, CDN, auth, hosting, or external sync work.

## Done Criteria

- [ ] CLI parser accepts dashboard serve options without breaking dashboard export.
- [ ] Local server returns valid /api/state JSON for a temp hub.
- [ ] SSE endpoint emits a revision notification when backend source changes.
- [ ] Mutation HTTP methods are rejected.
- [ ] Static viewer files are served from the existing viewer directory.

## Verification Strategy

### Regression Target

The live dashboard needs a read-only local API surface that exposes current backend snapshots while refusing mutation paths.

### Test Plan

- [ ] Unit: python3 -m unittest tests.test_agent_hub_v3
- [ ] Integration: server smoke against a temp hub for /, /api/state, /api/events, and /healthz
- [ ] Manual / inspection: verify POST/PUT/PATCH/DELETE return 405

### First Test

Path: tests/test_agent_hub_v3.py::AgentHubV3CliTests.test_dashboard_serve_exposes_read_only_state_api
Expected initial result: fails before dashboard serve and its state endpoint exist
Reason this proves the regression or requirement: it locks the public CLI/API shape and read-only behavior before implementation

### Final Verification

Commands: python3 -m unittest tests.test_file_hub_backend tests.test_agent_hub_v3
Expected result: focused live backend and CLI/server tests pass

### Untestable Surface

None beyond browser visual fidelity, which must be covered by desktop and mobile smoke evidence where the issue touches UI.

## Assumptions

- The serve command is local-first and not a hosted product surface.
- SSE is preferred for lightweight updates, with client polling fallback implemented separately.

## Dependencies

- hub-viewer-live-snapshot-cache must provide revision-aware read-only state helpers.

## Open Questions

None.

## Activity Log

### Claimed for work
Date: 2026-07-03T15:49:13.790405Z
Agent: Codex
Claim ID: work-ee84560d-7ae8-465b-b090-383e7b66ca99
Branch: codex/hub-viewer-live-serve-api
Worktree Path: /Users/jcpinto/git/agent-hub-skills-hub-viewer-live-serve-api

### Progress
Date: 2026-07-03T15:56:58.720311Z
Agent: Codex
Summary: Added failing-first CLI/server regression for dashboard serve, then implemented a dependency-free stdlib local read-only dashboard server backed by DashboardLiveSnapshotCache.
Evidence: tests/test_agent_hub_v3.py; skills/manage-agent-hub-issues/scripts/agent_hub.py; red test failed because argparse rejected dashboard serve; server exposes /healthz, static viewer, /api/state, /api/events SSE, and 405 mutation responses.
Verification: python3 -m unittest tests.test_agent_hub_v3.AgentHubV3Tests.test_dashboard_serve_exposes_read_only_state_api -> OK; python3 -m unittest tests.test_file_hub_backend tests.test_agent_hub_v3 -> OK (25 tests); python3 -m unittest -> OK (51 tests); python3 -m py_compile skills/manage-agent-hub-issues/scripts/agent_hub.py -> OK.
Risks / skipped checks: No live client changes included by issue scope. Independent review subagent did not return before the wait timeout; local diff review and full tests completed.
Next step: Commit, push, open a normal PR, submit the issue to review, and release the work claim.

### Status change: In Progress -> In Review
Date: 2026-07-03T15:57:00Z
Agent: Codex
Implemented: Added agent-hub dashboard serve with local host/port options, stdlib ThreadingHTTPServer, static viewer serving, /healthz, /api/state with schema v3 live revision metadata and no-store, /api/events SSE revision notifications, and 405 handling for mutation methods.
Touched: skills/manage-agent-hub-issues/scripts/agent_hub.py; tests/test_agent_hub_v3.py; .hub/issues/hub-viewer-live-serve-api.md; .hub/changes/hub-viewer-live-updates/change.yml.
Checks run: python3 -m unittest tests.test_agent_hub_v3.AgentHubV3Tests.test_dashboard_serve_exposes_read_only_state_api -> OK; python3 -m unittest tests.test_file_hub_backend tests.test_agent_hub_v3 -> OK (25 tests); python3 -m unittest -> OK (51 tests); python3 -m py_compile skills/manage-agent-hub-issues/scripts/agent_hub.py -> OK.
Artifacts: Commit 180b32cc7767c11f0d6b3b93483acee297b0a24e; PR https://github.com/jcpinto54/notion-agent-hub-skills/pull/3.
Findings: Red test failed before implementation because argparse rejected dashboard serve; green tests cover state, SSE, healthz, static viewer, and mutation rejection.
Risks / skipped checks: No live client changes included by scope. Independent review subagent timed out before returning; local review and full tests completed.
Reviewer should verify: Server remains stdlib-only, read-only, path-confined to the viewer directory, and emits SSE revision updates when .hub source files change.

### Released claim (submitted)
Date: 2026-07-03T15:58:56.289837Z
Claim ID: work-ee84560d-7ae8-465b-b090-383e7b66ca99
Mode: submitted
Status: In Review
Owner: Unassigned

### Claimed for review
Date: 2026-07-03T16:00:55.877510Z
Agent: Codex-Review
Claim ID: review-39e91b48-d24e-4b77-a121-c60f49c7b36b
Branch: codex/hub-viewer-live-serve-api
Worktree Path: /Users/jcpinto/git/notion-agent-hub-skills-hub-viewer-live-serve-api

### Status change: In Review -> In Progress
Date: 2026-07-03T16:01:10Z
Reviewer: Codex-Review
Review type: Independent code review send-back
Reviewed: PR https://github.com/jcpinto54/notion-agent-hub-skills/pull/3 and commit 180b32cc7767c11f0d6b3b93483acee297b0a24e.
Reason sent back: Acceptance criteria are not fully satisfied by the first PR revision.
Required fixes: P1 root viewer does not load live hub state because app.js defaults to ./hub-state.json and the server does not provide that route; P2 SSE handlers can retain request threads after disconnected clients when no revision changes occur; P2 mutation coverage only checks /api/state and should include /, /healthz, and /api/events; P3 SSE test should assert event: revision.
Dependencies: hub-viewer-live-snapshot-cache metadata was updated to Completed using recorded PR #2 merge evidence before this review claim.
Evidence: Independent review findings recorded in Codex subagent 019f28af-d144-7c22-9195-96c084b6996f.
Recommended next step: Reclaim work, add failing coverage for these review findings, implement the smallest server/test changes, rerun focused and full verification, update the PR.

### Released claim (review-fail)
Date: 2026-07-03T16:01:08.171972Z
Claim ID: review-39e91b48-d24e-4b77-a121-c60f49c7b36b
Mode: review-fail
Status: In Progress
Owner: Unassigned
