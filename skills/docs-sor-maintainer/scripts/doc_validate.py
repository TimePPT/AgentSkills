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
import doc_semantic_runtime as dsr  # noqa: E402
import doc_spec  # noqa: E402
import doc_topology as dt  # noqa: E402

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


def get_managed_markdown_files(manifest: dict[str, Any]) -> list[str]:
    required_files, _ = get_required(manifest)
    optional_files = get_optional_files(manifest)
    return sorted(
        {
            normalize(path)
            for path in (required_files + optional_files)
            if isinstance(path, str) and normalize(path).endswith(".md")
        }
    )


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


def check_topology_contract(
    root: Path,
    policy: dict[str, Any],
    manifest: dict[str, Any] | None = None,
) -> tuple[list[str], list[str], dict[str, Any]]:
    settings = dt.resolve_topology_settings(policy)
    contract, topology_report = dt.load_topology_contract(root, settings)

    errors: list[str] = []
    warnings: list[str] = []
    topology_raw_warnings = [
        str(message).strip()
        for message in (topology_report.get("warnings") or [])
        if str(message).strip()
    ]

    if topology_report.get("enabled", False):
        if not topology_report.get("exists", False):
            errors.append(
                f"doc-topology: missing topology contract: {topology_report.get('path')}"
            )
        errors.extend(
            [f"doc-topology: {message}" for message in topology_report.get("errors", [])]
        )

    topology_analysis: dict[str, Any] = {}
    if (
        topology_report.get("enabled", False)
        and topology_report.get("loaded", False)
        and isinstance(contract, dict)
    ):
        managed_markdown = get_managed_markdown_files(manifest or {})
        topology_analysis = dt.evaluate_topology(
            root,
            contract,
            settings,
            managed_docs=managed_markdown,
        )

        topology_raw_warnings.extend(
            [
                str(message).strip()
                for message in (topology_analysis.get("warnings") or [])
                if str(message).strip()
            ]
        )
        metrics = dict(topology_report.get("metrics") or {})
        metrics.update(topology_analysis.get("metrics") or {})
        topology_report["metrics"] = metrics

        orphan_count = int(metrics.get("topology_orphan_count", 0))
        unreachable_count = int(metrics.get("topology_unreachable_count", 0))
        max_depth = int(metrics.get("topology_max_depth", 0))
        depth_limit = int(metrics.get("topology_depth_limit", settings.get("max_depth", 3)))

        if settings.get("fail_on_orphan", True) and orphan_count > 0:
            errors.append(f"doc-topology: orphan docs detected: {orphan_count}")
        if settings.get("fail_on_unreachable", True) and unreachable_count > 0:
            errors.append(f"doc-topology: unreachable docs detected: {unreachable_count}")
        if settings.get("enforce_max_depth", True) and max_depth > depth_limit:
            errors.append(
                "doc-topology: depth limit exceeded: "
                f"max_depth={max_depth} limit={depth_limit}"
            )

    topology_report["warnings"] = sorted(set(topology_raw_warnings))
    if topology_report.get("enabled", False):
        warnings.extend(
            [
                f"doc-topology: {message}"
                for message in (topology_report.get("warnings") or [])
            ]
        )

    report = {
        "enabled": topology_report.get("enabled", False),
        "settings": settings,
        "path": topology_report.get("path"),
        "exists": topology_report.get("exists", False),
        "loaded": topology_report.get("loaded", False),
        "errors": topology_report.get("errors") or [],
        "warnings": topology_report.get("warnings") or [],
        "metrics": topology_report.get("metrics") or {},
        "contract": contract,
        "analysis": {
            "scope_docs": topology_analysis.get("scope_docs") or [],
            "orphan_docs": topology_analysis.get("orphan_docs") or [],
            "unreachable_docs": topology_analysis.get("unreachable_docs") or [],
            "over_depth_docs": topology_analysis.get("over_depth_docs") or [],
            "navigation_missing_by_parent": topology_analysis.get(
                "navigation_missing_by_parent"
            )
            or [],
        },
    }
    return errors, warnings, report


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


