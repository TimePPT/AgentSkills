#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import doc_validate  # noqa: E402
import language_profiles as lp  # noqa: E402


class ScopedValidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "docs").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _manifest(self) -> dict[str, object]:
        return {
            "version": 1,
            "required": {
                "files": [
                    "docs/index.md",
                    "docs/runbook.md",
                    "docs/architecture.md",
                    "docs/.doc-topology.json",
                ],
                "dirs": [],
            },
            "optional": {"files": []},
            "archive_dir": "docs/archive",
        }

    def _policy(self) -> dict[str, object]:
        policy = lp.build_default_policy(primary_language="zh-CN", profile="zh-CN")
        policy["doc_topology"]["enabled"] = True
        return policy

    def _write_docs(self) -> None:
        (self.root / "docs/index.md").write_text(
            "# 文档索引\n\n- [runbook](./runbook.md)\n",
            encoding="utf-8",
        )
        (self.root / "docs/runbook.md").write_text(
            "# 运行手册\n\n- [architecture](./architecture.md)\n",
            encoding="utf-8",
        )
        (self.root / "docs/architecture.md").write_text(
            "# 架构\n",
            encoding="utf-8",
        )
        (self.root / "docs/.doc-topology.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "root": "docs/index.md",
                    "nodes": [
                        {
                            "path": "docs/index.md",
                            "layer": "root",
                            "parent": None,
                            "domain": "core",
                        },
                        {
                            "path": "docs/runbook.md",
                            "layer": "section",
                            "parent": "docs/index.md",
                            "domain": "operations",
                        },
                        {
                            "path": "docs/architecture.md",
                            "layer": "section",
                            "parent": "docs/runbook.md",
                            "domain": "architecture",
                        },
                    ],
                    "archive": {
                        "root": "docs/archive",
                        "excluded_from_depth_gate": True,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def test_resolve_scope_expands_link_and_topology_dependencies(self) -> None:
        self._write_docs()
        scope = doc_validate.resolve_validation_scope(
            self.root,
            self._policy(),
            self._manifest(),
            scope_mode="changed",
            scope_files=["docs/runbook.md"],
        )
        self.assertEqual(scope.get("effective_mode"), "scoped")
        scope_docs = set(scope.get("scope_docs") or [])
        self.assertIn("docs/runbook.md", scope_docs)
        self.assertIn("docs/index.md", scope_docs)
        self.assertIn("docs/architecture.md", scope_docs)
        self.assertIsNone(scope.get("upgrade_reason"))

    def test_resolve_scope_upgrades_full_on_high_risk_change(self) -> None:
        scope = doc_validate.resolve_validation_scope(
            self.root,
            self._policy(),
            self._manifest(),
            scope_mode="changed",
            scope_files=["docs/.doc-policy.json"],
        )
        self.assertEqual(scope.get("effective_mode"), "full")
        self.assertTrue(str(scope.get("upgrade_reason", "")).startswith("high_risk_change"))

    def test_check_drift_scoped_keeps_sync_manifest_action(self) -> None:
        fake_plan = {
            "actions": [
                {
                    "id": "A001",
                    "type": "sync_manifest",
                    "path": "docs/.doc-manifest.json",
                    "manifest_snapshot": self._manifest(),
                }
            ]
        }
        with patch.object(doc_validate.doc_plan, "build_plan", return_value=fake_plan):
            has_drift, drift_count, drift_notes = doc_validate.check_drift(
                self.root,
                self.root / "docs/.doc-policy.json",
                self.root / "docs/.doc-manifest.json",
                facts=None,
                scope_docs={"docs/runbook.md"},
            )
        self.assertTrue(has_drift)
        self.assertEqual(drift_count, 1)
        self.assertEqual(len(drift_notes), 1)
        self.assertIn("sync_manifest", drift_notes[0])


if __name__ == "__main__":
    unittest.main()
