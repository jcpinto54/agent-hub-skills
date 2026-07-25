#!/usr/bin/env python3
"""Claim, check, renew, and release Agent Hub ownership leases."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

WORK_RELEASE_MODES = {"abandon", "handoff", "blocked", "submitted"}
REVIEW_RELEASE_MODES = {"review-pass", "review-fail", "review-abandon"}

COMMON_LIB = Path(__file__).resolve().parents[2] / "manage-agent-hub-issues" / "lib"
sys.path.insert(0, str(COMMON_LIB))

from file_hub_common import (  # noqa: E402
    check_issue as file_check_issue,
    claim_issue as file_claim_issue,
    issue_by_id as file_issue_by_id,
    release_issue as file_release_issue,
    renew_issue as file_renew_issue,
    resolve_hub_path,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    backend_kwargs = {
        "choices": ["auto", "file"],
        "help": "Use central file-backed Agent Hub state.",
    }
    parser.add_argument("--backend", default="auto", **backend_kwargs)
    parser.add_argument(
        "--hub-root", type=Path, help="Explicit hub directory override."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    claim = subparsers.add_parser("claim")
    claim.add_argument("--backend", default=argparse.SUPPRESS, **backend_kwargs)
    claim.add_argument("--hub-root", type=Path, default=argparse.SUPPRESS)
    claim.add_argument("--page-id", required=True)
    claim.add_argument("--purpose", choices=["work", "review"], required=True)
    claim.add_argument("--owner", required=True)
    claim.add_argument("--ttl-minutes", type=int, default=120)
    claim.add_argument("--claim-id")
    claim.add_argument("--base-branch")
    claim.add_argument("--branch")
    claim.add_argument("--worktree-path")
    claim.add_argument("--allow-missing-artifacts", action="store_true")

    check = subparsers.add_parser("check")
    check.add_argument("--backend", default=argparse.SUPPRESS, **backend_kwargs)
    check.add_argument("--hub-root", type=Path, default=argparse.SUPPRESS)
    check.add_argument("--page-id", required=True)
    check.add_argument("--claim-id")

    renew = subparsers.add_parser("renew")
    renew.add_argument("--backend", default=argparse.SUPPRESS, **backend_kwargs)
    renew.add_argument("--hub-root", type=Path, default=argparse.SUPPRESS)
    renew.add_argument("--page-id", required=True)
    renew.add_argument("--claim-id", required=True)
    renew.add_argument("--ttl-minutes", type=int, default=120)

    release = subparsers.add_parser("release")
    release.add_argument("--backend", default=argparse.SUPPRESS, **backend_kwargs)
    release.add_argument("--hub-root", type=Path, default=argparse.SUPPRESS)
    release.add_argument("--page-id", required=True)
    release.add_argument("--claim-id", required=True)
    release.add_argument(
        "--mode",
        choices=sorted(WORK_RELEASE_MODES | REVIEW_RELEASE_MODES),
        required=True,
    )
    release.add_argument("--owner")
    release.add_argument("--blocker")
    release.add_argument("--commit-sha")
    release.add_argument("--pr-url")
    return parser


def command_file(args: argparse.Namespace) -> dict[str, Any]:
    hub_path = resolve_hub_path(hub_root=args.hub_root)
    issue = file_issue_by_id(hub_path, args.page_id)
    if args.command == "claim":
        return file_claim_issue(
            hub_path=hub_path,
            issue=issue,
            purpose=args.purpose,
            owner=args.owner,
            ttl_minutes=args.ttl_minutes,
            claim_id=args.claim_id or f"{args.purpose}-{uuid.uuid4()}",
            base_branch=args.base_branch or "",
            branch=args.branch or "",
            worktree_path=args.worktree_path or "",
            allow_missing_artifacts=args.allow_missing_artifacts,
        )
    if args.command == "check":
        return file_check_issue(hub_path, issue, args.claim_id or "")
    if args.command == "renew":
        return file_renew_issue(hub_path, issue, args.claim_id, args.ttl_minutes)
    if args.command == "release":
        return file_release_issue(
            hub_path=hub_path,
            issue=issue,
            claim_id=args.claim_id,
            mode=args.mode,
            owner=args.owner or "",
            blocker=args.blocker or "",
            commit_sha=args.commit_sha or "",
            pr_url=args.pr_url or "",
        )
    raise SystemExit(f"Unknown command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = command_file(args)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
