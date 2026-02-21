#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import doc_apply  # noqa: E402
import doc_metadata as dm  # noqa: E402
import language_profiles as lp  # noqa: E402


class DocApplySectionActionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "docs").mkdir(parents=True, exist_ok=True)
        self.language = {
            "primary": "zh-CN",
            "profile": "zh-CN",
            "locked": False,
            "source": "test",
        }
        self.profile = "zh-CN"
        self.metadata_policy = dm.resolve_metadata_policy(lp.build_default_policy())

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _apply(self, action: dict[str, object]) -> dict[str, object]:
        return doc_apply.apply_action(
            self.root,
            action,
            dry_run=False,
            language_settings=self.language,
            template_profile=self.profile,
            metadata_policy=self.metadata_policy,
        )

    def test_update_section_adds_missing_section(self) -> None:
        runbook = self.root / "docs/runbook.md"
        runbook.write_text(
            "\n\n".join(
                [
                    lp.get_section_text("docs/runbook.md", "title", self.profile).strip(),
                    lp.get_section_text(
                        "docs/runbook.md", "dev_commands", self.profile
                    ).strip(),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        result = self._apply(
            {
                "id": "A001",
                "type": "update_section",
                "path": "docs/runbook.md",
                "section_id": "validation_commands",
            }
        )

        self.assertEqual(result["status"], "applied")
        heading = lp.get_section_heading(
            "docs/runbook.md", "validation_commands", self.profile
        )
        self.assertIn(heading, runbook.read_text(encoding="utf-8"))

    def test_update_section_is_idempotent(self) -> None:
        runbook = self.root / "docs/runbook.md"
        runbook.write_text(
            lp.get_managed_template("docs/runbook.md", self.profile), encoding="utf-8"
        )
        heading = lp.get_section_heading(
            "docs/runbook.md", "validation_commands", self.profile
        )

        result = self._apply(
            {
                "id": "A002",
                "type": "update_section",
                "path": "docs/runbook.md",
                "section_id": "validation_commands",
            }
        )

        self.assertEqual(result["status"], "skipped")
        content = runbook.read_text(encoding="utf-8")
        self.assertEqual(content.count(heading), 1)

    def test_fill_claim_appends_todo_once(self) -> None:
        runbook = self.root / "docs/runbook.md"
        runbook.write_text(
            lp.get_managed_template("docs/runbook.md", self.profile), encoding="utf-8"
        )
        claim_id = "runbook.dev_commands"
        token = f"TODO(claim:{claim_id})"
        action = {
            "id": "A003",
            "type": "fill_claim",
            "path": "docs/runbook.md",
            "section_id": "dev_commands",
            "claim_id": claim_id,
            "required_evidence_types": ["repo_scan.modules"],
        }

        first = self._apply(action)
        second = self._apply(action)

        self.assertEqual(first["status"], "applied")
        self.assertEqual(second["status"], "skipped")
        content = runbook.read_text(encoding="utf-8")
        self.assertEqual(content.count(token), 1)

    def test_update_section_supports_unknown_section_id(self) -> None:
        runbook = self.root / "docs/runbook.md"
        runbook.write_text(
            lp.get_section_text("docs/runbook.md", "title", self.profile).strip() + "\n",
            encoding="utf-8",
        )
        result = self._apply(
            {
                "id": "A005",
                "type": "update_section",
                "path": "docs/runbook.md",
                "section_id": "custom_checks",
                "section_heading": "## 自定义检查",
            }
        )

        self.assertEqual(result["status"], "applied")
        content = runbook.read_text(encoding="utf-8")
        self.assertIn("## 自定义检查", content)
        self.assertIn("TODO: 补充本节内容。", content)

    def test_refresh_evidence_returns_applied_without_modification(self) -> None:
        target = self.root / "docs/architecture.md"
        target.write_text(
            lp.get_managed_template("docs/architecture.md", self.profile),
            encoding="utf-8",
        )
        before = target.read_text(encoding="utf-8")

        result = self._apply(
            {
                "id": "A004",
                "type": "refresh_evidence",
                "path": "docs/architecture.md",
                "section_id": "module_inventory",
                "claim_id": "architecture.modules.top_level",
                "evidence_types": ["repo_scan.modules"],
            }
        )

        after = target.read_text(encoding="utf-8")
        self.assertEqual(result["status"], "applied")
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
