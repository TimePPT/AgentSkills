#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

DEFAULT_ARCHIVE_DIR = "docs/archive"
DEFAULT_MANIFEST = {
    "version": 1,
    "required": {
        "files": ["docs/index.md", "docs/architecture.md", "docs/runbook.md"],
        "dirs": [
            "docs/exec-plans/active",
            "docs/exec-plans/completed",
            "docs/tech-debt",
        ],
    },
    "optional": {
        "files": ["docs/glossary.md"],
    },
    "archive_dir": DEFAULT_ARCHIVE_DIR,
}

GOAL_ALIASES = {
    "index": "core.index",
    "core": "core.index",
    "architecture": "architecture.overview",
    "runbook": "operations.runbook",
    "operations": "operations.runbook",
    "planning": "planning.workspace",
    "exec-plans": "planning.workspace",
    "glossary": "glossary.terms",
    "incident": "incident.response",
    "incident-response": "incident.response",
    "security": "security.posture",
    "compliance": "compliance.controls",
}

CAPABILITIES = [
    {
        "id": "core.index",
        "required_files": {"docs/index.md"},
        "required_dirs": set(),
        "optional_files": set(),
    },
    {
        "id": "operations.runbook",
        "required_files": {"docs/runbook.md"},
        "required_dirs": set(),
        "optional_files": set(),
    },
    {
        "id": "architecture.overview",
        "required_files": {"docs/architecture.md"},
        "required_dirs": set(),
        "optional_files": set(),
    },
    {
        "id": "planning.workspace",
        "required_files": set(),
        "required_dirs": {
            "docs/exec-plans/active",
            "docs/exec-plans/completed",
            "docs/tech-debt",
        },
        "optional_files": set(),
    },
    {
        "id": "glossary.terms",
        "required_files": set(),
        "required_dirs": set(),
        "optional_files": {"docs/glossary.md"},
    },
    {
        "id": "incident.response",
        "required_files": {"docs/incident-response.md"},
        "required_dirs": set(),
        "optional_files": set(),
    },
    {
        "id": "security.posture",
        "required_files": {"docs/security.md"},
        "required_dirs": set(),
        "optional_files": set(),
    },
    {
        "id": "compliance.controls",
        "required_files": {"docs/compliance.md"},
        "required_dirs": set(),
        "optional_files": set(),
    },
]


def normalize_rel(path_str: str) -> str:
    return str(Path(path_str)).replace("\\", "/")


