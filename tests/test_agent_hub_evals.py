from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = ROOT / "evals"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run_evals = load_module("agent_hub_run_evals_tests", EVAL_ROOT / "run_evals.py")
scenario_adapter = load_module(
    "agent_hub_scenario_adapter_tests", EVAL_ROOT / "scenario_adapter.py"
)


class AgentHubEvalTests(unittest.TestCase):
    def test_fixture_eval_uses_repo_local_fixture_as_explicit_hub_root(self):
        expected_path = EVAL_ROOT / "expected" / "valid-lite-hub.json"
        spec = json.loads(expected_path.read_text(encoding="utf-8"))

        result = run_evals.run_fixture_eval(
            run_evals.find_agent_hub_cli(),
            expected_path,
            spec,
            spec["evaluations"][0],
        )

        self.assertEqual(result["status"], "passed", result)
        hub_root_index = result["command"].index("--hub-root")
        self.assertEqual(
            Path(result["command"][hub_root_index + 1]).name,
            ".hub",
        )
        self.assertLess(hub_root_index, result["command"].index("audit"))

    def test_central_hub_policy_scenarios_match_current_policy(self):
        scenario_ids = {
            "packet-loop-preview-verification",
            "packet-loop-stops-on-analysis-errors",
            "resolver-delegates-substantive-tasks",
            "resolver-refuses-manual-rewrites",
            "resolver-routes-mutations",
        }

        for scenario_path in sorted((EVAL_ROOT / "scenarios").glob("*.json")):
            scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
            if scenario["id"] not in scenario_ids:
                continue
            with self.subTest(scenario=scenario["id"]):
                result = scenario_adapter.evaluate_scenario(
                    scenario=scenario,
                    scenario_path=scenario_path,
                    fixture_dir=EVAL_ROOT / "fixtures" / scenario["fixture"],
                    repo_root=ROOT,
                    eval_root=EVAL_ROOT,
                )
                self.assertTrue(result["passed"], result)


if __name__ == "__main__":
    unittest.main()
