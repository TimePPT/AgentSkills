#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import fnmatch
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import doc_capabilities as dc  # noqa: E402
import doc_agents  # noqa: E402
import doc_legacy as dl  # noqa: E402
import doc_metadata as dm  # noqa: E402
import doc_semantic_runtime as dsr  # noqa: E402
import doc_topology as dt  # noqa: E402
import language_profiles as lp  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize(path_str: str) -> str:
    return str(Path(path_str)).replace("\\", "/")


def write_text(path: Path, content: str, dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, data: dict[str, Any], dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_json_mapping(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return data


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


def resolve_language_settings(root: Path, init_language: str | None) -> dict[str, Any]:
    policy_path = root / "docs/.doc-policy.json"
    policy_data = load_json_mapping(policy_path)

    policy_language_exists = bool(policy_data and isinstance(policy_data.get("language"), dict))
    effective_init_language = init_language

    if not policy_language_exists:
        inferred = infer_primary_language_from_docs(root)
        if not effective_init_language and inferred:
            effective_init_language = inferred

    return lp.resolve_language_settings(policy_data or {}, effective_init_language)


def ensure_policy_language(path: Path, language_settings: dict[str, Any], dry_run: bool) -> bool:
    current = load_json_mapping(path)
    if current is None:
        return False

    merged = lp.merge_language_into_policy(current, language_settings)
    if merged == current:
        return False

    write_json(path, merged, dry_run)
    return True


def append_missing_sections(
    rel_path: str,
    path: Path,
    dry_run: bool,
    template_profile: str,
) -> tuple[bool, list[str]]:
    rel = normalize(rel_path)
    required_sections = lp.get_required_sections(rel)
    if not required_sections:
        return False, []

    if not path.exists():
        write_text(path, lp.get_managed_template(rel, template_profile), dry_run)
        labels = [lp.get_section_heading(rel, section_id, template_profile) for section_id in required_sections]
        return True, labels

    text = path.read_text(encoding="utf-8")
    missing_sections: list[str] = []
    for section_id in required_sections:
        markers = lp.get_section_markers(rel, section_id)
        if not any(marker in text for marker in markers):
            missing_sections.append(section_id)

    if not missing_sections:
        return False, []

    updated = text.rstrip() + "\n\n"
    for section_id in missing_sections:
        updated += lp.get_section_text(rel, section_id, template_profile).rstrip() + "\n\n"

    write_text(path, updated.rstrip() + "\n", dry_run)
    labels = [lp.get_section_heading(rel, section_id, template_profile) for section_id in missing_sections]
    return True, labels


def section_exists(
    text: str,
    rel_path: str,
    section_id: str,
    template_profile: str,
    heading_override: str | None = None,
) -> bool:
    markers = lp.get_section_markers(rel_path, section_id)
    if any(marker in text for marker in markers):
        return True
    heading = heading_override or lp.get_section_heading(rel_path, section_id, template_profile)
    return bool(heading and heading in text)


def upsert_section(
    rel_path: str,
    path: Path,
    section_id: str,
    dry_run: bool,
    template_profile: str,
    section_heading: str | None = None,
) -> bool:
    rel = normalize(rel_path)
    if not isinstance(section_id, str) or not section_id.strip():
        return False
    section_id = section_id.strip()
    section_text = lp.get_section_text(rel, section_id, template_profile).strip()
    resolved_heading = (
        section_heading.strip()
        if isinstance(section_heading, str) and section_heading.strip()
        else lp.get_section_heading(rel, section_id, template_profile).strip()
    )
    if not resolved_heading:
        resolved_heading = section_id
    if not section_text:
        heading_line = resolved_heading if resolved_heading.startswith("#") else f"## {resolved_heading}"
        body = "TODO: 补充本节内容。" if template_profile == "zh-CN" else "TODO: Add section content."
        section_text = f"{heading_line}\n\n{body}"

    if not path.exists():
        base = lp.get_managed_template(rel, template_profile).rstrip()
        if section_exists(base, rel, section_id, template_profile, heading_override=resolved_heading):
            write_text(path, base + "\n", dry_run)
            return True
        write_text(path, base + "\n\n" + section_text + "\n", dry_run)
        return True

    text = path.read_text(encoding="utf-8")
    if section_exists(text, rel, section_id, template_profile, heading_override=resolved_heading):
        return False

    updated = text.rstrip() + "\n\n" + section_text + "\n"
    write_text(path, updated, dry_run)
    return True


def find_section_block_range(
    lines: list[str],
    rel_path: str,
    section_id: str,
    template_profile: str,
    section_heading: str | None = None,
) -> tuple[int, int] | None:
    markers = {
        marker.strip()
        for marker in lp.get_section_markers(rel_path, section_id)
        if isinstance(marker, str) and marker.strip()
    }
    resolved_heading = (
        section_heading.strip()
        if isinstance(section_heading, str) and section_heading.strip()
        else lp.get_section_heading(rel_path, section_id, template_profile).strip()
    )
    if resolved_heading:
        markers.add(resolved_heading)

    start_idx: int | None = None
    for idx, line in enumerate(lines):
        if line.strip() in markers:
            start_idx = idx
            break
    if start_idx is None:
        return None

    end_idx = len(lines)
    in_fence = False
    for idx in range(start_idx + 1, len(lines)):
        stripped = lines[idx].strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if re.match(r"^#\s+", stripped) or re.match(r"^##\s+", stripped):
            end_idx = idx
            break
    return start_idx, end_idx


def upsert_section_content(
    rel_path: str,
    path: Path,
    section_id: str,
    content: str,
    dry_run: bool,
    template_profile: str,
    section_heading: str | None = None,
) -> bool:
    if not isinstance(section_id, str) or not section_id.strip():
        return False
    if not isinstance(content, str) or not content.strip():
        return False

    section_id = section_id.strip()
    normalized_content = content.strip()
    upsert_section(
        rel_path,
        path,
        section_id,
        dry_run,
        template_profile,
        section_heading=section_heading,
    )
    if not path.exists():
        return False

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    section_range = find_section_block_range(
        lines,
        normalize(rel_path),
        section_id,
        template_profile,
        section_heading=section_heading,
    )
    if section_range is None:
        resolved_heading = (
            section_heading.strip()
            if isinstance(section_heading, str) and section_heading.strip()
            else lp.get_section_heading(
                normalize(rel_path), section_id, template_profile
            ).strip()
        )
        if not resolved_heading:
            return False
        heading_line = (
            resolved_heading
            if resolved_heading.startswith("#")
            else f"## {resolved_heading}"
        )
        updated = (
            text.rstrip()
            + "\n\n"
            + heading_line
            + "\n\n"
            + normalized_content
            + "\n"
        )
        if updated == text:
            return False
        write_text(path, updated, dry_run)
        return True

    start_idx, end_idx = section_range
    heading_line = lines[start_idx].rstrip()
    before = lines[:start_idx]
    after = lines[end_idx:]
    while after and not after[0].strip():
        after.pop(0)

    new_lines = before + [heading_line, ""] + normalized_content.splitlines()
    if after:
        new_lines += [""] + after
    updated = "\n".join(new_lines).rstrip() + "\n"
    if updated == text:
        return False
    write_text(path, updated, dry_run)
    return True


def upsert_claim_todo(
    rel_path: str,
    path: Path,
    section_id: str,
    claim_id: str,
    required_evidence_types: list[str],
    dry_run: bool,
    template_profile: str,
) -> bool:
    if not isinstance(claim_id, str) or not claim_id.strip():
        return False
    claim_id = claim_id.strip()

    upsert_section(rel_path, path, section_id, dry_run, template_profile)
    if not path.exists():
        return False

    text = path.read_text(encoding="utf-8")
    token = f"TODO(claim:{claim_id})"
    if token in text:
        return False

    evidence_types = ", ".join(required_evidence_types) if required_evidence_types else "UNKNOWN"
    if template_profile == "zh-CN":
        todo_line = (
            f"- {token}: 在 section `{section_id}` 补充证据类型 `{evidence_types}`，"
            "并更新对应段落。"
        )
    else:
        todo_line = (
            f"- {token}: Add evidence types `{evidence_types}` for section `{section_id}` "
            "and update the related content."
        )

    heading = "### Claim Follow-ups" if template_profile != "zh-CN" else "### Claim 待补项"
    updated = text.rstrip() + "\n\n" + heading + "\n\n" + todo_line + "\n"
    write_text(path, updated, dry_run)
    return True


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _dedupe_failures(failed_checks: list[str]) -> list[str]:
    deduped_failures: list[str] = []
    seen: set[str] = set()
    for failure in failed_checks:
        if failure in seen:
            continue
        seen.add(failure)
        deduped_failures.append(failure)
    return deduped_failures


def _normalize_runtime_slots(raw_slots: Any) -> dict[str, Any]:
    if not isinstance(raw_slots, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key, value in raw_slots.items():
        if not isinstance(key, str):
            continue
        slot_name = key.strip()
        if not slot_name:
            continue
        if isinstance(value, str):
            text = value.strip()
            if text:
                normalized[slot_name] = text
        elif isinstance(value, list):
            items = _normalize_string_list(value)
            if items:
                normalized[slot_name] = items
    return normalized


def _progressive_slot_heading(slot: str, template_profile: str) -> str:
    headings_zh = {
        "summary": "### 摘要",
        "key_facts": "### 关键事实",
        "next_steps": "### 下一步",
    }
    headings_en = {
        "summary": "### Summary",
        "key_facts": "### Key Facts",
        "next_steps": "### Next Steps",
    }
    table = headings_zh if template_profile == "zh-CN" else headings_en
    resolved = table.get(slot, slot.replace("_", " ").title())
    if resolved.startswith("#"):
        return resolved
    return f"### {resolved}"


def _resolve_progressive_slot_render_order(
    slots: dict[str, Any],
    required_slots: list[str] | None,
) -> list[str]:
    order: list[str] = []
    seen: set[str] = set()
    for slot in (required_slots or []):
        if slot in slots and slot not in seen:
            seen.add(slot)
            order.append(slot)
    for slot in slots:
        if slot not in seen:
            seen.add(slot)
            order.append(slot)
    return order


def render_progressive_slots_content(
    slots: dict[str, Any],
    template_profile: str,
    required_slots: list[str] | None = None,
) -> str:
    render_order = _resolve_progressive_slot_render_order(slots, required_slots)
    lines: list[str] = []
    for slot in render_order:
        slot_value = slots.get(slot)
        if isinstance(slot_value, str) and slot_value.strip():
            lines.extend(
                [
                    _progressive_slot_heading(slot, template_profile),
                    "",
                    slot_value.strip(),
                    "",
                ]
            )
            continue
        if isinstance(slot_value, list) and slot_value:
            lines.append(_progressive_slot_heading(slot, template_profile))
            lines.append("")
            if slot == "next_steps":
                lines.extend(
                    f"{index}. {item}"
                    for index, item in enumerate(slot_value, start=1)
                    if isinstance(item, str) and item.strip()
                )
            else:
                lines.extend(
                    f"- {item}"
                    for item in slot_value
                    if isinstance(item, str) and item.strip()
                )
            lines.append("")
    return "\n".join(lines).strip()


def _resolve_required_evidence_prefixes(semantic_settings: dict[str, Any]) -> list[str]:
    required_prefixes_raw = semantic_settings.get("required_evidence_prefixes")
    return [
        str(value).strip()
        for value in (
            required_prefixes_raw if isinstance(required_prefixes_raw, list) else []
        )
        if isinstance(value, str) and str(value).strip()
    ]


def _resolve_required_progressive_slots(progressive_settings: dict[str, Any]) -> list[str]:
    required_slots_raw = progressive_settings.get("required_slots")
    required_slots: list[str] = []
    seen: set[str] = set()
    for value in (
        required_slots_raw
        if isinstance(required_slots_raw, list)
        else ["summary", "key_facts", "next_steps"]
    ):
        if not isinstance(value, str):
            continue
        slot = str(value).strip()
        if not slot or slot in seen:
            continue
        seen.add(slot)
        required_slots.append(slot)
    if required_slots:
        return required_slots
    return ["summary", "key_facts", "next_steps"]


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


def render_claim_statement_line(
    claim_id: str,
    statement: str,
    citations: list[str],
    template_profile: str,
) -> str:
    token = f"CLAIM(claim:{claim_id})"
    citation_text = ", ".join(citations)
    if template_profile == "zh-CN":
        return f"- {token}: {statement} (citations: {citation_text})"
    return f"- {token}: {statement} (citations: {citation_text})"


def upsert_claim_statement(
    rel_path: str,
    path: Path,
    section_id: str,
    claim_id: str,
    statement: str,
    citations: list[str],
    dry_run: bool,
    template_profile: str,
) -> bool:
    if not isinstance(claim_id, str) or not claim_id.strip():
        return False
    if not isinstance(statement, str) or not statement.strip():
        return False
    normalized_citations = _normalize_string_list(citations)
    if not normalized_citations:
        return False

    claim_id = claim_id.strip()
    statement = statement.strip()
    upsert_section(rel_path, path, section_id, dry_run, template_profile)
    if not path.exists():
        return False

    text = path.read_text(encoding="utf-8")
    claim_token = f"CLAIM(claim:{claim_id})"
    todo_token = f"TODO(claim:{claim_id})"
    claim_line = render_claim_statement_line(
        claim_id, statement, normalized_citations, template_profile
    )
    lines = text.splitlines()

    for idx, line in enumerate(lines):
        if claim_token in line or todo_token in line:
            if line.strip() == claim_line.strip():
                return False
            lines[idx] = claim_line
            updated = "\n".join(lines).rstrip() + "\n"
            write_text(path, updated, dry_run)
            return True

    heading = "### Claim Statements" if template_profile != "zh-CN" else "### Claim 陈述"
    if heading in text:
        updated = text.rstrip() + "\n" + claim_line + "\n"
    else:
        updated = text.rstrip() + "\n\n" + heading + "\n\n" + claim_line + "\n"
    write_text(path, updated, dry_run)
    return True


def resolve_fill_claim_runtime_payload(
    action: dict[str, Any],
    runtime_entry: dict[str, Any] | None,
    semantic_settings: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(runtime_entry, dict):
        return None, ["runtime_entry_not_found"]

    failed_checks: list[str] = []
    if runtime_entry.get("status") != "ok":
        failed_checks.append("runtime_status_not_ok")

    statement = runtime_entry.get("statement")
    if not isinstance(statement, str) or not statement.strip():
        content = runtime_entry.get("content")
        if isinstance(content, str) and content.strip():
            statement = content.strip()
        else:
            statement = ""
    if not statement:
        failed_checks.append("missing_statement")

    citations = _normalize_string_list(runtime_entry.get("citations"))
    if not citations:
        failed_checks.append("missing_citations")

    citation_evidence_types: list[str] = []
    invalid_citations: list[str] = []
    for token in citations:
        evidence_type = parse_citation_token(token)
        if evidence_type is None:
            invalid_citations.append(token)
        else:
            citation_evidence_types.append(evidence_type)
    if invalid_citations:
        failed_checks.append("invalid_citation_token")

    required_prefixes = _resolve_required_evidence_prefixes(semantic_settings)
    if required_prefixes and citation_evidence_types:
        if any(
            not any(evidence.startswith(prefix) for prefix in required_prefixes)
            for evidence in citation_evidence_types
        ):
            failed_checks.append("citation_prefix_not_allowed")

    required_evidence_types = [
        str(value).strip()
        for value in (
            action.get("required_evidence_types")
            if isinstance(action.get("required_evidence_types"), list)
            else []
        )
        if isinstance(value, str) and str(value).strip()
    ]
    if required_evidence_types and citation_evidence_types:
        missing_required = [
            evidence
            for evidence in required_evidence_types
            if evidence not in citation_evidence_types
        ]
        if missing_required:
            failed_checks.append("missing_required_citations")

    deduped_failures = _dedupe_failures(failed_checks)
    if deduped_failures:
        return None, deduped_failures

    return {
        "statement": statement,
        "citations": citations,
    }, []


def resolve_update_section_runtime_payload(
    runtime_entry: dict[str, Any] | None,
    semantic_settings: dict[str, Any] | None = None,
    progressive_settings: dict[str, Any] | None = None,
    template_profile: str = "zh-CN",
) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(runtime_entry, dict):
        return None, ["runtime_entry_not_found"]

    semantic_cfg = (
        semantic_settings
        if isinstance(semantic_settings, dict)
        else dsr.resolve_semantic_generation_settings({})
    )
    progressive_cfg = (
        progressive_settings
        if isinstance(progressive_settings, dict)
        else dt.resolve_progressive_disclosure_settings({})
    )

    failed_checks: list[str] = []
    if runtime_entry.get("status") != "ok":
        failed_checks.append("runtime_status_not_ok")

    slots = _normalize_runtime_slots(runtime_entry.get("slots"))
    has_slots = isinstance(runtime_entry.get("slots"), dict)
    if has_slots:
        citations = _normalize_string_list(runtime_entry.get("citations"))
        citation_evidence_types: list[str] = []
        invalid_citations: list[str] = []
        for token in citations:
            evidence_type = parse_citation_token(token)
            if evidence_type is None:
                invalid_citations.append(token)
            else:
                citation_evidence_types.append(evidence_type)
        if invalid_citations:
            failed_checks.append("invalid_citation_token")

        required_prefixes = _resolve_required_evidence_prefixes(semantic_cfg)
        if required_prefixes and citation_evidence_types:
            if any(
                not any(evidence.startswith(prefix) for prefix in required_prefixes)
                for evidence in citation_evidence_types
            ):
                failed_checks.append("citation_prefix_not_allowed")

        required_slots = _resolve_required_progressive_slots(progressive_cfg)
        for slot in required_slots:
            slot_value = slots.get(slot)
            if slot == "summary":
                if not isinstance(slot_value, str) or not slot_value.strip():
                    failed_checks.append("missing_slot_summary")
            elif slot in {"key_facts", "next_steps"}:
                if not isinstance(slot_value, list) or not slot_value:
                    failed_checks.append(f"missing_slot_{slot}")
            else:
                if slot_value is None:
                    failed_checks.append(f"missing_slot_{slot}")

        summary_max_chars = int(progressive_cfg.get("summary_max_chars", 160))
        max_key_facts = int(progressive_cfg.get("max_key_facts", 5))
        max_next_steps = int(progressive_cfg.get("max_next_steps", 3))

        summary_text = slots.get("summary")
        if isinstance(summary_text, str) and len(summary_text) > summary_max_chars:
            failed_checks.append("summary_over_budget")
        key_facts = slots.get("key_facts")
        if isinstance(key_facts, list) and len(key_facts) > max_key_facts:
            failed_checks.append("key_facts_over_budget")
        next_steps = slots.get("next_steps")
        if isinstance(next_steps, list) and len(next_steps) > max_next_steps:
            failed_checks.append("next_steps_over_budget")

        deduped_failures = _dedupe_failures(failed_checks)
        if deduped_failures:
            return None, deduped_failures

        content = render_progressive_slots_content(
            slots,
            template_profile,
            required_slots=required_slots,
        )
        if not content:
            return None, ["missing_content"]
        return {
            "content": content,
            "slots": slots,
            "citations": citations,
        }, []

    content_raw = runtime_entry.get("content")
    statement_raw = runtime_entry.get("statement")
    if isinstance(content_raw, str) and content_raw.strip():
        content = content_raw.strip()
    elif isinstance(statement_raw, str) and statement_raw.strip():
        content = statement_raw.strip()
    else:
        content = ""
    if not content:
        failed_checks.append("missing_content")

    deduped_failures = _dedupe_failures(failed_checks)
    if deduped_failures:
        return None, deduped_failures
    return {"content": content}, []


def resolve_agents_runtime_payload(
    runtime_entry: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    payload, failures = resolve_update_section_runtime_payload(runtime_entry)
    if not payload:
        return None, failures
    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        return None, ["missing_content"]
    normalized = content.rstrip() + "\n"
    return {"content": normalized}, []


def resolve_topology_repair_runtime_payload(
    action: dict[str, Any],
    runtime_entry: dict[str, Any] | None,
    template_profile: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(runtime_entry, dict):
        return None, ["runtime_entry_not_found"]
    failed_checks: list[str] = []
    if runtime_entry.get("status") != "ok":
        failed_checks.append("runtime_status_not_ok")

    slots = _normalize_runtime_slots(runtime_entry.get("slots"))
    content: str = ""
    if slots:
        content = render_progressive_slots_content(slots, template_profile).strip()
    if not content:
        content_raw = runtime_entry.get("content")
        statement_raw = runtime_entry.get("statement")
        if isinstance(content_raw, str) and content_raw.strip():
            content = content_raw.strip()
        elif isinstance(statement_raw, str) and statement_raw.strip():
            content = statement_raw.strip()

    if not content:
        failed_checks.append("missing_content")

    path = normalize(str(action.get("path", "")).strip())
    if content and path.endswith(".json"):
        try:
            parsed = json.loads(content)
        except Exception:  # noqa: BLE001
            failed_checks.append("invalid_json_content")
        else:
            content = json.dumps(parsed, ensure_ascii=False, indent=2) + "\n"

    deduped_failures = _dedupe_failures(failed_checks)
    if deduped_failures:
        return None, deduped_failures
    return {"content": content}, []


def resolve_navigation_repair_runtime_payload(
    action: dict[str, Any],
    runtime_entry: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(runtime_entry, dict):
        return None, ["runtime_entry_not_found"]

    failed_checks: list[str] = []
    if runtime_entry.get("status") != "ok":
        failed_checks.append("runtime_status_not_ok")

    runtime_targets = _normalize_rel_list(runtime_entry.get("target_paths"))
    if not runtime_targets:
        runtime_targets = _normalize_rel_list(runtime_entry.get("index_links"))
    action_targets = _normalize_rel_list(action.get("missing_children"))
    targets = runtime_targets or action_targets
    if not targets:
        failed_checks.append("missing_navigation_targets")

    if action_targets:
        missing_declared = [
            target for target in action_targets if target not in set(targets)
        ]
        if missing_declared:
            failed_checks.append("missing_declared_navigation_targets")

    deduped_failures = _dedupe_failures(failed_checks)
    if deduped_failures:
        return None, deduped_failures
    return {"target_paths": targets}, []


def resolve_migrate_legacy_runtime_payload(
    runtime_entry: dict[str, Any] | None,
    template_profile: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(runtime_entry, dict):
        return None, ["runtime_entry_not_found"]

    failed_checks: list[str] = []
    if runtime_entry.get("status") != "ok":
        failed_checks.append("runtime_status_not_ok")

    slots = _normalize_runtime_slots(runtime_entry.get("slots"))
    content: str = ""
    if slots:
        content = render_progressive_slots_content(slots, template_profile).strip()
    if not content:
        content_raw = runtime_entry.get("content")
        statement_raw = runtime_entry.get("statement")
        if isinstance(content_raw, str) and content_raw.strip():
            content = content_raw.strip()
        elif isinstance(statement_raw, str) and statement_raw.strip():
            content = statement_raw.strip()
    if not content:
        failed_checks.append("missing_content")

    deduped_failures = _dedupe_failures(failed_checks)
    if deduped_failures:
        return None, deduped_failures

    payload: dict[str, Any] = {
        "content": content,
        "entry_id": runtime_entry.get("entry_id"),
    }
    citations = _normalize_string_list(runtime_entry.get("citations"))
    if citations:
        payload["citations"] = citations
    risk_notes = _normalize_string_list(runtime_entry.get("risk_notes"))
    if risk_notes:
        payload["risk_notes"] = risk_notes
    if slots:
        payload["slots"] = slots
    return payload, []


def _build_topology_repair_summary(action: dict[str, Any]) -> dict[str, Any]:
    orphan_docs = _normalize_rel_list(action.get("orphan_docs"))
    unreachable_docs = _normalize_rel_list(action.get("unreachable_docs"))
    over_depth_docs = _normalize_rel_list(action.get("over_depth_docs"))
    metrics = (
        action.get("topology_metrics")
        if isinstance(action.get("topology_metrics"), dict)
        else {}
    )
    return {
        "orphan_docs": orphan_docs,
        "unreachable_docs": unreachable_docs,
        "over_depth_docs": over_depth_docs,
        "topology_metrics": metrics,
    }


def _upsert_navigation_links(
    root: Path,
    parent_rel: str,
    children: list[str],
    dry_run: bool,
    template_profile: str,
) -> tuple[int, int]:
    parent_abs = root / parent_rel
    if not parent_abs.exists():
        return 0, len(children)

    text = parent_abs.read_text(encoding="utf-8")
    lines_to_add: list[str] = []
    parent_dir = Path(parent_rel).parent
    for child_rel in children:
        rel_link = os.path.relpath(child_rel, start=str(parent_dir)).replace("\\", "/")
        link_line = f"- [{child_rel}](./{rel_link})"
        if child_rel in text or f"](./{rel_link})" in text:
            continue
        lines_to_add.append(link_line)

    if not lines_to_add:
        return 0, len(children)

    heading = "## 子级文档导航" if template_profile == "zh-CN" else "## Child Document Links"
    updated = text.rstrip()
    if heading not in text:
        updated += "\n\n" + heading + "\n\n"
    else:
        updated += "\n"
    updated += "\n".join(lines_to_add) + "\n"
    write_text(parent_abs, updated, dry_run)
    return len(lines_to_add), len(children) - len(lines_to_add)


def _normalize_rel_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    paths: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            continue
        rel = normalize(item.strip())
        if not rel or rel in seen:
            continue
        seen.add(rel)
        paths.append(rel)
    return paths


def _write_if_changed(path: Path, content: str, dry_run: bool) -> bool:
    normalized = content.rstrip() + "\n"
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == normalized:
            return False
    write_text(path, normalized, dry_run)
    return True


def _build_fallback_merge_content(
    root: Path,
    source_paths: list[str],
    template_profile: str,
) -> tuple[str | None, list[str]]:
    if not source_paths:
        return None, ["missing_source_paths"]
    missing_sources: list[str] = []
    lines: list[str] = []
    title = "# 文档合并结果" if template_profile == "zh-CN" else "# Document Merge Result"
    summary = (
        "以下内容由 `merge_docs` fallback 合并，并保留来源追踪。"
        if template_profile == "zh-CN"
        else "The following content is merged by `merge_docs` fallback with source traceability."
    )
    lines.extend([title, "", summary, ""])
    for source_rel in source_paths:
        source_abs = root / source_rel
        if not source_abs.exists():
            missing_sources.append(source_rel)
            continue
        source_text = source_abs.read_text(encoding="utf-8").strip()
        heading = (
            f"## 来源 `{source_rel}`"
            if template_profile == "zh-CN"
            else f"## Source `{source_rel}`"
        )
        lines.extend(
            [
                heading,
                "",
                f"<!-- source-path: {source_rel} -->",
                "",
                source_text,
                "",
            ]
        )
    if missing_sources:
        return None, [f"missing_source:{source}" for source in missing_sources]
    return "\n".join(lines).rstrip() + "\n", []


def resolve_merge_docs_runtime_payload(
    action: dict[str, Any],
    runtime_entry: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(runtime_entry, dict):
        return None, ["runtime_entry_not_found"]
    failed_checks: list[str] = []
    if runtime_entry.get("status") != "ok":
        failed_checks.append("runtime_status_not_ok")

    content_raw = runtime_entry.get("content")
    content = content_raw.strip() if isinstance(content_raw, str) and content_raw.strip() else ""
    if not content:
        failed_checks.append("missing_content")

    runtime_sources = _normalize_rel_list(runtime_entry.get("source_paths"))
    action_sources = _normalize_rel_list(action.get("source_paths"))
    merged_sources = runtime_sources or action_sources
    if not merged_sources:
        failed_checks.append("missing_source_paths")
    if action_sources:
        missing_declared = [p for p in action_sources if p not in set(merged_sources)]
        if missing_declared:
            failed_checks.append("missing_declared_sources")

    deduped_failures = _dedupe_failures(failed_checks)
    if deduped_failures:
        return None, deduped_failures
    return {
        "content": content,
        "source_paths": merged_sources,
    }, []


def _normalize_split_outputs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    outputs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        content = item.get("content")
        if not isinstance(path, str) or not path.strip():
            continue
        if not isinstance(content, str) or not content.strip():
            continue
        rel = normalize(path.strip())
        if rel in seen:
            continue
        seen.add(rel)
        normalized: dict[str, Any] = {
            "path": rel,
            "content": content.strip(),
        }
        source_paths = _normalize_rel_list(item.get("source_paths"))
        if source_paths:
            normalized["source_paths"] = source_paths
        outputs.append(normalized)
    return outputs


def resolve_split_doc_runtime_payload(
    action: dict[str, Any],
    runtime_entry: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(runtime_entry, dict):
        return None, ["runtime_entry_not_found"]
    failed_checks: list[str] = []
    if runtime_entry.get("status") != "ok":
        failed_checks.append("runtime_status_not_ok")

    split_outputs = _normalize_split_outputs(runtime_entry.get("split_outputs"))
    if not split_outputs:
        failed_checks.append("missing_split_outputs")

    action_target_paths = _normalize_rel_list(action.get("target_paths"))
    output_paths = {str(item.get("path")) for item in split_outputs}
    if action_target_paths:
        missing_targets = [path for path in action_target_paths if path not in output_paths]
        if missing_targets:
            failed_checks.append("missing_declared_split_targets")

    index_links = _normalize_rel_list(runtime_entry.get("index_links"))
    if not index_links:
        index_links = [str(item.get("path")) for item in split_outputs if isinstance(item.get("path"), str)]

    deduped_failures = _dedupe_failures(failed_checks)
    if deduped_failures:
        return None, deduped_failures
    return {
        "split_outputs": split_outputs,
        "index_links": index_links,
    }, []


def _build_split_doc_fallback_payload(
    root: Path,
    action: dict[str, Any],
    template_profile: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    source_rel = normalize(
        str(action.get("source_path") or action.get("path") or "").strip()
    )
    if not source_rel:
        return None, ["missing_source_path"]
    source_abs = root / source_rel
    if not source_abs.exists():
        return None, [f"missing_source:{source_rel}"]
    source_content = source_abs.read_text(encoding="utf-8").strip()
    split_rules = action.get("split_rules")
    target_paths = _normalize_rel_list(action.get("target_paths"))
    if isinstance(split_rules, list):
        for item in split_rules:
            if not isinstance(item, dict):
                continue
            target = item.get("target_path")
            if isinstance(target, str) and target.strip():
                target_paths.append(normalize(target.strip()))
    deduped_targets: list[str] = []
    seen: set[str] = set()
    for target in target_paths:
        if target in seen:
            continue
        seen.add(target)
        deduped_targets.append(target)
    if not deduped_targets:
        return None, ["missing_target_paths"]

    outputs: list[dict[str, Any]] = []
    for target in deduped_targets:
        title = (
            f"# 拆分文档：{target}"
            if template_profile == "zh-CN"
            else f"# Split Document: {target}"
        )
        trace_title = "## 来源追踪" if template_profile == "zh-CN" else "## Source Trace"
        excerpt_title = "## 来源摘录" if template_profile == "zh-CN" else "## Source Excerpt"
        excerpt = "\n".join(source_content.splitlines()[:20]).strip()
        content = "\n".join(
            [
                title,
                "",
                f"<!-- split-from: {source_rel} -->",
                "",
                trace_title,
                "",
                f"- source_path: `{source_rel}`",
                f"- split_target: `{target}`",
                "",
                excerpt_title,
                "",
                "```markdown",
                excerpt or ("TODO: source content is empty." if template_profile != "zh-CN" else "TODO: 来源内容为空。"),
                "```",
            ]
        )
        outputs.append(
            {
                "path": target,
                "content": content,
                "source_paths": [source_rel],
            }
        )

    return {
        "split_outputs": outputs,
        "index_links": [item["path"] for item in outputs],
    }, []


def _upsert_index_links(
    root: Path,
    index_path: str,
    target_paths: list[str],
    dry_run: bool,
    template_profile: str,
) -> bool:
    index_rel = normalize(index_path)
    index_abs = root / index_rel
    if not index_abs.exists():
        base = (
            "# 文档索引\n\n## 结构化拆分产物\n"
            if template_profile == "zh-CN"
            else "# Documentation Index\n\n## Split Artifacts\n"
        )
        write_text(index_abs, base + "\n", dry_run)
    text = index_abs.read_text(encoding="utf-8")
    lines_to_add: list[str] = []
    for target_rel in target_paths:
        rel_link = os.path.relpath(target_rel, start=str(Path(index_rel).parent))
        rel_link = rel_link.replace("\\", "/")
        link_line = f"- [{target_rel}](./{rel_link})"
        if target_rel in text or f"](./{rel_link})" in text:
            continue
        lines_to_add.append(link_line)
    if not lines_to_add:
        return False
    section_heading = "## 结构化拆分产物" if template_profile == "zh-CN" else "## Split Artifacts"
    updated = text.rstrip()
    if section_heading not in text:
        updated += "\n\n" + section_heading + "\n\n"
    else:
        updated += "\n"
    updated += "\n".join(lines_to_add) + "\n"
    write_text(index_abs, updated, dry_run)
    return True


def upsert_module_inventory(path: Path, modules: list[str], dry_run: bool, template_profile: str) -> bool:
    if not modules or not path.exists():
        return False

    text = path.read_text(encoding="utf-8")
    line_template = lp.get_module_line_template(template_profile)
    additions = []
    for module in modules:
        line = line_template.format(module=module)
        if line not in text:
            additions.append(line)

    if not additions:
        return False

    markers = lp.get_module_inventory_markers()
    heading = lp.get_module_inventory_heading(template_profile)

    if any(marker in text for marker in markers):
        updated = text.rstrip() + "\n\n" + "\n".join(additions) + "\n"
    else:
        updated = text.rstrip() + "\n\n" + heading + "\n\n" + "\n".join(additions) + "\n"

    write_text(path, updated, dry_run)
    return True


def resolve_manifest_snapshot(action: dict[str, Any]) -> dict[str, Any]:
    snapshot = action.get("manifest_snapshot")
    if isinstance(snapshot, dict):
        return dc.normalize_manifest_snapshot(snapshot)
    return dc.clone_default_manifest()


def build_default_topology_contract() -> dict[str, Any]:
    return {
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
    }


def render_managed_file_content(rel_path: str, template_profile: str, metadata_policy: dict[str, Any]) -> str:
    content = lp.get_managed_template(rel_path, template_profile)
    if dm.should_enforce_for_path(rel_path, metadata_policy):
        content, _ = dm.ensure_metadata_block(content, metadata_policy, reference_date=date.today())
    return content


def upsert_doc_metadata(rel_path: str, path: Path, dry_run: bool, metadata_policy: dict[str, Any]) -> bool:
    if not dm.should_enforce_for_path(rel_path, metadata_policy):
        return False
    if not path.exists():
        return False

    text = path.read_text(encoding="utf-8")
    updated, changed = dm.ensure_metadata_block(text, metadata_policy, reference_date=date.today())
    if not changed:
        return False

    write_text(path, updated, dry_run)
    return True


def read_text_lossy(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def resolve_legacy_registry_path(root: Path, legacy_settings: dict[str, Any]) -> Path:
    registry_rel = normalize(
        str(
            legacy_settings.get(
                "registry_path", dl.DEFAULT_LEGACY_SETTINGS["registry_path"]
            )
        )
    )
    return root / registry_rel


def update_legacy_registry(
    root: Path,
    legacy_settings: dict[str, Any],
    source_rel: str,
    patch: dict[str, Any],
    dry_run: bool,
) -> None:
    registry_path = resolve_legacy_registry_path(root, legacy_settings)
    registry = dl.load_registry(registry_path)
    dl.upsert_registry_entry(registry, source_rel, patch)
    dl.save_registry(registry_path, registry, dry_run)


def resolve_legacy_semantic_patch(action: dict[str, Any]) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    category = action.get("semantic_category")
    if isinstance(category, str) and category.strip():
        patch["category"] = category.strip()

    confidence = action.get("semantic_confidence")
    if isinstance(confidence, (int, float)):
        patch["confidence"] = float(confidence)

    decision_source = action.get("decision_source")
    if isinstance(decision_source, str) and decision_source.strip():
        patch["decision_source"] = decision_source.strip()
    elif patch:
        patch["decision_source"] = "semantic"
    else:
        patch["decision_source"] = "rule"

    semantic_model = action.get("semantic_model")
    if isinstance(semantic_model, str) and semantic_model.strip():
        patch["semantic_model"] = semantic_model.strip()
    return patch


def build_summary_hash(entry_content: str) -> str:
    return hashlib.sha256(entry_content.encode("utf-8")).hexdigest()


FALLBACK_REASON_CODES = {
    "runtime_unavailable",
    "runtime_entry_not_found",
    "runtime_gate_failed",
    "path_denied",
    "runtime_quality_grade_c",
}
AGENTS_STRUCTURAL_TRIGGER_TYPES = {
    "sync_manifest",
    "add",
    "archive",
    "archive_legacy",
    "migrate_legacy",
    "semantic_rewrite",
}
AGENTS_SEMANTIC_TRIGGER_TYPES = {
    "update_section",
    "fill_claim",
    "semantic_rewrite",
    "migrate_legacy",
    "merge_docs",
    "split_doc",
}
AGENTS_SEMANTIC_RUNTIME_HIT_STATUSES = {
    "candidate_loaded",
    "section_runtime_applied",
    "claim_runtime_applied",
    "semantic_rewrite_applied",
    "merge_docs_runtime_applied",
    "split_doc_runtime_applied",
    "agents_runtime_applied",
}
SEMANTIC_OBSERVABILITY_EXEMPT_STATUSES = {
    "deterministic_mode",
    "semantic_disabled",
    "action_disabled",
    "semantic_not_enabled",
}


def is_agent_strict_mode(semantic_settings: dict[str, Any]) -> bool:
    return str(semantic_settings.get("mode", "")).strip() == "agent_strict"


def resolve_fallback_reason_code(failures: list[str]) -> str | None:
    if not failures:
        return None
    if "runtime_quality_manual_review" in failures:
        return "runtime_quality_manual_review"
    if "runtime_quality_grade_d" in failures:
        return "runtime_quality_grade_d"
    if "runtime_quality_grade_c" in failures:
        return "runtime_quality_grade_c"
    if "path_denied" in failures:
        return "path_denied"
    if "runtime_unavailable" in failures:
        return "runtime_unavailable"
    if "runtime_entry_not_found" in failures:
        return "runtime_entry_not_found"
    return "runtime_gate_failed"


def resolve_runtime_fallback_allowed(
    semantic_settings: dict[str, Any], fallback_reason: str | None
) -> bool:
    if is_agent_strict_mode(semantic_settings):
        return False
    if fallback_reason in {"runtime_quality_grade_d", "runtime_quality_manual_review"}:
        return False
    if fallback_reason == "runtime_quality_grade_c":
        input_quality = semantic_settings.get("input_quality")
        if not isinstance(input_quality, dict):
            return False
        c_grade_decision = str(input_quality.get("c_grade_decision", "fallback")).strip()
        if c_grade_decision != "fallback":
            return False
    if not bool(semantic_settings.get("allow_fallback_template", True)):
        return False
    return bool(fallback_reason in FALLBACK_REASON_CODES)


def has_agents_structural_trigger(results: list[dict[str, Any]]) -> bool:
    for result in results:
        if not isinstance(result, dict):
            continue
        result_type = str(result.get("type", "")).strip()
        result_status = str(result.get("status", "")).strip()
        if result_type == "add" and normalize(str(result.get("path", ""))) == "AGENTS.md":
            continue
        if result_status == "applied" and result_type in AGENTS_STRUCTURAL_TRIGGER_TYPES:
            return True
    return False


def has_agents_semantic_trigger(
    actions: list[dict[str, Any]], results: list[dict[str, Any]]
) -> bool:
    semantic_action_seen = any(
        isinstance(action, dict)
        and str(action.get("type", "")).strip() in AGENTS_SEMANTIC_TRIGGER_TYPES
        for action in actions
    )
    if semantic_action_seen:
        return True
    for result in results:
        if not isinstance(result, dict):
            continue
        semantic_runtime = result.get("semantic_runtime")
        if not isinstance(semantic_runtime, dict):
            continue
        status = str(semantic_runtime.get("status", "")).strip()
        if status in AGENTS_SEMANTIC_RUNTIME_HIT_STATUSES:
            return True
    return False


def is_runtime_path_denied(rel_path: str, semantic_settings: dict[str, Any]) -> bool:
    deny_paths = semantic_settings.get("deny_paths")
    if not isinstance(deny_paths, list):
        return False
    normalized = normalize(rel_path)
    for pattern in deny_paths:
        if not isinstance(pattern, str) or not pattern.strip():
            continue
        if fnmatch.fnmatch(normalized, pattern.strip()):
            return True
    return False


def runtime_required_for_action(action_type: str, semantic_settings: dict[str, Any]) -> bool:
    return bool(
        is_agent_strict_mode(semantic_settings)
        and dsr.should_attempt_runtime_semantics(action_type, semantic_settings)
    )


def summarize_semantic_observability(
    results: list[dict[str, Any]],
    semantic_settings: dict[str, Any],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "semantic_action_count": 0,
        "semantic_attempt_count": 0,
        "semantic_success_count": 0,
        "fallback_count": 0,
        "fallback_reason_breakdown": {},
        "runtime_quality_grade_distribution": {},
        "runtime_quality_decision_breakdown": {},
        "runtime_quality_degraded_count": 0,
        "semantic_exempt_count": 0,
        "semantic_unattempted_count": 0,
        "semantic_unattempted_without_exemption": 0,
        "semantic_hit_rate": 0.0,
        "semantic_unattempted_samples": [],
    }
    if not bool(semantic_settings.get("enabled", False)):
        return summary

    actions = semantic_settings.get("actions")
    if not isinstance(actions, dict):
        return summary
    enabled_actions = {
        str(action_type).strip()
        for action_type, enabled in actions.items()
        if isinstance(action_type, str) and bool(enabled)
    }
    if not enabled_actions:
        return summary

    fallback_reasons: Counter[str] = Counter()
    quality_grades: Counter[str] = Counter()
    quality_decisions: Counter[str] = Counter()
    unattempted_samples: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        action_type = str(result.get("type", "")).strip()
        if action_type not in enabled_actions:
            continue

        summary["semantic_action_count"] += 1
        runtime = result.get("semantic_runtime")
        if not isinstance(runtime, dict):
            summary["semantic_unattempted_without_exemption"] += 1
            if len(unattempted_samples) < 20:
                unattempted_samples.append(
                    {
                        "id": result.get("id"),
                        "type": action_type,
                        "path": normalize(str(result.get("path", ""))),
                        "reason": "missing_semantic_runtime_trace",
                    }
                )
            continue

        attempted = bool(runtime.get("attempted"))
        if attempted:
            summary["semantic_attempt_count"] += 1
        status = str(runtime.get("status", "")).strip()
        consumed = bool(runtime.get("consumed"))
        if consumed or status in AGENTS_SEMANTIC_RUNTIME_HIT_STATUSES:
            summary["semantic_success_count"] += 1

        if bool(runtime.get("fallback_used")):
            summary["fallback_count"] += 1
            fallback_reason = str(runtime.get("fallback_reason", "")).strip() or "unknown"
            fallback_reasons[fallback_reason] += 1

        quality_grade = str(runtime.get("quality_grade", "")).strip().upper()
        if quality_grade in dsr.SUPPORTED_RUNTIME_QUALITY_GRADES:
            quality_grades[quality_grade] += 1
        quality_decision = str(runtime.get("quality_decision", "")).strip()
        if quality_decision:
            quality_decisions[quality_decision] += 1
            if quality_decision in {"fallback", "manual_review", "block"}:
                summary["runtime_quality_degraded_count"] += 1

        if not attempted:
            exemption_reason = runtime.get("exemption_reason")
            if isinstance(exemption_reason, str) and exemption_reason.strip():
                summary["semantic_exempt_count"] += 1
            elif status in SEMANTIC_OBSERVABILITY_EXEMPT_STATUSES:
                summary["semantic_exempt_count"] += 1
            else:
                summary["semantic_unattempted_without_exemption"] += 1
                if len(unattempted_samples) < 20:
                    unattempted_samples.append(
                        {
                            "id": result.get("id"),
                            "type": action_type,
                            "path": normalize(str(result.get("path", ""))),
                            "reason": "attempt_missing_without_exemption",
                            "status": status or "unknown",
                        }
                    )

    action_count = int(summary["semantic_action_count"])
    attempt_count = int(summary["semantic_attempt_count"])
    success_count = int(summary["semantic_success_count"])
    summary["fallback_reason_breakdown"] = dict(sorted(fallback_reasons.items()))
    summary["runtime_quality_grade_distribution"] = dict(sorted(quality_grades.items()))
    summary["runtime_quality_decision_breakdown"] = dict(sorted(quality_decisions.items()))
    summary["semantic_unattempted_count"] = max(action_count - attempt_count, 0)
    summary["semantic_hit_rate"] = (
        round(success_count / attempt_count, 4) if attempt_count > 0 else 0.0
    )
    summary["semantic_unattempted_samples"] = unattempted_samples
    return summary


def apply_action(
    root: Path,
    action: dict[str, Any],
    dry_run: bool,
    language_settings: dict[str, Any],
    template_profile: str,
    metadata_policy: dict[str, Any],
    legacy_settings: dict[str, Any] | None = None,
    semantic_settings: dict[str, Any] | None = None,
    progressive_settings: dict[str, Any] | None = None,
    semantic_runtime_entries: list[dict[str, Any]] | None = None,
    semantic_runtime_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "id": action.get("id"),
        "type": action.get("type"),
        "path": action.get("path"),
        "status": "skipped",
        "details": "",
    }

    action_type = action.get("type")
    kind = action.get("kind")
    rel_path = normalize(action.get("path", ""))
    abs_path = root / rel_path
    legacy_cfg = legacy_settings or dl.resolve_legacy_settings({})
    semantic_cfg = (
        semantic_settings
        if isinstance(semantic_settings, dict)
        else dsr.resolve_semantic_generation_settings({})
    )
    progressive_cfg = (
        progressive_settings
        if isinstance(progressive_settings, dict)
        else dt.resolve_progressive_disclosure_settings({})
    )
    runtime_entries = (
        semantic_runtime_entries if isinstance(semantic_runtime_entries, list) else []
    )
    runtime_state = (
        semantic_runtime_state if isinstance(semantic_runtime_state, dict) else {}
    )

    def attach_runtime_candidate() -> tuple[dict[str, Any] | None, list[str]]:
        failures: list[str] = []
        if not isinstance(action_type, str):
            return None, failures
        if not dsr.should_attempt_runtime_semantics(action_type, semantic_cfg):
            if dsr.runtime_semantic_attempt_required(action_type, semantic_cfg):
                result["semantic_runtime"] = {
                    "status": "semantic_attempt_missing",
                    "attempted": False,
                    "required": True,
                    "mode": semantic_cfg.get("mode"),
                    "source": semantic_cfg.get("source"),
                }
            return None, failures
        if is_runtime_path_denied(rel_path, semantic_cfg):
            result["semantic_runtime"] = {
                "status": "path_denied",
                "attempted": True,
                "mode": semantic_cfg.get("mode"),
                "source": semantic_cfg.get("source"),
            }
            return None, ["path_denied"]
        candidate = dsr.select_runtime_entry(action, runtime_entries, semantic_cfg)
        if isinstance(candidate, dict):
            if not isinstance(candidate.get("quality_decision"), str):
                candidate = dict(candidate)
                candidate.update(dsr.evaluate_runtime_entry_quality(candidate, semantic_cfg))
            quality_grade = str(candidate.get("quality_grade", "")).strip().upper()
            quality_score = candidate.get("quality_score")
            quality_findings = (
                candidate.get("quality_findings")
                if isinstance(candidate.get("quality_findings"), list)
                else []
            )
            quality_decision = str(candidate.get("quality_decision", "")).strip() or "consume"
            quality_decision_reason = (
                str(candidate.get("quality_decision_reason", "")).strip()
                or "quality_grade_pass"
            )
            semantic_runtime_state: dict[str, Any] = {
                "status": "candidate_loaded",
                "entry_id": candidate.get("entry_id"),
                "candidate_status": candidate.get("status"),
                "attempted": True,
                "mode": semantic_cfg.get("mode"),
                "source": semantic_cfg.get("source"),
                "quality_grade": quality_grade,
                "quality_score": quality_score,
                "quality_decision": quality_decision,
                "quality_decision_reason": quality_decision_reason,
                "quality_findings": quality_findings,
            }
            result["semantic_runtime"] = semantic_runtime_state
            if quality_decision != "consume":
                if quality_decision == "fallback":
                    semantic_runtime_state["status"] = "quality_grade_c_downgraded"
                    return None, ["runtime_quality_grade_c"]
                if quality_decision == "manual_review":
                    semantic_runtime_state["status"] = "quality_manual_review"
                    return None, ["runtime_quality_manual_review"]
                semantic_runtime_state["status"] = "quality_blocked"
                return None, ["runtime_quality_grade_d"]
            return candidate, failures

        state_status = (
            "runtime_unavailable"
            if not runtime_state.get("available", False)
            else "runtime_entry_not_found"
        )
        state_error = runtime_state.get("error")
        semantic_state: dict[str, Any] = {
            "status": state_status,
            "attempted": True,
            "mode": semantic_cfg.get("mode"),
            "source": semantic_cfg.get("source"),
        }
        if isinstance(state_error, str) and state_error.strip():
            semantic_state["error"] = state_error.strip()
        result["semantic_runtime"] = semantic_state
        if state_status == "runtime_unavailable":
            failures.append("runtime_unavailable")
        elif state_status == "runtime_entry_not_found":
            failures.append("runtime_entry_not_found")
        return None, failures

    try:
        if action_type == "add":
            if kind == "dir":
                if abs_path.exists():
                    result["details"] = "directory already exists"
                else:
                    if not dry_run:
                        abs_path.mkdir(parents=True, exist_ok=True)
                    result["status"] = "applied"
                    result["details"] = "directory created"
                return result

            if abs_path.exists():
                result["details"] = "file already exists"
                return result

            if rel_path == "docs/.doc-policy.json":
                policy_data = lp.build_default_policy(
                    primary_language=language_settings["primary"],
                    profile=language_settings["profile"],
                )
                policy_data = lp.merge_language_into_policy(policy_data, language_settings)
                write_json(abs_path, policy_data, dry_run)
            elif rel_path == "docs/.doc-manifest.json":
                write_json(abs_path, resolve_manifest_snapshot(action), dry_run)
            elif rel_path == "docs/.doc-topology.json" or action.get("template") == "topology":
                write_json(abs_path, build_default_topology_contract(), dry_run)
            elif rel_path == "AGENTS.md":
                write_text(abs_path, lp.get_agents_md_template(template_profile), dry_run)
            else:
                write_text(
                    abs_path,
                    render_managed_file_content(rel_path, template_profile, metadata_policy),
                    dry_run,
                )

            result["status"] = "applied"
            result["details"] = "file created"
            return result

        if action_type == "sync_manifest":
            manifest_snapshot = resolve_manifest_snapshot(action)
            write_json(abs_path, manifest_snapshot, dry_run)
            result["status"] = "applied"
            result["details"] = "manifest synchronized"
            return result

        if action_type == "update":
            metadata_changed = False
            if action.get("missing_doc_metadata") or action.get("invalid_doc_metadata"):
                metadata_changed = upsert_doc_metadata(rel_path, abs_path, dry_run, metadata_policy)

            changed, labels = append_missing_sections(rel_path, abs_path, dry_run, template_profile)
            module_changed = False
            if rel_path == "docs/architecture.md":
                missing_modules = action.get("missing_modules") or []
                if isinstance(missing_modules, list):
                    module_changed = upsert_module_inventory(abs_path, missing_modules, dry_run, template_profile)

            detail_parts: list[str] = []
            if changed:
                detail_parts.append(f"sections upserted: {', '.join(labels)}")
            if module_changed:
                detail_parts.append("module inventory updated")
            if metadata_changed:
                detail_parts.append("doc metadata upserted")

            if detail_parts:
                result["status"] = "applied"
                result["details"] = "; ".join(detail_parts)
            else:
                result["details"] = "no update required"
            return result

        if action_type == "update_section":
            runtime_candidate, runtime_candidate_failures = attach_runtime_candidate()
            section_id = action.get("section_id")
            section_heading = action.get("section_heading")
            section_id_str = (
                section_id.strip() if isinstance(section_id, str) and section_id.strip() else ""
            )

            runtime_payload = None
            runtime_gate_failures: list[str] = list(runtime_candidate_failures)
            if isinstance(runtime_candidate, dict):
                runtime_payload, runtime_gate_failures = resolve_update_section_runtime_payload(
                    runtime_candidate,
                    semantic_cfg,
                    progressive_cfg,
                    template_profile,
                )
                runtime_gate_failures = list(runtime_candidate_failures) + runtime_gate_failures
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["gate"] = {
                        "status": "passed" if runtime_payload else "failed",
                        "failed_checks": runtime_gate_failures,
                    }
                    semantic_runtime["consumed"] = bool(runtime_payload)
                    if not runtime_payload:
                        semantic_runtime["status"] = "section_runtime_gate_failed"

            if isinstance(runtime_payload, dict):
                runtime_content = runtime_payload.get("content")
                changed = upsert_section_content(
                    rel_path,
                    abs_path,
                    section_id_str,
                    str(runtime_content) if isinstance(runtime_content, str) else "",
                    dry_run,
                    template_profile,
                    section_heading=section_heading if isinstance(section_heading, str) else None,
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["status"] = (
                        "section_runtime_applied"
                        if changed
                        else "section_runtime_no_change"
                    )
                if changed:
                    result["status"] = "applied"
                    result["details"] = f"section content upserted from runtime: {section_id_str}"
                else:
                    result["details"] = "section content already up-to-date"
                return result

            if runtime_required_for_action("update_section", semantic_cfg):
                result["status"] = "error"
                result["details"] = (
                    "agent_strict requires runtime semantic candidate with passing gate for update_section"
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["status"] = "runtime_required"
                    semantic_runtime["required"] = True
                return result

            fallback_reason = resolve_fallback_reason_code(runtime_gate_failures)
            fallback_allowed = resolve_runtime_fallback_allowed(
                semantic_cfg, fallback_reason
            )
            if runtime_gate_failures and not fallback_allowed:
                result["status"] = "skipped"
                result["details"] = (
                    "runtime semantics unavailable or gate failed, and fallback blocked by semantic policy"
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["status"] = "fallback_blocked"
                    semantic_runtime["required"] = False
                    semantic_runtime["fallback_allowed"] = False
                    semantic_runtime["fallback_reason"] = fallback_reason
                    semantic_runtime["gate"] = {
                        "status": "failed",
                        "failed_checks": runtime_gate_failures,
                    }
                return result

            changed = upsert_section(
                rel_path,
                abs_path,
                section_id,
                dry_run,
                template_profile,
                section_heading=section_heading if isinstance(section_heading, str) else None,
            )
            if changed:
                result["status"] = "applied"
                heading = section_heading or lp.get_section_heading(
                    rel_path, str(section_id), template_profile
                )
                if runtime_gate_failures:
                    semantic_runtime = result.get("semantic_runtime")
                    if isinstance(semantic_runtime, dict):
                        semantic_runtime["fallback_used"] = True
                        semantic_runtime["fallback_reason"] = fallback_reason
                    result["details"] = (
                        f"runtime gate failed; fallback section scaffold upserted: {heading}"
                    )
                else:
                    result["details"] = f"section upserted: {heading}"
            else:
                if runtime_gate_failures:
                    semantic_runtime = result.get("semantic_runtime")
                    if isinstance(semantic_runtime, dict):
                        semantic_runtime["fallback_used"] = True
                        semantic_runtime["fallback_reason"] = fallback_reason
                    result["details"] = (
                        "runtime gate failed; section already present or unsupported section_id"
                    )
                else:
                    result["details"] = "section already present or unsupported section_id"
            return result

        if action_type == "fill_claim":
            runtime_candidate, runtime_candidate_failures = attach_runtime_candidate()
            section_id = action.get("section_id")
            claim_id = action.get("claim_id")
            section_id_str = (
                section_id.strip() if isinstance(section_id, str) and section_id.strip() else ""
            )
            claim_id_str = (
                claim_id.strip() if isinstance(claim_id, str) and claim_id.strip() else ""
            )
            required_evidence_types = action.get("required_evidence_types") or []
            if not isinstance(required_evidence_types, list):
                required_evidence_types = []
            required_evidence_types = [
                str(v).strip()
                for v in required_evidence_types
                if isinstance(v, str) and str(v).strip()
            ]

            runtime_payload = None
            runtime_gate_failures: list[str] = list(runtime_candidate_failures)
            if isinstance(runtime_candidate, dict):
                runtime_payload, runtime_gate_failures = resolve_fill_claim_runtime_payload(
                    action,
                    runtime_candidate,
                    semantic_cfg,
                )
                runtime_gate_failures = list(runtime_candidate_failures) + runtime_gate_failures
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["gate"] = {
                        "status": "passed" if runtime_payload else "failed",
                        "failed_checks": runtime_gate_failures,
                    }
                    semantic_runtime["consumed"] = bool(runtime_payload)
                    if not runtime_payload:
                        semantic_runtime["status"] = "claim_runtime_gate_failed"

            if isinstance(runtime_payload, dict):
                statement = runtime_payload.get("statement")
                citations = runtime_payload.get("citations")
                statement_changed = upsert_claim_statement(
                    rel_path,
                    abs_path,
                    section_id_str,
                    claim_id_str,
                    str(statement) if isinstance(statement, str) else "",
                    citations if isinstance(citations, list) else [],
                    dry_run,
                    template_profile,
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["status"] = (
                        "claim_runtime_applied"
                        if statement_changed
                        else "claim_runtime_no_change"
                    )
                if statement_changed:
                    result["status"] = "applied"
                    result["details"] = f"claim statement upserted from runtime: {claim_id_str}"
                else:
                    result["details"] = "claim statement already up-to-date"
                return result

            if runtime_required_for_action("fill_claim", semantic_cfg):
                result["status"] = "error"
                result["details"] = (
                    "agent_strict requires runtime semantic candidate with passing gate for fill_claim"
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["status"] = "runtime_required"
                    semantic_runtime["required"] = True
                return result

            fallback_reason = resolve_fallback_reason_code(runtime_gate_failures)
            fallback_allowed = resolve_runtime_fallback_allowed(
                semantic_cfg, fallback_reason
            )
            if runtime_gate_failures and not fallback_allowed:
                result["status"] = "skipped"
                result["details"] = (
                    "runtime semantics unavailable or gate failed, and fallback blocked by semantic policy"
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["status"] = "fallback_blocked"
                    semantic_runtime["required"] = False
                    semantic_runtime["fallback_allowed"] = False
                    semantic_runtime["fallback_reason"] = fallback_reason
                    semantic_runtime["gate"] = {
                        "status": "failed",
                        "failed_checks": runtime_gate_failures,
                    }
                return result

            changed = upsert_claim_todo(
                rel_path,
                abs_path,
                section_id_str,
                claim_id_str,
                required_evidence_types,
                dry_run,
                template_profile,
            )
            if changed:
                result["status"] = "applied"
                if runtime_gate_failures:
                    semantic_runtime = result.get("semantic_runtime")
                    if isinstance(semantic_runtime, dict):
                        semantic_runtime["fallback_used"] = True
                        semantic_runtime["fallback_reason"] = fallback_reason
                    result["details"] = (
                        f"runtime gate failed; fallback claim TODO appended: {claim_id_str}"
                    )
                else:
                    result["details"] = f"claim TODO appended: {claim_id_str}"
            else:
                if runtime_gate_failures:
                    semantic_runtime = result.get("semantic_runtime")
                    if isinstance(semantic_runtime, dict):
                        semantic_runtime["fallback_used"] = True
                        semantic_runtime["fallback_reason"] = fallback_reason
                    result["details"] = (
                        "runtime gate failed; claim TODO already exists or invalid claim metadata"
                    )
                else:
                    result["details"] = "claim TODO already exists or invalid claim metadata"
            return result

        if action_type == "refresh_evidence":
            evidence_types = action.get("evidence_types") or []
            if isinstance(evidence_types, list) and evidence_types:
                details = f"evidence refresh delegated to scan step: {', '.join(str(v) for v in evidence_types)}"
            else:
                details = "evidence refresh delegated to scan step"
            result["status"] = "applied"
            result["details"] = details
            return result

        if action_type == "quality_repair":
            failed_checks = action.get("failed_checks") or []
            if isinstance(failed_checks, list) and failed_checks:
                details = "quality gate requires repair: " + ", ".join(
                    str(v) for v in failed_checks
                )
            else:
                details = "quality gate requires repair"
            result["status"] = "applied"
            result["details"] = details
            return result

        if action_type == "semantic_rewrite":
            runtime_candidate, runtime_candidate_failures = attach_runtime_candidate()
            section_id = action.get("section_id")
            section_id_str = (
                section_id.strip() if isinstance(section_id, str) and section_id.strip() else ""
            )
            section_heading = action.get("section_heading")
            runtime_payload = None
            runtime_gate_failures: list[str] = list(runtime_candidate_failures)
            if isinstance(runtime_candidate, dict):
                runtime_payload, runtime_gate_failures = resolve_update_section_runtime_payload(
                    runtime_candidate,
                    semantic_cfg,
                    progressive_cfg,
                    template_profile,
                )
                runtime_gate_failures = list(runtime_candidate_failures) + runtime_gate_failures
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["gate"] = {
                        "status": "passed" if runtime_payload else "failed",
                        "failed_checks": runtime_gate_failures,
                    }
                    semantic_runtime["consumed"] = bool(runtime_payload)
                    if not runtime_payload:
                        semantic_runtime["status"] = "semantic_rewrite_runtime_gate_failed"

            if isinstance(runtime_payload, dict):
                runtime_content = runtime_payload.get("content")
                if section_id_str:
                    changed = upsert_section_content(
                        rel_path,
                        abs_path,
                        section_id_str,
                        str(runtime_content) if isinstance(runtime_content, str) else "",
                        dry_run,
                        template_profile,
                        section_heading=section_heading if isinstance(section_heading, str) else None,
                    )
                    semantic_runtime = result.get("semantic_runtime")
                    if isinstance(semantic_runtime, dict):
                        semantic_runtime["status"] = (
                            "semantic_rewrite_applied"
                            if changed
                            else "semantic_rewrite_no_change"
                        )
                    if changed:
                        result["status"] = "applied"
                        result["details"] = f"semantic rewrite applied to section: {section_id_str}"
                    else:
                        result["details"] = "semantic rewrite content already up-to-date"
                    return result

                if abs_path.exists():
                    content_text = (
                        str(runtime_content).strip() + "\n"
                        if isinstance(runtime_content, str)
                        else ""
                    )
                    if content_text:
                        current = abs_path.read_text(encoding="utf-8")
                        if current != content_text:
                            write_text(abs_path, content_text, dry_run)
                            semantic_runtime = result.get("semantic_runtime")
                            if isinstance(semantic_runtime, dict):
                                semantic_runtime["status"] = "semantic_rewrite_applied"
                            result["status"] = "applied"
                            result["details"] = "semantic rewrite applied to document"
                            return result
                        semantic_runtime = result.get("semantic_runtime")
                        if isinstance(semantic_runtime, dict):
                            semantic_runtime["status"] = "semantic_rewrite_no_change"
                        result["details"] = "semantic rewrite content already up-to-date"
                        return result

            if runtime_required_for_action("semantic_rewrite", semantic_cfg):
                result["status"] = "error"
                result["details"] = (
                    "agent_strict requires runtime semantic candidate with passing gate for semantic_rewrite"
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["status"] = "runtime_required"
                    semantic_runtime["required"] = True
                return result

            fallback_reason = resolve_fallback_reason_code(runtime_gate_failures)
            fallback_allowed = resolve_runtime_fallback_allowed(
                semantic_cfg, fallback_reason
            )
            if runtime_gate_failures and not fallback_allowed:
                result["status"] = "skipped"
                result["details"] = (
                    "runtime semantics unavailable or gate failed, and fallback blocked by semantic policy"
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["status"] = "fallback_blocked"
                    semantic_runtime["required"] = False
                    semantic_runtime["fallback_allowed"] = False
                    semantic_runtime["fallback_reason"] = fallback_reason
                    semantic_runtime["gate"] = {
                        "status": "failed",
                        "failed_checks": runtime_gate_failures,
                    }
                return result

            source_rel = normalize(action.get("source_path", ""))
            backlog_reason = action.get("backlog_reason")
            details = "semantic rewrite deferred to runtime/manual workflow"
            if isinstance(backlog_reason, str) and backlog_reason.strip():
                details += f": reason={backlog_reason.strip()}"
            if source_rel:
                details += f", source={source_rel}"
            if runtime_gate_failures:
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["fallback_used"] = True
                    semantic_runtime["fallback_reason"] = fallback_reason
                details += ", runtime gate failed"
            result["status"] = "applied"
            result["details"] = details
            return result

        if action_type == "merge_docs":
            runtime_candidate, runtime_candidate_failures = attach_runtime_candidate()
            runtime_payload = None
            runtime_gate_failures: list[str] = list(runtime_candidate_failures)
            if isinstance(runtime_candidate, dict):
                runtime_payload, runtime_gate_failures = resolve_merge_docs_runtime_payload(
                    action, runtime_candidate
                )
                runtime_gate_failures = list(runtime_candidate_failures) + runtime_gate_failures
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["gate"] = {
                        "status": "passed" if runtime_payload else "failed",
                        "failed_checks": runtime_gate_failures,
                    }
                    semantic_runtime["consumed"] = bool(runtime_payload)
                    if not runtime_payload:
                        semantic_runtime["status"] = "merge_docs_runtime_gate_failed"

            if isinstance(runtime_payload, dict):
                runtime_content = runtime_payload.get("content")
                changed = _write_if_changed(
                    abs_path,
                    str(runtime_content) if isinstance(runtime_content, str) else "",
                    dry_run,
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["status"] = (
                        "merge_docs_runtime_applied"
                        if changed
                        else "merge_docs_runtime_no_change"
                    )
                if changed:
                    result["status"] = "applied"
                    result["details"] = "merge docs content upserted from runtime semantic candidate"
                else:
                    result["details"] = "merge docs content already up-to-date"
                result["merged_sources"] = runtime_payload.get("source_paths") or []
                return result

            if runtime_required_for_action("merge_docs", semantic_cfg):
                result["status"] = "error"
                result["details"] = (
                    "agent_strict requires runtime semantic candidate with passing gate for merge_docs"
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["status"] = "runtime_required"
                    semantic_runtime["required"] = True
                return result

            fallback_reason = resolve_fallback_reason_code(runtime_gate_failures)
            fallback_allowed = resolve_runtime_fallback_allowed(
                semantic_cfg, fallback_reason
            )
            if runtime_gate_failures and not fallback_allowed:
                result["status"] = "skipped"
                result["details"] = (
                    "runtime semantics unavailable or gate failed, and fallback blocked by semantic policy"
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["status"] = "fallback_blocked"
                    semantic_runtime["required"] = False
                    semantic_runtime["fallback_allowed"] = False
                    semantic_runtime["fallback_reason"] = fallback_reason
                    semantic_runtime["gate"] = {
                        "status": "failed",
                        "failed_checks": runtime_gate_failures,
                    }
                return result

            source_paths = _normalize_rel_list(action.get("source_paths"))
            fallback_content, fallback_errors = _build_fallback_merge_content(
                root,
                source_paths,
                template_profile,
            )
            if fallback_errors or not isinstance(fallback_content, str):
                result["status"] = "skipped"
                result["details"] = (
                    "merge docs fallback skipped: "
                    + ", ".join(fallback_errors or ["unknown_fallback_error"])
                )
                return result
            changed = _write_if_changed(abs_path, fallback_content, dry_run)
            if changed:
                result["status"] = "applied"
                result["details"] = "merge docs generated by deterministic fallback"
            else:
                result["details"] = "merge docs fallback content already up-to-date"
            result["merged_sources"] = source_paths
            semantic_runtime = result.get("semantic_runtime")
            if isinstance(semantic_runtime, dict) and runtime_gate_failures:
                semantic_runtime["fallback_used"] = True
                semantic_runtime["fallback_reason"] = fallback_reason
            return result

        if action_type == "split_doc":
            runtime_candidate, runtime_candidate_failures = attach_runtime_candidate()
            runtime_payload = None
            runtime_gate_failures: list[str] = list(runtime_candidate_failures)
            if isinstance(runtime_candidate, dict):
                runtime_payload, runtime_gate_failures = resolve_split_doc_runtime_payload(
                    action, runtime_candidate
                )
                runtime_gate_failures = list(runtime_candidate_failures) + runtime_gate_failures
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["gate"] = {
                        "status": "passed" if runtime_payload else "failed",
                        "failed_checks": runtime_gate_failures,
                    }
                    semantic_runtime["consumed"] = bool(runtime_payload)
                    if not runtime_payload:
                        semantic_runtime["status"] = "split_doc_runtime_gate_failed"

            if isinstance(runtime_payload, dict):
                split_outputs = runtime_payload.get("split_outputs") or []
                changed_count = 0
                created_targets: list[str] = []
                for output in split_outputs:
                    if not isinstance(output, dict):
                        continue
                    target_path = output.get("path")
                    content = output.get("content")
                    if not isinstance(target_path, str) or not target_path.strip():
                        continue
                    if not isinstance(content, str) or not content.strip():
                        continue
                    target_rel = normalize(target_path.strip())
                    target_abs = root / target_rel
                    if _write_if_changed(target_abs, content, dry_run):
                        changed_count += 1
                    created_targets.append(target_rel)
                index_path = normalize(
                    str(action.get("index_path") or "docs/index.md").strip()
                )
                index_changed = _upsert_index_links(
                    root,
                    index_path,
                    _normalize_rel_list(runtime_payload.get("index_links")),
                    dry_run,
                    template_profile,
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["status"] = (
                        "split_doc_runtime_applied"
                        if changed_count > 0 or index_changed
                        else "split_doc_runtime_no_change"
                    )
                if changed_count > 0 or index_changed:
                    result["status"] = "applied"
                    result["details"] = (
                        f"split doc applied from runtime: files_changed={changed_count}, "
                        f"index_changed={str(index_changed).lower()}"
                    )
                else:
                    result["details"] = "split doc runtime outputs already up-to-date"
                result["split_targets"] = created_targets
                return result

            if runtime_required_for_action("split_doc", semantic_cfg):
                result["status"] = "error"
                result["details"] = (
                    "agent_strict requires runtime semantic candidate with passing gate for split_doc"
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["status"] = "runtime_required"
                    semantic_runtime["required"] = True
                return result

            fallback_reason = resolve_fallback_reason_code(runtime_gate_failures)
            fallback_allowed = resolve_runtime_fallback_allowed(
                semantic_cfg, fallback_reason
            )
            if runtime_gate_failures and not fallback_allowed:
                result["status"] = "skipped"
                result["details"] = (
                    "runtime semantics unavailable or gate failed, and fallback blocked by semantic policy"
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["status"] = "fallback_blocked"
                    semantic_runtime["required"] = False
                    semantic_runtime["fallback_allowed"] = False
                    semantic_runtime["fallback_reason"] = fallback_reason
                    semantic_runtime["gate"] = {
                        "status": "failed",
                        "failed_checks": runtime_gate_failures,
                    }
                return result

            fallback_payload, fallback_errors = _build_split_doc_fallback_payload(
                root,
                action,
                template_profile,
            )
            if fallback_errors or not isinstance(fallback_payload, dict):
                result["status"] = "skipped"
                result["details"] = (
                    "split doc fallback skipped: "
                    + ", ".join(fallback_errors or ["unknown_fallback_error"])
                )
                return result
            changed_count = 0
            created_targets: list[str] = []
            for output in fallback_payload.get("split_outputs") or []:
                if not isinstance(output, dict):
                    continue
                target_path = output.get("path")
                content = output.get("content")
                if not isinstance(target_path, str) or not target_path.strip():
                    continue
                if not isinstance(content, str) or not content.strip():
                    continue
                target_rel = normalize(target_path.strip())
                if _write_if_changed(root / target_rel, content, dry_run):
                    changed_count += 1
                created_targets.append(target_rel)
            index_path = normalize(str(action.get("index_path") or "docs/index.md").strip())
            index_changed = _upsert_index_links(
                root,
                index_path,
                _normalize_rel_list(fallback_payload.get("index_links")),
                dry_run,
                template_profile,
            )
            if changed_count > 0 or index_changed:
                result["status"] = "applied"
                result["details"] = (
                    f"split doc generated by deterministic fallback: files_changed={changed_count}, "
                    f"index_changed={str(index_changed).lower()}"
                )
            else:
                result["details"] = "split doc fallback outputs already up-to-date"
            result["split_targets"] = created_targets
            semantic_runtime = result.get("semantic_runtime")
            if isinstance(semantic_runtime, dict) and runtime_gate_failures:
                semantic_runtime["fallback_used"] = True
                semantic_runtime["fallback_reason"] = fallback_reason
            return result

        if action_type == "topology_repair":
            runtime_candidate, runtime_candidate_failures = attach_runtime_candidate()
            runtime_payload = None
            runtime_gate_failures: list[str] = list(runtime_candidate_failures)
            if isinstance(runtime_candidate, dict):
                runtime_payload, runtime_gate_failures = (
                    resolve_topology_repair_runtime_payload(
                        action,
                        runtime_candidate,
                        template_profile,
                    )
                )
                runtime_gate_failures = (
                    list(runtime_candidate_failures) + runtime_gate_failures
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["gate"] = {
                        "status": "passed" if runtime_payload else "failed",
                        "failed_checks": runtime_gate_failures,
                    }
                    semantic_runtime["consumed"] = bool(runtime_payload)
                    if not runtime_payload:
                        semantic_runtime["status"] = "topology_runtime_gate_failed"

            topology_summary = _build_topology_repair_summary(action)
            result["topology"] = topology_summary
            if isinstance(runtime_payload, dict):
                runtime_content = runtime_payload.get("content")
                changed = False
                if (
                    isinstance(runtime_content, str)
                    and runtime_content.strip()
                    and rel_path.endswith(".json")
                ):
                    changed = _write_if_changed(abs_path, runtime_content, dry_run)
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["status"] = (
                        "topology_runtime_applied"
                        if changed
                        else "topology_runtime_no_change"
                    )
                result["status"] = "applied"
                if changed:
                    result["details"] = "topology repair applied from runtime semantic candidate"
                else:
                    result["details"] = "topology runtime guidance consumed without file diff"
                return result

            if runtime_required_for_action("topology_repair", semantic_cfg):
                result["status"] = "error"
                result["details"] = (
                    "agent_strict requires runtime semantic candidate with passing gate for topology_repair"
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["status"] = "runtime_required"
                    semantic_runtime["required"] = True
                return result

            fallback_reason = resolve_fallback_reason_code(runtime_gate_failures)
            fallback_allowed = resolve_runtime_fallback_allowed(
                semantic_cfg, fallback_reason
            )
            if runtime_gate_failures and not fallback_allowed:
                result["status"] = "skipped"
                result["details"] = (
                    "runtime semantics unavailable or gate failed, and fallback blocked by semantic policy"
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["status"] = "fallback_blocked"
                    semantic_runtime["required"] = False
                    semantic_runtime["fallback_allowed"] = False
                    semantic_runtime["fallback_reason"] = fallback_reason
                    semantic_runtime["gate"] = {
                        "status": "failed",
                        "failed_checks": runtime_gate_failures,
                    }
                return result

            if rel_path.endswith(".json") and not abs_path.exists():
                write_json(abs_path, build_default_topology_contract(), dry_run)
                result["status"] = "applied"
                result["details"] = "topology contract initialized for repair workflow"
            else:
                result["status"] = "applied"
                result["details"] = (
                    "topology repair guidance emitted: "
                    f"orphan={len(topology_summary.get('orphan_docs', []))}, "
                    f"unreachable={len(topology_summary.get('unreachable_docs', []))}, "
                    f"over_depth={len(topology_summary.get('over_depth_docs', []))}"
                )
            semantic_runtime = result.get("semantic_runtime")
            if isinstance(semantic_runtime, dict) and runtime_gate_failures:
                semantic_runtime["fallback_used"] = True
                semantic_runtime["fallback_reason"] = fallback_reason
            return result

        if action_type == "navigation_repair":
            parent_rel = normalize(str(action.get("parent_path") or rel_path).strip())
            if not parent_rel:
                result["details"] = "missing parent_path"
                return result
            result["path"] = parent_rel

            runtime_candidate, runtime_candidate_failures = attach_runtime_candidate()
            runtime_payload = None
            runtime_gate_failures: list[str] = list(runtime_candidate_failures)
            if isinstance(runtime_candidate, dict):
                runtime_payload, runtime_gate_failures = (
                    resolve_navigation_repair_runtime_payload(action, runtime_candidate)
                )
                runtime_gate_failures = (
                    list(runtime_candidate_failures) + runtime_gate_failures
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["gate"] = {
                        "status": "passed" if runtime_payload else "failed",
                        "failed_checks": runtime_gate_failures,
                    }
                    semantic_runtime["consumed"] = bool(runtime_payload)
                    if not runtime_payload:
                        semantic_runtime["status"] = "navigation_runtime_gate_failed"

            parent_abs = root / parent_rel
            if not parent_abs.exists():
                result["details"] = f"navigation parent does not exist: {parent_rel}"
                return result

            if isinstance(runtime_payload, dict):
                target_paths = _normalize_rel_list(runtime_payload.get("target_paths"))
                if not target_paths:
                    result["details"] = "navigation repair skipped: missing target paths"
                    return result
                added_count, unchanged_count = _upsert_navigation_links(
                    root,
                    parent_rel,
                    target_paths,
                    dry_run,
                    template_profile,
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["status"] = (
                        "navigation_runtime_applied"
                        if added_count > 0
                        else "navigation_runtime_no_change"
                    )
                if added_count > 0:
                    result["status"] = "applied"
                    result["details"] = (
                        "navigation links repaired from runtime semantic candidate: "
                        f"added={added_count}"
                    )
                else:
                    result["details"] = "navigation links already up-to-date"
                result["navigation"] = {
                    "parent_path": parent_rel,
                    "target_paths": target_paths,
                    "added_count": added_count,
                    "unchanged_count": unchanged_count,
                }
                return result

            if runtime_required_for_action("navigation_repair", semantic_cfg):
                result["status"] = "error"
                result["details"] = (
                    "agent_strict requires runtime semantic candidate with passing gate for navigation_repair"
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["status"] = "runtime_required"
                    semantic_runtime["required"] = True
                return result

            fallback_reason = resolve_fallback_reason_code(runtime_gate_failures)
            fallback_allowed = resolve_runtime_fallback_allowed(
                semantic_cfg, fallback_reason
            )
            if runtime_gate_failures and not fallback_allowed:
                result["status"] = "skipped"
                result["details"] = (
                    "runtime semantics unavailable or gate failed, and fallback blocked by semantic policy"
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["status"] = "fallback_blocked"
                    semantic_runtime["required"] = False
                    semantic_runtime["fallback_allowed"] = False
                    semantic_runtime["fallback_reason"] = fallback_reason
                    semantic_runtime["gate"] = {
                        "status": "failed",
                        "failed_checks": runtime_gate_failures,
                    }
                return result

            target_paths = _normalize_rel_list(action.get("missing_children"))
            if not target_paths:
                result["details"] = "navigation repair skipped: missing_children is empty"
                return result

            added_count, unchanged_count = _upsert_navigation_links(
                root,
                parent_rel,
                target_paths,
                dry_run,
                template_profile,
            )
            if added_count > 0:
                result["status"] = "applied"
                result["details"] = (
                    "navigation links repaired by deterministic fallback: "
                    f"added={added_count}"
                )
            else:
                result["details"] = "navigation links already up-to-date"
            semantic_runtime = result.get("semantic_runtime")
            if isinstance(semantic_runtime, dict) and runtime_gate_failures:
                semantic_runtime["fallback_used"] = True
                semantic_runtime["fallback_reason"] = fallback_reason
            result["navigation"] = {
                "parent_path": parent_rel,
                "target_paths": target_paths,
                "added_count": added_count,
                "unchanged_count": unchanged_count,
            }
            return result

        if action_type == "migrate_legacy":
            source_rel = normalize(action.get("source_path", ""))
            if not source_rel:
                result["details"] = "missing source_path"
                return result

            source_abs = root / source_rel
            if not source_abs.exists():
                result["details"] = "source does not exist"
                return result

            runtime_candidate, runtime_candidate_failures = attach_runtime_candidate()
            runtime_payload = None
            runtime_gate_failures: list[str] = list(runtime_candidate_failures)
            if isinstance(runtime_candidate, dict):
                runtime_payload, runtime_gate_failures = (
                    resolve_migrate_legacy_runtime_payload(
                        runtime_candidate,
                        template_profile,
                    )
                )
                runtime_gate_failures = (
                    list(runtime_candidate_failures) + runtime_gate_failures
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["gate"] = {
                        "status": "passed" if runtime_payload else "failed",
                        "failed_checks": runtime_gate_failures,
                    }
                    semantic_runtime["consumed"] = bool(runtime_payload)
                    if not runtime_payload:
                        semantic_runtime["status"] = "migrate_legacy_runtime_gate_failed"

            archive_rel = normalize(action.get("archive_path", ""))
            if not archive_rel:
                archive_rel = dl.resolve_archive_path(source_rel, legacy_cfg)
            marker = dl.source_marker(source_rel)
            semantic_patch = resolve_legacy_semantic_patch(action)
            if isinstance(runtime_payload, dict):
                semantic_patch["decision_source"] = "semantic"

            if abs_path.exists():
                base_content = read_text_lossy(abs_path)
            else:
                base_content = dl.render_target_header(template_profile)
                if dm.should_enforce_for_path(rel_path, metadata_policy):
                    base_content, _ = dm.ensure_metadata_block(
                        base_content,
                        metadata_policy,
                        reference_date=date.today(),
                    )

            if marker in base_content:
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict) and isinstance(runtime_payload, dict):
                    semantic_runtime["status"] = "migrate_legacy_runtime_no_change"
                update_legacy_registry(
                    root,
                    legacy_cfg,
                    source_rel,
                    {
                        "status": "migrated",
                        "target_path": rel_path,
                        "archive_path": archive_rel,
                        **semantic_patch,
                    },
                    dry_run,
                )
                result["details"] = "legacy source already migrated"
                return result

            runtime_fallback_reason = resolve_fallback_reason_code(runtime_gate_failures)
            fallback_allowed = resolve_runtime_fallback_allowed(
                semantic_cfg, runtime_fallback_reason
            )
            if (
                not isinstance(runtime_payload, dict)
                and runtime_required_for_action("migrate_legacy", semantic_cfg)
            ):
                result["status"] = "error"
                result["details"] = (
                    "agent_strict requires runtime semantic candidate with passing gate for migrate_legacy"
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["status"] = "runtime_required"
                    semantic_runtime["required"] = True
                return result

            if runtime_gate_failures and not fallback_allowed and not runtime_payload:
                result["status"] = "skipped"
                result["details"] = (
                    "runtime semantics unavailable or gate failed, and fallback blocked by semantic policy"
                )
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["status"] = "fallback_blocked"
                    semantic_runtime["required"] = False
                    semantic_runtime["fallback_allowed"] = False
                    semantic_runtime["fallback_reason"] = runtime_fallback_reason
                    semantic_runtime["gate"] = {
                        "status": "failed",
                        "failed_checks": runtime_gate_failures,
                    }
                return result

            source_content = read_text_lossy(source_abs)
            entry_content_source = source_content
            evidence_items = (
                action.get("evidence") if isinstance(action.get("evidence"), list) else []
            )
            if not isinstance(evidence_items, list):
                evidence_items = []
            if isinstance(runtime_payload, dict):
                runtime_content = runtime_payload.get("content")
                if isinstance(runtime_content, str) and runtime_content.strip():
                    entry_content_source = runtime_content.strip()
                runtime_entry_id = runtime_payload.get("entry_id")
                if isinstance(runtime_entry_id, str) and runtime_entry_id.strip():
                    evidence_items.append(
                        f"semantic runtime entry consumed: {runtime_entry_id.strip()}"
                    )
                for citation in _normalize_string_list(runtime_payload.get("citations"))[:3]:
                    evidence_items.append(f"semantic runtime citation: {citation}")
                for risk_note in _normalize_string_list(runtime_payload.get("risk_notes"))[:2]:
                    evidence_items.append(f"semantic runtime risk note: {risk_note}")

            entry = dl.render_structured_migration_entry(
                source_rel=source_rel,
                source_content=entry_content_source,
                archive_path=archive_rel,
                template_profile=template_profile,
                semantic={
                    "category": action.get("semantic_category"),
                    "confidence": action.get("semantic_confidence"),
                },
                evidence=evidence_items,
            ).rstrip()
            summary_hash = build_summary_hash(entry)

            merged_content = base_content.rstrip()
            if merged_content:
                merged_content += "\n\n" + entry + "\n"
            else:
                merged_content = entry + "\n"
            write_text(abs_path, merged_content, dry_run)

            if dm.should_enforce_for_path(rel_path, metadata_policy):
                upsert_doc_metadata(rel_path, abs_path, dry_run, metadata_policy)

            update_legacy_registry(
                root,
                legacy_cfg,
                source_rel,
                {
                    "status": "migrated",
                    "target_path": rel_path,
                    "archive_path": archive_rel,
                    "migrated_at": utc_now(),
                    "summary_hash": summary_hash,
                    **semantic_patch,
                },
                dry_run,
            )
            result["status"] = "applied"
            if isinstance(runtime_payload, dict):
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["status"] = "migrate_legacy_runtime_applied"
                result["details"] = (
                    f"legacy content migrated from {source_rel} using runtime semantic payload"
                )
            elif runtime_gate_failures:
                semantic_runtime = result.get("semantic_runtime")
                if isinstance(semantic_runtime, dict):
                    semantic_runtime["fallback_used"] = True
                    semantic_runtime["fallback_reason"] = runtime_fallback_reason
                result["details"] = (
                    f"legacy content migrated from {source_rel} by deterministic fallback"
                )
            else:
                result["details"] = f"legacy content migrated from {source_rel}"
            return result

        if action_type in {"archive", "archive_legacy"}:
            source_rel = normalize(action.get("source_path", ""))
            if not source_rel:
                result["details"] = "missing source_path"
                return result

            source_abs = root / source_rel
            if not source_abs.exists():
                result["details"] = "source does not exist"
                return result

            if abs_path.exists():
                result["details"] = "archive target already exists"
                return result

            if not dry_run:
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source_abs), str(abs_path))

            if action_type == "archive_legacy":
                semantic_patch = resolve_legacy_semantic_patch(action)
                update_legacy_registry(
                    root,
                    legacy_cfg,
                    source_rel,
                    {
                        "status": "archived",
                        "archive_path": rel_path,
                        "target_path": normalize(action.get("target_path", "")),
                        "archived_at": utc_now(),
                        **semantic_patch,
                    },
                    dry_run,
                )

            result["status"] = "applied"
            result["details"] = f"archived from {source_rel}"
            return result

        if action_type in {"manual_review", "legacy_manual_review", "keep"}:
            if action_type == "legacy_manual_review":
                source_rel = normalize(action.get("path") or action.get("source_path") or "")
                if source_rel:
                    semantic_patch = resolve_legacy_semantic_patch(action)
                    update_legacy_registry(
                        root,
                        legacy_cfg,
                        source_rel,
                        {
                            "status": "manual_review",
                            "target_path": normalize(action.get("target_path", "")),
                            "archive_path": normalize(action.get("archive_path", "")),
                            "reviewed_at": utc_now(),
                            **semantic_patch,
                        },
                        dry_run,
                    )
            result["details"] = "no automatic action"
            return result

        result["details"] = f"unsupported action type: {action_type}"
        return result

    except Exception as exc:  # noqa: BLE001
        result["status"] = "error"
        result["details"] = str(exc)
        return result


def render_markdown_report(report: dict[str, Any]) -> str:
    language = report.get("language", {})
    semantic_runtime = report.get("semantic_runtime", {})
    semantic_runtime_data = (
        semantic_runtime.get("runtime")
        if isinstance(semantic_runtime, dict) and isinstance(semantic_runtime.get("runtime"), dict)
        else {}
    )
    lines = [
        "# Doc Apply Report",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Root: {report['root']}",
        f"- Mode: {report['mode']}",
        f"- Dry run: {report['dry_run']}",
        f"- Language primary: {language.get('primary', 'N/A')}",
        f"- Language profile: {language.get('profile', 'N/A')}",
        f"- Language source: {language.get('source', 'N/A')}",
        f"- Semantic runtime enabled: {semantic_runtime_data.get('enabled', False)}",
        f"- Semantic runtime mode: {semantic_runtime_data.get('mode', 'N/A')}",
        f"- Semantic runtime available: {semantic_runtime_data.get('available', False)}",
        f"- Semantic runtime entries: {semantic_runtime_data.get('entry_count', 0)}",
        "",
        "## Summary",
        "",
        f"- Total actions: {report['summary']['total_actions']}",
        f"- Applied: {report['summary']['applied']}",
        f"- Skipped: {report['summary']['skipped']}",
        f"- Errors: {report['summary']['errors']}",
        f"- Semantic actions: {report['summary'].get('semantic_action_count', 0)}",
        f"- Semantic attempts: {report['summary'].get('semantic_attempt_count', 0)}",
        f"- Semantic successes: {report['summary'].get('semantic_success_count', 0)}",
        f"- Semantic hit rate: {report['summary'].get('semantic_hit_rate', 0.0)}",
        f"- Fallback count: {report['summary'].get('fallback_count', 0)}",
        "- Fallback reason breakdown: "
        f"{json.dumps(report['summary'].get('fallback_reason_breakdown', {}), ensure_ascii=False)}",
        "- Runtime quality grade distribution: "
        f"{json.dumps(report['summary'].get('runtime_quality_grade_distribution', {}), ensure_ascii=False)}",
        "- Runtime quality decision breakdown: "
        f"{json.dumps(report['summary'].get('runtime_quality_decision_breakdown', {}), ensure_ascii=False)}",
        "",
        "## Action Results",
        "",
    ]

    for item in report["results"]:
        lines.append(f"- {item['id']} `{item['type']}` `{item['path']}` -> {item['status']} ({item['details']})")

    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply doc maintenance plan.")
    parser.add_argument("--root", required=True, help="Repository root")
    parser.add_argument("--plan", required=True, help="Plan JSON path")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["bootstrap", "apply-safe", "apply-with-archive"],
        help="Execution mode",
    )
    parser.add_argument(
        "--init-language",
        help="Primary descriptive language used at initialization, e.g. zh-CN or en-US",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write any files")
    parser.add_argument("--report-json", default="docs/.doc-apply-report.json", help="JSON report path")
    parser.add_argument("--report-md", default="docs/.doc-apply-report.md", help="Markdown report path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    plan_path = Path(args.plan).resolve()

    if not root.exists() or not root.is_dir():
        raise SystemExit(f"[ERROR] Invalid root path: {root}")
    if not plan_path.exists():
        raise SystemExit(f"[ERROR] Plan file not found: {plan_path}")

    language_settings = resolve_language_settings(root, args.init_language)
    template_profile = language_settings["profile"]
    existing_policy = load_json_mapping(root / "docs/.doc-policy.json")
    effective_policy = (
        existing_policy
        if isinstance(existing_policy, dict)
        else lp.build_default_policy(
            primary_language=language_settings["primary"],
            profile=language_settings["profile"],
        )
    )
    metadata_policy = dm.resolve_metadata_policy(effective_policy)
    legacy_settings = dl.resolve_legacy_settings(effective_policy)
    semantic_settings = dsr.resolve_semantic_generation_settings(effective_policy)
    progressive_settings = dt.resolve_progressive_disclosure_settings(effective_policy)
    semantic_runtime_entries, semantic_runtime_state = dsr.load_runtime_report(
        root, semantic_settings
    )

    with plan_path.open("r", encoding="utf-8") as f:
        plan = json.load(f)
    if plan is None:
        plan = {}
    if not isinstance(plan, dict):
        raise SystemExit(f"[ERROR] Plan JSON root must be object: {plan_path}")

    plan_mode = (plan.get("meta") or {}).get("mode")
    if plan_mode and plan_mode not in {
        "bootstrap",
        "audit",
        "apply-safe",
        "apply-with-archive",
        "repair",
    }:
        raise SystemExit(f"[ERROR] Unsupported plan mode: {plan_mode}")

    if plan_mode in {"audit", "repair"} and args.mode != "apply-safe":
        print(
            "[WARN] Applying an audit/repair plan with mode != apply-safe is not recommended."
        )

    policy_language_updated = False
    policy_path = root / "docs/.doc-policy.json"
    if args.mode == "bootstrap" and policy_path.exists():
        policy_language_updated = ensure_policy_language(policy_path, language_settings, args.dry_run)

    actions = plan.get("actions") or []
    results = [
        apply_action(
            root,
            action,
            args.dry_run,
            language_settings,
            template_profile,
            metadata_policy,
            legacy_settings,
            semantic_settings,
            progressive_settings,
            semantic_runtime_entries,
            semantic_runtime_state,
        )
        for action in actions
    ]

    plan_meta = plan.get("meta") if isinstance(plan.get("meta"), dict) else {}
    agents_settings = doc_agents.resolve_agents_settings(effective_policy)
    agents_mode = str(agents_settings.get("mode", "dynamic")).strip().lower() or "dynamic"
    manifest_changed = bool(plan_meta.get("manifest_changed", False))
    sync_manifest_applied = any(
        r.get("type") == "sync_manifest" and r.get("status") == "applied"
        for r in results
    )
    agents_add_applied = any(
        r.get("type") == "add"
        and normalize(str(r.get("path", ""))) == "AGENTS.md"
        and r.get("status") == "applied"
        for r in results
    )
    agents_missing = not (root / "AGENTS.md").exists()
    structural_triggered = has_agents_structural_trigger(results)
    semantic_triggered = has_agents_semantic_trigger(actions, results)
    should_generate_agents = (
        agents_settings.get("enabled", False)
        and (
            args.mode == "bootstrap"
            or agents_add_applied
            or agents_missing
            or structural_triggered
            or (
                agents_settings.get("regenerate_on_semantic_actions", True)
                and semantic_triggered
            )
            or (
                agents_settings.get("sync_on_manifest_change", True)
                and (manifest_changed or sync_manifest_applied)
            )
        )
    )

    agents_runtime_candidate: dict[str, Any] | None = None
    agents_runtime_result: dict[str, Any] | None = None
    agents_runtime_payload: dict[str, Any] | None = None
    agents_runtime_gate_failures: list[str] = []
    agents_runtime_enabled = bool(
        agents_mode != "deterministic"
        and dsr.should_attempt_runtime_semantics("agents_generate", semantic_settings)
    )
    agents_runtime_required = bool(
        agents_runtime_enabled
        and runtime_required_for_action("agents_generate", semantic_settings)
    )
    if agents_mode == "deterministic":
        agents_runtime_result = {
            "status": "deterministic_mode",
            "attempted": False,
            "mode": semantic_settings.get("mode"),
            "source": semantic_settings.get("source"),
        }
    if agents_runtime_enabled:
        if is_runtime_path_denied("AGENTS.md", semantic_settings):
            agents_runtime_gate_failures = ["path_denied"]
            agents_runtime_result = {
                "status": "path_denied",
                "attempted": True,
                "mode": semantic_settings.get("mode"),
                "source": semantic_settings.get("source"),
            }
        else:
            agents_runtime_candidate = dsr.select_runtime_entry(
                {"type": "agents_generate", "path": "AGENTS.md"},
                semantic_runtime_entries,
                semantic_settings,
            )
            if isinstance(agents_runtime_candidate, dict):
                if not isinstance(agents_runtime_candidate.get("quality_decision"), str):
                    agents_runtime_candidate = dict(agents_runtime_candidate)
                    agents_runtime_candidate.update(
                        dsr.evaluate_runtime_entry_quality(
                            agents_runtime_candidate, semantic_settings
                        )
                    )
                quality_grade = str(agents_runtime_candidate.get("quality_grade", "")).strip().upper()
                quality_score = agents_runtime_candidate.get("quality_score")
                quality_findings = (
                    agents_runtime_candidate.get("quality_findings")
                    if isinstance(agents_runtime_candidate.get("quality_findings"), list)
                    else []
                )
                quality_decision = (
                    str(agents_runtime_candidate.get("quality_decision", "")).strip()
                    or "consume"
                )
                quality_decision_reason = (
                    str(
                        agents_runtime_candidate.get(
                            "quality_decision_reason",
                            "",
                        )
                    ).strip()
                    or "quality_grade_pass"
                )
                agents_runtime_result = {
                    "status": "candidate_loaded",
                    "entry_id": agents_runtime_candidate.get("entry_id"),
                    "candidate_status": agents_runtime_candidate.get("status"),
                    "attempted": True,
                    "mode": semantic_settings.get("mode"),
                    "source": semantic_settings.get("source"),
                    "quality_grade": quality_grade,
                    "quality_score": quality_score,
                    "quality_decision": quality_decision,
                    "quality_decision_reason": quality_decision_reason,
                    "quality_findings": quality_findings,
                }
                if quality_decision == "fallback":
                    agents_runtime_result["status"] = "quality_grade_c_downgraded"
                    agents_runtime_gate_failures = ["runtime_quality_grade_c"]
                    agents_runtime_payload = None
                elif quality_decision == "manual_review":
                    agents_runtime_result["status"] = "quality_manual_review"
                    agents_runtime_gate_failures = ["runtime_quality_manual_review"]
                    agents_runtime_payload = None
                elif quality_decision == "block":
                    agents_runtime_result["status"] = "quality_blocked"
                    agents_runtime_gate_failures = ["runtime_quality_grade_d"]
                    agents_runtime_payload = None
                else:
                    agents_runtime_payload, agents_runtime_gate_failures = (
                        resolve_agents_runtime_payload(agents_runtime_candidate)
                    )
                    agents_runtime_result["gate"] = {
                        "status": "passed" if agents_runtime_payload else "failed",
                        "failed_checks": agents_runtime_gate_failures,
                    }
                    agents_runtime_result["consumed"] = bool(agents_runtime_payload)
            else:
                state_status = (
                    "runtime_unavailable"
                    if not semantic_runtime_state.get("available", False)
                    else "runtime_entry_not_found"
                )
                agents_runtime_gate_failures = (
                    ["runtime_unavailable"]
                    if state_status == "runtime_unavailable"
                    else ["runtime_entry_not_found"]
                )
                agents_runtime_result = {
                    "status": state_status,
                    "attempted": True,
                    "mode": semantic_settings.get("mode"),
                    "source": semantic_settings.get("source"),
                }
                state_error = semantic_runtime_state.get("error")
                if isinstance(state_error, str) and state_error.strip():
                    agents_runtime_result["error"] = state_error.strip()
    agents_fallback_reason = resolve_fallback_reason_code(agents_runtime_gate_failures)
    agents_fallback_allowed = resolve_runtime_fallback_allowed(
        semantic_settings, agents_fallback_reason
    )

    agents_generation_report: dict[str, Any] | None = None
    if should_generate_agents:
        if agents_runtime_required and not isinstance(agents_runtime_payload, dict):
            error_result: dict[str, Any] = {
                "id": "AGENTS",
                "type": "agents_generate",
                "path": "AGENTS.md",
                "status": "error",
                "details": (
                    "agent_strict requires runtime semantic candidate with passing gate for agents_generate"
                ),
            }
            if isinstance(agents_runtime_result, dict):
                agents_runtime_result["status"] = "runtime_required"
                agents_runtime_result["required"] = True
                error_result["semantic_runtime"] = dict(agents_runtime_result)
            results.append(error_result)
        elif (
            agents_runtime_enabled
            and agents_runtime_gate_failures
            and not agents_fallback_allowed
        ):
            skipped_result: dict[str, Any] = {
                "id": "AGENTS",
                "type": "agents_generate",
                "path": "AGENTS.md",
                "status": "skipped",
                "details": (
                    "runtime semantics unavailable or gate failed, and fallback blocked by semantic policy"
                ),
            }
            if isinstance(agents_runtime_result, dict):
                agents_runtime_result["status"] = "fallback_blocked"
                agents_runtime_result["required"] = False
                agents_runtime_result["fallback_allowed"] = False
                agents_runtime_result["fallback_reason"] = agents_fallback_reason
                skipped_result["semantic_runtime"] = dict(agents_runtime_result)
            results.append(skipped_result)
        else:
            manifest_data = (
                plan_meta.get("manifest_effective")
                if isinstance(plan_meta.get("manifest_effective"), dict)
                else load_json_mapping(root / "docs/.doc-manifest.json")
            ) or {}
            facts_data = load_json_mapping(root / "docs/.repo-facts.json") or {}
            try:
                _, agents_generation_report = doc_agents.generate_agents_artifacts(
                    root=root,
                    policy=effective_policy,
                    manifest=manifest_data,
                    facts=facts_data,
                    output_path=root / "AGENTS.md",
                    report_path=root / "docs/.agents-report.json",
                    dry_run=args.dry_run,
                    force=False,
                )
                if agents_generation_report.get("status") == "generated":
                    details = "AGENTS generated from policy/manifest/index/facts"
                    if agents_mode == "deterministic":
                        details = "AGENTS generated from deterministic mode"
                    elif isinstance(agents_runtime_payload, dict):
                        write_text(
                            root / "AGENTS.md",
                            str(agents_runtime_payload.get("content", "")),
                            args.dry_run,
                        )
                        details = "AGENTS generated from runtime semantic candidate"
                        if isinstance(agents_runtime_result, dict):
                            agents_runtime_result["status"] = "agents_runtime_applied"
                    elif agents_runtime_enabled and agents_runtime_gate_failures:
                        details = (
                            "AGENTS generated via deterministic fallback "
                            f"(reason={agents_fallback_reason})"
                        )
                        if isinstance(agents_runtime_result, dict):
                            agents_runtime_result["status"] = "agents_runtime_gate_failed"
                    if isinstance(agents_generation_report, dict) and isinstance(
                        agents_runtime_result, dict
                    ):
                        agents_generation_report["semantic_runtime"] = dict(
                            agents_runtime_result
                        )
                    agent_result: dict[str, Any] = {
                        "id": "AGENTS",
                        "type": "agents_generate",
                        "path": "AGENTS.md",
                        "status": "applied",
                        "details": details,
                    }
                    if isinstance(agents_runtime_result, dict):
                        agent_result["semantic_runtime"] = dict(agents_runtime_result)
                    results.append(agent_result)
            except Exception as exc:  # noqa: BLE001
                error_result: dict[str, Any] = {
                    "id": "AGENTS",
                    "type": "agents_generate",
                    "path": "AGENTS.md",
                    "status": "error",
                    "details": f"agents generation failed: {exc}",
                }
                if isinstance(agents_runtime_result, dict):
                    error_result["semantic_runtime"] = dict(agents_runtime_result)
                results.append(error_result)

    summary = {
        "total_actions": len(results),
        "applied": sum(1 for r in results if r["status"] == "applied"),
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
        "errors": sum(1 for r in results if r["status"] == "error"),
    }
    semantic_observability = summarize_semantic_observability(results, semantic_settings)
    summary.update(
        {
            "semantic_action_count": semantic_observability["semantic_action_count"],
            "semantic_attempt_count": semantic_observability["semantic_attempt_count"],
            "semantic_success_count": semantic_observability["semantic_success_count"],
            "fallback_count": semantic_observability["fallback_count"],
            "fallback_reason_breakdown": semantic_observability[
                "fallback_reason_breakdown"
            ],
            "runtime_quality_grade_distribution": semantic_observability[
                "runtime_quality_grade_distribution"
            ],
            "runtime_quality_decision_breakdown": semantic_observability[
                "runtime_quality_decision_breakdown"
            ],
            "runtime_quality_degraded_count": semantic_observability[
                "runtime_quality_degraded_count"
            ],
            "semantic_hit_rate": semantic_observability["semantic_hit_rate"],
            "semantic_unattempted_count": semantic_observability[
                "semantic_unattempted_count"
            ],
            "semantic_exempt_count": semantic_observability["semantic_exempt_count"],
            "semantic_unattempted_without_exemption": semantic_observability[
                "semantic_unattempted_without_exemption"
            ],
        }
    )

    report = {
        "generated_at": utc_now(),
        "root": str(root),
        "mode": args.mode,
        "dry_run": args.dry_run,
        "language": {
            "primary": language_settings["primary"],
            "profile": language_settings["profile"],
            "locked": language_settings["locked"],
            "source": language_settings["source"],
            "policy_language_updated": policy_language_updated,
        },
        "summary": summary,
        "results": results,
        "semantic_runtime": {
            "settings": semantic_settings,
            "runtime": semantic_runtime_state,
        },
        "semantic_observability": semantic_observability,
        "agents_generation": agents_generation_report
        or {
            "status": "skipped",
            "enabled": agents_settings.get("enabled", False),
            "triggered": should_generate_agents,
        },
    }

    json_path = (
        (root / args.report_json).resolve() if not Path(args.report_json).is_absolute() else Path(args.report_json)
    )
    md_path = (root / args.report_md).resolve() if not Path(args.report_md).is_absolute() else Path(args.report_md)

    if not args.dry_run:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            f.write("\n")

        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_markdown_report(report), encoding="utf-8")

    print(f"[OK] Processed {summary['total_actions']} actions")
    print(f"[INFO] Applied={summary['applied']} Skipped={summary['skipped']} Errors={summary['errors']}")
    print(
        "[INFO] Language primary="
        f"{language_settings['primary']} profile={language_settings['profile']} source={language_settings['source']}"
    )
    print(
        "[INFO] Semantic runtime "
        f"enabled={semantic_settings.get('enabled')} "
        f"mode={semantic_settings.get('mode')} "
        f"available={semantic_runtime_state.get('available')} "
        f"entries={semantic_runtime_state.get('entry_count')}"
    )

    return 1 if summary["errors"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
