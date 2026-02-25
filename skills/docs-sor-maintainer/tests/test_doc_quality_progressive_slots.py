#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import doc_quality  # noqa: E402


class DocQualityProgressiveSlotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "docs").mkdir(parents=True, exist_ok=True)
        self.spec_path = self.root / "docs/.doc-spec.json"
        self.spec_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "documents": [
                        {
                            "path": "docs/runbook.md",
                            "required_sections": ["dev_commands"],
                            "sections": [
                                {
                                    "section_id": "dev_commands",
                                    "claims": [
                                        {
                                            "claim_id": "runbook.dev_commands.progressive",
                                            "statement_template": "当前开发命令集合为：{commands}",
                                            "required_evidence_types": [
                                                "repo_scan.nonexistent_signal"
                                            ],
                                            "allow_unknown": True,
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _policy(self) -> dict[str, object]:
        return {
            "progressive_disclosure": {
                "enabled": True,
                "required_slots": ["summary", "key_facts", "next_steps"],
                "summary_max_chars": 40,
                "max_key_facts": 5,
                "max_next_steps": 3,
                "fail_on_missing_slots": True,
            },
            "doc_quality_gates": {
                "enabled": True,
                "min_evidence_coverage": 0.0,
                "max_conflicts": 10,
                "max_unknown_claims": 10,
                "max_unresolved_todo": 10,
                "max_stale_metrics_days": 0,
                "min_progressive_slot_completeness": 1.0,
                "min_next_step_presence": 1.0,
                "max_section_verbosity_over_budget": 0,
                "fail_on_quality_gate": True,
            },
        }

    def test_progressive_gate_passes_when_slots_complete_and_within_budget(self) -> None:
        (self.root / "docs/runbook.md").write_text(
            "\n".join(
                [
                    "# 运行手册",
                    "",
                    "### 摘要",
                    "",
                    "本节概述开发命令入口。",
                    "",
                    "### 关键事实",
                    "",
                    "- 命令集中在 runbook",
                    "- 验证链路固定",
                    "",
                    "### 下一步",
                    "",
                    "- 执行 `python3 -m unittest`",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        report = doc_quality.evaluate_quality(
            root=self.root,
            policy=self._policy(),
            facts={},
            spec_path=self.spec_path,
            evidence_map_path=None,
        )

        self.assertEqual(report["gate"]["status"], "passed")
        self.assertEqual(report["metrics"]["progressive_slot_completeness"], 1.0)
        self.assertEqual(report["metrics"]["next_step_presence"], 1.0)
        self.assertEqual(report["metrics"]["section_verbosity_over_budget_count"], 0)
        self.assertEqual(report["metrics"]["progressive_missing_slots_count"], 0)

    def test_progressive_gate_fails_when_slots_missing_or_over_budget(self) -> None:
        (self.root / "docs/runbook.md").write_text(
            "\n".join(
                [
                    "# 运行手册",
                    "",
                    "### 摘要",
                    "",
                    "这是一个明显超过预算的摘要段落，用来验证 summary 字符数越界会触发门禁失败。",
                    "",
                    "### 关键事实",
                    "",
                    "- 只有事实，没有下一步",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        report = doc_quality.evaluate_quality(
            root=self.root,
            policy=self._policy(),
            facts={},
            spec_path=self.spec_path,
            evidence_map_path=None,
        )

        self.assertEqual(report["gate"]["status"], "failed")
        failed_checks = report["gate"]["failed_checks"]
        self.assertIn("min_progressive_slot_completeness", failed_checks)
        self.assertIn("min_next_step_presence", failed_checks)
        self.assertIn("max_section_verbosity_over_budget", failed_checks)
        self.assertIn("progressive_required_slots", failed_checks)


if __name__ == "__main__":
    unittest.main()
