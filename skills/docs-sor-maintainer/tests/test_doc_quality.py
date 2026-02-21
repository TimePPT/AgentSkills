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


class DocQualityTodoMetricsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "docs").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_missing_claim_counts_once_in_unresolved_todo(self) -> None:
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
                                    "required_evidence_types": ["repo_scan.modules"],
                                    "allow_unknown": False,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        spec_path = self.root / "docs/.doc-spec.json"
        spec_path.write_text(
            json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        policy = {
            "doc_quality_gates": {
                "enabled": True,
                "min_evidence_coverage": 0.0,
                "max_conflicts": 0,
                "max_unknown_claims": 0,
                "max_unresolved_todo": 1,
                "max_stale_metrics_days": 0,
            }
        }
        report = doc_quality.evaluate_quality(
            root=self.root,
            policy=policy,
            facts={},
            spec_path=spec_path,
            evidence_map_path=None,
        )

        self.assertEqual(report["metrics"]["missing_claims"], 1)
        self.assertEqual(report["metrics"]["unresolved_todo"], 1)
        self.assertEqual(report["gate"]["status"], "passed")
        self.assertNotIn("max_unresolved_todo", report["gate"]["failed_checks"])


if __name__ == "__main__":
    unittest.main()
