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

import doc_semantic_runtime as dsr  # noqa: E402


class DocSemanticRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "docs").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_resolve_semantic_generation_settings_defaults(self) -> None:
        settings = dsr.resolve_semantic_generation_settings({})
        self.assertTrue(settings["enabled"])
        self.assertEqual(settings["mode"], "hybrid")
        self.assertEqual(
            settings["runtime_report_path"], "docs/.semantic-runtime-report.json"
        )
        self.assertFalse(settings["allow_external_llm_api"])
        self.assertTrue(settings["actions"]["fill_claim"])

    def test_resolve_semantic_generation_settings_normalizes_fields(self) -> None:
        policy = {
            "semantic_generation": {
                "enabled": True,
                "mode": "hybrid",
                "source": "  invoking_agent  ",
                "runtime_report_path": "./docs/.semantic-runtime-report.json",
                "max_output_chars_per_section": "1024",
                "required_evidence_prefixes": ["repo_scan.", "", "semantic_report."],
                "deny_paths": ["docs/adr/**", "  "],
                "actions": {"fill_claim": True, "agents_generate": False},
            }
        }
        settings = dsr.resolve_semantic_generation_settings(policy)
        self.assertTrue(settings["enabled"])
        self.assertEqual(settings["mode"], "hybrid")
        self.assertEqual(settings["source"], "invoking_agent")
        self.assertEqual(
            settings["runtime_report_path"], "docs/.semantic-runtime-report.json"
        )
        self.assertEqual(settings["max_output_chars_per_section"], 1024)
        self.assertIn("repo_scan.", settings["required_evidence_prefixes"])
        self.assertIn("docs/adr/**", settings["deny_paths"])
        self.assertTrue(settings["actions"]["fill_claim"])
        self.assertFalse(settings["actions"]["agents_generate"])

    def test_load_runtime_report_and_select_best_entry(self) -> None:
        report = {
            "version": 1,
            "entries": [
                {
                    "entry_id": "generic",
                    "path": "docs/runbook.md",
                    "action_type": "fill_claim",
                    "status": "ok",
                    "content": "generic content",
                },
                {
                    "entry_id": "specific",
                    "path": "docs/runbook.md",
                    "action_type": "fill_claim",
                    "section_id": "dev_commands",
                    "claim_id": "runbook.dev_commands",
                    "status": "ok",
                    "statement": "specific claim statement",
                    "content": "specific content",
                    "citations": ["evidence://repo_scan.modules"],
                },
            ],
        }
        report_path = self.root / "docs/.semantic-runtime-report.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        settings = dsr.resolve_semantic_generation_settings(
            {
                "semantic_generation": {
                    "enabled": True,
                    "mode": "hybrid",
                }
            }
        )

        entries, metadata = dsr.load_runtime_report(self.root, settings)
        self.assertTrue(metadata["available"])
        self.assertEqual(metadata["entry_count"], 2)

        action = {
            "type": "fill_claim",
            "path": "docs/runbook.md",
            "section_id": "dev_commands",
            "claim_id": "runbook.dev_commands",
        }
        candidate = dsr.select_runtime_entry(action, entries, settings)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["entry_id"], "specific")
        self.assertEqual(candidate.get("statement"), "specific claim statement")

    def test_load_runtime_report_accepts_statement_only_fill_claim_entry(self) -> None:
        report_path = self.root / "docs/.semantic-runtime-report.json"
        report_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "entries": [
                        {
                            "entry_id": "claim-statement-only",
                            "path": "docs/runbook.md",
                            "action_type": "fill_claim",
                            "section_id": "dev_commands",
                            "claim_id": "runbook.dev_commands",
                            "status": "ok",
                            "statement": "statement only",
                            "citations": ["evidence://runbook.dev_commands"],
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        settings = dsr.resolve_semantic_generation_settings(
            {
                "semantic_generation": {
                    "enabled": True,
                    "mode": "hybrid",
                }
            }
        )
        entries, metadata = dsr.load_runtime_report(self.root, settings)
        self.assertTrue(metadata["available"])
        self.assertEqual(metadata["entry_count"], 1)
        self.assertEqual(entries[0].get("statement"), "statement only")
        self.assertEqual(entries[0].get("content"), "statement only")

    def test_load_runtime_report_accepts_slots_only_update_section_entry(self) -> None:
        report_path = self.root / "docs/.semantic-runtime-report.json"
        report_path.write_text(
            json.dumps(
                {
                    "version": 2,
                    "entries": [
                        {
                            "entry_id": "runbook-slots-v2",
                            "path": "docs/runbook.md",
                            "action_type": "update_section",
                            "section_id": "validation_commands",
                            "status": "ok",
                            "slots": {
                                "summary": "validate gate should run before merge.",
                                "key_facts": ["facts from docs/.repo-facts.json"],
                                "next_steps": ["run doc_validate --fail-on-drift"],
                            },
                            "citations": ["evidence://runbook.validation_commands"],
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        settings = dsr.resolve_semantic_generation_settings(
            {
                "semantic_generation": {
                    "enabled": True,
                    "mode": "hybrid",
                }
            }
        )
        entries, metadata = dsr.load_runtime_report(self.root, settings)

        self.assertTrue(metadata["available"])
        self.assertEqual(metadata["entry_count"], 1)
        slots = entries[0].get("slots") or {}
        self.assertEqual(slots.get("summary"), "validate gate should run before merge.")
        self.assertEqual(slots.get("key_facts"), ["facts from docs/.repo-facts.json"])
        self.assertEqual(slots.get("next_steps"), ["run doc_validate --fail-on-drift"])

    def test_load_runtime_report_fails_when_entries_not_list(self) -> None:
        report_path = self.root / "docs/.semantic-runtime-report.json"
        report_path.write_text(
            json.dumps({"version": 1, "entries": {}}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        settings = dsr.resolve_semantic_generation_settings(
            {
                "semantic_generation": {
                    "enabled": True,
                    "mode": "hybrid",
                }
            }
        )

        entries, metadata = dsr.load_runtime_report(self.root, settings)
        self.assertEqual(entries, [])
        self.assertFalse(metadata["available"])
        self.assertIn("entries must be list", metadata["error"])


if __name__ == "__main__":
    unittest.main()
