#!/usr/bin/env python3
from __future__ import annotations

import fnmatch
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import doc_capabilities as dc

DEFAULT_LEGACY_SETTINGS = {
    "enabled": False,
    "include_globs": [],
    "exclude_globs": [
        "docs/**",
        "docs/archive/**",
        ".git/**",
        ".agents/**",
        "skills/**",
        "**/__pycache__/**",
        "**/*.pyc",
    ],
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
}

COMPLETED_STATUSES = {"migrated", "archived", "exempted"}
DEFAULT_SEMANTIC_CATEGORIES = [
    "requirement",
    "plan",
    "progress",
    "worklog",
    "agent_ops",
    "not_migratable",
]
DEFAULT_SEMANTIC_SETTINGS = {
    "enabled": False,
    "engine": "llm",
    "provider": "agent_runtime",
    "model": "agent-runtime-report-v1",
    "auto_migrate_threshold": 0.85,
    "review_threshold": 0.60,
    "max_chars_per_doc": 20000,
    "categories": list(DEFAULT_SEMANTIC_CATEGORIES),
    "denylist_files": ["README.md", "AGENTS.md"],
    "fail_closed": True,
    "allow_fallback_auto_migrate": False,
}
_SEMANTIC_CATEGORY_SIGNALS = {
    "requirement": ["requirement", "requirements", "需求", "spec", "scope"],
    "plan": ["plan", "roadmap", "milestone", "timeline", "phase", "规划", "里程碑"],
    "progress": ["progress", "status", "update", "完成", "进度", "结论"],
    "worklog": ["worklog", "journal", "daily", "log", "日志", "记录"],
    "agent_ops": ["agent", "codex", "automation", "runbook", "script", "执行"],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_rel(path_str: str) -> str:
    return dc.normalize_rel(path_str)


def _normalize_globs(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = normalize_rel(item.strip())
        if normalized:
            out.append(normalized)
    return sorted(set(out))


def _normalize_mapping_table(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for key, target in value.items():
        if not isinstance(key, str) or not isinstance(target, str):
            continue
        source_rel = normalize_rel(key.strip())
        target_rel = normalize_rel(target.strip())
        if source_rel and target_rel:
            out[source_rel] = target_rel
    return out


def _normalize_confidence(value: Any, fallback: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return fallback
    if numeric < 0:
        return 0.0
    if numeric > 1:
        return 1.0
    return numeric


def _normalize_positive_int(value: Any, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return fallback
    if numeric <= 0:
        return fallback
    return numeric


def _normalize_semantic_categories(value: Any) -> list[str]:
    if not isinstance(value, list):
        return list(DEFAULT_SEMANTIC_CATEGORIES)
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if not normalized:
            continue
        out.append(normalized)
    if not out:
        return list(DEFAULT_SEMANTIC_CATEGORIES)
    if "not_migratable" not in out:
        out.append("not_migratable")
    return sorted(set(out))


def _normalize_denylist_files(value: Any) -> list[str]:
    if not isinstance(value, list):
        return list(DEFAULT_SEMANTIC_SETTINGS["denylist_files"])
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = normalize_rel(item.strip())
        if normalized:
            out.append(normalized)
    if not out:
        return list(DEFAULT_SEMANTIC_SETTINGS["denylist_files"])
    return sorted(set(out))


def resolve_legacy_semantic_settings(legacy_raw: dict[str, Any]) -> dict[str, Any]:
    semantic_raw = legacy_raw.get("semantic") if isinstance(legacy_raw.get("semantic"), dict) else {}
    enabled = bool(semantic_raw.get("enabled", DEFAULT_SEMANTIC_SETTINGS["enabled"]))
    engine = str(semantic_raw.get("engine", DEFAULT_SEMANTIC_SETTINGS["engine"])).strip() or str(
        DEFAULT_SEMANTIC_SETTINGS["engine"]
    )
    provider = str(semantic_raw.get("provider", DEFAULT_SEMANTIC_SETTINGS["provider"])).strip()
    if not provider:
        provider = (
            "agent_runtime"
            if engine == "llm"
            else (
                "deterministic_mock" if engine == "deterministic_mock" else str(DEFAULT_SEMANTIC_SETTINGS["provider"])
            )
        )
    model = str(semantic_raw.get("model", DEFAULT_SEMANTIC_SETTINGS["model"])).strip()
    if not model:
        model = str(DEFAULT_SEMANTIC_SETTINGS["model"])
    auto_threshold = _normalize_confidence(
        semantic_raw.get(
            "auto_migrate_threshold",
            DEFAULT_SEMANTIC_SETTINGS["auto_migrate_threshold"],
        ),
        float(DEFAULT_SEMANTIC_SETTINGS["auto_migrate_threshold"]),
    )
    review_threshold = _normalize_confidence(
        semantic_raw.get(
            "review_threshold",
            DEFAULT_SEMANTIC_SETTINGS["review_threshold"],
        ),
        float(DEFAULT_SEMANTIC_SETTINGS["review_threshold"]),
    )
    if review_threshold > auto_threshold:
        review_threshold = auto_threshold
    return {
        "enabled": enabled,
        "engine": engine,
        "provider": provider,
        "model": model,
        "auto_migrate_threshold": auto_threshold,
        "review_threshold": review_threshold,
        "max_chars_per_doc": _normalize_positive_int(
            semantic_raw.get("max_chars_per_doc", DEFAULT_SEMANTIC_SETTINGS["max_chars_per_doc"]),
            int(DEFAULT_SEMANTIC_SETTINGS["max_chars_per_doc"]),
        ),
        "categories": _normalize_semantic_categories(semantic_raw.get("categories")),
        "denylist_files": _normalize_denylist_files(semantic_raw.get("denylist_files")),
        "fail_closed": bool(semantic_raw.get("fail_closed", DEFAULT_SEMANTIC_SETTINGS["fail_closed"])),
        "allow_fallback_auto_migrate": bool(
            semantic_raw.get(
                "allow_fallback_auto_migrate",
                DEFAULT_SEMANTIC_SETTINGS["allow_fallback_auto_migrate"],
            )
        ),
    }


def _resolve_semantic_decision(category: str, confidence: float, semantic_settings: dict[str, Any]) -> str:
    if category == "not_migratable":
        return "skip"
    auto_threshold = float(semantic_settings.get("auto_migrate_threshold", 0.85))
    review_threshold = float(semantic_settings.get("review_threshold", 0.60))
    if confidence >= auto_threshold:
        return "auto_migrate"
    if confidence >= review_threshold:
        return "manual_review"
    return "skip"


def _normalize_semantic_decision(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    decision = value.strip()
    if decision in {"auto_migrate", "manual_review", "skip"}:
        return decision
    return None


def load_semantic_report_index(
    root: Path,
    settings: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    semantic_report_rel = normalize_rel(str(settings.get("semantic_report_path", "")).strip())
    metadata: dict[str, Any] = {
        "report_path": semantic_report_rel,
        "available": False,
        "entry_count": 0,
        "error": None,
    }
    if not semantic_report_rel:
        metadata["error"] = "semantic_report_path is empty"
        return {}, metadata

    report_path = (root / semantic_report_rel).resolve()
    if not report_path.exists():
        metadata["error"] = f"semantic report not found: {semantic_report_rel}"
        return {}, metadata

    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        metadata["error"] = f"semantic report unreadable: {exc}"
        return {}, metadata
    if not isinstance(payload, dict):
        metadata["error"] = "semantic report root must be object"
        return {}, metadata

    entries_raw = payload.get("entries")
    if not isinstance(entries_raw, list):
        metadata["error"] = "semantic report entries must be list"
        return {}, metadata

    index: dict[str, dict[str, Any]] = {}
    for item in entries_raw:
        if not isinstance(item, dict):
            continue
        source_path = item.get("source_path")
        if not isinstance(source_path, str) or not source_path.strip():
            continue
        index[normalize_rel(source_path)] = item

    metadata["available"] = True
    metadata["entry_count"] = len(index)
    return index, metadata


def _classify_with_deterministic_mock(
    source_rel: str, content: str, semantic_settings: dict[str, Any]
) -> dict[str, Any]:
    searchable = f"{source_rel.lower()}\n{content.lower()}"
    allowed_categories = set(semantic_settings.get("categories") or [])
    scores: dict[str, int] = {}
    matched_signals: dict[str, list[str]] = {}
    for category, keywords in _SEMANTIC_CATEGORY_SIGNALS.items():
        if allowed_categories and category not in allowed_categories:
            continue
        for keyword in keywords:
            if keyword.lower() not in searchable:
                continue
            scores[category] = scores.get(category, 0) + 1
            matched_signals.setdefault(category, []).append(keyword)

    if not scores:
        category = "not_migratable"
        confidence = 0.40
        rationale = "deterministic mock found no semantic signals"
        signals = ["no-matched-keyword"]
    else:
        category = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        score = scores[category]
        confidence = min(0.98, 0.55 + score * 0.12)
        signals = sorted(set(matched_signals.get(category, [])))
        rationale = "deterministic mock matched semantic signals"

    decision = _resolve_semantic_decision(category, confidence, semantic_settings)
    return {
        "category": category,
        "confidence": round(confidence, 4),
        "rationale": rationale,
        "signals": signals,
        "decision": decision,
    }


def _classify_with_agent_runtime(
    source_rel: str,
    semantic_settings: dict[str, Any],
    mapping_table: dict[str, str],
    runtime_entry: dict[str, Any] | None,
    runtime_state: dict[str, Any] | None,
) -> dict[str, Any]:
    state = runtime_state if isinstance(runtime_state, dict) else {}
    runtime_available = bool(state.get("available", False))
    runtime_error = state.get("error")
    normalized_source = normalize_rel(source_rel)

    if isinstance(runtime_entry, dict):
        category_raw = runtime_entry.get("category")
        category = (
            str(category_raw).strip()
            if isinstance(category_raw, str) and str(category_raw).strip()
            else "not_migratable"
        )
        confidence = _normalize_confidence(runtime_entry.get("confidence"), 0.0)
        decision = _normalize_semantic_decision(runtime_entry.get("decision"))
        if decision is None:
            decision = _resolve_semantic_decision(category, confidence, semantic_settings)
        rationale_raw = runtime_entry.get("rationale")
        rationale = (
            str(rationale_raw).strip()
            if isinstance(rationale_raw, str) and str(rationale_raw).strip()
            else "agent runtime semantic report matched source_path"
        )
        signals_raw = runtime_entry.get("signals")
        signals: list[str] = []
        if isinstance(signals_raw, list):
            for item in signals_raw:
                if isinstance(item, str) and item.strip():
                    signals.append(item.strip())
        if not signals:
            signals = ["agent_runtime_report"]

        provider_raw = runtime_entry.get("provider")
        provider = (
            str(provider_raw).strip()
            if isinstance(provider_raw, str) and str(provider_raw).strip()
            else "agent_runtime"
        )
        model_raw = runtime_entry.get("model")
        model = (
            str(model_raw).strip()
            if isinstance(model_raw, str) and str(model_raw).strip()
            else str(semantic_settings.get("model") or DEFAULT_SEMANTIC_SETTINGS["model"])
        )
        return {
            "source_path": normalized_source,
            "category": category,
            "confidence": round(confidence, 4),
            "rationale": rationale,
            "signals": sorted(set(signals)),
            "decision": decision,
            "provider": provider,
            "model": model,
            "decision_source": "semantic",
            "fallback_auto_migrate": False,
        }

    allow_fallback_auto = bool(semantic_settings.get("allow_fallback_auto_migrate", False))
    mapping_hit = normalized_source in mapping_table
    fallback_decision = "manual_review" if semantic_settings.get("fail_closed", True) else "skip"
    fallback_auto = False
    signals = ["agent_runtime_fallback"]
    rationale = "agent runtime semantic report missing source entry"
    if not runtime_available:
        rationale = "agent runtime semantic report unavailable"
        if isinstance(runtime_error, str) and runtime_error.strip():
            rationale = f"{rationale}: {runtime_error.strip()}"

    if allow_fallback_auto and mapping_hit:
        fallback_decision = "auto_migrate"
        fallback_auto = True
        signals.append("mapping_table")
        rationale = "fallback auto migration allowed by mapping_table"
    elif mapping_hit:
        signals.append("mapping_table")

    return {
        "source_path": normalized_source,
        "category": "not_migratable",
        "confidence": 0.0,
        "rationale": rationale,
        "signals": sorted(set(signals)),
        "decision": fallback_decision,
        "provider": "agent_runtime",
        "model": str(semantic_settings.get("model") or DEFAULT_SEMANTIC_SETTINGS["model"]),
        "decision_source": "fallback",
        "fallback_auto_migrate": fallback_auto,
    }


def classify_legacy_source(
    root: Path,
    source_rel: str,
    settings: dict[str, Any],
    runtime_semantic_index: dict[str, dict[str, Any]] | None = None,
    runtime_semantic_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_rel = normalize_rel(source_rel)
    semantic_settings = (
        settings.get("semantic") if isinstance(settings.get("semantic"), dict) else resolve_legacy_semantic_settings({})
    )
    if not semantic_settings.get("enabled", False):
        return {
            "source_path": source_rel,
            "category": None,
            "confidence": None,
            "rationale": "semantic classifier disabled by policy",
            "signals": [],
            "decision": "manual_review",
            "engine": semantic_settings.get("engine"),
            "provider": semantic_settings.get("provider"),
            "model": semantic_settings.get("model"),
        }

    provider_name = str(semantic_settings.get("provider", DEFAULT_SEMANTIC_SETTINGS["provider"])).strip() or str(
        DEFAULT_SEMANTIC_SETTINGS["provider"]
    )
    denylist = set(semantic_settings.get("denylist_files") or [])
    denylist_names = {Path(item).name for item in denylist}
    if source_rel in denylist or Path(source_rel).name in denylist_names:
        return {
            "source_path": source_rel,
            "category": "not_migratable",
            "confidence": 1.0,
            "rationale": "source matched semantic denylist_files",
            "signals": ["denylist_files"],
            "decision": "skip",
            "engine": semantic_settings.get("engine"),
            "provider": provider_name,
            "model": semantic_settings.get("model"),
            "decision_source": "semantic",
            "fallback_auto_migrate": False,
        }

    if provider_name == "agent_runtime":
        runtime_index = runtime_semantic_index if isinstance(runtime_semantic_index, dict) else {}
        runtime_state = runtime_semantic_state if isinstance(runtime_semantic_state, dict) else {}
        runtime_entry = runtime_index.get(source_rel)
        result = _classify_with_agent_runtime(
            source_rel=source_rel,
            semantic_settings=semantic_settings,
            mapping_table=settings.get("mapping_table") if isinstance(settings.get("mapping_table"), dict) else {},
            runtime_entry=runtime_entry if isinstance(runtime_entry, dict) else None,
            runtime_state=runtime_state,
        )
        result["engine"] = semantic_settings.get("engine")
        if not isinstance(result.get("provider"), str) or not str(result.get("provider")).strip():
            result["provider"] = provider_name
        if not isinstance(result.get("model"), str) or not str(result.get("model")).strip():
            result["model"] = semantic_settings.get("model")
        return result

    if provider_name != "deterministic_mock":
        fallback_decision = "manual_review" if semantic_settings.get("fail_closed", True) else "skip"
        return {
            "source_path": source_rel,
            "category": "not_migratable",
            "confidence": 0.0,
            "rationale": f"semantic provider failure: unsupported semantic provider: {provider_name}",
            "signals": ["provider-error"],
            "decision": fallback_decision,
            "engine": semantic_settings.get("engine"),
            "provider": provider_name,
            "model": semantic_settings.get("model"),
            "decision_source": "fallback",
            "fallback_auto_migrate": False,
        }

    source_abs = root / source_rel
    try:
        raw_content = source_abs.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        fallback_decision = "manual_review" if semantic_settings.get("fail_closed", True) else "skip"
        return {
            "source_path": source_rel,
            "category": "not_migratable",
            "confidence": 0.0,
            "rationale": f"semantic classifier failed to read source: {exc}",
            "signals": ["read-error"],
            "decision": fallback_decision,
            "engine": semantic_settings.get("engine"),
            "provider": provider_name,
            "model": semantic_settings.get("model"),
            "decision_source": "fallback",
            "fallback_auto_migrate": False,
        }

    max_chars = int(semantic_settings.get("max_chars_per_doc", 20000))
    content = raw_content[:max_chars]
    truncated = len(raw_content) > max_chars
    try:
        result = _classify_with_deterministic_mock(source_rel, content, semantic_settings)
    except Exception as exc:  # noqa: BLE001
        fallback_decision = "manual_review" if semantic_settings.get("fail_closed", True) else "skip"
        return {
            "source_path": source_rel,
            "category": "not_migratable",
            "confidence": 0.0,
            "rationale": f"semantic provider failure: {exc}",
            "signals": ["provider-error"],
            "decision": fallback_decision,
            "engine": semantic_settings.get("engine"),
            "provider": provider_name,
            "model": semantic_settings.get("model"),
            "decision_source": "fallback",
            "fallback_auto_migrate": False,
        }

    result["source_path"] = source_rel
    result["engine"] = semantic_settings.get("engine")
    result["provider"] = provider_name
    result["model"] = semantic_settings.get("model")
    result["truncated"] = truncated
    result["analyzed_chars"] = len(content)
    result["decision_source"] = "semantic"
    result["fallback_auto_migrate"] = False
    return result


def resolve_legacy_settings(policy: dict[str, Any] | None) -> dict[str, Any]:
    raw = (
        policy.get("legacy_sources")
        if isinstance(policy, dict) and isinstance(policy.get("legacy_sources"), dict)
        else {}
    )

    enabled = bool(raw.get("enabled", DEFAULT_LEGACY_SETTINGS["enabled"]))
    include_globs = _normalize_globs(raw.get("include_globs", DEFAULT_LEGACY_SETTINGS["include_globs"]))
    exclude_globs = _normalize_globs(raw.get("exclude_globs", DEFAULT_LEGACY_SETTINGS["exclude_globs"]))
    archive_root = normalize_rel(str(raw.get("archive_root", DEFAULT_LEGACY_SETTINGS["archive_root"])))
    mapping_strategy = str(raw.get("mapping_strategy", DEFAULT_LEGACY_SETTINGS["mapping_strategy"])).strip() or str(
        DEFAULT_LEGACY_SETTINGS["mapping_strategy"]
    )
    if mapping_strategy not in {"path_based", "tag_based", "manual_table"}:
        mapping_strategy = "path_based"
    target_root = normalize_rel(str(raw.get("target_root", DEFAULT_LEGACY_SETTINGS["target_root"])))
    target_doc = normalize_rel(str(raw.get("target_doc", DEFAULT_LEGACY_SETTINGS["target_doc"])))
    registry_path = normalize_rel(str(raw.get("registry_path", DEFAULT_LEGACY_SETTINGS["registry_path"])))
    allow_non_markdown = bool(raw.get("allow_non_markdown", DEFAULT_LEGACY_SETTINGS["allow_non_markdown"]))
    exempt_sources = _normalize_globs(raw.get("exempt_sources", DEFAULT_LEGACY_SETTINGS["exempt_sources"]))
    mapping_table = _normalize_mapping_table(raw.get("mapping_table", DEFAULT_LEGACY_SETTINGS["mapping_table"]))
    fail_on_legacy_drift = bool(raw.get("fail_on_legacy_drift", DEFAULT_LEGACY_SETTINGS["fail_on_legacy_drift"]))
    semantic_report_path = normalize_rel(
        str(raw.get("semantic_report_path", DEFAULT_LEGACY_SETTINGS["semantic_report_path"]))
    )
    semantic = resolve_legacy_semantic_settings(raw)

    archive_prefix = archive_root.rstrip("/") + "/"
    if not any(pattern.startswith(archive_prefix) for pattern in exclude_globs):
        exclude_globs = sorted(set(exclude_globs + [f"{archive_prefix}**"]))

    return {
        "enabled": enabled,
        "include_globs": include_globs,
        "exclude_globs": exclude_globs,
        "archive_root": archive_root,
        "mapping_strategy": mapping_strategy,
        "target_root": target_root,
        "target_doc": target_doc,
        "registry_path": registry_path,
        "allow_non_markdown": allow_non_markdown,
        "exempt_sources": exempt_sources,
        "mapping_table": mapping_table,
        "fail_on_legacy_drift": fail_on_legacy_drift,
        "semantic_report_path": semantic_report_path,
        "semantic": semantic,
    }


def discover_legacy_sources(root: Path, settings: dict[str, Any]) -> list[str]:
    if not settings.get("enabled", False):
        return []

    include_globs = settings.get("include_globs") or []
    if not include_globs:
        return []

    exclude_globs = settings.get("exclude_globs") or []
    archive_root = normalize_rel(str(settings.get("archive_root", "docs/archive/legacy")))
    archive_prefix = archive_root.rstrip("/") + "/"
    registry_path = normalize_rel(str(settings.get("registry_path", "")))
    target_doc = normalize_rel(str(settings.get("target_doc", "")))
    allow_non_markdown = bool(settings.get("allow_non_markdown", True))

    candidates: list[str] = []
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue

        rel = normalize_rel(str(file_path.relative_to(root)))
        if rel.startswith(archive_prefix):
            continue
        if rel in {registry_path, target_doc}:
            continue
        if file_path.name.startswith("."):
            continue
        if not any(fnmatch.fnmatch(rel, pattern) for pattern in include_globs):
            continue
        if any(fnmatch.fnmatch(rel, pattern) for pattern in exclude_globs):
            continue
        if not allow_non_markdown and file_path.suffix.lower() != ".md":
            continue
        candidates.append(rel)

    return sorted(set(candidates))


def resolve_target_path(source_rel: str, settings: dict[str, Any]) -> str:
    source_rel = normalize_rel(source_rel)
    mapping_table = settings.get("mapping_table") or {}
    mapped = mapping_table.get(source_rel)
    if isinstance(mapped, str) and mapped.strip():
        return normalize_rel(mapped)

    strategy = settings.get("mapping_strategy", "path_based")
    if strategy == "path_based":
        source_path = Path(source_rel)
        filename = source_path.name if source_path.suffix.lower() == ".md" else f"{source_path.name}.md"
        target = Path(str(settings.get("target_root", "docs/history/legacy")))
        return normalize_rel(str(target / source_path.parent / filename))

    return normalize_rel(str(settings.get("target_doc", "docs/history/legacy-migration.md")))


def resolve_archive_path(source_rel: str, settings: dict[str, Any]) -> str:
    source_path = Path(normalize_rel(source_rel))
    archive_root = Path(str(settings.get("archive_root", "docs/archive/legacy")))
    return normalize_rel(str(archive_root / source_path))


def source_marker(source_rel: str) -> str:
    return f"<!-- legacy-source: {normalize_rel(source_rel)} -->"


def render_target_header(template_profile: str) -> str:
    if template_profile == "zh-CN":
        return "# Legacy 迁移记录\n\n该文档由 docs-sor-maintainer 自动维护。\n"
    return "# Legacy Migration Records\n\nThis document is maintained by docs-sor-maintainer.\n"


def _collect_nonempty_lines(source_content: str, max_lines: int = 120) -> list[str]:
    out: list[str] = []
    for raw_line in source_content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        out.append(line)
        if len(out) >= max_lines:
            break
    return out


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _extract_lines_by_keywords(lines: list[str], keywords: list[str], max_items: int) -> list[str]:
    lowered_keywords = [k.lower() for k in keywords]
    out: list[str] = []
    for line in lines:
        lower_line = line.lower()
        if not any(keyword in lower_line for keyword in lowered_keywords):
            continue
        candidate = _truncate_text(line, 180)
        if candidate in out:
            continue
        out.append(candidate)
        if len(out) >= max_items:
            break
    return out


def _extract_date_lines(lines: list[str], max_items: int = 3) -> list[str]:
    pattern = re.compile(r"\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2})\b")
    out: list[str] = []
    for line in lines:
        if not pattern.search(line):
            continue
        candidate = _truncate_text(line, 180)
        if candidate in out:
            continue
        out.append(candidate)
        if len(out) >= max_items:
            break
    return out


def _render_structured_section(heading: str, items: list[str], fallback: str) -> list[str]:
    lines = [heading]
    if not items:
        lines.append(f"- {fallback}")
        lines.append("")
        return lines
    for item in items:
        lines.append(f"- {item}")
    lines.append("")
    return lines


def build_structured_migration_payload(
    source_rel: str,
    source_content: str,
    archive_path: str,
    template_profile: str,
    semantic: dict[str, Any] | None = None,
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    normalized_source = normalize_rel(source_rel)
    normalized_archive = normalize_rel(archive_path)
    semantic_payload = semantic if isinstance(semantic, dict) else {}
    lines = _collect_nonempty_lines(source_content)
    first_line = lines[0] if lines else "(empty)"
    summary_items: list[str] = [_truncate_text(first_line, 180)]
    category = semantic_payload.get("category")
    confidence = semantic_payload.get("confidence")
    if isinstance(category, str) and category.strip():
        if template_profile == "zh-CN":
            summary_items.append(f"语义分类：`{category.strip()}`")
        else:
            summary_items.append(f"Semantic category: `{category.strip()}`")
    if isinstance(confidence, (float, int)):
        if template_profile == "zh-CN":
            summary_items.append(f"语义置信度：`{float(confidence):.2f}`")
        else:
            summary_items.append(f"Semantic confidence: `{float(confidence):.2f}`")

    date_lines = _extract_date_lines(lines)
    module_hint = Path(normalized_source).parent.as_posix()
    key_facts: list[str] = []
    if template_profile == "zh-CN":
        key_facts.append(f"来源文件：`{normalized_source}`")
        if module_hint and module_hint != ".":
            key_facts.append(f"来源目录：`{module_hint}`")
    else:
        key_facts.append(f"Source file: `{normalized_source}`")
        if module_hint and module_hint != ".":
            key_facts.append(f"Source directory: `{module_hint}`")
    key_facts.extend(date_lines)
    key_facts = key_facts[:5]

    decision_keywords = ["decision", "decide", "constraint", "must", "结论", "决定", "约束", "需"]
    decision_items = _extract_lines_by_keywords(lines, decision_keywords, max_items=5)

    risk_keywords = ["todo", "risk", "block", "pending", "issue", "待办", "风险", "阻塞", "问题"]
    risk_items = _extract_lines_by_keywords(lines, risk_keywords, max_items=6)

    trace_items: list[str] = []
    if template_profile == "zh-CN":
        trace_items.append(f"来源路径：`{normalized_source}`")
        trace_items.append(f"归档路径：`{normalized_archive}`")
    else:
        trace_items.append(f"Source path: `{normalized_source}`")
        trace_items.append(f"Archive path: `{normalized_archive}`")
    if isinstance(evidence, list):
        compact_evidence = [str(item).strip() for item in evidence if str(item).strip()]
        if compact_evidence:
            label = "证据引用" if template_profile == "zh-CN" else "Evidence references"
            trace_items.append(f"{label}：`{compact_evidence[0]}`")

    excerpt_lines = source_content.splitlines()
    excerpt = "\n".join(excerpt_lines[:20]).strip()
    if not excerpt:
        excerpt = "(empty)"

    return {
        "summary": summary_items,
        "key_facts": key_facts,
        "decisions": decision_items,
        "risks": risk_items,
        "trace": trace_items,
        "excerpt": excerpt,
    }


def render_structured_migration_entry(
    source_rel: str,
    source_content: str,
    archive_path: str,
    template_profile: str,
    semantic: dict[str, Any] | None = None,
    evidence: list[str] | None = None,
) -> str:
    source_rel = normalize_rel(source_rel)
    archive_path = normalize_rel(archive_path)
    marker = source_marker(source_rel)
    migrated_at = utc_now()
    payload = build_structured_migration_payload(
        source_rel=source_rel,
        source_content=source_content,
        archive_path=archive_path,
        template_profile=template_profile,
        semantic=semantic,
        evidence=evidence,
    )

    if template_profile == "zh-CN":
        summary_heading = "### 摘要"
        key_facts_heading = "### 关键事实"
        decisions_heading = "### 决策与结论"
        risks_heading = "### 待办与风险"
        trace_heading = "### 来源追踪"
        excerpt_heading = "#### 原文短摘录"
        summary_fallback = "TODO: 补充文档目的与上下文"
        key_facts_fallback = "UNKNOWN"
        decisions_fallback = "TODO: 补充已决定事项与约束"
        risks_fallback = "暂无待办或风险"
    else:
        summary_heading = "### Summary"
        key_facts_heading = "### Key Facts"
        decisions_heading = "### Decisions"
        risks_heading = "### TODO & Risks"
        trace_heading = "### Source Trace"
        excerpt_heading = "#### Source Excerpt"
        summary_fallback = "TODO: Add document purpose and context"
        key_facts_fallback = "UNKNOWN"
        decisions_fallback = "TODO: Add decided constraints"
        risks_fallback = "No pending tasks or risks"

    lines: list[str] = [
        f"## Legacy Source `{source_rel}`",
        marker,
        f"<!-- legacy-migrated-at: {migrated_at} -->",
        "",
    ]
    lines.extend(_render_structured_section(summary_heading, payload["summary"], summary_fallback))
    lines.extend(_render_structured_section(key_facts_heading, payload["key_facts"], key_facts_fallback))
    lines.extend(_render_structured_section(decisions_heading, payload["decisions"], decisions_fallback))
    lines.extend(_render_structured_section(risks_heading, payload["risks"], risks_fallback))
    lines.extend(_render_structured_section(trace_heading, payload["trace"], key_facts_fallback))
    lines.extend(
        [
            excerpt_heading,
            "",
            "````text",
            payload["excerpt"],
            "````",
            "",
        ]
    )
    return "\n".join(lines)


def render_migration_entry(
    source_rel: str,
    source_content: str,
    archive_path: str,
    template_profile: str,
) -> str:
    # Backward-compatible wrapper: Phase B defaults to structured migration output.
    return render_structured_migration_entry(
        source_rel=source_rel,
        source_content=source_content,
        archive_path=archive_path,
        template_profile=template_profile,
    )


def load_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "updated_at": utc_now(), "entries": {}}

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if data is None or not isinstance(data, dict):
        return {"version": 1, "updated_at": utc_now(), "entries": {}}

    raw_entries = data.get("entries") if isinstance(data.get("entries"), dict) else {}
    entries: dict[str, dict[str, Any]] = {}
    for key, value in raw_entries.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        rel = normalize_rel(key)
        item = dict(value)
        if isinstance(item.get("source_path"), str):
            item["source_path"] = normalize_rel(item["source_path"])
        if isinstance(item.get("target_path"), str):
            item["target_path"] = normalize_rel(item["target_path"])
        if isinstance(item.get("archive_path"), str):
            item["archive_path"] = normalize_rel(item["archive_path"])
        entries[rel] = item

    return {
        "version": int(data.get("version", 1) or 1),
        "updated_at": str(data.get("updated_at") or utc_now()),
        "entries": entries,
    }


def save_registry(path: Path, registry: dict[str, Any], dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)
        f.write("\n")


def upsert_registry_entry(registry: dict[str, Any], source_rel: str, patch: dict[str, Any]) -> dict[str, Any]:
    source_key = normalize_rel(source_rel)
    entries = registry.setdefault("entries", {})
    current = entries.get(source_key) if isinstance(entries.get(source_key), dict) else {}
    updated = dict(current)
    updated.update(patch)
    updated["source_path"] = source_key
    entries[source_key] = updated
    registry["updated_at"] = utc_now()
    return updated


def has_completed_entry(registry: dict[str, Any], source_rel: str) -> bool:
    entries = registry.get("entries") if isinstance(registry.get("entries"), dict) else {}
    entry = entries.get(normalize_rel(source_rel))
    if not isinstance(entry, dict):
        return False
    status = entry.get("status")
    return isinstance(status, str) and status in COMPLETED_STATUSES
