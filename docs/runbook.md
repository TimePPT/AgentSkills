<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-22 -->
<!-- doc-review-cycle-days: 90 -->

# 运行手册

## 开发命令

统一变量：

```bash
REPO_ROOT="/Users/tompoet/AgentSkills"
SKILL_DIR="$REPO_ROOT/.agents/skills/docs-sor-maintainer"
PYTHON_BIN="${PYTHON_BIN:-python3}"
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
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_garden.py" --root "$REPO_ROOT" --apply-mode apply-safe --fail-on-drift --fail-on-freshness
```

Phase D 语义迁移回归：

```bash
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_legacy_migration
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
