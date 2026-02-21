#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import string
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import doc_spec  # noqa: E402
import language_profiles as lp  # noqa: E402


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


def _extract_runbook_section_commands(root: Path, section_id: str) -> list[str]:
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

    # Keep ordering stable while removing accidental duplicates.
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
    root: Path | None = None,
    runbook_cache: dict[str, list[str]] | None = None,
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
        if root is None:
            return None
        section_key = evidence_type.split(".", 1)[1]
        if section_key not in {"dev_commands", "validation_commands"}:
            return None
        cache = runbook_cache if isinstance(runbook_cache, dict) else {}
        if section_key not in cache:
            cache[section_key] = _extract_runbook_section_commands(root, section_key)
        return cache.get(section_key)

    return None


def evidence_is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict, str)):
        return len(value) == 0
    return False


def summarize_evidence(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    if isinstance(value, dict):
        if not value:
            return "UNKNOWN"
        if all(isinstance(v, bool) for v in value.values()):
            keys = [k for k, v in value.items() if v]
            return ", ".join(keys) if keys else "none"
        return ", ".join(f"{k}:{v}" for k, v in value.items())
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "UNKNOWN"
    return str(value)


def build_citation_token(evidence_type: str) -> str:
    return f"evidence://{evidence_type}"


def build_citations(evidence_items: list[dict[str, Any]]) -> list[str]:
    citations: list[str] = []
    seen: set[str] = set()
    for item in evidence_items:
        evidence_type = item.get("type")
        if not isinstance(evidence_type, str) or not evidence_type:
            continue
        token = build_citation_token(evidence_type)
        if token in seen:
            continue
        seen.add(token)
        citations.append(token)
    return citations


def render_statement(template: str, value: str) -> str:
    if not isinstance(template, str) or not template:
        return value
    formatter = string.Formatter()
    fields = [field for _, field, _, _ in formatter.parse(template) if field]
    if not fields:
        return template
    replacements = {field: value for field in fields}
    try:
        return template.format(**replacements)
    except Exception:  # noqa: BLE001
        return template


def build_claim_entry(
    claim: dict[str, Any],
    facts: dict[str, Any] | None,
    root: Path | None = None,
    runbook_cache: dict[str, list[str]] | None = None,
) -> tuple[dict[str, Any], str]:
    claim_id = claim.get("claim_id", "")
    statement_template = claim.get("statement_template", "")
    allow_unknown = bool(claim.get("allow_unknown", False))
    required_types = claim.get("required_evidence_types") or []
    missing_types: list[str] = []
    evidence_items: list[dict[str, Any]] = []

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
        else:
            evidence_items.append({"type": evidence_type, "value": value})

    if missing_types:
        status = "unknown" if allow_unknown else "missing"
        fill_value = "UNKNOWN" if allow_unknown else "TODO"
        statement = render_statement(statement_template, fill_value)
    else:
        status = "supported"
        summary = "UNKNOWN"
        if evidence_items:
            summary = summarize_evidence(evidence_items[0]["value"])
        statement = render_statement(statement_template, summary)

    citations = build_citations(evidence_items)
    entry = {
        "claim_id": claim_id,
        "status": status,
        "statement": statement,
        "statement_template": statement_template,
        "required_evidence_types": required_types,
        "missing_evidence_types": missing_types,
        "allow_unknown": allow_unknown,
        "evidence": evidence_items,
        "citations": citations,
        "citation": citations[0] if citations else None,
    }
    return entry, status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Synthesize doc claim statements with evidence bindings."
    )
    parser.add_argument("--root", required=True, help="Repository root")
    parser.add_argument(
        "--plan",
        default="docs/.doc-plan.json",
        help="Doc plan input (metadata only)",
    )
    parser.add_argument(
        "--spec", default="docs/.doc-spec.json", help="Doc spec path"
    )
    parser.add_argument(
        "--facts", default="docs/.repo-facts.json", help="Evidence pack"
    )
    parser.add_argument(
        "--output",
        default="docs/.doc-evidence-map.json",
        help="Evidence map output path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"[ERROR] Invalid root path: {root}")

    plan_path = (root / args.plan).resolve() if not Path(args.plan).is_absolute() else Path(args.plan)
    spec_path = (root / args.spec).resolve() if not Path(args.spec).is_absolute() else Path(args.spec)
    facts_path = (root / args.facts).resolve() if not Path(args.facts).is_absolute() else Path(args.facts)
    output_path = (root / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)

    plan = load_json(plan_path) or {}
    facts = load_json(facts_path)

    spec_data, spec_errors, spec_warnings = doc_spec.load_spec(spec_path)
    if spec_data is None:
        report = {
            "generated_at": utc_now(),
            "root": str(root),
            "plan": str(plan_path),
            "spec": str(spec_path),
            "facts": str(facts_path),
            "plan_meta": plan.get("meta", {}),
            "doc_spec": {
                "exists": False,
                "errors": [],
                "warnings": ["doc-spec missing; synthesis skipped"],
            },
            "metrics": {"claims": 0, "supported": 0, "unknown": 0, "missing": 0},
            "documents": [],
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"[OK] Wrote evidence map to {output_path}")
        print("[INFO] claims=0 supported=0 unknown=0 missing=0")
        print("[WARN] doc-spec missing; evidence synthesis skipped")
        return 0
    if spec_errors:
        raise SystemExit(
            "[ERROR] doc-spec validation failed: " + ", ".join(spec_errors)
        )

    documents_output: list[dict[str, Any]] = []
    metrics = {"claims": 0, "supported": 0, "unknown": 0, "missing": 0}
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
                claim_entry, status = build_claim_entry(
                    claim,
                    facts,
                    root=root,
                    runbook_cache=runbook_cache,
                )
                claim_outputs.append(claim_entry)
                metrics["claims"] += 1
                metrics[status] += 1

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

    report = {
        "generated_at": utc_now(),
        "root": str(root),
        "plan": str(plan_path),
        "spec": str(spec_path),
        "facts": str(facts_path),
        "plan_meta": plan.get("meta", {}),
        "doc_spec": {
            "errors": spec_errors,
            "warnings": spec_warnings,
        },
        "metrics": metrics,
        "documents": documents_output,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[OK] Wrote evidence map to {output_path}")
    print(
        "[INFO] claims="
        f"{metrics['claims']} supported={metrics['supported']} unknown={metrics['unknown']} missing={metrics['missing']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
