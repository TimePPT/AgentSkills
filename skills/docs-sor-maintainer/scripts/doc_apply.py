#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import doc_capabilities as dc  # noqa: E402
import doc_metadata as dm  # noqa: E402
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


def apply_action(
    root: Path,
    action: dict[str, Any],
    dry_run: bool,
    language_settings: dict[str, Any],
    template_profile: str,
    metadata_policy: dict[str, Any],
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

        if action_type == "archive":
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

            result["status"] = "applied"
            result["details"] = f"archived from {source_rel}"
            return result

        if action_type in {"manual_review", "keep"}:
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
    }:
        raise SystemExit(f"[ERROR] Unsupported plan mode: {plan_mode}")

    if plan_mode == "audit" and args.mode != "apply-safe":
        print("[WARN] Applying an audit plan with mode != apply-safe is not recommended.")

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
        )
        for action in actions
    ]

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

    return 1 if summary["errors"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
