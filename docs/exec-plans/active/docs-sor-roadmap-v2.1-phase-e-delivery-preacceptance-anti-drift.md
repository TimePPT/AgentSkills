<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-22 -->
<!-- doc-review-cycle-days: 90 -->
<!-- exec-plan-status: completed -->
<!-- exec-plan-closeout: docs/exec-plans/completed/docs-sor-roadmap-v2.1-phase-e-closeout-2026-02-22.md -->

# Phase E 实施方案：开发落地、测试预验收与反漂移反腐败

## 1. 目标与完成定义

Phase E 的唯一目标是把 V2.1（Phase A-D）能力转化为可持续交付机制，确保开发、预验收与文档治理形成闭环，而非一次性通过。

完成定义（全部满足才可出阶段）：

1. 开发侧：语义迁移与质量 gate 能在主流程稳定执行，且不依赖人工补丁。
2. 测试侧：存在可复用的预验收矩阵、演练脚本与证据清单，能够在发布前一轮跑通。
3. 治理侧：`docs/` 作为 SoR 的结构、索引、policy、manifest 同步一致，`doc_validate` 零漂移。
4. 运维侧：`doc_garden` 可按策略收敛常见漂移，超过上限时明确 fail-closed 并产出阻塞项。

## 2. 输入基线与边界

- 输入基线：
  - `docs/exec-plans/active/docs-sor-roadmap-v2.1-semantic-structured-generation.md`
  - `docs/exec-plans/active/docs-sor-roadmap-v2.1-phase-d-test-matrix.md`
  - `docs/exec-plans/active/docs-sor-roadmap-v2.1-phase-d-acceptance-report.md`
- 当前阶段边界：
  - 不新增“全仓库无限制语义扫描”能力。
  - 不放宽 denylist 与 fail-closed 规则。
  - 不用临时人工操作替代正式门禁。

## 3. 开发工作包（Work Packages）

| 工作包 | 目标 | 关键任务 | 输出物 | DoD |
| --- | --- | --- | --- | --- |
| E1 契约收敛 | 固定 SoR 契约，防止文档与实现分叉 | 对齐 `policy/manifest/index`；确认必需文档入口 | 更新后的 policy/manifest/index 与审计报告 | `doc_plan --mode audit` 无 `sync_manifest` 遗留动作 |
| E2 预验收编排 | 把分散检查变成单次可执行流程 | 固化“scan -> plan -> validate -> quality -> unittest”顺序；输出标准报告路径 | 预验收命令集与报告清单 | 同一仓库可重复执行，结果可追溯 |
| E3 Gate 加固 | 将语义质量门禁并入发布前阻断链路 | 明确冲突、低置信、结构化完整度阈值及失败语义 | gate 阈值基线与失败判定表 | 任一阈值越界必然非零退出 |
| E4 漂移修复闭环 | 让轻微漂移自动修复、不可修复项显式升级 | 启用 `doc_garden` 有界 repair；沉淀失败分类与升级标准 | garden 报告与阻塞项模板 | 达上限后停止重试并输出阻塞证据 |
| E5 发布前预验收 | 提供可审计的“准入/拒绝”结论 | 执行矩阵、记录实际结果、形成 PASS/FAIL 结论 | Phase E 预验收报告 | 报告包含命令、结果、偏差与后续动作 |

## 4. 开发实施顺序

1. 先收敛契约：先改 `policy/manifest/index`，再改执行逻辑，避免“先实现后补文档”。
2. 再固化入口：统一 runbook 命令与 CI 调用参数，避免本地与 CI 双口径。
3. 最后跑预验收：以同一份矩阵执行，禁止用临时命令替代标准链路。

## 5. 测试预验收设计

## 5.1 预验收入口条件（Go/No-Go）

