#!/usr/bin/env python3
"""Initialize a central Agent Hub."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

COMMON_LIB = Path(__file__).resolve().parents[2] / "manage-agent-hub-issues" / "lib"
sys.path.insert(0, str(COMMON_LIB))

from agent_hub_common import find_repo_root  # noqa: E402
from file_hub_common import create_central_hub, create_issue_file  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo", type=Path, default=Path.cwd(), help="Repository root or path inside it."
    )
    parser.add_argument("--project-name", help="Project name to write into central config.yml.")
    parser.add_argument(
        "--seed-issue",
        help="Optional first issue title to create under the central hub issues directory.",
    )
    parser.add_argument("--seed-issue-id", help="Optional ID for --seed-issue.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = find_repo_root(args.repo) or args.repo.expanduser().resolve()
    hub = create_central_hub(repo, args.project_name)
    print(f"OK: initialized central Agent Hub at {hub}")
    if args.seed_issue:
        issue = create_issue_file(hub, args.seed_issue, args.seed_issue_id)
        print(f"OK: created seed issue {issue.id} at {issue.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
