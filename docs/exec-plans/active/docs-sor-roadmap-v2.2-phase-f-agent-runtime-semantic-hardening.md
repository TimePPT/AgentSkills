<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-22 -->
<!-- doc-review-cycle-days: 90 -->
<!-- exec-plan-status: completed -->
<!-- exec-plan-closeout: docs/exec-plans/completed/docs-sor-roadmap-v2.2-phase-f-closeout-2026-02-22.md -->

# Phase F 实施方案：Agent Runtime 语义接入、保守降级与文档收口治理

## 1. 背景与目标

本文档是对 `codex://threads/019c83d8-0ad7-7563-a8f9-ee1dd8ae1241` 中 3 个 issue 的系统化收敛方案，目标是：

1. 保持 `docs/` 作为 SoR，不破坏既有 scan/plan/apply/validate 主链路。
2. 让语义判断能力符合 Skill 产品定位：语义能力由 Agent Runtime 提供，skill 负责契约、围栏、执行与校验。
3. 当语义能力缺席时降级到保守 pattern 流程，确保零误伤优先（尤其 `README.md` / `AGENTS.md`）。
4. 修复执行证据长期沉积在 `active` 的追溯性问题，建立 `active -> completed` 收口闭环。

## 2. 输入与证据锚点

需求与约束来源：

- 审阅 issue 线程：`codex://threads/019c83d8-0ad7-7563-a8f9-ee1dd8ae1241`
- 主需求文档：`docs/exec-plans/active/docs-sor-roadmap-v2.md`
- V2.1 语义需求：`docs/exec-plans/active/docs-sor-roadmap-v2.1-semantic-structured-generation.md`
- 运行手册：`docs/runbook.md`

Codebase As-Is 关键锚点：

- `doc_garden` repair 循环未切换独立 repair plan mode：`skills/docs-sor-maintainer/scripts/doc_garden.py`
- 语义 provider 当前仅 `deterministic_mock`：`skills/docs-sor-maintainer/scripts/doc_legacy.py`
- 语义围栏与 gate 统计已存在：`skills/docs-sor-maintainer/scripts/doc_plan.py`、`skills/docs-sor-maintainer/scripts/doc_validate.py`、`skills/docs-sor-maintainer/scripts/doc_quality.py`
- `docs/exec-plans/completed/` 为空，缺少收口文档

## 3. 三个 Issue 的根因分析

## 3.1 Issue-1（P2）：R7 要求 repair mode 重跑 plan，但实现未显式区分

现象：

- `doc_garden` 中 `run_cycle` 对 `doc_plan.py --mode` 始终使用 `args.plan_mode`，repair 轮未切换。

根因：

- 现有循环只实现了“重试次数与可修复动作”控制，没有实现“计划模式切换语义”。

影响：

- 行为层面可重试，但与 R7 文本契约不一致；报告无法清晰区分首轮与 repair 轮的规划策略。

## 3.2 Issue-2（P2）：语义 provider 仍是脚本内 mock，不匹配 Skill 产品定位

现象：

- policy 中语义 `engine` 为 `llm`，但 `doc_legacy.py` provider 映射仅 `deterministic_mock`。

根因：

- V2.1 Phase A 先行实现了 provider 抽象层，但没有把语义来源收敛为“Agent Runtime 注入契约”。

影响：

- 语义能力声明与实现载体不一致；后续切换真实 runtime 语义源时，边界与责任不清晰。

## 3.3 Issue-3（P3）：验收证据未沉淀到 completed，追溯性薄弱

现象：

- 阶段报告与验收证据主要在 `docs/exec-plans/active/`，`completed/` 目录为空。

根因：

- 文档生命周期缺少显式收口规则与 gate。

影响：

- active 文档长期膨胀；审计和回溯需要跨文档人工拼接，成本高且易遗漏。

## 4. To-Be 技术路径（从本源出发）

核心原则：

1. Skill 只做治理与执行，不内置具体厂商 API 调用。
2. 文档迁移优先“零误伤”，再追求召回率。
3. 语义缺席时可运行，但默认保守，不自动迁移高风险文档。