1. `docs/.doc-policy.json` 的 `doc_quality_gates` 与 `legacy_sources.semantic` 已落盘且生效。
2. `docs/.doc-manifest.json` 包含 Phase E 所需文档入口（至少索引可达）。
3. `python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'` 在基线分支可执行。
4. `doc_validate --fail-on-drift --fail-on-freshness` 在未改动状态下为 `errors=0`。

## 5.2 预验收矩阵

| 用例 ID | 场景 | 检查入口 | 通过标准 |
| --- | --- | --- | --- |
| E-01 | SoR 契约一致性 | `repo_scan + doc_plan(audit)` | `sync_manifest=0` 且无新增 manual_review 噪声 |
| E-02 | 文档漂移门禁 | `doc_validate --fail-on-drift` | 漂移相关 errors 为 0 |
| E-03 | 文档新鲜度门禁 | `doc_validate --fail-on-freshness` | freshness errors 为 0 |
| E-04 | 语义冲突门禁 | `doc_validate` + semantic 指标 | `semantic_conflict_count` 不超过 policy 阈值 |
| E-05 | 低置信自动迁移拦截 | migration + validate | `semantic_low_confidence_auto_count=0` |
| E-06 | 结构化完整度 | validate/quality 报告 | `structured_section_completeness >= 0.95` |
| E-07 | denylist 防误迁移 | legacy migration 测试 | denylist 来源不进入 `migrate_legacy` |
| E-08 | 迁移幂等 | 同一输入执行两次 migrate | 第二次无重复结构块与重复归档 |
| E-09 | repair 有界性 | `doc_garden` 故障样例 | 达上限后停止并输出阻塞项 |
| E-10 | 全量回归 | `unittest discover` | 全绿通过 |

## 5.3 预验收标准命令

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

## 6. 反漂移反腐败机制（必须长期执行）

1. 契约先行：所有行为变更必须先更新 `docs/.doc-policy.json` 与 `docs/.doc-manifest.json`，再进入实现。
2. 单一入口：开发与 CI 均使用 runbook 标准命令，禁止手写变体绕过 gate。
3. 失败即阻断：`fail_on_quality_gate=true` 与 `fail_on_semantic_gate=true` 保持开启，不允许“先合并后修”。
4. 证据闭环：每次预验收必须保留 `doc-plan/doc-validate/doc-quality` 报告，无法追溯即视为未验收。
5. 有界自愈：`doc_garden.max_repair_iterations` 保持有界，禁止无界重跑掩盖根因。
6. 文档分层：`AGENTS.md` 只保留控制面导航，细节集中在 `docs/`，避免知识重复与腐败扩散。
7. 定期复核：按文档 metadata 周期复核，逾期即触发 freshness gate。

## 7. 里程碑与时序建议

| 里程碑 | 时长 | 交付 |
| --- | --- | --- |
| M1 契约收敛 | 0.5-1 人日 | policy/manifest/index 对齐，零结构漂移 |
| M2 预验收编排 | 1 人日 | 标准命令链路与报告口径固定 |
| M3 门禁加固 | 1 人日 | semantic/quality gate 失败语义稳定 |
| M4 预验收执行 | 0.5-1 人日 | Phase E 预验收报告（PASS/FAIL） |

总工作量：约 3-4 人日。

## 8. 风险与回退策略

- 风险：新增规则导致误阻断。
  - 回退：保留阈值可配置，但不得关闭 fail-closed；通过小步调参恢复。
- 风险：报告过多导致不可读。
  - 回退：保留关键指标摘要，详细项进入 JSON 报告。
- 风险：本地与 CI 结果不一致。
  - 回退：统一使用 runbook 命令与同一 policy 文件，禁止环境特化参数。

## 9. 退出条件（Phase E PASS）

1. 预验收矩阵 E-01 至 E-10 全部通过。
2. `doc_validate` 与 `doc_quality` 报告均满足 policy 门槛。
3. 形成 Phase E 预验收报告并附阻塞项清零确认。
4. 连续两轮执行结果一致（验证稳定性与幂等）。
