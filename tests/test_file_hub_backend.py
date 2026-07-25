from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
COMMON_LIB = ROOT / "skills/manage-agent-hub-issues/lib"
sys.path.insert(0, str(COMMON_LIB))

import file_hub_common as file_hub  # noqa: E402

LIST_PATH = ROOT / "skills/list-agent-hub-issues/scripts/agent_hub_list.py"
CLAIM_PATH = ROOT / "skills/claim-agent-hub-issue/scripts/agent_hub_claim.py"
INIT_PATH = ROOT / "skills/init-agent-hub/scripts/init_file_hub.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


list_mod = load_module("agent_hub_list_file_tests", LIST_PATH)
claim_mod = load_module("agent_hub_claim_file_tests", CLAIM_PATH)
init_mod = load_module("init_file_hub_tests", INIT_PATH)


class FileHubBackendTests(unittest.TestCase):
    def make_repo(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        (root / ".git").mkdir()
        hub = file_hub.create_hub(root, "Test Project")
        return temp, root, hub

    def agent_ready_spec(self) -> str:
        return """# Tightened Spec

## Context

The read-only Kanban viewer and spec tightening command need deterministic
backend behavior that agents can rely on without hand-editing `.hub` files.

## Scope

- Add a deterministic `issue set-spec` backend path.
- Replace only the bounded spec sections in an existing issue.
- Preserve the issue frontmatter and existing activity log.

## Out Of Scope

- No hosted web dashboard.
- No external mirror updates.

## Done Criteria

- [ ] Existing frontmatter keys survive spec tightening.
- [ ] Bounded spec sections are replaced from the spec file.
- [ ] Existing activity log entries remain append-only.

## Verification Strategy

### Regression Target

The backend can tighten a vague issue into an audit-clean implementation spec.

### Test Plan

- [ ] Unit: python3 -m unittest tests.test_file_hub_backend tests.test_agent_hub_v3
- [ ] Integration: CLI smoke covers issue set-spec and dashboard export.
- [ ] E2E / Playwright: Not applicable for the backend-only command.
- [ ] Manual / inspection: Inspect the resulting issue markdown.

### First Test

Path: tests/test_file_hub_backend.py::FileHubBackendTests.test_set_issue_spec_preserves_frontmatter_replaces_sections_and_clears_diagnostics
Expected initial result: fails before deterministic set-spec support exists
Reason this proves the regression or requirement: it exercises the exact issue rewrite contract.

### Final Verification

Commands: python3 -m unittest tests.test_file_hub_backend tests.test_agent_hub_v3
Expected result: all targeted tests pass

### Untestable Surface

None.

## Assumptions

- Spec files use the same bounded headings as issue templates.

## Dependencies

- Existing issue frontmatter parsing and writing helpers.

## Open Questions

None.
"""

    def set_agent_ready_body(self, issue: file_hub.FileHubIssue) -> file_hub.FileHubIssue:
        issue.body = self.agent_ready_spec().split("# Tightened Spec\n", 1)[1].lstrip()
        issue.write()
        return file_hub.issue_by_id(issue.path.parent.parent, issue.id)

    def test_parse_and_write_issue_frontmatter(self):
        temp, _, hub = self.make_repo()
        self.addCleanup(temp.cleanup)

        issue = file_hub.create_issue_file(hub, "Add file backend", "hub-file-backend")
        loaded = file_hub.issue_by_id(hub, "hub-file-backend")

        self.assertEqual(loaded.id, "hub-file-backend")
        self.assertEqual(loaded.title, "Add file backend")
        self.assertEqual(loaded.status, "Not Started")
        self.assertIn("## Activity Log", loaded.body)

        loaded.status = "In Progress"
        loaded.depends_on = ["dependency"]
        loaded.write()
        reloaded = file_hub.issue_by_id(hub, "hub-file-backend")
        self.assertEqual(reloaded.status, "In Progress")
        self.assertEqual(reloaded.depends_on, ["dependency"])

    def test_readiness_from_dependencies_blockers_and_claims(self):
        temp, _, hub = self.make_repo()
        self.addCleanup(temp.cleanup)

        dep = file_hub.create_issue_file(hub, "Dependency", "dep")
        dep.status = "Completed"
        dep.write()
        ready = file_hub.create_issue_file(hub, "Ready", "ready")
        ready.depends_on = ["dep"]
        ready.write()
        blocked = file_hub.create_issue_file(hub, "Blocked", "blocked")
        blocked.blockers = "Waiting for credentials"
        blocked.write()
        claimed = file_hub.create_issue_file(hub, "Claimed", "claimed")
        claimed.claim = {
            "id": "work-other",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10))
            .isoformat()
            .replace("+00:00", "Z"),
        }
        claimed.write()

        issues = file_hub.load_issues(hub)
        by_id = {issue.id: issue for issue in issues}

        self.assertEqual(file_hub.readiness(by_id["ready"], by_id), ("Ready", ""))
        self.assertEqual(file_hub.readiness(by_id["blocked"], by_id)[0], "Blocked")
        self.assertEqual(file_hub.readiness(by_id["claimed"], by_id)[0], "Blocked")

    def test_claim_refusal_success_release_and_runtime_locking(self):
        temp, _, hub = self.make_repo()
        self.addCleanup(temp.cleanup)

        dep = file_hub.create_issue_file(hub, "Dependency", "dep")
        dep.status = "In Progress"
        dep.write()
        waiting = file_hub.create_issue_file(hub, "Waiting", "waiting")
        waiting.depends_on = ["dep"]
        waiting.write()

        with self.assertRaises(RuntimeError):
            file_hub.claim_issue(hub, waiting, "work", "Codex", 120, "work-waiting")

        dep.status = "Completed"
        dep.write()
        waiting = file_hub.issue_by_id(hub, "waiting")
        result = file_hub.claim_issue(
            hub,
            waiting,
            "work",
            "Codex",
            120,
            "work-waiting",
            base_branch="main",
            branch="codex/waiting",
            worktree_path="/tmp/waiting",
        )
        self.assertEqual(result["status"], "In Progress")
        runtime = json.loads((hub / "runtime/claims.json").read_text(encoding="utf-8"))
        self.assertEqual(runtime["waiting"]["id"], "work-waiting")

        with self.assertRaises(RuntimeError):
            file_hub.claim_issue(
                hub,
                file_hub.issue_by_id(hub, "waiting"),
                "work",
                "Other",
                120,
                "work-other",
            )

        released = file_hub.release_issue(
            hub,
            file_hub.issue_by_id(hub, "waiting"),
            "work-waiting",
            "submitted",
            pr_url="https://github.com/o/r/pull/1",
            commit_sha="abc123",
        )
        self.assertEqual(released["status"], "In Review")
        self.assertEqual(file_hub.load_runtime_claims(hub), {})

    def test_append_activity_is_append_only(self):
        temp, _, hub = self.make_repo()
        self.addCleanup(temp.cleanup)

        issue = file_hub.create_issue_file(hub, "Evidence", "evidence")
        issue.append_activity("Progress", ["Date: 2026-06-26T00:00:00Z", "Summary: first"])
        issue.append_activity("Review", ["Date: 2026-06-26T01:00:00Z", "Summary: second"])
        text = issue.path.read_text(encoding="utf-8")

        self.assertLess(text.index("### Progress"), text.index("### Review"))
        self.assertIn("Summary: first", text)
        self.assertIn("Summary: second", text)

    def test_set_issue_spec_preserves_frontmatter_replaces_sections_and_clears_diagnostics(self):
        temp, root, hub = self.make_repo()
        self.addCleanup(temp.cleanup)

        issue = file_hub.create_issue_file(hub, "Rough Issue", "rough-issue")
        frontmatter, body = file_hub.parse_frontmatter(issue.path.read_text(encoding="utf-8"))
        frontmatter["custom_field"] = "keep-me"
        issue.path.write_text(file_hub.dump_frontmatter(frontmatter) + body, encoding="utf-8")
        issue = file_hub.issue_by_id(hub, "rough-issue")
        issue.append_activity("Progress", ["Summary: existing note"])

        before_codes = {
            item["code"] for item in file_hub.issue_audit_diagnostics(hub, issue)
        }
        self.assertIn("implementation_missing_first_test", before_codes)
        self.assertIn("implementation_missing_final_verification", before_codes)

        spec_file = root / "spec.md"
        spec_file.write_text(self.agent_ready_spec(), encoding="utf-8")
        set_issue_spec = getattr(file_hub, "set_issue_spec", None)
        self.assertTrue(callable(set_issue_spec), "set_issue_spec backend helper is required.")

        result = set_issue_spec(hub, "rough-issue", spec_file)

        self.assertEqual(result["issue"], "rough-issue")
        updated_frontmatter, updated_body = file_hub.parse_frontmatter(
            issue.path.read_text(encoding="utf-8")
        )
        self.assertEqual(updated_frontmatter["custom_field"], "keep-me")
        self.assertEqual(updated_frontmatter["status"], "Not Started")
        self.assertIn("## Context", updated_body)
        self.assertIn("## Scope", updated_body)
        self.assertIn("Add a deterministic `issue set-spec` backend path.", updated_body)
        self.assertNotIn("## Context\n\n## Scope", updated_body)
        self.assertIn("### Progress\nSummary: existing note", updated_body)
        self.assertLess(updated_body.index("## Open Questions"), updated_body.index("## Activity Log"))

        updated_issue = file_hub.issue_by_id(hub, "rough-issue")
        self.assertTrue(file_hub.has_first_test(updated_issue.body))
        self.assertTrue(file_hub.has_final_verification(updated_issue.body))
        self.assertEqual(file_hub.issue_audit_diagnostics(hub, updated_issue), [])

    def test_dashboard_snapshot_is_read_only_change_filtered_kanban_payload(self):
        temp, _, hub = self.make_repo()
        self.addCleanup(temp.cleanup)
        file_hub.create_change_packet(hub, "viewer-change", "Viewer Change")
        file_hub.create_change_packet(hub, "other-change", "Other Change")

        def linked_issue(issue_id: str, title: str, status: str = "Not Started"):
            issue = file_hub.create_issue_file(
                hub,
                title,
                issue_id,
                change="viewer-change",
            )
            file_hub.link_issue_to_change(hub, "viewer-change", issue.id)
            issue = file_hub.issue_by_id(hub, issue.id)
            if status != "Not Started":
                issue.status = status
            return issue

        needs_spec = linked_issue("needs-spec", "Needs Spec")
        ready = self.set_agent_ready_body(linked_issue("ready-card", "Ready Card"))
        in_progress = self.set_agent_ready_body(
            linked_issue("progress-card", "Progress Card", "In Progress")
        )
        in_review = self.set_agent_ready_body(
            linked_issue("review-card", "Review Card", "In Review")
        )
        completed = self.set_agent_ready_body(
            linked_issue("completed-card", "Completed Card", "Completed")
        )
        blocked = self.set_agent_ready_body(linked_issue("blocked-card", "Blocked Card"))
        blocked.blockers = "Waiting for external credentials"
        blocked.write()
        other = file_hub.create_issue_file(
            hub,
            "Other Change Card",
            "other-card",
            change="other-change",
        )
        file_hub.link_issue_to_change(hub, "other-change", other.id)

        state_path = hub / "state.yml"
        state_before = state_path.read_text(encoding="utf-8")
        reports_before = sorted(
            path.relative_to(hub).as_posix()
            for path in (hub / "reports").rglob("*")
        )

        dashboard_snapshot = getattr(file_hub, "dashboard_snapshot", None)
        self.assertTrue(callable(dashboard_snapshot), "dashboard_snapshot helper is required.")
        snapshot = dashboard_snapshot(hub, change="viewer-change")

        self.assertEqual(state_path.read_text(encoding="utf-8"), state_before)
        reports_after = sorted(
            path.relative_to(hub).as_posix()
            for path in (hub / "reports").rglob("*")
        )
        self.assertEqual(reports_after, reports_before)

        self.assertEqual(snapshot["version"], "3")
        self.assertIn("generated_at", snapshot)
        self.assertEqual(snapshot["mode"], "read-only")
        self.assertEqual(snapshot["change"], "viewer-change")
        self.assertEqual(snapshot["hub"]["project"], "Test Project")
        self.assertEqual(snapshot["hub"]["source_of_truth"], "file")
        self.assertEqual(snapshot["hub"]["dashboard_mode"], "read-only")
        self.assertEqual(
            [column["title"] for column in snapshot["columns"]],
            ["Needs Spec", "Ready", "In Progress", "In Review", "Completed", "Blocked"],
        )
        cards_by_column = {
            column["title"]: [card["id"] for card in column["issues"]]
            for column in snapshot["columns"]
        }
        self.assertEqual(cards_by_column["Needs Spec"], [needs_spec.id])
        self.assertEqual(cards_by_column["Ready"], [ready.id])
        self.assertEqual(cards_by_column["In Progress"], [in_progress.id])
        self.assertEqual(cards_by_column["In Review"], [in_review.id])
        self.assertEqual(cards_by_column["Completed"], [completed.id])
        self.assertEqual(cards_by_column["Blocked"], [blocked.id])
        all_ids = [issue_id for values in cards_by_column.values() for issue_id in values]
        self.assertNotIn("other-card", all_ids)

        cards = {
            card["id"]: card
            for column in snapshot["columns"]
            for card in column["issues"]
        }
        ready_card = cards["ready-card"]
        self.assertEqual(ready_card["readiness"], {"state": "Ready", "reason": ""})
        self.assertEqual(ready_card["diagnostics"], [])
        self.assertIn("Existing frontmatter keys survive", "\n".join(ready_card["done_criteria"]))
        self.assertEqual(
            ready_card["verification"]["first_test"]["path"],
            "tests/test_file_hub_backend.py::FileHubBackendTests.test_set_issue_spec_preserves_frontmatter_replaces_sections_and_clears_diagnostics",
        )
        self.assertIn(
            "python3 -m unittest",
            ready_card["verification"]["final_verification"]["commands"],
        )

        needs_spec_codes = {item["code"] for item in cards["needs-spec"]["diagnostics"]}
        self.assertIn("implementation_missing_first_test", needs_spec_codes)
        self.assertIn("issue_scope_too_vague", needs_spec_codes)
        self.assertEqual(cards["blocked-card"]["readiness"]["state"], "Blocked")
        self.assertIn("external blocker", cards["blocked-card"]["readiness"]["reason"])
        review_codes = {item["code"] for item in cards["review-card"]["diagnostics"]}
        self.assertIn("review_ready_missing_commit", review_codes)

    def test_dashboard_live_state_recomputes_after_issue_file_change_without_writes(self):
        temp, root, hub = self.make_repo()
        self.addCleanup(temp.cleanup)
        file_hub.create_change_packet(hub, "viewer-change", "Viewer Change")

        issue = file_hub.create_issue_file(
            hub,
            "Ready Card",
            "ready-card",
            change="viewer-change",
        )
        file_hub.link_issue_to_change(hub, "viewer-change", issue.id)
        self.set_agent_ready_body(issue)

        state_path = hub / "state.yml"
        report_path = hub / "reports/latest-analysis.json"
        viewer_state_path = root / "skills/list-agent-hub-issues/viewer/hub-state.json"
        state_path.write_text("sentinel: state\n", encoding="utf-8")
        report_path.write_text('{"sentinel": "report"}\n', encoding="utf-8")
        viewer_state_path.parent.mkdir(parents=True, exist_ok=True)
        viewer_state_path.write_text('{"sentinel": "viewer"}\n', encoding="utf-8")

        protected_paths = [state_path, report_path, viewer_state_path]
        protected_before = {
            path: (path.read_text(encoding="utf-8"), path.stat().st_mtime_ns)
            for path in protected_paths
        }
        reports_before = sorted(
            path.relative_to(hub).as_posix()
            for path in (hub / "reports").rglob("*")
        )

        live_cache = getattr(file_hub, "DashboardLiveSnapshotCache", None)
        self.assertTrue(callable(live_cache), "DashboardLiveSnapshotCache helper is required.")
        cache = live_cache()
        first = cache.get(hub, change="viewer-change")
        second = cache.get(hub, change="viewer-change")

        self.assertEqual(first, second)
        self.assertEqual(first["version"], "3")
        self.assertEqual(first["change"], "viewer-change")
        self.assertIn("revision", first)
        self.assertRegex(first["revision"]["id"], r"^[a-f0-9]{64}$")
        self.assertEqual(first["revision"]["etag"], f'"{first["revision"]["id"]}"')
        self.assertEqual(first["summary"]["issue_count"], 1)
        first_revision = first["revision"]["id"]
        first_generated_at = first["generated_at"]

        updated = file_hub.issue_by_id(hub, "ready-card")
        updated.status = "Completed"
        updated.write()
        after_change = cache.get(hub, change="viewer-change")

        self.assertNotEqual(after_change["revision"]["id"], first_revision)
        self.assertNotEqual(after_change["generated_at"], first_generated_at)
        cards_by_column = {
            column["title"]: [card["id"] for card in column["issues"]]
            for column in after_change["columns"]
        }
        self.assertEqual(cards_by_column["Ready"], [])
        self.assertEqual(cards_by_column["Completed"], ["ready-card"])

        for path, (content, mtime_ns) in protected_before.items():
            self.assertEqual(path.read_text(encoding="utf-8"), content)
            self.assertEqual(path.stat().st_mtime_ns, mtime_ns)
        reports_after = sorted(
            path.relative_to(hub).as_posix()
            for path in (hub / "reports").rglob("*")
        )
        self.assertEqual(reports_after, reports_before)

    def test_list_and_claim_scripts_use_explicit_hub_root_file_backend(self):
        temp, root, hub = self.make_repo()
        self.addCleanup(temp.cleanup)

        file_hub.create_issue_file(hub, "Ready from script", "ready-script")
        cwd = Path.cwd()
        try:
            os.chdir(root)
            with redirect_stdout(StringIO()):
                list_rc = list_mod.main(
                    ["--hub-root", str(hub), "--format", "json", "--readiness", "Ready"]
                )
            self.assertEqual(list_rc, 0)
            with redirect_stdout(StringIO()):
                claim_rc = claim_mod.main(
                    [
                        "--hub-root",
                        str(hub),
                        "claim",
                        "--page-id",
                        "ready-script",
                        "--purpose",
                        "work",
                        "--owner",
                        "Codex",
                        "--claim-id",
                        "work-script",
                    ]
                )
            self.assertEqual(claim_rc, 0)
        finally:
            os.chdir(cwd)

    def test_init_script_creates_central_layout(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / ".git").mkdir()
        agent_hub_home = root / "agent-hub-home"

        with patch.dict(os.environ, {"AGENT_HUB_HOME": str(agent_hub_home)}):
            with redirect_stdout(StringIO()):
                rc = init_mod.main(["--repo", str(root), "--project-name", "Script Project"])
            hub = file_hub.central_hub_path(root)

        self.assertEqual(rc, 0)
        self.assertFalse((root / ".hub/config.yml").exists())
        self.assertTrue((hub / "config.yml").exists())
        self.assertTrue((hub / "issues").is_dir())
        self.assertTrue((hub / "decisions").is_dir())
        self.assertTrue((hub / "artifacts").is_dir())
        self.assertEqual((hub / ".gitignore").read_text(encoding="utf-8"), "runtime/\n")


if __name__ == "__main__":
    unittest.main()