目标分层：

1. 硬围栏层（Hard Fence）
- `include_globs/exclude_globs` + denylist 全程先行；命中即 `skip`。

2. 语义输入层（Semantic Input Contract）
- 由 Agent Runtime 产出 `docs/.legacy-semantic-report.json`。
- `doc_plan` 消费该报告分流，不在 skill 内调用具体 LLM API。

3. 保守降级层（Conservative Fallback）
- 若语义报告缺席或不可用，进入 fallback：仅 `manual_review/skip`；默认不自动迁移。

4. 门禁层（Gate）
- 继续由 `doc_validate/doc_quality` 统一阻断：冲突、低置信自动迁移、结构化完整度、source marker。

## 5. 改造方案（按 Issue 拆解）

## 5.1 Issue-1 改造：Repair Mode 显式化

改造范围：

- `skills/docs-sor-maintainer/scripts/doc_plan.py`
- `skills/docs-sor-maintainer/scripts/doc_garden.py`
- `skills/docs-sor-maintainer/scripts/doc_apply.py`
- `skills/docs-sor-maintainer/tests/test_doc_garden_repair_loop.py`

设计：

1. `doc_plan` 新增 `repair` 模式。
2. `doc_garden` 新增 `repair_plan_mode`（CLI + policy），首轮使用 `plan_mode`，repair 轮强制使用 `repair_plan_mode`。
3. `doc_apply` 放行 `plan.meta.mode=repair`。
4. `doc_garden` 报告按轮记录实际 `plan_mode`。

伪代码：

```python
ok = run_cycle(label="run", plan_mode=initial_plan_mode)

while should_repair(ok, validate_report, attempts, max_iterations):
    attempts += 1
    ok = run_cycle(label=f"repair-{attempts}", plan_mode=repair_plan_mode)
```

兼容性：

- 未设置 `repair_plan_mode` 时默认回退到 `audit`，保持保守行为。

## 5.2 Issue-2 改造：语义能力改为 Agent Runtime 注入

改造范围：

- `skills/docs-sor-maintainer/scripts/doc_legacy.py`
- `skills/docs-sor-maintainer/scripts/doc_plan.py`
- `skills/docs-sor-maintainer/scripts/doc_validate.py`
- `skills/docs-sor-maintainer/scripts/doc_quality.py`
- `skills/docs-sor-maintainer/tests/test_doc_legacy_migration.py`

设计：

1. 引入 `provider=agent_runtime`（默认生产路径），表示语义由 runtime 外部注入。
2. skill 通过统一契约读取 `docs/.legacy-semantic-report.json`，对每个 candidate 进行 join。
3. 语义缺席时走 fallback：
- `allow_fallback_auto_migrate=false`（默认）时，仅 `manual_review/skip`。
- 仅显式 `mapping_table` 命中时允许自动迁移。
4. 保留 `deterministic_mock` 仅用于测试与本地演练，不作为产品主路径。

语义报告最小契约（建议）：

```json
{
  "version": 1,
  "entries": [
    {
      "source_path": "legacy/plan.md",
      "category": "plan",
      "confidence": 0.92,
      "decision": "auto_migrate",
      "rationale": "...",
      "provider": "agent_runtime",
      "model": "runtime-model-id"
    }
  ]
}
```

降级伪代码：

```python
if hit_hard_denylist(source_rel):
    return skip

semantic_record = semantic_report.get(source_rel)
if semantic_record:
    return semantic_record.decision

if runtime_semantic_unavailable:
    if allow_fallback_auto_migrate is False:
        return manual_review_or_skip(source_rel)
    return conservative_pattern_decision(source_rel)

return manual_review
```

## 5.3 Issue-3 改造：建立 active/completed 收口治理

改造范围：

- `docs/exec-plans/completed/`（新增收口文档）
- `docs/index.md`（新增 completed 导航）
- `skills/docs-sor-maintainer/scripts/doc_validate.py`（新增收口一致性检查）
- `skills/docs-sor-maintainer/tests/`（新增收口 gate 测试）

