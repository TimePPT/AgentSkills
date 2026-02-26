#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import doc_capabilities as dc

DEFAULT_SEMANTIC_ACTIONS = {
    "update_section": True,
    "fill_claim": True,
    "semantic_rewrite": True,
    "migrate_legacy": True,
    "merge_docs": True,
    "split_doc": True,
    "agents_generate": True,
}

DEFAULT_SEMANTIC_GENERATION_SETTINGS = {
    "enabled": True,
    "mode": "hybrid",
    "prefer_agent_semantic_first": True,
    "require_semantic_attempt": True,
    "source": "invoking_agent",
    "runtime_report_path": "docs/.semantic-runtime-report.json",
    "fail_closed": True,
    "allow_fallback_template": True,
    "allow_external_llm_api": False,
    "max_output_chars_per_section": 4000,
    "required_evidence_prefixes": ["repo_scan.", "runbook.", "semantic_report."],
    "deny_paths": ["docs/adr/**"],
    "actions": deepcopy(DEFAULT_SEMANTIC_ACTIONS),
}

SUPPORTED_SEMANTIC_MODES = {"deterministic", "hybrid", "agent_strict"}
SUPPORTED_ENTRY_STATUS = {"ok", "manual_review"}


def normalize_rel(path_str: str) -> str:
    return dc.normalize_rel(path_str)


