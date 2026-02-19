#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import json
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import doc_capabilities as dc
import doc_metadata as dm
import language_profiles as lp

DEFAULT_POLICY = lp.build_default_policy()
ACTIONABLE_TYPES = {"add", "update", "archive", "manual_review", "sync_manifest"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_posix(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def normalize_rel(path_str: str) -> str:
    return dc.normalize_rel(path_str)


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


def load_json_or_default(
    path: Path, default: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    if not path.exists():
        return deepcopy(default), False
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return data, True


def load_facts(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("facts JSON must be an object")
    return data


def load_json(path: Path) -> tuple[dict[str, Any], bool]:
    if not path.exists():
        return {}, False
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return data, True


def new_action_id(index: int) -> str:
    return f"A{index:03d}"


def missing_required_sections(path: Path, rel_path: str) -> list[str]:
    section_ids = lp.get_required_sections(rel_path)
    if not section_ids:
        return []
    if not path.exists():
        return section_ids

    text = path.read_text(encoding="utf-8")
    missing: list[str] = []
    for section_id in section_ids:
        markers = lp.get_section_markers(rel_path, section_id)
        if not any(marker in text for marker in markers):
            missing.append(section_id)
    return missing


def stale_docs_candidates(
    root: Path,
    managed_files: set[str],
    archive_dir: str,
    protected_patterns: list[str],
) -> list[str]:
    docs_root = root / "docs"
    if not docs_root.exists():
        return []

    archive_prefix = normalize_rel(archive_dir).rstrip("/") + "/"
    stale: list[str] = []
    for p in docs_root.rglob("*.md"):
        rel = to_posix(p, root)
        if rel.startswith(archive_prefix):
            continue
        if rel in managed_files:
            continue
        if any(fnmatch.fnmatch(rel, pattern) for pattern in protected_patterns):
            continue
        if p.name.startswith("."):
            continue
        stale.append(rel)
    return sorted(stale)


def resolve_effective_manifest(
    policy: dict[str, Any],
    has_manifest: bool,
    current_manifest: dict[str, Any],
    facts: dict[str, Any] | None,
) -> tuple[dict[str, Any], str, str, list[dict[str, Any]], list[str], bool]:
    capability_decisions: list[dict[str, Any]] = []
    manifest_notes: list[str] = []

    if has_manifest:
        evolution = dc.get_manifest_evolution_settings(policy)
        manifest_profile = dc.infer_manifest_profile(dc.collect_repo_metrics(facts))
        if not evolution["allow_additive"]:
            snapshot = dc.normalize_manifest_snapshot(current_manifest)
            return (
                snapshot,
                "existing",
                manifest_profile,
                capability_decisions,
                manifest_notes,
                False,
            )

        desired_manifest, capability_decisions, _, override_notes = (
            dc.derive_adaptive_manifest(
                facts,
                policy,
                archive_dir=current_manifest.get("archive_dir", dc.DEFAULT_ARCHIVE_DIR),
            )
        )
        merged_manifest, merge_notes = dc.merge_manifest_additive(
            current_manifest, desired_manifest
        )
        manifest_notes.extend(override_notes)
        manifest_notes.extend(merge_notes)
        changed = not dc.manifests_equal(current_manifest, merged_manifest)
        source = "existing_additive" if changed else "existing"
        return (
            merged_manifest,
            source,
            manifest_profile,
            capability_decisions,
            manifest_notes,
            changed,
        )

    strategy = dc.get_bootstrap_manifest_strategy(policy)
    if strategy == "fixed" or facts is None:
        profile = dc.infer_manifest_profile(dc.collect_repo_metrics(facts))
        notes = (
            ["bootstrap_manifest_strategy=fixed"]
            if strategy == "fixed"
            else ["facts missing, fallback to fixed"]
        )
        return dc.clone_default_manifest(), "fixed_fallback", profile, [], notes, True

    derived_manifest, capability_decisions, metrics, override_notes = (
        dc.derive_adaptive_manifest(facts, policy)
    )
    profile = dc.infer_manifest_profile(metrics)
    notes = ["bootstrap_manifest_strategy=adaptive"] + override_notes
    return derived_manifest, "adaptive", profile, capability_decisions, notes, True


def build_plan(
    root: Path,
    mode: str,
    facts: dict[str, Any] | None,
    policy_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    policy, has_policy = load_json_or_default(policy_path, DEFAULT_POLICY)
    current_manifest, has_manifest = load_json(manifest_path)

    inferred_language = None
    policy_for_language = policy if has_policy else {}
    if not isinstance(policy_for_language.get("language"), dict):
        inferred_language = infer_primary_language_from_docs(root)

    language_settings = lp.resolve_language_settings(
        policy_for_language, inferred_language
    )
    template_profile = language_settings["profile"]

    (
        effective_manifest,
        manifest_source,
        manifest_profile,
        capability_decisions,
        manifest_notes,
        manifest_changed,
    ) = resolve_effective_manifest(policy, has_manifest, current_manifest, facts)
    required_files, required_dirs, optional_files = dc.get_manifest_lists(
        effective_manifest
    )
    archive_dir = normalize_rel(
        effective_manifest.get("archive_dir", dc.DEFAULT_ARCHIVE_DIR)
    )
    metadata_policy = dm.resolve_metadata_policy(policy)
    allow_auto_update = set(
        normalize_rel(p) for p in policy.get("allow_auto_update", [])
    )
    protected_patterns = [
        normalize_rel(p) for p in policy.get("protect_from_auto_overwrite", [])
    ]

    actions: list[dict[str, Any]] = []

    def add_action(
        action_type: str,
        kind: str,
        path: str,
        reason: str,
        evidence: list[str],
        **extra,
    ):
        action = {
            "id": new_action_id(len(actions) + 1),
            "type": action_type,
            "kind": kind,
            "path": normalize_rel(path),
            "risk": "low"
            if action_type in {"add", "archive", "sync_manifest"}
            else "medium",
            "reason": reason,
            "evidence": evidence,
        }
        action.update(extra)
        actions.append(action)

    docs_root = root / "docs"

    if mode == "bootstrap" and not docs_root.exists():
        add_action(
            "add",
            "dir",
            "docs",
            "docs directory is missing",
            ["repository has no docs/ root"],
        )

    if not has_policy:
        add_action(
            "add",
            "file",
            normalize_rel(policy_path.relative_to(root)),
            "policy file is missing",
            ["docs automation requires policy boundaries"],
            template="policy",
        )

    if not has_manifest:
        add_action(
            "add",
            "file",
            normalize_rel(manifest_path.relative_to(root)),
            "manifest file is missing",
            ["docs structure requires manifest contract"],
            template="manifest",
            manifest_snapshot=dc.normalize_manifest_snapshot(effective_manifest),
        )
    elif manifest_changed:
        add_action(
            "sync_manifest",
            "file",
            normalize_rel(manifest_path.relative_to(root)),
            "manifest requires additive evolution based on repository signals",
            manifest_notes or ["adaptive capabilities produced new required docs"],
            manifest_snapshot=dc.normalize_manifest_snapshot(effective_manifest),
        )

    for rel_dir in required_dirs:
        if not (root / rel_dir).exists():
            add_action(
                "add",
                "dir",
                rel_dir,
                "required directory is missing",
                [f"manifest.required.dirs includes {rel_dir}"],
            )

    for rel_file in required_files:
        abs_file = root / rel_file
        if not abs_file.exists():
            add_action(
                "add",
                "file",
                rel_file,
                "required file is missing",
                [f"manifest.required.files includes {rel_file}"],
                template="managed",
            )

    for rel_file in optional_files:
        abs_file = root / rel_file
        if not abs_file.exists() and mode == "bootstrap":
            add_action(
                "add",
                "file",
                rel_file,
                "optional managed file missing during bootstrap",
                [f"manifest.optional.files includes {rel_file}"],
                template="managed",
            )

    managed_files = set(required_files) | set(optional_files)

    for rel_file in sorted(managed_files):
        abs_file = root / rel_file
        if not abs_file.exists():
            continue

        missing_sections = missing_required_sections(abs_file, rel_file)
        metadata_missing: list[str] = []
        metadata_invalid: list[str] = []
        if dm.should_enforce_for_path(rel_file, metadata_policy):
            metadata_eval = dm.evaluate_metadata(
                rel_file,
                abs_file.read_text(encoding="utf-8"),
                metadata_policy,
                reference_date=date.today(),
            )
            metadata_missing = list(metadata_eval.get("missing") or [])
            metadata_invalid = list(metadata_eval.get("invalid") or [])

        if not (missing_sections or metadata_missing or metadata_invalid):
            continue

        evidence: list[str] = []
        missing_headings: list[str] = []
        if missing_sections:
            missing_headings = [
                lp.get_section_heading(rel_file, section_id, template_profile)
                for section_id in missing_sections
            ]
            evidence.append(f"missing sections: {', '.join(missing_headings)}")
        if metadata_missing:
            evidence.append(f"missing doc metadata: {', '.join(metadata_missing)}")
        if metadata_invalid:
            evidence.append(f"invalid doc metadata: {', '.join(metadata_invalid)}")

        if rel_file in allow_auto_update:
            reason = "managed file misses required sections"
            if not missing_sections:
                reason = "managed file misses required doc metadata"
            add_action(
                "update",
                "file",
                rel_file,
                reason,
                evidence,
                missing_sections=missing_sections,
                missing_markers=missing_headings,
                missing_doc_metadata=metadata_missing,
                invalid_doc_metadata=metadata_invalid,
                template="managed",
            )
        else:
            add_action(
                "manual_review",
                "file",
                rel_file,
                "managed file requires manual metadata/section fix",
                evidence,
            )

    if mode in {"apply-with-archive", "audit", "apply-safe"}:
        stale = stale_docs_candidates(
            root, managed_files, archive_dir, protected_patterns
        )
        for stale_path in stale:
            if mode == "apply-with-archive":
                rel_from_docs = Path(stale_path).relative_to("docs")
                target = normalize_rel(Path(archive_dir) / rel_from_docs)
                add_action(
                    "archive",
                    "file",
                    target,
                    "stale docs candidate archived in migration mode",
                    [f"not declared in manifest: {stale_path}"],
                    source_path=stale_path,
                )
            else:
                add_action(
                    "manual_review",
                    "file",
                    stale_path,
                    "stale docs candidate requires review",
                    [f"not declared in manifest: {stale_path}"],
                )

    has_agents_md = (root / "AGENTS.md").exists()
    if (
        mode == "bootstrap"
        and not has_agents_md
        and bool(policy.get("bootstrap_agents_md", True))
    ):
        add_action(
            "add",
            "file",
            "AGENTS.md",
            "AGENTS navigation file is missing during bootstrap",
            ["policy.bootstrap_agents_md=true"],
            template="agents",
        )

    if facts:
        modules = facts.get("modules") or []
        if (
            isinstance(modules, list)
            and modules
            and (root / "docs/architecture.md").exists()
        ):
            content = (root / "docs/architecture.md").read_text(encoding="utf-8")
            missing_modules = [m for m in modules if m not in content]
            if missing_modules and "docs/architecture.md" in allow_auto_update:
                add_action(
                    "update",
                    "file",
                    "docs/architecture.md",
                    "architecture file does not list discovered modules",
                    [f"missing modules: {', '.join(missing_modules)}"],
                    missing_modules=missing_modules,
                    template="managed",
                )

    counts: dict[str, int] = {}
    for action in actions:
        counts[action["type"]] = counts.get(action["type"], 0) + 1

    return {
        "meta": {
            "generated_at": utc_now(),
            "root": str(root),
            "mode": mode,
            "policy_path": normalize_rel(policy_path.relative_to(root)),
            "manifest_path": normalize_rel(manifest_path.relative_to(root)),
            "manifest_source": manifest_source,
            "manifest_profile": manifest_profile,
            "manifest_changed": manifest_changed,
            "manifest_effective": dc.normalize_manifest_snapshot(effective_manifest),
            "manifest_reasoning": manifest_notes,
            "capability_decisions": capability_decisions,
            "doc_metadata": {
                "enabled": metadata_policy.get("enabled", True),
                "require_owner": metadata_policy.get("require_owner", True),
                "require_last_reviewed": metadata_policy.get(
                    "require_last_reviewed", True
                ),
                "require_review_cycle_days": metadata_policy.get(
                    "require_review_cycle_days", True
                ),
            },
            "language": {
                "primary": language_settings["primary"],
                "profile": language_settings["profile"],
                "source": language_settings["source"],
            },
        },
        "inputs": {
            "policy_exists": has_policy,
            "manifest_exists": has_manifest,
            "facts_loaded": facts is not None,
        },
        "summary": {
            "action_count": len(actions),
            "action_counts": counts,
            "has_actionable_drift": any(a["type"] in ACTIONABLE_TYPES for a in actions),
        },
        "actions": actions,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate documentation maintenance plans."
    )
    parser.add_argument("--root", required=True, help="Repository root")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["bootstrap", "audit", "apply-safe", "apply-with-archive"],
        help="Planning mode",
    )
    parser.add_argument("--facts", help="Path to repo facts JSON from repo_scan.py")
    parser.add_argument(
        "--policy", default="docs/.doc-policy.json", help="Policy file path"
    )
    parser.add_argument(
        "--manifest", default="docs/.doc-manifest.json", help="Manifest file path"
    )
    parser.add_argument("--output", required=True, help="Output plan JSON path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output).resolve()
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
    facts_path = Path(args.facts).resolve() if args.facts else None

    if not root.exists() or not root.is_dir():
        raise SystemExit(f"[ERROR] Invalid root path: {root}")

    facts = load_facts(facts_path) if facts_path else None
    plan = build_plan(root, args.mode, facts, policy_path, manifest_path)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[OK] Wrote plan to {output}")
    print(f"[INFO] Action count: {plan['summary']['action_count']}")
    language = (plan.get("meta") or {}).get("language") or {}
    print(
        "[INFO] Language primary="
        f"{language.get('primary', 'N/A')} profile={language.get('profile', 'N/A')} source={language.get('source', 'N/A')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
