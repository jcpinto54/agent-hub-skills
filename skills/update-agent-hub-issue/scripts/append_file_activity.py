#!/usr/bin/env python3
"""Append an activity or review entry to a central Agent Hub issue."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

COMMON_LIB = Path(__file__).resolve().parents[2] / "manage-agent-hub-issues" / "lib"
sys.path.insert(0, str(COMMON_LIB))

from file_hub_common import issue_by_id, isoformat, now_utc, resolve_hub_path  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hub-root", type=Path)
    parser.add_argument("--issue", required=True, help="Issue ID.")
    parser.add_argument("--heading", default="Progress")
    parser.add_argument("--agent", default="Codex")
    parser.add_argument("--summary", required=True)
    parser.add_argument("--evidence", default="")
    parser.add_argument("--verification", default="")
    parser.add_argument("--risks", default="")
    parser.add_argument("--next-step", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    hub = resolve_hub_path(hub_root=args.hub_root)
    issue = issue_by_id(hub, args.issue)
    lines = [
        f"Date: {isoformat(now_utc())}",
        f"Agent: {args.agent}",
        f"Summary: {args.summary}",
        f"Evidence: {args.evidence or '-'}",
        f"Verification: {args.verification or '-'}",
        f"Risks / skipped checks: {args.risks or '-'}",
        f"Next step: {args.next_step or '-'}",
    ]
    issue.append_activity(args.heading, lines)
    print(f"OK: appended {args.heading!r} to {issue.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
