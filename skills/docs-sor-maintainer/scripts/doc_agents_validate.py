#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import doc_agents


LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
SCRIPT_REF_PATTERN = re.compile(r"scripts/([A-Za-z0-9_]+\.py)")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize(path_str: str) -> str:
    return str(Path(path_str)).replace("\\", "/")


def load_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def heading_present(content: str, candidates: list[str]) -> bool:
    return any(candidate in content for candidate in candidates)


def extract_links(content: str) -> list[str]:
    out: list[str] = []
    for match in LINK_PATTERN.finditer(content):
        link = match.group(1).strip()
        if link:
            out.append(link)
    return out


def resolve_target(root: Path, link: str) -> Path:
    target = link.split("#", 1)[0].strip()
    if target.startswith("./"):
        return (root / target[2:]).resolve()
    if target.startswith("../"):
        return (root / target).resolve()
    if target.startswith("/"):
        return Path(target)
    return (root / target).resolve()


def normalize_line(line: str) -> str:
    text = line.strip().lower()
    text = re.sub(r"`+", "", text)
    text = re.sub(r"\[[^\]]+\]\(([^)]+)\)", r"\1", text)
    text = re.sub(r"^[#>\-\d\.\s]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def overlap_ratio(a: str, b: str) -> float:
    lines_a = {normalize_line(line) for line in a.splitlines()}
    lines_b = {normalize_line(line) for line in b.splitlines()}
    lines_a = {line for line in lines_a if len(line) >= 6}
    lines_b = {line for line in lines_b if len(line) >= 6}
    if not lines_a or not lines_b:
        return 0.0
    inter = lines_a & lines_b
    return len(inter) / max(1, min(len(lines_a), len(lines_b)))


def evaluate_agents(
    root: Path,
    policy: dict[str, Any],
    agents_path: Path,
    index_path: Path,
) -> dict[str, Any]:
    settings = doc_agents.resolve_agents_settings(policy)
    required_links = settings.get("required_links") or []
    overlap_threshold = float(settings.get("max_overlap_ratio", 0.7))

    errors: list[str] = []
    warnings: list[str] = []
    failed_checks: list[str] = []

    if not agents_path.exists():
        errors.append(f"AGENTS.md not found: {normalize(agents_path.relative_to(root))}")
        failed_checks.append("agents_file_exists")
        return {
            "generated_at": utc_now(),
            "root": str(root),
            "enabled": settings.get("enabled", False),
            "settings": settings,
            "gate": {"status": "failed", "failed_checks": failed_checks},
            "errors": errors,
            "warnings": warnings,
            "metrics": {
                "line_count": 0,
                "missing_headings": 4,
                "missing_required_links": len(required_links),
                "broken_links": 0,
                "invalid_script_refs": 0,
                "overlap_ratio": 0.0,
            },
        }

    content = load_text(agents_path)

    heading_map = {
        "purpose": ["## 目标", "## Purpose"],
        "navigation": ["## 导航", "## Navigation"],
        "commands": ["## 标准命令", "## Standard Commands"],
        "guardrails": ["## Guardrails"],
    }
    missing_headings = []
    if "# AGENTS" not in content:
        missing_headings.append("# AGENTS")
    for key, candidates in heading_map.items():
        if not heading_present(content, candidates):
            missing_headings.append(key)
    if missing_headings:
        errors.append(f"missing AGENTS headings: {', '.join(missing_headings)}")
        failed_checks.append("required_headings")

    links = extract_links(content)
    broken_links = []
    for link in links:
        if link.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = resolve_target(root, link)
        if not target.exists():
            broken_links.append(link)
    if broken_links:
        errors.append(f"broken AGENTS links: {', '.join(sorted(set(broken_links)))}")
        failed_checks.append("dead_links")

    missing_required_links = []
    for rel in required_links:
        candidates = {rel, f"./{rel}"}
        found = any(link in candidates for link in links) or rel in content
        if not found:
            missing_required_links.append(rel)
    if missing_required_links:
        errors.append(
            f"missing required AGENTS links: {', '.join(missing_required_links)}"
        )
        failed_checks.append("required_links")

    invalid_script_refs = []
    script_refs = sorted(set(SCRIPT_REF_PATTERN.findall(content)))
    for script_name in script_refs:
        candidates = [
            root / f".agents/skills/docs-sor-maintainer/scripts/{script_name}",
            root / f"skills/docs-sor-maintainer/scripts/{script_name}",
        ]
        if not any(candidate.exists() for candidate in candidates):
            invalid_script_refs.append(script_name)
    if invalid_script_refs:
        errors.append(
            f"invalid script refs in AGENTS commands: {', '.join(invalid_script_refs)}"
        )
        failed_checks.append("command_paths")

    index_text = load_text(index_path)
    ratio = overlap_ratio(content, index_text) if index_text else 0.0
    if ratio > overlap_threshold:
        warnings.append(
            f"AGENTS/index overlap ratio is high: {ratio:.2f} > {overlap_threshold:.2f}"
        )
        failed_checks.append("overlap_ratio")

    status = "failed" if failed_checks else "passed"
    return {
        "generated_at": utc_now(),
        "root": str(root),
        "enabled": settings.get("enabled", False),
        "settings": settings,
        "gate": {
            "status": status,
            "failed_checks": failed_checks,
        },
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "line_count": len(content.splitlines()),
            "missing_headings": len(missing_headings),
            "missing_required_links": len(missing_required_links),
            "broken_links": len(broken_links),
            "invalid_script_refs": len(invalid_script_refs),
            "overlap_ratio": ratio,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate AGENTS.md quality gates.")
    parser.add_argument("--root", required=True, help="Repository root")
    parser.add_argument("--policy", default="docs/.doc-policy.json", help="Policy path")
    parser.add_argument("--agents", default="AGENTS.md", help="AGENTS path")
    parser.add_argument("--index", default="docs/index.md", help="Docs index path")
    parser.add_argument(
        "--output",
        default="docs/.agents-validate-report.json",
        help="Output report path",
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
    agents_path = (
        (root / args.agents).resolve()
        if not Path(args.agents).is_absolute()
        else Path(args.agents)
    )
    index_path = (
        (root / args.index).resolve()
        if not Path(args.index).is_absolute()
        else Path(args.index)
    )
    output_path = (
        (root / args.output).resolve()
        if not Path(args.output).is_absolute()
        else Path(args.output)
    )

    policy = doc_agents.load_json_mapping(policy_path) or {}
    report = evaluate_agents(root, policy, agents_path, index_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[OK] Wrote AGENTS validate report to {output_path}")
    print(
        "[INFO] "
        f"errors={len(report.get('errors', []))} warnings={len(report.get('warnings', []))} status={report.get('gate', {}).get('status')}"
    )
    return 0 if report.get("gate", {}).get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
