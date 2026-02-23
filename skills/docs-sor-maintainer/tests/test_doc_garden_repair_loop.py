#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import language_profiles as lp  # noqa: E402
import doc_garden  # noqa: E402


class DocGardenRepairLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "docs").mkdir(parents=True, exist_ok=True)
        (self.root / "skills").mkdir(parents=True, exist_ok=True)

        policy = lp.build_default_policy(primary_language="zh-CN", profile="zh-CN")
        policy["allow_auto_update"] = [
            "docs/index.md",
            "docs/architecture.md",
            "docs/runbook.md",
        ]
        policy["doc_gardening"]["enabled"] = True
        policy["doc_gardening"]["apply_mode"] = "apply-safe"
        policy["doc_gardening"]["repair_plan_mode"] = "repair"
        policy["doc_gardening"]["max_repair_iterations"] = 1
        policy["doc_gardening"]["fail_on_drift"] = True
        policy["doc_gardening"]["fail_on_freshness"] = True
        (self.root / "docs/.doc-policy.json").write_text(
            json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        manifest = {
            "version": 1,
            "required": {
                "files": [
                    "docs/index.md",
                    "docs/architecture.md",
                    "docs/runbook.md",
                    "docs/.doc-spec.json",
                ],
                "dirs": [],
            },
            "optional": {"files": []},
            "archive_dir": "docs/archive",
        }
        (self.root / "docs/.doc-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        spec = {
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
                                    "claim_id": "runbook.dev_commands",
                                    "statement_template": "当前开发命令集合为：{commands}",
                                    "required_evidence_types": [
                                        "repo_scan.nonexistent_signal"
                                    ],
                                    "allow_unknown": False,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        (self.root / "docs/.doc-spec.json").write_text(
            json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        (self.root / "docs/index.md").write_text(
            "\n".join(
                [
                    "<!-- doc-owner: docs-maintainer -->",
                    "<!-- doc-last-reviewed: 2026-02-21 -->",
                    "<!-- doc-review-cycle-days: 90 -->",
                    "",
                    "# 文档索引",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (self.root / "docs/architecture.md").write_text(
            "\n".join(
                [
                    "<!-- doc-owner: docs-maintainer -->",
                    "<!-- doc-last-reviewed: 2026-02-21 -->",
                    "<!-- doc-review-cycle-days: 90 -->",
                    "",
                    "# 架构概览",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (self.root / "docs/runbook.md").write_text(
            "\n".join(
                [
                    "<!-- doc-owner: docs-maintainer -->",
                    "<!-- doc-last-reviewed: 2026-02-21 -->",
                    "<!-- doc-review-cycle-days: 90 -->",
                    "",
                    "# 运行手册",
                    "",
                    "## 开发命令",
                    "",
                    "```bash",
                    "echo test",
                    "```",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_doc_garden_repair_loop_switches_to_repair_mode(self) -> None:
        cmd = [sys.executable, str(SCRIPT_DIR / "doc_garden.py"), "--root", str(self.root)]
        proc = subprocess.run(cmd, capture_output=True, text=True)

        self.assertEqual(proc.returncode, 1, msg=proc.stdout + proc.stderr)
        report_path = self.root / "docs/.doc-garden-report.json"
        self.assertTrue(report_path.exists())
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report.get("summary", {}).get("status"), "failed")
        self.assertEqual(report.get("repair", {}).get("attempts"), 1)
        self.assertEqual(report.get("repair", {}).get("max_iterations"), 1)
        self.assertEqual(report.get("settings", {}).get("repair_plan_mode"), "repair")

        cycles = report.get("repair", {}).get("cycles") or []
        self.assertGreaterEqual(len(cycles), 2)
        self.assertEqual(cycles[0].get("label"), "run")
        self.assertEqual(cycles[0].get("plan_mode"), "audit")
        self.assertEqual(cycles[1].get("label"), "repair-1")
        self.assertEqual(cycles[1].get("plan_mode"), "repair")

        plan_steps = [
            step
            for step in (report.get("steps") or [])
            if str(step.get("name", "")).endswith(":plan")
        ]
        self.assertEqual(len(plan_steps), 2)
        first_cmd = plan_steps[0].get("command", [])
        second_cmd = plan_steps[1].get("command", [])
        self.assertIsInstance(first_cmd, list)
        self.assertIsInstance(second_cmd, list)

        first_mode = first_cmd[first_cmd.index("--mode") + 1]
        second_mode = second_cmd[second_cmd.index("--mode") + 1]
        self.assertEqual(first_mode, "audit")
        self.assertEqual(second_mode, "repair")

    def test_collect_semantic_backlog_and_render(self) -> None:
        validate_report = {
            "legacy": {
                "semantic": {
                    "backlog": [
                        {"source_path": "legacy/a.md", "reason": "semantic_conflict"},
                        {
                            "source_path": "legacy/b.md",
                            "reason": "structured_section_incomplete",
                        },
                    ]
                }
            }
        }
        backlog = doc_garden.collect_semantic_backlog(validate_report)
        self.assertEqual(len(backlog), 2)

        report = {
            "generated_at": "2026-02-22T00:00:00+00:00",
            "root": str(self.root),
            "summary": {"status": "failed", "apply_mode": "apply-safe"},
            "steps": [],
            "semantic_backlog": {"count": 2, "sample": backlog},
        }
        markdown = doc_garden.render_report_markdown(report)
        self.assertIn("## Semantic Backlog", markdown)
        self.assertIn("legacy/a.md", markdown)

    def test_is_repairable_drift_accepts_semantic_rewrite(self) -> None:
        validate_report = {
            "drift": {"actions": ["A001 semantic_rewrite docs/history/legacy/a.md"]}
        }
        self.assertTrue(doc_garden.is_repairable_drift(validate_report))


if __name__ == "__main__":
    unittest.main()
