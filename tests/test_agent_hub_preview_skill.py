from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_repo_file(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class AgentHubPreviewSkillTests(unittest.TestCase):
    def test_run_loop_delegates_preview_verification_before_review(self):
        text = read_repo_file("skills/run-agent-hub-loop/SKILL.md")

        self.assertIn("$verify-agent-hub-pr-preview", text)
        self.assertIn("preview-verification subagent", text)

        preview_index = text.index("$verify-agent-hub-pr-preview")
        review_index = text.index("List ready review issues")
        self.assertLess(preview_index, review_index)

    def test_run_loop_does_not_document_missing_sync_merged_prs_command(self):
        text = read_repo_file("skills/run-agent-hub-loop/SKILL.md")

        self.assertNotIn("state sync-merged-prs", text)

    def test_preview_skill_contract_records_browser_evidence_without_review_decision(self):
        text = read_repo_file("skills/verify-agent-hub-pr-preview/SKILL.md")

        required_phrases = [
            "name: verify-agent-hub-pr-preview",
            "PR URL",
            "Preview URL",
            "browser-capable",
            "done criteria",
            "console errors",
            "network failures",
            "$update-agent-hub-issue",
            "no-preview rationale",
            "Do not implement code",
            "Do not mark review pass/fail",
        ]
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

        self.assertNotIn("--mode review-pass", text)
        self.assertNotIn("--mode review-fail", text)

    def test_shared_policy_names_preview_skill_as_review_prerequisite(self):
        router_policy = read_repo_file(
            "skills/manage-agent-hub-issues/references/v3-router-policy.md"
        )
        workflows = read_repo_file("skills/manage-agent-hub-issues/references/v3-workflows.md")

        for text in (router_policy, workflows):
            with self.subTest():
                self.assertIn("$verify-agent-hub-pr-preview", text)
                self.assertIn("no-preview rationale", text)


if __name__ == "__main__":
    unittest.main()
