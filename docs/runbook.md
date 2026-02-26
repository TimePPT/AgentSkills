<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-26 -->
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

PR scoped gate（可选，命中高风险会自动升级 full）：

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" \
  --root "$REPO_ROOT" \
  --facts "$REPO_ROOT/docs/.repo-facts.json" \
  --scope-files "docs/index.md,docs/runbook.md" \
  --scope-mode explicit \
  --fail-on-drift \
  --fail-on-freshness \
  --output "$REPO_ROOT/docs/.doc-validate-report-scoped.json"
```

双副本一致性检查（`skills` vs `.agents`）：

```bash
if [ -d "$REPO_ROOT/skills/docs-sor-maintainer" ] && [ -d "$REPO_ROOT/.agents/skills/docs-sor-maintainer" ]; then
  diff -qr \
    --exclude='.DS_Store' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    "$REPO_ROOT/skills/docs-sor-maintainer" \
    "$REPO_ROOT/.agents/skills/docs-sor-maintainer"
fi
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

V2.5 修复收敛（agent_strict + semantic policy 执行语义）验收链路：

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode audit --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan.json"
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_semantic_runtime
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_apply_section_actions
python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_quality.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.doc-quality-report.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --facts "$REPO_ROOT/docs/.repo-facts.json" --fail-on-drift --fail-on-freshness --output "$REPO_ROOT/docs/.doc-validate-report.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_garden.py" --root "$REPO_ROOT" --apply-mode apply-safe --repair-plan-mode repair --fail-on-drift --fail-on-freshness
```

V2.6 WP1（Topology + Progressive 契约）验收链路：

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode audit --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_apply.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan.json" --mode apply-safe
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_synthesize.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan.json" --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-evidence-map.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_quality.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.doc-quality-report.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --facts "$REPO_ROOT/docs/.repo-facts.json" --fail-on-drift --fail-on-freshness --output "$REPO_ROOT/docs/.doc-validate-report.json"
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_topology_schema
python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'
```

V2.6 WP2（Planner/Validator 能力接入）验收链路：

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode audit --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_apply.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan.json" --mode apply-safe
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_synthesize.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan.json" --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-evidence-map.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_quality.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.doc-quality-report.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --facts "$REPO_ROOT/docs/.repo-facts.json" --fail-on-drift --fail-on-freshness --output "$REPO_ROOT/docs/.doc-validate-report.json"
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_validate_topology_depth
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_quality_progressive_slots
python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'
```

V2.6 WP3（Apply 与语义输入 V2）验收链路：

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode audit --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_apply.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan.json" --mode apply-safe
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_synthesize.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan.json" --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-evidence-map.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_quality.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.doc-quality-report.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --facts "$REPO_ROOT/docs/.repo-facts.json" --fail-on-drift --fail-on-freshness --output "$REPO_ROOT/docs/.doc-validate-report.json"
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_semantic_runtime
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_apply_semantic_slots_v2
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_apply_section_actions
python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'
```

V2.6 WP4（Garden 增量优化）验收链路：

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode audit --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_apply.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan.json" --mode apply-safe
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_garden.py" --root "$REPO_ROOT" --apply-mode apply-safe --repair-plan-mode repair --fail-on-drift --fail-on-freshness
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_garden_skip_post_scan_when_no_apply
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_garden_repair_loop
python3 - <<'PY'
import json
from pathlib import Path
root = Path("/Users/tompoet/AgentSkills")
report = json.loads((root / "docs/.doc-garden-report.json").read_text(encoding="utf-8"))
steps = [str(step.get("name", "")) for step in report.get("steps", [])]
assert report.get("apply", {}).get("applied") == 0
assert "run:scan-post-apply" not in steps
assert isinstance(report.get("summary", {}).get("garden_total_duration_ms"), int)
assert isinstance(report.get("performance", {}).get("scan_duration_ms"), int)
assert isinstance(report.get("performance", {}).get("plan_duration_ms"), int)
assert isinstance(report.get("performance", {}).get("validate_duration_ms"), int)
print("WP4 acceptance checks passed")
PY
```

V2.6 WP5（文档与索引收敛）验收链路：

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode audit --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_apply.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan.json" --mode apply-safe
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_synthesize.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan.json" --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-evidence-map.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_quality.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.doc-quality-report.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --facts "$REPO_ROOT/docs/.repo-facts.json" --fail-on-drift --fail-on-freshness --output "$REPO_ROOT/docs/.doc-validate-report.json"
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_validate_exec_plan_closeout
python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'
python3 - <<'PY'
from pathlib import Path
root = Path("/Users/tompoet/AgentSkills")
artifacts = [
    "docs/exec-plans/active/docs-sor-roadmap-v2.6-acceptance-report.md",
    "docs/references/exec-plan-closeout-template.md",
    "docs/exec-plans/completed/docs-sor-roadmap-v2.6-closeout-2026-02-24.md",
]
for rel in artifacts:
    assert (root / rel).exists(), f"missing required V2.6 WP5 artifact: {rel}"
plan_text = (
    root / "docs/exec-plans/active/docs-sor-roadmap-v2.6-topology-progressive-disclosure-governance.md"
).read_text(encoding="utf-8")
assert "<!-- exec-plan-status: completed -->" in plan_text
assert (
    "<!-- exec-plan-closeout: docs/exec-plans/completed/docs-sor-roadmap-v2.6-closeout-2026-02-24.md -->"
    in plan_text
)
print("WP5 acceptance checks passed")
PY
```

