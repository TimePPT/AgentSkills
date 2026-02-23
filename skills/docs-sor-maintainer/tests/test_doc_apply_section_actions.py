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
        content = runbook.read_text(encoding="utf-8")
        self.assertIn("TODO(claim:runbook.dev_commands)", content)
        self.assertNotIn("CLAIM(claim:runbook.dev_commands)", content)

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


if __name__ == "__main__":
    unittest.main()
