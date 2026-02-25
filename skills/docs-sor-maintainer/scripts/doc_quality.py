#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import doc_spec  # noqa: E402
import doc_synthesize  # noqa: E402
import doc_legacy as dl  # noqa: E402
import doc_topology as dt  # noqa: E402


STRUCTURED_SECTION_MARKER_GROUPS = [
    ("summary", ["### 摘要", "### Summary"]),
    ("key_facts", ["### 关键事实", "### Key Facts"]),
    ("decisions", ["### 决策与结论", "### Decisions"]),
    ("risks", ["### 待办与风险", "### TODO & Risks"]),
    ("trace", ["### 来源追踪", "### Source Trace"]),
]
PROGRESSIVE_SLOT_MARKERS = {
    "summary": ["### 摘要", "### Summary"],
    "key_facts": ["### 关键事实", "### Key Facts"],
    "next_steps": ["### 下一步", "### Next Steps"],
}
LIST_ITEM_PATTERN = re.compile(r"^\s*(?:[-*+]\s+|\d+\.\s+)")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return data


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


def build_evidence_map(
    spec_data: dict[str, Any], facts: dict[str, Any] | None, root: Path
) -> list[dict[str, Any]]:
    documents_output: list[dict[str, Any]] = []
    runbook_cache: dict[str, list[str]] = {}
    for doc in spec_data.get("documents", []) or []:
        if not isinstance(doc, dict):
            continue
        path_value = doc.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            continue
        sections = doc.get("sections")
        if not isinstance(sections, list) or not sections:
            continue

        section_outputs: list[dict[str, Any]] = []
        for section in sections:
            if not isinstance(section, dict):
                continue
            section_id = section.get("section_id")
            if not isinstance(section_id, str) or not section_id.strip():
                continue
            claims = section.get("claims")
            if not isinstance(claims, list) or not claims:
                continue

            claim_outputs: list[dict[str, Any]] = []
            for claim in claims:
                if not isinstance(claim, dict):
                    continue
                claim_entry, _ = doc_synthesize.build_claim_entry(
                    claim,
                    facts,
                    root=root,
                    runbook_cache=runbook_cache,
                )
                claim_outputs.append(claim_entry)

            section_outputs.append(
                {
                    "section_id": section_id.strip(),
                    "claims": claim_outputs,
                }
            )

        documents_output.append(
            {
                "path": path_value.strip(),
                "sections": section_outputs,
            }
        )
    return documents_output


