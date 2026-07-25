from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYNC_PATH = ROOT / "skills/sync-agent-hub-skills/scripts/agent_hub_sync_skills.py"


def load_module():
    spec = importlib.util.spec_from_file_location("agent_hub_sync_skills", SYNC_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["agent_hub_sync_skills"] = module
    spec.loader.exec_module(module)
    return module


sync_mod = load_module()


def run(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, check=True, text=True, stdout=subprocess.PIPE)


def write(path: Path, text: str = "content\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_skill(root: Path, name: str, extra_file: str | None = None) -> None:
    write(root / name / "SKILL.md", f"---\nname: {name}\ndescription: {name}\n---\n\n# {name}\n")
    write(root / name / "agents" / "openai.yaml", "interface:\n  display_name: Skill\n")
    if extra_file:
        write(root / name / extra_file, "extra\n")


def init_repo(repo: Path) -> None:
    run(["git", "init", "-b", "main"], cwd=repo)
    run(["git", "config", "user.name", "Test"], cwd=repo)
    run(["git", "config", "user.email", "test@example.invalid"], cwd=repo)


def commit_all(repo: Path, message: str = "initial") -> None:
    run(["git", "add", "."], cwd=repo)
    run(["git", "commit", "-m", message], cwd=repo)


def make_local_and_repo(tmp: Path) -> tuple[Path, Path]:
    local = tmp / "local-skills"
    repo = tmp / "repo"
    repo.mkdir()
    init_repo(repo)
    for skill in sync_mod.EXPECTED_SKILLS:
        make_skill(local, skill)
        make_skill(repo / "skills", skill)
    commit_all(repo)
    return local, repo


class AgentHubSyncSkillsTests(unittest.TestCase):
    def test_expected_skills_include_dry_mece_context_skill(self):
        self.assertIn("dry-mece", sync_mod.EXPECTED_SKILLS)

    def test_expected_skills_include_iteration_orchestrator(self):
        self.assertIn("iterate-agent-hub-work", sync_mod.EXPECTED_SKILLS)

    def test_expected_skills_include_packet_loop_operator(self):
        self.assertIn("run-agent-hub-loop", sync_mod.EXPECTED_SKILLS)

    def test_expected_skills_include_pr_preview_verification(self):
        self.assertIn("verify-agent-hub-pr-preview", sync_mod.EXPECTED_SKILLS)

    def test_expected_skills_include_spec_gate(self):
        self.assertIn("spec-agent-hub-issue", sync_mod.EXPECTED_SKILLS)

    def test_requires_repo_dir(self):
        parser = sync_mod.build_parser()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args([])

    def test_rejects_non_agent_hub_repo(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw) / "repo"
            repo.mkdir()
            init_repo(repo)
            write(repo / "skills" / "other-skill" / "SKILL.md")
            commit_all(repo)
            with self.assertRaises(sync_mod.SyncError):
                sync_mod.ensure_repo(repo)

    def test_sync_copies_only_allowlisted_skills_and_excludes_cache(self):
        with tempfile.TemporaryDirectory() as raw:
            local, repo = make_local_and_repo(Path(raw))
            write(local / "list-agent-hub-issues" / "scripts" / "new.py", "print('new')\n")
            write(local / "list-agent-hub-issues" / "scripts" / "__pycache__" / "new.pyc", "cache")
            make_skill(local, "unrelated-local-skill", "SHOULD_NOT_COPY.md")

            synced = sync_mod.sync_skills(local, repo)

            self.assertIn("list-agent-hub-issues", synced)
            self.assertTrue((repo / "skills/list-agent-hub-issues/scripts/new.py").exists())
            self.assertFalse(
                (repo / "skills/list-agent-hub-issues/scripts/__pycache__/new.pyc").exists()
            )
            self.assertFalse((repo / "skills/unrelated-local-skill").exists())

    def test_dirty_repo_fails_preflight(self):
        with tempfile.TemporaryDirectory() as raw:
            _, repo = make_local_and_repo(Path(raw))
            write(repo / "dirty.txt", "dirty\n")
            with self.assertRaises(sync_mod.SyncError):
                sync_mod.ensure_clean_repo(repo)

    def test_missing_tracked_local_file_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            local, repo = make_local_and_repo(Path(raw))
            write(repo / "skills/list-agent-hub-issues/scripts/tracked.py", "print('repo')\n")
            commit_all(repo, "add tracked")

            with self.assertRaises(sync_mod.SyncError):
                sync_mod.ensure_no_missing_tracked_local_files(repo, local)

    def test_basic_metadata_validation_rejects_bad_skill_name(self):
        with tempfile.TemporaryDirectory() as raw:
            local, repo = make_local_and_repo(Path(raw))
            _ = local
            write(
                repo / "skills/list-agent-hub-issues/SKILL.md",
                "---\nname: wrong-name\ndescription: bad\n---\n\n# Bad\n",
            )

            with self.assertRaises(sync_mod.SyncError):
                sync_mod.basic_validate_skill_metadata(repo)

    def test_noop_sync_has_no_changes_to_commit(self):
        with tempfile.TemporaryDirectory() as raw:
            local, repo = make_local_and_repo(Path(raw))
            sync_mod.sync_skills(local, repo)
            result = sync_mod.commit_and_push(repo, "Sync", "origin", push=False)

            self.assertEqual(result, "No changes to commit.")

    def test_changed_sync_creates_commit_without_push(self):
        with tempfile.TemporaryDirectory() as raw:
            local, repo = make_local_and_repo(Path(raw))
            write(local / "list-agent-hub-issues" / "SKILL.md", "changed\n")
            sync_mod.sync_skills(local, repo)

            result = sync_mod.commit_and_push(repo, "Sync", "origin", push=False)

            self.assertIn("Committed", result)
            log = run(["git", "log", "--oneline", "-1"], cwd=repo).stdout
            self.assertIn("Sync", log)


if __name__ == "__main__":
    unittest.main()
