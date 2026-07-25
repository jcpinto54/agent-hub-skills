#!/usr/bin/env python3
"""Create a central Agent Hub issue file."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

COMMON_LIB = Path(__file__).resolve().parents[2] / "manage-agent-hub-issues" / "lib"
sys.path.insert(0, str(COMMON_LIB))

from file_hub_common import create_issue_file, resolve_hub_path  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("title")
    parser.add_argument("--id", dest="issue_id")
    parser.add_argument("--type", default="Feature")
    parser.add_argument("--priority", default="P2", choices=["P0", "P1", "P2", "P3"])
    parser.add_argument("--hub-root", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    hub = resolve_hub_path(hub_root=args.hub_root)
    issue = create_issue_file(hub, args.title, args.issue_id, args.type, args.priority)
    print(f"OK: created {issue.id} at {issue.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
