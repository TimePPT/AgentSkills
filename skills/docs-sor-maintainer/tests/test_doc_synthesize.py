#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import subprocess
import json
import sys


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import doc_synthesize  # noqa: E402


class DocSynthesizeEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "docs").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_runbook_command_evidence_is_supported(self) -> None:
        (self.root / "docs/runbook.md").write_text(
            "\n".join(
                [
                    "# 运行手册",
                    "",
                    "## 开发命令",
                    "",
                    "```bash",
                    "python3 script_a.py",
                    "python3 script_b.py",
                    "```",
                    "",
                    "## 校验命令",
                    "",
                    "```bash",
                    "python3 -m unittest",
                    "```",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        claim = {
            "claim_id": "runbook.dev_commands",
            "statement_template": "当前开发命令集合为：{commands}",
            "required_evidence_types": ["runbook.dev_commands"],
            "allow_unknown": False,
        }

        entry, status = doc_synthesize.build_claim_entry(
            claim=claim,
            facts=None,
            root=self.root,
            runbook_cache={},
        )

        self.assertEqual(status, "supported")
        self.assertEqual(entry["missing_evidence_types"], [])
        self.assertIn("python3 script_a.py", entry["statement"])
        self.assertIn("python3 script_b.py", entry["statement"])
        self.assertEqual(entry["citation"], "evidence://runbook.dev_commands")
        self.assertEqual(entry["citations"], ["evidence://runbook.dev_commands"])

    def test_bool_manifest_map_summarizes_to_none(self) -> None:
        claim = {
            "claim_id": "architecture.dependencies.manifests",
            "statement_template": "仓库依赖清单包括：{manifests}",
            "required_evidence_types": ["repo_scan.manifests"],
            "allow_unknown": False,
        }
        facts = {
            "manifests": {
                "go.mod": False,
                "package.json": False,
                "pyproject.toml": False,
            }
        }

        entry, status = doc_synthesize.build_claim_entry(
            claim=claim,
            facts=facts,
            root=self.root,
            runbook_cache={},
        )

        self.assertEqual(status, "supported")
        self.assertIn("none", entry["statement"])
        self.assertNotIn("UNKNOWN", entry["statement"])
        self.assertEqual(
            entry["citations"], ["evidence://repo_scan.manifests"]
        )

    def test_synthesize_succeeds_when_doc_spec_missing(self) -> None:
        plan_path = self.root / "docs/.doc-plan.json"
        facts_path = self.root / "docs/.repo-facts.json"
        output_path = self.root / "docs/.doc-evidence-map.json"
        plan_path.write_text("{}", encoding="utf-8")
        facts_path.write_text("{}", encoding="utf-8")

        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "doc_synthesize.py"),
                "--root",
                str(self.root),
                "--plan",
                str(plan_path),
                "--facts",
                str(facts_path),
                "--output",
                str(output_path),
            ],
            capture_output=True,
            text=True,
        )

        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertTrue(output_path.exists())
        report = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(report.get("metrics"), {"claims": 0, "supported": 0, "unknown": 0, "missing": 0})
        self.assertEqual(report.get("documents"), [])


if __name__ == "__main__":
    unittest.main()