def _normalize_string_list(value: Any, *, normalize_paths: bool) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text:
            continue
        out.append(normalize_rel(text) if normalize_paths else text)
    deduped: list[str] = []
    seen: set[str] = set()
    for item in out:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _normalize_positive_int(value: Any, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    if parsed <= 0:
        return fallback
    return parsed


def _normalize_split_outputs(
    value: Any,
    *,
    entry_index: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    if value is None:
        return [], warnings
    if not isinstance(value, list):
        return [], [f"entry[{entry_index}] split_outputs ignored: expected list"]

    outputs: list[dict[str, Any]] = []
    for split_index, item in enumerate(value):
        if not isinstance(item, dict):
            warnings.append(
                f"entry[{entry_index}] split_outputs[{split_index}] ignored: expected object"
            )
            continue
        path = item.get("path")
        content = item.get("content")
        if not isinstance(path, str) or not path.strip():
            warnings.append(
                f"entry[{entry_index}] split_outputs[{split_index}] ignored: missing path"
            )
            continue
        if not isinstance(content, str) or not content.strip():
            warnings.append(
                f"entry[{entry_index}] split_outputs[{split_index}] ignored: missing content"
            )
            continue
        normalized_item: dict[str, Any] = {
            "path": normalize_rel(path.strip()),
            "content": content.strip(),
        }
        title = item.get("title")
        if isinstance(title, str) and title.strip():
            normalized_item["title"] = title.strip()
        source_paths = _normalize_string_list(
            item.get("source_paths"), normalize_paths=True
        )
        if source_paths:
            normalized_item["source_paths"] = source_paths
        outputs.append(normalized_item)
    return outputs, warnings


def _normalize_actions(value: Any) -> dict[str, bool]:
    settings = dict(DEFAULT_SEMANTIC_ACTIONS)
    if not isinstance(value, dict):
        return settings
    for action_type in DEFAULT_SEMANTIC_ACTIONS:
        if action_type in value:
            settings[action_type] = bool(value.get(action_type))
    return settings


def resolve_semantic_generation_settings(policy: dict[str, Any] | None) -> dict[str, Any]:
    raw = (
        policy.get("semantic_generation")
        if isinstance(policy, dict) and isinstance(policy.get("semantic_generation"), dict)
        else {}
    )
    settings = deepcopy(DEFAULT_SEMANTIC_GENERATION_SETTINGS)
    if not raw:
        return settings

    settings["enabled"] = bool(raw.get("enabled", settings["enabled"]))
    mode = str(raw.get("mode", settings["mode"])).strip()
    settings["mode"] = mode if mode in SUPPORTED_SEMANTIC_MODES else settings["mode"]
    settings["prefer_agent_semantic_first"] = bool(
        raw.get(
            "prefer_agent_semantic_first",
            settings["prefer_agent_semantic_first"],
        )
    )
    settings["require_semantic_attempt"] = bool(
        raw.get("require_semantic_attempt", settings["require_semantic_attempt"])
    )
    source = str(raw.get("source", settings["source"])).strip()
    settings["source"] = source or settings["source"]
    runtime_report_path = str(
        raw.get("runtime_report_path", settings["runtime_report_path"])
    ).strip()
    settings["runtime_report_path"] = (
        normalize_rel(runtime_report_path)
        if runtime_report_path
        else settings["runtime_report_path"]
    )
    settings["fail_closed"] = bool(raw.get("fail_closed", settings["fail_closed"]))
    settings["allow_fallback_template"] = bool(
        raw.get("allow_fallback_template", settings["allow_fallback_template"])
    )
    settings["allow_external_llm_api"] = bool(
        raw.get("allow_external_llm_api", settings["allow_external_llm_api"])
    )
    settings["max_output_chars_per_section"] = _normalize_positive_int(
        raw.get(
            "max_output_chars_per_section", settings["max_output_chars_per_section"]
        ),
        int(settings["max_output_chars_per_section"]),
    )
    required_evidence_prefixes = _normalize_string_list(
        raw.get("required_evidence_prefixes"), normalize_paths=False
    )
    if required_evidence_prefixes:
        settings["required_evidence_prefixes"] = required_evidence_prefixes
    deny_paths = _normalize_string_list(raw.get("deny_paths"), normalize_paths=True)
    if deny_paths:
        settings["deny_paths"] = deny_paths
    settings["actions"] = _normalize_actions(raw.get("actions"))
    return settings


def should_attempt_runtime_semantics(action_type: str, settings: dict[str, Any]) -> bool:
    if not settings.get("enabled", False):
        return False
    if settings.get("mode") == "deterministic":
        return False
    if not settings.get("prefer_agent_semantic_first", True):
        return False
    actions = settings.get("actions")
    if not isinstance(actions, dict):
        return False
    return bool(actions.get(action_type, False))


def runtime_semantic_attempt_required(action_type: str, settings: dict[str, Any]) -> bool:
    actions = settings.get("actions")
    if not isinstance(actions, dict):
        return False
    if not bool(settings.get("enabled", False)):
        return False
    if settings.get("mode") == "deterministic":
        return False
    if not bool(actions.get(action_type, False)):
        return False
    return bool(settings.get("require_semantic_attempt", True))


def _normalize_runtime_entry(
    raw: dict[str, Any],
    *,
    entry_index: int,
    max_output_chars_per_section: int,
) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    path = raw.get("path")
    if not isinstance(path, str) or not path.strip():
        path = raw.get("doc_path")
    if not isinstance(path, str) or not path.strip():
        return None, [f"entry[{entry_index}] missing path/doc_path"]

    normalized_path = normalize_rel(path.strip())
    if not normalized_path:
        return None, [f"entry[{entry_index}] path invalid"]

    entry: dict[str, Any] = {
        "path": normalized_path,
        "entry_id": str(raw.get("entry_id", f"runtime-{entry_index:04d}")),
    }

    action_type: str | None = None
    for field in ("section_id", "claim_id", "action_type"):
        value = raw.get(field)
        if isinstance(value, str) and value.strip():
            normalized_value = value.strip()
            entry[field] = normalized_value
            if field == "action_type":
                action_type = normalized_value

    status = raw.get("status", "ok")
    if isinstance(status, str):
        status = status.strip() or "ok"
    else:
        status = "ok"
    if status not in SUPPORTED_ENTRY_STATUS:
        warnings.append(
            f"entry[{entry_index}] status unsupported: {status}; fallback to manual_review"
        )
        status = "manual_review"
    entry["status"] = status

    slots_raw = raw.get("slots")
    slots: dict[str, Any] = {}
    if slots_raw is not None:
        if not isinstance(slots_raw, dict):
            warnings.append(f"entry[{entry_index}] slots ignored: expected object")
        else:
            summary_raw = slots_raw.get("summary")
            if summary_raw is not None:
                if isinstance(summary_raw, str) and summary_raw.strip():
                    slots["summary"] = summary_raw.strip()
                else:
                    warnings.append(
                        f"entry[{entry_index}] slots.summary ignored: expected non-empty string"
                    )

            key_facts_raw = slots_raw.get("key_facts")
            if key_facts_raw is not None:
                if isinstance(key_facts_raw, list):
                    key_facts = _normalize_string_list(key_facts_raw, normalize_paths=False)
                    if key_facts:
                        slots["key_facts"] = key_facts
                    else:
                        warnings.append(
                            f"entry[{entry_index}] slots.key_facts ignored: empty list"
                        )
                else:
                    warnings.append(
                        f"entry[{entry_index}] slots.key_facts ignored: expected list"
                    )

            next_steps_raw = slots_raw.get("next_steps")
            if next_steps_raw is not None:
                if isinstance(next_steps_raw, list):
                    next_steps = _normalize_string_list(next_steps_raw, normalize_paths=False)
                    if next_steps:
                        slots["next_steps"] = next_steps
                    else:
                        warnings.append(
                            f"entry[{entry_index}] slots.next_steps ignored: empty list"
                        )
                else:
                    warnings.append(
                        f"entry[{entry_index}] slots.next_steps ignored: expected list"
                    )

    content_raw = raw.get("content")
    statement_raw = raw.get("statement")
    has_split_outputs = isinstance(raw.get("split_outputs"), list) and bool(
        raw.get("split_outputs")
    )
    if content_raw is None and statement_raw is None and not slots and not has_split_outputs:
        return None, [f"entry[{entry_index}] requires content or statement or slots"]

    content: str = ""
    if content_raw is not None:
        if not isinstance(content_raw, str):
            return None, [f"entry[{entry_index}] content must be string"]
        content = content_raw
        if len(content) > max_output_chars_per_section:
            warnings.append(
                f"entry[{entry_index}] content exceeds max_output_chars_per_section; truncated"
            )
            content = content[:max_output_chars_per_section]

    statement: str = ""
    if statement_raw is not None:
        if not isinstance(statement_raw, str):
            return None, [f"entry[{entry_index}] statement must be string"]
        statement = statement_raw.strip()
        if len(statement) > max_output_chars_per_section:
            warnings.append(
                f"entry[{entry_index}] statement exceeds max_output_chars_per_section; truncated"
            )
            statement = statement[:max_output_chars_per_section]

    if action_type == "fill_claim" and not statement and content.strip():
        statement = content.strip()
        warnings.append(
            f"entry[{entry_index}] fill_claim missing statement; fallback to content"
        )
    if not content and statement:
        content = statement

    if content:
        entry["content"] = content
    if statement:
        entry["statement"] = statement
    if slots:
        entry["slots"] = slots

    citations = _normalize_string_list(raw.get("citations"), normalize_paths=False)
    if citations:
        entry["citations"] = citations
    risk_notes = _normalize_string_list(raw.get("risk_notes"), normalize_paths=False)
    if risk_notes:
        entry["risk_notes"] = risk_notes

    source_paths = _normalize_string_list(raw.get("source_paths"), normalize_paths=True)
    if source_paths:
        entry["source_paths"] = source_paths
    target_paths = _normalize_string_list(raw.get("target_paths"), normalize_paths=True)
    if target_paths:
        entry["target_paths"] = target_paths
    index_links = _normalize_string_list(raw.get("index_links"), normalize_paths=True)
    if index_links:
        entry["index_links"] = index_links

    evidence_map_raw = raw.get("evidence_map")
    if evidence_map_raw is not None:
        if not isinstance(evidence_map_raw, dict):
            warnings.append(f"entry[{entry_index}] evidence_map ignored: expected object")
        else:
            normalized_map: dict[str, list[str]] = {}
            for source, evidence in evidence_map_raw.items():
                if not isinstance(source, str) or not source.strip():
                    continue
                normalized_evidence = _normalize_string_list(
                    evidence, normalize_paths=False
                )
                normalized_map[normalize_rel(source.strip())] = normalized_evidence
            if normalized_map:
                entry["evidence_map"] = normalized_map

    split_outputs, split_warnings = _normalize_split_outputs(
        raw.get("split_outputs"),
        entry_index=entry_index,
    )
    warnings.extend(split_warnings)
    if split_outputs:
        entry["split_outputs"] = split_outputs

    return entry, warnings


def load_runtime_report(
    root: Path, settings: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    runtime_report_path = normalize_rel(str(settings.get("runtime_report_path", "")).strip())
    metadata: dict[str, Any] = {
        "enabled": bool(settings.get("enabled", False)),
        "mode": str(settings.get("mode", "deterministic")),
        "source": str(settings.get("source", "invoking_agent")),
        "runtime_report_path": runtime_report_path,
        "available": False,
        "entry_count": 0,
        "error": None,
        "warnings": [],
    }

    if not metadata["enabled"]:
        return [], metadata
    if not runtime_report_path:
        metadata["error"] = "runtime_report_path is empty"
        return [], metadata

    report_path = (root / runtime_report_path).resolve()
    if not report_path.exists():
        metadata["error"] = f"runtime report not found: {runtime_report_path}"
        return [], metadata

    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        metadata["error"] = f"runtime report unreadable: {exc}"
        return [], metadata
    if not isinstance(payload, dict):
        metadata["error"] = "runtime report root must be object"
        return [], metadata

    entries_raw = payload.get("entries")
    if not isinstance(entries_raw, list):
        metadata["error"] = "runtime report entries must be list"
        return [], metadata

    max_output_chars_per_section = _normalize_positive_int(
        settings.get("max_output_chars_per_section"),
        int(DEFAULT_SEMANTIC_GENERATION_SETTINGS["max_output_chars_per_section"]),
    )
    entries: list[dict[str, Any]] = []
    warnings: list[str] = []
    for entry_index, item in enumerate(entries_raw):
        if not isinstance(item, dict):
            warnings.append(f"entry[{entry_index}] ignored: entry must be object")
            continue
        normalized_entry, entry_warnings = _normalize_runtime_entry(
            item,
            entry_index=entry_index,
            max_output_chars_per_section=max_output_chars_per_section,
        )
        warnings.extend(entry_warnings)
        if normalized_entry is None:
            continue
        entries.append(normalized_entry)

    metadata["available"] = True
    metadata["entry_count"] = len(entries)
    metadata["warnings"] = warnings
    return entries, metadata


def _match_field_score(
    action_value: str | None, entry_value: str | None, *, weight: int
) -> int | None:
    if action_value:
        if entry_value:
            if entry_value != action_value:
                return None
            return weight
        return 1
    if entry_value:
        return -1
    return 0


def select_runtime_entry(
    action: dict[str, Any],
    entries: list[dict[str, Any]],
    settings: dict[str, Any],
) -> dict[str, Any] | None:
    action_type = str(action.get("type", "")).strip()
    if not should_attempt_runtime_semantics(action_type, settings):
        return None

    path = normalize_rel(str(action.get("path", "")).strip())
    if not path:
        return None

    section_id_raw = action.get("section_id")
    section_id = section_id_raw.strip() if isinstance(section_id_raw, str) and section_id_raw.strip() else None
    claim_id_raw = action.get("claim_id")
    claim_id = claim_id_raw.strip() if isinstance(claim_id_raw, str) and claim_id_raw.strip() else None

    best_score: int | None = None
    best_entry: dict[str, Any] | None = None
    for entry in entries:
        if entry.get("path") != path:
            continue

        entry_action = entry.get("action_type")
        if isinstance(entry_action, str) and entry_action.strip():
            if entry_action != action_type:
                continue
            action_score = 8
        else:
            action_score = 1

        section_score = _match_field_score(
            section_id,
            entry.get("section_id") if isinstance(entry.get("section_id"), str) else None,
            weight=4,
        )
        if section_score is None:
            continue
        claim_score = _match_field_score(
            claim_id,
            entry.get("claim_id") if isinstance(entry.get("claim_id"), str) else None,
            weight=4,
        )
        if claim_score is None:
            continue

        status_score = 2 if entry.get("status") == "ok" else 0
        score = action_score + section_score + claim_score + status_score
        if best_score is None or score > best_score:
            best_score = score
            best_entry = entry

    return deepcopy(best_entry) if isinstance(best_entry, dict) else None
