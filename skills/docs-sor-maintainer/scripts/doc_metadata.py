#!/usr/bin/env python3
from __future__ import annotations

import fnmatch
import re
from datetime import date
from pathlib import Path
from typing import Any

METADATA_KEYS = (
    "doc-owner",
    "doc-last-reviewed",
    "doc-review-cycle-days",
)

METADATA_LINE_PATTERNS = {
    key: re.compile(rf"^\s*<!--\s*{re.escape(key)}\s*:\s*(.*?)\s*-->\s*$", re.MULTILINE)
    for key in METADATA_KEYS
}

METADATA_LINE_PREFIX = re.compile(
    r"^\s*<!--\s*doc-(?:owner|last-reviewed|review-cycle-days)\s*:.*?-->\s*$",
    re.MULTILINE,
)

DEFAULT_METADATA_POLICY = {
    "enabled": True,
    "require_owner": True,
    "require_last_reviewed": True,
    "require_review_cycle_days": True,
    "default_owner": "TODO-owner",
    "default_review_cycle_days": 90,
    "ignore_paths": ["docs/archive/**"],
    "stale_warning_enabled": True,
}


def normalize_rel(path_str: str) -> str:
    return str(Path(path_str)).replace("\\", "/")


def resolve_metadata_policy(policy: dict[str, Any]) -> dict[str, Any]:
    raw = (
        policy.get("doc_metadata")
        if isinstance(policy.get("doc_metadata"), dict)
        else {}
    )

    default_cycle = raw.get(
        "default_review_cycle_days",
        DEFAULT_METADATA_POLICY["default_review_cycle_days"],
    )
    try:
        default_cycle_value = int(default_cycle)
    except (TypeError, ValueError):
        default_cycle_value = DEFAULT_METADATA_POLICY["default_review_cycle_days"]
    if default_cycle_value <= 0:
        default_cycle_value = DEFAULT_METADATA_POLICY["default_review_cycle_days"]

    ignore_paths_raw = raw.get("ignore_paths")
    ignore_paths: list[str] = []
    if isinstance(ignore_paths_raw, list):
        ignore_paths = [
            normalize_rel(item)
            for item in ignore_paths_raw
            if isinstance(item, str) and item.strip()
        ]
    if not ignore_paths:
        ignore_paths = list(DEFAULT_METADATA_POLICY["ignore_paths"])

    return {
        "enabled": bool(raw.get("enabled", DEFAULT_METADATA_POLICY["enabled"])),
        "require_owner": bool(
            raw.get("require_owner", DEFAULT_METADATA_POLICY["require_owner"])
        ),
        "require_last_reviewed": bool(
            raw.get(
                "require_last_reviewed",
                DEFAULT_METADATA_POLICY["require_last_reviewed"],
            )
        ),
        "require_review_cycle_days": bool(
            raw.get(
                "require_review_cycle_days",
                DEFAULT_METADATA_POLICY["require_review_cycle_days"],
            )
        ),
        "default_owner": str(
            raw.get("default_owner", DEFAULT_METADATA_POLICY["default_owner"])
        ).strip()
        or DEFAULT_METADATA_POLICY["default_owner"],
        "default_review_cycle_days": default_cycle_value,
        "ignore_paths": ignore_paths,
        "stale_warning_enabled": bool(
            raw.get(
                "stale_warning_enabled",
                DEFAULT_METADATA_POLICY["stale_warning_enabled"],
            )
        ),
    }


def should_enforce_for_path(rel_path: str, metadata_policy: dict[str, Any]) -> bool:
    rel = normalize_rel(rel_path)
    if not metadata_policy.get("enabled", True):
        return False
    if not rel.startswith("docs/") or not rel.endswith(".md"):
        return False
    ignore_paths = metadata_policy.get("ignore_paths")
    if isinstance(ignore_paths, list) and any(
        fnmatch.fnmatch(rel, pattern) for pattern in ignore_paths
    ):
        return False
    return True