def flatten_claims(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for doc in documents:
        for section in doc.get("sections", []) or []:
            for claim in section.get("claims", []) or []:
                if isinstance(claim, dict):
                    claims.append(claim)
    return claims


def get_semantic_quality_thresholds(policy: dict[str, Any]) -> dict[str, Any]:
    quality_policy = policy.get("doc_quality_gates")
    quality_policy = quality_policy if isinstance(quality_policy, dict) else {}
    return {
        "max_semantic_conflicts": int(
            quality_policy.get("max_semantic_conflicts", 0)
        ),
        "max_semantic_low_confidence_auto": int(
            quality_policy.get("max_semantic_low_confidence_auto", 0)
        ),
        "max_fallback_auto_migrate": int(
            quality_policy.get("max_fallback_auto_migrate", 0)
        ),
        "min_structured_section_completeness": float(
            quality_policy.get("min_structured_section_completeness", 0.95)
        ),
        "fail_on_semantic_gate": bool(
            quality_policy.get("fail_on_semantic_gate", True)
        ),
    }


def _extract_legacy_entry_block(target_text: str, source_rel: str) -> str | None:
    marker = dl.source_marker(source_rel)
    start = target_text.find(marker)
    if start < 0:
        return None
    end = target_text.find("\n## Legacy Source `", start + len(marker))
    if end < 0:
        end = len(target_text)
    return target_text[start:end]


def _compute_structured_presence_ratio(entry_block: str) -> float:
    required = len(STRUCTURED_SECTION_MARKER_GROUPS)
    if required == 0:
        return 1.0
    hit = 0
    for _, markers in STRUCTURED_SECTION_MARKER_GROUPS:
        if any(marker in entry_block for marker in markers):
            hit += 1
    return hit / required


def _load_semantic_report_entries(root: Path, settings: dict[str, Any]) -> list[dict[str, Any]]:
    report_rel = str(settings.get("semantic_report_path", "")).strip()
    if not report_rel:
        return []
    report_path = root / dl.normalize_rel(report_rel)
    report = load_json(report_path)
    if not isinstance(report, dict):
        return []
    entries = report.get("entries")
    if not isinstance(entries, list):
        return []
    out: list[dict[str, Any]] = []
    for item in entries:
        if isinstance(item, dict):
            out.append(item)
    return out


def evaluate_semantic_migration_quality(
    root: Path,
    policy: dict[str, Any],
) -> dict[str, Any]:
    settings = dl.resolve_legacy_settings(policy)
    semantic_settings = (
        settings.get("semantic")
        if isinstance(settings.get("semantic"), dict)
        else {}
    )
    enabled = bool(settings.get("enabled", False) and semantic_settings.get("enabled", False))
    thresholds = get_semantic_quality_thresholds(policy)
    result: dict[str, Any] = {
        "enabled": enabled,
        "thresholds": thresholds,
        "metrics": {
            "semantic_auto_migrate_count": 0,
            "semantic_manual_review_count": 0,
            "semantic_skip_count": 0,
            "fallback_auto_migrate_count": 0,
            "semantic_low_confidence_count": 0,
            "semantic_conflict_count": 0,
            "structured_section_completeness": 1.0,
            "missing_source_marker_auto_count": 0,
        },
        "low_confidence_auto_sources": [],
        "conflicts": [],
        "incomplete_sources": [],
        "missing_source_marker_auto_sources": [],
        "backlog": [],
    }
    if not enabled:
        return result

    semantic_entries = _load_semantic_report_entries(root, settings)
    decision_counter = Counter(
        str(item.get("decision"))
        for item in semantic_entries
        if isinstance(item.get("decision"), str)
    )
    result["metrics"]["semantic_auto_migrate_count"] = int(
        decision_counter.get("auto_migrate", 0)
    )
    result["metrics"]["semantic_manual_review_count"] = int(
        decision_counter.get("manual_review", 0)
    )
    result["metrics"]["semantic_skip_count"] = int(decision_counter.get("skip", 0))
    result["metrics"]["fallback_auto_migrate_count"] = sum(
        1
        for item in semantic_entries
        if str(item.get("decision")) == "auto_migrate"
        and (
            bool(item.get("fallback_auto_migrate", False))
            or str(item.get("decision_source")) == "fallback"
        )
    )

    semantic_by_source: dict[str, dict[str, Any]] = {}
    for item in semantic_entries:
        source_rel = item.get("source_path")
        if isinstance(source_rel, str) and source_rel.strip():
            semantic_by_source[dl.normalize_rel(source_rel)] = item

    registry_path = root / str(settings.get("registry_path", dl.DEFAULT_LEGACY_SETTINGS["registry_path"]))
    registry = dl.load_registry(registry_path)
    registry_entries = (
        registry.get("entries") if isinstance(registry.get("entries"), dict) else {}
    )

    auto_review_threshold = float(semantic_settings.get("review_threshold", 0.60))
    structured_ratios: list[float] = []
    conflicts: list[dict[str, Any]] = []
    low_confidence_auto: list[str] = []
    incomplete_sources: list[str] = []
    missing_marker_auto: list[str] = []
    backlog: list[dict[str, Any]] = []

    for source_rel, entry in registry_entries.items():
        if not isinstance(source_rel, str) or not isinstance(entry, dict):
            continue
        normalized_source = dl.normalize_rel(source_rel)
        semantic_entry = semantic_by_source.get(normalized_source)
        status = entry.get("status")
        target_rel = entry.get("target_path")
        decision_source = entry.get("decision_source")
        confidence = entry.get("confidence")

        if (
            status in {"migrated", "archived"}
            and isinstance(decision_source, str)
            and decision_source == "semantic"
            and isinstance(confidence, (int, float))
            and float(confidence) < auto_review_threshold
        ):
            low_confidence_auto.append(normalized_source)
            backlog.append(
                {
                    "source_path": normalized_source,
                    "reason": "low_confidence_auto_migration",
                    "confidence": float(confidence),
                    "review_threshold": auto_review_threshold,
                }
            )

        if isinstance(target_rel, str) and target_rel.strip() and status in {"migrated", "archived"}:
            target_abs = root / dl.normalize_rel(target_rel)
            if target_abs.exists():
                target_text = target_abs.read_text(encoding="utf-8", errors="replace")
                entry_block = _extract_legacy_entry_block(target_text, normalized_source)
                if entry_block is None:
                    if isinstance(decision_source, str) and decision_source == "semantic":
                        missing_marker_auto.append(normalized_source)
                        backlog.append(
                            {
                                "source_path": normalized_source,
                                "reason": "missing_source_marker_auto",
                                "target_path": dl.normalize_rel(target_rel),
                            }
                        )
                else:
                    ratio = _compute_structured_presence_ratio(entry_block)
                    structured_ratios.append(ratio)
                    if ratio < 1.0:
                        incomplete_sources.append(normalized_source)
                        backlog.append(
                            {
                                "source_path": normalized_source,
                                "reason": "structured_section_incomplete",
                                "target_path": dl.normalize_rel(target_rel),
                                "completeness": round(ratio, 4),
                            }
                        )

        if semantic_entry is not None:
            semantic_category = semantic_entry.get("category")
            registry_category = entry.get("category")
            if (
                isinstance(semantic_category, str)
                and isinstance(registry_category, str)
                and semantic_category.strip()
                and registry_category.strip()
                and semantic_category.strip() != registry_category.strip()
            ):
                conflicts.append(
                    {
                        "source_path": normalized_source,
                        "kind": "category_mismatch",
                        "semantic_category": semantic_category.strip(),
                        "registry_category": registry_category.strip(),
                    }
                )
                backlog.append(
                    {
                        "source_path": normalized_source,
                        "reason": "semantic_conflict",
                        "kind": "category_mismatch",
                    }
                )

    result["metrics"]["semantic_low_confidence_count"] = len(low_confidence_auto)
    result["metrics"]["semantic_conflict_count"] = len(conflicts)
    result["metrics"]["missing_source_marker_auto_count"] = len(missing_marker_auto)
    result["metrics"]["structured_section_completeness"] = (
        round(sum(structured_ratios) / len(structured_ratios), 4)
        if structured_ratios
        else 1.0
    )
    result["low_confidence_auto_sources"] = low_confidence_auto
    result["conflicts"] = conflicts
    result["incomplete_sources"] = incomplete_sources
    result["missing_source_marker_auto_sources"] = missing_marker_auto
    result["backlog"] = backlog
    return result


def parse_citation_token(token: str) -> str | None:
    if not isinstance(token, str):
        return None
    prefix = "evidence://"
    if not token.startswith(prefix):
        return None
    evidence_type = token[len(prefix) :].strip()
    if not evidence_type:
        return None
    return evidence_type


def get_claim_citations(claim: dict[str, Any]) -> list[str]:
    citations = claim.get("citations")
    if isinstance(citations, list):
        return [str(value) for value in citations if isinstance(value, str) and value]
    citation = claim.get("citation")
    if isinstance(citation, str) and citation:
        return [citation]
    return []


def compute_citation_issues(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for claim in claims:
        status = claim.get("status")
        if status != "supported":
            continue
        claim_id = claim.get("claim_id")
        claim_label = claim_id if isinstance(claim_id, str) and claim_id else "UNKNOWN"
        citations = get_claim_citations(claim)
        evidence_items = claim.get("evidence")
        evidence_types = {
            item.get("type")
            for item in (evidence_items if isinstance(evidence_items, list) else [])
            if isinstance(item, dict) and isinstance(item.get("type"), str)
        }

        if not citations:
            issues.append(
                {
                    "claim_id": claim_label,
                    "issue": "missing_citation",
                    "detail": "supported claim is missing citation token",
                }
            )
            continue

        for token in citations:
            evidence_type = parse_citation_token(token)
            if evidence_type is None:
                issues.append(
                    {
                        "claim_id": claim_label,
                        "issue": "invalid_citation",
                        "detail": f"unparseable citation token: {token}",
                    }
                )
                continue
            if evidence_type not in evidence_types:
                issues.append(
                    {
                        "claim_id": claim_label,
                        "issue": "untraceable_citation",
                        "detail": f"citation not present in evidence payload: {token}",
                    }
                )
    return issues


def compute_conflicts(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, set[str]] = {}
    for claim in claims:
        claim_id = claim.get("claim_id")
        statement = claim.get("statement")
        if not isinstance(claim_id, str) or not claim_id.strip():
            continue
        if not isinstance(statement, str):
            continue
        by_id.setdefault(claim_id.strip(), set()).add(statement.strip())

    conflicts: list[dict[str, Any]] = []
    for claim_id, statements in sorted(by_id.items()):
        if len(statements) > 1:
            conflicts.append(
                {
                    "claim_id": claim_id,
                    "statement_count": len(statements),
                    "statements": sorted(statements),
                }
            )
    return conflicts


def _extract_heading_block(content: str, markers: list[str]) -> list[str]:
    marker_set = {marker.strip() for marker in markers if isinstance(marker, str) and marker.strip()}
    if not marker_set:
        return []

    lines = content.splitlines()
    for idx, line in enumerate(lines):
        if line.strip() not in marker_set:
            continue
        end = idx + 1
        while end < len(lines):
            if lines[end].lstrip().startswith("#"):
                break
            end += 1
        return lines[idx + 1 : end]
    return []


def _count_items(lines: list[str]) -> int:
    count = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        count += 1
    return count


def evaluate_progressive_disclosure_quality(
    root: Path,
    spec_data: dict[str, Any],
    progressive_settings: dict[str, Any],
) -> dict[str, Any]:
    enabled = bool(progressive_settings.get("enabled", False))
    required_slots = [
        str(slot).strip()
        for slot in (progressive_settings.get("required_slots") or [])
        if isinstance(slot, str) and str(slot).strip()
    ]
    if not required_slots:
        required_slots = ["summary", "key_facts", "next_steps"]

    result: dict[str, Any] = {
        "enabled": enabled,
        "required_slots": required_slots,
        "settings": {
            "summary_max_chars": int(progressive_settings.get("summary_max_chars", 160)),
            "max_key_facts": int(progressive_settings.get("max_key_facts", 5)),
            "max_next_steps": int(progressive_settings.get("max_next_steps", 3)),
            "fail_on_missing_slots": bool(
                progressive_settings.get("fail_on_missing_slots", True)
            ),
        },
        "metrics": {
            "progressive_candidate_sections": 0,
            "progressive_slot_completeness": 1.0,
            "next_step_presence": 1.0,
            "section_verbosity_over_budget_count": 0,
            "progressive_missing_slots_count": 0,
        },
        "findings": [],
    }
    if not enabled:
        return result

    documents = (
        spec_data.get("documents")
        if isinstance(spec_data, dict) and isinstance(spec_data.get("documents"), list)
        else []
    )
    doc_paths = [
        dt.normalize_rel(str(doc.get("path")))
        for doc in documents
        if isinstance(doc, dict)
        and isinstance(doc.get("path"), str)
        and str(doc.get("path")).strip()
        and dt.normalize_rel(str(doc.get("path"))).endswith(".md")
    ]

    slot_totals = 0
    slot_hits = 0
    next_step_hits = 0
    over_budget_count = 0
    missing_slots_count = 0
    findings: list[dict[str, Any]] = []
    summary_max_chars = int(result["settings"]["summary_max_chars"])
    max_key_facts = int(result["settings"]["max_key_facts"])
    max_next_steps = int(result["settings"]["max_next_steps"])

    for rel_path in sorted(set(doc_paths)):
        abs_path = root / rel_path
        if not abs_path.exists() or not abs_path.is_file():
            continue
        text = abs_path.read_text(encoding="utf-8", errors="replace")
        slot_blocks = {
            slot: _extract_heading_block(text, PROGRESSIVE_SLOT_MARKERS.get(slot, []))
            for slot in required_slots
        }
        present_slots = [slot for slot in required_slots if slot_blocks.get(slot)]
        if not present_slots:
            continue

        slot_totals += len(required_slots)
        slot_hits += len(present_slots)
        if "next_steps" in present_slots:
            next_step_hits += 1

        missing = [slot for slot in required_slots if slot not in present_slots]
        missing_slots_count += len(missing)

        verbosity_reasons: list[str] = []
        summary_block = slot_blocks.get("summary") or []
        if summary_block:
            summary_text = " ".join(
                part.strip().lstrip("-*+").strip()
                for part in summary_block
                if part.strip()
            )
            if len(summary_text) > summary_max_chars:
                over_budget_count += 1
                verbosity_reasons.append(
                    f"summary chars {len(summary_text)}>{summary_max_chars}"
                )

        key_facts_block = slot_blocks.get("key_facts") or []
        key_facts_count = _count_items(key_facts_block)
        if key_facts_count > max_key_facts:
            over_budget_count += 1
            verbosity_reasons.append(
                f"key_facts count {key_facts_count}>{max_key_facts}"
            )

        next_steps_block = slot_blocks.get("next_steps") or []
        next_steps_count = _count_items(next_steps_block)
        if next_steps_count > max_next_steps:
            over_budget_count += 1
            verbosity_reasons.append(
                f"next_steps count {next_steps_count}>{max_next_steps}"
            )

        findings.append(
            {
                "path": rel_path,
                "present_slots": present_slots,
                "missing_slots": missing,
                "verbosity_issues": verbosity_reasons,
            }
        )

    candidate_sections = len(findings)
    completeness = 1.0 if slot_totals == 0 else round(slot_hits / slot_totals, 4)
    next_step_presence = (
        1.0 if candidate_sections == 0 else round(next_step_hits / candidate_sections, 4)
    )
    result["metrics"] = {
        "progressive_candidate_sections": candidate_sections,
        "progressive_slot_completeness": completeness,
        "next_step_presence": next_step_presence,
        "section_verbosity_over_budget_count": over_budget_count,
        "progressive_missing_slots_count": missing_slots_count,
    }
    result["findings"] = findings
    return result


def evaluate_quality(
    root: Path,
    policy: dict[str, Any],
    facts: dict[str, Any] | None,
    spec_path: Path,
    evidence_map_path: Path | None = None,
) -> dict[str, Any]:
    spec_data, spec_errors, spec_warnings = doc_spec.load_spec(spec_path)
    if spec_data is None:
        raise ValueError(f"doc-spec missing: {spec_path}")
    if spec_errors:
        raise ValueError("doc-spec invalid: " + ", ".join(spec_errors))

    evidence_map = None
    if evidence_map_path:
        evidence_map = load_json(evidence_map_path)
    documents = None
    if evidence_map and isinstance(evidence_map.get("documents"), list):
        documents = evidence_map.get("documents")
    if documents is None:
        documents = build_evidence_map(spec_data, facts, root)

    claims = flatten_claims(documents)
    total_claims = len(claims)
    supported = sum(1 for c in claims if c.get("status") == "supported")
    unknown = sum(1 for c in claims if c.get("status") == "unknown")
    missing = sum(1 for c in claims if c.get("status") == "missing")
    unresolved_todo = sum(
        1
        for c in claims
        if c.get("status") == "missing"
        or (
            isinstance(c.get("statement"), str)
            and "TODO" in c.get("statement")
        )
    )
    unknown_text = sum(
        1
        for c in claims
        if isinstance(c.get("statement"), str)
        and "UNKNOWN" in c.get("statement")
    )
    evidence_coverage = 1.0 if total_claims == 0 else supported / total_claims

    conflicts = compute_conflicts(claims)
    citation_issues = compute_citation_issues(claims)
    facts_age_days = get_facts_age_days(facts)
    semantic_quality = evaluate_semantic_migration_quality(root, policy)
    progressive_settings = dt.resolve_progressive_disclosure_settings(policy)
    progressive_quality = evaluate_progressive_disclosure_quality(
        root, spec_data, progressive_settings
    )

    quality_policy = policy.get("doc_quality_gates")
    quality_policy = quality_policy if isinstance(quality_policy, dict) else {}
    enabled = bool(quality_policy.get("enabled", False))
    semantic_thresholds = get_semantic_quality_thresholds(policy)

    thresholds = {
        "min_evidence_coverage": quality_policy.get("min_evidence_coverage", 0.0),
        "max_conflicts": quality_policy.get("max_conflicts", 0),
        "max_unknown_claims": quality_policy.get("max_unknown_claims", 0),
        "max_unresolved_todo": quality_policy.get("max_unresolved_todo", 0),
        "max_stale_metrics_days": quality_policy.get("max_stale_metrics_days", 0),
        "max_semantic_conflicts": semantic_thresholds["max_semantic_conflicts"],
        "max_semantic_low_confidence_auto": semantic_thresholds[
            "max_semantic_low_confidence_auto"
        ],
        "max_fallback_auto_migrate": semantic_thresholds[
            "max_fallback_auto_migrate"
        ],
        "min_structured_section_completeness": semantic_thresholds[
            "min_structured_section_completeness"
        ],
        "min_progressive_slot_completeness": quality_policy.get(
            "min_progressive_slot_completeness", 0.95
        ),
        "min_next_step_presence": quality_policy.get("min_next_step_presence", 1.0),
        "max_section_verbosity_over_budget": quality_policy.get(
            "max_section_verbosity_over_budget", 0
        ),
    }

    failed_checks: list[str] = []
    if enabled:
        if evidence_coverage < float(thresholds["min_evidence_coverage"]):
            failed_checks.append("min_evidence_coverage")
        if len(conflicts) > int(thresholds["max_conflicts"]):
            failed_checks.append("max_conflicts")
        if citation_issues:
            failed_checks.append("citation_integrity")
        if unknown > int(thresholds["max_unknown_claims"]):
            failed_checks.append("max_unknown_claims")
        if unresolved_todo > int(thresholds["max_unresolved_todo"]):
            failed_checks.append("max_unresolved_todo")
        max_stale = thresholds["max_stale_metrics_days"]
        if isinstance(max_stale, int) and max_stale > 0:
            if facts_age_days is None or facts_age_days > max_stale:
                failed_checks.append("max_stale_metrics_days")
        if semantic_quality.get("enabled", False):
            semantic_metrics = semantic_quality.get("metrics") or {}
            if (
                int(semantic_metrics.get("semantic_conflict_count", 0))
                > int(thresholds["max_semantic_conflicts"])
            ):
                failed_checks.append("max_semantic_conflicts")
            if (
                int(semantic_metrics.get("semantic_low_confidence_count", 0))
                > int(thresholds["max_semantic_low_confidence_auto"])
            ):
                failed_checks.append("max_semantic_low_confidence_auto")
            if (
                int(semantic_metrics.get("fallback_auto_migrate_count", 0))
                > int(thresholds["max_fallback_auto_migrate"])
            ):
                failed_checks.append("max_fallback_auto_migrate")
            if (
                float(semantic_metrics.get("structured_section_completeness", 1.0))
                < float(thresholds["min_structured_section_completeness"])
            ):
                failed_checks.append("min_structured_section_completeness")
            if int(semantic_metrics.get("missing_source_marker_auto_count", 0)) > 0:
                failed_checks.append("semantic_source_marker_integrity")
        if progressive_quality.get("enabled", False):
            progressive_metrics = progressive_quality.get("metrics") or {}
            if float(progressive_metrics.get("progressive_slot_completeness", 1.0)) < float(
                thresholds["min_progressive_slot_completeness"]
            ):
                failed_checks.append("min_progressive_slot_completeness")
            if float(progressive_metrics.get("next_step_presence", 1.0)) < float(
                thresholds["min_next_step_presence"]
            ):
                failed_checks.append("min_next_step_presence")
            if int(
                progressive_metrics.get("section_verbosity_over_budget_count", 0)
            ) > int(thresholds["max_section_verbosity_over_budget"]):
                failed_checks.append("max_section_verbosity_over_budget")
            if progressive_quality.get("settings", {}).get(
                "fail_on_missing_slots", True
            ) and int(progressive_metrics.get("progressive_missing_slots_count", 0)) > 0:
                failed_checks.append("progressive_required_slots")

    report = {
        "generated_at": utc_now(),
        "root": str(root),
        "enabled": enabled,
        "doc_spec": {
            "errors": spec_errors,
            "warnings": spec_warnings,
        },
        "metrics": {
            "total_claims": total_claims,
            "supported_claims": supported,
            "unknown_claims": unknown,
            "missing_claims": missing,
            "unknown_text": unknown_text,
            "unresolved_todo": unresolved_todo,
            "evidence_coverage": evidence_coverage,
            "conflicts": len(conflicts),
            "citation_issues": len(citation_issues),
            "facts_age_days": facts_age_days,
            "semantic_auto_migrate_count": (
                (semantic_quality.get("metrics") or {}).get(
                    "semantic_auto_migrate_count", 0
                )
            ),
            "semantic_manual_review_count": (
                (semantic_quality.get("metrics") or {}).get(
                    "semantic_manual_review_count", 0
                )
            ),
            "semantic_skip_count": (
                (semantic_quality.get("metrics") or {}).get(
                    "semantic_skip_count", 0
                )
            ),
            "fallback_auto_migrate_count": (
                (semantic_quality.get("metrics") or {}).get(
                    "fallback_auto_migrate_count", 0
                )
            ),
            "semantic_low_confidence_count": (
                (semantic_quality.get("metrics") or {}).get(
                    "semantic_low_confidence_count", 0
                )
            ),
            "semantic_conflict_count": (
                (semantic_quality.get("metrics") or {}).get(
                    "semantic_conflict_count", 0
                )
            ),
            "structured_section_completeness": (
                (semantic_quality.get("metrics") or {}).get(
                    "structured_section_completeness", 1.0
                )
            ),
            "semantic_missing_source_marker_auto_count": (
                (semantic_quality.get("metrics") or {}).get(
                    "missing_source_marker_auto_count", 0
                )
            ),
            "progressive_candidate_sections": (
                (progressive_quality.get("metrics") or {}).get(
                    "progressive_candidate_sections", 0
                )
            ),
            "progressive_slot_completeness": (
                (progressive_quality.get("metrics") or {}).get(
                    "progressive_slot_completeness", 1.0
                )
            ),
            "next_step_presence": (
                (progressive_quality.get("metrics") or {}).get(
                    "next_step_presence", 1.0
                )
            ),
            "section_verbosity_over_budget_count": (
                (progressive_quality.get("metrics") or {}).get(
                    "section_verbosity_over_budget_count", 0
                )
            ),
            "progressive_missing_slots_count": (
                (progressive_quality.get("metrics") or {}).get(
                    "progressive_missing_slots_count", 0
                )
            ),
        },
        "conflicts": conflicts,
        "citation_issues": citation_issues,
        "semantic": semantic_quality,
        "progressive": progressive_quality,
        "gate": {
            "status": "failed" if enabled and failed_checks else "passed",
            "failed_checks": failed_checks,
            "thresholds": thresholds,
        },
    }
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate doc quality gates using doc-spec and evidence map."
    )
    parser.add_argument("--root", required=True, help="Repository root")
    parser.add_argument("--policy", default="docs/.doc-policy.json", help="Policy path")
    parser.add_argument("--spec", default="docs/.doc-spec.json", help="Doc spec path")
    parser.add_argument(
        "--facts", default="docs/.repo-facts.json", help="Facts JSON path"
    )
    parser.add_argument(
        "--evidence-map",
        default="docs/.doc-evidence-map.json",
        help="Evidence map JSON path",
    )
    parser.add_argument(
        "--output",
        default="docs/.doc-quality-report.json",
        help="Output JSON report path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"[ERROR] Invalid root path: {root}")

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
    evidence_map_path = (
        (root / args.evidence_map).resolve()
        if not Path(args.evidence_map).is_absolute()
        else Path(args.evidence_map)
    )
    output_path = (
        (root / args.output).resolve()
        if not Path(args.output).is_absolute()
        else Path(args.output)
    )

    policy = load_json(policy_path) or {}
    facts = load_json(facts_path)
    report = evaluate_quality(
        root,
        policy,
        facts,
        spec_path,
        evidence_map_path=evidence_map_path,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")

    status = report["gate"]["status"]
    print(f"[OK] Wrote quality report to {output_path}")
    print(
        "[INFO] gate="
        f"{status} coverage={report['metrics']['evidence_coverage']:.2f} "
        f"unknown={report['metrics']['unknown_claims']} conflicts={report['metrics']['conflicts']}"
    )

    fail_on_quality = bool(
        policy.get("doc_quality_gates", {}).get("fail_on_quality_gate", True)
        if isinstance(policy.get("doc_quality_gates"), dict)
        else True
    )
    if report["enabled"] and status != "passed" and fail_on_quality:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
