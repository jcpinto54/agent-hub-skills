#!/usr/bin/env python3
"""Stdlib scenario evaluator for local Agent Hub v3 evals."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any


POLICY_FILES = [
    "README.md",
    "skills/manage-agent-hub-issues/SKILL.md",
    "skills/manage-agent-hub-issues/references/v3-router-policy.md",
    "skills/manage-agent-hub-issues/references/v3-workflows.md",
    "skills/create-agent-hub-issue/SKILL.md",
    "skills/review-agent-hub-issue/SKILL.md",
    "skills/update-agent-hub-issue/SKILL.md",
    "skills/list-agent-hub-issues/SKILL.md",
    "skills/iterate-agent-hub-work/SKILL.md",
    "skills/run-agent-hub-loop/SKILL.md",
]


def _load_file_hub(repo_root: Path) -> Any:
    common_lib = repo_root / "skills" / "manage-agent-hub-issues" / "lib"
    sys.path.insert(0, str(common_lib))
    import file_hub_common  # type: ignore  # noqa: PLC0415

    return file_hub_common


def _codes(result: dict[str, Any]) -> set[str]:
    return {
        str(item.get("code"))
        for item in result.get("diagnostics", [])
        if isinstance(item, dict) and item.get("code")
    }


def _first_change_slug(hub: Path) -> str:
    changes_dir = hub / "changes"
    for path in sorted(changes_dir.glob("*/change.yml")):
        return path.parent.name
    return ""


def _extract_change_slug(prompt: str, fallback: str) -> str:
    match = re.search(r"\b([a-z0-9]+(?:-[a-z0-9]+)+)\b", prompt)
    return match.group(1) if match else fallback


def _policy_corpus(repo_root: Path) -> str:
    parts: list[str] = []
    for relative_path in POLICY_FILES:
        path = repo_root / relative_path
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts).lower()


def _contains_all(corpus: str, needles: list[str]) -> tuple[bool, list[str]]:
    missing = [needle for needle in needles if needle.lower() not in corpus]
    return not missing, missing


def _route_requirements(expected: dict[str, Any]) -> list[str]:
    route = expected.get("route")
    command = expected.get("command")
    requirements = [
        "central agent hub store",
        "only durable source of truth",
        "deterministic commands own hub mutations",
        "do not hand-edit",
    ]
    if command:
        requirements.append(str(command))
    if route == "delegate_to_subagent" or expected.get("subagent_required"):
        requirements.extend(
            [
                "substantive work belongs in bounded subagents",
                "parent agent routes",
            ]
        )
    if route == "refuse_manual_hub_rewrite":
        requirements.append("instead of hand-editing")
    return requirements


def _handoff_requirements(expected: dict[str, Any]) -> list[str]:
    handoff_type = expected.get("handoff_type")
    required = [str(item).lower() for item in expected.get("must_include", [])]
    requirements: list[str] = []
    for item in required:
        if "failing tests" in item or "expected initial failure" in item:
            requirements.append("initial failing result")
        elif "tdd" in item:
            requirements.append("tdd")
        elif "regression evidence" in item:
            requirements.append("regression evidence")
        elif "final verification" in item:
            requirements.append("final verification")
        elif "required files" in item:
            requirements.append("required files")
        elif "out-of-scope" in item or "out of scope" in item:
            requirements.append("out of scope")
        else:
            requirements.append(item)
    if handoff_type:
        requirements.append("handoff")
    return requirements


def evaluate_scenario(
    scenario: dict[str, Any],
    scenario_path: Path | None = None,
    fixture_dir: Path | None = None,
    repo_root: Path | None = None,
    eval_root: Path | None = None,
) -> dict[str, Any]:
    repo_root = repo_root or Path(__file__).resolve().parents[1]
    fixture_dir = fixture_dir or repo_root / "evals" / "fixtures" / str(scenario.get("fixture", ""))
    hub = fixture_dir / ".hub"
    kind = str(scenario.get("kind", ""))
    expected = scenario.get("expected", {}) if isinstance(scenario.get("expected"), dict) else {}

    if kind == "diagnostic_quality":
        file_hub = _load_file_hub(repo_root)
        slug = _extract_change_slug(str(scenario.get("prompt", "")), _first_change_slug(hub))
        result = file_hub.analyze_change(hub, slug)
        required_codes = set(expected.get("stable_codes", []))
        actual_codes = _codes(result)
        required_fields = expected.get("diagnostic_fields", [])
        fields_ok = all(
            all(field in item for field in required_fields)
            for item in result.get("diagnostics", [])
            if isinstance(item, dict)
        )
        passed = required_codes.issubset(actual_codes) and fields_ok
        return {
            "passed": passed,
            "kind": kind,
            "actual_codes": sorted(actual_codes),
            "required_codes": sorted(required_codes),
            "fields_ok": fields_ok,
        }

    if kind == "review_gate":
        file_hub = _load_file_hub(repo_root)
        result = file_hub.audit_hub(hub)
        required_codes = set(expected.get("required_diagnostics", []))
        actual_codes = _codes(result)
        return {
            "passed": required_codes.issubset(actual_codes),
            "kind": kind,
            "decision": "reject" if required_codes.issubset(actual_codes) else "unknown",
            "actual_codes": sorted(actual_codes),
            "required_codes": sorted(required_codes),
        }

    if kind == "router":
        corpus = _policy_corpus(repo_root)
        requirements = _route_requirements(expected)
        passed, missing = _contains_all(corpus, requirements)
        return {
            "passed": passed,
            "kind": kind,
            "route": expected.get("route"),
            "command": expected.get("command"),
            "subagent_required": expected.get("subagent_required"),
            "checked_files": POLICY_FILES,
            "missing_requirements": missing,
        }

    if kind == "handoff":
        corpus = _policy_corpus(repo_root)
        requirements = _handoff_requirements(expected)
        passed, missing = _contains_all(corpus, requirements)
        return {
            "passed": passed,
            "kind": kind,
            "handoff_type": expected.get("handoff_type"),
            "covered": requirements,
            "checked_files": POLICY_FILES,
            "missing_requirements": missing,
        }

    if kind == "policy_text":
        corpus = _policy_corpus(repo_root)
        requirements = [str(item) for item in expected.get("required_phrases", [])]
        passed, missing = _contains_all(corpus, requirements)
        return {
            "passed": passed,
            "kind": kind,
            "checked_files": POLICY_FILES,
            "missing_requirements": missing,
        }

    return {
        "passed": False,
        "kind": kind,
        "reason": f"Unsupported scenario kind {kind!r}.",
        "scenario_path": str(scenario_path or ""),
        "eval_root": str(eval_root or ""),
    }
