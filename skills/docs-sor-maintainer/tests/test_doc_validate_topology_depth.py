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

import doc_plan  # noqa: E402
import doc_validate  # noqa: E402
import language_profiles as lp  # noqa: E402


class DocTopologyDepthGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "docs").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_docs(self) -> None:
        (self.root / "docs/index.md").write_text(
            "# 文档索引\n\n- [runbook](./runbook.md)\n",
            encoding="utf-8",
        )
        (self.root / "docs/runbook.md").write_text(
            "# 运行手册\n",
            encoding="utf-8",
        )
        (self.root / "docs/leaf.md").write_text("# Leaf\n", encoding="utf-8")

    def _write_topology(self) -> None:
        payload = {
            "version": 1,
            "root": "docs/index.md",
            "max_depth": 3,
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
                    "path": "docs/leaf.md",
                    "layer": "leaf",
                    "parent": "docs/runbook.md",
                    "domain": "reference",
                },
            ],
            "archive": {
                "root": "docs/archive",
                "excluded_from_depth_gate": True,
            },
        }
        (self.root / "docs/.doc-topology.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _policy(self, *, max_depth: int) -> dict[str, object]:
        policy = lp.build_default_policy(primary_language="zh-CN", profile="zh-CN")
        policy["doc_metadata"]["enabled"] = False
        policy["doc_quality_gates"]["enabled"] = False
        policy["doc_topology"]["enabled"] = True
        policy["doc_topology"]["max_depth"] = max_depth
        policy["doc_topology"]["enforce_max_depth"] = True
        policy["doc_topology"]["fail_on_orphan"] = True
        policy["doc_topology"]["fail_on_unreachable"] = True
        return policy

    def _manifest(self) -> dict[str, object]:
        return {
            "version": 1,
            "required": {
                "files": [
                    "docs/index.md",
                    "docs/runbook.md",
                    "docs/leaf.md",
                    "docs/.doc-topology.json",
                ],
                "dirs": [],
            },
            "optional": {"files": []},
            "archive_dir": "docs/archive",
        }

    def test_validate_topology_gate_fails_for_unreachable_and_over_depth(self) -> None:
        self._write_docs()
        self._write_topology()
        policy = self._policy(max_depth=1)
        manifest = self._manifest()

        errors, warnings, report = doc_validate.check_topology_contract(
            self.root, policy, manifest
        )

        self.assertTrue(any("unreachable docs detected" in item for item in errors))
        self.assertTrue(any("depth limit exceeded" in item for item in errors))
        metrics = report.get("metrics") or {}
        self.assertEqual(metrics.get("topology_orphan_count"), 0)
        self.assertEqual(metrics.get("topology_unreachable_count"), 1)
        self.assertEqual(metrics.get("topology_max_depth"), 2)
        self.assertEqual(metrics.get("topology_depth_limit"), 1)
        self.assertLess(float(metrics.get("topology_reachable_ratio", 1.0)), 1.0)
        self.assertEqual(warnings, [])

    def test_plan_emits_topology_and_navigation_repairs(self) -> None:
        self._write_docs()
        self._write_topology()
        policy = self._policy(max_depth=3)
        manifest = self._manifest()
        policy_path = self.root / "docs/.doc-policy.json"
        manifest_path = self.root / "docs/.doc-manifest.json"
        policy_path.write_text(
            json.dumps(policy, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        plan = doc_plan.build_plan(
            root=self.root,
            mode="audit",
            facts=None,
            policy_path=policy_path,
            manifest_path=manifest_path,
        )
        actions = plan.get("actions") or []
        action_types = {str(action.get("type")) for action in actions if isinstance(action, dict)}

        self.assertIn("topology_repair", action_types)
        self.assertIn("navigation_repair", action_types)

    def test_validate_merges_topology_analysis_warnings_into_report(self) -> None:
        self._write_docs()
        policy = self._policy(max_depth=3)
        policy["doc_topology"]["fail_on_orphan"] = False
        policy["doc_topology"]["fail_on_unreachable"] = False
        manifest = self._manifest()
        (self.root / "docs/.doc-topology.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "root": "docs/index.md",
                    "max_depth": 3,
                    "nodes": [
                        {
                            "path": "docs/index.md",
                            "layer": "root",
                            "parent": None,
                            "domain": "core",
                        },
                        {
                            "path": "docs/missing.md",
                            "layer": "leaf",
                            "parent": "docs/index.md",
                            "domain": "reference",
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

        errors, warnings, report = doc_validate.check_topology_contract(
            self.root, policy, manifest
        )

        self.assertEqual(errors, [])
        report_warnings = report.get("warnings") or []
        self.assertTrue(any("docs/missing.md" in item for item in report_warnings))
        self.assertTrue(any("docs/missing.md" in item for item in warnings))
        self.assertEqual(len(report_warnings), len(set(report_warnings)))


if __name__ == "__main__":
    unittest.main()
