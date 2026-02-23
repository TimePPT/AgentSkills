#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
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

    required_prefixes_raw = semantic_settings.get("required_evidence_prefixes")
    required_prefixes = [
        str(value).strip()
        for value in (
            required_prefixes_raw if isinstance(required_prefixes_raw, list) else []
        )
        if isinstance(value, str) and str(value).strip()
    ]
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

    deduped_failures: list[str] = []
    seen: set[str] = set()
    for failure in failed_checks:
        if failure in seen:
            continue
        seen.add(failure)
        deduped_failures.append(failure)
    if deduped_failures:
        return None, deduped_failures

    return {
        "statement": statement,
        "citations": citations,
    }, []


def resolve_update_section_runtime_payload(
    runtime_entry: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(runtime_entry, dict):
        return None, ["runtime_entry_not_found"]

    failed_checks: list[str] = []
    if runtime_entry.get("status") != "ok":
        failed_checks.append("runtime_status_not_ok")

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

    deduped_failures: list[str] = []
    seen: set[str] = set()
    for failure in failed_checks:
        if failure in seen:
            continue
        seen.add(failure)
        deduped_failures.append(failure)
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


def apply_action(
    root: Path,
    action: dict[str, Any],
    dry_run: bool,
    language_settings: dict[str, Any],
    template_profile: str,
    metadata_policy: dict[str, Any],
    legacy_settings: dict[str, Any] | None = None,
    semantic_settings: dict[str, Any] | None = None,
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
    runtime_entries = (
        semantic_runtime_entries if isinstance(semantic_runtime_entries, list) else []
    )
    runtime_state = (
        semantic_runtime_state if isinstance(semantic_runtime_state, dict) else {}
    )

    def attach_runtime_candidate() -> dict[str, Any] | None:
        if not isinstance(action_type, str):
            return None
        if not dsr.should_attempt_runtime_semantics(action_type, semantic_cfg):
            return None
        candidate = dsr.select_runtime_entry(action, runtime_entries, semantic_cfg)
        if isinstance(candidate, dict):
            result["semantic_runtime"] = {
                "status": "candidate_loaded",
                "entry_id": candidate.get("entry_id"),
                "candidate_status": candidate.get("status"),
                "mode": semantic_cfg.get("mode"),
                "source": semantic_cfg.get("source"),
            }
            return candidate

        state_status = (
            "runtime_unavailable"
            if not runtime_state.get("available", False)
            else "entry_not_found"
        )
        state_error = runtime_state.get("error")
        semantic_state: dict[str, Any] = {
            "status": state_status,
            "mode": semantic_cfg.get("mode"),
            "source": semantic_cfg.get("source"),
        }
        if isinstance(state_error, str) and state_error.strip():
            semantic_state["error"] = state_error.strip()
        result["semantic_runtime"] = semantic_state
        return None

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
            runtime_candidate = attach_runtime_candidate()
            section_id = action.get("section_id")
            section_heading = action.get("section_heading")
            section_id_str = (
                section_id.strip() if isinstance(section_id, str) and section_id.strip() else ""
            )

            runtime_payload = None
            runtime_gate_failures: list[str] = []
            if isinstance(runtime_candidate, dict):
                runtime_payload, runtime_gate_failures = resolve_update_section_runtime_payload(
                    runtime_candidate
                )
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
                    result["details"] = (
                        f"runtime gate failed; fallback section scaffold upserted: {heading}"
                    )
                else:
                    result["details"] = f"section upserted: {heading}"
            else:
                if runtime_gate_failures:
                    result["details"] = (
                        "runtime gate failed; section already present or unsupported section_id"
                    )
                else:
                    result["details"] = "section already present or unsupported section_id"
            return result

        if action_type == "fill_claim":
            runtime_candidate = attach_runtime_candidate()
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
            runtime_gate_failures: list[str] = []
            if isinstance(runtime_candidate, dict):
                runtime_payload, runtime_gate_failures = resolve_fill_claim_runtime_payload(
                    action,
                    runtime_candidate,
                    semantic_cfg,
                )
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
                    result["details"] = (
                        f"runtime gate failed; fallback claim TODO appended: {claim_id_str}"
                    )
                else:
                    result["details"] = f"claim TODO appended: {claim_id_str}"
            else:
                if runtime_gate_failures:
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
            runtime_candidate = attach_runtime_candidate()
            section_id = action.get("section_id")
            section_id_str = (
                section_id.strip() if isinstance(section_id, str) and section_id.strip() else ""
            )
            section_heading = action.get("section_heading")
            runtime_payload = None
            runtime_gate_failures: list[str] = []
            if isinstance(runtime_candidate, dict):
                runtime_payload, runtime_gate_failures = resolve_update_section_runtime_payload(
                    runtime_candidate
                )
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

            source_rel = normalize(action.get("source_path", ""))
            backlog_reason = action.get("backlog_reason")
            details = "semantic rewrite deferred to runtime/manual workflow"
            if isinstance(backlog_reason, str) and backlog_reason.strip():
                details += f": reason={backlog_reason.strip()}"
            if source_rel:
                details += f", source={source_rel}"
            if runtime_gate_failures:
                details += ", runtime gate failed"
            result["status"] = "applied"
            result["details"] = details
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

            archive_rel = normalize(action.get("archive_path", ""))
            if not archive_rel:
                archive_rel = dl.resolve_archive_path(source_rel, legacy_cfg)
            marker = dl.source_marker(source_rel)
            semantic_patch = resolve_legacy_semantic_patch(action)

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

            source_content = read_text_lossy(source_abs)
            entry = dl.render_structured_migration_entry(
                source_rel=source_rel,
                source_content=source_content,
                archive_path=archive_rel,
                template_profile=template_profile,
                semantic={
                    "category": action.get("semantic_category"),
                    "confidence": action.get("semantic_confidence"),
                },
                evidence=action.get("evidence") if isinstance(action.get("evidence"), list) else None,
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
            semantic_runtime_entries,
            semantic_runtime_state,
        )
        for action in actions
    ]

    plan_meta = plan.get("meta") if isinstance(plan.get("meta"), dict) else {}
    agents_settings = doc_agents.resolve_agents_settings(effective_policy)
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
    should_generate_agents = (
        agents_settings.get("enabled", False)
        and (
            args.mode == "bootstrap"
            or agents_add_applied
            or agents_missing
            or (
                agents_settings.get("sync_on_manifest_change", True)
                and (manifest_changed or sync_manifest_applied)
            )
        )
    )

    agents_runtime_candidate: dict[str, Any] | None = None
    agents_runtime_result: dict[str, Any] | None = None
    if dsr.should_attempt_runtime_semantics("agents_generate", semantic_settings):
        agents_runtime_candidate = dsr.select_runtime_entry(
            {"type": "agents_generate", "path": "AGENTS.md"},
            semantic_runtime_entries,
            semantic_settings,
        )
        if isinstance(agents_runtime_candidate, dict):
            agents_runtime_result = {
                "status": "candidate_loaded",
                "entry_id": agents_runtime_candidate.get("entry_id"),
                "candidate_status": agents_runtime_candidate.get("status"),
                "mode": semantic_settings.get("mode"),
                "source": semantic_settings.get("source"),
            }
        else:
            state_status = (
                "runtime_unavailable"
                if not semantic_runtime_state.get("available", False)
                else "entry_not_found"
            )
            agents_runtime_result = {
                "status": state_status,
                "mode": semantic_settings.get("mode"),
                "source": semantic_settings.get("source"),
            }
            state_error = semantic_runtime_state.get("error")
            if isinstance(state_error, str) and state_error.strip():
                agents_runtime_result["error"] = state_error.strip()

    agents_generation_report: dict[str, Any] | None = None
    if should_generate_agents:
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
                if isinstance(agents_runtime_candidate, dict):
                    runtime_payload, runtime_gate_failures = resolve_agents_runtime_payload(
                        agents_runtime_candidate
                    )
                    if isinstance(agents_runtime_result, dict):
                        agents_runtime_result["gate"] = {
                            "status": "passed" if runtime_payload else "failed",
                            "failed_checks": runtime_gate_failures,
                        }
                        agents_runtime_result["consumed"] = bool(runtime_payload)
                    if runtime_payload:
                        write_text(
                            root / "AGENTS.md",
                            str(runtime_payload.get("content", "")),
                            args.dry_run,
                        )
                        details = "AGENTS generated from runtime semantic candidate"
                        if isinstance(agents_runtime_result, dict):
                            agents_runtime_result["status"] = "agents_runtime_applied"
                    else:
                        details = (
                            "AGENTS generated via deterministic fallback (runtime gate failed)"
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
