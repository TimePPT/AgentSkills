#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

IGNORE_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "target",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tmp",
}

LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".go": "go",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".java": "java",
    ".kt": "kotlin",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".c": "c",
    ".swift": "swift",
}

BUILD_MANIFESTS = [
    "go.mod",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "Makefile",
]

CI_FILES = [
    ".github/workflows",
    ".gitlab-ci.yml",
    "Jenkinsfile",
    ".circleci/config.yml",
]

TEST_FILE_PATTERNS = [
    "test_*.py",
    "*_test.py",
    "*.spec.ts",
    "*.test.ts",
    "*.spec.js",
    "*.test.js",
    "*_test.go",
    "*Test.java",
]
TEST_DIR_NAMES = {"tests", "test", "__tests__", "spec", "specs"}

API_SIGNAL_PATTERNS = [
    "*openapi*.yaml",
    "*openapi*.yml",
    "*swagger*.yaml",
    "*swagger*.yml",
    "*/api/*",
    "*/apis/*",
    "*/routes/*",
    "*/router/*",
    "*/controllers/*",
    "*/handlers/*",
]

DATA_SIGNAL_PATTERNS = [
    "*/migrations/*",
    "*/migration/*",
    "*/alembic/*",
    "*.sql",
    "*/schema/*",
    "*/models/*",
]

DELIVERY_SIGNAL_PATTERNS = [
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Procfile",
    "helmfile.yaml",
    "helmfile.yml",
    "*/deploy/*",
    "*/deployment/*",
    "*/release/*",
]

OPS_SIGNAL_PATTERNS = [
    "k8s/*",
    "kubernetes/*",
    "infra/*",
    "terraform/*",
    "ansible/*",
]

INCIDENT_SIGNAL_PATTERNS = [
    "incident/**",
    "**/incident/**",
    "**/*incident*.md",
    "**/*postmortem*.md",
    "**/*oncall*",
    "**/*pagerduty*",
]

SECURITY_SIGNAL_PATTERNS = [
    "SECURITY.md",
    "**/SECURITY.md",
    "security/**",
    "**/security/**",
    "**/*threat-model*",
    "**/*sast*",
    "**/*gitleaks*",
    "**/*trivy*",
    "**/*.snyk*",
]