def _to_list(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    return []


def _uniq_sorted(values: list[str]) -> list[str]:
    return sorted(
        {
            normalize_rel(value)
            for value in values
            if isinstance(value, str) and value.strip()
        }
    )


def get_manifest_lists(
    manifest: dict[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    required = manifest.get("required", {}) or {}
    optional = manifest.get("optional", {}) or {}

    required_files = _uniq_sorted(required.get("files", []))
    required_dirs = _uniq_sorted(required.get("dirs", []))
    optional_files = _uniq_sorted(optional.get("files", []))

    optional_files = [
        item for item in optional_files if item not in set(required_files)
    ]
    return required_files, required_dirs, optional_files


def build_manifest_snapshot(
    required_files: list[str],
    required_dirs: list[str],
    optional_files: list[str],
    archive_dir: str | None = None,
) -> dict[str, Any]:
    dedup_required_files = _uniq_sorted(required_files)
    dedup_required_dirs = _uniq_sorted(required_dirs)
    dedup_optional_files = [
        item
        for item in _uniq_sorted(optional_files)
        if item not in set(dedup_required_files)
    ]

    return {
        "version": 1,
        "required": {
            "files": dedup_required_files,
            "dirs": dedup_required_dirs,
        },
        "optional": {
            "files": dedup_optional_files,
        },
        "archive_dir": normalize_rel(archive_dir or DEFAULT_ARCHIVE_DIR),
    }


def normalize_manifest_snapshot(manifest: dict[str, Any]) -> dict[str, Any]:
    required_files, required_dirs, optional_files = get_manifest_lists(manifest)
    archive_dir = normalize_rel(manifest.get("archive_dir", DEFAULT_ARCHIVE_DIR))
    return build_manifest_snapshot(
        required_files, required_dirs, optional_files, archive_dir
    )


def manifests_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return normalize_manifest_snapshot(left) == normalize_manifest_snapshot(right)


def _truthy_count(mapping: dict[str, Any]) -> int:
    return sum(1 for value in mapping.values() if bool(value))


def collect_repo_metrics(facts: dict[str, Any] | None) -> dict[str, int]:
    facts_data = facts or {}
    stats = facts_data.get("stats") if isinstance(facts_data.get("stats"), dict) else {}
    docs = facts_data.get("docs") if isinstance(facts_data.get("docs"), dict) else {}
    manifests = (
        facts_data.get("manifests")
        if isinstance(facts_data.get("manifests"), dict)
        else {}
    )
    signals = (
        facts_data.get("signals") if isinstance(facts_data.get("signals"), dict) else {}
    )
    tests = signals.get("tests") if isinstance(signals.get("tests"), dict) else {}
    api = signals.get("api") if isinstance(signals.get("api"), dict) else {}
    data = signals.get("data") if isinstance(signals.get("data"), dict) else {}
    delivery = (
        signals.get("delivery") if isinstance(signals.get("delivery"), dict) else {}
    )
    ops = signals.get("ops") if isinstance(signals.get("ops"), dict) else {}
    incident = (
        signals.get("incident") if isinstance(signals.get("incident"), dict) else {}
    )
    security = (
        signals.get("security") if isinstance(signals.get("security"), dict) else {}
    )
    compliance = (
        signals.get("compliance") if isinstance(signals.get("compliance"), dict) else {}
    )

    modules = _to_list(facts_data.get("modules"))
    entrypoints = _to_list(facts_data.get("entrypoints"))
    ci = _to_list(facts_data.get("ci"))
    languages = (
        facts_data.get("languages")
        if isinstance(facts_data.get("languages"), dict)
        else {}
    )

    return {
        "file_count": int(stats.get("file_count", 0) or 0),
        "modules_count": len(modules),
        "entrypoints_count": len(entrypoints),
        "ci_count": len(ci),
        "language_count": len(languages),
        "manifests_present_count": _truthy_count(manifests),
        "docs_markdown_count": int(docs.get("docs_markdown_count", 0) or 0),
        "tests_detected": 1 if bool(tests.get("has_tests")) else 0,
        "api_detected": 1 if bool(api.get("detected")) else 0,
        "data_detected": 1 if bool(data.get("detected")) else 0,
        "delivery_detected": 1 if bool(delivery.get("detected")) else 0,
        "ops_detected": 1 if bool(ops.get("detected")) else 0,
        "incident_detected": 1 if bool(incident.get("detected")) else 0,
        "security_detected": 1 if bool(security.get("detected")) else 0,
        "compliance_detected": 1 if bool(compliance.get("detected")) else 0,
    }


def infer_manifest_profile(metrics: dict[str, int]) -> str:
    file_count = metrics.get("file_count", 0)
    if file_count <= 30:
        return "tiny"
    if file_count <= 120:
        return "small"
    if file_count <= 400:
        return "medium"
    return "large"


def normalize_goal_ids(raw_goals: Any) -> set[str]:
    values = _to_list(raw_goals)
    normalized: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        key = value.strip()
        if not key:
            continue
        normalized.add(GOAL_ALIASES.get(key, key))
    return normalized


def extract_goal_sets(policy: dict[str, Any]) -> tuple[set[str], set[str]]:
    goals = policy.get("doc_goals") if isinstance(policy.get("doc_goals"), dict) else {}
    include_set = normalize_goal_ids(goals.get("include"))
    exclude_set = normalize_goal_ids(goals.get("exclude"))
    return include_set, exclude_set


def _evaluate_signal_enabled(
    capability_id: str, metrics: dict[str, int]
) -> tuple[bool, list[str]]:
    evidence: list[str] = []

    if capability_id == "core.index":
        return True, ["baseline capability is always required"]

    if capability_id == "operations.runbook":
        if metrics["entrypoints_count"] > 0:
            evidence.append(f"entrypoints={metrics['entrypoints_count']}")
        if metrics["manifests_present_count"] > 0:
            evidence.append(f"manifests_present={metrics['manifests_present_count']}")
        if metrics["ci_count"] > 0:
            evidence.append(f"ci_configs={metrics['ci_count']}")
        if metrics["delivery_detected"] > 0:
            evidence.append("delivery_signals_detected")
        return bool(evidence), evidence

    if capability_id == "architecture.overview":
        if metrics["modules_count"] >= 2:
            evidence.append(f"modules={metrics['modules_count']}")
        if metrics["language_count"] >= 2:
            evidence.append(f"languages={metrics['language_count']}")
        if metrics["file_count"] >= 50:
            evidence.append(f"file_count={metrics['file_count']}")
        return bool(evidence), evidence

    if capability_id == "planning.workspace":
        if metrics["ci_count"] > 0:
            evidence.append(f"ci_configs={metrics['ci_count']}")
        if metrics["modules_count"] >= 2:
            evidence.append(f"modules={metrics['modules_count']}")
        if metrics["file_count"] >= 80:
            evidence.append(f"file_count={metrics['file_count']}")
        return bool(evidence), evidence

    if capability_id == "glossary.terms":
        if metrics["docs_markdown_count"] >= 6:
            evidence.append(f"docs_markdown_count={metrics['docs_markdown_count']}")
        if metrics["modules_count"] >= 5:
            evidence.append(f"modules={metrics['modules_count']}")
        return bool(evidence), evidence

    if capability_id == "incident.response":
        if metrics["incident_detected"] > 0:
            evidence.append("incident_signals_detected")
        if metrics["ops_detected"] > 0 and metrics["ci_count"] > 0:
            evidence.append("ops_and_ci_detected")
        return bool(evidence), evidence

    if capability_id == "security.posture":
        if metrics["security_detected"] > 0:
            evidence.append("security_signals_detected")
        if metrics["ci_count"] > 0 and metrics["manifests_present_count"] > 0:
            evidence.append("ci_and_build_manifests_detected")
        return bool(evidence), evidence

    if capability_id == "compliance.controls":
        if metrics["compliance_detected"] > 0:
            evidence.append("compliance_signals_detected")
        if (
            metrics["security_detected"] > 0
            and metrics["ci_count"] > 0
            and metrics["file_count"] >= 150
        ):
            evidence.append("large_repo_security_ci_detected")
        return bool(evidence), evidence

    return False, []


def derive_capability_decisions(
    facts: dict[str, Any] | None,
    policy: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    include_set, exclude_set = extract_goal_sets(policy)
    metrics = collect_repo_metrics(facts)
    decisions: list[dict[str, Any]] = []

    for capability in CAPABILITIES:
        capability_id = capability["id"]
        signal_enabled, signal_evidence = _evaluate_signal_enabled(
            capability_id, metrics
        )
        enabled = signal_enabled
        source = "signal" if signal_enabled else "disabled"
        evidence = list(signal_evidence)

        if capability_id in include_set:
            enabled = True
            source = "goal_include"
            evidence.append("enabled by doc_goals.include")

        if capability_id in exclude_set and capability_id != "core.index":
            enabled = False
            source = "goal_exclude"
            evidence = ["disabled by doc_goals.exclude"]

        if capability_id == "core.index":
            source = "baseline"
            if capability_id in exclude_set:
                evidence.append("core.index cannot be excluded")

        decisions.append(
            {
                "id": capability_id,
                "enabled": enabled,
                "source": source,
                "evidence": evidence or ["no enabling signals"],
                "required_files": sorted(capability["required_files"]),
                "required_dirs": sorted(capability["required_dirs"]),
                "optional_files": sorted(capability["optional_files"]),
            }
        )

    return decisions, metrics


def apply_adaptive_overrides(
    required_files: list[str],
    required_dirs: list[str],
    optional_files: list[str],
    policy: dict[str, Any],
) -> tuple[list[str], list[str], list[str], list[str]]:
    overrides = policy.get("adaptive_manifest_overrides")
    if not isinstance(overrides, dict):
        return (
            _uniq_sorted(required_files),
            _uniq_sorted(required_dirs),
            _uniq_sorted(optional_files),
            [],
        )

    include_files = _uniq_sorted(overrides.get("include_files", []))
    include_dirs = _uniq_sorted(overrides.get("include_dirs", []))
    exclude_files = set(_uniq_sorted(overrides.get("exclude_files", [])))
    exclude_dirs = set(_uniq_sorted(overrides.get("exclude_dirs", [])))

    required_file_set = set(_uniq_sorted(required_files)) | set(include_files)
    required_dir_set = set(_uniq_sorted(required_dirs)) | set(include_dirs)
    optional_file_set = set(_uniq_sorted(optional_files))

    required_file_set -= exclude_files
    required_dir_set -= exclude_dirs
    optional_file_set -= exclude_files

    # Keep required higher priority than optional.
    optional_file_set -= required_file_set

    override_notes: list[str] = []
    if include_files:
        override_notes.append(f"include_files={len(include_files)}")
    if include_dirs:
        override_notes.append(f"include_dirs={len(include_dirs)}")
    if exclude_files:
        override_notes.append(f"exclude_files={len(exclude_files)}")
    if exclude_dirs:
        override_notes.append(f"exclude_dirs={len(exclude_dirs)}")

    return (
        sorted(required_file_set),
        sorted(required_dir_set),
        sorted(optional_file_set),
        override_notes,
    )


def derive_adaptive_manifest(
    facts: dict[str, Any] | None,
    policy: dict[str, Any],
    archive_dir: str = DEFAULT_ARCHIVE_DIR,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, int], list[str]]:
    decisions, metrics = derive_capability_decisions(facts, policy)
    required_files: list[str] = []
    required_dirs: list[str] = []
    optional_files: list[str] = []

    for decision in decisions:
        if not decision["enabled"]:
            continue
        required_files.extend(decision["required_files"])
        required_dirs.extend(decision["required_dirs"])
        optional_files.extend(decision["optional_files"])

    required_files, required_dirs, optional_files, override_notes = (
        apply_adaptive_overrides(required_files, required_dirs, optional_files, policy)
    )

    # Keep index mandatory even with aggressive overrides.
    if "docs/index.md" not in required_files:
        required_files.append("docs/index.md")
        required_files = sorted(set(required_files))

    manifest = build_manifest_snapshot(
        required_files, required_dirs, optional_files, archive_dir
    )
    return manifest, decisions, metrics, override_notes


def get_bootstrap_manifest_strategy(policy: dict[str, Any]) -> str:
    raw = policy.get("bootstrap_manifest_strategy")
    if isinstance(raw, str) and raw.strip().lower() == "fixed":
        return "fixed"
    return "adaptive"


def get_manifest_evolution_settings(policy: dict[str, Any]) -> dict[str, bool]:
    settings = policy.get("manifest_evolution")
    if not isinstance(settings, dict):
        return {"allow_additive": True, "allow_pruning": False}
    return {
        "allow_additive": bool(settings.get("allow_additive", True)),
        "allow_pruning": bool(settings.get("allow_pruning", False)),
    }


def merge_manifest_additive(
    existing: dict[str, Any], desired: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    existing_snapshot = normalize_manifest_snapshot(existing)
    desired_snapshot = normalize_manifest_snapshot(desired)

    existing_required_files, existing_required_dirs, existing_optional_files = (
        get_manifest_lists(existing_snapshot)
    )
    desired_required_files, desired_required_dirs, desired_optional_files = (
        get_manifest_lists(desired_snapshot)
    )

    merged_required_files = sorted(
        set(existing_required_files) | set(desired_required_files)
    )
    merged_required_dirs = sorted(
        set(existing_required_dirs) | set(desired_required_dirs)
    )
    merged_optional_files = sorted(
        (set(existing_optional_files) | set(desired_optional_files))
        - set(merged_required_files)
    )

    merged_archive_dir = normalize_rel(
        existing_snapshot.get(
            "archive_dir", desired_snapshot.get("archive_dir", DEFAULT_ARCHIVE_DIR)
        )
    )
    merged = build_manifest_snapshot(
        merged_required_files,
        merged_required_dirs,
        merged_optional_files,
        merged_archive_dir,
    )

    notes: list[str] = []
    new_required_files = sorted(
        set(merged_required_files) - set(existing_required_files)
    )
    new_required_dirs = sorted(set(merged_required_dirs) - set(existing_required_dirs))
    new_optional_files = sorted(
        set(merged_optional_files) - set(existing_optional_files)
    )
    if new_required_files:
        notes.append(f"new required files: {', '.join(new_required_files)}")
    if new_required_dirs:
        notes.append(f"new required dirs: {', '.join(new_required_dirs)}")
    if new_optional_files:
        notes.append(f"new optional files: {', '.join(new_optional_files)}")

    return merged, notes


def clone_default_manifest() -> dict[str, Any]:
    return deepcopy(DEFAULT_MANIFEST)
