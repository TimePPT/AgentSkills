#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
from typing import Any

DEFAULT_PRIMARY_LANGUAGE = "zh-CN"
DEFAULT_PROFILE = "zh-CN"
SUPPORTED_PROFILES = {"zh-CN", "en-US"}

DEFAULT_ENGLISH_ONLY_CONTEXTS = [
    "code_identifiers",
    "config_keys",
    "cli_flags",
    "file_paths",
]

BASE_POLICY = {
    "version": 1,
    "mode_default": "audit",
    "require_evidence": True,
    "delete_behavior": "archive",
    "bootstrap_manifest_strategy": "adaptive",
    "bootstrap_agents_md": True,
    "doc_goals": {
        "include": [],
        "exclude": [],
    },
    "manifest_evolution": {
        "allow_additive": True,
        "allow_pruning": False,
    },
    "adaptive_manifest_overrides": {
        "include_files": [],
        "include_dirs": [],
        "exclude_files": [],
        "exclude_dirs": [],
    },
    "doc_metadata": {
        "enabled": True,
        "require_owner": True,
        "require_last_reviewed": True,
        "require_review_cycle_days": True,
        "default_owner": "TODO-owner",
        "default_review_cycle_days": 90,
        "ignore_paths": ["docs/archive/**"],
        "stale_warning_enabled": True,
    },
    "doc_gardening": {
        "enabled": True,
        "apply_mode": "apply-safe",
        "fail_on_drift": True,
        "fail_on_freshness": True,
        "report_json": "docs/.doc-garden-report.json",
        "report_md": "docs/.doc-garden-report.md",
    },
    "allow_auto_update": [
        "docs/index.md",
        "docs/architecture.md",
        "docs/runbook.md",
        "docs/glossary.md",
        "docs/incident-response.md",
        "docs/security.md",
        "docs/compliance.md",
    ],
    "protect_from_auto_overwrite": ["docs/adr/**"],
}

