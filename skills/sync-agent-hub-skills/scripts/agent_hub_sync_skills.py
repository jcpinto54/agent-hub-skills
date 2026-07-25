#!/usr/bin/env python3
"""Sync installed Agent Hub skills into their backing git repository."""

from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_LOCAL_SKILLS_DIR = Path.home() / ".codex" / "skills"
EXPECTED_SKILLS = [
    "dry-mece",
    "manage-agent-hub-issues",
    "init-agent-hub",
    "create-agent-hub-issue",
    "spec-agent-hub-issue",
    "list-agent-hub-issues",
    "claim-agent-hub-issue",
    "iterate-agent-hub-work",
    "run-agent-hub-loop",
    "verify-agent-hub-pr-preview",
    "update-agent-hub-issue",
    "review-agent-hub-issue",
    "review-agent-hub-workspace",
    "sync-agent-hub-skills",
]
LEGACY_SKILL_RENAMES: dict[str, str] = {}
OPTIONAL_UNINSTALLED_SKILLS = {"sync-agent-hub-skills"}
EXCLUDED_DIRS = {"__pycache__", ".git"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".swp", ".tmp"}
EXCLUDED_NAMES = {".DS_Store"}


class SyncError(RuntimeError):
    pass


def run(
    command: list[str],
    cwd: Path | None = None,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise SyncError(f"Command failed: {' '.join(command)}\n{detail}")
    return result


def git(repo_dir: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(["git", "-C", str(repo_dir), *args], check=check)


def is_excluded(path: Path) -> bool:
    return (
        any(part in EXCLUDED_DIRS for part in path.parts)
        or path.name in EXCLUDED_NAMES
        or path.suffix in EXCLUDED_SUFFIXES
        or path.name.endswith("~")
    )


def ensure_repo(repo_dir: Path) -> None:
    if not repo_dir.exists():
        raise SyncError(f"Repo does not exist: {repo_dir}")
    if not (repo_dir / ".git").exists():
        raise SyncError(f"Not a git repo: {repo_dir}")
    if not (repo_dir / "skills").is_dir():
        raise SyncError(f"Repo does not contain skills/: {repo_dir}")

    present = {path.name for path in (repo_dir / "skills").iterdir() if path.is_dir()}
    legacy_present = {
        new for old, new in LEGACY_SKILL_RENAMES.items() if old in present
    }
    known_present = (present & set(EXPECTED_SKILLS)) | legacy_present
    if not known_present:
        raise SyncError(f"Repo does not appear to contain Agent Hub skills: {repo_dir}")


def ensure_clean_repo(repo_dir: Path) -> None:
    status = git(repo_dir, "status", "--porcelain").stdout.strip()
    if status:
        raise SyncError("Repo has uncommitted changes before sync:\n" + status)


def ensure_local_skills(local_skills_dir: Path) -> None:
    if not local_skills_dir.is_dir():
        raise SyncError(f"Local skills dir does not exist: {local_skills_dir}")
    missing = []
    for skill in EXPECTED_SKILLS:
        if skill in OPTIONAL_UNINSTALLED_SKILLS and not (local_skills_dir / skill).exists():
            continue
        if not (local_skills_dir / skill / "SKILL.md").is_file():
            missing.append(skill)
    if missing:
        raise SyncError("Local Agent Hub skills are missing: " + ", ".join(missing))


def tracked_files(repo_dir: Path) -> list[Path]:
    result = git(repo_dir, "ls-files", "skills")
    files = []
    for raw in result.stdout.splitlines():
        if raw:
            files.append(Path(raw))
    return files


def ensure_no_missing_tracked_local_files(repo_dir: Path, local_skills_dir: Path) -> None:
    missing = []
    for relative in tracked_files(repo_dir):
        parts = relative.parts
        if len(parts) < 3 or parts[0] != "skills" or parts[1] not in EXPECTED_SKILLS:
            continue
        skill = parts[1]
        if skill in OPTIONAL_UNINSTALLED_SKILLS and not (local_skills_dir / skill).exists():
            continue
        local_file = local_skills_dir / skill / Path(*parts[2:])
        if not local_file.exists():
            missing.append(str(relative))
    if missing:
        raise SyncError(
            "Tracked repo files are missing locally; refusing to hide drift:\n"
            + "\n".join(missing)
        )


def copy_skill(local_skill: Path, repo_skill: Path) -> None:
    repo_skill.mkdir(parents=True, exist_ok=True)
    for source in local_skill.rglob("*"):
        relative = source.relative_to(local_skill)
        if is_excluded(relative):
            continue
        target = repo_skill / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and filecmp.cmp(source, target, shallow=False):
            continue
        shutil.copy2(source, target)


def sync_skills(local_skills_dir: Path, repo_dir: Path) -> list[str]:
    synced = []
    for old, new in LEGACY_SKILL_RENAMES.items():
        old_repo_skill = repo_dir / "skills" / old
        if old_repo_skill.exists() and (local_skills_dir / new).exists():
            shutil.rmtree(old_repo_skill)
    for skill in EXPECTED_SKILLS:
        local_skill = local_skills_dir / skill
        if skill in OPTIONAL_UNINSTALLED_SKILLS and not local_skill.exists():
            continue
        copy_skill(local_skill, repo_dir / "skills" / skill)
        synced.append(skill)
    return synced


def python_script_paths(repo_dir: Path) -> list[str]:
    scripts = []
    for path in sorted((repo_dir / "skills").glob("*/scripts/*.py")):
        scripts.append(str(path.relative_to(repo_dir)))
    return scripts


def basic_validate_skill_metadata(repo_dir: Path) -> None:
    for skill_dir in sorted((repo_dir / "skills").iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            raise SyncError(f"Missing SKILL.md: {skill_dir}")
        text = skill_md.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            raise SyncError(f"Missing frontmatter: {skill_md}")
        try:
            _, frontmatter, _ = text.split("---", 2)
        except ValueError as exc:
            raise SyncError(f"Malformed frontmatter: {skill_md}") from exc
        fields = {}
        for raw_line in frontmatter.splitlines():
            if ":" not in raw_line:
                continue
            key, value = raw_line.split(":", 1)
            fields[key.strip()] = value.strip().strip("'\"")
        if fields.get("name") != skill_dir.name:
            raise SyncError(f"Skill name mismatch in {skill_md}")
        if not fields.get("description"):
            raise SyncError(f"Missing skill description in {skill_md}")


def quick_validator_available() -> bool:
    return run([sys.executable, "-c", "import yaml"], check=False).returncode == 0


def validate(repo_dir: Path) -> None:
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=repo_dir)

    basic_validate_skill_metadata(repo_dir)

    validator = Path.home() / ".codex" / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py"
    if validator.exists() and quick_validator_available():
        for skill_dir in sorted((repo_dir / "skills").iterdir()):
            if skill_dir.is_dir():
                run([sys.executable, str(validator), str(skill_dir)], cwd=repo_dir)

    scripts = python_script_paths(repo_dir)
    if scripts:
        run([sys.executable, "-m", "py_compile", *scripts], cwd=repo_dir)


def changed_files(repo_dir: Path) -> list[str]:
    result = git(repo_dir, "status", "--porcelain")
    files = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        files.append(line[3:])
    return files


def stage_allowed_paths(repo_dir: Path) -> None:
    paths = [
        path
        for path in ["skills", "tests", "README.md", "pyproject.toml"]
        if (repo_dir / path).exists()
    ]
    if paths:
        git(repo_dir, "add", "--", *paths)


def commit_and_push(repo_dir: Path, message: str, remote: str, push: bool) -> str:
    if not changed_files(repo_dir):
        return "No changes to commit."

    stage_allowed_paths(repo_dir)
    staged = git(repo_dir, "diff", "--cached", "--name-only").stdout.strip()
    if not staged:
        return "No relevant changes to commit."

    git(
        repo_dir,
        "-c",
        "user.name=Agent Hub Sync",
        "-c",
        "user.email=agent-hub-sync@example.invalid",
        "commit",
        "-m",
        message,
    )
    commit = git(repo_dir, "rev-parse", "--short", "HEAD").stdout.strip()
    if push:
        branch = git(repo_dir, "branch", "--show-current").stdout.strip()
        if not branch:
            raise SyncError("Cannot push from detached HEAD")
        git(repo_dir, "push", remote, branch)
        return f"Committed {commit} and pushed to {remote}/{branch}."
    return f"Committed {commit}. Push skipped."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-dir", required=True, type=Path, help="Discovered Agent Hub skills repo")
    parser.add_argument("--local-skills-dir", type=Path, default=DEFAULT_LOCAL_SKILLS_DIR)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--commit-message", default="Sync Agent Hub skills")
    parser.add_argument("--no-push", action="store_true", help="Commit locally without pushing")
    parser.add_argument("--skip-validate", action="store_true", help="Skip validation checks")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_dir = args.repo_dir.expanduser().resolve()
    local_skills_dir = args.local_skills_dir.expanduser().resolve()

    try:
        ensure_repo(repo_dir)
        ensure_clean_repo(repo_dir)
        ensure_local_skills(local_skills_dir)
        ensure_no_missing_tracked_local_files(repo_dir, local_skills_dir)
        synced = sync_skills(local_skills_dir, repo_dir)
        if not args.skip_validate:
            validate(repo_dir)
        result = commit_and_push(
            repo_dir,
            args.commit_message,
            args.remote,
            push=not args.no_push,
        )
    except SyncError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print("Synced skills: " + ", ".join(synced))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
