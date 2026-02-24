<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-24 -->
<!-- doc-review-cycle-days: 90 -->
<!-- exec-plan-status: completed -->
<!-- exec-plan-closeout: docs/exec-plans/completed/docs-sor-roadmap-v2.5-remediation-closeout-2026-02-24.md -->

# Docs SoR Roadmap V2.5 修复计划（agent_strict 与语义策略落地）

## 状态变更（2026-02-24）

本计划已完成并通过验收，收口文档：
`docs/exec-plans/completed/docs-sor-roadmap-v2.5-remediation-closeout-2026-02-24.md`。

## 1. 背景

基于 `bba1f2f` 基线审阅，V2.5 存在 3 个阻断级问题：

1. `agent_strict` 模式未实现“无 runtime/门禁失败即失败”。
2. `semantic_generation` 的 `fail_closed`、`allow_fallback_template`、`deny_paths` 为死配置。
3. 文档收口结论与代码事实不一致，存在语义漂移（文档腐败）。

本计划目标是：在不破坏既有 deterministic 路径的前提下，完成以上 3 项修复，并给出可复验的测试和验收证据。

## 2. 范围与非目标

范围：

1. `skills/docs-sor-maintainer/scripts/doc_apply.py`
2. `skills/docs-sor-maintainer/scripts/doc_semantic_runtime.py`
3. `skills/docs-sor-maintainer/tests/` 下相关用例
4. `docs/` 下执行计划、收口文档、运行手册与索引

非目标：

1. 不引入外部 LLM API 依赖。
2. 不改动与本次问题无关的 legacy 迁移判定算法。

## 3. 修复策略（按 issue 顺序执行）

## 3.1 Issue-1：`agent_strict` 强约束生效

修复要求：

1. 当 `semantic_generation.mode=agent_strict` 且动作启用语义通道时：
   - runtime 候选缺失 -> action `error`
   - runtime gate 失败 -> action `error`
2. 适用动作至少覆盖：
   - `update_section`
   - `fill_claim`
   - `semantic_rewrite`
   - `agents_generate`

验收标准：

1. 新增单测覆盖“runtime 缺失/门禁失败 -> error”。
2. `hybrid` 与 `deterministic` 行为不回归。

## 3.2 Issue-2：语义策略字段从“可配”变“可执行”

修复要求：

1. `deny_paths`：命中路径禁止消费 runtime 语义候选。
2. `allow_fallback_template`：控制 runtime 失败后是否允许模板兜底。
3. `fail_closed`：当 fallback 不允许时，策略应转为阻断或人工审查语义，不得静默继续。

执行语义：

1. `agent_strict`：始终不允许 fallback（强失败）。
2. `hybrid`：
   - `allow_fallback_template=true` -> 允许模板兜底
   - `allow_fallback_template=false` 且 `fail_closed=true` -> 阻断自动写入
3. `deterministic`：不进入 runtime 语义通道。

验收标准：

1. 新增单测覆盖 `deny_paths` 与 fallback 开关分支。
2. `doc_apply` 报告中可追踪策略命中结果（例如 `path_denied`、`runtime_required`、`fallback_blocked`）。

## 3.3 Issue-3：文档语义漂移修复与收口

修复要求：

1. 产出本修复计划的 closeout 文档并在 active 计划中建立 `exec-plan-closeout` 链接。
2. 在 closeout 中明确修复前事实、修复动作、验收证据，不得继续使用“未满足时已满足”的表述。
3. 同步更新 `docs/index.md`、`docs/runbook.md`，确保后续开发和验收可复现。

验收标准：

1. `doc_validate --fail-on-drift --fail-on-freshness` 通过。
2. `exec_plan_closeout` 指标无缺失链接或目标丢失。

## 4. 开发与测试计划

## 4.1 开发步骤

1. 增加语义策略辅助函数（strict/fallback/deny-path 判定）。
2. 在 `doc_apply` 的各语义动作分支接入策略判定并统一错误语义。
3. 调整 `agents_generate` 的 runtime 优先与 strict 失败路径。
4. 补齐单元测试并执行全量回归。

## 4.2 测试矩阵

1. 单测：
   - `test_doc_semantic_runtime.py`
   - `test_doc_apply_section_actions.py`
   - `test_doc_garden_repair_loop.py`（回归）
2. 全量回归：
   - `python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'`
3. 门禁：
   - `repo_scan -> doc_plan(audit) -> doc_validate --fail-on-drift --fail-on-freshness`
   - `doc_quality.py`
   - `doc_garden.py --apply-mode apply-safe --repair-plan-mode repair --fail-on-drift --fail-on-freshness`

## 5. 交付与验收定义（DoD）

全部满足才视为验收成功：

1. 3 个 issue 均有代码与测试证据闭环。
2. 全量测试通过且无回归失败。
3. 文档链路（plan -> closeout -> index/runbook）完整且可追溯。
4. `doc_validate`、`doc_quality`、`doc_garden` 门禁通过。
