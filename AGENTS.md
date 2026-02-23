# AGENTS

## 目标

将 `docs/` 作为仓库的 system of record。

## 导航

- 从 `docs/index.md` 开始。
- [docs/index.md](./docs/index.md)
- [docs/.doc-policy.json](./docs/.doc-policy.json)
- [docs/.doc-manifest.json](./docs/.doc-manifest.json)
- [docs/runbook.md](./docs/runbook.md)
- [docs/exec-plans/active/docs-sor-roadmap-v2.5-hybrid-template-llm-governance.md](./docs/exec-plans/active/docs-sor-roadmap-v2.5-hybrid-template-llm-governance.md)
- [docs/exec-plans/active/docs-sor-legacy-migration-automation-plan.md](./docs/exec-plans/active/docs-sor-legacy-migration-automation-plan.md)
- [docs/exec-plans/active/docs-sor-roadmap-v2.1-phase-e-delivery-preacceptance-anti-drift.md](./docs/exec-plans/active/docs-sor-roadmap-v2.1-phase-e-delivery-preacceptance-anti-drift.md)
- [docs/exec-plans/active/docs-sor-roadmap-v2.2-phase-f-agent-runtime-semantic-hardening.md](./docs/exec-plans/active/docs-sor-roadmap-v2.2-phase-f-agent-runtime-semantic-hardening.md)
- [docs/exec-plans/active/docs-sor-roadmap-v2.1-semantic-structured-generation.md](./docs/exec-plans/active/docs-sor-roadmap-v2.1-semantic-structured-generation.md)
- 当前顶层模块：`skills`。

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
elif [ -d "$REPO_ROOT/skills/docs-sor-maintainer/scripts" ]; then
  SKILL_DIR="$REPO_ROOT/skills/docs-sor-maintainer"
elif [ -d "$REPO_ROOT/.agents/skills/docs-sor-maintainer/scripts" ]; then
  SKILL_DIR="$REPO_ROOT/.agents/skills/docs-sor-maintainer"
elif [ -d "$CODEX_HOME_RESOLVED/skills/docs-sor-maintainer/scripts" ]; then
  SKILL_DIR="$CODEX_HOME_RESOLVED/skills/docs-sor-maintainer"
else
  echo 'docs-sor-maintainer not found. Set SKILL_DIR or install under skills, .agents/skills or $HOME/.codex/skills.' >&2
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
