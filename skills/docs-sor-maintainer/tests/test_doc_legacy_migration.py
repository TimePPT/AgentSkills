#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import doc_apply  # noqa: E402
import doc_legacy as dl  # noqa: E402
import doc_metadata as dm  # noqa: E402
import doc_plan  # noqa: E402
import doc_quality  # noqa: E402
import doc_validate  # noqa: E402
import language_profiles as lp  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DocLegacyMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "docs").mkdir(parents=True, exist_ok=True)
        (self.root / "legacy").mkdir(parents=True, exist_ok=True)
        (self.root / "docs/index.md").write_text("# 文档索引\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_policy(
        self,
        *,
        semantic_enabled: bool = False,
        semantic_provider: str = "deterministic_mock",
        semantic_model: str = "gpt-5-codex",
        allow_fallback_auto_migrate: bool = False,
        include_globs: list[str] | None = None,
        exclude_globs: list[str] | None = None,
    ) -> dict[str, object]:
        policy = lp.build_default_policy(primary_language="zh-CN", profile="zh-CN")
        policy["legacy_sources"] = {
            "enabled": True,
            "include_globs": include_globs if isinstance(include_globs, list) else ["legacy/**"],
            "exclude_globs": exclude_globs if isinstance(exclude_globs, list) else [],
            "archive_root": "docs/archive/legacy",
            "mapping_strategy": "path_based",
            "target_root": "docs/history/legacy",
            "target_doc": "docs/history/legacy-migration.md",
            "registry_path": "docs/.legacy-migration-map.json",
            "allow_non_markdown": True,
            "exempt_sources": [],
            "mapping_table": {},
            "fail_on_legacy_drift": True,
            "semantic_report_path": "docs/.legacy-semantic-report.json",
            "semantic": {
                "enabled": semantic_enabled,
                "engine": "llm",
                "provider": semantic_provider,
                "model": semantic_model,
                "auto_migrate_threshold": 0.85,
                "review_threshold": 0.60,
                "max_chars_per_doc": 20000,
                "categories": [
                    "requirement",
                    "plan",
                    "progress",
                    "worklog",
                    "agent_ops",
                    "not_migratable",
                ],
                "denylist_files": ["README.md", "AGENTS.md"],
                "fail_closed": True,
                "allow_fallback_auto_migrate": allow_fallback_auto_migrate,
            },
        }
        (self.root / "docs/.doc-policy.json").write_text(
            json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return policy

    def _write_manifest(self) -> None:
        manifest = {
            "version": 1,
            "required": {"files": ["docs/index.md"], "dirs": []},
            "optional": {"files": []},
            "archive_dir": "docs/archive",
        }
        (self.root / "docs/.doc-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_plan_emits_migrate_and_archive_actions_for_legacy_sources(self) -> None:
        self._write_policy()
        self._write_manifest()
        (self.root / "legacy/notes.txt").write_text("legacy content\n", encoding="utf-8")

        plan = doc_plan.build_plan(
            root=self.root,
            mode="apply-with-archive",
            facts={"generated_at": utc_now()},
            policy_path=self.root / "docs/.doc-policy.json",
            manifest_path=self.root / "docs/.doc-manifest.json",
        )

        actions = plan.get("actions") or []
        types = [action.get("type") for action in actions]
        self.assertIn("migrate_legacy", types)
        self.assertIn("archive_legacy", types)
        self.assertIn("sync_manifest", types)

        migrate = next(action for action in actions if action.get("type") == "migrate_legacy")
        archive = next(action for action in actions if action.get("type") == "archive_legacy")
        self.assertEqual(migrate.get("source_path"), "legacy/notes.txt")
        self.assertEqual(archive.get("source_path"), "legacy/notes.txt")
        self.assertEqual(migrate.get("archive_path"), archive.get("path"))
        self.assertTrue(str(migrate.get("path")).startswith("docs/history/legacy/"))

    def test_apply_migrates_and_archives_legacy_source_with_registry(self) -> None:
        policy = self._write_policy()
        settings = dl.resolve_legacy_settings(policy)
        source_rel = "legacy/log.txt"
        source_abs = self.root / source_rel
        source_abs.write_text("line1\nline2\n", encoding="utf-8")

        language = {
            "primary": "zh-CN",
            "profile": "zh-CN",
            "locked": False,
            "source": "test",
        }
        metadata_policy = dm.resolve_metadata_policy(policy)
        target_rel = dl.resolve_target_path(source_rel, settings)
        archive_rel = dl.resolve_archive_path(source_rel, settings)

        migrate_result = doc_apply.apply_action(
            self.root,
            {
                "id": "A001",
                "type": "migrate_legacy",
                "kind": "file",
                "path": target_rel,
                "source_path": source_rel,
                "archive_path": archive_rel,
            },
            dry_run=False,
            language_settings=language,
            template_profile="zh-CN",
            metadata_policy=metadata_policy,
            legacy_settings=settings,
        )
        archive_result = doc_apply.apply_action(
            self.root,
            {
                "id": "A002",
                "type": "archive_legacy",
                "kind": "file",
                "path": archive_rel,
                "source_path": source_rel,
                "target_path": target_rel,
            },
            dry_run=False,
            language_settings=language,
            template_profile="zh-CN",
            metadata_policy=metadata_policy,
            legacy_settings=settings,
        )

        self.assertEqual(migrate_result.get("status"), "applied")
        self.assertEqual(archive_result.get("status"), "applied")

        target_text = (self.root / target_rel).read_text(encoding="utf-8")
        self.assertIn(dl.source_marker(source_rel), target_text)
        self.assertIn("line1", target_text)
        self.assertFalse(source_abs.exists())
        self.assertTrue((self.root / archive_rel).exists())

        registry = dl.load_registry(self.root / settings["registry_path"])
        entry = (registry.get("entries") or {}).get(source_rel)
        self.assertIsInstance(entry, dict)
        self.assertEqual(entry.get("status"), "archived")
        self.assertEqual(entry.get("archive_path"), archive_rel)

    def test_validate_legacy_gate_detects_unresolved_and_passes_after_archive(self) -> None:
        policy = self._write_policy()
        self._write_manifest()
        settings = dl.resolve_legacy_settings(policy)
        source_rel = "legacy/todo.md"
        source_abs = self.root / source_rel
        source_abs.write_text("# TODO\n", encoding="utf-8")

        errors, warnings, report = doc_validate.check_legacy_coverage(self.root, policy)
        self.assertTrue(errors)
        self.assertIn("legacy unresolved sources", errors[0])
        self.assertEqual(report.get("metrics", {}).get("unresolved_sources"), 1)
        self.assertEqual(warnings, [])

        target_rel = dl.resolve_target_path(source_rel, settings)
        archive_rel = dl.resolve_archive_path(source_rel, settings)
        (self.root / Path(target_rel)).parent.mkdir(parents=True, exist_ok=True)
        (self.root / target_rel).write_text(
            dl.render_target_header("zh-CN")
            + "\n"
            + dl.render_migration_entry(source_rel, "# TODO\n", archive_rel, "zh-CN"),
            encoding="utf-8",
        )
        (self.root / Path(archive_rel)).parent.mkdir(parents=True, exist_ok=True)
        (self.root / archive_rel).write_text("# TODO\n", encoding="utf-8")
        source_abs.unlink()

        registry_path = self.root / settings["registry_path"]
        registry = dl.load_registry(registry_path)
        dl.upsert_registry_entry(
            registry,
            source_rel,
            {
                "status": "archived",
                "target_path": target_rel,
                "archive_path": archive_rel,
            },
        )
        dl.save_registry(registry_path, registry, dry_run=False)

        errors2, _, report2 = doc_validate.check_legacy_coverage(self.root, policy)
        self.assertEqual(errors2, [])
        self.assertEqual(report2.get("metrics", {}).get("unresolved_sources"), 0)

    def test_resolve_legacy_settings_parses_semantic_policy(self) -> None:
        policy = self._write_policy(semantic_enabled=True)
        settings = dl.resolve_legacy_settings(policy)
        semantic = settings.get("semantic") or {}

        self.assertTrue(semantic.get("enabled"))
        self.assertEqual(semantic.get("engine"), "llm")
        self.assertEqual(semantic.get("provider"), "deterministic_mock")
        self.assertEqual(semantic.get("model"), "gpt-5-codex")
        self.assertEqual(settings.get("semantic_report_path"), "docs/.legacy-semantic-report.json")
        self.assertIn("not_migratable", semantic.get("categories") or [])

    def test_semantic_classifier_uses_mock_provider_and_denylist(self) -> None:
        policy = self._write_policy(semantic_enabled=True)
        settings = dl.resolve_legacy_settings(policy)
        (self.root / "legacy/roadmap-plan.md").write_text(
            "Roadmap phase milestone timeline plan\n",
            encoding="utf-8",
        )

        record = dl.classify_legacy_source(self.root, "legacy/roadmap-plan.md", settings)
        self.assertEqual(record.get("source_path"), "legacy/roadmap-plan.md")
        self.assertEqual(record.get("provider"), "deterministic_mock")
        self.assertEqual(record.get("decision"), "auto_migrate")
        self.assertGreaterEqual(float(record.get("confidence", 0.0)), 0.85)

        deny = dl.classify_legacy_source(self.root, "README.md", settings)
        self.assertEqual(deny.get("decision"), "skip")
        self.assertEqual(deny.get("category"), "not_migratable")

    def test_plan_adds_semantic_fields_and_writes_semantic_report(self) -> None:
        self._write_policy(semantic_enabled=True)
        self._write_manifest()
        (self.root / "legacy/progress.md").write_text(
            "progress status update done\n",
            encoding="utf-8",
        )

        plan = doc_plan.build_plan(
            root=self.root,
            mode="apply-with-archive",
            facts={"generated_at": utc_now()},
            policy_path=self.root / "docs/.doc-policy.json",
            manifest_path=self.root / "docs/.doc-manifest.json",
        )

        migrate = next(
            action for action in (plan.get("actions") or []) if action.get("type") == "migrate_legacy"
        )
        self.assertIn("semantic_category", migrate)
        self.assertIn("semantic_confidence", migrate)
        self.assertIn("semantic_decision", migrate)
        self.assertIn("semantic_model", migrate)
        self.assertIn("semantic:", "\n".join(migrate.get("evidence") or []))

        report_path = doc_plan.maybe_write_semantic_report(self.root, plan)
        self.assertIsNotNone(report_path)
        self.assertTrue(Path(report_path).exists())
        payload = json.loads(Path(report_path).read_text(encoding="utf-8"))
        self.assertEqual(payload.get("summary", {}).get("candidate_count"), 1)
        self.assertEqual(len(payload.get("entries") or []), 1)

    def test_plan_routes_manual_review_and_skip_for_semantic_decision(self) -> None:
        self._write_policy(semantic_enabled=True)
        self._write_manifest()
        (self.root / "legacy/high.md").write_text(
            "roadmap milestone timeline phase\n", encoding="utf-8"
        )
        (self.root / "legacy/mid.md").write_text("plan\n", encoding="utf-8")
        (self.root / "legacy/low.md").write_text("misc content without signals\n", encoding="utf-8")

        plan = doc_plan.build_plan(
            root=self.root,
            mode="apply-with-archive",
            facts={"generated_at": utc_now()},
            policy_path=self.root / "docs/.doc-policy.json",
            manifest_path=self.root / "docs/.doc-manifest.json",
        )
        actions = plan.get("actions") or []
        actions_by_source: dict[str, set[str]] = {}
        for action in actions:
            if not isinstance(action, dict):
                continue
            source = action.get("source_path") or action.get("path")
            if not isinstance(source, str):
                continue
            actions_by_source.setdefault(source, set()).add(str(action.get("type")))

        self.assertIn("migrate_legacy", actions_by_source.get("legacy/high.md", set()))
        self.assertIn("archive_legacy", actions_by_source.get("legacy/high.md", set()))
        self.assertEqual(actions_by_source.get("legacy/mid.md"), {"legacy_manual_review"})
        self.assertNotIn("legacy/low.md", actions_by_source)

    def test_plan_never_auto_migrates_denylist_sources(self) -> None:
        self._write_policy(
            semantic_enabled=True,
            include_globs=["legacy/**", "AGENTS.md"],
            exclude_globs=[],
        )
        self._write_manifest()
        (self.root / "legacy/high.md").write_text(
            "roadmap milestone timeline phase\n", encoding="utf-8"
        )
        (self.root / "AGENTS.md").write_text(
            "# AGENTS\n\nroadmap milestone timeline phase\n", encoding="utf-8"
        )

        plan = doc_plan.build_plan(
            root=self.root,
            mode="apply-with-archive",
            facts={"generated_at": utc_now()},
            policy_path=self.root / "docs/.doc-policy.json",
            manifest_path=self.root / "docs/.doc-manifest.json",
        )

        actions = plan.get("actions") or []
        migration_sources = {
            str(action.get("source_path"))
            for action in actions
            if action.get("type") in {"migrate_legacy", "archive_legacy"}
            and isinstance(action.get("source_path"), str)
        }
        self.assertIn("legacy/high.md", migration_sources)
        self.assertNotIn("AGENTS.md", migration_sources)

        semantic_entries = plan.get("legacy_semantic_report") or []
        agents_entry = next(
            (item for item in semantic_entries if item.get("source_path") == "AGENTS.md"),
            None,
        )
        self.assertIsNotNone(agents_entry)
        self.assertEqual((agents_entry or {}).get("decision"), "skip")
        self.assertEqual((agents_entry or {}).get("category"), "not_migratable")

    def test_legacy_semantic_agent_runtime_report_consumption(self) -> None:
        self._write_policy(
            semantic_enabled=True,
            semantic_provider="agent_runtime",
            semantic_model="runtime-model-v1",
        )
        self._write_manifest()
        (self.root / "legacy/high.md").write_text("# High\n", encoding="utf-8")
        (self.root / "legacy/mid.md").write_text("# Mid\n", encoding="utf-8")
        (self.root / "legacy/low.md").write_text("# Low\n", encoding="utf-8")
        (self.root / "docs/.legacy-semantic-report.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "entries": [
                        {
                            "source_path": "legacy/high.md",
                            "category": "plan",
                            "confidence": 0.92,
                            "decision": "auto_migrate",
                            "rationale": "runtime detected migration candidate",
                            "provider": "agent_runtime",
                            "model": "runtime-model-v1",
                        },
                        {
                            "source_path": "legacy/mid.md",
                            "category": "plan",
                            "confidence": 0.71,
                            "decision": "manual_review",
                            "provider": "agent_runtime",
                            "model": "runtime-model-v1",
                        },
                        {
                            "source_path": "legacy/low.md",
                            "category": "not_migratable",
                            "confidence": 0.12,
                            "decision": "skip",
                            "provider": "agent_runtime",
                            "model": "runtime-model-v1",
                        },
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        plan = doc_plan.build_plan(
            root=self.root,
            mode="apply-with-archive",
            facts={"generated_at": utc_now()},
            policy_path=self.root / "docs/.doc-policy.json",
            manifest_path=self.root / "docs/.doc-manifest.json",
        )

        actions = plan.get("actions") or []
        actions_by_source: dict[str, set[str]] = {}
        for action in actions:
            if not isinstance(action, dict):
                continue
            source = action.get("source_path") or action.get("path")
            if not isinstance(source, str):
                continue
            actions_by_source.setdefault(source, set()).add(str(action.get("type")))

        self.assertIn("migrate_legacy", actions_by_source.get("legacy/high.md", set()))
        self.assertIn("archive_legacy", actions_by_source.get("legacy/high.md", set()))
        self.assertEqual(actions_by_source.get("legacy/mid.md"), {"legacy_manual_review"})
        self.assertNotIn("legacy/low.md", actions_by_source)

        semantic_meta = (
            ((plan.get("meta") or {}).get("legacy_sources") or {}).get("semantic") or {}
        )
        self.assertEqual(semantic_meta.get("provider"), "agent_runtime")
        self.assertTrue(semantic_meta.get("report_available"))
        self.assertEqual(semantic_meta.get("report_entry_count"), 3)
        self.assertEqual(semantic_meta.get("fallback_auto_migrate_count"), 0)

        semantic_entries = plan.get("legacy_semantic_report") or []
        high = next(
            (
                item
                for item in semantic_entries
                if isinstance(item, dict) and item.get("source_path") == "legacy/high.md"
            ),
            None,
        )
        self.assertIsNotNone(high)
        self.assertEqual((high or {}).get("provider"), "agent_runtime")
        self.assertEqual((high or {}).get("decision_source"), "semantic")
        self.assertEqual((high or {}).get("model"), "runtime-model-v1")

    def test_legacy_semantic_fallback_no_auto_migrate(self) -> None:
        self._write_policy(
            semantic_enabled=True,
            semantic_provider="agent_runtime",
            allow_fallback_auto_migrate=False,
        )
        self._write_manifest()
        (self.root / "legacy/fallback.md").write_text("fallback scenario\n", encoding="utf-8")

        plan = doc_plan.build_plan(
            root=self.root,
            mode="apply-with-archive",
            facts={"generated_at": utc_now()},
            policy_path=self.root / "docs/.doc-policy.json",
            manifest_path=self.root / "docs/.doc-manifest.json",
        )

        actions = plan.get("actions") or []
        source_actions = [
            action
            for action in actions
            if isinstance(action, dict)
            and (
                action.get("source_path") == "legacy/fallback.md"
                or action.get("path") == "legacy/fallback.md"
            )
        ]
        self.assertEqual([action.get("type") for action in source_actions], ["legacy_manual_review"])

        semantic_entries = plan.get("legacy_semantic_report") or []
        fallback_entry = next(
            (
                item
                for item in semantic_entries
                if isinstance(item, dict) and item.get("source_path") == "legacy/fallback.md"
            ),
            None,
        )
        self.assertIsNotNone(fallback_entry)
        self.assertEqual((fallback_entry or {}).get("decision"), "manual_review")
        self.assertEqual((fallback_entry or {}).get("decision_source"), "fallback")
        self.assertFalse(bool((fallback_entry or {}).get("fallback_auto_migrate")))

        semantic_meta = (
            ((plan.get("meta") or {}).get("legacy_sources") or {}).get("semantic") or {}
        )
        self.assertFalse(semantic_meta.get("report_available"))
        self.assertEqual(semantic_meta.get("fallback_auto_migrate_count"), 0)

    def test_validate_blocks_denylist_migration(self) -> None:
        policy = self._write_policy(
            semantic_enabled=True,
            semantic_provider="agent_runtime",
            include_globs=["legacy/**", "AGENTS.md"],
            exclude_globs=[],
        )
        self._write_manifest()
        settings = dl.resolve_legacy_settings(policy)
        source_rel = "AGENTS.md"
        (self.root / source_rel).write_text("# AGENTS\n", encoding="utf-8")
        target_rel = dl.resolve_target_path(source_rel, settings)
        archive_rel = dl.resolve_archive_path(source_rel, settings)
        (self.root / Path(target_rel)).parent.mkdir(parents=True, exist_ok=True)
        (self.root / target_rel).write_text(
            dl.render_target_header("zh-CN")
            + "\n"
            + dl.render_migration_entry(source_rel, "# AGENTS\n", archive_rel, "zh-CN"),
            encoding="utf-8",
        )
        (self.root / Path(archive_rel)).parent.mkdir(parents=True, exist_ok=True)
        (self.root / archive_rel).write_text("# AGENTS\n", encoding="utf-8")

        registry = dl.load_registry(self.root / str(settings["registry_path"]))
        dl.upsert_registry_entry(
            registry,
            source_rel,
            {
                "status": "archived",
                "target_path": target_rel,
                "archive_path": archive_rel,
                "decision_source": "semantic",
                "category": "plan",
                "confidence": 0.99,
                "semantic_model": "runtime-model-v1",
            },
        )
        dl.save_registry(self.root / str(settings["registry_path"]), registry, dry_run=False)

        (self.root / "docs/.legacy-semantic-report.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "entries": [
                        {
                            "source_path": source_rel,
                            "decision": "auto_migrate",
                            "category": "plan",
                            "confidence": 0.99,
                            "provider": "agent_runtime",
                            "model": "runtime-model-v1",
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        errors, warnings, report = doc_validate.check_legacy_coverage(self.root, policy)
        self.assertEqual(warnings, [])
        self.assertTrue(
            any("denylist sources attempted migration" in message for message in errors)
        )
        self.assertEqual(report.get("metrics", {}).get("denylist_migration_count"), 1)

    def test_legacy_semantic_agent_runtime_missing_fields(self) -> None:
        self._write_policy(
            semantic_enabled=True,
            semantic_provider="agent_runtime",
        )
        self._write_manifest()
        (self.root / "legacy/missing-fields.md").write_text(
            "runtime missing fields\n", encoding="utf-8"
        )
        (self.root / "docs/.legacy-semantic-report.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "entries": [
                        {
                            "source_path": "legacy/missing-fields.md",
                            "category": "plan",
                            "confidence": 0.92,
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        plan = doc_plan.build_plan(
            root=self.root,
            mode="apply-with-archive",
            facts={"generated_at": utc_now()},
            policy_path=self.root / "docs/.doc-policy.json",
            manifest_path=self.root / "docs/.doc-manifest.json",
        )
        semantic_entries = plan.get("legacy_semantic_report") or []
        entry = next(
            (
                item
                for item in semantic_entries
                if isinstance(item, dict)
                and item.get("source_path") == "legacy/missing-fields.md"
            ),
            None,
        )
        self.assertIsNotNone(entry)
        self.assertEqual((entry or {}).get("decision"), "auto_migrate")
        self.assertEqual((entry or {}).get("provider"), "agent_runtime")
        self.assertEqual((entry or {}).get("decision_source"), "semantic")
        self.assertEqual((entry or {}).get("model"), "gpt-5-codex")

    def test_legacy_semantic_partial_runtime_report_uses_fallback_without_auto(self) -> None:
        self._write_policy(
            semantic_enabled=True,
            semantic_provider="agent_runtime",
            allow_fallback_auto_migrate=False,
        )
        self._write_manifest()
        (self.root / "legacy/has-entry.md").write_text("has entry\n", encoding="utf-8")
        (self.root / "legacy/missing-entry.md").write_text("missing entry\n", encoding="utf-8")
        (self.root / "docs/.legacy-semantic-report.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "entries": [
                        {
                            "source_path": "legacy/has-entry.md",
                            "category": "plan",
                            "confidence": 0.91,
                            "decision": "auto_migrate",
                            "provider": "agent_runtime",
                            "model": "runtime-model-v1",
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        plan = doc_plan.build_plan(
            root=self.root,
            mode="apply-with-archive",
            facts={"generated_at": utc_now()},
            policy_path=self.root / "docs/.doc-policy.json",
            manifest_path=self.root / "docs/.doc-manifest.json",
        )
        actions = plan.get("actions") or []
        has_entry_action_types = {
            str(action.get("type"))
            for action in actions
            if isinstance(action, dict)
            and str(action.get("source_path")) == "legacy/has-entry.md"
        }
        missing_entry_action_types = {
            str(action.get("type"))
            for action in actions
            if isinstance(action, dict)
            and (
                str(action.get("source_path")) == "legacy/missing-entry.md"
                or str(action.get("path")) == "legacy/missing-entry.md"
            )
        }
        self.assertIn("migrate_legacy", has_entry_action_types)
        self.assertEqual(missing_entry_action_types, {"legacy_manual_review"})

        semantic_entries = plan.get("legacy_semantic_report") or []
        missing_entry = next(
            (
                item
                for item in semantic_entries
                if isinstance(item, dict)
                and item.get("source_path") == "legacy/missing-entry.md"
            ),
            None,
        )
        self.assertIsNotNone(missing_entry)
        self.assertEqual((missing_entry or {}).get("decision"), "manual_review")
        self.assertEqual((missing_entry or {}).get("decision_source"), "fallback")
        self.assertFalse(bool((missing_entry or {}).get("fallback_auto_migrate")))

    def test_legacy_semantic_mapping_table_allows_controlled_fallback_auto(self) -> None:
        policy = self._write_policy(
            semantic_enabled=True,
            semantic_provider="agent_runtime",
            allow_fallback_auto_migrate=True,
        )
        policy["legacy_sources"]["mapping_table"] = {  # type: ignore[index]
            "legacy/controlled.md": "docs/history/legacy/custom-controlled.md"
        }
        policy["doc_quality_gates"] = {
            "enabled": True,
            "min_evidence_coverage": 0.0,
            "max_conflicts": 10,
            "max_unknown_claims": 10,
            "max_unresolved_todo": 10,
            "max_stale_metrics_days": 0,
            "max_semantic_conflicts": 10,
            "max_semantic_low_confidence_auto": 10,
            "max_fallback_auto_migrate": 1,
            "min_structured_section_completeness": 0.0,
            "fail_on_quality_gate": True,
            "fail_on_semantic_gate": True,
        }
        (self.root / "docs/.doc-policy.json").write_text(
            json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self._write_manifest()
        (self.root / "legacy/controlled.md").write_text("controlled fallback\n", encoding="utf-8")

        plan = doc_plan.build_plan(
            root=self.root,
            mode="apply-with-archive",
            facts={"generated_at": utc_now()},
            policy_path=self.root / "docs/.doc-policy.json",
            manifest_path=self.root / "docs/.doc-manifest.json",
        )

        actions = plan.get("actions") or []
        controlled_action_types = {
            str(action.get("type"))
            for action in actions
            if isinstance(action, dict)
            and str(action.get("source_path")) == "legacy/controlled.md"
        }
        self.assertEqual(controlled_action_types, {"migrate_legacy", "archive_legacy"})

        semantic_entries = plan.get("legacy_semantic_report") or []
        controlled_entry = next(
            (
                item
                for item in semantic_entries
                if isinstance(item, dict)
                and item.get("source_path") == "legacy/controlled.md"
            ),
            None,
        )
        self.assertIsNotNone(controlled_entry)
        self.assertEqual((controlled_entry or {}).get("decision"), "auto_migrate")
        self.assertEqual((controlled_entry or {}).get("decision_source"), "fallback")
        self.assertTrue(bool((controlled_entry or {}).get("fallback_auto_migrate")))

        report_path = doc_plan.maybe_write_semantic_report(self.root, plan)
        self.assertIsNotNone(report_path)
        quality_report = doc_quality.evaluate_semantic_migration_quality(
            root=self.root,
            policy=policy,
        )
        self.assertTrue(quality_report.get("enabled"))
        self.assertEqual(
            (quality_report.get("metrics") or {}).get("fallback_auto_migrate_count"),
            1,
        )

    def test_validate_blocks_fallback_auto_migrate_when_threshold_zero(self) -> None:
        policy = self._write_policy(
            semantic_enabled=True,
            semantic_provider="agent_runtime",
            allow_fallback_auto_migrate=True,
        )
        policy["legacy_sources"]["mapping_table"] = {  # type: ignore[index]
            "legacy/fallback-auto.md": "docs/history/legacy/fallback-auto.md"
        }
        policy["doc_quality_gates"] = {
            "enabled": True,
            "min_evidence_coverage": 0.0,
            "max_conflicts": 10,
            "max_unknown_claims": 10,
            "max_unresolved_todo": 10,
            "max_stale_metrics_days": 0,
            "max_semantic_conflicts": 10,
            "max_semantic_low_confidence_auto": 10,
            "max_fallback_auto_migrate": 0,
            "min_structured_section_completeness": 0.0,
            "fail_on_quality_gate": True,
            "fail_on_semantic_gate": True,
        }
        (self.root / "docs/.doc-policy.json").write_text(
            json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self._write_manifest()
        (self.root / "legacy/fallback-auto.md").write_text("fallback auto\n", encoding="utf-8")

        plan = doc_plan.build_plan(
            root=self.root,
            mode="audit",
            facts={"generated_at": utc_now()},
            policy_path=self.root / "docs/.doc-policy.json",
            manifest_path=self.root / "docs/.doc-manifest.json",
        )
        report_path = doc_plan.maybe_write_semantic_report(self.root, plan)
        self.assertIsNotNone(report_path)

        errors, warnings, report = doc_validate.check_legacy_coverage(self.root, policy)
        self.assertEqual(warnings, [])
        self.assertTrue(
            any(
                "fallback auto migration exceeds threshold" in message
                for message in errors
            )
        )
        self.assertEqual(report.get("metrics", {}).get("fallback_auto_migrate_count"), 1)

    def test_apply_structured_migration_and_registry_semantic_fields(self) -> None:
        policy = self._write_policy(semantic_enabled=True)
        settings = dl.resolve_legacy_settings(policy)
        source_rel = "legacy/structured.md"
        (self.root / source_rel).write_text(
            "# Sprint Plan\n"
            "2026-02-21 owner: docs-maintainer\n"
            "Decision: keep denylist hard boundary\n"
            "TODO: verify migration quality gate\n",
            encoding="utf-8",
        )
        target_rel = dl.resolve_target_path(source_rel, settings)
        archive_rel = dl.resolve_archive_path(source_rel, settings)
        language = {
            "primary": "zh-CN",
            "profile": "zh-CN",
            "locked": False,
            "source": "test",
        }
        metadata_policy = dm.resolve_metadata_policy(policy)

        migrate_result = doc_apply.apply_action(
            self.root,
            {
                "id": "A101",
                "type": "migrate_legacy",
                "kind": "file",
                "path": target_rel,
                "source_path": source_rel,
                "archive_path": archive_rel,
                "semantic_category": "plan",
                "semantic_confidence": 0.91,
                "semantic_model": "gpt-5-codex",
                "decision_source": "semantic",
                "evidence": ["legacy source matched include_globs: legacy/structured.md"],
            },
            dry_run=False,
            language_settings=language,
            template_profile="zh-CN",
            metadata_policy=metadata_policy,
            legacy_settings=settings,
        )
        self.assertEqual(migrate_result.get("status"), "applied")

        target_text = (self.root / target_rel).read_text(encoding="utf-8")
        self.assertIn("### 摘要", target_text)
        self.assertIn("### 关键事实", target_text)
        self.assertIn("### 决策与结论", target_text)
        self.assertIn("### 待办与风险", target_text)
        self.assertIn("### 来源追踪", target_text)
        self.assertIn(dl.source_marker(source_rel), target_text)
        self.assertIn("#### 原文短摘录", target_text)

        migrate_result_second = doc_apply.apply_action(
            self.root,
            {
                "id": "A101B",
                "type": "migrate_legacy",
                "kind": "file",
                "path": target_rel,
                "source_path": source_rel,
                "archive_path": archive_rel,
                "semantic_category": "plan",
                "semantic_confidence": 0.91,
                "semantic_model": "gpt-5-codex",
                "decision_source": "semantic",
            },
            dry_run=False,
            language_settings=language,
            template_profile="zh-CN",
            metadata_policy=metadata_policy,
            legacy_settings=settings,
        )
        self.assertEqual(migrate_result_second.get("status"), "skipped")
        target_text_second = (self.root / target_rel).read_text(encoding="utf-8")
        self.assertEqual(target_text.count("### 摘要"), target_text_second.count("### 摘要"))
        self.assertEqual(
            target_text.count(dl.source_marker(source_rel)),
            target_text_second.count(dl.source_marker(source_rel)),
        )

        archive_result = doc_apply.apply_action(
            self.root,
            {
                "id": "A102",
                "type": "archive_legacy",
                "kind": "file",
                "path": archive_rel,
                "source_path": source_rel,
                "target_path": target_rel,
                "semantic_category": "plan",
                "semantic_confidence": 0.91,
                "semantic_model": "gpt-5-codex",
                "decision_source": "semantic",
            },
            dry_run=False,
            language_settings=language,
            template_profile="zh-CN",
            metadata_policy=metadata_policy,
            legacy_settings=settings,
        )
        self.assertEqual(archive_result.get("status"), "applied")

        registry = dl.load_registry(self.root / settings["registry_path"])
        entry = (registry.get("entries") or {}).get(source_rel)
        self.assertIsInstance(entry, dict)
        self.assertEqual(entry.get("decision_source"), "semantic")
        self.assertEqual(entry.get("category"), "plan")
        self.assertAlmostEqual(float(entry.get("confidence")), 0.91, places=2)
        self.assertEqual(entry.get("semantic_model"), "gpt-5-codex")
        self.assertTrue(isinstance(entry.get("summary_hash"), str) and len(entry.get("summary_hash")) == 64)

    def test_validate_reports_semantic_gate_failures(self) -> None:
        policy = self._write_policy(semantic_enabled=True)
        policy["doc_quality_gates"] = {
            "enabled": True,
            "min_evidence_coverage": 0.0,
            "max_conflicts": 10,
            "max_unknown_claims": 10,
            "max_unresolved_todo": 10,
            "max_stale_metrics_days": 0,
            "max_semantic_conflicts": 0,
            "max_semantic_low_confidence_auto": 0,
            "min_structured_section_completeness": 0.95,
            "fail_on_quality_gate": True,
            "fail_on_semantic_gate": True,
        }
        (self.root / "docs/.doc-policy.json").write_text(
            json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        settings = dl.resolve_legacy_settings(policy)

        target_rel = "docs/history/legacy/legacy/problem.md"
        (self.root / "docs/history/legacy/legacy").mkdir(parents=True, exist_ok=True)
        (self.root / target_rel).write_text(
            "\n".join(
                [
                    "# Legacy 迁移记录",
                    "",
                    "## Legacy Source `legacy/problem.md`",
                    dl.source_marker("legacy/problem.md"),
                    "<!-- legacy-migrated-at: 2026-02-21T00:00:00+00:00 -->",
                    "",
                    "### 摘要",
                    "",
                    "- only summary",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        registry = dl.load_registry(self.root / settings["registry_path"])
        dl.upsert_registry_entry(
            registry,
            "legacy/problem.md",
            {
                "status": "archived",
                "target_path": target_rel,
                "archive_path": "docs/archive/legacy/legacy/problem.md",
                "decision_source": "semantic",
                "category": "plan",
                "confidence": 0.5,
                "semantic_model": "gpt-5-codex",
            },
        )
        dl.save_registry(self.root / settings["registry_path"], registry, dry_run=False)
        semantic_report = {
            "version": 1,
            "entries": [
                {
                    "source_path": "legacy/problem.md",
                    "decision": "auto_migrate",
                    "category": "plan",
                    "confidence": 0.5,
                }
            ],
        }
        (self.root / settings["semantic_report_path"]).write_text(
            json.dumps(semantic_report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        errors, warnings, report = doc_validate.check_legacy_coverage(self.root, policy)
        self.assertTrue(errors)
        self.assertEqual(warnings, [])
        self.assertGreater(
            report.get("metrics", {}).get("semantic_low_confidence_count", 0), 0
        )
        self.assertLess(
            float(
                report.get("metrics", {}).get(
                    "structured_section_completeness", 1.0
                )
            ),
            0.95,
        )

    def test_validate_reports_semantic_conflict_gate_failure(self) -> None:
        policy = self._write_policy(semantic_enabled=True)
        policy["doc_quality_gates"] = {
            "enabled": True,
            "min_evidence_coverage": 0.0,
            "max_conflicts": 10,
            "max_unknown_claims": 10,
            "max_unresolved_todo": 10,
            "max_stale_metrics_days": 0,
            "max_semantic_conflicts": 0,
            "max_semantic_low_confidence_auto": 10,
            "min_structured_section_completeness": 0.95,
            "fail_on_quality_gate": True,
            "fail_on_semantic_gate": True,
        }
        (self.root / "docs/.doc-policy.json").write_text(
            json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        settings = dl.resolve_legacy_settings(policy)
        source_rel = "legacy/conflict.md"
        archive_rel = dl.resolve_archive_path(source_rel, settings)
        target_rel = dl.resolve_target_path(source_rel, settings)
        source_content = (
            "# Conflict Sample\n"
            "phase timeline roadmap\n"
            "Decision: follow migration policy\n"
        )

        (self.root / source_rel).write_text(source_content, encoding="utf-8")
        (self.root / Path(target_rel)).parent.mkdir(parents=True, exist_ok=True)
        (self.root / target_rel).write_text(
            dl.render_target_header("zh-CN")
            + "\n"
            + dl.render_structured_migration_entry(
                source_rel=source_rel,
                source_content=source_content,
                archive_path=archive_rel,
                template_profile="zh-CN",
                semantic={"category": "requirement", "confidence": 0.95},
            ),
            encoding="utf-8",
        )
        (self.root / Path(archive_rel)).parent.mkdir(parents=True, exist_ok=True)
        (self.root / archive_rel).write_text(source_content, encoding="utf-8")

        registry_path = self.root / str(settings["registry_path"])
        registry = dl.load_registry(registry_path)
        dl.upsert_registry_entry(
            registry,
            source_rel,
            {
                "status": "archived",
                "target_path": target_rel,
                "archive_path": archive_rel,
                "decision_source": "semantic",
                "category": "requirement",
                "confidence": 0.95,
                "semantic_model": "gpt-5-codex",
            },
        )
        dl.save_registry(registry_path, registry, dry_run=False)

        semantic_report = {
            "version": 1,
            "entries": [
                {
                    "source_path": source_rel,
                    "decision": "auto_migrate",
                    "category": "plan",
                    "confidence": 0.95,
                }
            ],
        }
        (self.root / str(settings["semantic_report_path"])).write_text(
            json.dumps(semantic_report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        errors, warnings, report = doc_validate.check_legacy_coverage(self.root, policy)
        self.assertEqual(warnings, [])
        self.assertIn(
            "semantic gate failed: semantic conflicts exceed threshold",
            errors,
        )
        self.assertEqual(report.get("metrics", {}).get("semantic_conflict_count"), 1)

    def test_validate_treats_semantic_skip_sources_as_exempted(self) -> None:
        self._write_policy(semantic_enabled=True)
        self._write_manifest()
        source_rel = "legacy/low.md"
        (self.root / source_rel).write_text(
            "misc content without semantic hints\n", encoding="utf-8"
        )

        plan = doc_plan.build_plan(
            root=self.root,
            mode="audit",
            facts={"generated_at": utc_now()},
            policy_path=self.root / "docs/.doc-policy.json",
            manifest_path=self.root / "docs/.doc-manifest.json",
        )
        report_path = doc_plan.maybe_write_semantic_report(self.root, plan)
        self.assertIsNotNone(report_path)

        policy = json.loads((self.root / "docs/.doc-policy.json").read_text(encoding="utf-8"))
        errors, warnings, report = doc_validate.check_legacy_coverage(self.root, policy)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(report.get("metrics", {}).get("unresolved_sources"), 0)
        self.assertEqual(report.get("metrics", {}).get("exempted_sources"), 1)


if __name__ == "__main__":
    unittest.main()