SEMANTIC_OBSERVABILITY_EXEMPT_STATUSES = {
    "deterministic_mode",
    "semantic_disabled",
    "action_disabled",
    "semantic_not_enabled",
}
DEFAULT_SEMANTIC_OBSERVABILITY_SETTINGS = {
    "enabled": True,
    "large_unattempted_ratio": 0.5,
    "large_unattempted_count": 3,
    "fail_on_large_unattempted": True,
}


def _safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def resolve_semantic_observability_settings(policy: dict[str, Any]) -> dict[str, Any]:
    settings = dict(DEFAULT_SEMANTIC_OBSERVABILITY_SETTINGS)
    if not isinstance(policy, dict):
        return settings
    semantic_raw = policy.get("semantic_generation")
    if not isinstance(semantic_raw, dict):
        return settings
    observability_raw = semantic_raw.get("observability")
    if not isinstance(observability_raw, dict):
        return settings

    settings["enabled"] = bool(observability_raw.get("enabled", settings["enabled"]))
    ratio = _safe_float(
        observability_raw.get(
            "large_unattempted_ratio",
            settings["large_unattempted_ratio"],
        ),
        settings["large_unattempted_ratio"],
    )
    settings["large_unattempted_ratio"] = min(max(ratio, 0.0), 1.0)
    count = _safe_int(
        observability_raw.get(
            "large_unattempted_count",
            settings["large_unattempted_count"],
        ),
        settings["large_unattempted_count"],
    )
    settings["large_unattempted_count"] = max(count, 0)
    settings["fail_on_large_unattempted"] = bool(
        observability_raw.get(
            "fail_on_large_unattempted",
            settings["fail_on_large_unattempted"],
        )
    )
    return settings


def _normalize_reason_breakdown(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, int] = {}
    for key, raw_value in value.items():
        reason = str(key).strip()
        if not reason:
            continue
        normalized[reason] = max(_safe_int(raw_value, 0), 0)
    return dict(sorted(normalized.items()))