COMPLIANCE_SIGNAL_PATTERNS = [
    "compliance/**",
    "**/compliance/**",
    "**/*soc2*",
    "**/*iso27001*",
    "**/*gdpr*",
    "**/*hipaa*",
    "**/*pci*",
    "**/controls/**",
    "**/audit/**",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_posix(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def should_skip(path: Path, root: Path) -> bool:
    rel_parts = path.relative_to(root).parts
    return any(part in IGNORE_DIRS for part in rel_parts)


def iter_repo_files(root: Path):
    for path in root.rglob("*"):
        if should_skip(path, root):
            continue
        if path.is_file():
            yield path


def detect_languages(root: Path) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for file_path in iter_repo_files(root):
        lang = LANGUAGE_BY_EXTENSION.get(file_path.suffix.lower())
        if lang:
            counts[lang] += 1
    return dict(sorted(counts.items()))


def detect_manifests(root: Path) -> dict[str, bool]:
    result = {}
    for item in BUILD_MANIFESTS:
        result[item] = (root / item).exists()
    return result


def detect_ci(root: Path) -> list[str]:
    ci_paths: list[str] = []
    for item in CI_FILES:
        p = root / item
        if p.exists():
            if p.is_dir():
                for wf in sorted(p.glob("*.y*ml")):
                    ci_paths.append(str(wf.relative_to(root)).replace("\\", "/"))
            else:
                ci_paths.append(item)
    return sorted(set(ci_paths))


def detect_entrypoints(root: Path) -> list[str]:
    candidates = [
        "main.py",
        "main.go",
        "manage.py",
        "cmd",
        "src/main.py",
        "src/main.go",
    ]
    found: list[str] = []
    for item in candidates:
        p = root / item
        if not p.exists():
            continue
        if p.is_file():
            found.append(item)
        else:
            for child in p.rglob("main.go"):
                if should_skip(child, root):
                    continue
                found.append(str(child.relative_to(root)).replace("\\", "/"))
    return sorted(set(found))


def detect_top_level_modules(root: Path) -> list[str]:
    exclude = IGNORE_DIRS | {"docs", "scripts", "references", "assets", "agents"}
    modules = []
    for path in root.iterdir():
        if not path.is_dir():
            continue
        if path.name.startswith(".") or path.name in exclude:
            continue
        modules.append(path.name)
    return sorted(modules)


def detect_docs_state(root: Path) -> dict:
    docs_dir = root / "docs"
    markdown_files: list[str] = []
    if docs_dir.exists():
        for p in docs_dir.rglob("*.md"):
            if p.is_file() and not should_skip(p, root):
                markdown_files.append(str(p.relative_to(root)).replace("\\", "/"))
    return {
        "docs_exists": docs_dir.exists(),
        "docs_markdown_files": sorted(markdown_files),
        "docs_markdown_count": len(markdown_files),
    }


def _match_any(rel_path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel_path, pattern) for pattern in patterns)


def detect_test_signals(root: Path) -> dict[str, object]:
    test_files: set[str] = set()
    test_dirs: set[str] = set()

    for file_path in iter_repo_files(root):
        rel = to_posix(file_path, root)
        if _match_any(rel, TEST_FILE_PATTERNS):
            test_files.add(rel)

        rel_parts = Path(rel).parts
        for index, part in enumerate(rel_parts[:-1]):
            if part.lower() in TEST_DIR_NAMES:
                test_dirs.add(str(Path(*rel_parts[: index + 1])).replace("\\", "/"))
                break

    return {
        "has_tests": bool(test_files or test_dirs),
        "test_file_count": len(test_files),
        "test_files": sorted(test_files),
        "test_dirs": sorted(test_dirs),
    }


def _detect_generic_signals(root: Path, patterns: list[str]) -> dict[str, object]:
    matched: set[str] = set()
    for file_path in iter_repo_files(root):
        rel = to_posix(file_path, root)
        if _match_any(rel, patterns):
            matched.add(rel)

    return {
        "detected": bool(matched),
        "count": len(matched),
        "paths": sorted(matched),
    }


def detect_api_signals(root: Path) -> dict[str, object]:
    return _detect_generic_signals(root, API_SIGNAL_PATTERNS)


def detect_data_signals(root: Path) -> dict[str, object]:
    return _detect_generic_signals(root, DATA_SIGNAL_PATTERNS)


def detect_delivery_signals(root: Path) -> dict[str, object]:
    return _detect_generic_signals(root, DELIVERY_SIGNAL_PATTERNS)


def detect_ops_signals(root: Path) -> dict[str, object]:
    return _detect_generic_signals(root, OPS_SIGNAL_PATTERNS)


def detect_incident_signals(root: Path) -> dict[str, object]:
    return _detect_generic_signals(root, INCIDENT_SIGNAL_PATTERNS)


def detect_security_signals(root: Path) -> dict[str, object]:
    return _detect_generic_signals(root, SECURITY_SIGNAL_PATTERNS)


def detect_compliance_signals(root: Path) -> dict[str, object]:
    return _detect_generic_signals(root, COMPLIANCE_SIGNAL_PATTERNS)


def scan_repository(root: Path) -> dict:
    all_files = list(iter_repo_files(root))
    top_level_files = sorted(
        str(p.relative_to(root)).replace("\\", "/")
        for p in root.iterdir()
        if p.is_file() and not p.name.startswith(".")
    )

    manifests = detect_manifests(root)
    ci = detect_ci(root)
    signals = {
        "tests": detect_test_signals(root),
        "api": detect_api_signals(root),
        "data": detect_data_signals(root),
        "delivery": detect_delivery_signals(root),
        "ops": detect_ops_signals(root),
        "incident": detect_incident_signals(root),
        "security": detect_security_signals(root),
        "compliance": detect_compliance_signals(root),
    }

    return {
        "generated_at": utc_now(),
        "root": str(root),
        "repo_name": root.name,
        "stats": {
            "file_count": len(all_files),
            "top_level_file_count": len(top_level_files),
        },
        "top_level_files": top_level_files,
        "modules": detect_top_level_modules(root),
        "entrypoints": detect_entrypoints(root),
        "languages": detect_languages(root),
        "manifests": manifests,
        "ci": ci,
        "docs": detect_docs_state(root),
        "signals": signals,
        "has_agents_md": (root / "AGENTS.md").exists(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan repository facts for docs planning."
    )
    parser.add_argument("--root", required=True, help="Repository root path")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    parser.add_argument(
        "--pretty", action="store_true", help="Pretty-print JSON output"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output).resolve()

    if not root.exists() or not root.is_dir():
        raise SystemExit(f"[ERROR] Invalid root path: {root}")

    facts = scan_repository(root)
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", encoding="utf-8") as f:
        if args.pretty:
            json.dump(facts, f, ensure_ascii=False, indent=2)
            f.write("\n")
        else:
            json.dump(facts, f, ensure_ascii=False)

    print(f"[OK] Wrote facts to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
