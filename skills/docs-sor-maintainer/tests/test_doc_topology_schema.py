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
import doc_apply  # noqa: E402
import doc_topology as dt  # noqa: E402
import doc_validate  # noqa: E402
import language_profiles as lp  # noqa: E402


class DocTopologyContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "docs").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_index(self) -> None:
        content = "\n".join(
            [
                "<!-- doc-owner: docs-maintainer -->",
                "<!-- doc-last-reviewed: 2026-02-24 -->",
                "<!-- doc-review-cycle-days: 90 -->",
                "",
                lp.get_managed_template("docs/index.md", "zh-CN").rstrip(),
            ]
        )
        (self.root / "docs/index.md").write_text(content + "\n", encoding="utf-8")

    def _write_manifest(self, *, include_topology: bool = False) -> Path:
        required_files = ["docs/index.md"]
        if include_topology:
            required_files.append("docs/.doc-topology.json")
        manifest = {
            "version": 1,
            "required": {
                "files": required_files,
                "dirs": [],
            },
            "optional": {"files": []},
            "archive_dir": "docs/archive",
        }
        path = self.root / "docs/.doc-manifest.json"
        path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def _write_policy(self, *, topology_enabled: bool) -> Path:
        policy = lp.build_default_policy(primary_language="zh-CN", profile="zh-CN")
        policy["allow_auto_update"] = []
        policy["doc_metadata"]["enabled"] = False
        policy["doc_topology"]["enabled"] = topology_enabled
        path = self.root / "docs/.doc-policy.json"
        path.write_text(
            json.dumps(policy, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def test_resolve_settings_defaults_are_backward_compatible(self) -> None:
        topology = dt.resolve_topology_settings({})
        progressive = dt.resolve_progressive_disclosure_settings({})
        self.assertFalse(topology["enabled"])
        self.assertEqual(topology["path"], "docs/.doc-topology.json")
        self.assertFalse(progressive["enabled"])
        self.assertEqual(
            progressive["required_slots"], ["summary", "key_facts", "next_steps"]
        )

    def test_plan_is_compatible_when_topology_disabled_and_file_missing(self) -> None:
        policy_path = self._write_policy(topology_enabled=False)
        manifest_path = self._write_manifest()
        self._write_index()

        plan = doc_plan.build_plan(
            root=self.root,
            mode="audit",
            facts=None,
            policy_path=policy_path,
            manifest_path=manifest_path,
        )

        topology_meta = (plan.get("meta") or {}).get("doc_topology") or {}
        self.assertFalse(topology_meta.get("enabled", True))
        self.assertFalse(topology_meta.get("exists", True))
        self.assertFalse(topology_meta.get("loaded", True))
        self.assertFalse(
            any(
                action.get("path") == "docs/.doc-topology.json"
                for action in (plan.get("actions") or [])
            )
        )

    def test_plan_emits_manual_review_when_topology_enabled_but_missing(self) -> None:
        policy_path = self._write_policy(topology_enabled=True)
        manifest_path = self._write_manifest()
        self._write_index()

        plan = doc_plan.build_plan(
            root=self.root,
            mode="audit",
            facts=None,
            policy_path=policy_path,
            manifest_path=manifest_path,
        )

        topology_actions = [
            action
            for action in (plan.get("actions") or [])
            if action.get("path") == "docs/.doc-topology.json"
        ]
        self.assertEqual(len(topology_actions), 1)
        self.assertEqual(topology_actions[0].get("type"), "manual_review")
        self.assertEqual(
            topology_actions[0].get("reason"),
            "topology contract enabled but file is missing",
        )

    def test_plan_emits_add_with_topology_template_when_declared_in_manifest(self) -> None:
        policy_path = self._write_policy(topology_enabled=True)
        manifest_path = self._write_manifest(include_topology=True)
        self._write_index()

        plan = doc_plan.build_plan(
            root=self.root,
            mode="audit",
            facts=None,
            policy_path=policy_path,
            manifest_path=manifest_path,
        )

        topology_actions = [
            action
            for action in (plan.get("actions") or [])
            if action.get("path") == "docs/.doc-topology.json"
        ]
        self.assertEqual(len(topology_actions), 1)
        self.assertEqual(topology_actions[0].get("type"), "add")
        self.assertEqual(topology_actions[0].get("template"), "topology")

    def test_apply_add_topology_writes_valid_json_contract(self) -> None:
        language_settings = lp.resolve_language_settings({}, None)
        result = doc_apply.apply_action(
            root=self.root,
            action={
                "id": "A001",
                "type": "add",
                "kind": "file",
                "path": "docs/.doc-topology.json",
                "template": "topology",
            },
            dry_run=False,
            language_settings=language_settings,
            template_profile=language_settings["profile"],
            metadata_policy={"enabled": False},
        )
        self.assertEqual(result.get("status"), "applied")

        topology_path = self.root / "docs/.doc-topology.json"
        payload = json.loads(topology_path.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("root"), "docs/index.md")
        self.assertEqual(payload.get("max_depth"), 3)
        nodes = payload.get("nodes") or []
        self.assertTrue(nodes)
        self.assertEqual(nodes[0].get("layer"), "root")

    def test_validate_reports_schema_errors_when_topology_invalid(self) -> None:
        policy = lp.build_default_policy(primary_language="zh-CN", profile="zh-CN")
        policy["doc_topology"]["enabled"] = True
        (self.root / "docs/.doc-topology.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "root": "docs/index.md",
                    "max_depth": 3,
                    "nodes": "invalid",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        errors, warnings, report = doc_validate.check_topology_contract(
            self.root, policy
        )
        self.assertTrue(errors)
        self.assertTrue(any("nodes must be list" in err for err in errors))
        self.assertTrue(any("nodes is empty" in warning for warning in warnings))
        self.assertFalse(report.get("loaded", True))
        self.assertTrue(report.get("exists", False))

    def test_validate_passes_when_topology_contract_is_valid(self) -> None:
        policy = lp.build_default_policy(primary_language="zh-CN", profile="zh-CN")
        policy["doc_topology"]["enabled"] = True
        (self.root / "docs/index.md").write_text("# 文档索引\n", encoding="utf-8")
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
                        }
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
            self.root, policy
        )
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertTrue(report.get("loaded", False))
        self.assertEqual((report.get("metrics") or {}).get("node_count"), 1)

    def test_evaluate_topology_honors_archive_excluded_flag(self) -> None:
        (self.root / "docs/index.md").write_text("# 文档索引\n", encoding="utf-8")
        (self.root / "docs/archive").mkdir(parents=True, exist_ok=True)
        (self.root / "docs/archive/history.md").write_text(
            "# 历史记录\n", encoding="utf-8"
        )

        contract = {
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
                    "path": "docs/archive/history.md",
                    "layer": "archive",
                    "parent": "docs/index.md",
                    "domain": "history",
                },
            ],
            "archive": {
                "root": "docs/archive",
                "excluded_from_depth_gate": False,
            },
        }
        settings = dt.resolve_topology_settings(
            {"doc_topology": {"enabled": True, "max_depth": 3}}
        )

        analysis = dt.evaluate_topology(
            self.root,
            contract,
            settings,
            managed_docs=["docs/index.md", "docs/archive/history.md"],
        )
        self.assertIn("docs/archive/history.md", analysis.get("scope_docs", []))
        self.assertEqual((analysis.get("metrics") or {}).get("managed_markdown_count"), 2)

        contract_excluded = json.loads(json.dumps(contract))
        contract_excluded["archive"]["excluded_from_depth_gate"] = True
        analysis_excluded = dt.evaluate_topology(
            self.root,
            contract_excluded,
            settings,
            managed_docs=["docs/index.md", "docs/archive/history.md"],
        )
        self.assertNotIn(
            "docs/archive/history.md", analysis_excluded.get("scope_docs", [])
        )
        self.assertEqual(
            (analysis_excluded.get("metrics") or {}).get("managed_markdown_count"), 1
        )


if __name__ == "__main__":
    unittest.main()
