#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import json
import re
from collections import Counter
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import doc_capabilities as dc
import doc_legacy as dl
import doc_metadata as dm
import doc_quality
import doc_spec
import language_profiles as lp

DEFAULT_POLICY = lp.build_default_policy()
ACTIONABLE_TYPES = {
    "add",
    "update",
    "archive",
    "manual_review",
    "sync_manifest",
    "update_section",
    "fill_claim",
    "refresh_evidence",
    "semantic_rewrite",
    "quality_repair",
    "migrate_legacy",
    "archive_legacy",
    "legacy_manual_review",
}
REPAIRABLE_ACTION_TYPES = {
    "update_section",
    "fill_claim",
    "refresh_evidence",
    "semantic_rewrite",
    "quality_repair",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_posix(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def normalize_rel(path_str: str) -> str:
    return dc.normalize_rel(path_str)


def summarize_semantic_decisions(
    records: list[dict[str, Any]],
) -> dict[str, int]:
    decisions = [
        str(record.get("decision"))
        for record in records
        if isinstance(record.get("decision"), str)
    ]
    return dict(Counter(decisions))


def summarize_fallback_auto_migrate(records: list[dict[str, Any]]) -> int:
    return sum(
        1
        for record in records
        if isinstance(record, dict)
        and bool(record.get("fallback_auto_migrate", False))
        and str(record.get("decision")) == "auto_migrate"
    )


def build_semantic_action_fields(record: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    decision_source = record.get("decision_source")
    normalized_source = (
        str(decision_source).strip()
        if isinstance(decision_source, str) and str(decision_source).strip()
        else "semantic"
    )
    return {
        "semantic_category": record.get("category"),
        "semantic_confidence": record.get("confidence"),
        "semantic_decision": record.get("decision"),
        "semantic_rationale": record.get("rationale"),
        "semantic_signals": record.get("signals") or [],
        "semantic_engine": record.get("engine"),
        "semantic_provider": record.get("provider"),
        "semantic_model": record.get("model"),
        "decision_source": normalized_source,
    }


def maybe_write_semantic_report(root: Path, plan: dict[str, Any]) -> Path | None:
    meta = plan.get("meta") if isinstance(plan, dict) else {}
    legacy_meta = meta.get("legacy_sources") if isinstance(meta, dict) else {}
    semantic_meta = (
        legacy_meta.get("semantic") if isinstance(legacy_meta, dict) else {}
    )
    if not isinstance(semantic_meta, dict) or not semantic_meta.get("enabled", False):
        return None

    report_rel = str(semantic_meta.get("report_path") or "").strip()
    if not report_rel:
        return None

    entries = plan.get("legacy_semantic_report")
    if not isinstance(entries, list):
        entries = []

    report_path = (root / report_rel).resolve()
    payload = {
        "version": 1,
        "generated_at": meta.get("generated_at"),
        "root": str(root),
        "mode": meta.get("mode"),
        "engine": semantic_meta.get("engine"),
        "provider": semantic_meta.get("provider"),
        "model": semantic_meta.get("model"),
        "auto_migrate_threshold": semantic_meta.get("auto_migrate_threshold"),
        "review_threshold": semantic_meta.get("review_threshold"),
        "entries": entries,
        "summary": {
            "candidate_count": len(entries),
            "decision_counts": summarize_semantic_decisions(entries),
            "fallback_auto_migrate_count": summarize_fallback_auto_migrate(entries),
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return report_path


def infer_primary_language_from_docs(root: Path) -> str | None:
    zh_hits = 0
    en_hits = 0

    for rel_path in (
        "docs/index.md",
        "docs/architecture.md",
        "docs/runbook.md",
        "docs/glossary.md",
    ):
        abs_path = root / rel_path
        if not abs_path.exists():
            continue
        text = abs_path.read_text(encoding="utf-8")

        for section_id in lp.get_required_sections(rel_path):
            if lp.get_section_heading(rel_path, section_id, "zh-CN") in text:
                zh_hits += 1
            if lp.get_section_heading(rel_path, section_id, "en-US") in text:
                en_hits += 1

    if zh_hits == 0 and en_hits == 0:
        return None
    return "zh-CN" if zh_hits >= en_hits else "en-US"


def load_json_or_default(
    path: Path, default: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    if not path.exists():
        return deepcopy(default), False
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return data, True


def load_facts(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("facts JSON must be an object")
    return data


def load_json(path: Path) -> tuple[dict[str, Any], bool]:
    if not path.exists():
        return {}, False
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return data, True


def new_action_id(index: int) -> str:
    return f"A{index:03d}"


def missing_required_sections(path: Path, rel_path: str) -> list[str]:
    section_ids = lp.get_required_sections(rel_path)
    if not section_ids:
        return []
    if not path.exists():
        return section_ids

    text = path.read_text(encoding="utf-8")
    missing: list[str] = []
    for section_id in section_ids:
        markers = lp.get_section_markers(rel_path, section_id)
        if not any(marker in text for marker in markers):
            missing.append(section_id)
    return missing


def extract_runbook_section_commands(root: Path, section_id: str) -> list[str]:
    runbook_path = root / "docs/runbook.md"
    if not runbook_path.exists():
        return []

    markers = {
        marker.strip()
        for marker in lp.get_section_markers("docs/runbook.md", section_id)
        if isinstance(marker, str) and marker.strip()
    }
    if not markers:
        return []

    lines = runbook_path.read_text(encoding="utf-8").splitlines()
    section_start = None
    section_end = len(lines)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if section_start is None and stripped in markers:
            section_start = index + 1
            continue
        if section_start is not None and re.match(r"^##\s+", stripped):
            section_end = index
            break

    if section_start is None:
        return []

    commands: list[str] = []
    in_command_block = False
    for line in lines[section_start:section_end]:
        stripped = line.strip()
        if stripped.startswith("```"):
            language = stripped[3:].strip().lower()
            if in_command_block:
                in_command_block = False
            else:
                in_command_block = language in {"", "bash", "sh", "zsh"}
            continue
        if not in_command_block:
            continue
        if not stripped or stripped.startswith("#"):
            continue
        commands.append(stripped)

    deduped: list[str] = []
    seen: set[str] = set()
    for command in commands:
        if command in seen:
            continue
        seen.add(command)
        deduped.append(command)
    return deduped


def resolve_evidence_value(
    facts: dict[str, Any] | None,
    evidence_type: str,
    root: Path,
    runbook_cache: dict[str, list[str]],
) -> Any | None:
    if not isinstance(evidence_type, str):
        return None

    if evidence_type.startswith("repo_scan."):
        if not facts:
            return None
        cursor: Any = facts
        for key in evidence_type.split(".")[1:]:
            if isinstance(cursor, dict) and key in cursor:
                cursor = cursor[key]
            else:
                return None
        return cursor

    if evidence_type.startswith("runbook."):
        section_key = evidence_type.split(".", 1)[1]
        if section_key not in {"dev_commands", "validation_commands"}:
            return None
        if section_key not in runbook_cache:
            runbook_cache[section_key] = extract_runbook_section_commands(
                root, section_key
            )
        return runbook_cache.get(section_key)

    return None

def evidence_is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict, str)):
        return len(value) == 0
    return False

def get_facts_age_days(facts: dict[str, Any] | None) -> int | None:
    if not facts:
        return None
    generated_at = facts.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at:
        return None
    try:
        generated_time = datetime.fromisoformat(generated_at)
    except ValueError:
        return None
    if generated_time.tzinfo is None:
        generated_time = generated_time.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return (now - generated_time).days

def resolve_section_markers(rel_path: str, section_id: str) -> list[str]:
    markers = lp.get_section_markers(rel_path, section_id)
    return markers or []


def stale_docs_candidates(
    root: Path,
    managed_files: set[str],
    archive_dir: str,
    protected_patterns: list[str],
) -> list[str]:
    docs_root = root / "docs"
    if not docs_root.exists():
        return []

    archive_prefix = normalize_rel(archive_dir).rstrip("/") + "/"
    stale: list[str] = []
    for p in docs_root.rglob("*.md"):
        rel = to_posix(p, root)
        if rel.startswith(archive_prefix):
            continue
        if rel in managed_files:
            continue
        if any(fnmatch.fnmatch(rel, pattern) for pattern in protected_patterns):
            continue
        if p.name.startswith("."):
            continue
        stale.append(rel)
    return sorted(stale)


def resolve_effective_manifest(
    policy: dict[str, Any],
    has_manifest: bool,
    current_manifest: dict[str, Any],
    facts: dict[str, Any] | None,
) -> tuple[dict[str, Any], str, str, list[dict[str, Any]], list[str], bool]:
    capability_decisions: list[dict[str, Any]] = []
    manifest_notes: list[str] = []

    if has_manifest:
        evolution = dc.get_manifest_evolution_settings(policy)
        manifest_profile = dc.infer_manifest_profile(dc.collect_repo_metrics(facts))
        if not evolution["allow_additive"]:
            snapshot = dc.normalize_manifest_snapshot(current_manifest)
            return (
                snapshot,
                "existing",
                manifest_profile,
                capability_decisions,
                manifest_notes,
                False,
            )

        desired_manifest, capability_decisions, _, override_notes = (
            dc.derive_adaptive_manifest(
                facts,
                policy,
                archive_dir=current_manifest.get("archive_dir", dc.DEFAULT_ARCHIVE_DIR),
            )
        )
        merged_manifest, merge_notes = dc.merge_manifest_additive(
            current_manifest, desired_manifest
        )
        manifest_notes.extend(override_notes)
        manifest_notes.extend(merge_notes)
        changed = not dc.manifests_equal(current_manifest, merged_manifest)
        source = "existing_additive" if changed else "existing"
        return (
            merged_manifest,
            source,
            manifest_profile,
            capability_decisions,
            manifest_notes,
            changed,
        )

    strategy = dc.get_bootstrap_manifest_strategy(policy)
    if strategy == "fixed" or facts is None:
        profile = dc.infer_manifest_profile(dc.collect_repo_metrics(facts))
        notes = (
            ["bootstrap_manifest_strategy=fixed"]
            if strategy == "fixed"
            else ["facts missing, fallback to fixed"]
        )
        return dc.clone_default_manifest(), "fixed_fallback", profile, [], notes, True

    derived_manifest, capability_decisions, metrics, override_notes = (
        dc.derive_adaptive_manifest(facts, policy)
    )
    profile = dc.infer_manifest_profile(metrics)
    notes = ["bootstrap_manifest_strategy=adaptive"] + override_notes
    return derived_manifest, "adaptive", profile, capability_decisions, notes, True


def build_plan(
    root: Path,
    mode: str,
    facts: dict[str, Any] | None,
    policy_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    policy, has_policy = load_json_or_default(policy_path, DEFAULT_POLICY)
    current_manifest, has_manifest = load_json(manifest_path)

    inferred_language = None
    policy_for_language = policy if has_policy else {}
    if not isinstance(policy_for_language.get("language"), dict):
        inferred_language = infer_primary_language_from_docs(root)

    language_settings = lp.resolve_language_settings(
        policy_for_language, inferred_language
    )
    template_profile = language_settings["profile"]

    (
        effective_manifest,
        manifest_source,
        manifest_profile,
        capability_decisions,
        manifest_notes,
        manifest_changed,
    ) = resolve_effective_manifest(policy, has_manifest, current_manifest, facts)

    legacy_settings = dl.resolve_legacy_settings(policy)
    legacy_candidates = dl.discover_legacy_sources(root, legacy_settings)
    legacy_semantic_records: list[dict[str, Any]] = []
    legacy_semantic_index: dict[str, dict[str, Any]] = {}
    runtime_semantic_index: dict[str, dict[str, Any]] = {}
    runtime_semantic_state: dict[str, Any] = {
        "available": False,
        "entry_count": 0,
        "error": None,
    }
    semantic_settings = (
        legacy_settings.get("semantic")
        if isinstance(legacy_settings.get("semantic"), dict)
        else {}
    )
    semantic_provider = str(semantic_settings.get("provider") or "").strip()
    if semantic_settings.get("enabled", False) and semantic_provider == "agent_runtime":
        runtime_semantic_index, runtime_semantic_state = dl.load_semantic_report_index(
            root, legacy_settings
        )
    if semantic_settings.get("enabled", False):
        for source_rel in legacy_candidates:
            semantic_record = dl.classify_legacy_source(
                root,
                source_rel,
                legacy_settings,
                runtime_semantic_index=runtime_semantic_index,
                runtime_semantic_state=runtime_semantic_state,
            )
            legacy_semantic_records.append(semantic_record)
            legacy_semantic_index[source_rel] = semantic_record
    legacy_target_files = sorted(
        {
            dl.resolve_target_path(source_rel, legacy_settings)
            for source_rel in legacy_candidates
        }
    )
    if legacy_settings.get("enabled", False) and legacy_target_files:
        manifest_with_legacy = dc.normalize_manifest_snapshot(effective_manifest)
        _, _, optional_files_existing = dc.get_manifest_lists(manifest_with_legacy)
        merged_optional = sorted(set(optional_files_existing) | set(legacy_target_files))
        manifest_with_legacy.setdefault("optional", {})["files"] = merged_optional
        if not dc.manifests_equal(effective_manifest, manifest_with_legacy):
            effective_manifest = manifest_with_legacy
            manifest_notes.append(
                "legacy_sources enabled: append legacy migration targets to optional files"
            )
            if has_manifest:
                manifest_changed = not dc.manifests_equal(
                    current_manifest, effective_manifest
                )
                if manifest_changed and manifest_source == "existing":
                    manifest_source = "existing_additive"
            else:
                manifest_changed = True

    required_files, required_dirs, optional_files = dc.get_manifest_lists(
        effective_manifest
    )
    archive_dir = normalize_rel(
        effective_manifest.get("archive_dir", dc.DEFAULT_ARCHIVE_DIR)
    )
    metadata_policy = dm.resolve_metadata_policy(policy)
    spec_path = root / "docs/.doc-spec.json"
    spec_data, spec_errors, spec_warnings = doc_spec.load_spec(spec_path)
    allow_auto_update = set(
        normalize_rel(p) for p in policy.get("allow_auto_update", [])
    )
    protected_patterns = [
        normalize_rel(p) for p in policy.get("protect_from_auto_overwrite", [])
    ]

    spec_documents: dict[str, dict[str, Any]] = {}
    if isinstance(spec_data, dict):
        for doc in spec_data.get("documents", []) or []:
            if not isinstance(doc, dict):
                continue
            path_value = doc.get("path")
            if not isinstance(path_value, str) or not path_value.strip():
                continue
            spec_documents[normalize_rel(path_value)] = doc

    actions: list[dict[str, Any]] = []

    def add_action(
        action_type: str,
        kind: str,
        path: str,
        reason: str,
        evidence: list[str],
        **extra,
    ):
        action = {
            "id": new_action_id(len(actions) + 1),
            "type": action_type,
            "kind": kind,
            "path": normalize_rel(path),
            "risk": "low"
            if action_type in {"add", "archive", "archive_legacy", "sync_manifest"}
            else "medium",
            "reason": reason,
            "evidence": evidence,
        }
        action.update(extra)
        actions.append(action)

    docs_root = root / "docs"

    if mode == "bootstrap" and not docs_root.exists():
        add_action(
            "add",
            "dir",
            "docs",
            "docs directory is missing",
            ["repository has no docs/ root"],
        )

    if not has_policy:
        add_action(
            "add",
            "file",
            normalize_rel(policy_path.relative_to(root)),
            "policy file is missing",
            ["docs automation requires policy boundaries"],
            template="policy",
        )

    if not has_manifest:
        add_action(
            "add",
            "file",
            normalize_rel(manifest_path.relative_to(root)),
            "manifest file is missing",
            ["docs structure requires manifest contract"],
            template="manifest",
            manifest_snapshot=dc.normalize_manifest_snapshot(effective_manifest),
        )
    elif manifest_changed:
        add_action(
            "sync_manifest",
            "file",
            normalize_rel(manifest_path.relative_to(root)),
            "manifest requires additive evolution based on repository signals",
            manifest_notes or ["adaptive capabilities produced new required docs"],
            manifest_snapshot=dc.normalize_manifest_snapshot(effective_manifest),
        )

    for rel_dir in required_dirs:
        if not (root / rel_dir).exists():
            add_action(
                "add",
                "dir",
                rel_dir,
                "required directory is missing",
                [f"manifest.required.dirs includes {rel_dir}"],
            )

    for rel_file in required_files:
        abs_file = root / rel_file
        if not abs_file.exists():
            add_action(
                "add",
                "file",
                rel_file,
                "required file is missing",
                [f"manifest.required.files includes {rel_file}"],
                template="managed",
            )

    for rel_file in optional_files:
        abs_file = root / rel_file
        if not abs_file.exists() and mode == "bootstrap":
            add_action(
                "add",
                "file",
                rel_file,
                "optional managed file missing during bootstrap",
                [f"manifest.optional.files includes {rel_file}"],
                template="managed",
            )

    managed_files = set(required_files) | set(optional_files)

    for rel_file in sorted(managed_files):
        abs_file = root / rel_file
        if not abs_file.exists():
            continue

        missing_sections = missing_required_sections(abs_file, rel_file)
        metadata_missing: list[str] = []
        metadata_invalid: list[str] = []
        if dm.should_enforce_for_path(rel_file, metadata_policy):
            metadata_eval = dm.evaluate_metadata(
                rel_file,
                abs_file.read_text(encoding="utf-8"),
                metadata_policy,
                reference_date=date.today(),
            )
            metadata_missing = list(metadata_eval.get("missing") or [])
            metadata_invalid = list(metadata_eval.get("invalid") or [])

        if not (missing_sections or metadata_missing or metadata_invalid):
            continue

        evidence: list[str] = []
        missing_headings: list[str] = []
        if missing_sections:
            missing_headings = [
                lp.get_section_heading(rel_file, section_id, template_profile)
                for section_id in missing_sections
            ]
            evidence.append(f"missing sections: {', '.join(missing_headings)}")
        if metadata_missing:
            evidence.append(f"missing doc metadata: {', '.join(metadata_missing)}")
        if metadata_invalid:
            evidence.append(f"invalid doc metadata: {', '.join(metadata_invalid)}")

        if rel_file in allow_auto_update:
            reason = "managed file misses required sections"
            if not missing_sections:
                reason = "managed file misses required doc metadata"
            add_action(
                "update",
                "file",
                rel_file,
                reason,
                evidence,
                missing_sections=missing_sections,
                missing_markers=missing_headings,
                missing_doc_metadata=metadata_missing,
                invalid_doc_metadata=metadata_invalid,
                template="managed",
            )
        else:
            add_action(
                "manual_review",
                "file",
                rel_file,
                "managed file requires manual metadata/section fix",
                evidence,
            )

    facts_age_days = get_facts_age_days(facts)
    runbook_cache: dict[str, list[str]] = {}
    quality_gates = policy.get("doc_quality_gates")
    max_stale_days = None
    if isinstance(quality_gates, dict):
        max_stale_days = quality_gates.get("max_stale_metrics_days")
    if not isinstance(max_stale_days, int) or max_stale_days <= 0:
        max_stale_days = None

    for rel_path, spec_doc in spec_documents.items():
        abs_path = root / rel_path
        if not abs_path.exists():
            continue

        sections = spec_doc.get("sections")
        if not isinstance(sections, list) or not sections:
            continue

        content = abs_path.read_text(encoding="utf-8")
        for section in sections:
            if not isinstance(section, dict):
                continue
            section_id = section.get("section_id")
            if not isinstance(section_id, str) or not section_id.strip():
                continue
            section_id = section_id.strip()
            markers = resolve_section_markers(rel_path, section_id)
            if markers and not any(marker in content for marker in markers):
                heading = lp.get_section_heading(
                    rel_path, section_id, template_profile
                )
                add_action(
                    "update_section",
                    "section",
                    rel_path,
                    "doc-spec section missing",
                    [f"missing section marker: {heading}"],
                    section_id=section_id,
                    section_heading=heading,
                )

            claims = section.get("claims")
            if not isinstance(claims, list) or not claims:
                continue

            for claim in claims:
                if not isinstance(claim, dict):
                    continue
                claim_id = claim.get("claim_id")
                if not isinstance(claim_id, str) or not claim_id.strip():
                    continue
                claim_id = claim_id.strip()
                required_types = claim.get("required_evidence_types") or []
                if not isinstance(required_types, list) or not required_types:
                    continue

                missing_types: list[str] = []
                stale_types: list[str] = []
                for evidence_type in required_types:
                    if not isinstance(evidence_type, str):
                        continue
                    value = resolve_evidence_value(
                        facts,
                        evidence_type,
                        root=root,
                        runbook_cache=runbook_cache,
                    )
                    if evidence_is_empty(value):
                        missing_types.append(evidence_type)
                    elif (
                        max_stale_days is not None
                        and facts_age_days is not None
                        and evidence_type.startswith("repo_scan.")
                        and facts_age_days > max_stale_days
                    ):
                        stale_types.append(evidence_type)

                if stale_types:
                    add_action(
                        "refresh_evidence",
                        "claim",
                        rel_path,
                        "repo-scan evidence is stale",
                        [
                            f"facts age {facts_age_days}d exceeds {max_stale_days}d",
                            f"evidence types: {', '.join(stale_types)}",
                        ],
                        section_id=section_id,
                        claim_id=claim_id,
                        evidence_types=stale_types,
                    )

                if missing_types:
                    allow_unknown = bool(claim.get("allow_unknown", False))
                    if allow_unknown:
                        continue
                    statement_template = claim.get("statement_template", "")
                    add_action(
                        "fill_claim",
                        "claim",
                        rel_path,
                        "doc-spec claim missing evidence",
                        [f"missing evidence: {', '.join(missing_types)}"],
                        section_id=section_id,
                        claim_id=claim_id,
                        statement_template=statement_template,
                        required_evidence_types=required_types,
                        allow_unknown=allow_unknown,
                        missing_evidence_types=missing_types,
                    )

    if isinstance(quality_gates, dict) and bool(quality_gates.get("enabled", False)):
        try:
            quality_report = doc_quality.evaluate_quality(
                root=root,
                policy=policy,
                facts=facts,
                spec_path=spec_path,
                evidence_map_path=None,
            )
        except Exception as exc:  # noqa: BLE001
            add_action(
                "quality_repair",
                "quality",
                "docs/.doc-quality-report.json",
                "doc-quality evaluation failed during planning",
                [str(exc)],
            )
        else:
            gate = quality_report.get("gate") or {}
            failed_checks = gate.get("failed_checks") or []
            semantic = (
                quality_report.get("semantic")
                if isinstance(quality_report.get("semantic"), dict)
                else {}
            )
            semantic_backlog = (
                semantic.get("backlog")
                if isinstance(semantic.get("backlog"), list)
                else []
            )
            emitted_semantic_rewrite: set[tuple[str, str, str]] = set()
            for item in semantic_backlog:
                if not isinstance(item, dict):
                    continue
                backlog_reason = (
                    str(item.get("reason")).strip()
                    if isinstance(item.get("reason"), str)
                    else "semantic_backlog"
                )
                source_path = (
                    normalize_rel(str(item.get("source_path")).strip())
                    if isinstance(item.get("source_path"), str)
                    and str(item.get("source_path")).strip()
                    else ""
                )
                target_path = (
                    normalize_rel(str(item.get("target_path")).strip())
                    if isinstance(item.get("target_path"), str)
                    and str(item.get("target_path")).strip()
                    else ""
                )
                action_path = target_path or source_path or "docs/.legacy-semantic-report.json"
                dedupe_key = (action_path, source_path, backlog_reason)
                if dedupe_key in emitted_semantic_rewrite:
                    continue
                emitted_semantic_rewrite.add(dedupe_key)
                evidence = [f"semantic backlog reason: {backlog_reason}"]
                if source_path:
                    evidence.append(f"source_path={source_path}")
                if target_path:
                    evidence.append(f"target_path={target_path}")
                add_action(
                    "semantic_rewrite",
                    "semantic",
                    action_path,
                    "semantic backlog requires rewrite",
                    evidence,
                    source_path=source_path,
                    target_path=target_path,
                    backlog_reason=backlog_reason,
                )
            if gate.get("status") != "passed":
                metrics = quality_report.get("metrics") or {}
                add_action(
                    "quality_repair",
                    "quality",
                    "docs/.doc-quality-report.json",
                    "doc-quality gate failed",
                    [
                        "failed checks: "
                        + ", ".join(str(v) for v in failed_checks)
                        if failed_checks
                        else "failed checks: unknown",
                        "metrics: "
                        f"coverage={metrics.get('evidence_coverage')} "
                        f"unknown={metrics.get('unknown_claims')} "
                        f"todo={metrics.get('unresolved_todo')} "
                        f"conflicts={metrics.get('conflicts')} "
                        f"citation_issues={metrics.get('citation_issues')}",
                    ],
                    failed_checks=failed_checks,
                    quality_metrics=metrics,
                )

    if mode in {"apply-with-archive", "audit", "apply-safe"}:
        stale = stale_docs_candidates(
            root, managed_files, archive_dir, protected_patterns
        )
        for stale_path in stale:
            if mode == "apply-with-archive":
                rel_from_docs = Path(stale_path).relative_to("docs")
                target = normalize_rel(Path(archive_dir) / rel_from_docs)
                add_action(
                    "archive",
                    "file",
                    target,
                    "stale docs candidate archived in migration mode",
                    [f"not declared in manifest: {stale_path}"],
                    source_path=stale_path,
                )
            else:
                add_action(
                    "manual_review",
                    "file",
                    stale_path,
                    "stale docs candidate requires review",
                    [f"not declared in manifest: {stale_path}"],
                )

    if legacy_settings.get("enabled", False) and mode in {
        "apply-with-archive",
        "audit",
        "apply-safe",
    }:
        exempt_sources = set(legacy_settings.get("exempt_sources") or [])
        for source_rel in legacy_candidates:
            if source_rel in exempt_sources:
                continue
            target_rel = dl.resolve_target_path(source_rel, legacy_settings)
            archive_target = dl.resolve_archive_path(source_rel, legacy_settings)
            semantic_record = legacy_semantic_index.get(source_rel)
            semantic_fields = build_semantic_action_fields(semantic_record)
            route_fields: dict[str, Any] = (
                dict(semantic_fields) if semantic_fields else {"decision_source": "rule"}
            )
            semantic_decision = (
                str(semantic_record.get("decision"))
                if isinstance(semantic_record, dict)
                and isinstance(semantic_record.get("decision"), str)
                else None
            )
            evidence = [
                f"legacy source matched include_globs: {source_rel}",
                f"mapping_strategy={legacy_settings.get('mapping_strategy')}",
            ]
            if semantic_record:
                evidence.append(
                    "semantic: "
                    f"category={semantic_record.get('category')} "
                    f"confidence={semantic_record.get('confidence')} "
                    f"decision={semantic_record.get('decision')}"
                )

            if semantic_record and semantic_decision == "skip":
                continue

            if semantic_record and semantic_decision == "manual_review":
                add_action(
                    "legacy_manual_review",
                    "file",
                    source_rel,
                    "legacy source routed to manual review by semantic decision",
                    evidence,
                    target_path=target_rel,
                    archive_path=archive_target,
                    **route_fields,
                )
                continue

            if mode == "apply-with-archive":
                add_action(
                    "migrate_legacy",
                    "file",
                    target_rel,
                    "legacy source requires SoR migration",
                    evidence,
                    source_path=source_rel,
                    archive_path=archive_target,
                    **route_fields,
                )
                add_action(
                    "archive_legacy",
                    "file",
                    archive_target,
                    "legacy source archived after successful migration",
                    [f"migration target: {target_rel}"],
                    source_path=source_rel,
                    target_path=target_rel,
                    **route_fields,
                )
            else:
                add_action(
                    "legacy_manual_review",
                    "file",
                    source_rel,
                    "legacy source requires mapping review before migration",
                    evidence,
                    target_path=target_rel,
                    archive_path=archive_target,
                    **route_fields,
                )

    has_agents_md = (root / "AGENTS.md").exists()
    if (
        mode == "bootstrap"
        and not has_agents_md
        and bool(policy.get("bootstrap_agents_md", True))
    ):
        add_action(
            "add",
            "file",
            "AGENTS.md",
            "AGENTS navigation file is missing during bootstrap",
            ["policy.bootstrap_agents_md=true"],
            template="agents",
        )

    if facts:
        modules = facts.get("modules") or []
        if (
            isinstance(modules, list)
            and modules
            and (root / "docs/architecture.md").exists()
        ):
            content = (root / "docs/architecture.md").read_text(encoding="utf-8")
            missing_modules = [m for m in modules if m not in content]
            if missing_modules and "docs/architecture.md" in allow_auto_update:
                add_action(
                    "update",
                    "file",
                    "docs/architecture.md",
                    "architecture file does not list discovered modules",
                    [f"missing modules: {', '.join(missing_modules)}"],
                    missing_modules=missing_modules,
                    template="managed",
                )

    if mode == "repair":
        actions = [
            action
            for action in actions
            if str(action.get("type")) in REPAIRABLE_ACTION_TYPES
        ]

    counts: dict[str, int] = {}
    section_action_counts: dict[str, int] = {}
    claim_action_counts: dict[str, int] = {}
    for action in actions:
        counts[action["type"]] = counts.get(action["type"], 0) + 1
        section_id = action.get("section_id")
        if isinstance(section_id, str) and section_id.strip():
            key = section_id.strip()
            section_action_counts[key] = section_action_counts.get(key, 0) + 1
        claim_id = action.get("claim_id")
        if isinstance(claim_id, str) and claim_id.strip():
            key = claim_id.strip()
            claim_action_counts[key] = claim_action_counts.get(key, 0) + 1

    return {
        "meta": {
            "generated_at": utc_now(),
            "root": str(root),
            "mode": mode,
            "policy_path": normalize_rel(policy_path.relative_to(root)),
            "manifest_path": normalize_rel(manifest_path.relative_to(root)),
            "manifest_source": manifest_source,
            "manifest_profile": manifest_profile,
            "manifest_changed": manifest_changed,
            "manifest_effective": dc.normalize_manifest_snapshot(effective_manifest),
            "manifest_reasoning": manifest_notes,
            "capability_decisions": capability_decisions,
            "doc_metadata": {
                "enabled": metadata_policy.get("enabled", True),
                "require_owner": metadata_policy.get("require_owner", True),
                "require_last_reviewed": metadata_policy.get(
                    "require_last_reviewed", True
                ),
                "require_review_cycle_days": metadata_policy.get(
                    "require_review_cycle_days", True
                ),
            },
            "legacy_sources": {
                "enabled": legacy_settings.get("enabled", False),
                "mapping_strategy": legacy_settings.get("mapping_strategy"),
                "candidate_count": len(legacy_candidates),
                "target_doc_count": len(legacy_target_files),
                "semantic": {
                    "enabled": semantic_settings.get("enabled", False),
                    "engine": semantic_settings.get("engine"),
                    "provider": semantic_settings.get("provider"),
                    "model": semantic_settings.get("model"),
                    "auto_migrate_threshold": semantic_settings.get(
                        "auto_migrate_threshold"
                    ),
                    "review_threshold": semantic_settings.get("review_threshold"),
                    "allow_fallback_auto_migrate": semantic_settings.get(
                        "allow_fallback_auto_migrate", False
                    ),
                    "report_path": legacy_settings.get("semantic_report_path"),
                    "report_available": runtime_semantic_state.get("available", False)
                    if semantic_provider == "agent_runtime"
                    else True,
                    "report_entry_count": runtime_semantic_state.get("entry_count", 0)
                    if semantic_provider == "agent_runtime"
                    else len(legacy_semantic_records),
                    "report_error": runtime_semantic_state.get("error")
                    if semantic_provider == "agent_runtime"
                    else None,
                    "decision_counts": summarize_semantic_decisions(
                        legacy_semantic_records
                    ),
                    "fallback_auto_migrate_count": summarize_fallback_auto_migrate(
                        legacy_semantic_records
                    ),
                },
            },
            "language": {
                "primary": language_settings["primary"],
                "profile": language_settings["profile"],
                "source": language_settings["source"],
            },
        },
        "inputs": {
            "policy_exists": has_policy,
            "manifest_exists": has_manifest,
            "facts_loaded": facts is not None,
            "doc_spec": {
                "path": normalize_rel(spec_path.relative_to(root)),
                "exists": spec_data is not None,
                "error_count": len(spec_errors),
                "warning_count": len(spec_warnings),
                "errors": spec_errors,
                "warnings": spec_warnings,
            },
        },
        "summary": {
            "action_count": len(actions),
            "action_counts": counts,
            "section_action_counts": section_action_counts,
            "claim_action_counts": claim_action_counts,
            "has_actionable_drift": any(a["type"] in ACTIONABLE_TYPES for a in actions),
        },
        "legacy_semantic_report": legacy_semantic_records,
        "actions": actions,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate documentation maintenance plans."
    )
    parser.add_argument("--root", required=True, help="Repository root")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["bootstrap", "audit", "apply-safe", "apply-with-archive", "repair"],
        help="Planning mode",
    )
    parser.add_argument("--facts", help="Path to repo facts JSON from repo_scan.py")
    parser.add_argument(
        "--policy", default="docs/.doc-policy.json", help="Policy file path"
    )
    parser.add_argument(
        "--manifest", default="docs/.doc-manifest.json", help="Manifest file path"
    )
    parser.add_argument("--output", required=True, help="Output plan JSON path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output).resolve()
    policy_path = (
        (root / args.policy).resolve()
        if not Path(args.policy).is_absolute()
        else Path(args.policy)
    )
    manifest_path = (
        (root / args.manifest).resolve()
        if not Path(args.manifest).is_absolute()
        else Path(args.manifest)
    )
    facts_path = Path(args.facts).resolve() if args.facts else None

    if not root.exists() or not root.is_dir():
        raise SystemExit(f"[ERROR] Invalid root path: {root}")

    facts = load_facts(facts_path) if facts_path else None
    plan = build_plan(root, args.mode, facts, policy_path, manifest_path)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
        f.write("\n")

    semantic_report_path = maybe_write_semantic_report(root, plan)

    print(f"[OK] Wrote plan to {output}")
    print(f"[INFO] Action count: {plan['summary']['action_count']}")
    if semantic_report_path is not None:
        print(f"[INFO] Semantic report: {semantic_report_path}")
    language = (plan.get("meta") or {}).get("language") or {}
    print(
        "[INFO] Language primary="
        f"{language.get('primary', 'N/A')} profile={language.get('profile', 'N/A')} source={language.get('source', 'N/A')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
