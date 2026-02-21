#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import doc_plan  # noqa: E402
import language_profiles as lp  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DocPlanSectionActionTests(unittest.TestCase):
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
        policy["doc_quality_gates"]["enabled"] = True
        policy["doc_quality_gates"]["min_evidence_coverage"] = 1.0
        policy_path = self.root / "docs/.doc-policy.json"
        policy_path.write_text(
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
        manifest_path = self.root / "docs/.doc-manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        spec = {
            "version": 1,
            "documents": [
                {
                    "path": "docs/architecture.md",
                    "required_sections": ["module_inventory", "dependency_manifests"],
                    "sections": [
                        {
                            "section_id": "module_inventory",
                            "claims": [
                                {
                                    "claim_id": "architecture.modules.top_level",
                                    "statement_template": "仓库的顶层模块包括：{modules}",
                                    "required_evidence_types": ["repo_scan.modules"],
                                    "allow_unknown": False,
                                }
                            ],
                        },
                        {
                            "section_id": "dependency_manifests",
                            "claims": [
                                {
                                    "claim_id": "architecture.dependencies.manifests",
                                    "statement_template": "仓库依赖清单包括：{manifests}",
                                    "required_evidence_types": ["repo_scan.manifests"],
                                    "allow_unknown": False,
                                }
                            ],
                        },
                    ],
                },
                {
                    "path": "docs/runbook.md",
                    "required_sections": ["dev_commands", "validation_commands"],
                    "sections": [
                        {
                            "section_id": "dev_commands",
                            "claims": [
                                {
                                    "claim_id": "runbook.dev_commands",
                                    "statement_template": "当前开发命令集合为：{commands}",
                                    "required_evidence_types": [
                                        "runbook.dev_commands"
                                    ],
                                    "allow_unknown": False,
                                }
                            ],
                        },
                        {
                            "section_id": "validation_commands",
                            "claims": [
                                {
                                    "claim_id": "runbook.validation_commands",
                                    "statement_template": "当前校验命令集合为：{commands}",
                                    "required_evidence_types": [
                                        "runbook.validation_commands"
                                    ],
                                    "allow_unknown": False,
                                }
                            ],
                        },
                    ],
                },
            ],
        }
        spec_path = self.root / "docs/.doc-spec.json"
        spec_path.write_text(
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
            lp.get_managed_template("docs/architecture.md", "zh-CN"), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _build_plan(self, facts: dict[str, object]) -> dict[str, object]:
        return doc_plan.build_plan(
            root=self.root,
            mode="audit",
            facts=facts,
            policy_path=self.root / "docs/.doc-policy.json",
            manifest_path=self.root / "docs/.doc-manifest.json",
        )

    def test_plan_emits_update_section_and_fill_claim_with_evidence(self) -> None:
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
                    "python3 tool.py",
                    "```",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        facts = {
            "generated_at": utc_now(),
            "modules": ["skills"],
            "manifests": {"go.mod": False, "package.json": False, "pyproject.toml": False},
        }

        plan = self._build_plan(facts)
        actions = plan.get("actions") or []
        section_actions = [a for a in actions if a.get("type") == "update_section"]
        claim_actions = [a for a in actions if a.get("type") == "fill_claim"]

        self.assertTrue(section_actions)
        self.assertTrue(claim_actions)
        self.assertIn("section_action_counts", (plan.get("summary") or {}))
        self.assertIn("claim_action_counts", (plan.get("summary") or {}))

        target = next(
            action
            for action in section_actions
            if action.get("section_id") == "validation_commands"
        )
        self.assertEqual(target.get("reason"), "doc-spec section missing")
        self.assertTrue(target.get("evidence"))

        claim_target = next(
            action
            for action in claim_actions
            if action.get("claim_id") == "runbook.validation_commands"
        )
        self.assertEqual(claim_target.get("reason"), "doc-spec claim missing evidence")
        self.assertTrue(claim_target.get("evidence"))

    def test_plan_emits_refresh_evidence_for_stale_facts(self) -> None:
        (self.root / "docs/runbook.md").write_text(
            lp.get_managed_template("docs/runbook.md", "zh-CN"), encoding="utf-8"
        )
        facts = {
            "generated_at": "2025-01-01T00:00:00+00:00",
            "modules": ["skills"],
            "manifests": {"go.mod": False, "package.json": False, "pyproject.toml": False},
        }

        plan = self._build_plan(facts)
        refresh_actions = [
            action for action in (plan.get("actions") or []) if action.get("type") == "refresh_evidence"
        ]
        self.assertTrue(refresh_actions)
        self.assertTrue(all(action.get("evidence") for action in refresh_actions))

    def test_plan_emits_quality_repair_when_quality_gate_fails(self) -> None:
        runbook = self.root / "docs/runbook.md"
        runbook.write_text(
            lp.get_managed_template("docs/runbook.md", "zh-CN"), encoding="utf-8"
        )
        policy_path = self.root / "docs/.doc-policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["doc_quality_gates"]["min_evidence_coverage"] = 1.1
        policy_path.write_text(
            json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        facts = {
            "generated_at": utc_now(),
            "modules": ["skills"],
            "manifests": {"go.mod": False, "package.json": False, "pyproject.toml": False},
        }

        plan = self._build_plan(facts)
        quality_repairs = [
            action for action in (plan.get("actions") or []) if action.get("type") == "quality_repair"
        ]
        self.assertEqual(len(quality_repairs), 1)
        repair = quality_repairs[0]
        self.assertEqual(repair.get("reason"), "doc-quality gate failed")
        self.assertIn("min_evidence_coverage", repair.get("failed_checks", []))
        self.assertTrue(repair.get("evidence"))


if __name__ == "__main__":
    unittest.main()
