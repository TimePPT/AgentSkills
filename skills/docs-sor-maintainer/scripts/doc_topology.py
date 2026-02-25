#!/usr/bin/env python3
from __future__ import annotations

from collections import deque
from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any

DEFAULT_TOPOLOGY_SETTINGS = {
    "enabled": False,
    "path": "docs/.doc-topology.json",
    "enforce_max_depth": True,
    "max_depth": 3,
    "fail_on_orphan": True,
    "fail_on_unreachable": True,
}

DEFAULT_PROGRESSIVE_DISCLOSURE_SETTINGS = {
    "enabled": False,
    "required_slots": ["summary", "key_facts", "next_steps"],
    "summary_max_chars": 160,
    "max_key_facts": 5,
    "max_next_steps": 3,
    "fail_on_missing_slots": True,
}

SUPPORTED_TOPOLOGY_LAYERS = {"root", "section", "leaf", "archive"}
LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def normalize_rel(path_str: str) -> str:
    return str(Path(path_str)).replace("\\", "/")


def _normalize_positive_int(value: Any, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    if parsed <= 0:
        return fallback
    return parsed


def _normalize_required_slots(value: Any) -> list[str]:
    slots = (
        value
        if isinstance(value, list)
        else DEFAULT_PROGRESSIVE_DISCLOSURE_SETTINGS["required_slots"]
    )
    normalized: list[str] = []
    seen: set[str] = set()
    for item in slots:
        if not isinstance(item, str):
            continue
        slot = item.strip()
        if not slot or slot in seen:
            continue
        seen.add(slot)
        normalized.append(slot)
    if normalized:
        return normalized
    return list(DEFAULT_PROGRESSIVE_DISCLOSURE_SETTINGS["required_slots"])


def resolve_topology_settings(policy: dict[str, Any] | None) -> dict[str, Any]:
    raw = (
        policy.get("doc_topology")
        if isinstance(policy, dict) and isinstance(policy.get("doc_topology"), dict)
        else {}
    )
    settings = deepcopy(DEFAULT_TOPOLOGY_SETTINGS)
    if not raw:
        return settings

    settings["enabled"] = bool(raw.get("enabled", settings["enabled"]))
    path = str(raw.get("path", "")).strip()
    if path:
        settings["path"] = normalize_rel(path)
    settings["enforce_max_depth"] = bool(
        raw.get("enforce_max_depth", settings["enforce_max_depth"])
    )
    settings["max_depth"] = _normalize_positive_int(
        raw.get("max_depth", settings["max_depth"]),
        int(settings["max_depth"]),
    )
    settings["fail_on_orphan"] = bool(
        raw.get("fail_on_orphan", settings["fail_on_orphan"])
    )
    settings["fail_on_unreachable"] = bool(
        raw.get("fail_on_unreachable", settings["fail_on_unreachable"])
    )
    return settings


def resolve_progressive_disclosure_settings(
    policy: dict[str, Any] | None,
) -> dict[str, Any]:
    raw = (
        policy.get("progressive_disclosure")
        if isinstance(policy, dict)
        and isinstance(policy.get("progressive_disclosure"), dict)
        else {}
    )
    settings = deepcopy(DEFAULT_PROGRESSIVE_DISCLOSURE_SETTINGS)
    if not raw:
        return settings

    settings["enabled"] = bool(raw.get("enabled", settings["enabled"]))
    settings["required_slots"] = _normalize_required_slots(raw.get("required_slots"))
    settings["summary_max_chars"] = _normalize_positive_int(
        raw.get("summary_max_chars", settings["summary_max_chars"]),
        int(settings["summary_max_chars"]),
    )
    settings["max_key_facts"] = _normalize_positive_int(
        raw.get("max_key_facts", settings["max_key_facts"]),
        int(settings["max_key_facts"]),
    )
    settings["max_next_steps"] = _normalize_positive_int(
        raw.get("max_next_steps", settings["max_next_steps"]),
        int(settings["max_next_steps"]),
    )
    settings["fail_on_missing_slots"] = bool(
        raw.get("fail_on_missing_slots", settings["fail_on_missing_slots"])
    )
    return settings


def normalize_topology_payload(
    payload: dict[str, Any],
    settings: dict[str, Any],
) -> tuple[dict[str, Any], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    version_raw = payload.get("version", 1)
    if not isinstance(version_raw, int) or version_raw <= 0:
        errors.append("version must be positive integer")
        version = 1
    else:
        version = version_raw

    root_raw = payload.get("root")
    if not isinstance(root_raw, str) or not root_raw.strip():
        errors.append("root must be non-empty string")
        root = "docs/index.md"
    else:
        root = normalize_rel(root_raw.strip())

    max_depth_raw = payload.get("max_depth", settings.get("max_depth", 3))
    max_depth = _normalize_positive_int(max_depth_raw, int(settings.get("max_depth", 3)))
    if max_depth_raw != max_depth:
        warnings.append(f"max_depth invalid, fallback to {max_depth}")

    nodes_raw = payload.get("nodes")
    nodes: list[dict[str, Any]] = []
    if not isinstance(nodes_raw, list):
        errors.append("nodes must be list")
        nodes_raw = []

    seen_paths: set[str] = set()
    for index, node_raw in enumerate(nodes_raw):
        if not isinstance(node_raw, dict):
            errors.append(f"nodes[{index}] must be object")
            continue

        path_raw = node_raw.get("path")
        if not isinstance(path_raw, str) or not path_raw.strip():
            errors.append(f"nodes[{index}].path must be non-empty string")
            continue
        path = normalize_rel(path_raw.strip())
        if path in seen_paths:
            warnings.append(f"nodes duplicated path: {path}")
        seen_paths.add(path)

        layer_raw = node_raw.get("layer")
        if not isinstance(layer_raw, str) or not layer_raw.strip():
            errors.append(f"nodes[{index}].layer must be non-empty string")
            continue
        layer = layer_raw.strip()
        if layer not in SUPPORTED_TOPOLOGY_LAYERS:
            errors.append(
                f"nodes[{index}].layer invalid: {layer} (expected one of root|section|leaf|archive)"
            )
            continue

        parent_raw = node_raw.get("parent")
        parent: str | None
        if parent_raw is None:
            parent = None
        elif isinstance(parent_raw, str) and parent_raw.strip():
            parent = normalize_rel(parent_raw.strip())
        else:
            errors.append(f"nodes[{index}].parent must be string or null")
            continue

        domain = ""
        domain_raw = node_raw.get("domain")
        if isinstance(domain_raw, str):
            domain = domain_raw.strip()
        elif domain_raw is not None:
            warnings.append(f"nodes[{index}].domain ignored: non-string value")

        node = {
            "path": path,
            "layer": layer,
            "parent": parent,
            "domain": domain,
        }
        nodes.append(node)

    if not nodes:
        warnings.append("nodes is empty")

    path_set = {item["path"] for item in nodes}
    if root not in path_set:
        warnings.append("topology root not present in nodes")
    for item in nodes:
        parent = item.get("parent")
        if parent and parent not in path_set:
            warnings.append(
                f"parent node missing for {item.get('path')}: {parent}"
            )

    archive_raw = payload.get("archive")
    if archive_raw is None:
        archive_raw = {}
    if not isinstance(archive_raw, dict):
        errors.append("archive must be object")
        archive_raw = {}
    archive_root_raw = archive_raw.get("root", "docs/archive")
    archive_root = (
        normalize_rel(str(archive_root_raw).strip())
        if str(archive_root_raw).strip()
        else "docs/archive"
    )
    archive_excluded = bool(
        archive_raw.get("excluded_from_depth_gate", True)
    )

    normalized = {
        "version": version,
        "root": root,
        "max_depth": max_depth,
        "nodes": nodes,
        "archive": {
            "root": archive_root,
            "excluded_from_depth_gate": archive_excluded,
        },
    }
    return normalized, errors, warnings


def load_topology_contract(
    root: Path,
    settings: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    path_rel = normalize_rel(
        str(settings.get("path") or DEFAULT_TOPOLOGY_SETTINGS["path"])
    )
    report: dict[str, Any] = {
        "enabled": bool(settings.get("enabled", False)),
        "path": path_rel,
        "exists": False,
        "loaded": False,
        "errors": [],
        "warnings": [],
        "metrics": {
            "node_count": 0,
        },
    }
    if not report["enabled"]:
        return None, report

    abs_path = (root / path_rel).resolve()
    if not abs_path.exists():
        report["warnings"].append(f"topology file not found: {path_rel}")
        return None, report

    report["exists"] = True
    try:
        payload = json.loads(abs_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"topology file unreadable: {exc}")
        return None, report
    if not isinstance(payload, dict):
        report["errors"].append("topology JSON root must be object")
        return None, report

    normalized, errors, warnings = normalize_topology_payload(payload, settings)
    report["errors"].extend(errors)
    report["warnings"].extend(warnings)
    report["metrics"]["node_count"] = len(normalized.get("nodes", []))
    report["loaded"] = len(errors) == 0
    if not report["loaded"]:
        return None, report
    return normalized, report


def _is_markdown_path(path: str) -> bool:
    return normalize_rel(path).lower().endswith(".md")


def _is_archive_path(path: str, archive_root: str) -> bool:
    normalized_path = normalize_rel(path)
    normalized_archive = normalize_rel(archive_root).rstrip("/")
    return normalized_path == normalized_archive or normalized_path.startswith(
        normalized_archive + "/"
    )


def _should_skip_archive_path(
    path: str,
    archive_root: str,
    exclude_archive: bool,
) -> bool:
    return bool(exclude_archive) and _is_archive_path(path, archive_root)


def _collect_scope_docs(
    root: Path,
    managed_docs: list[str] | None,
    node_paths: list[str],
    archive_root: str,
    exclude_archive: bool,
) -> list[str]:
    scope: set[str] = set()

    if isinstance(managed_docs, list):
        for rel_path in managed_docs:
            if not isinstance(rel_path, str):
                continue
            normalized = normalize_rel(rel_path)
            if not _is_markdown_path(normalized):
                continue
            if _should_skip_archive_path(normalized, archive_root, exclude_archive):
                continue
            if (root / normalized).exists():
                scope.add(normalized)

    for rel_path in node_paths:
        normalized = normalize_rel(rel_path)
        if not _is_markdown_path(normalized):
            continue
        if _should_skip_archive_path(normalized, archive_root, exclude_archive):
            continue
        if (root / normalized).exists():
            scope.add(normalized)

    return sorted(scope)


def _extract_doc_links(root: Path, source_path: str) -> set[str]:
    abs_path = root / source_path
    if not abs_path.exists() or not abs_path.is_file():
        return set()

    links: set[str] = set()
    content = abs_path.read_text(encoding="utf-8", errors="replace")
    for match in LINK_PATTERN.finditer(content):
        link = match.group(1).strip()
        if not link or link.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = link.split("#", 1)[0].strip()
        if not target:
            continue
        resolved = (abs_path.parent / target).resolve()
        try:
            rel_target = normalize_rel(str(resolved.relative_to(root.resolve())))
        except ValueError:
            continue
        links.add(rel_target)
    return links


def _build_parent_children(
    nodes: list[dict[str, Any]],
    archive_root: str,
    exclude_archive: bool,
) -> tuple[dict[str, dict[str, Any]], dict[str, set[str]]]:
    node_map: dict[str, dict[str, Any]] = {}
    children: dict[str, set[str]] = {}

    for node in nodes:
        if not isinstance(node, dict):
            continue
        path = normalize_rel(str(node.get("path", "")).strip())
        if not path:
            continue
        node_map[path] = node

    for path, node in node_map.items():
        if _should_skip_archive_path(path, archive_root, exclude_archive):
            continue
        parent = node.get("parent")
        if not isinstance(parent, str) or not parent.strip():
            continue
        parent_rel = normalize_rel(parent.strip())
        if _should_skip_archive_path(parent_rel, archive_root, exclude_archive):
            continue
        children.setdefault(parent_rel, set()).add(path)

    return node_map, children


def _compute_depths(root_path: str, children: dict[str, set[str]]) -> dict[str, int]:
    depths: dict[str, int] = {root_path: 0}
    queue: deque[str] = deque([root_path])

    while queue:
        current = queue.popleft()
        current_depth = depths.get(current, 0)
        for child in sorted(children.get(current, set())):
            next_depth = current_depth + 1
            if child in depths and depths[child] <= next_depth:
                continue
            depths[child] = next_depth
            queue.append(child)
    return depths


def _compute_navigation_reachability(
    root_path: str,
    adjacency: dict[str, set[str]],
) -> set[str]:
    reachable: set[str] = set()
    queue: deque[str] = deque([root_path])

    while queue:
        current = queue.popleft()
        if current in reachable:
            continue
        reachable.add(current)
        for target in sorted(adjacency.get(current, set())):
            if target not in reachable:
                queue.append(target)
    return reachable


def evaluate_topology(
    root: Path,
    contract: dict[str, Any],
    settings: dict[str, Any],
    managed_docs: list[str] | None = None,
) -> dict[str, Any]:
    archive_cfg = contract.get("archive")
    archive_cfg = archive_cfg if isinstance(archive_cfg, dict) else {}
    archive_root = normalize_rel(str(archive_cfg.get("root") or "docs/archive"))
    archive_excluded = bool(archive_cfg.get("excluded_from_depth_gate", True))
    root_path = normalize_rel(str(contract.get("root") or "docs/index.md"))
    nodes = contract.get("nodes")
    nodes = nodes if isinstance(nodes, list) else []

    node_map, children = _build_parent_children(
        nodes,
        archive_root,
        archive_excluded,
    )
    node_paths = sorted(node_map.keys())
    scope_docs = _collect_scope_docs(
        root,
        managed_docs,
        node_paths,
        archive_root,
        archive_excluded,
    )
    scope_set = set(scope_docs)

    depths = _compute_depths(root_path, children)
    max_depth = max((depths.get(path, 0) for path in scope_docs), default=0)
    depth_limit = _normalize_positive_int(
        settings.get("max_depth", contract.get("max_depth", 3)),
        3,
    )
    over_depth_docs = sorted(
        [
            path
            for path in scope_docs
            if path in depths and int(depths[path]) > depth_limit
        ]
    )

    orphan_docs = sorted([path for path in scope_docs if path not in node_map])

    adjacency: dict[str, set[str]] = {}
    for doc_path in scope_docs:
        targets = _extract_doc_links(root, doc_path)
        adjacency[doc_path] = {target for target in targets if target in scope_set}

    navigation_reachable = (
        _compute_navigation_reachability(root_path, adjacency)
        if root_path in scope_set
        else set()
    )
    unreachable_docs = sorted(
        [path for path in scope_docs if path not in navigation_reachable]
    )

    navigation_missing_links: list[dict[str, str]] = []
    for child_path, node in sorted(node_map.items()):
        if child_path not in scope_set:
            continue
        if _should_skip_archive_path(child_path, archive_root, archive_excluded):
            continue
        if child_path in navigation_reachable:
            continue
        parent = node.get("parent")
        if not isinstance(parent, str) or not parent.strip():
            continue
        parent_path = normalize_rel(parent.strip())
        if parent_path not in scope_set or _should_skip_archive_path(
            parent_path,
            archive_root,
            archive_excluded,
        ):
            continue
        parent_links = adjacency.get(parent_path, set())
        if child_path not in parent_links:
            navigation_missing_links.append(
                {"parent": parent_path, "child": child_path}
            )

    grouped_missing: dict[str, set[str]] = {}
    for item in navigation_missing_links:
        parent_path = item["parent"]
        child_path = item["child"]
        grouped_missing.setdefault(parent_path, set()).add(child_path)
    navigation_missing_by_parent = [
        {"parent": parent_path, "missing_children": sorted(children_set)}
        for parent_path, children_set in sorted(grouped_missing.items())
    ]

    missing_node_files = sorted(
        [
            path
            for path in node_paths
            if _is_markdown_path(path)
            and not _should_skip_archive_path(path, archive_root, archive_excluded)
            and not (root / path).exists()
        ]
    )

    reachable_ratio = (
        1.0
        if not scope_docs
        else round((len(scope_docs) - len(unreachable_docs)) / len(scope_docs), 4)
    )

    warnings: list[str] = []
    if missing_node_files:
        warnings.append(
            "topology nodes reference missing markdown files: "
            + ", ".join(missing_node_files[:20])
        )

    metrics = {
        "node_count": len(node_paths),
        "managed_markdown_count": len(scope_docs),
        "topology_reachable_ratio": reachable_ratio,
        "topology_orphan_count": len(orphan_docs),
        "topology_unreachable_count": len(unreachable_docs),
        "topology_max_depth": int(max_depth),
        "topology_depth_limit": int(depth_limit),
        "topology_over_depth_count": len(over_depth_docs),
        "navigation_missing_count": len(navigation_missing_links),
    }
    return {
        "metrics": metrics,
        "warnings": warnings,
        "scope_docs": scope_docs,
        "orphan_docs": orphan_docs,
        "unreachable_docs": unreachable_docs,
        "over_depth_docs": over_depth_docs,
        "missing_node_files": missing_node_files,
        "navigation_missing_links": navigation_missing_links,
        "navigation_missing_by_parent": navigation_missing_by_parent,
    }
