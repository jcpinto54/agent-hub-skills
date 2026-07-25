from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
COMMON_LIB = ROOT / "skills/manage-agent-hub-issues/lib"
CLI_PATH = ROOT / "skills/manage-agent-hub-issues/scripts/agent_hub.py"
sys.path.insert(0, str(COMMON_LIB))

import file_hub_common as file_hub  # noqa: E402


PROJECT_TEMPLATES = {
    "principles.md": [
        "# Principles",
        "## Quality Bar",
        "## TDD And Regression Policy",
        "## Review Rules",
        "## Security And Safety",
        "## Non-Negotiables",
        "## Tradeoffs",
    ],
    "product.md": ["# Product"],
    "tech.md": ["# Tech"],
    "structure.md": ["# Structure"],
    "standards-index.md": ["# Standards Index"],
    "delegation.md": [
        "# Delegation Rules",
        "The main agent is an orchestrator, not an executor.",
        "## Main Agent Responsibilities",
        "## Subagent Responsibilities",
        "## Handoff Contract",
        "## Evidence Requirements",
        "## Stop Conditions",
        "## Exceptions",
    ],
}

CHANGE_TEMPLATES = {
    "proposal.md": ["# Proposal", "## Why", "## What Changes", "## Out Of Scope"],
    "shape.md": ["# Shape", "## User Intent", "## Constraints"],
    "design.md": ["# Design", "## Approach", "## Data Flow", "## Interfaces"],
    "tasks.md": ["# Tasks", "## Dependency Graph", "## Issues"],
    "checklist.md": ["# Checklist", "## Spec Quality", "## TDD Readiness"],
    "evidence.md": ["# Evidence", "## Test Runs", "## Notes"],
    "review.md": ["# Review", "## Review Status", "## Findings"],
}


