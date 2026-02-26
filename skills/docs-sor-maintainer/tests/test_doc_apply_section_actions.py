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

import doc_apply  # noqa: E402
import doc_metadata as dm  # noqa: E402
import doc_semantic_runtime as dsr  # noqa: E402
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

    def test_main_accepts_repair_plan_mode(self) -> None:
        plan_path = self.root / "docs/repair-plan.json"
        plan_path.write_text(
            json.dumps({"meta": {"mode": "repair"}, "actions": []}, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )

        cmd = [
            sys.executable,
            str(SCRIPT_DIR / "doc_apply.py"),
            "--root",
            str(self.root),
            "--plan",
            str(plan_path),
            "--mode",
            "apply-safe",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)

    def test_fill_claim_attaches_runtime_candidate_metadata(self) -> None:
        runbook = self.root / "docs/runbook.md"
        runbook.write_text(
            lp.get_managed_template("docs/runbook.md", self.profile), encoding="utf-8"
        )
        report_path = self.root / "docs/.semantic-runtime-report.json"
        report_payload = {
            "version": 1,
            "entries": [
                {
                    "entry_id": "claim-dev-commands",
                    "path": "docs/runbook.md",
                    "action_type": "fill_claim",
                    "section_id": "dev_commands",
                    "claim_id": "runbook.dev_commands",
                    "status": "ok",
                    "statement": "runtime semantic candidate",
                    "citations": ["evidence://repo_scan.modules"],
                }
            ],
        }
        report_path.write_text(
            json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n",
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
        runtime_entries, runtime_state = dsr.load_runtime_report(
            self.root, semantic_settings
        )

        result = doc_apply.apply_action(
            self.root,
            {
                "id": "A006",
                "type": "fill_claim",
                "path": "docs/runbook.md",
                "section_id": "dev_commands",
                "claim_id": "runbook.dev_commands",
                "required_evidence_types": ["repo_scan.modules"],
            },
            dry_run=False,
            language_settings=self.language,
            template_profile=self.profile,
            metadata_policy=self.metadata_policy,
            semantic_settings=semantic_settings,
            semantic_runtime_entries=runtime_entries,
            semantic_runtime_state=runtime_state,
        )

        self.assertIn("semantic_runtime", result)
        semantic_runtime = result["semantic_runtime"]
        self.assertEqual(semantic_runtime["status"], "claim_runtime_applied")
        self.assertEqual(semantic_runtime["entry_id"], "claim-dev-commands")
        self.assertEqual(semantic_runtime.get("gate", {}).get("status"), "passed")
        self.assertTrue(semantic_runtime.get("consumed"))
        content = runbook.read_text(encoding="utf-8")
        self.assertIn("CLAIM(claim:runbook.dev_commands)", content)
        self.assertIn("runtime semantic candidate", content)
        self.assertIn("evidence://repo_scan.modules", content)
        self.assertNotIn("TODO(claim:runbook.dev_commands)", content)

    def test_fill_claim_runtime_gate_falls_back_to_todo_when_citations_missing(self) -> None:
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
        runtime_entries = [
            {
                "entry_id": "claim-dev-commands",
                "path": "docs/runbook.md",
                "action_type": "fill_claim",
                "section_id": "dev_commands",
                "claim_id": "runbook.dev_commands",
                "status": "ok",
                "statement": "runtime semantic candidate",
            }
        ]
        runtime_state = {
            "enabled": True,
            "mode": "hybrid",
            "source": "invoking_agent",
            "available": True,
            "entry_count": 1,
            "error": None,
            "warnings": [],
        }

        result = doc_apply.apply_action(
            self.root,
            {
                "id": "A007",
                "type": "fill_claim",
                "path": "docs/runbook.md",
                "section_id": "dev_commands",
                "claim_id": "runbook.dev_commands",
                "required_evidence_types": ["repo_scan.modules"],
            },
            dry_run=False,
            language_settings=self.language,
            template_profile=self.profile,
            metadata_policy=self.metadata_policy,
            semantic_settings=semantic_settings,
            semantic_runtime_entries=runtime_entries,
            semantic_runtime_state=runtime_state,
        )

        self.assertEqual(result["status"], "applied")
        semantic_runtime = result.get("semantic_runtime") or {}
        self.assertEqual(semantic_runtime.get("status"), "claim_runtime_gate_failed")
        self.assertEqual(semantic_runtime.get("gate", {}).get("status"), "failed")
        self.assertIn("missing_citations", semantic_runtime.get("gate", {}).get("failed_checks", []))
        self.assertFalse(semantic_runtime.get("consumed"))
        self.assertEqual(semantic_runtime.get("fallback_reason"), "runtime_gate_failed")
        self.assertTrue(semantic_runtime.get("fallback_used"))
        content = runbook.read_text(encoding="utf-8")
        self.assertIn("TODO(claim:runbook.dev_commands)", content)
        self.assertNotIn("CLAIM(claim:runbook.dev_commands)", content)

    def test_fill_claim_agent_strict_requires_runtime_candidate(self) -> None:
        runbook = self.root / "docs/runbook.md"
        runbook.write_text(
            lp.get_managed_template("docs/runbook.md", self.profile), encoding="utf-8"
        )
        semantic_settings = dsr.resolve_semantic_generation_settings(
            {
                "semantic_generation": {
                    "enabled": True,
                    "mode": "agent_strict",
                }
            }
        )
        runtime_state = {
            "enabled": True,
            "mode": "agent_strict",
            "source": "invoking_agent",
            "available": False,
            "entry_count": 0,
            "error": "runtime report not found",
            "warnings": [],
        }

        result = doc_apply.apply_action(
            self.root,
            {
                "id": "A007S",
                "type": "fill_claim",
                "path": "docs/runbook.md",
                "section_id": "dev_commands",
                "claim_id": "runbook.dev_commands",
                "required_evidence_types": ["repo_scan.modules"],
            },
            dry_run=False,
            language_settings=self.language,
            template_profile=self.profile,
            metadata_policy=self.metadata_policy,
            semantic_settings=semantic_settings,
            semantic_runtime_entries=[],
            semantic_runtime_state=runtime_state,
        )

        self.assertEqual(result["status"], "error")
        self.assertIn("agent_strict requires runtime semantic candidate", result["details"])
        semantic_runtime = result.get("semantic_runtime") or {}
        self.assertEqual(semantic_runtime.get("status"), "runtime_required")
        content = runbook.read_text(encoding="utf-8")
        self.assertNotIn("TODO(claim:runbook.dev_commands)", content)
        self.assertNotIn("CLAIM(claim:runbook.dev_commands)", content)

    def test_fill_claim_fallback_blocked_by_policy(self) -> None:
        runbook = self.root / "docs/runbook.md"
        runbook.write_text(
            lp.get_managed_template("docs/runbook.md", self.profile), encoding="utf-8"
        )
        semantic_settings = dsr.resolve_semantic_generation_settings(
            {
                "semantic_generation": {
                    "enabled": True,
                    "mode": "hybrid",
                    "allow_fallback_template": False,
                    "fail_closed": True,
                }
            }
        )
        runtime_entries = [
            {
                "entry_id": "claim-dev-commands",
                "path": "docs/runbook.md",
                "action_type": "fill_claim",
                "section_id": "dev_commands",
                "claim_id": "runbook.dev_commands",
                "status": "ok",
                "statement": "runtime semantic candidate",
            }
        ]
        runtime_state = {
            "enabled": True,
            "mode": "hybrid",
            "source": "invoking_agent",
            "available": True,
            "entry_count": 1,
            "error": None,
            "warnings": [],
        }

        result = doc_apply.apply_action(
            self.root,
            {
                "id": "A007P",
                "type": "fill_claim",
                "path": "docs/runbook.md",
                "section_id": "dev_commands",
                "claim_id": "runbook.dev_commands",
                "required_evidence_types": ["repo_scan.modules"],
            },
            dry_run=False,
            language_settings=self.language,
            template_profile=self.profile,
            metadata_policy=self.metadata_policy,
            semantic_settings=semantic_settings,
            semantic_runtime_entries=runtime_entries,
            semantic_runtime_state=runtime_state,
        )

        self.assertEqual(result["status"], "skipped")
        self.assertIn("fallback blocked by semantic policy", result["details"])
        semantic_runtime = result.get("semantic_runtime") or {}
        self.assertEqual(semantic_runtime.get("status"), "fallback_blocked")
        self.assertFalse(semantic_runtime.get("fallback_allowed", True))
        self.assertEqual(semantic_runtime.get("fallback_reason"), "runtime_gate_failed")
        content = runbook.read_text(encoding="utf-8")
        self.assertNotIn("TODO(claim:runbook.dev_commands)", content)
        self.assertNotIn("CLAIM(claim:runbook.dev_commands)", content)

    def test_update_section_path_denied_blocks_runtime_and_fallback(self) -> None:
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
                    "allow_fallback_template": False,
                    "fail_closed": True,
                    "deny_paths": ["docs/runbook.md"],
                }
            }
        )
        runtime_entries = [
            {
                "entry_id": "section-custom",
                "path": "docs/runbook.md",
                "action_type": "update_section",
                "section_id": "custom_checks",
                "status": "ok",
                "content": "custom runtime content",
            }
        ]
        runtime_state = {
            "enabled": True,
            "mode": "hybrid",
            "source": "invoking_agent",
            "available": True,
            "entry_count": 1,
            "error": None,
            "warnings": [],
        }

        result = doc_apply.apply_action(
            self.root,
            {
                "id": "A008D",
                "type": "update_section",
                "path": "docs/runbook.md",
                "section_id": "custom_checks",
                "section_heading": "## 自定义检查",
            },
            dry_run=False,
            language_settings=self.language,
            template_profile=self.profile,
            metadata_policy=self.metadata_policy,
            semantic_settings=semantic_settings,
            semantic_runtime_entries=runtime_entries,
            semantic_runtime_state=runtime_state,
        )

        self.assertEqual(result["status"], "skipped")
        semantic_runtime = result.get("semantic_runtime") or {}
        self.assertEqual(semantic_runtime.get("status"), "fallback_blocked")
        self.assertEqual(semantic_runtime.get("fallback_reason"), "path_denied")
        gate = semantic_runtime.get("gate") or {}
        self.assertIn("path_denied", gate.get("failed_checks", []))
        content = runbook.read_text(encoding="utf-8")
        self.assertNotIn("## 自定义检查", content)

    def test_update_section_runtime_content_is_consumed(self) -> None:
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
        runtime_entries = [
            {
                "entry_id": "section-validation-commands",
                "path": "docs/runbook.md",
                "action_type": "update_section",
                "section_id": "validation_commands",
                "status": "ok",
                "content": "```bash\npython3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'\n```",
            }
        ]
        runtime_state = {
            "enabled": True,
            "mode": "hybrid",
            "source": "invoking_agent",
            "available": True,
            "entry_count": 1,
            "error": None,
            "warnings": [],
        }

        result = doc_apply.apply_action(
            self.root,
            {
                "id": "A008",
                "type": "update_section",
                "path": "docs/runbook.md",
                "section_id": "validation_commands",
            },
            dry_run=False,
            language_settings=self.language,
            template_profile=self.profile,
            metadata_policy=self.metadata_policy,
            semantic_settings=semantic_settings,
            semantic_runtime_entries=runtime_entries,
            semantic_runtime_state=runtime_state,
        )

        self.assertEqual(result.get("status"), "applied")
        semantic_runtime = result.get("semantic_runtime") or {}
        self.assertEqual(semantic_runtime.get("status"), "section_runtime_applied")
        self.assertEqual(semantic_runtime.get("gate", {}).get("status"), "passed")
        content = runbook.read_text(encoding="utf-8")
        self.assertIn("## 校验命令", content)
        self.assertIn("python3 -m unittest discover", content)

    def test_merge_docs_runtime_content_is_consumed(self) -> None:
        (self.root / "docs/history").mkdir(parents=True, exist_ok=True)
        merged = self.root / "docs/history/merged.md"
        (self.root / "docs/history/a.md").write_text("# A\n", encoding="utf-8")
        (self.root / "docs/history/b.md").write_text("# B\n", encoding="utf-8")
        semantic_settings = dsr.resolve_semantic_generation_settings(
            {"semantic_generation": {"enabled": True, "mode": "hybrid"}}
        )
        runtime_entries = [
            {
                "entry_id": "merge-history",
                "path": "docs/history/merged.md",
                "action_type": "merge_docs",
                "status": "ok",
                "source_paths": ["docs/history/a.md", "docs/history/b.md"],
                "content": "# merged-from-runtime\n\n- docs/history/a.md\n- docs/history/b.md",
            }
        ]
        runtime_state = {
            "enabled": True,
            "mode": "hybrid",
            "source": "invoking_agent",
            "available": True,
            "entry_count": 1,
            "error": None,
            "warnings": [],
        }

        result = doc_apply.apply_action(
            self.root,
            {
                "id": "A009",
                "type": "merge_docs",
                "path": "docs/history/merged.md",
                "source_paths": ["docs/history/a.md", "docs/history/b.md"],
            },
            dry_run=False,
            language_settings=self.language,
            template_profile=self.profile,
            metadata_policy=self.metadata_policy,
            semantic_settings=semantic_settings,
            semantic_runtime_entries=runtime_entries,
            semantic_runtime_state=runtime_state,
        )

        self.assertEqual(result.get("status"), "applied")
        semantic_runtime = result.get("semantic_runtime") or {}
        self.assertEqual(semantic_runtime.get("status"), "merge_docs_runtime_applied")
        self.assertEqual(semantic_runtime.get("gate", {}).get("status"), "passed")
        self.assertEqual(result.get("merged_sources"), ["docs/history/a.md", "docs/history/b.md"])
        self.assertIn("merged-from-runtime", merged.read_text(encoding="utf-8"))

    def test_split_doc_runtime_outputs_are_applied_and_index_linked(self) -> None:
        (self.root / "docs/history").mkdir(parents=True, exist_ok=True)
        (self.root / "docs/history/merged.md").write_text("# merged\n", encoding="utf-8")
        (self.root / "docs/index.md").write_text("# 文档索引\n", encoding="utf-8")
        semantic_settings = dsr.resolve_semantic_generation_settings(
            {"semantic_generation": {"enabled": True, "mode": "hybrid"}}
        )
        runtime_entries = [
            {
                "entry_id": "split-history",
                "path": "docs/history/merged.md",
                "action_type": "split_doc",
                "status": "ok",
                "split_outputs": [
                    {
                        "path": "docs/history/part-a.md",
                        "content": "# part-a",
                        "source_paths": ["docs/history/merged.md"],
                    },
                    {
                        "path": "docs/history/part-b.md",
                        "content": "# part-b",
                        "source_paths": ["docs/history/merged.md"],
                    },
                ],
                "index_links": ["docs/history/part-a.md", "docs/history/part-b.md"],
            }
        ]
        runtime_state = {
            "enabled": True,
            "mode": "hybrid",
            "source": "invoking_agent",
            "available": True,
            "entry_count": 1,
            "error": None,
            "warnings": [],
        }

        result = doc_apply.apply_action(
            self.root,
            {
                "id": "A010",
                "type": "split_doc",
                "path": "docs/history/merged.md",
                "source_path": "docs/history/merged.md",
                "target_paths": ["docs/history/part-a.md", "docs/history/part-b.md"],
                "index_path": "docs/index.md",
            },
            dry_run=False,
            language_settings=self.language,
            template_profile=self.profile,
            metadata_policy=self.metadata_policy,
            semantic_settings=semantic_settings,
            semantic_runtime_entries=runtime_entries,
            semantic_runtime_state=runtime_state,
        )

        self.assertEqual(result.get("status"), "applied")
        semantic_runtime = result.get("semantic_runtime") or {}
        self.assertEqual(semantic_runtime.get("status"), "split_doc_runtime_applied")
        self.assertEqual(semantic_runtime.get("gate", {}).get("status"), "passed")
        self.assertTrue((self.root / "docs/history/part-a.md").exists())
        self.assertTrue((self.root / "docs/history/part-b.md").exists())
        index_text = (self.root / "docs/index.md").read_text(encoding="utf-8")
        self.assertIn("docs/history/part-a.md", index_text)
        self.assertIn("docs/history/part-b.md", index_text)

    def test_split_doc_runtime_dry_run_handles_missing_index_file(self) -> None:
        (self.root / "docs/history").mkdir(parents=True, exist_ok=True)
        (self.root / "docs/history/merged.md").write_text("# merged\n", encoding="utf-8")
        semantic_settings = dsr.resolve_semantic_generation_settings(
            {"semantic_generation": {"enabled": True, "mode": "hybrid"}}
        )
        runtime_entries = [
            {
                "entry_id": "split-history-dry-run",
                "path": "docs/history/merged.md",
                "action_type": "split_doc",
                "status": "ok",
                "split_outputs": [
                    {
                        "path": "docs/history/part-a.md",
                        "content": "# part-a",
                        "source_paths": ["docs/history/merged.md"],
                    }
                ],
                "index_links": ["docs/history/part-a.md"],
            }
        ]
        runtime_state = {
            "enabled": True,
            "mode": "hybrid",
            "source": "invoking_agent",
            "available": True,
            "entry_count": 1,
            "error": None,
            "warnings": [],
        }

        result = doc_apply.apply_action(
            self.root,
            {
                "id": "A010B",
                "type": "split_doc",
                "path": "docs/history/merged.md",
                "source_path": "docs/history/merged.md",
                "target_paths": ["docs/history/part-a.md"],
                "index_path": "docs/index-generated.md",
            },
            dry_run=True,
            language_settings=self.language,
            template_profile=self.profile,
            metadata_policy=self.metadata_policy,
            semantic_settings=semantic_settings,
            semantic_runtime_entries=runtime_entries,
            semantic_runtime_state=runtime_state,
        )

        self.assertNotEqual(result.get("status"), "error")
        self.assertEqual(result.get("status"), "applied")
        semantic_runtime = result.get("semantic_runtime") or {}
        self.assertEqual(semantic_runtime.get("status"), "split_doc_runtime_applied")
        self.assertEqual(semantic_runtime.get("gate", {}).get("status"), "passed")
        self.assertFalse((self.root / "docs/index-generated.md").exists())

    def test_merge_docs_hybrid_fallback_generates_traceable_content(self) -> None:
        (self.root / "docs/history").mkdir(parents=True, exist_ok=True)
        (self.root / "docs/history/a.md").write_text("# A\n\ncontent-a\n", encoding="utf-8")
        (self.root / "docs/history/b.md").write_text("# B\n\ncontent-b\n", encoding="utf-8")
        semantic_settings = dsr.resolve_semantic_generation_settings(
            {"semantic_generation": {"enabled": True, "mode": "hybrid"}}
        )
        runtime_state = {
            "enabled": True,
            "mode": "hybrid",
            "source": "invoking_agent",
            "available": False,
            "entry_count": 0,
            "error": "runtime report not found",
            "warnings": [],
        }

        result = doc_apply.apply_action(
            self.root,
            {
                "id": "A011",
                "type": "merge_docs",
                "path": "docs/history/merged.md",
                "source_paths": ["docs/history/a.md", "docs/history/b.md"],
            },
            dry_run=False,
            language_settings=self.language,
            template_profile=self.profile,
            metadata_policy=self.metadata_policy,
            semantic_settings=semantic_settings,
            semantic_runtime_entries=[],
            semantic_runtime_state=runtime_state,
        )

        self.assertEqual(result.get("status"), "applied")
        self.assertIn("deterministic fallback", str(result.get("details", "")))
        semantic_runtime = result.get("semantic_runtime") or {}
        self.assertEqual(semantic_runtime.get("fallback_reason"), "runtime_unavailable")
        self.assertTrue(semantic_runtime.get("fallback_used"))
        merged_text = (self.root / "docs/history/merged.md").read_text(encoding="utf-8")
        self.assertIn("source-path: docs/history/a.md", merged_text)
        self.assertIn("source-path: docs/history/b.md", merged_text)

    def test_agents_generate_prefers_runtime_candidate_when_available(self) -> None:
        policy = lp.build_default_policy(primary_language="zh-CN", profile="zh-CN")
        policy["agents_generation"]["enabled"] = True
        policy["semantic_generation"]["enabled"] = True
        policy["semantic_generation"]["mode"] = "hybrid"
        (self.root / "docs/.doc-policy.json").write_text(
            json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        manifest = {
            "version": 1,
            "required": {
                "files": ["docs/index.md", "docs/.doc-policy.json", "docs/.doc-manifest.json"],
                "dirs": [],
            },
            "optional": {"files": []},
            "archive_dir": "docs/archive",
        }
        (self.root / "docs/.doc-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (self.root / "docs/index.md").write_text("# 文档索引\n", encoding="utf-8")
        (self.root / "docs/.repo-facts.json").write_text(
            json.dumps({"modules": ["skills"]}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (self.root / "docs/.semantic-runtime-report.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "entries": [
                        {
                            "entry_id": "agents-runtime",
                            "path": "AGENTS.md",
                            "action_type": "agents_generate",
                            "status": "ok",
                            "content": "# AGENTS\n\n## Runtime Candidate\n\n- generated by runtime\n",
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        plan_path = self.root / "docs/plan-agents.json"
        plan_path.write_text(
            json.dumps(
                {
                    "meta": {
                        "mode": "apply-safe",
                        "manifest_changed": True,
                        "manifest_effective": manifest,
                    },
                    "actions": [],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        cmd = [
            sys.executable,
            str(SCRIPT_DIR / "doc_apply.py"),
            "--root",
            str(self.root),
            "--plan",
            str(plan_path),
            "--mode",
            "apply-safe",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)

        agents_text = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("## Runtime Candidate", agents_text)
        self.assertIn("generated by runtime", agents_text)
        report = json.loads(
            (self.root / "docs/.doc-apply-report.json").read_text(encoding="utf-8")
        )
        agent_results = [
            item
            for item in (report.get("results") or [])
            if isinstance(item, dict) and item.get("type") == "agents_generate"
        ]
        self.assertEqual(len(agent_results), 1)
        self.assertIn(
            "runtime semantic candidate", str(agent_results[0].get("details", ""))
        )

    def test_agents_generate_agent_strict_requires_runtime_candidate(self) -> None:
        policy = lp.build_default_policy(primary_language="zh-CN", profile="zh-CN")
        policy["agents_generation"]["enabled"] = True
        policy["semantic_generation"]["enabled"] = True
        policy["semantic_generation"]["mode"] = "agent_strict"
        (self.root / "docs/.doc-policy.json").write_text(
            json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        manifest = {
            "version": 1,
            "required": {
                "files": ["docs/index.md", "docs/.doc-policy.json", "docs/.doc-manifest.json"],
                "dirs": [],
            },
            "optional": {"files": []},
            "archive_dir": "docs/archive",
        }
        (self.root / "docs/.doc-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (self.root / "docs/index.md").write_text("# 文档索引\n", encoding="utf-8")
        (self.root / "docs/.repo-facts.json").write_text(
            json.dumps({"modules": ["skills"]}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        plan_path = self.root / "docs/plan-agents-strict.json"
        plan_path.write_text(
            json.dumps(
                {
                    "meta": {
                        "mode": "apply-safe",
                        "manifest_changed": True,
                        "manifest_effective": manifest,
                    },
                    "actions": [],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        cmd = [
            sys.executable,
            str(SCRIPT_DIR / "doc_apply.py"),
            "--root",
            str(self.root),
            "--plan",
            str(plan_path),
            "--mode",
            "apply-safe",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1, msg=proc.stdout + proc.stderr)

        report = json.loads(
            (self.root / "docs/.doc-apply-report.json").read_text(encoding="utf-8")
        )
        agent_results = [
            item
            for item in (report.get("results") or [])
            if isinstance(item, dict) and item.get("type") == "agents_generate"
        ]
        self.assertEqual(len(agent_results), 1)
        self.assertEqual(agent_results[0].get("status"), "error")
        self.assertIn(
            "agent_strict requires runtime semantic candidate",
            str(agent_results[0].get("details", "")),
        )
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_agents_generate_deterministic_mode_skips_runtime_candidate(self) -> None:
        policy = lp.build_default_policy(primary_language="zh-CN", profile="zh-CN")
        policy["agents_generation"]["enabled"] = True
        policy["agents_generation"]["mode"] = "deterministic"
        policy["semantic_generation"]["enabled"] = True
        policy["semantic_generation"]["mode"] = "hybrid"
        (self.root / "docs/.doc-policy.json").write_text(
            json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        manifest = {
            "version": 1,
            "required": {
                "files": ["docs/index.md", "docs/.doc-policy.json", "docs/.doc-manifest.json"],
                "dirs": [],
            },
            "optional": {"files": []},
            "archive_dir": "docs/archive",
        }
        (self.root / "docs/.doc-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (self.root / "docs/index.md").write_text("# 文档索引\n", encoding="utf-8")
        (self.root / "docs/.repo-facts.json").write_text(
            json.dumps({"modules": ["skills"]}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (self.root / "docs/.semantic-runtime-report.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "entries": [
                        {
                            "entry_id": "agents-runtime",
                            "path": "AGENTS.md",
                            "action_type": "agents_generate",
                            "status": "ok",
                            "content": "# AGENTS\n\n## Runtime Candidate\n",
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        plan_path = self.root / "docs/plan-agents-deterministic.json"
        plan_path.write_text(
            json.dumps(
                {
                    "meta": {
                        "mode": "apply-safe",
                        "manifest_changed": True,
                        "manifest_effective": manifest,
                    },
                    "actions": [],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        cmd = [
            sys.executable,
            str(SCRIPT_DIR / "doc_apply.py"),
            "--root",
            str(self.root),
            "--plan",
            str(plan_path),
            "--mode",
            "apply-safe",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)

        agents_text = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("## 导航", agents_text)
        self.assertNotIn("## Runtime Candidate", agents_text)
        report = json.loads(
            (self.root / "docs/.doc-apply-report.json").read_text(encoding="utf-8")
        )
        agent_results = [
            item
            for item in (report.get("results") or [])
            if isinstance(item, dict) and item.get("type") == "agents_generate"
        ]
        self.assertEqual(len(agent_results), 1)
        self.assertIn("deterministic mode", str(agent_results[0].get("details", "")))
        semantic_runtime = agent_results[0].get("semantic_runtime") or {}
        self.assertEqual(semantic_runtime.get("status"), "deterministic_mode")

    def test_agents_generate_triggers_on_semantic_action_when_manifest_unchanged(self) -> None:
        policy = lp.build_default_policy(primary_language="zh-CN", profile="zh-CN")
        policy["agents_generation"]["enabled"] = True
        policy["agents_generation"]["sync_on_manifest_change"] = False
        policy["agents_generation"]["regenerate_on_semantic_actions"] = True
        policy["semantic_generation"]["enabled"] = True
        policy["semantic_generation"]["mode"] = "hybrid"
        (self.root / "docs/.doc-policy.json").write_text(
            json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        manifest = {
            "version": 1,
            "required": {
                "files": [
                    "docs/index.md",
                    "docs/runbook.md",
                    "docs/.doc-policy.json",
                    "docs/.doc-manifest.json",
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
        (self.root / "docs/index.md").write_text("# 文档索引\n", encoding="utf-8")
        (self.root / "docs/runbook.md").write_text("# 运行手册\n", encoding="utf-8")
        (self.root / "AGENTS.md").write_text("# AGENTS\n\nlegacy\n", encoding="utf-8")
        (self.root / "docs/.repo-facts.json").write_text(
            json.dumps({"modules": ["skills"]}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (self.root / "docs/.semantic-runtime-report.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "entries": [
                        {
                            "entry_id": "runbook-validation",
                            "path": "docs/runbook.md",
                            "action_type": "update_section",
                            "section_id": "validation_commands",
                            "status": "ok",
                            "content": "```bash\npython3 -m unittest discover\n```",
                        },
                        {
                            "entry_id": "agents-runtime",
                            "path": "AGENTS.md",
                            "action_type": "agents_generate",
                            "status": "ok",
                            "content": "# AGENTS\n\n## Runtime Refresh\n",
                        },
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        plan_path = self.root / "docs/plan-agents-semantic-trigger.json"
        plan_path.write_text(
            json.dumps(
                {
                    "meta": {
                        "mode": "apply-safe",
                        "manifest_changed": False,
                        "manifest_effective": manifest,
                    },
                    "actions": [
                        {
                            "id": "A100",
                            "type": "update_section",
                            "path": "docs/runbook.md",
                            "section_id": "validation_commands",
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        cmd = [
            sys.executable,
            str(SCRIPT_DIR / "doc_apply.py"),
            "--root",
            str(self.root),
            "--plan",
            str(plan_path),
            "--mode",
            "apply-safe",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)

        agents_text = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("## Runtime Refresh", agents_text)
        report = json.loads(
            (self.root / "docs/.doc-apply-report.json").read_text(encoding="utf-8")
        )
        agent_results = [
            item
            for item in (report.get("results") or [])
            if isinstance(item, dict) and item.get("type") == "agents_generate"
        ]
        self.assertEqual(len(agent_results), 1)
        self.assertIn(
            "runtime semantic candidate", str(agent_results[0].get("details", ""))
        )

    def test_navigation_repair_adds_missing_links_and_is_idempotent(self) -> None:
        index_path = self.root / "docs/index.md"
        index_path.write_text("# 文档索引\n", encoding="utf-8")
        action = {
            "id": "A200",
            "type": "navigation_repair",
            "path": "docs/index.md",
            "parent_path": "docs/index.md",
            "missing_children": ["docs/runbook.md"],
        }

        first = self._apply(action)
        second = self._apply(action)

        self.assertEqual(first.get("status"), "applied")
        self.assertEqual(second.get("status"), "skipped")
        content = index_path.read_text(encoding="utf-8")
        self.assertEqual(content.count("docs/runbook.md"), 1)
        self.assertIn("## 子级文档导航", content)

    def test_navigation_repair_skips_when_parent_missing(self) -> None:
        result = self._apply(
            {
                "id": "A201",
                "type": "navigation_repair",
                "path": "docs/missing-parent.md",
                "parent_path": "docs/missing-parent.md",
                "missing_children": ["docs/runbook.md"],
            }
        )
        self.assertEqual(result.get("status"), "skipped")
        self.assertIn("does not exist", str(result.get("details", "")))

    def test_topology_repair_is_consumed_by_apply(self) -> None:
        result = self._apply(
            {
                "id": "A202",
                "type": "topology_repair",
                "path": "docs/.doc-topology.json",
                "orphan_docs": ["docs/runbook.md"],
                "unreachable_docs": ["docs/architecture.md"],
                "over_depth_docs": [],
                "topology_metrics": {"topology_max_depth": 4, "topology_depth_limit": 3},
            }
        )
        self.assertEqual(result.get("status"), "applied")
        self.assertTrue((self.root / "docs/.doc-topology.json").exists())
        self.assertIn("topology", result)

    def test_summarize_semantic_observability_metrics(self) -> None:
        semantic_settings = dsr.resolve_semantic_generation_settings(
            {"semantic_generation": {"enabled": True, "mode": "hybrid"}}
        )
        results = [
            {
                "id": "A100",
                "type": "update_section",
                "path": "docs/runbook.md",
                "status": "applied",
                "semantic_runtime": {
                    "status": "section_runtime_applied",
                    "attempted": True,
                    "consumed": True,
                },
            },
            {
                "id": "A101",
                "type": "fill_claim",
                "path": "docs/runbook.md",
                "status": "applied",
                "semantic_runtime": {
                    "status": "claim_runtime_gate_failed",
                    "attempted": True,
                    "fallback_used": True,
                    "fallback_reason": "runtime_gate_failed",
                },
            },
            {
                "id": "A102",
                "type": "merge_docs",
                "path": "docs/history/merged.md",
                "status": "skipped",
                "semantic_runtime": {
                    "status": "semantic_attempt_missing",
                    "attempted": False,
                    "required": True,
                },
            },
            {
                "id": "A103",
                "type": "add",
                "path": "docs/architecture.md",
                "status": "applied",
            },
        ]

        summary = doc_apply.summarize_semantic_observability(results, semantic_settings)
        self.assertEqual(summary.get("semantic_action_count"), 3)
        self.assertEqual(summary.get("semantic_attempt_count"), 2)
        self.assertEqual(summary.get("semantic_success_count"), 1)
        self.assertEqual(summary.get("fallback_count"), 1)
        self.assertEqual(
            summary.get("fallback_reason_breakdown"),
            {"runtime_gate_failed": 1},
        )
        self.assertEqual(summary.get("semantic_unattempted_count"), 1)
        self.assertEqual(summary.get("semantic_unattempted_without_exemption"), 1)
        self.assertEqual(summary.get("semantic_hit_rate"), 0.5)

    def test_summarize_semantic_observability_includes_topology_navigation(self) -> None:
        semantic_settings = dsr.resolve_semantic_generation_settings(
            {"semantic_generation": {"enabled": True, "mode": "hybrid"}}
        )
        results = [
            {
                "id": "A300",
                "type": "navigation_repair",
                "path": "docs/index.md",
                "status": "applied",
                "semantic_runtime": {
                    "status": "navigation_runtime_applied",
                    "attempted": True,
                    "consumed": True,
                },
            },
            {
                "id": "A301",
                "type": "topology_repair",
                "path": "docs/.doc-topology.json",
                "status": "applied",
                "semantic_runtime": {
                    "status": "topology_runtime_gate_failed",
                    "attempted": True,
                    "fallback_used": True,
                    "fallback_reason": "runtime_gate_failed",
                },
            },
        ]

        summary = doc_apply.summarize_semantic_observability(results, semantic_settings)
        self.assertEqual(summary.get("semantic_action_count"), 2)
        self.assertEqual(summary.get("semantic_attempt_count"), 2)
        self.assertEqual(summary.get("semantic_success_count"), 1)
        self.assertEqual(summary.get("fallback_count"), 1)
        self.assertEqual(
            summary.get("fallback_reason_breakdown"),
            {"runtime_gate_failed": 1},
        )


if __name__ == "__main__":
    unittest.main()
