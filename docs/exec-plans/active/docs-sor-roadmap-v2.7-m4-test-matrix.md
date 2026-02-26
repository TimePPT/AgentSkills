<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-26 -->
<!-- doc-review-cycle-days: 90 -->

# V2.7 M4 测试矩阵与验收清单（2026-02-26）

## 范围

- 来源计划：`docs/exec-plans/active/docs-sor-roadmap-v2.7-agent-first-semantic-priority-governance.md`
- 目标阶段：`M4（验收收口）`
- 关注场景：语义优先策略回归、merge/split 通道稳定性、可观测性门禁、closeout 规则、端到端 gate

## 自动化矩阵

| 用例 ID | 场景 | 自动化入口 | 关键断言 |
| --- | --- | --- | --- |
| M4-01 | 语义策略与 runtime 决策回归 | `test_doc_semantic_runtime` | `prefer_agent_semantic_first/require_semantic_attempt` 默认值与 gate 语义稳定 |
| M4-02 | Planner 显式语义动作输出 | `test_doc_plan_section_actions` | `semantic_rewrite/merge_docs/split_doc` 具备 `reason + evidence` |
| M4-03 | Apply 语义优先与 fallback 行为 | `test_doc_apply_section_actions` | runtime 优先、`agent_strict` 禁止 fallback、fallback reason code 标准化 |
| M4-04 | Validate 语义可观测门禁 | `test_doc_validate_semantic_observability` | 大量未尝试语义动作触发 gate 失败或告警 |
| M4-05 | Garden 语义观测指标输出 | `test_doc_garden_repair_loop` | 报告含 `semantic_observability` 与 hit rate 摘要 |
| M4-06 | Completed 计划 closeout 合规 | `test_doc_validate_exec_plan_closeout` | `exec-plan-status: completed` 必须具备且可达 `exec-plan-closeout` |
| M4-07 | 仓库端到端验收链路 | `repo_scan -> doc_plan -> doc_apply -> doc_synthesize -> doc_validate -> doc_garden` | `action_count=0`、`errors=0`、`warnings=0`、`drift=0`、`status=passed` |

## 运行命令

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

## 回归通过标准

1. 聚焦专项测试通过（43/43）。
2. 全量测试通过（`93/93`）。
3. `doc_validate --fail-on-drift --fail-on-freshness` 通过，且 `errors=0 warnings=0 drift=0`。
4. `doc_garden` 通过，且 `status=passed`。
5. active 计划 `completed + closeout` 规则在 validate 校验中通过。
