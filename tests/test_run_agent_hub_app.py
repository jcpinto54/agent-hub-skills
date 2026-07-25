from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
COMMON_LIB = ROOT / "skills/manage-agent-hub-issues/lib"
RUNNER_PATH = ROOT / "skills/run-agent-hub-app/scripts/run_agent_hub_app.py"
sys.path.insert(0, str(COMMON_LIB))

import file_hub_common as file_hub  # noqa: E402


def load_runner():
    spec = importlib.util.spec_from_file_location("run_agent_hub_app_tests", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["run_agent_hub_app_tests"] = module
    spec.loader.exec_module(module)
    return module


runner = load_runner()


class RunAgentHubAppTests(unittest.TestCase):
    def test_runtime_dir_uses_central_hub_runtime(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = root / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            agent_hub_home = root / "agent-hub-home"

            with mock.patch.dict(runner.os.environ, {"AGENT_HUB_HOME": str(agent_hub_home)}):
                hub = file_hub.create_central_hub(repo, "Runner Project")
                run_dir = runner.runtime_dir(repo)

            self.assertEqual(run_dir, hub / "runtime" / "agent-hub-app")
            self.assertTrue(run_dir.is_dir())
            self.assertFalse((repo / ".hub").exists())

    def test_runtime_dir_accepts_explicit_hub_root_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = root / "repo"
            repo.mkdir()
            explicit_hub = file_hub.create_hub(root / "explicit", "Explicit Project")

            run_dir = runner.runtime_dir(repo, explicit_hub)

            self.assertEqual(run_dir, explicit_hub / "runtime" / "agent-hub-app")
            self.assertTrue(run_dir.is_dir())

    def test_background_server_prefers_live_dashboard_serve_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = root / "repo"
            viewer_dir = root / "viewer"
            run_dir = root / "runtime"
            agent_hub_script = root / "skills/manage-agent-hub-issues/scripts/agent_hub.py"
            repo.mkdir()
            viewer_dir.mkdir()
            run_dir.mkdir()
            agent_hub_script.parent.mkdir(parents=True)
            agent_hub_script.write_text("# cli\n", encoding="utf-8")

            with mock.patch.object(runner.subprocess, "Popen") as popen:
                popen.return_value.pid = 123
                process = runner.start_background_server(
                    "127.0.0.1",
                    8765,
                    viewer_dir,
                    run_dir,
                    repo,
                    "live-change",
                    agent_hub_script,
                )

        self.assertIs(process, popen.return_value)
        command = popen.call_args.args[0]
        self.assertEqual(command[:5], [sys.executable, str(agent_hub_script), "--repo", str(repo), "dashboard"])
        self.assertIn("serve", command)
        self.assertIn("--change", command)
        self.assertIn("live-change", command)
        self.assertNotIn("http.server", command)

    def test_background_server_forwards_hub_root_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = root / "repo"
            viewer_dir = root / "viewer"
            run_dir = root / "runtime"
            explicit_hub = root / "explicit" / ".hub"
            agent_hub_script = root / "skills/manage-agent-hub-issues/scripts/agent_hub.py"
            repo.mkdir()
            viewer_dir.mkdir()
            run_dir.mkdir()
            agent_hub_script.parent.mkdir(parents=True)
            agent_hub_script.write_text("# cli\n", encoding="utf-8")

            with mock.patch.object(runner.subprocess, "Popen") as popen:
                popen.return_value.pid = 123
                runner.start_background_server(
                    "127.0.0.1",
                    8765,
                    viewer_dir,
                    run_dir,
                    repo,
                    "live-change",
                    agent_hub_script,
                    explicit_hub,
                )

        command = popen.call_args.args[0]
        self.assertLess(command.index("--hub-root"), command.index("dashboard"))
        self.assertIn(str(explicit_hub), command)

    def test_export_snapshot_forwards_hub_root_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = root / "repo"
            output = root / "snapshot.json"
            explicit_hub = root / "explicit" / ".hub"
            agent_hub_script = root / "skills/manage-agent-hub-issues/scripts/agent_hub.py"
            repo.mkdir()
            agent_hub_script.parent.mkdir(parents=True)
            agent_hub_script.write_text("# cli\n", encoding="utf-8")

            completed = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout='{"ok": true}\n',
                stderr="",
            )
            with mock.patch.object(runner.subprocess, "run", return_value=completed) as run:
                payload = runner.export_snapshot(
                    repo,
                    "live-change",
                    output,
                    agent_hub_script,
                    explicit_hub,
                )

        self.assertEqual(payload, {"ok": True})
        command = run.call_args.args[0]
        self.assertLess(command.index("--hub-root"), command.index("dashboard"))
        self.assertIn(str(explicit_hub), command)

    def test_export_snapshot_writes_revision_that_allows_matching_server_reuse(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = root / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            agent_hub_home = root / "agent-hub-home"
            output = root / "snapshot.json"
            agent_hub_script = ROOT / "skills/manage-agent-hub-issues/scripts/agent_hub.py"

            with mock.patch.dict(runner.os.environ, {"AGENT_HUB_HOME": str(agent_hub_home)}):
                hub = file_hub.create_central_hub(repo, "Runner Project")
                file_hub.create_issue_file(hub, "Runner Issue", "runner-issue")
                runner.export_snapshot(repo, "", output, agent_hub_script)

            snapshot = runner.json.loads(output.read_text(encoding="utf-8"))
            revision = snapshot["revision"]["id"]
            body = runner.json.dumps(snapshot).encode("utf-8")

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return body

        self.assertTrue(revision)
        with (
            mock.patch.object(runner.urllib.request, "urlopen", return_value=Response()),
            mock.patch.object(runner, "port_is_open", return_value=True),
        ):
            self.assertEqual(runner.choose_port("127.0.0.1", 8765, snapshot), (8765, True))

    def test_reused_live_server_is_detected_by_state_api(self):
        state = {
            "version": "3",
            "columns": [],
            "summary": {},
            "revision": {"id": "rev-1"},
        }
        body = runner.json.dumps(state).encode("utf-8")

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return body

        with mock.patch.object(runner.urllib.request, "urlopen", return_value=Response()) as urlopen:
            self.assertTrue(runner.serves_hub_snapshot("127.0.0.1", 8765))

        self.assertEqual(urlopen.call_args.args[0], "http://127.0.0.1:8765/api/state")

    def test_choose_port_does_not_reuse_server_with_different_revision(self):
        state = {
            "version": "3",
            "columns": [],
            "summary": {},
            "revision": {"id": "old-revision"},
        }
        body = runner.json.dumps(state).encode("utf-8")

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return body

        expected = {"revision": {"id": "new-revision"}}
        with (
            mock.patch.object(runner.urllib.request, "urlopen", return_value=Response()),
            mock.patch.object(runner, "port_is_open", side_effect=[True, False]),
        ):
            self.assertEqual(runner.choose_port("127.0.0.1", 8765, expected), (8766, False))

    def test_choose_port_reuses_server_with_matching_revision(self):
        state = {
            "version": "3",
            "columns": [],
            "summary": {},
            "revision": {"id": "same-revision"},
        }
        body = runner.json.dumps(state).encode("utf-8")

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return body

        expected = {"revision": {"id": "same-revision"}}
        with (
            mock.patch.object(runner.urllib.request, "urlopen", return_value=Response()),
            mock.patch.object(runner, "port_is_open", return_value=True),
        ):
            self.assertEqual(runner.choose_port("127.0.0.1", 8765, expected), (8765, True))


if __name__ == "__main__":
    unittest.main()
