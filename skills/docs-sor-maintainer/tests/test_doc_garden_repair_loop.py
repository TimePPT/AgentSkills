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

    def test_repair_loop_respects_max_iterations(self) -> None:
        cmd = [sys.executable, str(SCRIPT_DIR / "doc_garden.py"), "--root", str(self.root)]
        proc = subprocess.run(cmd, capture_output=True, text=True)

        self.assertEqual(proc.returncode, 1, msg=proc.stdout + proc.stderr)
        report_path = self.root / "docs/.doc-garden-report.json"
        self.assertTrue(report_path.exists())
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report.get("summary", {}).get("status"), "failed")
        self.assertEqual(report.get("repair", {}).get("attempts"), 1)
        self.assertEqual(report.get("repair", {}).get("max_iterations"), 1)


if __name__ == "__main__":
    unittest.main()