DOC_DEFINITIONS = {
    "docs/index.md": {
        "required_sections": ["title", "core_docs", "workflow"],
        "template_order": ["title", "core_docs", "workflow"],
        "sections": {
            "title": {
                "markers": {
                    "zh-CN": "# 文档索引",
                    "en-US": "# Documentation Index",
                },
                "content": {
                    "zh-CN": "# 文档索引",
                    "en-US": "# Documentation Index",
                },
            },
            "core_docs": {
                "markers": {
                    "zh-CN": "## 核心文档",
                    "en-US": "## Core Documents",
                },
                "content": {
                    "zh-CN": "## 核心文档\n\n- `docs/.doc-policy.json`\n- `docs/.doc-manifest.json`\n- 按仓库演进逐步补充 `docs/architecture.md`、`docs/runbook.md` 等专题文档。",
                    "en-US": "## Core Documents\n\n- `docs/.doc-policy.json`\n- `docs/.doc-manifest.json`\n- Add specialized docs like `docs/architecture.md` and `docs/runbook.md` as the repository evolves.",
                },
            },
            "workflow": {
                "markers": {
                    "zh-CN": "## 操作流程",
                    "en-US": "## Operational Workflow",
                },
                "content": {
                    "zh-CN": "## 操作流程\n\n1. 运行 repository scan 并生成 doc plan。\n2. 审阅 actions 后执行 safe mode。\n3. 合并前校验 links 与 drift 状态。",
                    "en-US": "## Operational Workflow\n\n1. Run repository scan and generate a doc plan.\n2. Review actions and apply with safe mode.\n3. Validate links and drift status before merge.",
                },
            },
        },
    },
    "docs/architecture.md": {
        "required_sections": ["title", "module_inventory", "dependency_manifests"],
        "template_order": [
            "title",
            "summary",
            "module_inventory",
            "dependency_manifests",
        ],
        "sections": {
            "title": {
                "markers": {
                    "zh-CN": "# 仓库架构",
                    "en-US": "# Repository Architecture",
                },
                "content": {
                    "zh-CN": "# 仓库架构",
                    "en-US": "# Repository Architecture",
                },
            },
            "summary": {
                "markers": {
                    "zh-CN": "## 概述",
                    "en-US": "## Summary",
                },
                "content": {
                    "zh-CN": "## 概述\n\n说明仓库边界与执行模型。",
                    "en-US": "## Summary\n\nDescribe the repository boundaries and execution model.",
                },
            },
            "module_inventory": {
                "markers": {
                    "zh-CN": "## 模块清单",
                    "en-US": "## Module Inventory",
                },
                "content": {
                    "zh-CN": "## 模块清单\n\n列出顶层 modules 及其职责。",
                    "en-US": "## Module Inventory\n\nList top-level modules and their responsibilities.",
                },
            },
            "dependency_manifests": {
                "markers": {
                    "zh-CN": "## 依赖清单",
                    "en-US": "## Dependency Manifests",
                },
                "content": {
                    "zh-CN": "## 依赖清单\n\n列出构建与 dependency manifests。",
                    "en-US": "## Dependency Manifests\n\nList build/dependency manifests used by this repository.",
                },
            },
        },
    },
    "docs/runbook.md": {
        "required_sections": ["title", "dev_commands", "validation_commands"],
        "template_order": ["title", "dev_commands", "validation_commands"],
        "sections": {
            "title": {
                "markers": {
                    "zh-CN": "# 运行手册",
                    "en-US": "# Runbook",
                },
                "content": {
                    "zh-CN": "# 运行手册",
                    "en-US": "# Runbook",
                },
            },
            "dev_commands": {
                "markers": {
                    "zh-CN": "## 开发命令",
                    "en-US": "## Development Commands",
                },
                "content": {
                    "zh-CN": "## 开发命令\n\n记录 build、run 与本地开发工作流命令。",
                    "en-US": "## Development Commands\n\nDocument build, run, and local workflow commands.",
                },
            },
            "validation_commands": {
                "markers": {
                    "zh-CN": "## 校验命令",
                    "en-US": "## Validation Commands",
                },
                "content": {
                    "zh-CN": "## 校验命令\n\n记录 lint、test 与 drift check 命令。",
                    "en-US": "## Validation Commands\n\nDocument lint, test, and drift check commands.",
                },
            },
        },
    },
    "docs/glossary.md": {
        "required_sections": ["title"],
        "template_order": ["title", "summary"],
        "sections": {
            "title": {
                "markers": {
                    "zh-CN": "# 术语表",
                    "en-US": "# Glossary",
                },
                "content": {
                    "zh-CN": "# 术语表",
                    "en-US": "# Glossary",
                },
            },
            "summary": {
                "markers": {
                    "zh-CN": "仓库特有术语",
                    "en-US": "repository-specific terminology",
                },
                "content": {
                    "zh-CN": "记录仓库特有术语、缩写与上下文定义。",
                    "en-US": "Document repository-specific terminology.",
                },
            },
        },
    },
    "docs/incident-response.md": {
        "required_sections": [
            "title",
            "severity_levels",
            "response_flow",
            "postmortem",
        ],
        "template_order": ["title", "severity_levels", "response_flow", "postmortem"],
        "sections": {
            "title": {
                "markers": {
                    "zh-CN": "# 事故响应",
                    "en-US": "# Incident Response",
                },
                "content": {
                    "zh-CN": "# 事故响应",
                    "en-US": "# Incident Response",
                },
            },
            "severity_levels": {
                "markers": {
                    "zh-CN": "## 严重级别",
                    "en-US": "## Severity Levels",
                },
                "content": {
                    "zh-CN": "## 严重级别\n\n- `SEV1`：核心功能不可用，需要立即响应。\n- `SEV2`：关键功能受影响，需要尽快修复。\n- `SEV3`：局部影响，可按计划处理。",
                    "en-US": "## Severity Levels\n\n- `SEV1`: Core functionality unavailable, immediate response required.\n- `SEV2`: Key functionality degraded, urgent mitigation required.\n- `SEV3`: Limited impact, plan and track remediation.",
                },
            },
            "response_flow": {
                "markers": {
                    "zh-CN": "## 响应流程",
                    "en-US": "## Response Flow",
                },
                "content": {
                    "zh-CN": "## 响应流程\n\n1. 触发告警并确认值班负责人。\n2. 建立事件频道并记录时间线。\n3. 执行缓解动作并持续同步状态。\n4. 恢复服务后进入复盘流程。",
                    "en-US": "## Response Flow\n\n1. Trigger alert and confirm incident commander.\n2. Create incident channel and capture timeline.\n3. Execute mitigation and publish status updates.\n4. After recovery, start postmortem workflow.",
                },
            },
            "postmortem": {
                "markers": {
                    "zh-CN": "## 复盘要求",
                    "en-US": "## Postmortem Requirements",
                },
                "content": {
                    "zh-CN": "## 复盘要求\n\n- 记录根因、影响范围、恢复时间与改进项。\n- 改进项必须进入可追踪任务系统并指定 owner。",
                    "en-US": "## Postmortem Requirements\n\n- Document root cause, impact scope, recovery timeline, and action items.\n- Track each action item with an owner in the task system.",
                },
            },
        },
    },
    "docs/security.md": {
        "required_sections": [
            "title",
            "threat_model",
            "security_controls",
            "vuln_management",
        ],
        "template_order": [
            "title",
            "threat_model",
            "security_controls",
            "vuln_management",
        ],
        "sections": {
            "title": {
                "markers": {
                    "zh-CN": "# 安全基线",
                    "en-US": "# Security Baseline",
                },
                "content": {
                    "zh-CN": "# 安全基线",
                    "en-US": "# Security Baseline",
                },
            },
            "threat_model": {
                "markers": {
                    "zh-CN": "## 威胁模型",
                    "en-US": "## Threat Model",
                },
                "content": {
                    "zh-CN": "## 威胁模型\n\n描述关键资产、威胁来源、攻击面与主要风险假设。",
                    "en-US": "## Threat Model\n\nDescribe critical assets, threat actors, attack surfaces, and risk assumptions.",
                },
            },
            "security_controls": {
                "markers": {
                    "zh-CN": "## 安全控制",
                    "en-US": "## Security Controls",
                },
                "content": {
                    "zh-CN": "## 安全控制\n\n- 认证与授权策略\n- 密钥与凭据管理\n- 依赖与镜像扫描策略",
                    "en-US": "## Security Controls\n\n- Authentication and authorization policy\n- Secret and credential management\n- Dependency and image scanning policy",
                },
            },
            "vuln_management": {
                "markers": {
                    "zh-CN": "## 漏洞管理",
                    "en-US": "## Vulnerability Management",
                },
                "content": {
                    "zh-CN": "## 漏洞管理\n\n定义漏洞分级、响应 SLA、修复验证与披露流程。",
                    "en-US": "## Vulnerability Management\n\nDefine vulnerability severity levels, response SLA, remediation verification, and disclosure workflow.",
                },
            },
        },
    },
    "docs/compliance.md": {
        "required_sections": [
            "title",
            "framework_scope",
            "control_mapping",
            "evidence_retention",
        ],
        "template_order": [
            "title",
            "framework_scope",
            "control_mapping",
            "evidence_retention",
        ],
        "sections": {
            "title": {
                "markers": {
                    "zh-CN": "# 合规控制",
                    "en-US": "# Compliance Controls",
                },
                "content": {
                    "zh-CN": "# 合规控制",
                    "en-US": "# Compliance Controls",
                },
            },
            "framework_scope": {
                "markers": {
                    "zh-CN": "## 框架范围",
                    "en-US": "## Framework Scope",
                },
                "content": {
                    "zh-CN": "## 框架范围\n\n记录适用的合规框架（如 SOC2、ISO27001、GDPR）及适用边界。",
                    "en-US": "## Framework Scope\n\nList applicable frameworks (for example SOC2, ISO27001, GDPR) and system boundaries in scope.",
                },
            },
            "control_mapping": {
                "markers": {
                    "zh-CN": "## 控制映射",
                    "en-US": "## Control Mapping",
                },
                "content": {
                    "zh-CN": "## 控制映射\n\n将关键控制项映射到实现位置、责任人和验证方式。",
                    "en-US": "## Control Mapping\n\nMap key controls to implementation locations, owners, and validation methods.",
                },
            },
            "evidence_retention": {
                "markers": {
                    "zh-CN": "## 证据留存",
                    "en-US": "## Evidence Retention",
                },
                "content": {
                    "zh-CN": "## 证据留存\n\n定义审计证据的来源、保存周期、访问权限和抽样方式。",
                    "en-US": "## Evidence Retention\n\nDefine audit evidence sources, retention windows, access controls, and sampling process.",
                },
            },
        },
    },
}