class AgentHubV3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent_hub_home_temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.agent_hub_home_temp.cleanup)
        self.agent_hub_home = Path(self.agent_hub_home_temp.name).resolve()

    def make_repo(self) -> Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / ".git").mkdir()
        return root

    def free_local_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.bind(("127.0.0.1", 0))
            return int(server.getsockname()[1])

    def make_git_repo(self, name: str = "repo") -> Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / name
        root.mkdir()
        self.git(root, "init")
        (root / "README.md").write_text(f"# {name}\n", encoding="utf-8")
        self.git(root, "add", "README.md")
        self.git(
            root,
            "-c",
            "user.name=Agent Hub",
            "-c",
            "user.email=agent@example.invalid",
            "commit",
            "-m",
            "init",
        )
        return root

    def remove_worktree(self, root: Path, linked: Path) -> None:
        subprocess.run(
            ["git", "-C", str(root), "worktree", "remove", "--force", str(linked)],
            capture_output=True,
            text=True,
            check=False,
        )

    def git(self, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"git {' '.join(args)} failed in {cwd}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        return result

    def read_frontmatter(self, path: Path) -> tuple[dict[str, object], str]:
        return file_hub.parse_frontmatter(path.read_text(encoding="utf-8"))

    def read_yamlish(self, path: Path) -> dict[str, object]:
        text = path.read_text(encoding="utf-8")
        data, _ = file_hub.parse_frontmatter(f"---\n{text}\n---\n")
        return data

    def require_backend_function(self, name: str):
        func = getattr(file_hub, name, None)
        self.assertTrue(
            callable(func),
            f"file_hub_common.{name} must exist for deterministic v3 .hub writes.",
        )
        return func

    def assert_has_diagnostic(self, result: dict[str, object], code: str) -> None:
        diagnostics = result.get("diagnostics")
        self.assertIsInstance(diagnostics, list)
        matches = [
            diag
            for diag in diagnostics
            if isinstance(diag, dict) and diag.get("code") == code
        ]
        self.assertTrue(
            matches,
            f"Expected diagnostic code {code!r}; got {json.dumps(diagnostics, sort_keys=True)}",
        )

    def assert_stable_diagnostics(self, result: dict[str, object]) -> None:
        diagnostics = result.get("diagnostics")
        self.assertIsInstance(diagnostics, list)
        for diagnostic in diagnostics:
            self.assertIsInstance(diagnostic, dict)
            self.assertIsInstance(diagnostic.get("code"), str)
            self.assertIn(diagnostic.get("severity"), {"error", "warning", "info"})
            self.assertIsInstance(diagnostic.get("target"), str)
            self.assertIsInstance(diagnostic.get("message"), str)
            self.assertIsInstance(diagnostic.get("recommendation"), str)

    def run_cli(
        self, repo: Path, *args: str, hub_root: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        self.assertTrue(
            CLI_PATH.exists(),
            "skills/manage-agent-hub-issues/scripts/agent_hub.py must provide the v3 CLI.",
        )
        command = [sys.executable, str(CLI_PATH), "--repo", str(repo)]
        if hub_root is not None:
            command.extend(["--hub-root", str(hub_root)])
        command.extend(args)
        env = os.environ.copy()
        env["AGENT_HUB_HOME"] = str(self.agent_hub_home)
        return subprocess.run(
            command,
            cwd=repo,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def assert_cli_ok(
        self, repo: Path, *args: str, hub_root: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        result = self.run_cli(repo, *args, hub_root=hub_root)
        self.assertEqual(
            result.returncode,
            0,
            f"CLI command failed: {' '.join(args)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        return result

    def assert_cli_fails(
        self, repo: Path, *args: str, hub_root: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        result = self.run_cli(repo, *args, hub_root=hub_root)
        self.assertNotEqual(
            result.returncode,
            0,
            f"CLI command unexpectedly succeeded: {' '.join(args)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        return result

    def agent_ready_spec(self) -> str:
        return """# CLI Tightened Spec

## Context

The CLI needs deterministic commands for tightening issue specs and exporting a
read-only dashboard snapshot.

## Scope

- Support `agent-hub issue set-spec`.
- Support `agent-hub dashboard export`.

## Out Of Scope

- No mutable dashboard operations.
- No web server.

## Done Criteria

- [ ] The CLI can tighten an issue spec from a markdown file.
- [ ] The CLI can export a dashboard JSON file filtered by change.

## Verification Strategy

### Regression Target

The top-level CLI exposes the new deterministic backend commands.

### Test Plan

- [ ] Unit: python3 -m unittest tests.test_file_hub_backend tests.test_agent_hub_v3
- [ ] Integration: top-level CLI smoke invokes both commands.
- [ ] E2E / Playwright: Not applicable.
- [ ] Manual / inspection: Inspect JSON output.

### First Test

Path: tests/test_agent_hub_v3.py::AgentHubV3Tests.test_top_level_cli_exists_and_supports_representative_v3_commands
Expected initial result: fails before new CLI commands exist
Reason this proves the regression or requirement: it exercises the public command surface.

### Final Verification

Commands: python3 -m unittest tests.test_file_hub_backend tests.test_agent_hub_v3
Expected result: all targeted tests pass

### Untestable Surface

None.

## Assumptions

- The dashboard command returns stable JSON.

## Dependencies

- Existing v3 CLI parser and backend helpers.

## Open Questions

None.
"""

    def test_central_hub_resolution_shares_linked_worktrees_but_not_separate_clones(self):
        root = self.make_git_repo("central-resolution")
        linked = root.parent / "central-resolution-linked"
        self.git(root, "worktree", "add", str(linked))
        self.addCleanup(self.remove_worktree, root, linked)
        separate = root.parent / "central-resolution-copy"
        shutil.copytree(root, separate, ignore=shutil.ignore_patterns(".git"))
        self.git(separate, "init")

        with patch.dict(os.environ, {"AGENT_HUB_HOME": str(self.agent_hub_home)}):
            root_hub = file_hub.central_hub_path(start=root)
            linked_hub = file_hub.central_hub_path(start=linked)
            separate_hub = file_hub.central_hub_path(start=separate)

        self.assertEqual(root_hub, linked_hub)
        self.assertNotEqual(root_hub, separate_hub)
        self.assertTrue(str(root_hub).startswith(str(self.agent_hub_home / "projects")))
        self.assertEqual(root_hub.name, "hub")

    def test_cli_init_uses_central_store_and_linked_worktree_runtime_claims_are_shared(self):
        root = self.make_git_repo("central-cli")
        linked = root.parent / "central-cli-linked"
        self.git(root, "worktree", "add", str(linked))
        self.addCleanup(self.remove_worktree, root, linked)

        init_result = self.assert_cli_ok(root, "init", "--project-name", "Central CLI")
        init_payload = json.loads(init_result.stdout)
        central_hub = Path(init_payload["hub"])

        self.assertTrue(central_hub.exists())
        self.assertTrue(str(central_hub).startswith(str(self.agent_hub_home)))
        self.assertFalse((root / ".hub/config.yml").exists())

        self.assert_cli_ok(
            root, "issue", "create", "--id", "shared-claim", "--title", "Shared Claim"
        )
        self.assert_cli_ok(
            linked,
            "claim",
            "acquire",
            "--issue",
            "shared-claim",
            "--owner",
            "Codex",
            "--claim-id",
            "shared-work",
        )
        claims_path = central_hub / "runtime/claims.json"
        claims = json.loads(claims_path.read_text(encoding="utf-8"))
        self.assertEqual(claims["shared-claim"]["id"], "shared-work")

        check_result = self.assert_cli_ok(
            root, "claim", "check", "--issue", "shared-claim", "--claim-id", "shared-work"
        )
        check_payload = json.loads(check_result.stdout)
        self.assertEqual(check_payload["claim_id"], "shared-work")

        metadata = json.loads((central_hub.parent / "project.json").read_text(encoding="utf-8"))
        self.assertEqual(
            set(metadata["worktrees"]),
            {str(root.resolve()), str(linked.resolve())},
        )

    def test_cli_migrate_imports_legacy_hub_without_mutating_repo_hub(self):
        root = self.make_repo()
        legacy_hub = file_hub.create_hub(root, "Legacy Project")
        file_hub.create_issue_file(legacy_hub, "Legacy Issue", "legacy-issue")
        file_hub.claim_issue(
            legacy_hub,
            file_hub.issue_by_id(legacy_hub, "legacy-issue"),
            "work",
            "Codex",
            120,
            "legacy-work",
        )
        before = {
            path.relative_to(legacy_hub).as_posix(): path.read_bytes()
            for path in sorted(legacy_hub.rglob("*"))
            if path.is_file()
        }

        result = self.assert_cli_ok(root, "migrate")
        payload = json.loads(result.stdout)
        central_hub = Path(payload["hub"])

        self.assertTrue((central_hub / "issues/legacy-issue.md").exists())
        claims = json.loads((central_hub / "runtime/claims.json").read_text(encoding="utf-8"))
        self.assertEqual(
            claims["legacy-issue"]["id"],
            "legacy-work",
        )
        after = {
            path.relative_to(legacy_hub).as_posix(): path.read_bytes()
            for path in sorted(legacy_hub.rglob("*"))
            if path.is_file()
        }
        self.assertEqual(before, after)

        migrated_issue = self.assert_cli_ok(root, "dashboard", "export")
        dashboard = json.loads(migrated_issue.stdout)
        self.assertEqual(dashboard["summary"]["issue_count"], 1)

        (legacy_hub / "issues/repo-local-only.md").write_text(
            """---
id: repo-local-only
title: "Repo Local Only"
status: Not Started
type: Feature
priority: P2
owner: Unassigned
change: ""
depends_on: []
blocks: []
claim: {}
base_branch: ""
branch: ""
worktree_path: ""
commit_sha: ""
pr_url: ""
related_links: ""
---

## Context
""",
            encoding="utf-8",
        )
        ignored_legacy = self.assert_cli_ok(root, "dashboard", "export")
        ignored_dashboard = json.loads(ignored_legacy.stdout)
        self.assertEqual(ignored_dashboard["summary"]["issue_count"], 1)

    def test_cli_init_refuses_legacy_repo_hub_before_migration(self):
        root = self.make_repo()
        legacy_hub = file_hub.create_hub(root, "Legacy Project")

        result = self.assert_cli_fails(root, "init", "--project-name", "Wrong Empty Hub")

        self.assertIn("migrate", result.stderr)
        self.assertFalse(file_hub.central_hub_path(root).exists())
        self.assertTrue((legacy_hub / "config.yml").exists())

    def test_cli_migrate_rejects_explicit_hub_root_override(self):
        root = self.make_repo()
        legacy_hub = file_hub.create_hub(root, "Legacy Project")

        result = self.assert_cli_fails(root, "migrate", hub_root=legacy_hub)

        self.assertIn("--hub-root", result.stderr)
        self.assertFalse(file_hub.central_hub_path(root).exists())

    def test_hub_root_escape_hatch_uses_explicit_hub_path(self):
        root = self.make_repo()
        central_init = self.assert_cli_ok(root, "init", "--project-name", "Central Project")
        central_hub = Path(json.loads(central_init.stdout)["hub"])
        explicit_parent = root / "explicit"
        explicit_hub = file_hub.create_hub(explicit_parent, "Explicit Project")
        file_hub.create_issue_file(explicit_hub, "Explicit Issue", "explicit-issue")

        central_dashboard = json.loads(self.assert_cli_ok(root, "dashboard", "export").stdout)
        explicit_dashboard = json.loads(
            self.assert_cli_ok(root, "dashboard", "export", hub_root=explicit_hub).stdout
        )

        self.assertEqual(central_dashboard["hub"]["project"], "Central Project")
        self.assertEqual(central_hub, file_hub.resolve_hub_path(hub_root=central_hub))
        self.assertEqual(explicit_dashboard["hub"]["project"], "Explicit Project")
        self.assertEqual(explicit_dashboard["summary"]["issue_count"], 1)

    def test_dashboard_revision_distinguishes_separate_hubs_with_same_contents(self):
        root = self.make_repo()
        first = file_hub.create_hub(root / "first", "Same Project")
        second = file_hub.create_hub(root / "second", "Same Project")
        file_hub.create_issue_file(first, "Same Issue", "same-issue")
        file_hub.create_issue_file(second, "Same Issue", "same-issue")

        first_revision = file_hub.dashboard_live_snapshot(first)["revision"]["id"]
        second_revision = file_hub.dashboard_live_snapshot(second)["revision"]["id"]

        self.assertNotEqual(first_revision, second_revision)

    def test_v3_hub_layout_initialization_creates_required_files_and_templates(self):
        root = self.make_repo()

        hub = file_hub.create_hub(root, "V3 Project")

        required_paths = [
            hub / "config.yml",
            hub / "state.yml",
            hub / ".gitignore",
            hub / "project",
            hub / "changes",
            hub / "issues",
            hub / "decisions",
            hub / "reports",
            hub / "artifacts",
            hub / "runtime",
            *(hub / "project" / name for name in PROJECT_TEMPLATES),
        ]
        missing = [str(path.relative_to(hub)) for path in required_paths if not path.exists()]
        self.assertEqual(missing, [], "v3 init must create the complete .hub layout.")

        self.assertEqual((hub / ".gitignore").read_text(encoding="utf-8"), "runtime/\n")

        config = file_hub.load_config(hub)
        self.assertEqual(str(config.get("version")), "3")
        self.assertEqual(config.get("source_of_truth"), "file")
        self.assertEqual(config.get("project"), "V3 Project")
        self.assertEqual(config.get("cli", {}).get("strict_writes"), True)
        self.assertEqual(config.get("cli", {}).get("preserve_unknown_frontmatter"), True)
        self.assertEqual(config.get("agents", {}).get("require_subagent_for_tasks"), True)
        self.assertEqual(config.get("audit", {}).get("tdd_required_for_implementation"), True)
        self.assertEqual(config.get("dashboard", {}).get("mode"), "read-only")

        for filename, expected_snippets in PROJECT_TEMPLATES.items():
            text = (hub / "project" / filename).read_text(encoding="utf-8")
            for snippet in expected_snippets:
                self.assertIn(snippet, text, f"{filename} missing {snippet!r}")

    def test_issue_template_includes_change_field_and_verification_strategy(self):
        root = self.make_repo()
        hub = file_hub.create_hub(root, "V3 Project")

        issue = file_hub.create_issue_file(
            hub,
            "Add deterministic CLI",
            "add-deterministic-cli",
        )
        frontmatter, body = self.read_frontmatter(issue.path)

        expected_keys = {
            "id",
            "title",
            "status",
            "type",
            "priority",
            "owner",
            "change",
            "depends_on",
            "blocks",
            "claim",
            "base_branch",
            "branch",
            "worktree_path",
            "commit_sha",
            "pr_url",
            "related_links",
        }
        missing_keys = sorted(expected_keys.difference(frontmatter))
        self.assertEqual(missing_keys, [], "v3 issues must expose the required frontmatter.")
        self.assertEqual(frontmatter["change"], "")

        expected_sections = [
            "## Context",
            "## Scope",
            "## Out Of Scope",
            "## Done Criteria",
            "## Verification Strategy",
            "### Regression Target",
            "### Test Plan",
            "- [ ] Unit:",
            "- [ ] Integration:",
            "- [ ] E2E / Playwright:",
            "- [ ] Manual / inspection:",
            "### First Test",
            "Path:",
            "Expected initial result:",
            "Reason this proves the regression or requirement:",
            "### Final Verification",
            "Commands:",
            "Expected result:",
            "### Untestable Surface",
            "## Assumptions",
            "## Dependencies",
            "## Open Questions",
            "## Activity Log",
        ]
        missing_sections = [section for section in expected_sections if section not in body]
        self.assertEqual(
            missing_sections,
            [],
            "v3 issue template must include the verification strategy contract.",
        )

    def test_change_packet_creation_and_issue_linking(self):
        root = self.make_repo()
        hub = file_hub.create_hub(root, "V3 Project")
        create_change_packet = self.require_backend_function("create_change_packet")
        link_issue_to_change = self.require_backend_function("link_issue_to_change")

        create_change_packet(
            hub,
            "agent-hub-v3",
            "Agent Hub v3",
            priority="P1",
            owner="Codex",
        )
        issue = file_hub.create_issue_file(hub, "Build v3 CLI", "build-v3-cli")
        link_issue_to_change(hub, "agent-hub-v3", issue.id)

        change_dir = hub / "changes/agent-hub-v3"
        missing_templates = [
            name
            for name in ["change.yml", *CHANGE_TEMPLATES]
            if not (change_dir / name).exists()
        ]
        self.assertEqual(missing_templates, [], "change creation must write all packet files.")

        change_data = self.read_yamlish(change_dir / "change.yml")
        self.assertEqual(change_data.get("id"), "agent-hub-v3")
        self.assertEqual(change_data.get("title"), "Agent Hub v3")
        self.assertEqual(change_data.get("status"), "Draft")
        self.assertEqual(change_data.get("priority"), "P1")
        self.assertEqual(change_data.get("owner"), "Codex")
        self.assertEqual(change_data.get("issues"), ["build-v3-cli"])

        for filename, expected_snippets in CHANGE_TEMPLATES.items():
            text = (change_dir / filename).read_text(encoding="utf-8")
            for snippet in expected_snippets:
                self.assertIn(snippet, text, f"{filename} missing {snippet!r}")

        issue_frontmatter, _ = self.read_frontmatter(hub / "issues/build-v3-cli.md")
        self.assertEqual(issue_frontmatter.get("change"), "agent-hub-v3")
        self.assertIn("build-v3-cli", (change_dir / "tasks.md").read_text(encoding="utf-8"))

    def test_change_packet_issue_unlinking_clears_issue_and_packet_links(self):
        root = self.make_repo()
        hub = file_hub.create_hub(root, "V3 Project")
        create_change_packet = self.require_backend_function("create_change_packet")
        link_issue_to_change = self.require_backend_function("link_issue_to_change")
        unlink_issue_from_change = self.require_backend_function("unlink_issue_from_change")

        create_change_packet(hub, "agent-hub-v3", "Agent Hub v3")
        issue = file_hub.create_issue_file(hub, "Build v3 CLI", "build-v3-cli")
        link_issue_to_change(hub, "agent-hub-v3", issue.id)

        result = unlink_issue_from_change(hub, "agent-hub-v3", issue.id)

        self.assertEqual(result["issue"], "build-v3-cli")
        self.assertEqual(result["previous_change"], "agent-hub-v3")
        self.assertTrue(result["removed_from_change"])
        self.assertTrue(result["cleared_issue_change"])
        self.assertTrue(result["removed_task"])

        change_dir = hub / "changes/agent-hub-v3"
        change_data = self.read_yamlish(change_dir / "change.yml")
        self.assertEqual(change_data.get("issues"), [])
        issue_frontmatter, _ = self.read_frontmatter(hub / "issues/build-v3-cli.md")
        self.assertEqual(issue_frontmatter.get("change"), "")
        self.assertNotIn("build-v3-cli", (change_dir / "tasks.md").read_text(encoding="utf-8"))

    def test_issue_dependency_add_and_remove_updates_both_sides(self):
        root = self.make_repo()
        hub = file_hub.create_hub(root, "V3 Project")
        add_dependency = self.require_backend_function("add_issue_dependency")
        remove_dependency = self.require_backend_function("remove_issue_dependency")

        file_hub.create_issue_file(hub, "Provider", "provider")
        file_hub.create_issue_file(hub, "Consumer", "consumer")

        add_dependency(hub, "consumer", "provider")
        add_dependency(hub, "consumer", "provider")

        consumer = file_hub.issue_by_id(hub, "consumer")
        provider = file_hub.issue_by_id(hub, "provider")
        self.assertEqual(consumer.depends_on, ["provider"])
        self.assertEqual(provider.blocks, ["consumer"])

        remove_dependency(hub, "consumer", "provider")

        consumer = file_hub.issue_by_id(hub, "consumer")
        provider = file_hub.issue_by_id(hub, "provider")
        self.assertEqual(consumer.depends_on, [])
        self.assertEqual(provider.blocks, [])

    def test_issue_file_paths_are_confined_to_issues_directory(self):
        root = self.make_repo()
        hub = file_hub.create_hub(root, "V3 Project")

        issue = file_hub.create_issue_file(hub, "Confined issue", "confined-issue")
        self.assertEqual(issue.path.resolve().parent, (hub / "issues").resolve())

        with self.assertRaises(Exception):  # noqa: B017 - API-level refusal is the contract.
            file_hub.create_issue_file(hub, "Escaped issue", "../escaped-issue")

        self.assertFalse((hub / "escaped-issue.md").exists())
        self.assertFalse((root / "escaped-issue.md").exists())

    def test_mutating_issue_commands_reject_path_escape_inputs(self):
        root = self.make_repo()
        hub = file_hub.create_hub(root, "V3 Project")
        file_hub.create_issue_file(hub, "Safe Issue", "safe-issue")

        outside_issue = root.parent / "outside-issue.md"
        outside_text = """---
id: outside-issue
title: "Outside Issue"
status: Not Started
type: Feature
priority: P2
owner: Unassigned
depends_on: []
blocks: []
claim: {}
---

## Context

Outside the hub.
"""
        outside_issue.write_text(outside_text, encoding="utf-8")

        created = self.assert_cli_fails(
            root,
            "issue",
            "create",
            "--id",
            "../escaped-issue",
            "--title",
            "Escaped Issue",
            hub_root=hub,
        )
        self.assertIn("issue", created.stderr.lower())
        self.assertFalse((hub / "escaped-issue.md").exists())

        appended = self.assert_cli_fails(
            root,
            "issue",
            "append-activity",
            "--issue",
            str(outside_issue),
            "--heading",
            "Escape",
            "--line",
            "Summary: should not write outside .hub/issues",
            hub_root=hub,
        )
        self.assertIn("issue", appended.stderr.lower())
        self.assertEqual(outside_issue.read_text(encoding="utf-8"), outside_text)

        evidenced = self.assert_cli_fails(
            root,
            "issue",
            "add-evidence",
            "--issue",
            "safe-issue/../safe-issue",
            "--heading",
            "Escape",
            "--line",
            "Command: should fail before writing artifacts",
            hub_root=hub,
        )
        self.assertIn("issue", evidenced.stderr.lower())
        self.assertFalse((hub / "artifacts/safe-issue").exists())

    def test_issue_create_with_missing_change_fails_without_creating_issue(self):
        root = self.make_repo()
        hub = file_hub.create_hub(root, "V3 Project")

        result = self.assert_cli_fails(
            root,
            "issue",
            "create",
            "--id",
            "orphaned-work",
            "--title",
            "Orphaned Work",
            "--change",
            "missing-change",
            hub_root=hub,
        )

        self.assertIn("missing-change", result.stderr)
        self.assertFalse((hub / "issues/orphaned-work.md").exists())

    def test_strict_status_transitions_reject_skips_and_preserve_current_status(self):
        root = self.make_repo()
        hub = file_hub.create_hub(root, "V3 Project")
        set_status = self.require_backend_function("set_issue_status")
        file_hub.create_issue_file(hub, "Status flow", "status-flow")

        invalid_error: Exception | None = None
        try:
            set_status(hub, "status-flow", "Completed", reason="cannot skip review")
        except Exception as exc:  # noqa: BLE001 - test asserts API-level refusal.
            invalid_error = exc
        self.assertIsNotNone(invalid_error)
        self.assertNotIsInstance(invalid_error, TypeError)
        self.assertEqual(file_hub.issue_by_id(hub, "status-flow").status, "Not Started")

        set_status(hub, "status-flow", "In Progress", reason="implementation started")
        set_status(hub, "status-flow", "In Review", reason="submitted for review")
        set_status(hub, "status-flow", "Completed", reason="review passed")
        self.assertEqual(file_hub.issue_by_id(hub, "status-flow").status, "Completed")

    def test_activity_and_evidence_entries_are_append_only(self):
        root = self.make_repo()
        hub = file_hub.create_hub(root, "V3 Project")
        append_activity = self.require_backend_function("append_issue_activity")
        add_evidence = self.require_backend_function("add_issue_evidence")
        issue = file_hub.create_issue_file(hub, "Append-only entries", "append-only")
        original_text = issue.path.read_text(encoding="utf-8")

        append_activity(
            hub,
            "append-only",
            "Progress",
            ["Date: 2026-06-26T00:00:00Z", "Summary: first note"],
        )
        add_evidence(
            hub,
            "append-only",
            "Initial failing test",
            ["Command: python3 -m unittest tests.test_agent_hub_v3", "Result: failed"],
        )
        add_evidence(
            hub,
            "append-only",
            "Final verification",
            ["Command: python3 -m unittest discover -s tests", "Result: passed"],
        )

        updated_text = (hub / "issues/append-only.md").read_text(encoding="utf-8")
        self.assertIn(original_text.split("## Activity Log")[0], updated_text)
        self.assertLess(updated_text.index("Summary: first note"), updated_text.index("Initial failing test"))
        self.assertLess(updated_text.index("Initial failing test"), updated_text.index("Final verification"))
        self.assertTrue((hub / "artifacts/append-only").is_dir())

    def test_state_refresh_writes_state_file_with_current_issue_and_change_summary(self):
        root = self.make_repo()
        hub = file_hub.create_hub(root, "V3 Project")
        create_change_packet = self.require_backend_function("create_change_packet")
        link_issue_to_change = self.require_backend_function("link_issue_to_change")
        refresh_state = self.require_backend_function("refresh_state")

        create_change_packet(hub, "state-refresh", "State refresh")
        file_hub.create_issue_file(hub, "Refresh state", "refresh-state")
        link_issue_to_change(hub, "state-refresh", "refresh-state")

        result = refresh_state(hub)

        self.assertIsInstance(result, dict)
        self.assertEqual(str(result.get("version")), "3")
        state_path = hub / "state.yml"
        self.assertTrue(state_path.exists(), "state refresh must write .hub/state.yml")
        state_text = state_path.read_text(encoding="utf-8")
        self.assertIn("version: 3", state_text)
        self.assertIn("refresh-state", state_text)
        self.assertIn("state-refresh", state_text)

    def test_sync_merged_pr_marks_in_review_issue_completed(self):
        root = self.make_repo()
        hub = file_hub.create_hub(root, "V3 Project")
        file_hub.create_change_packet(hub, "merge-sync", "Merge sync")
        merged = file_hub.create_issue_file(
            hub,
            "Merged PR",
            "merged-pr",
            change="merge-sync",
        )
        merged.status = "In Review"
        merged.owner = "Codex"
        merged.claim = {"id": "review-claim"}
        merged.pr_url = "https://github.com/example/repo/pull/42"
        merged.commit_sha = "headsha123"
        merged.write()
        dependent = file_hub.create_issue_file(
            hub,
            "Dependent",
            "dependent",
            change="merge-sync",
        )
        dependent.depends_on = ["merged-pr"]
        dependent.write()
        file_hub.write_runtime_claims(
            hub,
            {
                "merged-pr": {
                    "id": "review-claim",
                    "purpose": "review",
                    "owner": "Codex",
                    "expires_at": "2099-01-01T00:00:00Z",
                }
            },
        )
        sync_merged_prs = self.require_backend_function("sync_merged_prs")

        def provider(pr_url: str) -> dict[str, object]:
            self.assertEqual(pr_url, "https://github.com/example/repo/pull/42")
            return {
                "state": "MERGED",
                "url": pr_url,
                "merge_commit_sha": "mergecommit456",
                "merged_at": "2026-07-03T12:00:00Z",
            }

        result = sync_merged_prs(hub, provider=provider)

        self.assertEqual(result["completed"], ["merged-pr"])
        self.assertEqual(result["skipped"], [])
        updated = file_hub.issue_by_id(hub, "merged-pr")
        self.assertEqual(updated.status, "Completed")
        self.assertEqual(updated.claim, {})
        self.assertEqual(file_hub.load_runtime_claims(hub), {})
        self.assertIn("PR URL: https://github.com/example/repo/pull/42", updated.body)
        self.assertIn("Merge commit: mergecommit456", updated.body)
        self.assertIn("Merged at: 2026-07-03T12:00:00Z", updated.body)
        state = file_hub.refresh_state(hub)
        self.assertEqual(state["issues"]["merged-pr"]["status"], "Completed")
        by_id = {issue.id: issue for issue in file_hub.load_issues(hub)}
        self.assertEqual(file_hub.readiness(by_id["dependent"], by_id), ("Ready", ""))

    def test_audit_and_analyze_return_stable_diagnostics(self):
        root = self.make_repo()
        hub = file_hub.create_hub(root, "V3 Project")
        audit_hub = self.require_backend_function("audit_hub")
        audit_issue = self.require_backend_function("audit_issue")
        analyze_change = self.require_backend_function("analyze_change")
        create_change_packet = self.require_backend_function("create_change_packet")

        create_change_packet(hub, "broken-change", "Broken change")
        (hub / "project/tech.md").unlink(missing_ok=True)
        (hub / "issues/missing-tdd.md").write_text(
            """---
id: missing-tdd
title: "Missing TDD"
status: Not Started
type: Feature
priority: P2
owner: Unassigned
change: broken-change
depends_on: ["ghost-dependency"]
blocks: []
claim: {}
base_branch: ""
branch: ""
worktree_path: ""
commit_sha: ""
pr_url: ""
related_links: ""
---

## Context

## Scope

## Out Of Scope

## Done Criteria

- [ ] Observable behavior exists

## Verification Strategy

### Regression Target

### Test Plan

### First Test

Path:
Expected initial result:
Reason this proves the regression or requirement:

### Final Verification

Commands:
Expected result:

### Untestable Surface

## Activity Log
""",
            encoding="utf-8",
        )

        hub_result = audit_hub(hub)
        issue_result = audit_issue(hub, "missing-tdd")
        analysis_result = analyze_change(hub, "broken-change")

        for result in [hub_result, issue_result, analysis_result]:
            self.assertIsInstance(result, dict)
            self.assert_stable_diagnostics(result)

        self.assert_has_diagnostic(hub_result, "missing_required_file")
        self.assert_has_diagnostic(hub_result, "dangling_dependency")
        self.assert_has_diagnostic(issue_result, "implementation_missing_first_test")
        self.assert_has_diagnostic(analysis_result, "change_issue_link_mismatch")

        self.assertTrue((hub / "reports/latest-audit.json").exists())
        self.assertTrue((hub / "reports/latest-audit.md").exists())
        self.assertTrue((hub / "reports/latest-analysis.json").exists())
        self.assertTrue((hub / "reports/latest-analysis.md").exists())

    def test_audit_issue_reports_malformed_frontmatter_for_specific_issue(self):
        root = self.make_repo()
        hub = file_hub.create_hub(root, "V3 Project")
        malformed_path = hub / "issues/malformed.md"
        malformed_path.write_text(
            """---
id: malformed
title: "Malformed Issue
status: Not Started
depends_on: [missing
---

## Context

Malformed frontmatter should be reported deterministically.
""",
            encoding="utf-8",
        )

        result = self.assert_cli_ok(root, "audit", "issue", "malformed", hub_root=hub)
        payload = json.loads(result.stdout)

        self.assert_stable_diagnostics(payload)
        self.assert_has_diagnostic(payload, "malformed_frontmatter")
        diagnostics = payload["diagnostics"]
        malformed = [item for item in diagnostics if item["code"] == "malformed_frontmatter"]
        self.assertEqual(malformed[0]["target"], ".hub/issues/malformed.md")

    def test_audit_hub_reports_malformed_runtime_claims_json(self):
        root = self.make_repo()
        hub = file_hub.create_hub(root, "V3 Project")
        (hub / "runtime/claims.json").write_text("{not json", encoding="utf-8")

        result = file_hub.audit_hub(hub)

        self.assert_stable_diagnostics(result)
        self.assert_has_diagnostic(result, "malformed_runtime_claims")

    def test_audit_hub_reports_expired_runtime_claim_for_known_issue(self):
        root = self.make_repo()
        hub = file_hub.create_hub(root, "V3 Project")
        file_hub.create_issue_file(hub, "Runtime Worker", "runtime-worker")
        (hub / "runtime/claims.json").write_text(
            json.dumps(
                {
                    "runtime-worker": {
                        "id": "runtime-claim",
                        "purpose": "work",
                        "owner": "Codex",
                        "claimed_at": "2000-01-01T00:00:00Z",
                        "expires_at": "2000-01-01T01:00:00Z",
                    }
                }
            ),
            encoding="utf-8",
        )

        result = file_hub.audit_hub(hub)

        self.assert_stable_diagnostics(result)
        self.assert_has_diagnostic(result, "stale_claim")
        stale = [item for item in result["diagnostics"] if item["code"] == "stale_claim"]
        self.assertIn(".hub/issues/runtime-worker.md", {item["target"] for item in stale})

    def test_top_level_cli_exists_and_supports_representative_v3_commands(self):
        root = self.make_repo()

        self.assert_cli_ok(root, "init", "--project-name", "CLI Project")
        self.assert_cli_ok(root, "state", "refresh")
        sync_result = self.assert_cli_ok(root, "state", "sync-merged-prs")
        sync_payload = json.loads(sync_result.stdout)
        self.assertEqual(sync_payload["completed"], [])
        self.assertEqual(sync_payload["skipped"], [])
        self.assert_cli_ok(root, "change", "create", "--slug", "cli-change", "--title", "CLI Change")
        self.assert_cli_ok(root, "issue", "create", "--id", "cli-dependency", "--title", "CLI Dependency")
        self.assert_cli_ok(
            root,
            "issue",
            "create",
            "--id",
            "cli-issue",
            "--title",
            "CLI Issue",
            "--change",
            "cli-change",
        )
        spec_file = root / "cli-spec.md"
        spec_file.write_text(self.agent_ready_spec(), encoding="utf-8")
        self.assert_cli_ok(
            root,
            "issue",
            "set-spec",
            "--issue",
            "cli-issue",
            "--spec-file",
            str(spec_file),
        )
        dashboard_path = root / "dashboard.json"
        export_result = self.assert_cli_ok(
            root,
            "dashboard",
            "export",
            "--change",
            "cli-change",
            "--output",
            str(dashboard_path),
        )
        export_payload = json.loads(export_result.stdout)
        self.assertEqual(export_payload["output"], str(dashboard_path))
        dashboard_payload = json.loads(dashboard_path.read_text(encoding="utf-8"))
        self.assertEqual(dashboard_payload["mode"], "read-only")
        self.assertEqual(dashboard_payload["change"], "cli-change")
        self.assertEqual(dashboard_payload["revision"]["change"], "cli-change")
        stdout_dashboard = self.assert_cli_ok(root, "dashboard", "export", "--change", "cli-change")
        stdout_payload = json.loads(stdout_dashboard.stdout)
        self.assertEqual(stdout_payload["revision"]["change"], "cli-change")
        self.assertEqual(stdout_payload["columns"][1]["title"], "Ready")
        self.assert_cli_ok(root, "change", "link-issue", "--change", "cli-change", "--issue", "cli-issue")
        self.assert_cli_ok(root, "change", "unlink-issue", "--change", "cli-change", "--issue", "cli-issue")
        self.assert_cli_ok(root, "change", "link-issue", "--change", "cli-change", "--issue", "cli-issue")
        self.assert_cli_ok(root, "issue", "add-dependency", "--issue", "cli-issue", "--depends-on", "cli-dependency")
        self.assert_cli_ok(root, "issue", "remove-dependency", "--issue", "cli-issue", "--depends-on", "cli-dependency")
        self.assert_cli_ok(root, "issue", "set-status", "--issue", "cli-dependency", "--status", "In Progress")
        self.assert_cli_ok(root, "issue", "set-status", "--issue", "cli-dependency", "--status", "In Review")
        self.assert_cli_ok(root, "issue", "set-status", "--issue", "cli-dependency", "--status", "Completed")
        self.assert_cli_ok(root, "claim", "acquire", "--issue", "cli-issue", "--purpose", "work", "--owner", "Codex", "--claim-id", "cli-work", "--ttl-minutes", "60")
        self.assert_cli_ok(root, "claim", "check", "--issue", "cli-issue", "--claim-id", "cli-work")
        self.assert_cli_ok(root, "claim", "renew", "--issue", "cli-issue", "--claim-id", "cli-work", "--ttl-minutes", "120")
        self.assert_cli_ok(root, "issue", "append-activity", "--issue", "cli-issue", "--heading", "Progress", "--line", "Summary: CLI smoke")
        self.assert_cli_ok(root, "issue", "add-evidence", "--issue", "cli-issue", "--heading", "CLI smoke", "--line", "Command: agent-hub smoke")
        self.assert_cli_ok(root, "claim", "release", "--issue", "cli-issue", "--claim-id", "cli-work", "--mode", "submitted", "--pr-url", "https://github.com/example/repo/pull/1")
        self.assert_cli_ok(root, "audit", "hub")
        self.assert_cli_ok(root, "audit", "issue", "cli-issue")
        self.assert_cli_ok(root, "analyze", "change", "cli-change")

    def test_dashboard_serve_exposes_read_only_state_api(self):
        root = self.make_repo()
        hub = file_hub.create_hub(root, "Serve Project")
        file_hub.create_change_packet(hub, "serve-change", "Serve Change")
        issue = file_hub.create_issue_file(
            hub,
            "Serve Card",
            "serve-card",
            change="serve-change",
        )
        file_hub.link_issue_to_change(hub, "serve-change", issue.id)

        port = self.free_local_port()
        server = subprocess.Popen(
            [
                sys.executable,
                str(CLI_PATH),
                "--repo",
                str(root),
                "--hub-root",
                str(hub),
                "dashboard",
                "serve",
                "--change",
                "serve-change",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--poll-interval",
                "0.05",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        def stop_server() -> None:
            if server.poll() is None:
                server.terminate()
                try:
                    server.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.communicate(timeout=5)
            else:
                server.communicate(timeout=5)

        self.addCleanup(stop_server)
        base_url = f"http://127.0.0.1:{port}"

        for _ in range(100):
            if server.poll() is not None:
                stdout, stderr = server.communicate()
                self.fail(f"dashboard serve exited early\nstdout:\n{stdout}\nstderr:\n{stderr}")
            try:
                with urllib.request.urlopen(f"{base_url}/healthz", timeout=0.2) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.read().decode("utf-8"), "ok\n")
                    break
            except OSError:
                time.sleep(0.05)
        else:
            self.fail("dashboard serve did not become healthy")

        health_head = urllib.request.Request(f"{base_url}/healthz", method="HEAD")
        with urllib.request.urlopen(health_head, timeout=2) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get("Content-Length"), str(len(b"ok\n")))
            self.assertEqual(response.read(), b"")

        with urllib.request.urlopen(f"{base_url}/", timeout=2) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("text/html", response.headers.get("Content-Type", ""))
            self.assertIn("Read-only hub dashboard", response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/state", timeout=2) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get("Cache-Control"), "no-store")
            state = json.loads(response.read().decode("utf-8"))
        self.assertEqual(state["version"], "3")
        self.assertEqual(state["change"], "serve-change")
        self.assertEqual(state["revision"]["source"], "file")
        self.assertEqual(state["summary"]["issue_count"], 1)
        first_revision = state["revision"]["id"]

        with urllib.request.urlopen(f"{base_url}/hub-state.json", timeout=2) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get("Cache-Control"), "no-store")
            viewer_state = json.loads(response.read().decode("utf-8"))
        self.assertEqual(viewer_state["revision"]["id"], first_revision)

        mutation_paths = ["/", "/healthz", "/api/state", "/hub-state.json", "/api/events"]
        for path in mutation_paths:
            for method in ["POST", "PUT", "PATCH", "DELETE"]:
                request = urllib.request.Request(f"{base_url}{path}", method=method)
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(request, timeout=2)
                self.assertEqual(raised.exception.code, 405)
                self.assertEqual(raised.exception.headers.get("Allow"), "GET, HEAD")
                self.assertEqual(raised.exception.headers.get("Cache-Control"), "no-store")

        events_request = urllib.request.Request(
            f"{base_url}/api/events",
            headers={"Accept": "text/event-stream"},
        )
        with urllib.request.urlopen(events_request, timeout=3) as events:
            self.assertEqual(events.status, 200)
            self.assertEqual(events.headers.get("Cache-Control"), "no-store")
            self.assertIn("text/event-stream", events.headers.get("Content-Type", ""))

            def read_revision_event() -> tuple[str, dict[str, object]]:
                deadline = time.monotonic() + 3
                event_name = ""
                data_lines: list[str] = []
                while time.monotonic() < deadline:
                    line = events.readline().decode("utf-8").rstrip("\r\n")
                    if not line:
                        if data_lines:
                            return event_name, json.loads("\n".join(data_lines))
                        event_name = ""
                        continue
                    if line.startswith("event:"):
                        event_name = line.removeprefix("event:").strip()
                    elif line.startswith("data:"):
                        data_lines.append(line.removeprefix("data:").lstrip())
                self.fail("timed out waiting for SSE event data")

            initial_event_name, initial_event = read_revision_event()
            self.assertEqual(initial_event_name, "revision")
            self.assertEqual(initial_event["revision"]["id"], first_revision)

            updated = file_hub.issue_by_id(hub, "serve-card")
            updated.status = "Completed"
            updated.write()

            changed_event_name, changed_event = read_revision_event()
            self.assertEqual(changed_event_name, "revision")
            self.assertNotEqual(changed_event["revision"]["id"], first_revision)
            self.assertEqual(changed_event["summary"]["issue_count"], 1)

        stop_server()


if __name__ == "__main__":
    unittest.main()