设计：

1. 对已完成计划，要求存在 completed 收口文档。
2. active 文档需给出收口链接（或 metadata 标记）。
3. `doc_validate` 增加 gate：
- 标记 completed 但缺收口链接 -> error
- 收口链接不存在 -> error

伪代码：

```python
for plan in active_exec_plans:
    if plan.status == "completed":
        if not plan.closeout_link:
            errors.append("missing closeout link")
        elif not exists(closeout_link):
            errors.append("closeout file missing")
```

## 6. 实施分期与里程碑

## 6.1 F1（0.5-1 人日）契约与文档基线

- 更新 policy/manifest/index/runbook。
- 新增本方案文档与 completed 收口基线。

DoD：

- 文档索引可达，`docs/exec-plans/completed` 不再为空。

## 6.2 F2（1-1.5 人日）Repair Mode 与运行报告

- `doc_plan` 增加 repair mode。
- `doc_garden` 增加 repair_plan_mode 并落盘到报告。

DoD：

- 可证明 repair 轮与首轮计划模式不同，且有界终止保持不变。

## 6.3 F3（1.5-2 人日）Runtime 语义注入与保守降级

- 增加 `agent_runtime` 语义输入路径。
- 完成语义缺席 fallback 与 denylist 强化。

DoD：

- LLM 缺席时流程可运行且默认不误迁移。

## 6.4 F4（1 人日）门禁与回归收敛

- 完成新增单测、集成链路测试与预验收报告。

DoD：

- 全量测试通过，validate/quality gate 通过。

## 7. 测试与验证设计

## 7.1 单元测试新增项

- `test_doc_plan_repair_mode_filters_actions`
- `test_doc_garden_repair_loop_switches_to_repair_mode`
- `test_legacy_semantic_agent_runtime_report_consumption`
- `test_legacy_semantic_fallback_no_auto_migrate`
- `test_validate_blocks_denylist_migration`
- `test_validate_requires_exec_plan_closeout`

## 7.2 集成测试场景

1. runtime 语义可用：`auto_migrate/manual_review/skip` 分流正确。
2. runtime 语义缺席：仅 `manual_review/skip`，不产生误迁移。
3. denylist（`README*`、`AGENTS*`）命中：永远不进入迁移动作。
4. repair loop：达到上限后 fail-closed 并输出阻塞项。

## 7.3 预验收命令链

```bash
REPO_ROOT="/Users/tompoet/AgentSkills"
SKILL_DIR="$REPO_ROOT/.agents/skills/docs-sor-maintainer"
PYTHON_BIN="${PYTHON_BIN:-python3}"

"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode audit --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --facts "$REPO_ROOT/docs/.repo-facts.json" --fail-on-drift --fail-on-freshness --output "$REPO_ROOT/docs/.doc-validate-report.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_quality.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.doc-quality-report.json"
python3 -m unittest discover -s "$REPO_ROOT/skills/docs-sor-maintainer/tests" -p 'test_*.py'
```

## 8. 验收 Checklist（发布前必须全部满足）

- [x] repair 轮使用独立 `repair_plan_mode`，并在 report 中可追溯。
- [x] `provider=agent_runtime` 可消费语义报告，不依赖 skill 内部厂商 API 调用。
- [x] 语义缺席降级后，默认 `fallback_auto_migrate_count=0`。
- [x] `README*` / `AGENTS*` 命中 denylist 时不进入迁移动作。
- [x] active/completed 收口规则通过 validate gate。
- [x] `doc_validate --fail-on-drift --fail-on-freshness` 通过。
- [x] 全量 `test_*.py` 通过。

## 9. 风险与回退策略

风险：

1. 语义报告输入不稳定，导致 manual_review 激增。
2. 降级过保守，迁移效率下降。
3. 新 gate 引入误阻断。

回退：

