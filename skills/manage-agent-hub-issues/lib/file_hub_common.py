#!/usr/bin/env python3
"""Repo-native Agent Hub helpers for .hub issue files."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from agent_hub_common import PRIORITY_ORDER, STATUS_ORDER, find_repo_root, is_unassigned


HUB_DIR_NAME = ".hub"
CONFIG_NAME = "config.yml"
RUNTIME_DIR = "runtime"
CLAIMS_NAME = "claims.json"
ISSUES_DIR = "issues"
DECISIONS_DIR = "decisions"
ARTIFACTS_DIR = "artifacts"
PROJECT_DIR = "project"
CHANGES_DIR = "changes"
REPORTS_DIR = "reports"
STATE_NAME = "state.yml"
AGENT_HUB_HOME_ENV = "AGENT_HUB_HOME"
DEFAULT_AGENT_HUB_HOME = ".agents-hub"
CENTRAL_PROJECTS_DIR = "projects"
CENTRAL_HUB_DIR = "hub"
PROJECT_METADATA_NAME = "project.json"
ISSUE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
CHANGE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

PROJECT_TEMPLATES = {
    "principles.md": """# Principles

## Quality Bar

## TDD And Regression Policy

## Review Rules

## Security And Safety

## Non-Negotiables

## Tradeoffs
""",
    "product.md": """# Product

## Purpose

## Users

## Outcomes

## Non-Goals

## Success Signals
""",
    "tech.md": """# Tech

## Stack

## Package Manager

## Test Commands

## Environment Notes
""",
    "structure.md": """# Structure

## Repo Map

## Boundaries

## Entry Points

## Extension Points

## Areas To Avoid
""",
    "standards-index.md": """# Standards Index

## When To Read

## Standards
""",
    "delegation.md": """# Delegation Rules

The main agent is an orchestrator, not an executor.

## Main Agent Responsibilities

## Subagent Responsibilities

## Handoff Contract

## Evidence Requirements

## Stop Conditions

## Exceptions
""",
}

CHANGE_TEMPLATES = {
    "proposal.md": """# Proposal

## Why

## What Changes

## Out Of Scope
""",
    "shape.md": """# Shape

## User Intent

## Constraints
""",
    "design.md": """# Design

## Approach

## Data Flow

## Interfaces
""",
    "tasks.md": """# Tasks

## Dependency Graph

## Issues
""",
    "checklist.md": """# Checklist

## Spec Quality

## TDD Readiness
""",
    "evidence.md": """# Evidence

## Test Runs

## Notes
""",
    "review.md": """# Review

## Review Status