MODULE_LINE_TEMPLATES = {
    "zh-CN": "- `{module}`：TODO 补充职责说明。",
    "en-US": "- `{module}`: TODO define responsibility.",
}

AGENTS_MD_TEMPLATES = {
    "zh-CN": """# AGENTS

## 目标

将 `docs/` 作为仓库的 system of record。

## 导航

- 从 `docs/index.md` 开始。
- Policy: `docs/.doc-policy.json`。
- Target structure: `docs/.doc-manifest.json`。

## 标准命令

```bash
REPO_ROOT="/absolute/path/to/repo"
PYTHON_BIN="${PYTHON_BIN:-python3}"
command -v "$PYTHON_BIN" >/dev/null || { echo "python not found: $PYTHON_BIN" >&2; exit 2; }
CODEX_HOME_RESOLVED="${CODEX_HOME:-$HOME/.codex}"
if [ -n "${SKILL_DIR:-}" ]; then
  [ -d "$SKILL_DIR/scripts" ] || {
    echo "invalid SKILL_DIR: $SKILL_DIR (expected scripts/ under this path)" >&2
    exit 2
  }
elif [ -d "$REPO_ROOT/.agents/skills/docs-sor-maintainer/scripts" ]; then
  SKILL_DIR="$REPO_ROOT/.agents/skills/docs-sor-maintainer"
elif [ -d "$CODEX_HOME_RESOLVED/skills/docs-sor-maintainer/scripts" ]; then
  SKILL_DIR="$CODEX_HOME_RESOLVED/skills/docs-sor-maintainer"
else
  echo 'docs-sor-maintainer not found. Set SKILL_DIR or install under .agents/skills or $HOME/.codex/skills.' >&2
  exit 2
fi
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode audit --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --fail-on-drift --fail-on-freshness
```

## Guardrails

- 保持 AGENTS 精简；详细知识放在 `docs/`。
- 禁止硬删除 docs；统一归档到 `docs/archive/`。
- 在 CI 驱动仓库中通过 PR 流程应用文档变更。
""",
    "en-US": """# AGENTS

## Purpose

Treat `docs/` as the repository system of record.

## Navigation

- Start at `docs/index.md`.
- Policy: `docs/.doc-policy.json`.
- Target structure: `docs/.doc-manifest.json`.

## Standard Commands

```bash
REPO_ROOT="/absolute/path/to/repo"
PYTHON_BIN="${PYTHON_BIN:-python3}"
command -v "$PYTHON_BIN" >/dev/null || { echo "python not found: $PYTHON_BIN" >&2; exit 2; }
CODEX_HOME_RESOLVED="${CODEX_HOME:-$HOME/.codex}"
if [ -n "${SKILL_DIR:-}" ]; then
  [ -d "$SKILL_DIR/scripts" ] || {
    echo "invalid SKILL_DIR: $SKILL_DIR (expected scripts/ under this path)" >&2
    exit 2
  }
elif [ -d "$REPO_ROOT/.agents/skills/docs-sor-maintainer/scripts" ]; then
  SKILL_DIR="$REPO_ROOT/.agents/skills/docs-sor-maintainer"
elif [ -d "$CODEX_HOME_RESOLVED/skills/docs-sor-maintainer/scripts" ]; then
  SKILL_DIR="$CODEX_HOME_RESOLVED/skills/docs-sor-maintainer"
else
  echo 'docs-sor-maintainer not found. Set SKILL_DIR or install under .agents/skills or $HOME/.codex/skills.' >&2
  exit 2
fi
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode audit --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --fail-on-drift --fail-on-freshness
```

## Guardrails

- Keep AGENTS concise; store detailed knowledge under `docs/`.
- Do not hard-delete docs; archive to `docs/archive/`.
- Apply changes through PR flow in CI-driven repositories.
""",
}