def extract_metadata(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, pattern in METADATA_LINE_PATTERNS.items():
        match = pattern.search(text)
        if not match:
            continue
        values[key] = match.group(1).strip()
    return values


def _is_valid_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _parse_positive_int(value: str) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number


def evaluate_metadata(
    rel_path: str,
    text: str,
    metadata_policy: dict[str, Any],
    reference_date: date | None = None,
) -> dict[str, Any]:
    ref = reference_date or date.today()
    values = extract_metadata(text)

    missing: list[str] = []
    invalid: list[str] = []

    owner = values.get("doc-owner", "").strip()
    last_reviewed = values.get("doc-last-reviewed", "").strip()
    cycle_raw = values.get("doc-review-cycle-days", "").strip()

    if metadata_policy.get("require_owner", True):
        if not owner:
            missing.append("doc-owner")

    if metadata_policy.get("require_last_reviewed", True):
        if not last_reviewed:
            missing.append("doc-last-reviewed")
        elif not _is_valid_iso_date(last_reviewed):
            invalid.append("doc-last-reviewed")

    cycle_value = _parse_positive_int(cycle_raw) if cycle_raw else None
    if metadata_policy.get("require_review_cycle_days", True):
        if not cycle_raw:
            missing.append("doc-review-cycle-days")
        elif cycle_value is None:
            invalid.append("doc-review-cycle-days")

    stale = False
    age_days: int | None = None
    if metadata_policy.get("stale_warning_enabled", True):
        if last_reviewed and _is_valid_iso_date(last_reviewed):
            reviewed_date = date.fromisoformat(last_reviewed)
            days = (ref - reviewed_date).days
            age_days = days
            effective_cycle = cycle_value or int(
                metadata_policy.get("default_review_cycle_days", 90)
            )
            if days > effective_cycle:
                stale = True

    return {
        "path": normalize_rel(rel_path),
        "values": values,
        "missing": missing,
        "invalid": invalid,
        "stale": stale,
        "age_days": age_days,
    }


def build_metadata_block(
    metadata_policy: dict[str, Any], reference_date: date | None = None
) -> str:
    ref = reference_date or date.today()
    owner = metadata_policy.get(
        "default_owner", DEFAULT_METADATA_POLICY["default_owner"]
    )
    cycle = int(
        metadata_policy.get(
            "default_review_cycle_days",
            DEFAULT_METADATA_POLICY["default_review_cycle_days"],
        )
    )
    lines = [
        f"<!-- doc-owner: {owner} -->",
        f"<!-- doc-last-reviewed: {ref.isoformat()} -->",
        f"<!-- doc-review-cycle-days: {cycle} -->",
    ]
    return "\n".join(lines)


def _sanitize_body_without_metadata(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines():
        if METADATA_LINE_PREFIX.match(raw_line):
            continue
        lines.append(raw_line)
    return "\n".join(lines).strip("\n")


def ensure_metadata_block(
    text: str, metadata_policy: dict[str, Any], reference_date: date | None = None
) -> tuple[str, bool]:
    ref = reference_date or date.today()
    values = extract_metadata(text)

    owner = values.get("doc-owner", "").strip() or metadata_policy.get(
        "default_owner", DEFAULT_METADATA_POLICY["default_owner"]
    )
    last_reviewed = values.get("doc-last-reviewed", "").strip()
    if not last_reviewed or not _is_valid_iso_date(last_reviewed):
        last_reviewed = ref.isoformat()

    cycle_raw = values.get("doc-review-cycle-days", "").strip()
    cycle_value = _parse_positive_int(cycle_raw)
    if cycle_value is None:
        cycle_value = int(
            metadata_policy.get(
                "default_review_cycle_days",
                DEFAULT_METADATA_POLICY["default_review_cycle_days"],
            )
        )

    block = "\n".join(
        [
            f"<!-- doc-owner: {owner} -->",
            f"<!-- doc-last-reviewed: {last_reviewed} -->",
            f"<!-- doc-review-cycle-days: {cycle_value} -->",
        ]
    )
    body = _sanitize_body_without_metadata(text)
    if body:
        updated = f"{block}\n\n{body}\n"
    else:
        updated = f"{block}\n"
    return updated, updated != text