def _derive_semantic_observability_from_results(
    apply_report: dict[str, Any],
    semantic_settings: dict[str, Any],
) -> dict[str, Any]:
    actions = semantic_settings.get("actions")
    enabled_actions = (
        {
            str(action_type).strip()
            for action_type, enabled in actions.items()
            if isinstance(action_type, str) and bool(enabled)
        }
        if isinstance(actions, dict)
        else set()
    )
    metrics = {
        "semantic_action_count": 0,
        "semantic_attempt_count": 0,
        "semantic_success_count": 0,
        "fallback_count": 0,
        "fallback_reason_breakdown": {},
        "semantic_exempt_count": 0,
        "semantic_unattempted_count": 0,
        "semantic_unattempted_without_exemption": 0,
        "semantic_hit_rate": 0.0,
        "semantic_unattempted_samples": [],
    }
    if not enabled_actions:
        return metrics

    fallback_reason_breakdown: dict[str, int] = {}
    results = apply_report.get("results")
    if not isinstance(results, list):
        return metrics
    for item in results:
        if not isinstance(item, dict):
            continue
        action_type = str(item.get("type", "")).strip()
        if action_type not in enabled_actions:
            continue
        metrics["semantic_action_count"] += 1
        semantic_runtime = item.get("semantic_runtime")
        if not isinstance(semantic_runtime, dict):
            metrics["semantic_unattempted_without_exemption"] += 1
            if len(metrics["semantic_unattempted_samples"]) < 20:
                metrics["semantic_unattempted_samples"].append(
                    {
                        "id": item.get("id"),
                        "type": action_type,
                        "path": normalize(str(item.get("path", ""))),
                        "reason": "missing_semantic_runtime_trace",
                    }
                )
            continue

        attempted = bool(semantic_runtime.get("attempted"))
        if attempted:
            metrics["semantic_attempt_count"] += 1
        if bool(semantic_runtime.get("consumed")):
            metrics["semantic_success_count"] += 1
        if bool(semantic_runtime.get("fallback_used")):
            metrics["fallback_count"] += 1
            fallback_reason = (
                str(semantic_runtime.get("fallback_reason", "")).strip() or "unknown"
            )
            fallback_reason_breakdown[fallback_reason] = (
                fallback_reason_breakdown.get(fallback_reason, 0) + 1
            )
        if not attempted:
            exemption_reason = semantic_runtime.get("exemption_reason")
            status = str(semantic_runtime.get("status", "")).strip()
            if (
                isinstance(exemption_reason, str)
                and exemption_reason.strip()
                or status in SEMANTIC_OBSERVABILITY_EXEMPT_STATUSES
            ):
                metrics["semantic_exempt_count"] += 1
            else:
                metrics["semantic_unattempted_without_exemption"] += 1
                if len(metrics["semantic_unattempted_samples"]) < 20:
                    metrics["semantic_unattempted_samples"].append(
                        {
                            "id": item.get("id"),
                            "type": action_type,
                            "path": normalize(str(item.get("path", ""))),
                            "reason": "attempt_missing_without_exemption",
                            "status": status or "unknown",
                        }
                    )

    action_count = metrics["semantic_action_count"]
    attempt_count = metrics["semantic_attempt_count"]
    metrics["fallback_reason_breakdown"] = dict(sorted(fallback_reason_breakdown.items()))
    metrics["semantic_unattempted_count"] = max(action_count - attempt_count, 0)
    metrics["semantic_hit_rate"] = (
        round(metrics["semantic_success_count"] / attempt_count, 4)
        if attempt_count > 0
        else 0.0
    )
    return metrics


