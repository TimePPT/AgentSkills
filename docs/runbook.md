<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-23 -->
<!-- doc-review-cycle-days: 90 -->

# 运行手册

## 开发命令

统一变量：

```bash
REPO_ROOT="/Users/tompoet/AgentSkills"
PYTHON_BIN="${PYTHON_BIN:-python3}"
CODEX_HOME_RESOLVED="${CODEX_HOME:-$HOME/.codex}"
if [ -n "${SKILL_DIR:-}" ]; then
  [ -d "$SKILL_DIR/scripts" ] || { echo "invalid SKILL_DIR: $SKILL_DIR" >&2; exit 2; }
elif [ -d "$REPO_ROOT/skills/docs-sor-maintainer/scripts" ]; then
  SKILL_DIR="$REPO_ROOT/skills/docs-sor-maintainer"
elif [ -d "$REPO_ROOT/.agents/skills/docs-sor-maintainer/scripts" ]; then
  SKILL_DIR="$REPO_ROOT/.agents/skills/docs-sor-maintainer"
elif [ -d "$CODEX_HOME_RESOLVED/skills/docs-sor-maintainer/scripts" ]; then
  SKILL_DIR="$CODEX_HOME_RESOLVED/skills/docs-sor-maintainer"
else
  echo "docs-sor-maintainer not found" >&2
  exit 2
fi
```

初始化/补齐基线：

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode bootstrap --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan-bootstrap.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_apply.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan-bootstrap.json" --mode bootstrap
```

日常维护（推荐）：

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode apply-safe --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan-apply-safe.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_apply.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan-apply-safe.json" --mode apply-safe
```

证据映射生成：

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_synthesize.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan-apply-safe.json" --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-evidence-map.json"
```

## 校验命令

合并前 gate：

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --facts "$REPO_ROOT/docs/.repo-facts.json" --fail-on-drift --fail-on-freshness --output "$REPO_ROOT/docs/.doc-validate-report.json"
```

质量门槛评估（可独立运行）：

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_quality.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.doc-quality-report.json"
```

一体化 gardening（可用于定时任务）：

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_garden.py" --root "$REPO_ROOT" --apply-mode apply-safe --repair-plan-mode repair --fail-on-drift --fail-on-freshness
```

Phase D 语义迁移回归：

```bash
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_legacy_migration
python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'
```

Phase E 预验收链路：

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode audit --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --facts "$REPO_ROOT/docs/.repo-facts.json" --fail-on-drift --fail-on-freshness --output "$REPO_ROOT/docs/.doc-validate-report.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_quality.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.doc-quality-report.json"
python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'
```

Phase F（Runtime 语义 + 保守降级 + 收口治理）预验收链路：

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode audit --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan-phase-f-audit.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_garden.py" --root "$REPO_ROOT" --apply-mode apply-safe --repair-plan-mode repair --fail-on-drift --fail-on-freshness
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --facts "$REPO_ROOT/docs/.repo-facts.json" --fail-on-drift --fail-on-freshness --output "$REPO_ROOT/docs/.doc-validate-report.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_quality.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.doc-quality-report.json"
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_agents_validate
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_garden_repair_loop
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_legacy_migration
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_validate_exec_plan_closeout
python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'
```

脚本语法自检：

```bash
python3 -m py_compile "$SKILL_DIR"/scripts/*.py
```

## 失败排查顺序

1. 看 `docs/.doc-validate-report.json` 中 `errors` 与 `drift.actions`。
2. 若是结构漂移，先执行 `doc_plan + doc_apply`，再复验。
3. 若是 metadata stale，更新目标文档的 `doc-last-reviewed` 与 `doc-review-cycle-days`。
4. 若是 `manual_review` 动作，禁止直接忽略，需补证据或调整 policy/manifest。
5. 若 legacy 扫描误纳入 `README*` / `AGENTS*`，优先检查 `legacy_sources.exclude_globs` 与 denylist 配置是否生效。
6. 若语义输入缺席，应进入保守降级（`manual_review/skip`）；默认 gate 要求 `fallback_auto_migrate_count==0`。
7. 若 validate 报告出现 `denylist_migration_count>0`，视为误迁移阻断，必须先修复策略或数据，不允许放行。
8. 若 plan 出现 `semantic_rewrite`，需补充 runtime 候选或转人工审查；不得绕过 gate 直接改写 SoR 文档。
9. 若 active 计划声明 `completed`，必须同时提供 `exec-plan-closeout` marker 且目标文档可达，否则 validate 会阻断。
