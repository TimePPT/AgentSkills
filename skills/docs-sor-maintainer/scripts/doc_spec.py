#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_rel(path_str: str) -> str:
    return str(Path(path_str)).replace("\\", "/")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"doc-spec JSON root must be object: {path}")
    return data


def _ensure_string(value: Any, label: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} must be non-empty string")
        return ""
    return value.strip()


def _ensure_string_list(
    value: Any, label: str, errors: list[str], allow_empty: bool = True
) -> list[str]:
    if value is None:
        if not allow_empty:
            errors.append(f"{label} must be list of strings")
        return []
    if not isinstance(value, list):
        errors.append(f"{label} must be list of strings")
        return []
    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{label}[{index}] must be non-empty string")
            continue
        items.append(item.strip())
    return items


def validate_spec(spec: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    version = spec.get("version")
    if not isinstance(version, int):
        errors.append("version must be integer")
    elif version <= 0:
        errors.append("version must be positive")

    documents = spec.get("documents")
    if not isinstance(documents, list) or not documents:
        errors.append("documents must be non-empty list")
        return errors, warnings

    seen_paths: set[str] = set()

    for doc_index, doc in enumerate(documents):
        doc_label = f"documents[{doc_index}]"
        if not isinstance(doc, dict):
            errors.append(f"{doc_label} must be object")
            continue

        path_value = doc.get("path")
        path = _ensure_string(path_value, f"{doc_label}.path", errors)
        if path:
            normalized = normalize_rel(path)
            if normalized != path:
                errors.append(f"{doc_label}.path must be POSIX style: {path}")
            if normalized in seen_paths:
                errors.append(f"{doc_label}.path duplicated: {normalized}")
            seen_paths.add(normalized)

        required_sections = _ensure_string_list(
            doc.get("required_sections"),
            f"{doc_label}.required_sections",
            errors,
            allow_empty=True,
        )
        render_order = doc.get("render_order")
        render_order_list = _ensure_string_list(
            render_order, f"{doc_label}.render_order", errors, allow_empty=True
        )

        sections = doc.get("sections")
        if not isinstance(sections, list) or not sections:
            errors.append(f"{doc_label}.sections must be non-empty list")
            continue

        section_ids: set[str] = set()
        doc_claim_ids: set[str] = set()
        for sec_index, section in enumerate(sections):
            sec_label = f"{doc_label}.sections[{sec_index}]"
            if not isinstance(section, dict):
                errors.append(f"{sec_label} must be object")
                continue

            section_id = _ensure_string(
                section.get("section_id"), f"{sec_label}.section_id", errors
            )
            if section_id:
                if section_id in section_ids:
                    errors.append(f"{sec_label}.section_id duplicated: {section_id}")
                section_ids.add(section_id)

            claims = section.get("claims")
            if not isinstance(claims, list) or not claims:
                errors.append(f"{sec_label}.claims must be non-empty list")
                continue

            claim_ids: set[str] = set()
            for claim_index, claim in enumerate(claims):
                claim_label = f"{sec_label}.claims[{claim_index}]"
                if not isinstance(claim, dict):
                    errors.append(f"{claim_label} must be object")
                    continue

                claim_id = _ensure_string(
                    claim.get("claim_id"), f"{claim_label}.claim_id", errors
                )
                if claim_id:
                    if claim_id in claim_ids:
                        errors.append(
                            f"{claim_label}.claim_id duplicated in section: {claim_id}"
                        )
                    if claim_id in doc_claim_ids:
                        errors.append(
                            f"{claim_label}.claim_id duplicated in document: {claim_id}"
                        )
                    claim_ids.add(claim_id)
                    doc_claim_ids.add(claim_id)

                _ensure_string(
                    claim.get("statement_template"),
                    f"{claim_label}.statement_template",
                    errors,
                )
                evidence_types = _ensure_string_list(
                    claim.get("required_evidence_types"),
                    f"{claim_label}.required_evidence_types",
                    errors,
                    allow_empty=False,
                )
                if not evidence_types:
                    errors.append(
                        f"{claim_label}.required_evidence_types must be non-empty"
                    )

                allow_unknown = claim.get("allow_unknown")
                if not isinstance(allow_unknown, bool):
                    errors.append(f"{claim_label}.allow_unknown must be boolean")

        if required_sections:
            missing_required = [s for s in required_sections if s not in section_ids]
            if missing_required:
                errors.append(
                    f"{doc_label}.required_sections missing definitions: {', '.join(missing_required)}"
                )

        if render_order_list:
            missing_in_order = [s for s in render_order_list if s not in section_ids]
            if missing_in_order:
                errors.append(
                    f"{doc_label}.render_order missing sections: {', '.join(missing_in_order)}"
                )

    return errors, warnings


def load_spec(path: Path) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    if not path.exists():
        return None, [], []
    data = _load_json(path)
    errors, warnings = validate_spec(data)
    return data, errors, warnings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate doc-spec schema.")
    parser.add_argument("--root", required=True, help="Repository root")
    parser.add_argument(
        "--spec", default="docs/.doc-spec.json", help="Doc spec path"
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output report path (JSON)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"[ERROR] Invalid root path: {root}")

    spec_path = (
        (root / args.spec).resolve()
        if not Path(args.spec).is_absolute()
        else Path(args.spec)
    )

    spec, errors, warnings = load_spec(spec_path)
    report = {
        "generated_at": utc_now(),
        "root": str(root),
        "spec_path": normalize_rel(spec_path.relative_to(root)),
        "spec_exists": spec is not None,
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }

    if args.output:
        output_path = (
            (root / args.output).resolve()
            if not Path(args.output).is_absolute()
            else Path(args.output)
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"[OK] Wrote doc-spec report to {output_path}")

    print(
        f"[INFO] spec_exists={report['spec_exists']} errors={len(errors)} warnings={len(warnings)}"
    )

    return 0 if len(errors) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