1. 保持 fail-closed，不放开自动迁移。
2. 通过 policy 调整阈值与 include 范围，但不放宽 denylist。
3. 逐步放量：先 audit 观察，再 apply-with-archive。

## 10. 交付物清单

1. 本方案文档（Phase F）。
2. completed 收口基线文档。
3. runbook 中新增 Phase F 预验收与排障指引。
4. 后续代码改造 PR（按 F2/F3/F4 分批）。

## 11. Phase F1（F2）执行记录（2026-02-22）

- 代码改造：
  - `doc_plan` 新增 `repair` mode，并在该模式下仅保留 `update_section/fill_claim/refresh_evidence/quality_repair` 动作。
  - `doc_garden` 新增 `repair_plan_mode`（policy + CLI），repair 轮与首轮可独立指定 mode，并在 report 中输出 `initial_plan_mode/repair_plan_mode/cycles`。
  - `doc_apply` 放行 `plan.meta.mode=repair`。
- 测试与门禁：
  - 新增并通过：`test_doc_plan_repair_mode_filters_actions`、`test_doc_garden_repair_loop_switches_to_repair_mode`、`test_main_accepts_repair_plan_mode`。
  - `python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'` 通过（32/32）。
  - `doc_validate --fail-on-drift --fail-on-freshness` 通过（errors=0, warnings=0, drift=0）。
  - `doc_quality` gate 通过（coverage=1.00, conflicts=0）。

## 12. Phase F2（F3）执行记录（2026-02-22）

- 代码改造：
  - `doc_legacy` 新增 `provider=agent_runtime` 语义报告消费路径，按 `source_path` 与 candidate join。
  - 新增 `allow_fallback_auto_migrate`（默认 `false`），runtime 语义缺席时默认仅 `manual_review/skip`。
  - fallback 路径新增 `fallback_auto_migrate` 标记；`doc_plan/doc_quality/doc_validate` 全链路输出 `fallback_auto_migrate_count`。
  - `doc_validate` 新增 denylist 迁移动作阻断与指标（`denylist_migration_count`）。
- 测试补齐：
  - 新增并通过：`test_legacy_semantic_agent_runtime_report_consumption`。
  - 新增并通过：`test_legacy_semantic_fallback_no_auto_migrate`。
  - 新增并通过：`test_validate_blocks_denylist_migration`。
- 门禁与验收：
  - `python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'` 通过（35/35）。
  - `repo_scan -> doc_plan(audit) -> doc_validate(--fail-on-drift --fail-on-freshness) -> doc_quality` 通过。
  - 关键指标：`fallback_auto_migrate_count=0`、`denylist_migration_count=0`、`errors=0`、`drift=0`。

## 13. Phase F3（F4）执行记录（2026-02-22）

- 代码改造：
  - `doc_legacy` 完成 runtime 集成鲁棒性收敛：支持 runtime 报告缺字段、部分候选缺席与 `mapping_table` 受控 fallback auto 场景。
  - `doc_quality`/`doc_validate` 增加 `max_fallback_auto_migrate` 语义门禁阈值，默认 0，形成发布前必过断言。
  - `doc_validate` 新增 `exec-plan closeout` 检查：active 计划声明 `completed` 时必须给出可达的 completed 收口文档。
- 测试补齐：
  - 新增并通过：`test_legacy_semantic_agent_runtime_missing_fields`。
  - 新增并通过：`test_legacy_semantic_partial_runtime_report_uses_fallback_without_auto`。
  - 新增并通过：`test_legacy_semantic_mapping_table_allows_controlled_fallback_auto`。
  - 新增并通过：`test_validate_blocks_fallback_auto_migrate_when_threshold_zero`。
  - 新增并通过：`test_semantic_gate_fails_when_fallback_auto_migrate_exceeds_threshold`。
  - 新增并通过：`test_doc_validate_exec_plan_closeout.py`（3 个场景）。
- 收口文档：
  - `docs/exec-plans/completed/docs-sor-roadmap-v2.2-phase-f-closeout-2026-02-22.md`。