def check_semantic_observability(
    root: Path,
    policy: dict[str, Any],
    apply_report_path: Path,
) -> tuple[list[str], list[str], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    semantic_settings = dsr.resolve_semantic_generation_settings(policy)
    observability_settings = resolve_semantic_observability_settings(policy)
    semantic_first_required = bool(
        semantic_settings.get("enabled", False)
        and semantic_settings.get("mode") != "deterministic"
        and semantic_settings.get("prefer_agent_semantic_first", True)
        and semantic_settings.get("require_semantic_attempt", True)
    )

    try:
        apply_report_rel = normalize(str(apply_report_path.relative_to(root)))
    except ValueError:
        apply_report_rel = normalize(str(apply_report_path))

    report: dict[str, Any] = {
        "enabled": bool(observability_settings.get("enabled", True)),
        "semantic_first_required": semantic_first_required,
        "settings": observability_settings,
        "apply_report_path": apply_report_rel,
        "apply_report_exists": apply_report_path.exists(),
        "gate": {"status": "skipped", "failed_checks": []},
        "metrics": {
            "semantic_action_count": 0,
            "semantic_attempt_count": 0,
            "semantic_success_count": 0,
            "fallback_count": 0,
            "fallback_reason_breakdown": {},
            "semantic_exempt_count": 0,
            "semantic_unattempted_count": 0,
            "semantic_unattempted_without_exemption": 0,
            "semantic_hit_rate": 0.0,
        },
        "samples": [],
    }

    if not observability_settings.get("enabled", True):
        report["gate"]["status"] = "skipped"
        return errors, warnings, report
    if not semantic_first_required:
        report["gate"]["status"] = "not_required"
        return errors, warnings, report
    if not apply_report_path.exists():
        warnings.append(
            "semantic gate warning: apply report missing; cannot evaluate semantic attempt coverage"
        )
        report["gate"]["status"] = "warn"
        return errors, warnings, report

    apply_report = load_json(apply_report_path)
    summary = apply_report.get("summary") if isinstance(apply_report, dict) else {}
    metrics_from_summary = {
        "semantic_action_count": _safe_int(
            (summary or {}).get("semantic_action_count", -1), -1
        ),
        "semantic_attempt_count": _safe_int(
            (summary or {}).get("semantic_attempt_count", -1), -1
        ),
        "semantic_success_count": _safe_int(
            (summary or {}).get("semantic_success_count", -1), -1
        ),
        "fallback_count": _safe_int((summary or {}).get("fallback_count", -1), -1),
        "semantic_exempt_count": _safe_int(
            (summary or {}).get("semantic_exempt_count", -1), -1
        ),
        "semantic_unattempted_count": _safe_int(
            (summary or {}).get("semantic_unattempted_count", -1), -1
        ),
        "semantic_unattempted_without_exemption": _safe_int(
            (summary or {}).get("semantic_unattempted_without_exemption", -1), -1
        ),
        "semantic_hit_rate": _safe_float(
            (summary or {}).get("semantic_hit_rate", -1.0), -1.0
        ),
        "fallback_reason_breakdown": _normalize_reason_breakdown(
            (summary or {}).get("fallback_reason_breakdown")
        ),
    }
    summary_complete = all(
        metrics_from_summary[key] >= 0
        for key in (
            "semantic_action_count",
            "semantic_attempt_count",
            "semantic_success_count",
            "fallback_count",
            "semantic_exempt_count",
            "semantic_unattempted_count",
            "semantic_unattempted_without_exemption",
        )
    )
    if summary_complete and metrics_from_summary["semantic_hit_rate"] >= 0:
        metrics = dict(metrics_from_summary)
    else:
        metrics = _derive_semantic_observability_from_results(apply_report, semantic_settings)

    report["metrics"] = {
        "semantic_action_count": max(_safe_int(metrics.get("semantic_action_count", 0), 0), 0),
        "semantic_attempt_count": max(
            _safe_int(metrics.get("semantic_attempt_count", 0), 0), 0
        ),
        "semantic_success_count": max(
            _safe_int(metrics.get("semantic_success_count", 0), 0), 0
        ),
        "fallback_count": max(_safe_int(metrics.get("fallback_count", 0), 0), 0),
        "fallback_reason_breakdown": _normalize_reason_breakdown(
            metrics.get("fallback_reason_breakdown")
        ),
        "semantic_exempt_count": max(
            _safe_int(metrics.get("semantic_exempt_count", 0), 0), 0
        ),
        "semantic_unattempted_count": max(
            _safe_int(metrics.get("semantic_unattempted_count", 0), 0), 0
        ),
        "semantic_unattempted_without_exemption": max(
            _safe_int(metrics.get("semantic_unattempted_without_exemption", 0), 0), 0
        ),
        "semantic_hit_rate": max(
            min(_safe_float(metrics.get("semantic_hit_rate", 0.0), 0.0), 1.0), 0.0
        ),
    }
    samples = metrics.get("semantic_unattempted_samples")
    if isinstance(samples, list):
        report["samples"] = [item for item in samples if isinstance(item, dict)][:20]

    semantic_action_count = report["metrics"]["semantic_action_count"]
    unattempted_without_exemption = report["metrics"][
        "semantic_unattempted_without_exemption"
    ]
    if semantic_action_count <= 0:
        report["gate"]["status"] = "passed"
        return errors, warnings, report

    unattempted_ratio = unattempted_without_exemption / semantic_action_count
    report["metrics"]["semantic_unattempted_ratio"] = round(unattempted_ratio, 4)

    large_ratio_threshold = float(observability_settings["large_unattempted_ratio"])
    large_count_threshold = int(observability_settings["large_unattempted_count"])
    large_gap = (
        unattempted_without_exemption >= large_count_threshold
        or unattempted_ratio >= large_ratio_threshold
    )

    if unattempted_without_exemption > 0:
        message = (
            "semantic gate warning: semantic-first actions missing runtime attempts: "
            f"count={unattempted_without_exemption}/{semantic_action_count} "
            f"ratio={round(unattempted_ratio, 4)}"
        )
        if large_gap and observability_settings.get("fail_on_large_unattempted", True):
            errors.append(message)
            report["gate"] = {
                "status": "failed",
                "failed_checks": ["semantic_unattempted_large_gap"],
            }
        else:
            warnings.append(message)
            report["gate"] = {
                "status": "warn" if large_gap else "passed_with_warning",
                "failed_checks": ["semantic_unattempted_large_gap"] if large_gap else [],
            }
    else:
        report["gate"]["status"] = "passed"

    return errors, warnings, report


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
        "--apply-report",
        default="docs/.doc-apply-report.json",
        help="Doc apply JSON report path for semantic observability gate",
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
    apply_report_path = (
        (root / args.apply_report).resolve()
        if not Path(args.apply_report).is_absolute()
        else Path(args.apply_report)
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

    topology_errors, topology_warnings, topology_report = check_topology_contract(
        root, policy, manifest
    )
    errors.extend(topology_errors)
    warnings.extend(topology_warnings)

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

    semantic_obs_errors, semantic_obs_warnings, semantic_obs_report = (
        check_semantic_observability(root, policy, apply_report_path)
    )
    errors.extend(semantic_obs_errors)
    warnings.extend(semantic_obs_warnings)

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
            "topology_enabled": topology_report.get("enabled", False),
            "topology_loaded": topology_report.get("loaded", False),
            "topology_error_count": len(topology_report.get("errors", [])),
            "topology_warning_count": len(topology_report.get("warnings", [])),
            "topology_reachable_ratio": (topology_report.get("metrics") or {}).get(
                "topology_reachable_ratio", 1.0
            ),
            "topology_orphan_count": (topology_report.get("metrics") or {}).get(
                "topology_orphan_count", 0
            ),
            "topology_unreachable_count": (topology_report.get("metrics") or {}).get(
                "topology_unreachable_count", 0
            ),
            "topology_max_depth": (topology_report.get("metrics") or {}).get(
                "topology_max_depth", 0
            ),
            "topology_depth_limit": (topology_report.get("metrics") or {}).get(
                "topology_depth_limit",
                (topology_report.get("settings") or {}).get("max_depth", 0),
            ),
            "topology_navigation_missing_count": (
                topology_report.get("metrics") or {}
            ).get("navigation_missing_count", 0),
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
            "semantic_observability_enabled": semantic_obs_report.get("enabled", False),
            "semantic_observability_required": semantic_obs_report.get(
                "semantic_first_required", False
            ),
            "semantic_observability_gate_status": (
                (semantic_obs_report.get("gate") or {}).get("status", "skipped")
            ),
            "semantic_action_count": (semantic_obs_report.get("metrics") or {}).get(
                "semantic_action_count", 0
            ),
            "semantic_attempt_count": (semantic_obs_report.get("metrics") or {}).get(
                "semantic_attempt_count", 0
            ),
            "semantic_success_count": (semantic_obs_report.get("metrics") or {}).get(
                "semantic_success_count", 0
            ),
            "fallback_count": (semantic_obs_report.get("metrics") or {}).get(
                "fallback_count", 0
            ),
            "fallback_reason_breakdown": (semantic_obs_report.get("metrics") or {}).get(
                "fallback_reason_breakdown", {}
            ),
            "semantic_hit_rate": (semantic_obs_report.get("metrics") or {}).get(
                "semantic_hit_rate", 0.0
            ),
            "semantic_unattempted_count": (semantic_obs_report.get("metrics") or {}).get(
                "semantic_unattempted_count", 0
            ),
            "semantic_unattempted_without_exemption": (
                (semantic_obs_report.get("metrics") or {}).get(
                    "semantic_unattempted_without_exemption", 0
                )
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
        "doc_topology": topology_report,
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
        "semantic_observability": semantic_obs_report,
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