## Findings
""",
}

SPEC_SECTION_HEADINGS = [
    "## Context",
    "## Scope",
    "## Out Of Scope",
    "## Done Criteria",
    "## Verification Strategy",
    "## Assumptions",
    "## Dependencies",
    "## Open Questions",
]

SPEC_DIAGNOSTIC_CODES = {
    "implementation_missing_first_test",
    "implementation_missing_final_verification",
    "issue_scope_too_vague",
    "issue_out_of_scope_too_vague",
    "issue_done_criteria_not_observable",
}

DASHBOARD_COLUMNS = [
    ("needs-spec", "Needs Spec"),
    ("ready", "Ready"),
    ("in-progress", "In Progress"),
    ("in-review", "In Review"),
    ("completed", "Completed"),
    ("blocked", "Blocked"),
]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(value: datetime | None) -> str:
    return value.isoformat().replace("+00:00", "Z") if value else ""


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def agent_hub_home() -> Path:
    configured = os.environ.get(AGENT_HUB_HOME_ENV)
    return (
        Path(configured).expanduser().resolve()
        if configured
        else Path.home() / DEFAULT_AGENT_HUB_HOME
    )


def git_common_dir(start: Path | None = None) -> Path:
    root = find_repo_root(start)
    if not root:
        return (start or Path.cwd()).expanduser().resolve()
    result = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        common = Path(result.stdout.strip())
        if not common.is_absolute():
            common = root / common
        return common.resolve()
    return (root / ".git").resolve()


def central_project_id(start: Path | None = None) -> str:
    common = git_common_dir(start)
    return hashlib.sha256(str(common).encode("utf-8")).hexdigest()[:24]


def central_project_path(start: Path | None = None) -> Path:
    return agent_hub_home() / CENTRAL_PROJECTS_DIR / central_project_id(start)


def central_hub_path(start: Path | None = None) -> Path:
    return central_project_path(start) / CENTRAL_HUB_DIR


def legacy_repo_hub_path(start: Path | None = None) -> Path | None:
    root = find_repo_root(start)
    if not root:
        return None
    hub = root / HUB_DIR_NAME
    return hub if (hub / CONFIG_NAME).exists() else None


def write_central_project_metadata(start: Path, hub: Path) -> None:
    root = find_repo_root(start) or start.expanduser().resolve()
    common = git_common_dir(root)
    project = hub.parent
    metadata_path = project / PROJECT_METADATA_NAME
    worktree = str(root)
    existing: dict[str, Any] = {}
    if metadata_path.exists():
        try:
            loaded = json.loads(metadata_path.read_text(encoding="utf-8") or "{}")
            if isinstance(loaded, dict):
                existing = loaded
        except json.JSONDecodeError:
            existing = {}
    worktrees = sorted({*normalize_list(existing.get("worktrees")), worktree})
    metadata = {
        "version": 1,
        "project_id": project.name,
        "git_common_dir": str(common),
        "hub": str(hub),
        "worktrees": worktrees,
        "legacy_hub": str(root / HUB_DIR_NAME),
        "legacy_hub_exists": (root / HUB_DIR_NAME / CONFIG_NAME).exists(),
    }
    comparable_existing = {key: existing.get(key) for key in metadata}
    if comparable_existing == metadata:
        return
    metadata["updated_at"] = isoformat(now_utc())
    atomic_write(metadata_path, json.dumps(metadata, indent=2, sort_keys=True) + "\n")


def repo_hub_path(start: Path | None = None) -> Path | None:
    hub = central_hub_path(start)
    return hub if (hub / CONFIG_NAME).exists() else None


def resolve_hub_path(start: Path | None = None, hub_root: Path | None = None) -> Path:
    if hub_root:
        return hub_root.expanduser().resolve()
    hub = repo_hub_path(start)
    if not hub:
        legacy = legacy_repo_hub_path(start)
        if legacy:
            raise RuntimeError(
                "No central Agent Hub found. Run `agent-hub migrate` to import legacy .hub state."
            )
        raise RuntimeError("No central Agent Hub found. Run `agent-hub init`.")
    write_central_project_metadata((start or Path.cwd()).expanduser().resolve(), hub)
    return hub


def has_file_hub(start: Path | None = None, hub_root: Path | None = None) -> bool:
    try:
        return (resolve_hub_path(start, hub_root) / CONFIG_NAME).exists()
    except RuntimeError:
        return False


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "issue"


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"", "null", "None"}:
        return "" if value == "" else None
    if value in {"[]", "{}"}:
        return [] if value == "[]" else {}
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith(('"', "'")):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value.strip("'\"")
    if value.startswith("[") or value.startswith("{"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    raw = text[4:end].splitlines()
    body = text[end + 5 :]
    data: dict[str, Any] = {}
    current_key: str | None = None
    for line in raw:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" ") and ":" in line:
            key, value = line.split(":", 1)
            current_key = key.strip()
            value = value.strip()
            data[current_key] = parse_scalar(value) if value else {}
            continue
        if current_key and line.startswith("  ") and ":" in line:
            if not isinstance(data.get(current_key), dict):
                data[current_key] = {}
            key, value = line.strip().split(":", 1)
            data[current_key][key.strip()] = parse_scalar(value)
            continue
        if current_key and line.startswith("  - "):
            if not isinstance(data.get(current_key), list):
                data[current_key] = []
            data[current_key].append(parse_scalar(line[4:]))
    return data, body


def format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True)
    return json.dumps(str(value))


def dump_frontmatter(data: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in data.items():
        if isinstance(value, dict):
            if not value:
                lines.append(f"{key}: {{}}")
            else:
                lines.append(f"{key}:")
                for sub_key, sub_value in value.items():
                    lines.append(f"  {sub_key}: {format_scalar(sub_value)}")
        else:
            lines.append(f"{key}: {format_scalar(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def format_yamlish_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        if value == "":
            return '""'
        if re.fullmatch(r"[A-Za-z0-9_./:-]+", value):
            return value
        return json.dumps(value)
    return json.dumps(value, sort_keys=True)


def dump_yamlish(data: dict[str, Any], indent: int = 0) -> str:
    lines: list[str] = []
    prefix = " " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            if not value:
                lines.append(f"{prefix}{key}: {{}}")
            else:
                lines.append(f"{prefix}{key}:")
                lines.append(dump_yamlish(value, indent + 2).rstrip())
        elif isinstance(value, list):
            if not value:
                lines.append(f"{prefix}{key}: []")
            else:
                lines.append(f"{prefix}{key}:")
                for item in value:
                    if isinstance(item, dict):
                        lines.append(f"{prefix}  -")
                        lines.append(dump_yamlish(item, indent + 4).rstrip())
                    else:
                        lines.append(f"{prefix}  - {format_yamlish_scalar(item)}")
        else:
            lines.append(f"{prefix}{key}: {format_yamlish_scalar(value)}")
    return "\n".join(lines) + "\n"


def load_yamlish(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    data, _ = parse_frontmatter(f"---\n{text.rstrip()}\n---\n")
    return data


def write_yamlish(path: Path, data: dict[str, Any]) -> None:
    atomic_write(path, dump_yamlish(data))


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(text)
        temp_name = handle.name
    Path(temp_name).replace(path)


def normalize_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def validate_issue_id(issue_id: str | None, field_name: str = "issue id") -> str:
    value = str(issue_id or "")
    if not value:
        raise RuntimeError(f"Invalid {field_name}: value is required.")
    if Path(value).is_absolute() or "/" in value or "\\" in value:
        raise RuntimeError(
            f"Invalid {field_name}: issue IDs must not be paths or contain separators."
        )
    if value in {".", ".."} or ".." in Path(value).parts:
        raise RuntimeError(f"Invalid {field_name}: traversal segments are not allowed.")
    if not ISSUE_ID_RE.fullmatch(value):
        raise RuntimeError(
            f"Invalid {field_name}: use lowercase letters, numbers, and hyphens."
        )
    return value


def validate_change_slug(change_slug: str | None, field_name: str = "change slug") -> str:
    value = str(change_slug or "")
    if not value:
        raise RuntimeError(f"Invalid {field_name}: value is required.")
    if Path(value).is_absolute() or "/" in value or "\\" in value:
        raise RuntimeError(
            f"Invalid {field_name}: change slugs must not be paths or contain separators."
        )
    if value in {".", ".."} or ".." in Path(value).parts:
        raise RuntimeError(f"Invalid {field_name}: traversal segments are not allowed.")
    if not CHANGE_SLUG_RE.fullmatch(value):
        raise RuntimeError(
            f"Invalid {field_name}: use lowercase letters, numbers, and hyphens."
        )
    return value


def issue_path_for_id(hub_path: Path, issue_id: str) -> Path:
    safe_id = validate_issue_id(issue_id)
    issues_dir = (hub_path / ISSUES_DIR).resolve()
    path = (issues_dir / f"{safe_id}.md").resolve()
    if path.parent != issues_dir:
        raise RuntimeError("Issue file paths must stay directly inside .hub/issues.")
    return path


@dataclass
class FileHubIssue:
    id: str
    path: Path
    body: str
    title: str = ""
    status: str = "Not Started"
    owner: str = "Unassigned"
    priority: str = "P2"
    type: str = "Feature"
    area: str = ""
    summary: str = ""
    blockers: str = ""
    dependency_notes: str = ""
    change: str = ""
    depends_on: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    claim: dict[str, Any] = field(default_factory=dict)
    base_branch: str = ""
    branch: str = ""
    worktree_path: str = ""
    commit_sha: str = ""
    pr_url: str = ""
    related_links: str = ""
    external_url: str = ""
    updated_at: datetime | None = None
    extra_frontmatter: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_path(cls, path: Path) -> "FileHubIssue":
        data, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        stat = path.stat()
        issue_id = str(data.get("id") or path.stem)
        known_keys = {
            "id",
            "title",
            "status",
            "type",
            "priority",
            "owner",
            "area",
            "summary",
            "blockers",
            "dependency_notes",
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
            "external_url",
        }
        return cls(
            id=issue_id,
            path=path,
            body=body,
            title=str(data.get("title") or issue_id),
            status=str(data.get("status") or "Not Started"),
            owner=str(data.get("owner") or "Unassigned"),
            priority=str(data.get("priority") or "P2"),
            type=str(data.get("type") or "Feature"),
            area=str(data.get("area") or ""),
            summary=str(data.get("summary") or ""),
            blockers=str(data.get("blockers") or ""),
            dependency_notes=str(data.get("dependency_notes") or ""),
            change=str(data.get("change") or ""),
            depends_on=normalize_list(data.get("depends_on")),
            blocks=normalize_list(data.get("blocks")),
            claim=data.get("claim") if isinstance(data.get("claim"), dict) else {},
            base_branch=str(data.get("base_branch") or ""),
            branch=str(data.get("branch") or ""),
            worktree_path=str(data.get("worktree_path") or ""),
            commit_sha=str(data.get("commit_sha") or ""),
            pr_url=str(data.get("pr_url") or ""),
            related_links=str(data.get("related_links") or ""),
            external_url=str(data.get("external_url") or ""),
            updated_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc),
            extra_frontmatter={
                key: value for key, value in data.items() if key not in known_keys
            },
        )

    @property
    def url(self) -> str:
        return str(self.path)

    @property
    def claim_id(self) -> str:
        return str(self.claim.get("id") or "")

    @property
    def claim_expires_at(self) -> datetime | None:
        return parse_datetime(self.claim.get("expires_at"))

    def to_frontmatter(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "type": self.type,
            "priority": self.priority,
            "owner": self.owner,
            "area": self.area,
            "summary": self.summary,
            "blockers": self.blockers,
            "dependency_notes": self.dependency_notes,
            "change": self.change,
            "depends_on": self.depends_on,
            "blocks": self.blocks,
            "claim": self.claim,
            "base_branch": self.base_branch,
            "branch": self.branch,
            "worktree_path": self.worktree_path,
            "commit_sha": self.commit_sha,
            "pr_url": self.pr_url,
            "related_links": self.related_links,
            "external_url": self.external_url,
        }

    def write(self) -> None:
        frontmatter = self.to_frontmatter()
        if self.path.exists():
            existing, _ = parse_frontmatter(self.path.read_text(encoding="utf-8"))
            for key, value in existing.items():
                if key not in frontmatter:
                    frontmatter[key] = value
        for key, value in self.extra_frontmatter.items():
            if key not in frontmatter:
                frontmatter[key] = value
        atomic_write(self.path, dump_frontmatter(frontmatter) + self.body.lstrip("\n"))

    def append_activity(self, heading: str, lines: list[str]) -> None:
        body = self.body.rstrip() + "\n\n"
        body += f"### {heading}\n"
        body += "\n".join(lines).rstrip() + "\n"
        self.body = body
        self.write()


def load_config(hub_path: Path) -> dict[str, Any]:
    config_path = hub_path / CONFIG_NAME
    if not config_path.exists():
        return {}
    data, body = parse_frontmatter("---\n" + config_path.read_text(encoding="utf-8") + "\n---\n")
    return data or {"raw": body}


def load_issues(hub_path: Path) -> list[FileHubIssue]:
    issues_dir = hub_path / ISSUES_DIR
    if not issues_dir.exists():
        return []
    return [FileHubIssue.from_path(path) for path in sorted(issues_dir.glob("*.md"))]


def issue_by_id(hub_path: Path, issue_id_or_path: str) -> FileHubIssue:
    issue_id = validate_issue_id(issue_id_or_path)
    path = issue_path_for_id(hub_path, issue_id)
    if path.exists():
        return FileHubIssue.from_path(path)
    issues = load_issues(hub_path)
    by_id = {issue.id: issue for issue in issues}
    if issue_id in by_id:
        return by_id[issue_id]
    for issue in issues:
        if issue.path.stem == issue_id:
            return issue
    raise RuntimeError(f"No .hub issue found for {issue_id!r}.")


def active_claim(issue: FileHubIssue, runtime_claim: dict[str, Any] | None = None) -> bool:
    claim = runtime_claim or issue.claim
    claim_id = str(claim.get("id") or "")
    if not claim_id:
        return False
    expires_at = parse_datetime(claim.get("expires_at"))
    if not expires_at:
        return True
    return expires_at > now_utc()


def readiness(issue: FileHubIssue, by_id: dict[str, FileHubIssue]) -> tuple[str, str]:
    if issue.status == "In Review":
        reasons: list[str] = []
        if issue.owner and not is_unassigned(issue.owner):
            reasons.append(f"owned by {issue.owner}")
        if active_claim(issue):
            reasons.append("active claim")
        if reasons:
            return "Blocked", "; ".join(reasons)
        return "Ready", "ready for review"
    if issue.status != "Not Started":
        return "-", ""
    reasons: list[str] = []
    if issue.owner and not is_unassigned(issue.owner):
        reasons.append(f"owned by {issue.owner}")
    if issue.blockers:
        reasons.append("external blocker")
    if active_claim(issue):
        reasons.append("active claim")
    unknown_deps: list[str] = []
    incomplete_deps: list[str] = []
    for dep_id in issue.depends_on:
        dep = by_id.get(dep_id)
        if not dep:
            unknown_deps.append(dep_id)
        elif dep.status != "Completed":
            incomplete_deps.append(dep.title)
    if unknown_deps:
        return "Unknown", "dependency status unavailable"
    if incomplete_deps:
        reasons.append("waiting on " + ", ".join(incomplete_deps))
    if reasons:
        return "Blocked", "; ".join(reasons)
    return "Ready", ""


def issue_sort_key(issue: FileHubIssue) -> tuple[int, int, float]:
    status_index = (
        STATUS_ORDER.index(issue.status) if issue.status in STATUS_ORDER else len(STATUS_ORDER)
    )
    priority_index = PRIORITY_ORDER.get(issue.priority, 99)
    updated = issue.updated_at.timestamp() if issue.updated_at else 0
    return (status_index, priority_index, -updated)


def runtime_claims_path(hub_path: Path) -> Path:
    return hub_path / RUNTIME_DIR / CLAIMS_NAME


def load_runtime_claims(hub_path: Path) -> dict[str, Any]:
    path = runtime_claims_path(hub_path)
    if not path.exists():
        return {}
    try:
        claims = json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Malformed runtime claims file {path}: {exc}") from exc
    if not isinstance(claims, dict):
        raise RuntimeError(f"Malformed runtime claims file {path}: expected a JSON object.")
    return claims


def write_runtime_claims(hub_path: Path, claims: dict[str, Any]) -> None:
    path = runtime_claims_path(hub_path)
    atomic_write(path, json.dumps(claims, indent=2, sort_keys=True) + "\n")


def current_runtime_claim(hub_path: Path, issue_id: str) -> dict[str, Any] | None:
    claim = load_runtime_claims(hub_path).get(issue_id)
    if isinstance(claim, dict) and active_claim_placeholder(claim):
        return claim
    return None


def active_claim_placeholder(claim: dict[str, Any]) -> bool:
    if not claim.get("id"):
        return False
    expires_at = parse_datetime(claim.get("expires_at"))
    return True if not expires_at else expires_at > now_utc()


def dependency_failures(issue: FileHubIssue, by_id: dict[str, FileHubIssue]) -> list[str]:
    failures: list[str] = []
    for dep_id in issue.depends_on:
        dep = by_id.get(dep_id)
        if not dep or dep.status != "Completed":
            failures.append(f"{dep_id} ({dep.status if dep else 'unknown'})")
    return failures


def has_waiver(issue: FileHubIssue) -> bool:
    text = issue.dependency_notes.lower()
    return "waive" in text or "override" in text


def create_hub_layout(hub: Path, project_name: str | None = None) -> Path:
    hub = hub.expanduser().resolve()
    (hub / PROJECT_DIR).mkdir(parents=True, exist_ok=True)
    (hub / CHANGES_DIR).mkdir(parents=True, exist_ok=True)
    (hub / ISSUES_DIR).mkdir(parents=True, exist_ok=True)
    (hub / DECISIONS_DIR).mkdir(parents=True, exist_ok=True)
    (hub / REPORTS_DIR).mkdir(parents=True, exist_ok=True)
    (hub / ARTIFACTS_DIR).mkdir(parents=True, exist_ok=True)
    (hub / RUNTIME_DIR).mkdir(parents=True, exist_ok=True)
    if not (hub / ".gitignore").exists():
        (hub / ".gitignore").write_text("runtime/\n", encoding="utf-8")
    if not (hub / CONFIG_NAME).exists():
        name = project_name or hub.parent.name
        config = {
            "version": 3,
            "source_of_truth": "file",
            "project": name,
            "canonical_store": "file",
            "external_mirror": {
                "enabled": False,
                "data_source_id": "",
                "page_url": "",
            },
            "cli": {
                "strict_writes": True,
                "preserve_unknown_frontmatter": True,
            },
            "agents": {
                "enabled": False,
                "require_subagent_for_tasks": True,
            },
            "audit": {
                "tdd_required_for_implementation": True,
                "stale_claim_minutes": 120,
            },
            "dashboard": {
                "enabled": False,
                "mode": "read-only",
            },
        }
        write_yamlish(hub / CONFIG_NAME, config)
    if not (hub / STATE_NAME).exists():
        write_yamlish(
            hub / STATE_NAME,
            {"version": 3, "updated_at": isoformat(now_utc()), "issues": {}, "changes": {}},
        )
    for filename, text in PROJECT_TEMPLATES.items():
        path = hub / PROJECT_DIR / filename
        if not path.exists():
            atomic_write(path, text.rstrip() + "\n")
    return hub


def create_hub(root: Path, project_name: str | None = None) -> Path:
    root = root.expanduser().resolve()
    return create_hub_layout(root / HUB_DIR_NAME, project_name or root.name)


def create_central_hub(root: Path, project_name: str | None = None) -> Path:
    root = root.expanduser().resolve()
    repo_root = find_repo_root(root) or root
    if legacy_repo_hub_path(repo_root) and not (central_hub_path(repo_root) / CONFIG_NAME).exists():
        raise RuntimeError(
            "Legacy .hub/config.yml exists. Run `agent-hub migrate` to import it before init."
        )
    hub = create_hub_layout(central_hub_path(repo_root), project_name or repo_root.name)
    write_central_project_metadata(repo_root, hub)
    return hub


def migrate_legacy_hub(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    repo_root = find_repo_root(root) or root
    legacy = legacy_repo_hub_path(repo_root)
    if not legacy:
        raise RuntimeError(f"No legacy .hub/config.yml found for migration: {repo_root}")
    hub = central_hub_path(repo_root)
    if hub.exists():
        if (hub / CONFIG_NAME).exists():
            raise RuntimeError(f"Central Agent Hub already exists: {hub}")
        if any(hub.iterdir()):
            raise RuntimeError(f"Central Agent Hub path is not empty: {hub}")
        hub.rmdir()
    shutil.copytree(legacy, hub)
    write_central_project_metadata(repo_root, hub)
    return {
        "ok": True,
        "hub": str(hub),
        "legacy_hub": str(legacy),
        "project_id": hub.parent.name,
    }


def create_issue_file(
    hub_path: Path,
    title: str,
    issue_id: str | None = None,
    issue_type: str = "Feature",
    priority: str = "P2",
    change: str = "",
) -> FileHubIssue:
    issue_id = validate_issue_id(issue_id or slugify(title))
    if change:
        change = validate_change_slug(change)
        if not change_yml_path(hub_path, change).exists():
            raise RuntimeError(f"No change packet found for {change!r}.")
    path = issue_path_for_id(hub_path, issue_id)
    if path.exists():
        raise RuntimeError(f"Issue already exists: {path}")
    issue = FileHubIssue(
        id=issue_id,
        path=path,
        title=title,
        type=issue_type,
        priority=priority,
        change=change,
        body="""## Context

