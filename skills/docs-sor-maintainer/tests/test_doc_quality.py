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
import doc_legacy as dl  # noqa: E402


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

    def test_semantic_gate_metrics_and_fail_checks(self) -> None:
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
                                    "claim_id": "runbook.dev_commands.semantic",
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
        }
        spec_path = self.root / "docs/.doc-spec.json"
        spec_path.write_text(
            json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        policy = {
            "doc_quality_gates": {
                "enabled": True,
                "min_evidence_coverage": 0.0,
                "max_conflicts": 10,
                "max_unknown_claims": 10,
                "max_unresolved_todo": 10,
                "max_stale_metrics_days": 0,
                "max_semantic_conflicts": 0,
                "max_semantic_low_confidence_auto": 0,
                "min_structured_section_completeness": 0.95,
                "fail_on_quality_gate": True,
                "fail_on_semantic_gate": True,
            },
            "legacy_sources": {
                "enabled": True,
                "include_globs": ["legacy/**"],
                "exclude_globs": [],
                "archive_root": "docs/archive/legacy",
                "mapping_strategy": "path_based",
                "target_root": "docs/history/legacy",
                "target_doc": "docs/history/legacy-migration.md",
                "registry_path": "docs/.legacy-migration-map.json",
                "allow_non_markdown": True,
                "exempt_sources": [],
                "mapping_table": {},
                "fail_on_legacy_drift": True,
                "semantic_report_path": "docs/.legacy-semantic-report.json",
                "semantic": {
                    "enabled": True,
                    "engine": "llm",
                    "provider": "deterministic_mock",
                    "model": "gpt-5-codex",
                    "auto_migrate_threshold": 0.85,
                    "review_threshold": 0.6,
                },
            },
        }

        target_rel = "docs/history/legacy/legacy/a.md"
        (self.root / "docs/history/legacy/legacy").mkdir(parents=True, exist_ok=True)
        (self.root / target_rel).write_text(
            "\n".join(
                [
                    "# Legacy 迁移记录",
                    "",
                    "## Legacy Source `legacy/a.md`",
                    dl.source_marker("legacy/a.md"),
                    "<!-- legacy-migrated-at: 2026-02-21T00:00:00+00:00 -->",
                    "",
                    "### 摘要",
                    "",
                    "- test summary",
                    "",
                    # deliberately missing structured sections
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        registry = {
            "version": 1,
            "updated_at": "2026-02-21T00:00:00+00:00",
            "entries": {
                "legacy/a.md": {
                    "status": "archived",
                    "source_path": "legacy/a.md",
                    "target_path": target_rel,
                    "archive_path": "docs/archive/legacy/legacy/a.md",
                    "decision_source": "semantic",
                    "category": "plan",
                    "confidence": 0.5,
                    "semantic_model": "gpt-5-codex",
                }
            },
        }
        (self.root / "docs/.legacy-migration-map.json").write_text(
            json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        semantic_report = {
            "version": 1,
            "entries": [
                {
                    "source_path": "legacy/a.md",
                    "decision": "auto_migrate",
                    "category": "plan",
                    "confidence": 0.5,
                }
            ],
        }
        (self.root / "docs/.legacy-semantic-report.json").write_text(
            json.dumps(semantic_report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        report = doc_quality.evaluate_quality(
            root=self.root,
            policy=policy,
            facts={},
            spec_path=spec_path,
            evidence_map_path=None,
        )

        self.assertEqual(report["metrics"]["semantic_auto_migrate_count"], 1)
        self.assertEqual(report["metrics"]["semantic_low_confidence_count"], 1)
        self.assertLess(report["metrics"]["structured_section_completeness"], 0.95)
        self.assertIn("max_semantic_low_confidence_auto", report["gate"]["failed_checks"])
        self.assertIn("min_structured_section_completeness", report["gate"]["failed_checks"])


if __name__ == "__main__":
    unittest.main()