def _uniq(values: list[str]) -> list[str]:
    seen = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            ordered.append(value)
            seen.add(value)
    return ordered


def normalize_primary_language(raw: str | None) -> str:
    if raw is None:
        return DEFAULT_PRIMARY_LANGUAGE
    value = str(raw).strip()
    return value or DEFAULT_PRIMARY_LANGUAGE


def resolve_template_profile(
    primary: str | None, explicit_profile: str | None = None
) -> str:
    candidate = explicit_profile or primary or DEFAULT_PRIMARY_LANGUAGE
    candidate = str(candidate).strip()
    if candidate in SUPPORTED_PROFILES:
        return candidate

    low = candidate.lower()
    if low.startswith("zh"):
        return "zh-CN"
    if low.startswith("en"):
        return "en-US"
    return "en-US"


def build_default_policy(
    primary_language: str | None = None, profile: str | None = None
) -> dict[str, Any]:
    primary = normalize_primary_language(primary_language)
    resolved_profile = resolve_template_profile(primary, profile)

    policy = deepcopy(BASE_POLICY)
    policy["language"] = {
        "primary": primary,
        "profile": resolved_profile,
        "locked": True,
        "preserve_english_terms": True,
        "english_only_contexts": deepcopy(DEFAULT_ENGLISH_ONLY_CONTEXTS),
    }
    return policy


