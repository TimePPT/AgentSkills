#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import doc_agents  # noqa: E402
import doc_agents_validate  # noqa: E402


class DocAgentsValidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "docs").mkdir(parents=True, exist_ok=True)
        scripts_root = self.root / "skills/docs-sor-maintainer/scripts"
        scripts_root.mkdir(parents=True, exist_ok=True)
        for name in ("repo_scan.py", "doc_plan.py", "doc_validate.py"):
            (scripts_root / name).write_text("# stub\n", encoding="utf-8")

        self.policy = {
            "agents_generation": {
                "enabled": True,
                "mode": "dynamic",
                "max_lines": 140,
                "required_links": [
                    "docs/index.md",
                    "docs/.doc-policy.json",
                    "docs/.doc-manifest.json",
                    "docs/runbook.md",
                ],
                "regenerate_on_semantic_actions": True,
                "sync_on_manifest_change": True,
                "fail_on_agents_drift": True,
                "max_overlap_ratio": 0.95,
            },
            "language": {"primary": "zh-CN", "profile": "zh-CN", "locked": True},
        }
        self.manifest = {
            "version": 1,
            "required": {"files": ["docs/index.md", "docs/runbook.md"], "dirs": []},
            "optional": {"files": []},
            "archive_dir": "docs/archive",
        }
        self.facts = {"modules": ["skills"], "repo_name": "AgentSkills"}
        (self.root / "docs/index.md").write_text(
            "# 文档索引\n\n- [runbook](./runbook.md)\n", encoding="utf-8"
        )
        (self.root / "docs/runbook.md").write_text("# 运行手册\n", encoding="utf-8")
        (self.root / "docs/.doc-policy.json").write_text("{}", encoding="utf-8")
        (self.root / "docs/.doc-manifest.json").write_text("{}", encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _generate(self) -> None:
        doc_agents.generate_agents_artifacts(
            root=self.root,
            policy=self.policy,
            manifest=self.manifest,
            facts=self.facts,
            output_path=self.root / "AGENTS.md",
            report_path=self.root / "docs/.agents-report.json",
            dry_run=False,
            force=False,
        )

    def test_agents_validate_passes_for_generated_content(self) -> None:
        self._generate()
        report = doc_agents_validate.evaluate_agents(
            root=self.root,
            policy=self.policy,
            agents_path=self.root / "AGENTS.md",
            index_path=self.root / "docs/index.md",
        )
        self.assertEqual(report.get("gate", {}).get("status"), "passed")

    def test_agents_validate_fails_when_required_link_missing(self) -> None:
        self._generate()
        agents = self.root / "AGENTS.md"
        content = agents.read_text(encoding="utf-8").replace(
            "[docs/runbook.md](./docs/runbook.md)", ""
        )
        agents.write_text(content, encoding="utf-8")

        report = doc_agents_validate.evaluate_agents(
            root=self.root,
            policy=self.policy,
            agents_path=self.root / "AGENTS.md",
            index_path=self.root / "docs/index.md",
        )
        self.assertEqual(report.get("gate", {}).get("status"), "failed")
        self.assertIn("required_links", report.get("gate", {}).get("failed_checks", []))


if __name__ == "__main__":
    unittest.main()
