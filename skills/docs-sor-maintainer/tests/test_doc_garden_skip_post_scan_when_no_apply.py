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


class DocGardenIncrementalOptimizationTests(unittest.TestCase):
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
        policy["doc_gardening"]["max_repair_iterations"] = 0
        policy["doc_gardening"]["fail_on_drift"] = True
        policy["doc_gardening"]["fail_on_freshness"] = True
        (self.root / "docs/.doc-policy.json").write_text(
            json.dumps(policy, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        manifest = {
            "version": 1,
            "required": {
                "files": [
                    "docs/index.md",
                    "docs/architecture.md",
                    "docs/runbook.md",
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

        (self.root / "docs/index.md").write_text(
            "\n".join(
                [
                    "<!-- doc-owner: docs-maintainer -->",
                    "<!-- doc-last-reviewed: 2026-02-24 -->",
                    "<!-- doc-review-cycle-days: 90 -->",
                    "",
                    "# 文档索引",
                    "",
                    "## 核心文档",
                    "",
                    "- `docs/.doc-policy.json`",
                    "- `docs/.doc-manifest.json`",
                    "- `docs/architecture.md`",
                    "- `docs/runbook.md`",
                    "",
                    "## 操作流程",
                    "",
                    "1. 运行 repository scan 并生成 doc plan。",
                    "2. 审阅 actions 后执行 safe mode。",
                    "3. 合并前校验 links 与 drift 状态。",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (self.root / "docs/architecture.md").write_text(
            "\n".join(
                [
                    "<!-- doc-owner: docs-maintainer -->",
                    "<!-- doc-last-reviewed: 2026-02-24 -->",
                    "<!-- doc-review-cycle-days: 90 -->",
                    "",
                    "# 仓库架构",
                    "",
                    "## 模块清单",
                    "",
                    "- `skills/docs-sor-maintainer`：文档治理脚本与测试。",
                    "",
                    "## 依赖清单",
                    "",
                    "- `python3`",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (self.root / "docs/runbook.md").write_text(
            "\n".join(
                [
                    "<!-- doc-owner: docs-maintainer -->",
                    "<!-- doc-last-reviewed: 2026-02-24 -->",
                    "<!-- doc-review-cycle-days: 90 -->",
                    "",
                    "# 运行手册",
                    "",
                    "## 开发命令",
                    "",
                    "```bash",
                    "echo dev",
                    "```",
                    "",
                    "## 校验命令",
                    "",
                    "```bash",
                    "echo validate",
                    "```",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_doc_garden_skips_post_scan_and_reports_performance_when_no_apply(self) -> None:
        cmd = [sys.executable, str(SCRIPT_DIR / "doc_garden.py"), "--root", str(self.root)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)

        report_path = self.root / "docs/.doc-garden-report.json"
        self.assertTrue(report_path.exists())
        report = json.loads(report_path.read_text(encoding="utf-8"))

        steps = report.get("steps") or []
        step_names = [str(step.get("name", "")) for step in steps]
        self.assertIn("run:scan", step_names)
        self.assertIn("run:plan", step_names)
        self.assertIn("run:apply", step_names)
        self.assertIn("run:synthesize", step_names)
        self.assertIn("run:validate", step_names)
        self.assertNotIn("run:scan-post-apply", step_names)

        for step in steps:
            self.assertIn("duration_ms", step)
            self.assertIsInstance(step.get("duration_ms"), int)
            self.assertGreaterEqual(step.get("duration_ms"), 0)

        apply_summary = report.get("apply") or {}
        self.assertEqual(apply_summary.get("applied"), 0)
        self.assertEqual(report.get("summary", {}).get("status"), "passed")

        cycles = report.get("repair", {}).get("cycles") or []
        self.assertEqual(len(cycles), 1)
        self.assertEqual(cycles[0].get("apply_applied"), 0)
        self.assertEqual(cycles[0].get("post_apply_scan_skipped"), True)
        self.assertEqual(
            cycles[0].get("post_apply_scan_skip_reason"), "apply_applied_zero"
        )

        performance = report.get("performance") or {}
        required_metrics = [
            "scan_duration_ms",
            "plan_duration_ms",
            "apply_duration_ms",
            "synthesize_duration_ms",
            "validate_duration_ms",
            "garden_total_duration_ms",
        ]
        for metric in required_metrics:
            self.assertIn(metric, performance)
            self.assertIsInstance(performance.get(metric), int)
            self.assertGreaterEqual(performance.get(metric), 0)
        self.assertEqual(
            report.get("summary", {}).get("garden_total_duration_ms"),
            performance.get("garden_total_duration_ms"),
        )


if __name__ == "__main__":
    unittest.main()
