#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_GARDENING_POLICY = {
    "enabled": True,
    "apply_mode": "apply-safe",
    "fail_on_drift": True,
    "fail_on_freshness": True,
    "report_json": "docs/.doc-garden-report.json",
    "report_md": "docs/.doc-garden-report.md",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize(path_str: str) -> str:
    return str(Path(path_str)).replace("\\", "/")


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


def resolve_doc_gardening_settings(policy: dict[str, Any] | None) -> dict[str, Any]:
    policy_data = policy if isinstance(policy, dict) else {}
    raw = policy_data.get("doc_gardening")
    if not isinstance(raw, dict):
        return dict(DEFAULT_GARDENING_POLICY)

    settings = dict(DEFAULT_GARDENING_POLICY)
    settings["enabled"] = bool(raw.get("enabled", settings["enabled"]))
    apply_mode = raw.get("apply_mode")
    if isinstance(apply_mode, str) and apply_mode in {
        "none",
        "apply-safe",
        "apply-with-archive",
    }:
        settings["apply_mode"] = apply_mode
    settings["fail_on_drift"] = bool(
        raw.get("fail_on_drift", settings["fail_on_drift"])
    )
    settings["fail_on_freshness"] = bool(
        raw.get("fail_on_freshness", settings["fail_on_freshness"])
    )

    for key in ("report_json", "report_md"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            settings[key] = value.strip()
    return settings


def resolve_bool(cli_true: bool, cli_false: bool, default: bool) -> bool:
    if cli_true:
        return True
    if cli_false:
        return False
    return default


def run_step(step_name: str, cmd: list[str], cwd: Path) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    finished = datetime.now(timezone.utc)
    return {
        "name": step_name,
        "command": cmd,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "status": "ok" if proc.returncode == 0 else "failed",
    }


def load_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def render_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Doc Garden Report",
        "",
        f"- Generated at: {report.get('generated_at')}",
        f"- Root: {report.get('root')}",
        f"- Status: {report.get('summary', {}).get('status')}",
        f"- Apply mode: {report.get('summary', {}).get('apply_mode')}",
        "",
        "## Steps",
        "",
    ]

    for step in report.get("steps", []):
        lines.append(
            f"- `{step.get('name')}` rc={step.get('returncode')} status={step.get('status')}"
        )

    plan = report.get("plan") or {}
    if plan:
        lines.extend(
            [
                "",
                "## Plan",
                "",
                f"- Action count: {plan.get('action_count', 0)}",
                f"- Action types: {json.dumps(plan.get('action_counts', {}), ensure_ascii=False)}",
            ]
        )

    validate = report.get("validate") or {}
    if validate:
        lines.extend(
            [
                "",
                "## Validate",
                "",
                f"- Passed: {validate.get('passed')}",
                f"- Errors: {validate.get('errors')}",
                f"- Warnings: {validate.get('warnings')}",
                f"- Drift actions: {validate.get('drift_action_count')}",
                f"- Metadata stale docs: {validate.get('metadata_stale_docs')}",
            ]
        )

    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run automated docs gardening workflow (scan/plan/apply/validate)."
    )
    parser.add_argument("--root", required=True, help="Repository root")
    parser.add_argument(
        "--facts", default="docs/.repo-facts.json", help="Facts output path"
    )
    parser.add_argument(
        "--plan", default="docs/.doc-plan.json", help="Plan output path"
    )
    parser.add_argument(
        "--plan-mode",
        choices=["audit", "apply-with-archive"],
        default="audit",
        help="Planning mode used by gardening run",
    )
    parser.add_argument(
        "--apply-mode",
        choices=["none", "apply-safe", "apply-with-archive"],
        help="Apply mode override; defaults to policy doc_gardening.apply_mode",
    )
    parser.add_argument(
        "--init-language", help="Optional init language passed to doc_apply"
    )
    parser.add_argument(
        "--skip-validate", action="store_true", help="Skip validate step"
    )
    parser.add_argument(
        "--fail-on-drift", action="store_true", help="Force validate with drift gate"
    )
    parser.add_argument(
        "--no-fail-on-drift", action="store_true", help="Disable drift gate"
    )
    parser.add_argument(
        "--fail-on-freshness",
        action="store_true",
        help="Force validate with freshness gate",
    )
    parser.add_argument(
        "--no-fail-on-freshness", action="store_true", help="Disable freshness gate"
    )
    parser.add_argument("--report-json", help="Garden report JSON path override")
    parser.add_argument("--report-md", help="Garden report Markdown path override")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"[ERROR] Invalid root path: {root}")

    policy_path = root / "docs/.doc-policy.json"
    policy = load_json_mapping(policy_path)
    gardening_settings = resolve_doc_gardening_settings(policy)

    apply_mode = args.apply_mode or gardening_settings["apply_mode"]
    fail_on_drift = resolve_bool(
        args.fail_on_drift, args.no_fail_on_drift, gardening_settings["fail_on_drift"]
    )
    fail_on_freshness = resolve_bool(
        args.fail_on_freshness,
        args.no_fail_on_freshness,
        gardening_settings["fail_on_freshness"],
    )

    facts_rel = normalize(args.facts)
    plan_rel = normalize(args.plan)
    report_json_rel = normalize(args.report_json or gardening_settings["report_json"])
    report_md_rel = normalize(args.report_md or gardening_settings["report_md"])

    facts_abs = root / facts_rel
    plan_abs = root / plan_rel
    report_json_abs = root / report_json_rel
    report_md_abs = root / report_md_rel

    script_dir = Path(__file__).resolve().parent
    py = sys.executable

    if not gardening_settings.get("enabled", True):
        skipped_report = {
            "generated_at": utc_now(),
            "root": str(root),
            "settings": {
                "plan_mode": args.plan_mode,
                "apply_mode": apply_mode,
                "fail_on_drift": fail_on_drift,
                "fail_on_freshness": fail_on_freshness,
                "skip_validate": args.skip_validate,
            },
            "steps": [],
            "plan": {},
            "apply": {},
            "validate": {},
            "summary": {
                "status": "skipped",
                "apply_mode": apply_mode,
                "step_count": 0,
                "failed_step_count": 0,
            },
        }
        report_json_abs.parent.mkdir(parents=True, exist_ok=True)
        with report_json_abs.open("w", encoding="utf-8") as f:
            json.dump(skipped_report, f, ensure_ascii=False, indent=2)
            f.write("\n")
        report_md_abs.parent.mkdir(parents=True, exist_ok=True)
        report_md_abs.write_text(render_report_markdown(skipped_report), encoding="utf-8")
        print(f"[OK] doc_gardening is disabled by policy, wrote report to {report_json_abs}")
        return 0

    steps: list[dict[str, Any]] = []

    def exec_or_stop(step_name: str, cmd: list[str]) -> bool:
        step = run_step(step_name, cmd, root)
        steps.append(step)
        return step["returncode"] == 0

    ok = exec_or_stop(
        "scan",
        [
            py,
            str(script_dir / "repo_scan.py"),
            "--root",
            str(root),
            "--output",
            str(facts_abs),
        ],
    )

    if ok:
        ok = exec_or_stop(
            "plan",
            [
                py,
                str(script_dir / "doc_plan.py"),
                "--root",
                str(root),
                "--mode",
                args.plan_mode,
                "--facts",
                str(facts_abs),
                "--output",
                str(plan_abs),
            ],
        )

    if ok and apply_mode != "none":
        apply_cmd = [
            py,
            str(script_dir / "doc_apply.py"),
            "--root",
            str(root),
            "--plan",
            str(plan_abs),
            "--mode",
            apply_mode,
        ]
        if args.init_language:
            apply_cmd.extend(["--init-language", args.init_language])
        ok = exec_or_stop("apply", apply_cmd)

    if ok and not args.skip_validate:
        ok = exec_or_stop(
            "scan-post-apply",
            [
                py,
                str(script_dir / "repo_scan.py"),
                "--root",
                str(root),
                "--output",
                str(facts_abs),
            ],
        )

    validate_report: dict[str, Any] | None = None
    if ok and not args.skip_validate:
        validate_cmd = [
            py,
            str(script_dir / "doc_validate.py"),
            "--root",
            str(root),
            "--facts",
            str(facts_abs),
        ]
        if fail_on_drift:
            validate_cmd.append("--fail-on-drift")
        if fail_on_freshness:
            validate_cmd.append("--fail-on-freshness")
        ok = exec_or_stop("validate", validate_cmd)

    plan_data = load_json_object(plan_abs) or {}
    apply_report_data = load_json_object(root / "docs/.doc-apply-report.json") or {}
    validate_report = load_json_object(root / "docs/.doc-validate-report.json") or {}

    report = {
        "generated_at": utc_now(),
        "root": str(root),
        "settings": {
            "plan_mode": args.plan_mode,
            "apply_mode": apply_mode,
            "fail_on_drift": fail_on_drift,
            "fail_on_freshness": fail_on_freshness,
            "skip_validate": args.skip_validate,
        },
        "steps": steps,
        "plan": {
            "action_count": ((plan_data.get("summary") or {}).get("action_count", 0)),
            "action_counts": (
                (plan_data.get("summary") or {}).get("action_counts", {})
            ),
        },
        "apply": (apply_report_data.get("summary") or {}),
        "validate": {
            "passed": validate_report.get("passed"),
            "errors": ((validate_report.get("metrics") or {}).get("errors")),
            "warnings": ((validate_report.get("metrics") or {}).get("warnings")),
            "drift_action_count": (
                (validate_report.get("metrics") or {}).get("drift_action_count")
            ),
            "metadata_stale_docs": (
                (validate_report.get("metrics") or {}).get("metadata_stale_docs")
            ),
        },
        "summary": {
            "status": "passed" if ok else "failed",
            "apply_mode": apply_mode,
            "step_count": len(steps),
            "failed_step_count": sum(1 for step in steps if step["status"] != "ok"),
        },
    }

    report_json_abs.parent.mkdir(parents=True, exist_ok=True)
    with report_json_abs.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")

    report_md_abs.parent.mkdir(parents=True, exist_ok=True)
    report_md_abs.write_text(render_report_markdown(report), encoding="utf-8")

    print(f"[OK] Wrote garden report to {report_json_abs}")
    print(f"[INFO] status={report['summary']['status']} apply_mode={apply_mode}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