## Scope

## Out Of Scope

## Done Criteria

- [ ]

## Verification Strategy

### Regression Target

### Test Plan

- [ ] Unit:
- [ ] Integration:
- [ ] E2E / Playwright:
- [ ] Manual / inspection:

### First Test

Path:
Expected initial result:
Reason this proves the regression or requirement:

### Final Verification

Commands:
Expected result:

### Untestable Surface

## Assumptions

## Dependencies

## Open Questions

## Activity Log
""",
    )
    issue.write()
    return issue


def claim_issue(
    hub_path: Path,
    issue: FileHubIssue,
    purpose: str,
    owner: str,
    ttl_minutes: int,
    claim_id: str,
    base_branch: str = "",
    branch: str = "",
    worktree_path: str = "",
    allow_missing_artifacts: bool = False,
) -> dict[str, Any]:
    issues = load_issues(hub_path)
    by_id = {item.id: item for item in issues}
    runtime_claim = current_runtime_claim(hub_path, issue.id)
    if runtime_claim:
        raise RuntimeError(
            f"Refusing claim: active runtime claim {runtime_claim.get('id')}."
        )
    if active_claim(issue):
        raise RuntimeError(f"Refusing claim: active issue claim {issue.claim_id}.")
    failures = dependency_failures(issue, by_id)
    if purpose == "work":
        if issue.status != "Not Started":
            raise RuntimeError(f"Refusing work claim: status is {issue.status!r}.")
        if issue.owner and not is_unassigned(issue.owner):
            raise RuntimeError(f"Refusing work claim: owner is already {issue.owner!r}.")
        if issue.blockers:
            raise RuntimeError(f"Refusing work claim: Blockers is not empty: {issue.blockers}")
        if failures:
            raise RuntimeError(
                "Refusing work claim: dependencies are not completed: " + ", ".join(failures)
            )
        issue.status = "In Progress"
    else:
        if issue.status != "In Review":
            raise RuntimeError(f"Refusing review claim: status is {issue.status!r}.")
        if failures and not has_waiver(issue):
            raise RuntimeError(
                "Refusing review claim: prerequisites incomplete: " + ", ".join(failures)
            )
        if not allow_missing_artifacts and not (
            issue.pr_url or issue.commit_sha or issue.related_links
        ):
            raise RuntimeError(
                "Refusing review claim: issue lacks PR URL, Commit SHA, or Related Links evidence."
            )
    claimed_at = now_utc()
    expires_at = claimed_at + timedelta(minutes=ttl_minutes)
    claim = {
        "id": claim_id,
        "purpose": purpose,
        "owner": owner,
        "claimed_at": isoformat(claimed_at),
        "expires_at": isoformat(expires_at),
        "machine": socket.gethostname(),
    }
    issue.owner = owner
    issue.claim = claim
    issue.base_branch = base_branch or issue.base_branch
    issue.branch = branch or issue.branch
    issue.worktree_path = worktree_path or issue.worktree_path
    claims = load_runtime_claims(hub_path)
    claims[issue.id] = claim
    write_runtime_claims(hub_path, claims)
    issue.append_activity(
        f"Claimed for {purpose}",
        [
            f"Date: {isoformat(claimed_at)}",
            f"Agent: {owner}",
            f"Claim ID: {claim_id}",
            f"Branch: {issue.branch or '-'}",
            f"Worktree Path: {issue.worktree_path or '-'}",
        ],
    )
    refetched = issue_by_id(hub_path, issue.id)
    runtime_refetched = current_runtime_claim(hub_path, issue.id) or {}
    if refetched.claim_id != claim_id or runtime_refetched.get("id") != claim_id:
        raise RuntimeError("Optimistic file claim verification failed.")
    return {
        "ok": True,
        "action": "claim",
        "purpose": purpose,
        "page_id": refetched.id,
        "title": refetched.title,
        "status": refetched.status,
        "owner": refetched.owner,
        "claim_id": refetched.claim_id,
        "claim_expires_at": isoformat(refetched.claim_expires_at),
        "backend": "file",
    }


def check_issue(hub_path: Path, issue: FileHubIssue, claim_id: str = "") -> dict[str, Any]:
    runtime_claim = current_runtime_claim(hub_path, issue.id)
    active = active_claim(issue, runtime_claim)
    current_id = str((runtime_claim or issue.claim).get("id") or "")
    if claim_id and current_id != claim_id:
        raise RuntimeError(f"Claim mismatch: issue has {current_id!r}, got {claim_id!r}.")
    return {
        "ok": True,
        "action": "check",
        "page_id": issue.id,
        "title": issue.title,
        "status": issue.status,
        "owner": issue.owner,
        "claim_id": current_id,
        "active": active,
        "claim_expires_at": str((runtime_claim or issue.claim).get("expires_at") or ""),
        "backend": "file",
    }


def renew_issue(
    hub_path: Path, issue: FileHubIssue, claim_id: str, ttl_minutes: int
) -> dict[str, Any]:
    check_issue(hub_path, issue, claim_id)
    expires_at = now_utc() + timedelta(minutes=ttl_minutes)
    issue.claim["expires_at"] = isoformat(expires_at)
    claims = load_runtime_claims(hub_path)
    claims.setdefault(issue.id, issue.claim)
    claims[issue.id]["expires_at"] = isoformat(expires_at)
    write_runtime_claims(hub_path, claims)
    issue.write()
    return {
        "ok": True,
        "action": "renew",
        "page_id": issue.id,
        "claim_id": claim_id,
        "claim_expires_at": isoformat(expires_at),
        "backend": "file",
    }


def release_issue(
    hub_path: Path,
    issue: FileHubIssue,
    claim_id: str,
    mode: str,
    owner: str = "",
    blocker: str = "",
    commit_sha: str = "",
    pr_url: str = "",
) -> dict[str, Any]:
    check_issue(hub_path, issue, claim_id)
    if mode in {"abandon", "handoff", "blocked", "submitted"} and issue.status != "In Progress":
        raise RuntimeError(
            f"Refusing work release from status {issue.status!r}; expected 'In Progress'."
        )
    if mode in {"review-pass", "review-fail", "review-abandon"} and issue.status != "In Review":
        raise RuntimeError(
            f"Refusing review release from status {issue.status!r}; expected 'In Review'."
        )
    if mode == "abandon":
        repo_work_exists = bool(issue.commit_sha or issue.pr_url or issue.branch)
        issue.status = "In Progress" if repo_work_exists else "Not Started"
        issue.owner = owner or ("Unassigned" if not repo_work_exists else issue.owner)
    elif mode == "handoff":
        issue.status = "In Progress"
        issue.owner = owner or "Unassigned"
    elif mode == "blocked":
        issue.status = "In Progress"
        issue.blockers = blocker or issue.blockers
        if owner:
            issue.owner = owner
    elif mode == "submitted":
        if not issue.pr_url and not pr_url:
            raise RuntimeError("Refusing submitted release: PR URL is required.")
        issue.status = "In Review"
        issue.owner = owner or "Unassigned"
        issue.commit_sha = commit_sha or issue.commit_sha
        issue.pr_url = pr_url or issue.pr_url
    elif mode == "review-pass":
        issue.status = "Completed"
        issue.owner = owner or issue.owner
    elif mode == "review-fail":
        issue.status = "In Progress"
        issue.owner = owner or "Unassigned"
    elif mode == "review-abandon":
        issue.status = "In Review"
        issue.owner = owner or "Unassigned"
    else:
        raise RuntimeError(f"Unsupported release mode: {mode}")
    claims = load_runtime_claims(hub_path)
    claims.pop(issue.id, None)
    write_runtime_claims(hub_path, claims)
    issue.claim = {}
    issue.append_activity(
        f"Released claim ({mode})",
        [
            f"Date: {isoformat(now_utc())}",
            f"Claim ID: {claim_id}",
            f"Mode: {mode}",
            f"Status: {issue.status}",
            f"Owner: {issue.owner}",
        ],
    )
    refetched = issue_by_id(hub_path, issue.id)
    if current_runtime_claim(hub_path, issue.id) or refetched.claim_id:
        raise RuntimeError("Release verification failed: claim still present.")
    return {
        "ok": True,
        "action": "release",
        "mode": mode,
        "page_id": refetched.id,
        "title": refetched.title,
        "status": refetched.status,
        "owner": refetched.owner,
        "claim_id": refetched.claim_id,
        "backend": "file",
    }


def change_dir(hub_path: Path, change_slug: str) -> Path:
    return hub_path / CHANGES_DIR / validate_change_slug(change_slug)


def change_yml_path(hub_path: Path, change_slug: str) -> Path:
    return change_dir(hub_path, change_slug) / "change.yml"


def load_change(hub_path: Path, change_slug: str) -> dict[str, Any]:
    path = change_yml_path(hub_path, change_slug)
    if not path.exists():
        raise RuntimeError(f"No change packet found for {change_slug!r}.")
    return load_yamlish(path)


def write_change(hub_path: Path, change_slug: str, data: dict[str, Any]) -> None:
    write_yamlish(change_yml_path(hub_path, change_slug), data)


def create_change_packet(
    hub_path: Path,
    slug: str,
    title: str,
    priority: str = "P2",
    owner: str = "Unassigned",
    status: str = "Draft",
) -> Path:
    slug = validate_change_slug(slugify(slug))
    target_dir = change_dir(hub_path, slug)
    if target_dir.exists() and (target_dir / "change.yml").exists():
        raise RuntimeError(f"Change packet already exists: {target_dir}")
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = isoformat(now_utc())
    write_yamlish(
        target_dir / "change.yml",
        {
            "id": slug,
            "title": title,
            "status": status,
            "priority": priority,
            "owner": owner,
            "issues": [],
            "depends_on": [],
            "blocks": [],
            "created_at": timestamp,
            "updated_at": timestamp,
        },
    )
    for filename, text in CHANGE_TEMPLATES.items():
        path = target_dir / filename
        if not path.exists():
            atomic_write(path, text.rstrip() + "\n")
    return target_dir


def unique_append(values: list[str], value: str) -> list[str]:
    return values if value in values else [*values, value]


def remove_value(values: list[str], value: str) -> list[str]:
    return [item for item in values if item != value]


def link_issue_to_change(hub_path: Path, change_slug: str, issue_id: str) -> dict[str, Any]:
    issue = issue_by_id(hub_path, issue_id)
    change = load_change(hub_path, change_slug)
    issues = normalize_list(change.get("issues"))
    change["issues"] = unique_append(issues, issue.id)
    change["updated_at"] = isoformat(now_utc())
    write_change(hub_path, change_slug, change)

    issue.change = change_slug
    issue.write()

    tasks_path = change_dir(hub_path, change_slug) / "tasks.md"
    tasks_text = tasks_path.read_text(encoding="utf-8") if tasks_path.exists() else CHANGE_TEMPLATES["tasks.md"]
    if issue.id not in extract_task_issue_ids(tasks_text):
        tasks_text = tasks_text.rstrip() + f"\n\n- [ ] {issue.id} - {issue.title}\n"
        atomic_write(tasks_path, tasks_text)
    return {"ok": True, "change": change_slug, "issue": issue.id}


def unlink_issue_from_change(hub_path: Path, change_slug: str, issue_id: str) -> dict[str, Any]:
    issue = issue_by_id(hub_path, issue_id)
    change = load_change(hub_path, change_slug)
    previous_issues = normalize_list(change.get("issues"))
    change["issues"] = remove_value(previous_issues, issue.id)
    change["updated_at"] = isoformat(now_utc())
    write_change(hub_path, change_slug, change)

    previous_change = issue.change
    if issue.change == change_slug:
        issue.change = ""
        issue.write()

    tasks_path = change_dir(hub_path, change_slug) / "tasks.md"
    removed_task = False
    if tasks_path.exists():
        tasks_text = tasks_path.read_text(encoding="utf-8")
        updated_tasks = remove_task_issue(tasks_text, issue.id)
        removed_task = updated_tasks != tasks_text
        if removed_task:
            atomic_write(tasks_path, updated_tasks)

    return {
        "ok": True,
        "change": change_slug,
        "issue": issue.id,
        "previous_change": previous_change,
        "removed_from_change": issue.id in previous_issues,
        "cleared_issue_change": previous_change == change_slug,
        "removed_task": removed_task,
    }


def add_issue_dependency(hub_path: Path, issue_id: str, depends_on: str) -> dict[str, Any]:
    issue = issue_by_id(hub_path, issue_id)
    provider = issue_by_id(hub_path, depends_on)
    issue.depends_on = unique_append(issue.depends_on, provider.id)
    provider.blocks = unique_append(provider.blocks, issue.id)
    issue.write()
    provider.write()
    return {"ok": True, "issue": issue.id, "depends_on": provider.id}


def remove_issue_dependency(hub_path: Path, issue_id: str, depends_on: str) -> dict[str, Any]:
    issue = issue_by_id(hub_path, issue_id)
    provider = issue_by_id(hub_path, depends_on)
    issue.depends_on = remove_value(issue.depends_on, provider.id)
    provider.blocks = remove_value(provider.blocks, issue.id)
    issue.write()
    provider.write()
    return {"ok": True, "issue": issue.id, "removed": provider.id}


def set_issue_status(
    hub_path: Path, issue_id: str, status: str, reason: str = "", agent: str = "Codex"
) -> dict[str, Any]:
    issue = issue_by_id(hub_path, issue_id)
    if status not in STATUS_ORDER:
        raise RuntimeError(f"Unsupported status: {status}")
    if issue.status not in STATUS_ORDER:
        raise RuntimeError(f"Unsupported current status: {issue.status}")
    current_index = STATUS_ORDER.index(issue.status)
    target_index = STATUS_ORDER.index(status)
    if target_index not in {current_index, current_index + 1}:
        raise RuntimeError(
            f"Refusing status transition {issue.status!r} -> {status!r}; use the next workflow state."
        )
    previous = issue.status
    issue.status = status
    issue.append_activity(
        f"Status changed to {status}",
        [
            f"Date: {isoformat(now_utc())}",
            f"Agent: {agent}",
            f"Previous status: {previous}",
            f"Reason: {reason or '-'}",
        ],
    )
    return {"ok": True, "issue": issue.id, "status": status, "previous_status": previous}


def append_issue_activity(
    hub_path: Path, issue_id: str, heading: str, lines: list[str]
) -> dict[str, Any]:
    issue = issue_by_id(hub_path, issue_id)
    issue.append_activity(heading, lines)
    return {"ok": True, "issue": issue.id, "heading": heading}


def add_issue_evidence(
    hub_path: Path, issue_id: str, heading: str, lines: list[str]
) -> dict[str, Any]:
    issue = issue_by_id(hub_path, issue_id)
    artifact_dir = hub_path / ARTIFACTS_DIR / issue.id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    index_path = artifact_dir / "evidence.md"
    entry = f"### {heading}\n" + "\n".join(lines).rstrip() + "\n"
    existing = index_path.read_text(encoding="utf-8") if index_path.exists() else "# Evidence\n"
    atomic_write(index_path, existing.rstrip() + "\n\n" + entry)
    issue.append_activity(heading, lines)
    return {"ok": True, "issue": issue.id, "heading": heading}


def list_changes(hub_path: Path) -> list[dict[str, Any]]:
    changes_root = hub_path / CHANGES_DIR
    if not changes_root.exists():
        return []
    changes: list[dict[str, Any]] = []
    for path in sorted(changes_root.glob("*/change.yml")):
        data = load_yamlish(path)
        data.setdefault("id", path.parent.name)
        data["_path"] = path
        changes.append(data)
    return changes


def refresh_state(hub_path: Path) -> dict[str, Any]:
    issues = load_issues(hub_path)
    changes = list_changes(hub_path)
    state = {
        "version": 3,
        "updated_at": isoformat(now_utc()),
        "issues": {
            issue.id: {
                "title": issue.title,
                "status": issue.status,
                "priority": issue.priority,
                "owner": issue.owner,
                "change": issue.change,
                "depends_on": issue.depends_on,
                "blocks": issue.blocks,
            }
            for issue in sorted(issues, key=lambda item: item.id)
        },
        "changes": {
            str(change.get("id")): {
                "title": str(change.get("title") or ""),
                "status": str(change.get("status") or ""),
                "priority": str(change.get("priority") or ""),
                "owner": str(change.get("owner") or ""),
                "issues": normalize_list(change.get("issues")),
            }
            for change in sorted(changes, key=lambda item: str(item.get("id") or ""))
        },
    }
    write_yamlish(hub_path / STATE_NAME, state)
    return state


def parse_github_pr_url(value: str) -> tuple[str, str, str] | None:
    parsed = urlparse(value)
    parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme in {"http", "https"}
        and parsed.netloc.lower() == "github.com"
        and len(parts) == 4
        and parts[2] == "pull"
        and parts[3].isdigit()
    ):
        return parts[0], parts[1], parts[3]
    return None


def github_pr_state_from_token(pr_url: str, token: str) -> dict[str, Any]:
    parsed = parse_github_pr_url(pr_url)
    if not parsed:
        raise RuntimeError("Unsupported GitHub PR URL.")
    owner, repo, number = parsed
    request = urllib.request.Request(
        f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API failed: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub API failed: {exc}") from exc
    return {
        "state": "MERGED" if payload.get("merged") else str(payload.get("state") or "").upper(),
        "url": payload.get("html_url") or pr_url,
        "merge_commit_sha": payload.get("merge_commit_sha"),
        "merged_at": payload.get("merged_at"),
    }


def github_pr_state_from_gh(pr_url: str) -> dict[str, Any]:
    command = [
        "gh",
        "pr",
        "view",
        pr_url,
        "--json",
        "state,mergedAt,mergeCommit,url",
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Unable to inspect PR with gh: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or f"exit {result.returncode}"
        raise RuntimeError(f"Unable to inspect PR with gh: {detail}")
    payload = json.loads(result.stdout or "{}")
    merge_commit = payload.get("mergeCommit")
    return {
        "state": payload.get("state"),
        "url": payload.get("url") or pr_url,
        "merge_commit_sha": (
            merge_commit.get("oid")
            if isinstance(merge_commit, dict)
            else payload.get("mergeCommit")
        ),
        "merged_at": payload.get("mergedAt"),
    }


def github_pr_state(pr_url: str) -> dict[str, Any]:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    try:
        return github_pr_state_from_gh(pr_url)
    except RuntimeError:
        if token:
            return github_pr_state_from_token(pr_url, token)
        raise


def is_github_pr_url(value: str) -> bool:
    return parse_github_pr_url(value) is not None


def sync_merged_prs(
    hub_path: Path,
    provider: Callable[[str], dict[str, Any]] | None = None,
    change: str = "",
) -> dict[str, Any]:
    provider = provider or github_pr_state
    change = str(change or "")
    completed: list[str] = []
    skipped: list[str] = []
    diagnostics: list[dict[str, str]] = []
    claims = load_runtime_claims(hub_path)
    claims_changed = False

    for issue in load_issues(hub_path):
        if change and issue.change != change:
            continue
        if issue.status != "In Review":
            continue
        if not issue.pr_url:
            skipped.append(issue.id)
            diagnostics.append(
                diagnostic(
                    "sync_missing_pr_url",
                    "warning",
                    relative_hub_target(hub_path, issue.path),
                    "In Review issue has no PR URL to inspect.",
                    "Record a PR URL before running merged PR sync.",
                )
            )
            continue
        if not is_github_pr_url(issue.pr_url):
            skipped.append(issue.id)
            diagnostics.append(
                diagnostic(
                    "sync_malformed_pr_url",
                    "warning",
                    relative_hub_target(hub_path, issue.path),
                    f"PR URL is not a supported GitHub pull request URL: {issue.pr_url}",
                    "Record a URL like https://github.com/owner/repo/pull/123.",
                )
            )
            continue
        try:
            pr_state = provider(issue.pr_url)
        except Exception as exc:  # noqa: BLE001 - sync should report and continue.
            skipped.append(issue.id)
            diagnostics.append(
                diagnostic(
                    "sync_pr_lookup_failed",
                    "warning",
                    relative_hub_target(hub_path, issue.path),
                    f"Could not inspect PR {issue.pr_url}: {exc}",
                    "Check GitHub authentication, network access, and the recorded PR URL.",
                )
            )
            continue
        state = str(pr_state.get("state") or "").upper()
        if state != "MERGED":
            skipped.append(issue.id)
            diagnostics.append(
                diagnostic(
                    "sync_pr_not_merged",
                    "info",
                    relative_hub_target(hub_path, issue.path),
                    f"PR {issue.pr_url} is {state or 'unknown'}, not merged.",
                    "Leave the issue In Review until the PR is merged or review sends it back.",
                )
            )
            continue

        merge_commit = str(pr_state.get("merge_commit_sha") or "")
        merged_at = str(pr_state.get("merged_at") or "")
        issue.status = "Completed"
        issue.claim = {}
        issue.append_activity(
            "Status change: In Review -> Completed",
            [
                f"Date: {isoformat(now_utc())}",
                "Agent: agent-hub state sync-merged-prs",
                f"PR URL: {issue.pr_url}",
                f"Merge commit: {merge_commit or 'unknown'}",
                f"Merged at: {merged_at or 'unknown'}",
                "Reason: GitHub PR is merged.",
            ],
        )
        if issue.id in claims:
            del claims[issue.id]
            claims_changed = True
        completed.append(issue.id)

    if claims_changed:
        write_runtime_claims(hub_path, claims)
    return {
        "ok": True,
        "change": change,
        "completed": completed,
        "skipped": skipped,
        "diagnostics": diagnostics,
    }


def relative_hub_target(hub_path: Path, path: Path) -> str:
    try:
        return ".hub/" + path.relative_to(hub_path).as_posix()
    except ValueError:
        return path.as_posix()


def diagnostic(
    code: str, severity: str, target: str, message: str, recommendation: str
) -> dict[str, str]:
    return {
        "code": code,
        "severity": severity,
        "target": target,
        "message": message,
        "recommendation": recommendation,
    }


def frontmatter_malformed(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return True
    end = text.find("\n---\n", 4)
    if end == -1:
        return True
    raw = text[4:end].splitlines()
    for line in raw:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.count('"') % 2 == 1 or stripped.count("'") % 2 == 1:
            return True
        if ("[" in stripped and "]" not in stripped) or ("]" in stripped and "[" not in stripped):
            return True
    return False


def malformed_frontmatter_diagnostic(hub_path: Path, path: Path) -> dict[str, str]:
    return diagnostic(
        "malformed_frontmatter",
        "error",
        relative_hub_target(hub_path, path),
        "Issue frontmatter is malformed.",
        "Repair the YAML frontmatter with the deterministic issue update command or recreate the issue file.",
    )


def load_valid_issue_paths(hub_path: Path) -> list[Path]:
    issues_dir = hub_path / ISSUES_DIR
    if not issues_dir.exists():
        return []
    return [
        path
        for path in sorted(issues_dir.glob("*.md"))
        if not frontmatter_malformed(path)
    ]


def runtime_claim_audit_diagnostics(
    hub_path: Path, by_id: dict[str, FileHubIssue]
) -> list[dict[str, str]]:
    path = runtime_claims_path(hub_path)
    if not path.exists():
        return []

    target = relative_hub_target(hub_path, path)
    try:
        claims = json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        return [
            diagnostic(
                "malformed_runtime_claims",
                "error",
                target,
                "Runtime claims file is malformed JSON.",
                "Repair or remove .hub/runtime/claims.json before claiming or auditing work.",
            )
        ]

    if not isinstance(claims, dict):
        return [
            diagnostic(
                "malformed_runtime_claims",
                "error",
                target,
                "Runtime claims file must contain a JSON object.",
                "Rewrite .hub/runtime/claims.json as an object keyed by issue ID.",
            )
        ]

    diagnostics: list[dict[str, str]] = []
    for issue_id, claim in sorted(claims.items()):
        if not isinstance(claim, dict):
            diagnostics.append(
                diagnostic(
                    "malformed_runtime_claim",
                    "error",
                    f"{target}#{issue_id}",
                    "Runtime claim entry is not an object.",
                    "Remove the malformed entry or recreate the claim with the deterministic claim command.",
                )
            )
            continue

        issue = by_id.get(str(issue_id))
        if issue is None:
            diagnostics.append(
                diagnostic(
                    "runtime_claim_unknown_issue",
                    "warning",
                    f"{target}#{issue_id}",
                    "Runtime claim references an unknown issue.",
                    "Remove stale runtime claim entries for issues that no longer exist.",
                )
            )
            continue

        expires_at = parse_datetime(claim.get("expires_at"))
        if claim.get("id") and expires_at and expires_at <= now_utc():
            diagnostics.append(
                diagnostic(
                    "stale_claim",
                    "error",
                    relative_hub_target(hub_path, issue.path),
                    "Issue has an expired work claim.",
                    "Use the deterministic claim release or renew command before another agent claims this issue.",
                )
            )
    return diagnostics


def section_text(body: str, heading: str) -> str:
    pattern = re.compile(
        rf"^{re.escape(heading)}\s*$([\s\S]*?)(?=^##+ .*$|\Z)",
        re.MULTILINE,
    )
    match = pattern.search(body)
    return match.group(1).strip() if match else ""


def markdown_heading_level(heading: str) -> int:
    return len(heading) - len(heading.lstrip("#"))


def markdown_section_text(body: str, heading: str) -> str | None:
    level = markdown_heading_level(heading)
    if level <= 0:
        raise RuntimeError(f"Invalid markdown heading: {heading!r}")
    heading_pattern = re.compile(rf"^{re.escape(heading)}\s*$", re.MULTILINE)
    match = heading_pattern.search(body)
    if not match:
        return None
    end_pattern = re.compile(rf"^#{{1,{level}}}\s+.*$", re.MULTILINE)
    next_match = end_pattern.search(body, match.end())
    end = next_match.start() if next_match else len(body)
    return body[match.end() : end].strip()


def render_markdown_section(heading: str, text: str) -> str:
    text = text.strip()
    return f"{heading}\n\n{text}".rstrip() if text else heading


def activity_log_text(body: str) -> str:
    section = markdown_section_text(body, "## Activity Log")
    if section is None:
        return "## Activity Log"
    return render_markdown_section("## Activity Log", section)


def bounded_spec_body(spec_body: str, existing_body: str) -> tuple[str, list[str]]:
    sections: list[str] = []
    updated: list[str] = []
    for heading in SPEC_SECTION_HEADINGS:
        text = markdown_section_text(spec_body, heading)
        if text is not None:
            updated.append(heading)
        else:
            text = markdown_section_text(existing_body, heading) or ""
        sections.append(render_markdown_section(heading, text))
    sections.append(activity_log_text(existing_body))
    return "\n\n".join(sections).rstrip() + "\n", updated


def set_issue_spec(hub_path: Path, issue_id: str, spec_file: Path) -> dict[str, Any]:
    issue = issue_by_id(hub_path, issue_id)
    spec_path = spec_file.expanduser().resolve()
    if not spec_path.exists() or not spec_path.is_file():
        raise RuntimeError(f"Spec file does not exist: {spec_file}")
    _, spec_body = parse_frontmatter(spec_path.read_text(encoding="utf-8"))
    new_body, updated_sections = bounded_spec_body(spec_body, issue.body)
    if not updated_sections:
        raise RuntimeError("Spec file does not contain any bounded Agent Hub issue sections.")
    issue.body = new_body
    issue.write()
    updated_issue = issue_by_id(hub_path, issue.id)
    diagnostics = issue_audit_diagnostics(hub_path, updated_issue)
    return {
        "ok": True,
        "issue": updated_issue.id,
        "path": str(updated_issue.path),
        "updated_sections": updated_sections,
        "diagnostics": diagnostics,
    }


def field_value(section: str, field: str) -> str:
    match = re.search(rf"^{re.escape(field)}:\s*(.*)$", section, re.MULTILINE)
    return match.group(1).strip().strip("`") if match else ""


def has_first_test(body: str) -> bool:
    first_test = section_text(body, "### First Test")
    return bool(
        field_value(first_test, "Path")
        and field_value(first_test, "Expected initial result")
        and field_value(first_test, "Reason this proves the regression or requirement")
    )


def has_final_verification(body: str) -> bool:
    final = section_text(body, "### Final Verification")
    return bool(field_value(final, "Commands") and field_value(final, "Expected result"))


def is_placeholder_text(text: str) -> bool:
    normalized = " ".join(text.strip().lower().split())
    return normalized in {"", "tbd", "tbd.", "todo", "todo.", "none", "n/a"}


def issue_audit_diagnostics(hub_path: Path, issue: FileHubIssue) -> list[dict[str, str]]:
    target = relative_hub_target(hub_path, issue.path)
    diagnostics: list[dict[str, str]] = []

    if issue.type in {"Feature", "Bug", "Task"} and not has_first_test(issue.body):
        diagnostics.append(
            diagnostic(
                "implementation_missing_first_test",
                "error",
                target,
                "Implementation issue has no First Test recorded.",
                "Add a regression test path and expected initial failing result before claim.",
            )
        )
    if issue.type in {"Feature", "Bug", "Task"} and not has_final_verification(issue.body):
        diagnostics.append(
            diagnostic(
                "implementation_missing_final_verification",
                "error",
                target,
                "Implementation issue has no final verification command recorded.",
                "Add the focused command that must pass after implementation.",
            )
        )

    if issue.status == "In Review":
        if not issue.commit_sha:
            diagnostics.append(
                diagnostic(
                    "review_ready_missing_commit",
                    "error",
                    target,
                    "Issue is In Review without commit evidence.",
                    "Record the commit SHA before submitting repo-changing work for review.",
                )
            )
        if not issue.pr_url:
            diagnostics.append(
                diagnostic(
                    "review_ready_missing_pr",
                    "error",
                    target,
                    "Issue is In Review without PR evidence.",
                    "Record the pull request URL before review can complete.",
                )
            )
        if "Command:" not in issue.body and "Result:" not in issue.body:
            diagnostics.append(
                diagnostic(
                    "review_ready_missing_regression_evidence",
                    "error",
                    target,
                    "Issue is In Review without regression or final verification evidence.",
                    "Add focused command output and final verification results before review.",
                )
            )

    claim_expires_at = parse_datetime(issue.claim.get("expires_at"))
    if issue.claim and claim_expires_at and claim_expires_at <= now_utc():
        diagnostics.append(
            diagnostic(
                "stale_claim",
                "error",
                target,
                "Issue has an expired work claim.",
                "Use the deterministic claim release or renew command before another agent claims this issue.",
            )
        )

    scope = section_text(issue.body, "## Scope")
    if is_placeholder_text(scope):
        diagnostics.append(
            diagnostic(
                "issue_scope_too_vague",
                "error",
                target,
                "Issue scope is too vague for an independent subagent.",
                "Replace placeholder scope text with concrete in-scope changes and boundaries.",
            )
        )
    out_of_scope = section_text(issue.body, "## Out Of Scope")
    if is_placeholder_text(out_of_scope):
        diagnostics.append(
            diagnostic(
                "issue_out_of_scope_too_vague",
                "error",
                target,
                "Issue out-of-scope section is missing concrete exclusions.",
                "List explicit non-goals so the subagent can avoid unrelated work.",
            )
        )
    done = section_text(issue.body, "## Done Criteria")
    if is_placeholder_text(done) or re.search(r"- \[[ xX]\]\s*better\.?\s*$", done, re.I | re.M):
        diagnostics.append(
            diagnostic(
                "issue_done_criteria_not_observable",
                "error",
                target,
                "Done criteria are not observable.",
                "Replace subjective criteria with checkable outcomes.",
            )
        )

    return diagnostics


def issue_dependency_diagnostics(
    hub_path: Path, issue: FileHubIssue, by_id: dict[str, FileHubIssue]
) -> list[dict[str, str]]:
    diagnostics: list[dict[str, str]] = []
    target = relative_hub_target(hub_path, issue.path)
    for dep_id in issue.depends_on:
        if dep_id not in by_id:
            diagnostics.append(
                diagnostic(
                    "dangling_dependency",
                    "error",
                    target,
                    f"Issue depends on missing issue {dep_id}.",
                    f"Create .hub/issues/{dep_id}.md or remove the dependency with the deterministic command.",
                )
            )
    return diagnostics


def markdown_section_lines(body: str, heading: str) -> list[str]:
    text = markdown_section_text(body, heading) or ""
    return [line.rstrip() for line in text.splitlines() if line.strip()]


def verification_snapshot(body: str) -> dict[str, dict[str, str]]:
    first = markdown_section_text(body, "### First Test") or ""
    final = markdown_section_text(body, "### Final Verification") or ""
    return {
        "first_test": {
            "path": field_value(first, "Path"),
            "expected_initial_result": field_value(first, "Expected initial result"),
            "reason": field_value(
                first, "Reason this proves the regression or requirement"
            ),
            "snippet": first,
        },
        "final_verification": {
            "commands": field_value(final, "Commands"),
            "expected_result": field_value(final, "Expected result"),
            "snippet": final,
        },
    }


def dashboard_column_id(
    issue: FileHubIssue, diagnostics: list[dict[str, str]], readiness_state: str
) -> str:
    if issue.status == "In Progress":
        return "in-progress"
    if issue.status == "In Review":
        return "in-review"
    if issue.status == "Completed":
        return "completed"
    spec_codes = {item.get("code", "") for item in diagnostics}
    if spec_codes.intersection(SPEC_DIAGNOSTIC_CODES):
        return "needs-spec"
    if readiness_state != "Ready":
        return "blocked"
    return "ready"


def dashboard_sort_key(issue: FileHubIssue) -> tuple[int, str]:
    return (PRIORITY_ORDER.get(issue.priority, 99), issue.id)


def issue_dashboard_card(
    hub_path: Path,
    issue: FileHubIssue,
    by_id: dict[str, FileHubIssue],
    diagnostics: list[dict[str, str]],
) -> dict[str, Any]:
    ready_state, reason = readiness(issue, by_id)
    return {
        "id": issue.id,
        "title": issue.title,
        "status": issue.status,
        "type": issue.type,
        "priority": issue.priority,
        "owner": issue.owner,
        "change": issue.change,
        "area": issue.area,
        "summary": issue.summary,
        "path": relative_hub_target(hub_path, issue.path),
        "depends_on": issue.depends_on,
        "blocks": issue.blocks,
        "blockers": issue.blockers,
        "fields": {
            "status": issue.status,
            "type": issue.type,
            "priority": issue.priority,
            "owner": issue.owner,
            "change": issue.change,
        },
        "readiness": {"state": ready_state, "reason": reason},
        "diagnostics": diagnostics,
        "done_criteria": markdown_section_lines(issue.body, "## Done Criteria"),
        "verification": verification_snapshot(issue.body),
    }


def dashboard_snapshot(hub_path: Path, change: str = "") -> dict[str, Any]:
    change_filter = validate_change_slug(change) if change else ""
    if change_filter and not change_yml_path(hub_path, change_filter).exists():
        raise RuntimeError(f"No change packet found for {change_filter!r}.")
    config = load_config(hub_path)
    dashboard_config = config.get("dashboard") if isinstance(config.get("dashboard"), dict) else {}

    issues_dir = hub_path / ISSUES_DIR
    issue_paths = sorted(issues_dir.glob("*.md")) if issues_dir.exists() else []
    valid_issues: list[FileHubIssue] = []
    diagnostics: list[dict[str, str]] = []
    for path in issue_paths:
        if frontmatter_malformed(path):
            diagnostics.append(malformed_frontmatter_diagnostic(hub_path, path))
            continue
        valid_issues.append(FileHubIssue.from_path(path))

    by_id = {issue.id: issue for issue in valid_issues}
    diagnostics.extend(runtime_claim_audit_diagnostics(hub_path, by_id))
    filtered_issues = [
        issue
        for issue in valid_issues
        if not change_filter or issue.change == change_filter
    ]

    grouped_cards: dict[str, list[dict[str, Any]]] = {
        column_id: [] for column_id, _ in DASHBOARD_COLUMNS
    }
    for issue in sorted(filtered_issues, key=dashboard_sort_key):
        issue_diagnostics = [
            *issue_dependency_diagnostics(hub_path, issue, by_id),
            *issue_audit_diagnostics(hub_path, issue),
        ]
        diagnostics.extend(issue_diagnostics)
        ready_state, _ = readiness(issue, by_id)
        column_id = dashboard_column_id(issue, issue_diagnostics, ready_state)
        grouped_cards[column_id].append(
            issue_dashboard_card(hub_path, issue, by_id, issue_diagnostics)
        )

    columns = [
        {"id": column_id, "title": title, "issues": grouped_cards[column_id]}
        for column_id, title in DASHBOARD_COLUMNS
    ]
    return {
        "version": "3",
        "generated_at": isoformat(now_utc()),
        "mode": "read-only",
        "change": change_filter,
        "hub": {
            "project": str(config.get("project") or ""),
            "source_of_truth": str(config.get("source_of_truth") or "file"),
            "dashboard_mode": str(dashboard_config.get("mode") or "read-only"),
        },
        "columns": columns,
        "diagnostics": diagnostics,
        "summary": {
            "issue_count": len(filtered_issues),
            "diagnostic_count": len(diagnostics),
            "columns": {
                title: len(grouped_cards[column_id])
                for column_id, title in DASHBOARD_COLUMNS
            },
        },
    }


def dashboard_source_paths(hub_path: Path) -> list[Path]:
    paths: list[Path] = []
    config_path = hub_path / CONFIG_NAME
    if config_path.exists():
        paths.append(config_path)

    issues_dir = hub_path / ISSUES_DIR
    if issues_dir.exists():
        paths.extend(path for path in issues_dir.glob("*.md") if path.is_file())

    changes_dir = hub_path / CHANGES_DIR
    if changes_dir.exists():
        paths.extend(path for path in changes_dir.rglob("*") if path.is_file())

    claims_path = hub_path / RUNTIME_DIR / CLAIMS_NAME
    if claims_path.exists():
        paths.append(claims_path)

    return sorted(paths, key=lambda path: relative_hub_target(hub_path, path))


def dashboard_source_fingerprint(hub_path: Path) -> str:
    hub_path = hub_path.expanduser().resolve()
    digest = hashlib.sha256()
    digest.update(b"agent-hub-dashboard-source-v1\0")
    digest.update(str(hub_path).encode("utf-8"))
    digest.update(b"\0")
    for path in dashboard_source_paths(hub_path):
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            continue
        digest.update(relative_hub_target(hub_path, path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(content)).encode("ascii"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def dashboard_live_revision(source_fingerprint: str, change: str = "") -> str:
    digest = hashlib.sha256()
    digest.update(b"agent-hub-dashboard-live-revision-v1\0")
    digest.update(change.encode("utf-8"))
    digest.update(b"\0")
    digest.update(source_fingerprint.encode("ascii"))
    return digest.hexdigest()


def dashboard_live_snapshot(
    hub_path: Path, change: str = "", source_fingerprint: str | None = None
) -> dict[str, Any]:
    change_filter = validate_change_slug(change) if change else ""
    fingerprint = source_fingerprint or dashboard_source_fingerprint(hub_path)
    revision_id = dashboard_live_revision(fingerprint, change_filter)
    snapshot = dashboard_snapshot(hub_path, change=change_filter)
    snapshot["revision"] = {
        "id": revision_id,
        "etag": f'"{revision_id}"',
        "source_fingerprint": fingerprint,
        "source": "file",
        "change": change_filter,
    }
    return snapshot


@dataclass
class DashboardLiveSnapshotCache:
    entries: dict[str, dict[str, Any]] = field(default_factory=dict)

    def get(self, hub_path: Path, change: str = "") -> dict[str, Any]:
        hub_path = hub_path.expanduser().resolve()
        change_filter = validate_change_slug(change) if change else ""
        fingerprint = dashboard_source_fingerprint(hub_path)
        revision_id = dashboard_live_revision(fingerprint, change_filter)
        cache_key = f"{hub_path}\0{change_filter}"
        cached = self.entries.get(cache_key)
        if cached and cached.get("revision_id") == revision_id:
            return copy.deepcopy(cached["snapshot"])

        snapshot = dashboard_live_snapshot(
            hub_path,
            change=change_filter,
            source_fingerprint=fingerprint,
        )
        self.entries[cache_key] = {
            "revision_id": revision_id,
            "snapshot": copy.deepcopy(snapshot),
        }
        return snapshot


def extract_task_issue_ids(tasks_text: str) -> list[str]:
    ids: list[str] = []
    for line in tasks_text.splitlines():
        match = re.match(r"\s*-\s*\[[ xX]\]\s*`?([a-z0-9][a-z0-9-]*)`?\b", line)
        if match:
            ids.append(match.group(1))
    return ids


def remove_task_issue(tasks_text: str, issue_id: str) -> str:
    pattern = re.compile(rf"\s*-\s*\[[ xX]\]\s*`?{re.escape(issue_id)}`?\b")
    kept = [line for line in tasks_text.splitlines() if not pattern.match(line)]
    return "\n".join(kept).rstrip() + "\n"


def write_report(hub_path: Path, name: str, result: dict[str, Any]) -> None:
    reports_dir = hub_path / REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / f"latest-{name}.json"
    md_path = reports_dir / f"latest-{name}.md"
    atomic_write(json_path, json.dumps(result, indent=2, sort_keys=True) + "\n")

    lines = [f"# Agent Hub {name.title()} Report", ""]
    diagnostics = result.get("diagnostics", [])
    if not diagnostics:
        lines.append("No diagnostics.")
    else:
        for item in diagnostics:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- {item.get('severity', 'info').upper()} `{item.get('code', '')}` "
                f"{item.get('target', '')}: {item.get('message', '')}"
            )
            lines.append(f"  Recommendation: {item.get('recommendation', '')}")
    atomic_write(md_path, "\n".join(lines).rstrip() + "\n")


def audit_hub(hub_path: Path) -> dict[str, Any]:
    diagnostics: list[dict[str, str]] = []

    for filename in sorted(PROJECT_TEMPLATES):
        path = hub_path / PROJECT_DIR / filename
        target = relative_hub_target(hub_path, path)
        if path.exists():
            continue
        diagnostics.append(
            diagnostic(
                "missing_required_file",
                "error",
                target,
                "Required Agent Hub v3 file is missing.",
                f"Create {target} with the Agent Hub v3 required headings.",
            )
        )
        if filename == "principles.md":
            diagnostics.append(
                diagnostic(
                    "missing_required_project_guidance",
                    "error",
                    target,
                    "Required project guidance file is missing.",
                    "Create .hub/project/principles.md with the Agent Hub v3 required headings.",
                )
            )
        elif filename == "delegation.md":
            diagnostics.append(
                diagnostic(
                    "missing_required_project_guidance",
                    "error",
                    target,
                    "Required delegation guidance file is missing.",
                    "Create .hub/project/delegation.md with the subagent handoff contract, evidence requirements, and stop conditions.",
                )
            )

    issues_dir = hub_path / ISSUES_DIR
    issue_paths = sorted(issues_dir.glob("*.md")) if issues_dir.exists() else []
    valid_issues: list[FileHubIssue] = []
    for path in issue_paths:
        if frontmatter_malformed(path):
            diagnostics.append(malformed_frontmatter_diagnostic(hub_path, path))
            continue
        issue = FileHubIssue.from_path(path)
        valid_issues.append(issue)

    by_id = {issue.id: issue for issue in valid_issues}
    diagnostics.extend(runtime_claim_audit_diagnostics(hub_path, by_id))
    for issue in valid_issues:
        target = relative_hub_target(hub_path, issue.path)
        for dep_id in issue.depends_on:
            if dep_id not in by_id:
                diagnostics.append(
                    diagnostic(
                        "dangling_dependency",
                        "error",
                        target,
                        f"Issue depends on missing issue {dep_id}.",
                        f"Create .hub/issues/{dep_id}.md or remove the dependency with the deterministic command.",
                    )
                )
        diagnostics.extend(issue_audit_diagnostics(hub_path, issue))

    result = {
        "version": "3",
        "diagnostics": diagnostics,
        "summary": {"diagnostic_count": len(diagnostics), "issue_count": len(valid_issues)},
    }
    write_report(hub_path, "audit", result)
    return result


def audit_issue(hub_path: Path, issue_id: str) -> dict[str, Any]:
    issue_path = issue_path_for_id(hub_path, issue_id)
    if issue_path.exists() and frontmatter_malformed(issue_path):
        result = {
            "version": "3",
            "issue": validate_issue_id(issue_id),
            "diagnostics": [malformed_frontmatter_diagnostic(hub_path, issue_path)],
            "summary": {"diagnostic_count": 1},
        }
        write_report(hub_path, "audit", result)
        return result

    issue = issue_by_id(hub_path, issue_id)
    diagnostics = issue_audit_diagnostics(hub_path, issue)
    by_id = {
        item.id: item
        for item in (FileHubIssue.from_path(path) for path in load_valid_issue_paths(hub_path))
    }
    target = relative_hub_target(hub_path, issue.path)
    for dep_id in issue.depends_on:
        if dep_id not in by_id:
            diagnostics.insert(
                0,
                diagnostic(
                    "dangling_dependency",
                    "error",
                    target,
                    f"Issue depends on missing issue {dep_id}.",
                    f"Create .hub/issues/{dep_id}.md or remove the dependency with the deterministic command.",
                ),
            )
    result = {
        "version": "3",
        "issue": issue.id,
        "diagnostics": diagnostics,
        "summary": {"diagnostic_count": len(diagnostics)},
    }
    write_report(hub_path, "audit", result)
    return result


def analyze_change(hub_path: Path, change_slug: str) -> dict[str, Any]:
    change = load_change(hub_path, change_slug)
    listed_issues = normalize_list(change.get("issues"))
    issue_paths = {
        path.stem: path for path in sorted((hub_path / ISSUES_DIR).glob("*.md"))
    }
    valid_issues: dict[str, FileHubIssue] = {}
    for issue_id, path in issue_paths.items():
        if not frontmatter_malformed(path):
            issue = FileHubIssue.from_path(path)
            valid_issues[issue.id] = issue

    diagnostics: list[dict[str, str]] = []
    change_target = relative_hub_target(hub_path, change_yml_path(hub_path, change_slug))
    for issue_id in listed_issues:
        issue = valid_issues.get(issue_id)
        if not issue:
            diagnostics.append(
                diagnostic(
                    "change_missing_issue",
                    "error",
                    change_target,
                    "Change packet references an issue file that does not exist.",
                    f"Create .hub/issues/{issue_id}.md or remove {issue_id} from the change packet.",
                )
            )
            continue
        if issue.change != change_slug:
            diagnostics.append(
                diagnostic(
                    "issue_change_mismatch",
                    "error",
                    relative_hub_target(hub_path, issue.path),
                    "Issue frontmatter points to a different change packet.",
                    f"Set issue field change to {change_slug} or move the issue to the referenced packet.",
                )
            )

    for issue in sorted(valid_issues.values(), key=lambda item: item.id):
        if issue.change == change_slug and issue.id not in listed_issues:
            diagnostics.append(
                diagnostic(
                    "change_issue_link_mismatch",
                    "error",
                    relative_hub_target(hub_path, issue.path),
                    "Issue frontmatter points to this change but change.yml does not list it.",
                    f"Add {issue.id} to .hub/changes/{change_slug}/change.yml issues or clear the issue change field.",
                )
            )

    tasks_path = change_dir(hub_path, change_slug) / "tasks.md"
    if tasks_path.exists():
        task_ids = extract_task_issue_ids(tasks_path.read_text(encoding="utf-8"))
        for task_id in task_ids:
            if task_id not in listed_issues:
                diagnostics.append(
                    diagnostic(
                        "change_task_not_linked",
                        "warning",
                        relative_hub_target(hub_path, tasks_path),
                        "Task list mentions an issue not linked from change.yml.",
                        f"Add {task_id} to change.yml issues or remove it from tasks.md.",
                    )
                )

    result = {
        "version": "3",
        "change": change_slug,
        "diagnostics": diagnostics,
        "summary": {
            "diagnostic_count": len(diagnostics),
            "listed_issue_count": len(listed_issues),
        },
    }
    write_report(hub_path, "analysis", result)
    return result
