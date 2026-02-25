#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import language_profiles as lp


DEFAULT_AGENTS_SETTINGS = dict(
    (lp.build_default_policy().get("agents_generation") or {})
)


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


def load_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def content_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def resolve_agents_settings(policy: dict[str, Any] | None) -> dict[str, Any]:
    base = dict(DEFAULT_AGENTS_SETTINGS)
    raw = (
        policy.get("agents_generation")
        if isinstance(policy, dict) and isinstance(policy.get("agents_generation"), dict)
        else {}
    )
    if not isinstance(raw, dict):
        raw = {}

    enabled = bool(raw.get("enabled", base.get("enabled", False)))
    mode = str(raw.get("mode", base.get("mode", "dynamic")))
    max_lines = raw.get("max_lines", base.get("max_lines", 140))
    if not isinstance(max_lines, int) or max_lines <= 0:
        max_lines = 140
    required_links = raw.get("required_links", base.get("required_links", []))
    if not isinstance(required_links, list):
        required_links = []
    sync_on_manifest_change = bool(
        raw.get(
            "sync_on_manifest_change", base.get("sync_on_manifest_change", True)
        )
    )
    fail_on_agents_drift = bool(
        raw.get("fail_on_agents_drift", base.get("fail_on_agents_drift", True))
    )
    overlap_threshold = raw.get("max_overlap_ratio", 0.7)
    if not isinstance(overlap_threshold, (float, int)):
        overlap_threshold = 0.7
    overlap_threshold = max(0.0, min(float(overlap_threshold), 1.0))

    return {
        "enabled": enabled,
        "mode": mode,
        "max_lines": max_lines,
        "required_links": [normalize(str(v)) for v in required_links if isinstance(v, str)],
        "sync_on_manifest_change": sync_on_manifest_change,
        "fail_on_agents_drift": fail_on_agents_drift,
        "max_overlap_ratio": overlap_threshold,
    }


def resolve_profile(policy: dict[str, Any] | None) -> str:
    language = (
        policy.get("language")
        if isinstance(policy, dict) and isinstance(policy.get("language"), dict)
        else {}
    )
    profile = language.get("profile") if isinstance(language, dict) else None
    if isinstance(profile, str) and profile.strip() in {"zh-CN", "en-US"}:
        return profile.strip()
    primary = language.get("primary") if isinstance(language, dict) else None
    return "zh-CN" if isinstance(primary, str) and primary.lower().startswith("zh") else "en-US"


