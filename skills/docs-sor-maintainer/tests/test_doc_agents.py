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

import doc_agents  # noqa: E402


class DocAgentsGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "docs").mkdir(parents=True, exist_ok=True)
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
            },
            "language": {"primary": "zh-CN", "profile": "zh-CN", "locked": True},
        }
        self.manifest = {
            "version": 1,
            "required": {
                "files": [
                    "docs/index.md",
                    "docs/runbook.md",
                    "docs/architecture.md",
                ],
                "dirs": [],
            },
            "optional": {"files": []},
            "archive_dir": "docs/archive",
        }
        self.facts = {"modules": ["skills"], "repo_name": "AgentSkills"}

        (self.root / "docs/index.md").write_text(
            "# 文档索引\n\n- [runbook](./runbook.md)\n", encoding="utf-8"
        )
        (self.root / "docs/runbook.md").write_text("# 运行手册\n", encoding="utf-8")
        (self.root / "docs/architecture.md").write_text(
            "# 仓库架构\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_generate_agents_artifacts(self) -> None:
        output_path = self.root / "AGENTS.md"
        report_path = self.root / "docs/.agents-report.json"
        content, report = doc_agents.generate_agents_artifacts(
            root=self.root,
            policy=self.policy,
            manifest=self.manifest,
            facts=self.facts,
            output_path=output_path,
            report_path=report_path,
            dry_run=False,
            force=False,
        )

        self.assertTrue(output_path.exists())
        self.assertTrue(report_path.exists())
        self.assertIn("## 导航", content)
        self.assertIn("[docs/index.md](./docs/index.md)", content)
        self.assertEqual(report.get("status"), "generated")
        self.assertGreater(report.get("metrics", {}).get("line_count", 0), 0)

        stored_report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(stored_report.get("status"), "generated")

    def test_resolve_agents_settings_includes_semantic_regenerate_toggle(self) -> None:
        settings = doc_agents.resolve_agents_settings(self.policy)
        self.assertTrue(settings.get("regenerate_on_semantic_actions"))


if __name__ == "__main__":
    unittest.main()