def resolve_language_settings(
    existing_policy: dict[str, Any] | None, init_language: str | None
) -> dict[str, Any]:
    policy = existing_policy if isinstance(existing_policy, dict) else {}
    language = (
        policy.get("language") if isinstance(policy.get("language"), dict) else {}
    )

    existing_primary_raw = language.get("primary") if language else None
    existing_primary = (
        normalize_primary_language(existing_primary_raw)
        if existing_primary_raw
        else None
    )
    existing_profile = (
        language.get("profile") if isinstance(language.get("profile"), str) else None
    )
    locked = bool(language.get("locked", True)) if language else True

    requested_primary = (
        normalize_primary_language(init_language) if init_language else None
    )

    if existing_primary and locked:
        primary = existing_primary
        source = "policy_locked"
    elif existing_primary and requested_primary:
        primary = requested_primary
        source = "cli_override"
    elif existing_primary:
        primary = existing_primary
        source = "policy"
    elif requested_primary:
        primary = requested_primary
        source = "cli_init"
    else:
        primary = DEFAULT_PRIMARY_LANGUAGE
        source = "default"

    profile = resolve_template_profile(primary, existing_profile)

    preserve_english_terms = (
        bool(language.get("preserve_english_terms", True)) if language else True
    )

    raw_contexts = language.get("english_only_contexts") if language else None
    if isinstance(raw_contexts, list) and raw_contexts:
        english_only_contexts = [str(item) for item in raw_contexts]
    else:
        english_only_contexts = deepcopy(DEFAULT_ENGLISH_ONLY_CONTEXTS)

    return {
        "primary": primary,
        "profile": profile,
        "locked": locked,
        "preserve_english_terms": preserve_english_terms,
        "english_only_contexts": english_only_contexts,
        "source": source,
    }


def merge_language_into_policy(
    policy: dict[str, Any], language_settings: dict[str, Any]
) -> dict[str, Any]:
    merged = deepcopy(policy)
    merged_language = {
        "primary": language_settings["primary"],
        "profile": language_settings["profile"],
        "locked": bool(language_settings.get("locked", True)),
        "preserve_english_terms": bool(
            language_settings.get("preserve_english_terms", True)
        ),
        "english_only_contexts": list(
            language_settings.get("english_only_contexts")
            or DEFAULT_ENGLISH_ONLY_CONTEXTS
        ),
    }
    merged["language"] = merged_language
    return merged


def get_required_sections(rel_path: str) -> list[str]:
    doc = DOC_DEFINITIONS.get(rel_path)
    if not doc:
        return []
    return list(doc["required_sections"])


def get_template_sections(rel_path: str) -> list[str]:
    doc = DOC_DEFINITIONS.get(rel_path)
    if not doc:
        return []
    return list(doc["template_order"])


def get_section_markers(rel_path: str, section_id: str) -> list[str]:
    doc = DOC_DEFINITIONS.get(rel_path)
    if not doc:
        return []
    section = doc["sections"].get(section_id)
    if not section:
        return []
    markers = [str(v) for v in section["markers"].values() if isinstance(v, str) and v]
    return _uniq(markers)


def get_section_heading(rel_path: str, section_id: str, profile: str) -> str:
    doc = DOC_DEFINITIONS.get(rel_path)
    if not doc:
        return section_id
    section = doc["sections"].get(section_id)
    if not section:
        return section_id

    markers = section["markers"]
    if profile in markers:
        return markers[profile]
    if DEFAULT_PROFILE in markers:
        return markers[DEFAULT_PROFILE]
    return next(iter(markers.values()))


def get_section_text(rel_path: str, section_id: str, profile: str) -> str:
    doc = DOC_DEFINITIONS.get(rel_path)
    if not doc:
        return ""
    section = doc["sections"].get(section_id)
    if not section:
        return ""

    content = section["content"]
    if profile in content:
        return str(content[profile]).rstrip() + "\n"
    if DEFAULT_PROFILE in content:
        return str(content[DEFAULT_PROFILE]).rstrip() + "\n"
    return str(next(iter(content.values()))).rstrip() + "\n"


def get_managed_template(rel_path: str, profile: str) -> str:
    section_ids = get_template_sections(rel_path)
    if not section_ids:
        if profile.startswith("zh"):
            return "# TODO\n\n请补充与仓库相关的文档内容。\n"
        return "# TODO\n\nAdd repository-specific content.\n"

    blocks = [
        get_section_text(rel_path, section_id, profile).strip()
        for section_id in section_ids
    ]
    return "\n\n".join(block for block in blocks if block).rstrip() + "\n"


def get_module_inventory_heading(profile: str) -> str:
    return get_section_heading("docs/architecture.md", "module_inventory", profile)


def get_module_inventory_markers() -> list[str]:
    return get_section_markers("docs/architecture.md", "module_inventory")


def get_module_line_template(profile: str) -> str:
    return MODULE_LINE_TEMPLATES.get(profile, MODULE_LINE_TEMPLATES["en-US"])


def get_agents_md_template(profile: str) -> str:
    return AGENTS_MD_TEMPLATES.get(profile, AGENTS_MD_TEMPLATES["en-US"])
