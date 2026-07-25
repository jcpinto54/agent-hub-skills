#!/usr/bin/env python3
"""List Agent Hub issues and compute dependency-aware readiness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

COMMON_LIB = Path(__file__).resolve().parents[2] / "manage-agent-hub-issues" / "lib"
sys.path.insert(0, str(COMMON_LIB))

from agent_hub_common import STATUS_ORDER  # noqa: E402
from file_hub_common import (  # noqa: E402
    issue_sort_key as file_issue_sort_key,
    load_change,
    load_issues as load_file_issues,
    readiness as file_readiness,
    resolve_hub_path,
)


def apply_filters(
    issues: list[Any], by_id: dict[str, Any], args: argparse.Namespace
) -> list[tuple[Any, str, str]]:
    rows: list[tuple[Any, str, str]] = []
    for issue in issues:
        ready, reason = file_readiness(issue, by_id)
        if getattr(args, "change", None) and issue.change != args.change:
            continue
        if args.status and issue.status != args.status:
            continue
        if args.owner and args.owner.lower() not in issue.owner.lower():
            continue
        if args.priority and issue.priority != args.priority:
            continue
        if args.type and issue.type != args.type:
            continue
        if args.area and args.area.lower() not in issue.area.lower():
            continue
        if args.readiness and ready.lower() != args.readiness.lower():
            continue
        rows.append((issue, ready, reason))
    return rows


def short(value: str, limit: int = 48) -> str:
    value = " ".join(value.split())
    if not value:
        return "-"
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "..."


def dependency_titles(ids: list[str], by_id: dict[str, Any]) -> str:
    if not ids:
        return "-"
    return ", ".join(short(by_id.get(item_id).title if item_id in by_id else item_id, 28) for item_id in ids)


def render_board(
    lines: list[str],
    title: str,
    rows: list[tuple[Any, str, str]],
    by_id: dict[str, Any],
    start_number: int,
) -> int:
    lines.append(f"### {title}")
    if not rows:
        lines.append("No issues.")
        lines.append("")
        return start_number

    lines.append("| # | Issue | Status | Owner | Priority | Type | Depends On | Reason |")
    lines.append("|---|---|---|---|---|---|---|---|")
    number = start_number
    for issue, ready, reason in rows:
        title_text = short(issue.title, 56)
        linked = f"[{title_text}]({issue.url})" if issue.url else title_text
        reason_text = issue.blockers or reason or ready
        lines.append(
            f"| {number} | {linked} | {short(issue.status, 18)} | {short(issue.owner)} | "
            f"{short(issue.priority, 12)} | {short(issue.type, 18)} | "
            f"{dependency_titles(issue.depends_on, by_id)} | {short(reason_text, 44)} |"
        )
        number += 1
    lines.append("")
    return number


def markdown(
    rows: list[tuple[Any, str, str]],
    by_id: dict[str, Any],
    limit: int,
    change: str = "",
) -> str:
    counts = {status: 0 for status in STATUS_ORDER}
    for issue, _, _ in rows:
        if issue.status in counts:
            counts[issue.status] += 1

    eligible_not_started_rows = [row for row in rows if row[0].status == "Not Started" and row[1] == "Ready"]
    eligible_in_review_rows = [row for row in rows if row[0].status == "In Review" and row[1] == "Ready"]
    blocked_rows = [row for row in rows if row[1] in {"Blocked", "Unknown"}]
    eligible_not_started_visible = eligible_not_started_rows[:limit]
    eligible_in_review_visible = eligible_in_review_rows[:limit]
    blocked_visible = blocked_rows[:limit]
    lines = ["## Agent Hub Issues", ""]
    if change:
        lines.append(f"Change filter: `{change}`")
        lines.append("")
    lines.append(
        "Counts: "
        + " | ".join(f"{status} `{counts[status]}`" for status in STATUS_ORDER)
    )
    lines.append("")
    lines.append(
        f"Eligible to pick up: Not Started `{len(eligible_not_started_rows)}` | "
        f"In Review `{len(eligible_in_review_rows)}` | "
        f"Blocked: `{len(blocked_rows)}` | Completed: `{counts['Completed']}`"
    )
    lines.append("")

    number = 1
    number = render_board(lines, "Eligible (Not Started)", eligible_not_started_visible, by_id, number)
    number = render_board(lines, "Eligible (In Review)", eligible_in_review_visible, by_id, number)
    number = render_board(lines, "Blocked", blocked_visible, by_id, number)

    if len(eligible_not_started_rows) > limit:
        lines.append(
            f"Showing {limit} of {len(eligible_not_started_rows)} eligible Not Started issues. "
            "Increase --limit to see more."
        )
    if len(eligible_in_review_rows) > limit:
        lines.append(
            f"Showing {limit} of {len(eligible_in_review_rows)} eligible In Review issues. "
            "Increase --limit to see more."
        )
    if len(blocked_rows) > limit:
        lines.append(
            f"Showing {limit} of {len(blocked_rows)} blocked issues. Increase --limit to see more."
        )
    lines.append("")
    lines.append("Use iterate-agent-hub-work to spawn subagents for eligible issues.")
    return "\n".join(lines).rstrip() + "\n"


def json_rows(rows: list[tuple[Any, str, str]], by_id: dict[str, Any], limit: int | None = None) -> str:
    payload = []
    visible_rows = rows[:limit] if limit is not None else rows
    for issue, ready, reason in visible_rows:
        payload.append(
            {
                "id": issue.id,
                "url": issue.url,
                "title": issue.title,
                "status": issue.status,
                "owner": issue.owner,
                "priority": issue.priority,
                "change": getattr(issue, "change", ""),
                "type": issue.type,
                "area": issue.area,
                "summary": issue.summary,
                "blockers": issue.blockers,
                "depends_on": [
                    {"id": dep_id, "title": by_id[dep_id].title if dep_id in by_id else None}
                    for dep_id in issue.depends_on
                ],
                "blocks": [
                    {"id": block_id, "title": by_id[block_id].title if block_id in by_id else None}
                    for block_id in issue.blocks
                ],
                "readiness": ready,
                "readiness_reason": reason,
                "claim_id": issue.claim_id,
                "claim_expires_at": issue.claim_expires_at.isoformat()
                if issue.claim_expires_at
                else "",
                "updated_at": issue.updated_at.isoformat() if issue.updated_at else "",
            }
        )
    return json.dumps(payload, indent=2, sort_keys=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["auto", "file"], default="auto")
    parser.add_argument("--hub-root", type=Path, help="Explicit hub directory override.")
    parser.add_argument("--status", choices=STATUS_ORDER)
    parser.add_argument("--owner")
    parser.add_argument("--priority", choices=["P0", "P1", "P2", "P3"])
    parser.add_argument("--change", help="Change packet slug to filter by.")
    parser.add_argument("--type")
    parser.add_argument("--area")
    parser.add_argument("--readiness", choices=["Ready", "Blocked", "Unknown"])
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--limit", type=int, default=30)
    return parser


def load_file_rows(args: argparse.Namespace) -> tuple[list[tuple[Any, str, str]], dict[str, Any]]:
    hub_path = resolve_hub_path(hub_root=args.hub_root)
    if args.change:
        try:
            load_change(hub_path, args.change)
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
    issues = load_file_issues(hub_path)
    issues.sort(key=file_issue_sort_key)
    by_id = {issue.id: issue for issue in issues}
    return apply_filters(issues, by_id, args), by_id


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    rows, by_id = load_file_rows(args)
    if args.format == "json":
        print(json_rows(rows, by_id, args.limit))
    else:
        print(markdown(rows, by_id, args.limit, args.change or ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
