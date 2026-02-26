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
import doc_semantic_runtime as dsr  # noqa: E402
import language_profiles as lp  # noqa: E402


class DocApplySemanticSlotsV2Tests(unittest.TestCase):
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

    def _apply_with_runtime(
        self,
        *,
        action: dict[str, object],
        semantic_settings: dict[str, object],
        runtime_entry: dict[str, object],
        progressive_settings: dict[str, object] | None = None,
    ) -> dict[str, object]:
        runtime_state = {
            "enabled": True,
            "mode": semantic_settings.get("mode"),
            "source": "invoking_agent",
            "available": True,
            "entry_count": 1,
            "error": None,
            "warnings": [],
        }
        return doc_apply.apply_action(
            self.root,
            action,
            dry_run=False,
            language_settings=self.language,
            template_profile=self.profile,
            metadata_policy=self.metadata_policy,
            semantic_settings=semantic_settings,
            progressive_settings=progressive_settings,
            semantic_runtime_entries=[runtime_entry],
            semantic_runtime_state=runtime_state,
        )

    def test_update_section_slots_v2_agent_strict_blocks_on_missing_required_slots(self) -> None:
        runbook = self.root / "docs/runbook.md"
        runbook.write_text(
            lp.get_section_text("docs/runbook.md", "title", self.profile).strip() + "\n",
            encoding="utf-8",
        )
        semantic_settings = dsr.resolve_semantic_generation_settings(
            {
                "semantic_generation": {
                    "enabled": True,
                    "mode": "agent_strict",
                }
            }
        )
        runtime_entry = {
            "entry_id": "slots-missing-next-steps",
            "path": "docs/runbook.md",
            "action_type": "update_section",
            "section_id": "custom_checks",
            "status": "ok",
            "slots": {
                "summary": "运行前先校验工具链。",
                "key_facts": ["统一走 scan-plan-apply-validate 链路。"],
            },
            "citations": ["evidence://runbook.dev_commands"],
        }
        result = self._apply_with_runtime(
            action={
                "id": "S001",
                "type": "update_section",
                "path": "docs/runbook.md",
                "section_id": "custom_checks",
                "section_heading": "## 自定义检查",
            },
            semantic_settings=semantic_settings,
            runtime_entry=runtime_entry,
        )

        self.assertEqual(result.get("status"), "error")
        self.assertIn(
            "agent_strict requires runtime semantic candidate", str(result.get("details", ""))
        )
        semantic_runtime = result.get("semantic_runtime") or {}
        self.assertEqual(semantic_runtime.get("status"), "runtime_required")
        gate = semantic_runtime.get("gate") or {}
        self.assertEqual(gate.get("status"), "failed")
        self.assertIn("missing_slot_next_steps", gate.get("failed_checks", []))
        self.assertNotIn("## 自定义检查", runbook.read_text(encoding="utf-8"))

    def test_update_section_slots_v2_hybrid_fallback_with_audit_when_gate_failed(self) -> None:
        runbook = self.root / "docs/runbook.md"
        runbook.write_text(
            lp.get_section_text("docs/runbook.md", "title", self.profile).strip() + "\n",
            encoding="utf-8",
        )
        semantic_settings = dsr.resolve_semantic_generation_settings(
            {
                "semantic_generation": {
                    "enabled": True,
                    "mode": "hybrid",
                }
            }
        )
        runtime_entry = {
            "entry_id": "slots-invalid-citations",
            "path": "docs/runbook.md",
            "action_type": "update_section",
            "section_id": "custom_checks",
            "status": "ok",
            "slots": {
                "summary": "开发流程以审计和门禁为主。",
                "key_facts": ["先跑 doc_plan audit。"],
                "next_steps": ["执行 doc_validate。"],
            },
            "citations": ["invalid://repo_scan.modules"],
        }
        result = self._apply_with_runtime(
            action={
                "id": "S002",
                "type": "update_section",
                "path": "docs/runbook.md",
                "section_id": "custom_checks",
                "section_heading": "## 自定义检查",
            },
            semantic_settings=semantic_settings,
            runtime_entry=runtime_entry,
        )

        self.assertEqual(result.get("status"), "applied")
        self.assertIn("runtime gate failed", str(result.get("details", "")))
        semantic_runtime = result.get("semantic_runtime") or {}
        self.assertEqual(semantic_runtime.get("status"), "section_runtime_gate_failed")
        gate = semantic_runtime.get("gate") or {}
        self.assertEqual(gate.get("status"), "failed")
        self.assertIn("invalid_citation_token", gate.get("failed_checks", []))

        content = runbook.read_text(encoding="utf-8")
        self.assertIn("## 自定义检查", content)
        self.assertIn("TODO: 补充本节内容。", content)
        self.assertNotIn("开发流程以审计和门禁为主。", content)

    def test_update_section_slots_v2_applies_structured_content_when_gate_passes(self) -> None:
        runbook = self.root / "docs/runbook.md"
        runbook.write_text(
            lp.get_managed_template("docs/runbook.md", self.profile), encoding="utf-8"
        )
        semantic_settings = dsr.resolve_semantic_generation_settings(
            {
                "semantic_generation": {
                    "enabled": True,
                    "mode": "hybrid",
                }
            }
        )
        runtime_entry = {
            "entry_id": "slots-valid",
            "path": "docs/runbook.md",
            "action_type": "update_section",
            "section_id": "validation_commands",
            "status": "ok",
            "slots": {
                "summary": "合并前必须完成 validate 与 quality gate。",
                "key_facts": [
                    "事实文件来自 docs/.repo-facts.json。",
                    "计划文件来自 docs/.doc-plan.json。",
                ],
                "next_steps": [
                    "执行 repo_scan 生成事实。",
                    "执行 doc_plan --mode audit。",
                    "执行 doc_validate --fail-on-drift --fail-on-freshness。",
                ],
            },
            "citations": [
                "evidence://repo_scan.modules",
                "evidence://runbook.dev_commands",
            ],
        }
        result = self._apply_with_runtime(
            action={
                "id": "S003",
                "type": "update_section",
                "path": "docs/runbook.md",
                "section_id": "validation_commands",
            },
            semantic_settings=semantic_settings,
            runtime_entry=runtime_entry,
        )

        self.assertEqual(result.get("status"), "applied")
        semantic_runtime = result.get("semantic_runtime") or {}
        self.assertEqual(semantic_runtime.get("status"), "section_runtime_applied")
        gate = semantic_runtime.get("gate") or {}
        self.assertEqual(gate.get("status"), "passed")
        self.assertTrue(semantic_runtime.get("consumed"))

        content = runbook.read_text(encoding="utf-8")
        self.assertIn("### 摘要", content)
        self.assertIn("### 关键事实", content)
        self.assertIn("### 下一步", content)
        self.assertIn("合并前必须完成 validate 与 quality gate。", content)
        self.assertIn("执行 doc_plan --mode audit。", content)

    def test_update_section_slots_v2_renders_custom_required_slot(self) -> None:
        runbook = self.root / "docs/runbook.md"
        runbook.write_text(
            lp.get_managed_template("docs/runbook.md", self.profile), encoding="utf-8"
        )
        semantic_settings = dsr.resolve_semantic_generation_settings(
            {
                "semantic_generation": {
                    "enabled": True,
                    "mode": "hybrid",
                }
            }
        )
        progressive_settings = {
            "enabled": True,
            "required_slots": ["summary", "key_facts", "next_steps", "risks"],
            "summary_max_chars": 160,
            "max_key_facts": 5,
            "max_next_steps": 3,
            "fail_on_missing_slots": True,
        }
        runtime_entry = {
            "entry_id": "slots-with-risks",
            "path": "docs/runbook.md",
            "action_type": "update_section",
            "section_id": "validation_commands",
            "status": "ok",
            "slots": {
                "summary": "发布前需要完成质量门禁与拓扑门禁。",
                "key_facts": ["质量门禁负责结构化与证据一致性。"],
                "next_steps": ["执行 doc_quality。"],
                "risks": ["若 gate 配置与文档结构不一致会触发阻断。"],
            },
            "citations": [
                "evidence://repo_scan.modules",
            ],
        }
        result = self._apply_with_runtime(
            action={
                "id": "S004",
                "type": "update_section",
                "path": "docs/runbook.md",
                "section_id": "validation_commands",
            },
            semantic_settings=semantic_settings,
            runtime_entry=runtime_entry,
            progressive_settings=progressive_settings,
        )

        self.assertEqual(result.get("status"), "applied")
        semantic_runtime = result.get("semantic_runtime") or {}
        gate = semantic_runtime.get("gate") or {}
        self.assertEqual(gate.get("status"), "passed")

        content = runbook.read_text(encoding="utf-8")
        self.assertIn("### Risks", content)
        self.assertIn("若 gate 配置与文档结构不一致会触发阻断。", content)

    def test_update_section_slots_v2_quality_grade_c_uses_fallback_when_configured(self) -> None:
        runbook = self.root / "docs/runbook.md"
        runbook.write_text(
            lp.get_section_text("docs/runbook.md", "title", self.profile).strip() + "\n",
            encoding="utf-8",
        )
        semantic_settings = dsr.resolve_semantic_generation_settings(
            {
                "semantic_generation": {
                    "enabled": True,
                    "mode": "hybrid",
                    "input_quality": {
                        "enabled": True,
                        "c_grade_decision": "fallback",
                    },
                }
            }
        )
        runtime_entry = {
            "entry_id": "slots-grade-c",
            "path": "docs/runbook.md",
            "action_type": "update_section",
            "section_id": "custom_checks",
            "status": "manual_review",
            "slots": {
                "summary": "先做审计，再做修复。",
                "key_facts": ["语义结果需保留证据映射。"],
                "next_steps": ["执行 scoped validate。"],
            },
            "citations": ["evidence://runbook.dev_commands"],
        }
        result = self._apply_with_runtime(
            action={
                "id": "S005",
                "type": "update_section",
                "path": "docs/runbook.md",
                "section_id": "custom_checks",
                "section_heading": "## 自定义检查",
            },
            semantic_settings=semantic_settings,
            runtime_entry=runtime_entry,
        )

        self.assertEqual(result.get("status"), "applied")
        semantic_runtime = result.get("semantic_runtime") or {}
        self.assertEqual(semantic_runtime.get("quality_grade"), "C")
        self.assertEqual(semantic_runtime.get("quality_decision"), "fallback")
        self.assertTrue(semantic_runtime.get("fallback_used"))
        self.assertEqual(semantic_runtime.get("fallback_reason"), "runtime_quality_grade_c")
        content = runbook.read_text(encoding="utf-8")
        self.assertIn("## 自定义检查", content)
        self.assertIn("TODO: 补充本节内容。", content)

    def test_update_section_slots_v2_quality_grade_d_blocks_auto_apply(self) -> None:
        runbook = self.root / "docs/runbook.md"
        runbook.write_text(
            lp.get_section_text("docs/runbook.md", "title", self.profile).strip() + "\n",
            encoding="utf-8",
        )
        semantic_settings = dsr.resolve_semantic_generation_settings(
            {
                "semantic_generation": {
                    "enabled": True,
                    "mode": "hybrid",
                    "input_quality": {
                        "enabled": True,
                        "c_grade_decision": "fallback",
                    },
                }
            }
        )
        runtime_entry = {
            "entry_id": "slots-grade-d",
            "path": "docs/runbook.md",
            "action_type": "update_section",
            "section_id": "custom_checks",
            "status": "manual_review",
            "slots": {
                "summary": "该条目质量不足。",
                "key_facts": ["状态为 manual_review。"],
                "next_steps": ["需要人工处理。"],
            },
            "citations": [],
        }
        result = self._apply_with_runtime(
            action={
                "id": "S006",
                "type": "update_section",
                "path": "docs/runbook.md",
                "section_id": "custom_checks",
                "section_heading": "## 自定义检查",
            },
            semantic_settings=semantic_settings,
            runtime_entry=runtime_entry,
        )

        self.assertEqual(result.get("status"), "skipped")
        self.assertIn("fallback blocked", str(result.get("details", "")))
        semantic_runtime = result.get("semantic_runtime") or {}
        self.assertEqual(semantic_runtime.get("quality_grade"), "D")
        self.assertEqual(semantic_runtime.get("quality_decision"), "block")
        self.assertEqual(semantic_runtime.get("fallback_reason"), "runtime_quality_grade_d")
        self.assertFalse(semantic_runtime.get("fallback_allowed"))
        self.assertNotIn("## 自定义检查", runbook.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