V2.7 M1（策略落地：语义优先接线 + AGENTS 再生触发）验收链路：

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode audit --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan-v2.7-m1.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_apply.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan-v2.7-m1.json" --mode apply-safe
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_semantic_runtime
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_agents
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_apply_section_actions
python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --facts "$REPO_ROOT/docs/.repo-facts.json" --fail-on-drift --fail-on-freshness --output "$REPO_ROOT/docs/.doc-validate-report.json"
```

V2.7 M2（动作扩展：merge_docs + split_doc）验收链路：

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode audit --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan-v2.7-m2.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_apply.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan-v2.7-m2.json" --mode apply-safe
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_semantic_runtime
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_plan_section_actions
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_apply_section_actions
python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --facts "$REPO_ROOT/docs/.repo-facts.json" --fail-on-drift --fail-on-freshness --output "$REPO_ROOT/docs/.doc-validate-report.json"
```

V2.7 M3（门禁与观测：validate/garden 语义优先闭环）验收链路：

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode audit --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan-v2.7-m3.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_apply.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan-v2.7-m3.json" --mode apply-safe
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_synthesize.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan-v2.7-m3.json" --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-evidence-map.json"
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_apply_section_actions
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_validate_semantic_observability
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_garden_repair_loop
python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --facts "$REPO_ROOT/docs/.repo-facts.json" --fail-on-drift --fail-on-freshness --output "$REPO_ROOT/docs/.doc-validate-report.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_garden.py" --root "$REPO_ROOT" --plan-mode audit --apply-mode apply-safe --fail-on-drift --fail-on-freshness
```

V2.7 M4（验收收口：测试矩阵 + closeout）验收链路：

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode audit --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan-v2.7-m4.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_apply.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan-v2.7-m4.json" --mode apply-safe
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_synthesize.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan-v2.7-m4.json" --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-evidence-map.json"
python3 -m unittest -v \
  skills.docs-sor-maintainer.tests.test_doc_semantic_runtime \
  skills.docs-sor-maintainer.tests.test_doc_plan_section_actions \
  skills.docs-sor-maintainer.tests.test_doc_apply_section_actions \
  skills.docs-sor-maintainer.tests.test_doc_validate_semantic_observability \
  skills.docs-sor-maintainer.tests.test_doc_garden_repair_loop \
  skills.docs-sor-maintainer.tests.test_doc_validate_exec_plan_closeout
python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --facts "$REPO_ROOT/docs/.repo-facts.json" --fail-on-drift --fail-on-freshness --output "$REPO_ROOT/docs/.doc-validate-report.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_garden.py" --root "$REPO_ROOT" --plan-mode audit --apply-mode apply-safe --fail-on-drift --fail-on-freshness
```

V2.7.3（Semantic Input Quality Grading + Scoped Validate）验收链路：

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode audit --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan-v2.7.3.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_apply.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan-v2.7.3.json" --mode apply-safe
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --facts "$REPO_ROOT/docs/.repo-facts.json" --scope-files "docs/index.md,docs/runbook.md" --scope-mode explicit --fail-on-drift --fail-on-freshness --output "$REPO_ROOT/docs/.doc-validate-report-scoped.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --facts "$REPO_ROOT/docs/.repo-facts.json" --fail-on-drift --fail-on-freshness --output "$REPO_ROOT/docs/.doc-validate-report.json"
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
