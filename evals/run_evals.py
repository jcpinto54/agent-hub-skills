#!/usr/bin/env python3
"""Local Agent Hub v3 fixture and scenario eval runner.

This runner intentionally uses only the Python standard library. It is designed
to fail clearly until the future deterministic Agent Hub v3 CLI/library exists.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EVAL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EVAL_ROOT.parent
FIXTURES_DIR = EVAL_ROOT / "fixtures"
EXPECTED_DIR = EVAL_ROOT / "expected"
SCENARIOS_DIR = EVAL_ROOT / "scenarios"
REPORTS_DIR = EVAL_ROOT / "reports"

LOCAL_AGENT_HUB_SCRIPT = (
    REPO_ROOT / "skills" / "manage-agent-hub-issues" / "scripts" / "agent_hub.py"
)
SCENARIO_EVALUATOR_CANDIDATES = [
    EVAL_ROOT / "scenario_adapter.py",
    REPO_ROOT
    / "skills"
    / "manage-agent-hub-issues"
    / "lib"
    / "agent_hub_scenarios.py",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@contextmanager
def isolated_fixture_dir(fixture_dir: Path):
    if not fixture_dir.exists() or fixture_dir == FIXTURES_DIR:
        yield fixture_dir
        return
    with tempfile.TemporaryDirectory(prefix="agent-hub-eval-") as temp_dir:
        target = Path(temp_dir) / fixture_dir.name
        shutil.copytree(fixture_dir, target)
        yield target


def text_tail(value: str, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


def find_agent_hub_cli() -> dict[str, Any] | None:
    if LOCAL_AGENT_HUB_SCRIPT.exists():
        return {
            "kind": "local_script",
            "source": str(LOCAL_AGENT_HUB_SCRIPT),
            "command": [sys.executable, str(LOCAL_AGENT_HUB_SCRIPT)],
        }

    executable = shutil.which("agent-hub")
    if executable:
        return {
            "kind": "path_executable",
            "source": executable,
            "command": [executable],
        }

    return None


def load_scenario_evaluator() -> dict[str, Any] | None:
    for path in SCENARIO_EVALUATOR_CANDIDATES:
        if not path.exists():
            continue
        sys.path.insert(0, str(path.parent))
        spec = importlib.util.spec_from_file_location("agent_hub_scenario_eval", path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        evaluator = getattr(module, "evaluate_scenario", None)
        if callable(evaluator):
            return {"source": str(path), "function": evaluator}
    return None


def extract_diagnostics(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("diagnostics", "findings", "issues"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    report = payload.get("report")
    if isinstance(report, dict):
        return extract_diagnostics(report)

    return []


def diagnostic_matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(actual.get(key) == expected_value for key, expected_value in expected.items())


def compare_diagnostics(
    match_mode: str, actual: list[dict[str, Any]], expected: list[dict[str, Any]]
) -> tuple[bool, list[dict[str, Any]]]:
    if match_mode == "exact_diagnostics":
        return actual == expected, [] if actual == expected else expected

    if match_mode != "diagnostic_subset":
        return False, [
            {
                "code": "eval_invalid_match_mode",
                "severity": "error",
                "target": "evals/expected",
                "message": f"Unknown match mode {match_mode!r}.",
                "recommendation": "Use exact_diagnostics or diagnostic_subset.",
            }
        ]

    unmatched: list[dict[str, Any]] = []
    for expected_diagnostic in expected:
        if not any(diagnostic_matches(actual_diagnostic, expected_diagnostic) for actual_diagnostic in actual):
            unmatched.append(expected_diagnostic)
    return not unmatched, unmatched


def validate_expected_spec(path: Path, spec: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("id", "fixture", "evaluations"):
        if key not in spec:
            errors.append(f"{path.name}: missing top-level key {key!r}")
    if "evaluations" in spec and not isinstance(spec["evaluations"], list):
        errors.append(f"{path.name}: evaluations must be a list")
    for index, evaluation in enumerate(spec.get("evaluations", [])):
        if not isinstance(evaluation, dict):
            errors.append(f"{path.name}: evaluation {index} must be an object")
            continue
        for key in ("id", "command", "result_file", "match", "expected_diagnostics"):
            if key not in evaluation:
                errors.append(f"{path.name}: evaluation {index} missing key {key!r}")
    fixture_name = spec.get("fixture")
    if isinstance(fixture_name, str) and not (FIXTURES_DIR / fixture_name).exists():
        errors.append(f"{path.name}: fixture {fixture_name!r} does not exist")
    return errors


def validate_scenario(path: Path, scenario: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("id", "prompt", "expected", "must_not", "rubric"):
        if key not in scenario:
            errors.append(f"{path.name}: missing key {key!r}")
    if not isinstance(scenario.get("expected"), dict):
        errors.append(f"{path.name}: expected must be an object")
    if not isinstance(scenario.get("must_not"), list):
        errors.append(f"{path.name}: must_not must be a list")
    if not isinstance(scenario.get("rubric"), list):
        errors.append(f"{path.name}: rubric must be a list")
    fixture_name = scenario.get("fixture")
    if isinstance(fixture_name, str) and not (FIXTURES_DIR / fixture_name).exists():
        errors.append(f"{path.name}: fixture {fixture_name!r} does not exist")
    return errors


def run_fixture_eval(
    cli: dict[str, Any] | None,
    expected_path: Path,
    spec: dict[str, Any],
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    result_id = f"{spec['id']}::{evaluation['id']}"
    fixture_dir = FIXTURES_DIR / spec["fixture"]
    base_result = {
        "type": "fixture",
        "id": result_id,
        "fixture": spec["fixture"],
        "expected_file": str(expected_path.relative_to(REPO_ROOT)),
        "command": evaluation["command"],
    }

    if cli is None:
        return {
            **base_result,
            "status": "failed",
            "reason": (
                "Agent Hub v3 deterministic CLI is missing. Expected local script "
                f"{LOCAL_AGENT_HUB_SCRIPT} or an agent-hub executable on PATH."
            ),
        }

    with isolated_fixture_dir(fixture_dir) as run_dir:
        command = [
            *cli["command"],
            "--hub-root",
            str(run_dir / ".hub"),
            *evaluation["command"],
        ]
        completed = subprocess.run(
            command,
            cwd=run_dir,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        command_result = {
            **base_result,
            "command": command,
            "returncode": completed.returncode,
            "stdout_tail": text_tail(completed.stdout),
            "stderr_tail": text_tail(completed.stderr),
        }
        if completed.returncode != 0:
            return {
                **command_result,
                "status": "failed",
                "reason": "Deterministic command exited nonzero.",
            }

        report_path = run_dir / evaluation["result_file"]
        if not report_path.exists():
            return {
                **command_result,
                "status": "failed",
                "reason": f"Expected report file was not produced: {report_path}",
            }

        try:
            payload = load_json(report_path)
        except json.JSONDecodeError as exc:
            return {
                **command_result,
                "status": "failed",
                "reason": f"Report file is not valid JSON: {exc}",
            }

    actual_diagnostics = extract_diagnostics(payload)
    expected_diagnostics = evaluation["expected_diagnostics"]
    passed, unmatched = compare_diagnostics(
        evaluation["match"], actual_diagnostics, expected_diagnostics
    )
    if not passed:
        return {
            **command_result,
            "status": "failed",
            "reason": "Diagnostics did not match expected contract.",
            "actual_diagnostics": actual_diagnostics,
            "unmatched_expected_diagnostics": unmatched,
        }

    return {
        **command_result,
        "status": "passed",
        "actual_diagnostic_count": len(actual_diagnostics),
    }


def normalize_scenario_outcome(outcome: Any) -> tuple[bool, dict[str, Any]]:
    if isinstance(outcome, bool):
        return outcome, {"passed": outcome}
    if isinstance(outcome, dict):
        if "passed" in outcome:
            return bool(outcome["passed"]), outcome
        if outcome.get("status") in {"passed", "pass"}:
            return True, outcome
        return False, outcome
    return False, {"reason": f"Unsupported scenario evaluator result: {type(outcome).__name__}"}


def call_scenario_evaluator(
    evaluator: Any, scenario: dict[str, Any], scenario_path: Path, fixture_dir: Path
) -> Any:
    try:
        return evaluator(
            scenario=scenario,
            scenario_path=scenario_path,
            fixture_dir=fixture_dir,
            repo_root=REPO_ROOT,
            eval_root=EVAL_ROOT,
        )
    except TypeError:
        try:
            return evaluator(scenario, fixture_dir, REPO_ROOT)
        except TypeError:
            return evaluator(scenario)


def run_scenario_eval(
    cli: dict[str, Any] | None,
    evaluator: dict[str, Any] | None,
    scenario_path: Path,
    scenario: dict[str, Any],
) -> dict[str, Any]:
    fixture_dir = FIXTURES_DIR / scenario.get("fixture", "")
    base_result = {
        "type": "scenario",
        "id": scenario["id"],
        "scenario_file": str(scenario_path.relative_to(REPO_ROOT)),
        "fixture": scenario.get("fixture"),
    }

    if evaluator is not None:
        with isolated_fixture_dir(fixture_dir) as run_dir:
            outcome = call_scenario_evaluator(
                evaluator["function"], scenario, scenario_path, run_dir
            )
        passed, details = normalize_scenario_outcome(outcome)
        return {
            **base_result,
            "status": "passed" if passed else "failed",
            "evaluator": evaluator["source"],
            "details": details,
        }

    if cli is None:
        return {
            **base_result,
            "status": "failed",
            "reason": (
                "Agent Hub v3 scenario evaluator is missing. Expected "
                "evals/scenario_adapter.py or "
                "skills/manage-agent-hub-issues/lib/agent_hub_scenarios.py with "
                "evaluate_scenario(...), or an agent-hub CLI with scenario eval support."
            ),
        }

    command = [*cli["command"], "scenario", "eval", str(scenario_path)]
    with isolated_fixture_dir(fixture_dir) as run_dir:
        completed = subprocess.run(
            command,
            cwd=run_dir if run_dir.exists() else REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    if completed.returncode != 0:
        return {
            **base_result,
            "status": "failed",
            "command": command,
            "returncode": completed.returncode,
            "stdout_tail": text_tail(completed.stdout),
            "stderr_tail": text_tail(completed.stderr),
            "reason": "Scenario eval command exited nonzero.",
        }

    try:
        outcome = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {
            **base_result,
            "status": "failed",
            "command": command,
            "stdout_tail": text_tail(completed.stdout),
            "stderr_tail": text_tail(completed.stderr),
            "reason": f"Scenario eval stdout was not JSON: {exc}",
        }

    passed, details = normalize_scenario_outcome(outcome)
    return {
        **base_result,
        "status": "passed" if passed else "failed",
        "command": command,
        "details": details,
    }


def collect_results() -> dict[str, Any]:
    cli = find_agent_hub_cli()
    scenario_evaluator = load_scenario_evaluator()
    results: list[dict[str, Any]] = []

    for expected_path in sorted(EXPECTED_DIR.glob("*.json")):
        try:
            spec = load_json(expected_path)
        except json.JSONDecodeError as exc:
            results.append(
                {
                    "type": "fixture",
                    "id": expected_path.stem,
                    "status": "failed",
                    "reason": f"Expected file is not valid JSON: {exc}",
                }
            )
            continue

        errors = validate_expected_spec(expected_path, spec)
        if errors:
            results.append(
                {
                    "type": "fixture",
                    "id": spec.get("id", expected_path.stem),
                    "status": "failed",
                    "reason": "Invalid expected spec.",
                    "errors": errors,
                }
            )
            continue

        for evaluation in spec["evaluations"]:
            results.append(run_fixture_eval(cli, expected_path, spec, evaluation))

    for scenario_path in sorted(SCENARIOS_DIR.glob("*.json")):
        try:
            scenario = load_json(scenario_path)
        except json.JSONDecodeError as exc:
            results.append(
                {
                    "type": "scenario",
                    "id": scenario_path.stem,
                    "status": "failed",
                    "reason": f"Scenario file is not valid JSON: {exc}",
                }
            )
            continue

        errors = validate_scenario(scenario_path, scenario)
        if errors:
            results.append(
                {
                    "type": "scenario",
                    "id": scenario.get("id", scenario_path.stem),
                    "status": "failed",
                    "reason": "Invalid scenario spec.",
                    "errors": errors,
                }
            )
            continue

        results.append(run_scenario_eval(cli, scenario_evaluator, scenario_path, scenario))

    passed = sum(1 for result in results if result["status"] == "passed")
    failed = sum(1 for result in results if result["status"] == "failed")
    report = {
        "generated_at": utc_now(),
        "repo_root": str(REPO_ROOT),
        "implementation": {
            "agent_hub_cli": None
            if cli is None
            else {"kind": cli["kind"], "source": cli["source"]},
            "scenario_evaluator": None
            if scenario_evaluator is None
            else {"source": scenario_evaluator["source"]},
        },
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
        },
        "results": results,
    }
    return report


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Agent Hub v3 Eval Report",
        "",
        f"Generated: {report['generated_at']}",
        f"Repository: `{report['repo_root']}`",
        "",
        "## Summary",
        "",
        f"- Total: {report['summary']['total']}",
        f"- Passed: {report['summary']['passed']}",
        f"- Failed: {report['summary']['failed']}",
        "",
        "## Implementation",
        "",
        f"- Agent Hub CLI: `{report['implementation']['agent_hub_cli']}`",
        f"- Scenario evaluator: `{report['implementation']['scenario_evaluator']}`",
        "",
        "## Results",
        "",
    ]
    for result in report["results"]:
        status = result["status"].upper()
        lines.append(f"- {status} `{result['type']}::{result['id']}`")
        if result.get("reason"):
            lines.append(f"  Reason: {result['reason']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_summary(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(
        "Agent Hub v3 evals: "
        f"{summary['passed']} passed, {summary['failed']} failed, {summary['total']} total"
    )
    print(f"JSON report: {REPORTS_DIR / 'latest-eval-report.json'}")
    print(f"Markdown report: {REPORTS_DIR / 'latest-eval-report.md'}")
    if summary["failed"]:
        print("")
        print("Failures:")
        for result in report["results"]:
            if result["status"] != "failed":
                continue
            reason = result.get("reason", "No reason recorded.")
            print(f"- {result['type']}::{result['id']}: {reason}")


def main() -> int:
    report = collect_results()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    write_json(REPORTS_DIR / "latest-eval-report.json", report)
    write_markdown_report(REPORTS_DIR / "latest-eval-report.md", report)
    print_summary(report)
    return 1 if report["summary"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
