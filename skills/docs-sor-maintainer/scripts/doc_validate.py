#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import doc_metadata as dm  # noqa: E402
import doc_agents_validate  # noqa: E402
import doc_legacy as dl  # noqa: E402
import doc_plan  # noqa: E402
import doc_quality  # noqa: E402
import doc_spec  # noqa: E402

LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
EXEC_PLAN_STATUS_PATTERN = re.compile(
    r"<!--\s*exec-plan-status:\s*([a-zA-Z_-]+)\s*-->"
)
EXEC_PLAN_CLOSEOUT_PATTERN = re.compile(
    r"<!--\s*exec-plan-closeout:\s*([^\s][^>]*)\s*-->"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize(path_str: str) -> str:
    return str(Path(path_str)).replace("\\", "/")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return data


def get_required(manifest: dict[str, Any]) -> tuple[list[str], list[str]]:
    required = manifest.get("required", {}) or {}
    files = [normalize(p) for p in required.get("files", [])]
    dirs = [normalize(p) for p in required.get("dirs", [])]
    return files, dirs


def get_optional_files(manifest: dict[str, Any]) -> list[str]:
    optional = manifest.get("optional", {}) or {}
    return [normalize(p) for p in optional.get("files", [])]


def check_required(root: Path, manifest: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    req_files, req_dirs = get_required(manifest)

    for rel in req_files:
        if not (root / rel).exists():
            errors.append(f"missing required file: {rel}")

    for rel in req_dirs:
        if not (root / rel).exists():
            errors.append(f"missing required directory: {rel}")

    if not req_files and not req_dirs:
        warnings.append("manifest has no required files/dirs")

    return errors, warnings


def iter_docs_markdown(root: Path):
    docs = root / "docs"
    if not docs.exists():
        return []
    return [p for p in docs.rglob("*.md") if p.is_file()]


def check_internal_links(root: Path) -> tuple[list[str], list[str], int]:
    errors: list[str] = []
    warnings: list[str] = []
    checked = 0

    for file_path in iter_docs_markdown(root):
        content = file_path.read_text(encoding="utf-8")
        for match in LINK_PATTERN.finditer(content):
            link = match.group(1).strip()
            if not link or link.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = link.split("#", 1)[0]
            if not target:
                continue

            checked += 1
            resolved = (file_path.parent / target).resolve()
            if not resolved.exists():
                rel_file = normalize(file_path.relative_to(root).as_posix())
                errors.append(f"broken link in {rel_file}: {link}")

    if checked == 0:
        warnings.append("no internal markdown links found")

    return errors, warnings, checked


def check_index_coverage(
    root: Path, manifest: dict[str, Any]
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    index_path = root / "docs/index.md"
    if not index_path.exists():
        errors.append("docs/index.md not found for coverage check")
        return errors, warnings

    text = index_path.read_text(encoding="utf-8")
    req_files, _ = get_required(manifest)

    for rel in req_files:
        if rel == "docs/index.md":
            continue
        basename = Path(rel).name
        if basename not in text and rel not in text:
            warnings.append(f"index may not reference required file: {rel}")

    return errors, warnings


def check_doc_metadata(
    root: Path,
    manifest: dict[str, Any],
    metadata_policy: dict[str, Any],
) -> tuple[list[str], list[str], dict[str, int], list[dict[str, Any]]]:
    errors: list[str] = []
    warnings: list[str] = []
    findings: list[dict[str, Any]] = []

    required_files, _ = get_required(manifest)
    optional_files = get_optional_files(manifest)
    managed_files = sorted(set(required_files) | set(optional_files))

    checked_docs = 0
    missing_count = 0
    invalid_count = 0
    stale_count = 0

    for rel in managed_files:
        if not dm.should_enforce_for_path(rel, metadata_policy):
            continue
        abs_path = root / rel
        if not abs_path.exists():
            continue

        checked_docs += 1
        text = abs_path.read_text(encoding="utf-8")
        result = dm.evaluate_metadata(
            rel,
            text,
            metadata_policy,
            reference_date=date.today(),
        )
        findings.append(result)

        missing = result.get("missing") or []
        invalid = result.get("invalid") or []
        stale = bool(result.get("stale"))

        if missing:
            missing_count += len(missing)
            errors.append(f"missing doc metadata in {rel}: {', '.join(missing)}")
        if invalid:
            invalid_count += len(invalid)
            errors.append(f"invalid doc metadata in {rel}: {', '.join(invalid)}")
        if stale:
            stale_count += 1
            age_days = result.get("age_days")
            warnings.append(f"stale doc metadata in {rel}: age_days={age_days}")

    metrics = {
        "checked_docs": checked_docs,
        "missing_fields": missing_count,
        "invalid_fields": invalid_count,
        "stale_docs": stale_count,
    }
    return errors, warnings, metrics, findings


def load_facts(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"facts JSON must be an object: {path}")
    return data


def check_drift(
    root: Path,
    policy_path: Path,
    manifest_path: Path,
    facts: dict[str, Any] | None,
) -> tuple[bool, int, list[str]]:
    plan = doc_plan.build_plan(root, "audit", facts, policy_path, manifest_path)
    actions = plan.get("actions") or []
    actionable = [a for a in actions if a.get("type") in doc_plan.ACTIONABLE_TYPES]
    notes = [f"{a.get('id')} {a.get('type')} {a.get('path')}" for a in actionable]
    return len(actionable) > 0, len(actionable), notes


def check_exec_plan_closeout(
    root: Path,
) -> tuple[list[str], list[str], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    metrics = {
        "active_exec_plan_files": 0,
        "completed_declared_files": 0,
        "missing_closeout_link_files": 0,
        "missing_closeout_target_files": 0,
    }

    active_dir = root / "docs/exec-plans/active"
    if not active_dir.exists():
        return errors, warnings, metrics

    for file_path in sorted(active_dir.rglob("*.md")):
        if not file_path.is_file():
            continue
        rel = normalize(str(file_path.relative_to(root)))
        metrics["active_exec_plan_files"] += 1
        text = file_path.read_text(encoding="utf-8", errors="replace")

        status_match = EXEC_PLAN_STATUS_PATTERN.search(text)
        if status_match is None:
            continue

        status = status_match.group(1).strip().lower()
        if status != "completed":
            continue
        metrics["completed_declared_files"] += 1

        closeout_match = EXEC_PLAN_CLOSEOUT_PATTERN.search(text)
        if closeout_match is None:
            metrics["missing_closeout_link_files"] += 1
            errors.append(f"exec-plan closeout missing link marker: {rel}")
            continue

        closeout_rel = normalize(closeout_match.group(1).strip())
        closeout_abs = root / closeout_rel
        if not closeout_abs.exists():
            metrics["missing_closeout_target_files"] += 1
            errors.append(
                f"exec-plan closeout target missing for {rel}: {closeout_rel}"
            )

    return errors, warnings, metrics


def check_legacy_coverage(
    root: Path,
    policy: dict[str, Any],
) -> tuple[list[str], list[str], dict[str, Any]]:
    settings = dl.resolve_legacy_settings(policy)
    report: dict[str, Any] = {
        "enabled": settings.get("enabled", False),
        "settings": settings,
        "registry_path": settings.get("registry_path"),
        "metrics": {
            "discovered_sources": 0,
            "registry_entries": 0,
            "completed_sources": 0,
            "exempted_sources": 0,
            "unresolved_sources": 0,
            "missing_archive_files": 0,
            "missing_target_docs": 0,
            "missing_source_markers": 0,
            "semantic_auto_migrate_count": 0,
            "semantic_manual_review_count": 0,
            "semantic_skip_count": 0,
            "fallback_auto_migrate_count": 0,
            "semantic_low_confidence_count": 0,
            "semantic_conflict_count": 0,
            "structured_section_completeness": 1.0,
            "semantic_missing_source_marker_auto_count": 0,
            "denylist_migration_count": 0,
        },
        "unresolved_sources": [],
        "semantic": {
            "enabled": False,
            "thresholds": {},
            "metrics": {},
            "backlog": [],
            "conflicts": [],
            "low_confidence_auto_sources": [],
            "incomplete_sources": [],
            "missing_source_marker_auto_sources": [],
            "denylist_migration_sources": [],
        },
        "errors": [],
        "warnings": [],
    }

    if not settings.get("enabled", False):
        return [], [], report

    candidates = dl.discover_legacy_sources(root, settings)
    report["metrics"]["discovered_sources"] = len(candidates)
    exempt_sources = set(settings.get("exempt_sources") or [])

    registry_path = root / str(settings.get("registry_path"))
    registry = dl.load_registry(registry_path)
    entries = (
        registry.get("entries") if isinstance(registry.get("entries"), dict) else {}
    )
    report["metrics"]["registry_entries"] = len(entries)

    semantic_settings = (
        settings.get("semantic")
        if isinstance(settings.get("semantic"), dict)
        else {}
    )
    denylist = {normalize(str(value)) for value in (semantic_settings.get("denylist_files") or [])}
    denylist_names = {Path(item).name for item in denylist}

    semantic_skip_sources: set[str] = set()
    denylist_semantic_migration_sources: set[str] = set()
    semantic_entries: list[dict[str, Any]] = []
    semantic_report_rel = normalize(str(settings.get("semantic_report_path", "")))
    semantic_report_path = root / semantic_report_rel if semantic_report_rel else None
    if semantic_report_path and semantic_report_path.exists():
        try:
            semantic_payload = load_json(semantic_report_path)
        except Exception:  # noqa: BLE001
            semantic_payload = {}
        semantic_entries = (
            semantic_payload.get("entries")
            if isinstance(semantic_payload.get("entries"), list)
            else []
        )
        for item in semantic_entries:
            if not isinstance(item, dict):
                continue
            source_path = item.get("source_path")
            decision = item.get("decision")
            normalized_source = (
                normalize(source_path)
                if isinstance(source_path, str) and source_path.strip()
                else None
            )
            if (
                isinstance(normalized_source, str)
                and isinstance(decision, str)
                and decision.strip() == "skip"
            ):
                semantic_skip_sources.add(normalized_source)
            if (
                isinstance(normalized_source, str)
                and isinstance(decision, str)
                and decision.strip() == "auto_migrate"
                and (
                    normalized_source in denylist
                    or Path(normalized_source).name in denylist_names
                )
            ):
                denylist_semantic_migration_sources.add(normalized_source)

    completed_sources = [rel for rel in candidates if dl.has_completed_entry(registry, rel)]
    unresolved_sources = [
        rel
        for rel in candidates
        if rel not in exempt_sources
        and rel not in semantic_skip_sources
        and not dl.has_completed_entry(registry, rel)
    ]
    report["metrics"]["completed_sources"] = len(completed_sources)
    report["metrics"]["exempted_sources"] = len(
        [rel for rel in candidates if rel in exempt_sources or rel in semantic_skip_sources]
    )
    report["metrics"]["unresolved_sources"] = len(unresolved_sources)
    report["unresolved_sources"] = unresolved_sources

    errors: list[str] = []
    warnings: list[str] = []
    if unresolved_sources:
        message = (
            "legacy unresolved sources: " + ", ".join(unresolved_sources[:20])
        )
        if settings.get("fail_on_legacy_drift", True):
            errors.append(message)
        else:
            warnings.append(message)

    for source_rel, entry in entries.items():
        if not isinstance(source_rel, str) or not isinstance(entry, dict):
            continue
        normalized_source = normalize(source_rel)
        status = entry.get("status")
        target_rel = normalize(entry.get("target_path", ""))
        archive_rel = normalize(entry.get("archive_path", ""))

        if status == "archived":
            if not archive_rel or not (root / archive_rel).exists():
                report["metrics"]["missing_archive_files"] += 1
                errors.append(
                    f"legacy archive missing for {normalized_source}: {archive_rel or 'UNKNOWN'}"
                )

        if status in {"migrated", "archived"}:
            if normalized_source in denylist or Path(normalized_source).name in denylist_names:
                denylist_semantic_migration_sources.add(normalized_source)
            if not target_rel or not (root / target_rel).exists():
                report["metrics"]["missing_target_docs"] += 1
                errors.append(
                    f"legacy target missing for {normalized_source}: {target_rel or 'UNKNOWN'}"
                )
                continue

            target_text = (root / target_rel).read_text(encoding="utf-8", errors="replace")
            if dl.source_marker(normalized_source) not in target_text:
                report["metrics"]["missing_source_markers"] += 1
                warnings.append(
                    f"legacy source marker missing in {target_rel}: {normalized_source}"
                )

    semantic_quality = doc_quality.evaluate_semantic_migration_quality(root, policy)
    report["semantic"] = semantic_quality
    semantic_metrics = semantic_quality.get("metrics") or {}
    report["metrics"]["semantic_auto_migrate_count"] = int(
        semantic_metrics.get("semantic_auto_migrate_count", 0)
    )
    report["metrics"]["semantic_manual_review_count"] = int(
        semantic_metrics.get("semantic_manual_review_count", 0)
    )
    report["metrics"]["semantic_skip_count"] = int(
        semantic_metrics.get("semantic_skip_count", 0)
    )
    report["metrics"]["fallback_auto_migrate_count"] = int(
        semantic_metrics.get("fallback_auto_migrate_count", 0)
    )
    report["metrics"]["semantic_low_confidence_count"] = int(
        semantic_metrics.get("semantic_low_confidence_count", 0)
    )
    report["metrics"]["semantic_conflict_count"] = int(
        semantic_metrics.get("semantic_conflict_count", 0)
    )
    report["metrics"]["structured_section_completeness"] = float(
        semantic_metrics.get("structured_section_completeness", 1.0)
    )
    report["metrics"]["semantic_missing_source_marker_auto_count"] = int(
        semantic_metrics.get("missing_source_marker_auto_count", 0)
    )
    denylist_migration_sources = sorted(denylist_semantic_migration_sources)
    report["metrics"]["denylist_migration_count"] = len(denylist_migration_sources)
    report["semantic"]["denylist_migration_sources"] = denylist_migration_sources
    if denylist_migration_sources:
        errors.append(
            "semantic gate failed: denylist sources attempted migration: "
            + ", ".join(denylist_migration_sources[:20])
        )

    if semantic_quality.get("enabled", False):
        thresholds = semantic_quality.get("thresholds") or {}
        fail_on_semantic_gate = bool(thresholds.get("fail_on_semantic_gate", True))
        semantic_gate_failures: list[str] = []
        if report["metrics"]["semantic_missing_source_marker_auto_count"] > 0:
            semantic_gate_failures.append(
                "semantic gate failed: auto migrated entries contain missing source markers"
            )
        if (
            report["metrics"]["semantic_low_confidence_count"]
            > int(thresholds.get("max_semantic_low_confidence_auto", 0))
        ):
            semantic_gate_failures.append(
                "semantic gate failed: low confidence auto migration exceeds threshold"
            )
        if (
            report["metrics"]["semantic_conflict_count"]
            > int(thresholds.get("max_semantic_conflicts", 0))
        ):
            semantic_gate_failures.append(
                "semantic gate failed: semantic conflicts exceed threshold"
            )
        if (
            report["metrics"]["fallback_auto_migrate_count"]
            > int(thresholds.get("max_fallback_auto_migrate", 0))
        ):
            semantic_gate_failures.append(
                "semantic gate failed: fallback auto migration exceeds threshold"
            )
        if report["metrics"]["structured_section_completeness"] < float(
            thresholds.get("min_structured_section_completeness", 0.95)
        ):
            semantic_gate_failures.append(
                "semantic gate failed: structured section completeness below threshold"
            )
        if fail_on_semantic_gate:
            errors.extend(semantic_gate_failures)
        else:
            warnings.extend(semantic_gate_failures)

    report["errors"] = errors
    report["warnings"] = warnings
    return errors, warnings, report


def resolve_quality_gate_settings(policy: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(policy, dict):
        return {"enabled": False, "fail_on_quality_gate": False}
    raw = policy.get("doc_quality_gates")
    if not isinstance(raw, dict):
        return {"enabled": False, "fail_on_quality_gate": False}
    return {
        "enabled": bool(raw.get("enabled", False)),
        "fail_on_quality_gate": bool(raw.get("fail_on_quality_gate", True)),
    }


def resolve_agents_gate_settings(policy: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(policy, dict):
        return {
            "enabled": False,
            "fail_on_agents_drift": False,
        }
    raw = policy.get("agents_generation")
    if not isinstance(raw, dict):
        return {
            "enabled": False,
            "fail_on_agents_drift": False,
        }
    return {
        "enabled": bool(raw.get("enabled", False)),
        "fail_on_agents_drift": bool(raw.get("fail_on_agents_drift", True)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate repository docs consistency and drift."
    )
    parser.add_argument("--root", required=True, help="Repository root")
    parser.add_argument(
        "--manifest", default="docs/.doc-manifest.json", help="Manifest path"
    )
    parser.add_argument("--policy", default="docs/.doc-policy.json", help="Policy path")
    parser.add_argument("--spec", default="docs/.doc-spec.json", help="Doc spec path")
    parser.add_argument(
        "--facts", default="docs/.repo-facts.json", help="Facts JSON path"
    )
    parser.add_argument(
        "--output",
        default="docs/.doc-validate-report.json",
        help="Output JSON report path",
    )
    parser.add_argument(
        "--fail-on-drift", action="store_true", help="Exit non-zero when drift exists"
    )
    parser.add_argument(
        "--fail-on-freshness",
        action="store_true",
        help="Exit non-zero when stale doc metadata exists",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()

    if not root.exists() or not root.is_dir():
        raise SystemExit(f"[ERROR] Invalid root path: {root}")

    manifest_path = (
        (root / args.manifest).resolve()
        if not Path(args.manifest).is_absolute()
        else Path(args.manifest)
    )
    policy_path = (
        (root / args.policy).resolve()
        if not Path(args.policy).is_absolute()
        else Path(args.policy)
    )
    spec_path = (
        (root / args.spec).resolve()
        if not Path(args.spec).is_absolute()
        else Path(args.spec)
    )
    facts_path = (
        (root / args.facts).resolve()
        if not Path(args.facts).is_absolute()
        else Path(args.facts)
    )
    output_path = (
        (root / args.output).resolve()
        if not Path(args.output).is_absolute()
        else Path(args.output)
    )

    manifest = load_json(manifest_path)
    policy = load_json(policy_path)
    metadata_policy = dm.resolve_metadata_policy(policy)
    facts = load_facts(facts_path)

    errors: list[str] = []
    warnings: list[str] = []

    req_errors, req_warnings = check_required(root, manifest)
    errors.extend(req_errors)
    warnings.extend(req_warnings)

    link_errors, link_warnings, link_count = check_internal_links(root)
    errors.extend(link_errors)
    warnings.extend(link_warnings)

    idx_errors, idx_warnings = check_index_coverage(root, manifest)
    errors.extend(idx_errors)
    warnings.extend(idx_warnings)

    metadata_errors, metadata_warnings, metadata_metrics, metadata_findings = (
        check_doc_metadata(root, manifest, metadata_policy)
    )
    errors.extend(metadata_errors)
    warnings.extend(metadata_warnings)

    spec_data, spec_errors, spec_warnings = doc_spec.load_spec(spec_path)
    errors.extend([f"doc-spec: {message}" for message in spec_errors])
    warnings.extend([f"doc-spec: {message}" for message in spec_warnings])

    quality_settings = resolve_quality_gate_settings(policy)
    quality_report = None
    quality_failed = False
    if quality_settings["enabled"]:
        try:
            quality_report = doc_quality.evaluate_quality(
                root,
                policy,
                facts,
                spec_path,
                evidence_map_path=root / "docs/.doc-evidence-map.json",
            )
            quality_failed = quality_report.get("gate", {}).get("status") != "passed"
            if quality_failed and quality_settings["fail_on_quality_gate"]:
                errors.append("doc-quality: quality gate failed")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"doc-quality: {exc}")
            quality_failed = True

    agents_settings = resolve_agents_gate_settings(policy)
    agents_report = None
    agents_failed = False
    if agents_settings["enabled"]:
        try:
            agents_report = doc_agents_validate.evaluate_agents(
                root=root,
                policy=policy,
                agents_path=root / "AGENTS.md",
                index_path=root / "docs/index.md",
            )
            agents_failed = agents_report.get("gate", {}).get("status") != "passed"
            if agents_failed and agents_settings["fail_on_agents_drift"]:
                errors.append("agents-quality: agents gate failed")
            warnings.extend([f"agents-quality: {w}" for w in agents_report.get("warnings", [])])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"agents-quality: {exc}")
            agents_failed = True

    legacy_errors, legacy_warnings, legacy_report = check_legacy_coverage(root, policy)
    errors.extend(legacy_errors)
    warnings.extend(legacy_warnings)

    has_drift, drift_count, drift_notes = check_drift(
        root, policy_path, manifest_path, facts
    )
    exec_plan_errors, exec_plan_warnings, exec_plan_metrics = check_exec_plan_closeout(
        root
    )
    errors.extend(exec_plan_errors)
    warnings.extend(exec_plan_warnings)

    has_stale_metadata = metadata_metrics.get("stale_docs", 0) > 0
    passed = (
        len(errors) == 0
        and (not args.fail_on_drift or not has_drift)
        and (not args.fail_on_freshness or not has_stale_metadata)
        and (not quality_settings["fail_on_quality_gate"] or not quality_failed)
        and (not agents_settings["fail_on_agents_drift"] or not agents_failed)
    )

    report = {
        "generated_at": utc_now(),
        "root": str(root),
        "passed": passed,
        "fail_on_drift": args.fail_on_drift,
        "fail_on_freshness": args.fail_on_freshness,
        "metrics": {
            "errors": len(errors),
            "warnings": len(warnings),
            "checked_links": link_count,
            "drift_action_count": drift_count,
            "facts_loaded": facts is not None,
            "metadata_checked_docs": metadata_metrics.get("checked_docs", 0),
            "metadata_missing_fields": metadata_metrics.get("missing_fields", 0),
            "metadata_invalid_fields": metadata_metrics.get("invalid_fields", 0),
            "metadata_stale_docs": metadata_metrics.get("stale_docs", 0),
            "doc_spec_exists": spec_data is not None,
            "doc_spec_errors": len(spec_errors),
            "doc_spec_warnings": len(spec_warnings),
            "doc_quality_enabled": quality_settings["enabled"],
            "doc_quality_failed": quality_failed,
            "agents_validate_enabled": agents_settings["enabled"],
            "agents_validate_failed": agents_failed,
            "legacy_enabled": legacy_report.get("enabled", False),
            "legacy_unresolved_sources": legacy_report.get("metrics", {}).get(
                "unresolved_sources", 0
            ),
            "semantic_auto_migrate_count": legacy_report.get("metrics", {}).get(
                "semantic_auto_migrate_count", 0
            ),
            "semantic_manual_review_count": legacy_report.get("metrics", {}).get(
                "semantic_manual_review_count", 0
            ),
            "semantic_skip_count": legacy_report.get("metrics", {}).get(
                "semantic_skip_count", 0
            ),
            "fallback_auto_migrate_count": legacy_report.get("metrics", {}).get(
                "fallback_auto_migrate_count", 0
            ),
            "semantic_low_confidence_count": legacy_report.get("metrics", {}).get(
                "semantic_low_confidence_count", 0
            ),
            "semantic_conflict_count": legacy_report.get("metrics", {}).get(
                "semantic_conflict_count", 0
            ),
            "denylist_migration_count": legacy_report.get("metrics", {}).get(
                "denylist_migration_count", 0
            ),
            "structured_section_completeness": legacy_report.get("metrics", {}).get(
                "structured_section_completeness", 1.0
            ),
            "active_exec_plan_files": exec_plan_metrics.get(
                "active_exec_plan_files", 0
            ),
            "completed_declared_exec_plans": exec_plan_metrics.get(
                "completed_declared_files", 0
            ),
            "missing_exec_plan_closeout_links": exec_plan_metrics.get(
                "missing_closeout_link_files", 0
            ),
            "missing_exec_plan_closeout_targets": exec_plan_metrics.get(
                "missing_closeout_target_files", 0
            ),
        },
        "errors": errors,
        "warnings": warnings,
        "drift": {
            "has_drift": has_drift,
            "actions": drift_notes,
        },
        "doc_spec": {
            "path": normalize(spec_path.relative_to(root)),
            "exists": spec_data is not None,
            "errors": spec_errors,
            "warnings": spec_warnings,
        },
        "doc_quality": quality_report
        or {
            "enabled": quality_settings["enabled"],
            "gate": {
                "status": "skipped" if not quality_settings["enabled"] else "failed",
                "failed_checks": [],
            },
        },
        "doc_metadata": {
            "policy": metadata_policy,
            "findings": metadata_findings,
        },
        "agents": agents_report
        or {
            "enabled": agents_settings["enabled"],
            "gate": {
                "status": "skipped" if not agents_settings["enabled"] else "failed",
                "failed_checks": [],
            },
            "errors": [],
            "warnings": [],
            "metrics": {},
        },
        "legacy": legacy_report,
        "exec_plan_closeout": {
            "errors": exec_plan_errors,
            "warnings": exec_plan_warnings,
            "metrics": exec_plan_metrics,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[OK] Wrote validate report to {output_path}")
    print(f"[INFO] errors={len(errors)} warnings={len(warnings)} drift={drift_count}")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