def uniq(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            out.append(item)
            seen.add(item)
    return out


def markdown_link(path: str) -> str:
    target = f"./{path}" if not path.startswith("./") else path
    return f"[{path}]({target})"


def build_navigation_links(
    settings: dict[str, Any], manifest: dict[str, Any] | None
) -> list[str]:
    required = []
    for path in ("docs/index.md", "docs/.doc-policy.json", "docs/.doc-manifest.json"):
        required.append(path)
    required.extend(settings.get("required_links") or [])

    manifest_files: list[str] = []
    required_block = manifest.get("required") if isinstance(manifest, dict) else {}
    if isinstance(required_block, dict):
        files = required_block.get("files")
        if isinstance(files, list):
            manifest_files = [normalize(str(v)) for v in files if isinstance(v, str)]

    preferred = [
        path
        for path in manifest_files
        if path.startswith("docs/")
        and path.endswith(".md")
        and path
        not in {
            "docs/index.md",
            "docs/architecture.md",
            "docs/runbook.md",
        }
    ]
    required.extend(preferred[:4])
    return uniq([normalize(v) for v in required if v.strip()])


def build_standard_commands(profile: str) -> list[str]:
    if profile == "zh-CN":
        return [
            "```bash",
            'REPO_ROOT="/absolute/path/to/repo"',
            'PYTHON_BIN="${PYTHON_BIN:-python3}"',
            'command -v "$PYTHON_BIN" >/dev/null || { echo "python not found: $PYTHON_BIN" >&2; exit 2; }',
            'CODEX_HOME_RESOLVED="${CODEX_HOME:-$HOME/.codex}"',
            'if [ -n "${SKILL_DIR:-}" ]; then',
            '  [ -d "$SKILL_DIR/scripts" ] || {',
            '    echo "invalid SKILL_DIR: $SKILL_DIR (expected scripts/ under this path)" >&2',
            "    exit 2",
            "  }",
            'elif [ -d "$REPO_ROOT/.agents/skills/docs-sor-maintainer/scripts" ]; then',
            '  SKILL_DIR="$REPO_ROOT/.agents/skills/docs-sor-maintainer"',
            'elif [ -d "$CODEX_HOME_RESOLVED/skills/docs-sor-maintainer/scripts" ]; then',
            '  SKILL_DIR="$CODEX_HOME_RESOLVED/skills/docs-sor-maintainer"',
            "else",
            "  echo 'docs-sor-maintainer not found. Set SKILL_DIR or install under .agents/skills or $HOME/.codex/skills.' >&2",
            "  exit 2",
            "fi",
            '"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"',
            '"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode audit --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan.json"',
            '"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --fail-on-drift --fail-on-freshness',
            "```",
        ]
    return [
        "```bash",
        'REPO_ROOT="/absolute/path/to/repo"',
        'PYTHON_BIN="${PYTHON_BIN:-python3}"',
        'command -v "$PYTHON_BIN" >/dev/null || { echo "python not found: $PYTHON_BIN" >&2; exit 2; }',
        'CODEX_HOME_RESOLVED="${CODEX_HOME:-$HOME/.codex}"',
        'if [ -n "${SKILL_DIR:-}" ]; then',
        '  [ -d "$SKILL_DIR/scripts" ] || {',
        '    echo "invalid SKILL_DIR: $SKILL_DIR (expected scripts/ under this path)" >&2',
        "    exit 2",
        "  }",
        'elif [ -d "$REPO_ROOT/.agents/skills/docs-sor-maintainer/scripts" ]; then',
        '  SKILL_DIR="$REPO_ROOT/.agents/skills/docs-sor-maintainer"',
        'elif [ -d "$CODEX_HOME_RESOLVED/skills/docs-sor-maintainer/scripts" ]; then',
        '  SKILL_DIR="$CODEX_HOME_RESOLVED/skills/docs-sor-maintainer"',
        "else",
        "  echo 'docs-sor-maintainer not found. Set SKILL_DIR or install under .agents/skills or $HOME/.codex/skills.' >&2",
        "  exit 2",
        "fi",
        '"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"',
        '"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode audit --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan.json"',
        '"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --fail-on-drift --fail-on-freshness',
        "```",
    ]


def render_agents_content(
    profile: str,
    links: list[str],
    modules: list[str],
) -> str:
    if profile == "zh-CN":
        lines = [
            "# AGENTS",
            "",
            "## 目标",
            "",
            "将 `docs/` 作为仓库的 system of record。",
            "",
            "## 导航",
            "",
            "- 从 `docs/index.md` 开始。",
        ]
        lines.extend([f"- {markdown_link(path)}" for path in links])
        if modules:
            lines.append(f"- 当前顶层模块：`{', '.join(modules[:8])}`。")
        lines.extend(
            [
                "",
                "## 标准命令",
                "",
            ]
        )
        lines.extend(build_standard_commands(profile))
        lines.extend(
            [
                "",
                "## Guardrails",
                "",
                "- 保持 AGENTS 精简；详细知识放在 `docs/`。",
                "- 禁止硬删除 docs；统一归档到 `docs/archive/`。",
                "- 在 CI 驱动仓库中通过 PR 流程应用文档变更。",
            ]
        )
        return "\n".join(lines).rstrip() + "\n"

    lines = [
        "# AGENTS",
        "",
        "## Purpose",
        "",
        "Treat `docs/` as the repository system of record.",
        "",
        "## Navigation",
        "",
        "- Start at `docs/index.md`.",
    ]
    lines.extend([f"- {markdown_link(path)}" for path in links])
    if modules:
        lines.append(f"- Top-level modules detected: `{', '.join(modules[:8])}`.")
    lines.extend(
        [
            "",
            "## Standard Commands",
            "",
        ]
    )
    lines.extend(build_standard_commands(profile))
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- Keep AGENTS concise; store detailed knowledge under `docs/`.",
            "- Do not hard-delete docs; archive to `docs/archive/`.",
            "- Apply documentation changes through PR flow in CI-driven repositories.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def clip_to_max_lines(content: str, max_lines: int) -> str:
    lines = content.splitlines()
    if len(lines) <= max_lines:
        return content
    return "\n".join(lines[: max_lines - 1] + [""]) + "\n"


def generate_agents_artifacts(
    root: Path,
    policy: dict[str, Any] | None,
    manifest: dict[str, Any] | None,
    facts: dict[str, Any] | None,
    output_path: Path,
    report_path: Path,
    dry_run: bool = False,
    force: bool = False,
) -> tuple[str, dict[str, Any]]:
    settings = resolve_agents_settings(policy)
    enabled = settings.get("enabled", False)
    if not enabled and not force:
        report = {
            "generated_at": utc_now(),
            "root": str(root),
            "output": normalize(output_path.relative_to(root)),
            "status": "skipped",
            "reason": "agents_generation disabled",
            "settings": settings,
        }
        return "", report

    profile = resolve_profile(policy)
    links = build_navigation_links(settings, manifest or {})
    modules_raw = facts.get("modules") if isinstance(facts, dict) else []
    modules = [str(v) for v in modules_raw] if isinstance(modules_raw, list) else []

    content = render_agents_content(profile, links, modules)
    content = clip_to_max_lines(content, int(settings.get("max_lines", 140)))
    line_count = len(content.splitlines())

    report = {
        "generated_at": utc_now(),
        "root": str(root),
        "output": normalize(output_path.relative_to(root)),
        "status": "generated",
        "profile": profile,
        "settings": settings,
        "inputs": {
            "policy_loaded": isinstance(policy, dict),
            "manifest_loaded": isinstance(manifest, dict),
            "facts_loaded": isinstance(facts, dict),
            "navigation_links": links,
            "modules": modules,
        },
        "metrics": {
            "line_count": line_count,
            "content_sha256": content_sha256(content),
        },
    }

    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            f.write("\n")

    return content, report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate dynamic AGENTS.md.")
    parser.add_argument("--root", required=True, help="Repository root")
    parser.add_argument("--policy", default="docs/.doc-policy.json", help="Policy path")
    parser.add_argument(
        "--manifest", default="docs/.doc-manifest.json", help="Manifest path"
    )
    parser.add_argument("--facts", default="docs/.repo-facts.json", help="Facts path")
    parser.add_argument("--output", default="AGENTS.md", help="AGENTS output path")
    parser.add_argument(
        "--report", default="docs/.agents-report.json", help="Generation report path"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Render only without writing"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Generate even if agents_generation.enabled is false",
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
    manifest_path = (
        (root / args.manifest).resolve()
        if not Path(args.manifest).is_absolute()
        else Path(args.manifest)
    )
    facts_path = (
        (root / args.facts).resolve()
        if not Path(args.facts).is_absolute()
        else Path(args.facts)
    )
    output_path = (
        (root / args.output).resolve()
        if not Path(args.output).is_absolute()
        else Path(args.output)
    )
    report_path = (
        (root / args.report).resolve()
        if not Path(args.report).is_absolute()
        else Path(args.report)
    )

    policy = load_json_mapping(policy_path) or {}
    manifest = load_json_mapping(manifest_path) or {}
    facts = load_json_mapping(facts_path) or {}

    _, report = generate_agents_artifacts(
        root=root,
        policy=policy,
        manifest=manifest,
        facts=facts,
        output_path=output_path,
        report_path=report_path,
        dry_run=args.dry_run,
        force=args.force,
    )

    if report.get("status") == "skipped":
        print("[INFO] AGENTS generation skipped: agents_generation disabled")
        return 0
    print(f"[OK] Wrote AGENTS to {output_path}")
    print(f"[OK] Wrote agents report to {report_path}")
    print(f"[INFO] lines={report.get('metrics', {}).get('line_count', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
