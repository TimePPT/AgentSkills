#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import doc_spec  # noqa: E402
import doc_synthesize  # noqa: E402


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
    todo_count = sum(
        1
        for c in claims
        if isinstance(c.get("statement"), str)
        and "TODO" in c.get("statement")
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

    quality_policy = policy.get("doc_quality_gates")
    quality_policy = quality_policy if isinstance(quality_policy, dict) else {}
    enabled = bool(quality_policy.get("enabled", False))

    thresholds = {
        "min_evidence_coverage": quality_policy.get("min_evidence_coverage", 0.0),
        "max_conflicts": quality_policy.get("max_conflicts", 0),
        "max_unknown_claims": quality_policy.get("max_unknown_claims", 0),
        "max_unresolved_todo": quality_policy.get("max_unresolved_todo", 0),
        "max_stale_metrics_days": quality_policy.get("max_stale_metrics_days", 0),
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
        unresolved_todo = todo_count + missing
        if unresolved_todo > int(thresholds["max_unresolved_todo"]):
            failed_checks.append("max_unresolved_todo")
        max_stale = thresholds["max_stale_metrics_days"]
        if isinstance(max_stale, int) and max_stale > 0:
            if facts_age_days is None or facts_age_days > max_stale:
                failed_checks.append("max_stale_metrics_days")

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
            "unresolved_todo": todo_count + missing,
            "evidence_coverage": evidence_coverage,
            "conflicts": len(conflicts),
            "citation_issues": len(citation_issues),
            "facts_age_days": facts_age_days,
        },
        "conflicts": conflicts,
        "citation_issues": citation_issues,
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
