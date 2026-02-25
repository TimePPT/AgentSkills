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
    "repair_plan_mode": "audit",
    "fail_on_drift": True,
    "fail_on_freshness": True,
    "max_repair_iterations": 2,
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
    repair_plan_mode = raw.get("repair_plan_mode")
    if isinstance(repair_plan_mode, str) and repair_plan_mode in {
        "audit",
        "apply-with-archive",
        "repair",
    }:
        settings["repair_plan_mode"] = repair_plan_mode
    settings["fail_on_drift"] = bool(
        raw.get("fail_on_drift", settings["fail_on_drift"])
    )
    settings["fail_on_freshness"] = bool(
        raw.get("fail_on_freshness", settings["fail_on_freshness"])
    )
    max_repair_iterations = raw.get("max_repair_iterations")
    if isinstance(max_repair_iterations, int) and max_repair_iterations >= 0:
        settings["max_repair_iterations"] = max_repair_iterations

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
    duration_ms = int((finished - started).total_seconds() * 1000)
    return {
        "name": step_name,
        "command": cmd,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_ms": duration_ms,
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


def extract_applied_count(apply_report: dict[str, Any] | None) -> int | None:
    if not isinstance(apply_report, dict):
        return None
    summary = apply_report.get("summary")
    if not isinstance(summary, dict):
        return None
    value = summary.get("applied")
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return None


def build_performance_metrics(
    steps: list[dict[str, Any]], garden_total_duration_ms: int
) -> dict[str, int]:
    scan_duration_ms = 0
    plan_duration_ms = 0
    apply_duration_ms = 0
    synthesize_duration_ms = 0
    validate_duration_ms = 0

    for step in steps:
        name = str(step.get("name") or "")
        duration = step.get("duration_ms")
        if isinstance(duration, bool) or not isinstance(duration, int):
            continue
        if name.endswith(":scan") or name.endswith(":scan-post-apply"):
            scan_duration_ms += duration
        elif name.endswith(":plan"):
            plan_duration_ms += duration
        elif name.endswith(":apply"):
            apply_duration_ms += duration
        elif name.endswith(":synthesize"):
            synthesize_duration_ms += duration
        elif name.endswith(":validate"):
            validate_duration_ms += duration

    return {
        "scan_duration_ms": scan_duration_ms,
        "plan_duration_ms": plan_duration_ms,
        "apply_duration_ms": apply_duration_ms,
        "synthesize_duration_ms": synthesize_duration_ms,
        "validate_duration_ms": validate_duration_ms,
        "garden_total_duration_ms": garden_total_duration_ms,
    }


def parse_drift_action_type(note: str) -> str | None:
    if not note:
        return None
    parts = note.split()
    if len(parts) < 2:
        return None
    return parts[1]

def is_repairable_drift(validate_report: dict[str, Any] | None) -> bool:
    if not validate_report:
        return False
    drift = validate_report.get("drift") or {}
    actions = drift.get("actions") or []
    if not isinstance(actions, list) or not actions:
        return False
    repairable = {
        "update_section",
        "fill_claim",
        "refresh_evidence",
        "semantic_rewrite",
        "quality_repair",
    }
    for note in actions:
        if not isinstance(note, str):
            return False
        action_type = parse_drift_action_type(note)
        if action_type not in repairable:
            return False
    return True


def collect_semantic_backlog(validate_report: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(validate_report, dict):
        return []
    legacy = validate_report.get("legacy")
    if not isinstance(legacy, dict):
        return []
    semantic = legacy.get("semantic")
    if not isinstance(semantic, dict):
        return []
    backlog = semantic.get("backlog")
    if not isinstance(backlog, list):
        return []
    items: list[dict[str, Any]] = []
    for item in backlog:
        if isinstance(item, dict):
            items.append(item)
    return items


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
            f"- `{step.get('name')}` rc={step.get('returncode')} status={step.get('status')} duration_ms={step.get('duration_ms')}"
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

    repair = report.get("repair") or {}
    if repair:
        lines.extend(
            [
                "",
                "## Repair",
                "",
                f"- Attempts: {repair.get('attempts', 0)}",
                f"- Max iterations: {repair.get('max_iterations', 0)}",
                f"- Repairable drift: {repair.get('repairable_drift')}",
                f"- Initial plan mode: {repair.get('initial_plan_mode')}",
                f"- Repair plan mode: {repair.get('repair_plan_mode')}",
            ]
        )
        cycles = repair.get("cycles")
        if isinstance(cycles, list) and cycles:
            cycle_modes = ", ".join(
                f"{str(item.get('label', 'UNKNOWN'))}:{str(item.get('plan_mode', 'UNKNOWN'))}"
                for item in cycles
                if isinstance(item, dict)
            )
            if cycle_modes:
                lines.append(f"- Cycle modes: {cycle_modes}")

    semantic_backlog = report.get("semantic_backlog") or {}
    if semantic_backlog:
        lines.extend(
            [
                "",
                "## Semantic Backlog",
                "",
                f"- Count: {semantic_backlog.get('count', 0)}",
            ]
        )
        sample = semantic_backlog.get("sample") or []
        if isinstance(sample, list):
            for item in sample[:10]:
                if not isinstance(item, dict):
                    continue
                source_path = item.get("source_path", "UNKNOWN")
                reason = item.get("reason", "UNKNOWN")
                lines.append(f"- `{source_path}`: {reason}")

    performance = report.get("performance") or {}
    if performance:
        lines.extend(
            [
                "",
                "## Performance",
                "",
                f"- scan_duration_ms: {performance.get('scan_duration_ms')}",
                f"- plan_duration_ms: {performance.get('plan_duration_ms')}",
                f"- apply_duration_ms: {performance.get('apply_duration_ms')}",
                f"- synthesize_duration_ms: {performance.get('synthesize_duration_ms')}",
                f"- validate_duration_ms: {performance.get('validate_duration_ms')}",
                f"- garden_total_duration_ms: {performance.get('garden_total_duration_ms')}",
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
        "--repair-plan-mode",
        choices=["audit", "apply-with-archive", "repair"],
        help="Planning mode used by repair rounds (defaults to policy)",
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
    started_at = datetime.now(timezone.utc)
    args = parse_args()
    root = Path(args.root).resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"[ERROR] Invalid root path: {root}")

    policy_path = root / "docs/.doc-policy.json"
    policy = load_json_mapping(policy_path)
    gardening_settings = resolve_doc_gardening_settings(policy)

    apply_mode = args.apply_mode or gardening_settings["apply_mode"]
    initial_plan_mode = args.plan_mode
    repair_plan_mode = args.repair_plan_mode or str(
        gardening_settings.get("repair_plan_mode", "audit")
    )
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
    max_repair_iterations = int(gardening_settings.get("max_repair_iterations", 0))

    facts_abs = root / facts_rel
    plan_abs = root / plan_rel
    report_json_abs = root / report_json_rel
    report_md_abs = root / report_md_rel

    script_dir = Path(__file__).resolve().parent
    py = sys.executable

    if not gardening_settings.get("enabled", True):
        finished_at = datetime.now(timezone.utc)
        garden_total_duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        skipped_report = {
            "generated_at": utc_now(),
            "root": str(root),
            "settings": {
                "plan_mode": args.plan_mode,
                "repair_plan_mode": repair_plan_mode,
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
                "garden_total_duration_ms": garden_total_duration_ms,
            },
            "performance": {"garden_total_duration_ms": garden_total_duration_ms},
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
    cycle_plan_modes: list[dict[str, Any]] = []
    repair_attempts = 0
    last_validate_report: dict[str, Any] | None = None

    def exec_or_stop(step_name: str, cmd: list[str]) -> bool:
        step = run_step(step_name, cmd, root)
        steps.append(step)
        return step["returncode"] == 0

    def run_cycle(label: str, plan_mode: str) -> bool:
        cycle_record = {"label": label, "plan_mode": plan_mode}
        cycle_plan_modes.append(cycle_record)
        ok = exec_or_stop(
            f"{label}:scan",
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
                f"{label}:plan",
                [
                    py,
                    str(script_dir / "doc_plan.py"),
                    "--root",
                    str(root),
                    "--mode",
                    plan_mode,
                    "--facts",
                    str(facts_abs),
                    "--output",
                    str(plan_abs),
                ],
            )

        should_scan_post_apply = apply_mode != "none"
        apply_applied_count: int | None = None
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
            ok = exec_or_stop(f"{label}:apply", apply_cmd)
            if ok:
                apply_report = load_json_object(root / "docs/.doc-apply-report.json")
                apply_applied_count = extract_applied_count(apply_report)
                if apply_applied_count == 0:
                    should_scan_post_apply = False

        if ok and not args.skip_validate and should_scan_post_apply:
            ok = exec_or_stop(
                f"{label}:scan-post-apply",
                [
                    py,
                    str(script_dir / "repo_scan.py"),
                    "--root",
                    str(root),
                    "--output",
                    str(facts_abs),
                ],
            )
        elif ok and not args.skip_validate:
            cycle_record["post_apply_scan_skipped"] = True
            cycle_record["post_apply_scan_skip_reason"] = (
                "apply_mode_none"
                if apply_mode == "none"
                else "apply_applied_zero"
            )

        if ok and not args.skip_validate:
            synth_cmd = [
                py,
                str(script_dir / "doc_synthesize.py"),
                "--root",
                str(root),
                "--plan",
                str(plan_abs),
                "--facts",
                str(facts_abs),
                "--output",
                str(root / "docs/.doc-evidence-map.json"),
            ]
            ok = exec_or_stop(f"{label}:synthesize", synth_cmd)

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
            ok = exec_or_stop(f"{label}:validate", validate_cmd)

        nonlocal last_validate_report
        last_validate_report = load_json_object(root / "docs/.doc-validate-report.json")
        cycle_record["apply_applied"] = apply_applied_count
        cycle_record["success"] = ok
        return ok

    cycle_index = 0
    ok = run_cycle("run", initial_plan_mode)
    while (
        not ok
        and not args.skip_validate
        and apply_mode != "none"
        and cycle_index < max_repair_iterations
        and is_repairable_drift(last_validate_report)
    ):
        repair_attempts += 1
        cycle_index += 1
        ok = run_cycle(f"repair-{cycle_index}", repair_plan_mode)

    plan_data = load_json_object(plan_abs) or {}
    apply_report_data = load_json_object(root / "docs/.doc-apply-report.json") or {}
    validate_report = last_validate_report or {}
    semantic_backlog = collect_semantic_backlog(validate_report)
    finished_at = datetime.now(timezone.utc)
    garden_total_duration_ms = int((finished_at - started_at).total_seconds() * 1000)
    performance_metrics = build_performance_metrics(steps, garden_total_duration_ms)

    report = {
        "generated_at": utc_now(),
        "root": str(root),
        "settings": {
            "plan_mode": initial_plan_mode,
            "repair_plan_mode": repair_plan_mode,
            "apply_mode": apply_mode,
            "fail_on_drift": fail_on_drift,
            "fail_on_freshness": fail_on_freshness,
            "skip_validate": args.skip_validate,
            "max_repair_iterations": max_repair_iterations,
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
        "repair": {
            "attempts": repair_attempts,
            "max_iterations": max_repair_iterations,
            "repairable_drift": is_repairable_drift(last_validate_report),
            "initial_plan_mode": initial_plan_mode,
            "repair_plan_mode": repair_plan_mode,
            "cycles": cycle_plan_modes,
        },
        "semantic_backlog": {
            "count": len(semantic_backlog),
            "sample": semantic_backlog[:20],
        },
        "summary": {
            "status": "passed" if ok else "failed",
            "apply_mode": apply_mode,
            "step_count": len(steps),
            "failed_step_count": sum(1 for step in steps if step["status"] != "ok"),
            "garden_total_duration_ms": garden_total_duration_ms,
        },
        "performance": performance_metrics,
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
