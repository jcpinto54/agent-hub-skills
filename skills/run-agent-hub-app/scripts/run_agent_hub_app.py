#!/usr/bin/env python3
"""Export and serve the local read-only Agent Hub viewer."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

COMMON_LIB = Path(__file__).resolve().parents[2] / "manage-agent-hub-issues" / "lib"
sys.path.insert(0, str(COMMON_LIB))

from file_hub_common import resolve_hub_path  # noqa: E402


def skill_paths() -> tuple[Path, Path, Path]:
    skill_dir = Path(__file__).resolve().parents[1]
    skills_dir = skill_dir.parent
    viewer_dir = skills_dir / "list-agent-hub-issues" / "viewer"
    agent_hub_script = skills_dir / "manage-agent-hub-issues" / "scripts" / "agent_hub.py"
    return skill_dir, viewer_dir, agent_hub_script


def port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


def fetch_hub_snapshot(host: str, port: int) -> dict[str, Any] | None:
    url = f"http://{host}:{port}/api/state"
    try:
        with urllib.request.urlopen(url, timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def is_hub_snapshot_payload(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    return (
        payload.get("version") == "3"
        and isinstance(payload.get("columns"), list)
        and isinstance(payload.get("summary"), dict)
        and isinstance(payload.get("revision"), dict)
    )


def serves_hub_snapshot(host: str, port: int) -> bool:
    return is_hub_snapshot_payload(fetch_hub_snapshot(host, port))


def serves_expected_hub_snapshot(host: str, port: int, expected: dict[str, Any]) -> bool:
    payload = fetch_hub_snapshot(host, port)
    if not is_hub_snapshot_payload(payload):
        return False
    expected_revision = str(expected.get("revision", {}).get("id") or "")
    actual_revision = str(payload.get("revision", {}).get("id") or "")
    return bool(expected_revision and actual_revision == expected_revision)


def choose_port(
    host: str, requested_port: int, expected_snapshot: dict[str, Any] | None = None
) -> tuple[int, bool]:
    if not port_is_open(host, requested_port):
        return requested_port, False
    if expected_snapshot:
        if serves_expected_hub_snapshot(host, requested_port, expected_snapshot):
            return requested_port, True
    elif serves_hub_snapshot(host, requested_port):
        return requested_port, True
    for port in range(requested_port + 1, requested_port + 51):
        if not port_is_open(host, port):
            return port, False
    raise RuntimeError(f"No free local port found near {requested_port}.")


def runtime_dir(repo: Path, hub_root: Path | None = None) -> Path:
    hub_runtime = resolve_hub_path(start=repo, hub_root=hub_root) / "runtime" / "agent-hub-app"
    hub_runtime.mkdir(parents=True, exist_ok=True)
    return hub_runtime


def agent_hub_base_command(repo: Path, agent_hub_script: Path, hub_root: Path | None) -> list[str]:
    if agent_hub_script.exists():
        command = [sys.executable, str(agent_hub_script), "--repo", str(repo)]
    else:
        command = ["agent-hub", "--repo", str(repo)]
    if hub_root:
        command.extend(["--hub-root", str(hub_root)])
    return command


def export_snapshot(
    repo: Path,
    change: str,
    output: Path,
    agent_hub_script: Path,
    hub_root: Path | None = None,
) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        *agent_hub_base_command(repo, agent_hub_script, hub_root),
        "dashboard",
        "export",
        "--output",
        str(output),
    ]
    if change:
        command.extend(["--change", change])

    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "dashboard export failed").strip())
    return json.loads(result.stdout or "{}")


def build_serve_command(
    host: str,
    port: int,
    repo: Path,
    change: str,
    agent_hub_script: Path,
    hub_root: Path | None = None,
) -> list[str]:
    command = [*agent_hub_base_command(repo, agent_hub_script, hub_root), "dashboard", "serve"]
    if change:
        command.extend(["--change", change])
    command.extend(["--host", host, "--port", str(port)])
    return command


def start_background_server(
    host: str,
    port: int,
    viewer_dir: Path,
    run_dir: Path,
    repo: Path,
    change: str,
    agent_hub_script: Path,
    hub_root: Path | None = None,
) -> subprocess.Popen[str]:
    del viewer_dir
    log_path = run_dir / "server.log"
    log_file = log_path.open("ab")
    command = build_serve_command(host, port, repo, change, agent_hub_script, hub_root)
    try:
        process = subprocess.Popen(
            command,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        log_file.close()
    (run_dir / "server.pid").write_text(f"{process.pid}\n", encoding="utf-8")
    return process


def wait_for_server(host: str, port: int, process: subprocess.Popen[str] | None) -> None:
    for _ in range(30):
        if port_is_open(host, port):
            return
        if process is not None and process.poll() is not None:
            raise RuntimeError(f"server exited early with status {process.returncode}")
        time.sleep(0.1)
    raise RuntimeError(f"server did not start on {host}:{port}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Target repo or worktree.")
    parser.add_argument("--hub-root", type=Path, help="Explicit hub directory override.")
    parser.add_argument(
        "--change", default="", help="Optional change slug to filter the dashboard."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host for the local viewer.")
    parser.add_argument("--port", type=int, default=8765, help="Port for the local viewer.")
    parser.add_argument(
        "--foreground", action="store_true", help="Run the HTTP server in the foreground."
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repo = args.repo.expanduser().resolve()
    _, viewer_dir, agent_hub_script = skill_paths()
    if not viewer_dir.exists():
        print(f"Viewer directory not found: {viewer_dir}", file=sys.stderr)
        return 1
    try:
        run_dir = runtime_dir(repo, args.hub_root)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    snapshot_path = viewer_dir / "hub-state.json"
    try:
        export_payload = export_snapshot(
            repo, args.change, snapshot_path, agent_hub_script, args.hub_root
        )
        expected_snapshot = json.loads(snapshot_path.read_text(encoding="utf-8") or "{}")
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        port, reused = choose_port(args.host, args.port, expected_snapshot)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    url = f"http://{args.host}:{port}"
    if args.foreground:
        if reused:
            print(
                json.dumps(
                    {"ok": True, "url": url, "snapshot": str(snapshot_path), "server": "reused"}
                )
            )
            return 0
        print(
            json.dumps(
                {"ok": True, "url": url, "snapshot": str(snapshot_path), "foreground": True}
            )
        )
        command = build_serve_command(
            args.host, port, repo, args.change, agent_hub_script, args.hub_root
        )
        os.execvp(command[0], command)

    process = None
    if not reused:
        process = start_background_server(
            args.host,
            port,
            viewer_dir,
            run_dir,
            repo,
            args.change,
            agent_hub_script,
            args.hub_root,
        )
        wait_for_server(args.host, port, process)

    response = {
        "ok": True,
        "url": url,
        "repo": str(repo),
        "change": args.change,
        "snapshot": str(snapshot_path),
        "server": "reused" if reused else "started",
        "pid": None if reused else process.pid if process else None,
        "port": port,
        "requested_port": args.port,
        "export": export_payload,
    }
    print(json.dumps(response, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
