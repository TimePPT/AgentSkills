<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-26 -->
<!-- doc-review-cycle-days: 90 -->
<!-- exec-plan-status: completed -->
<!-- exec-plan-closeout: docs/exec-plans/completed/docs-sor-roadmap-v2.7-closeout-2026-02-26.md -->

# Docs SoR Roadmap V2.7 需求与实施方案（Agent 优先语义生成）

## 状态变更（2026-02-26）

本计划已完成并通过验收，收口文档：
`docs/exec-plans/completed/docs-sor-roadmap-v2.7-closeout-2026-02-26.md`。

## 1. 背景与问题定义

现状中，`Docs SoR Maintainer` 在不少场景仍以规则模板为主路径，语义能力依赖 runtime 工件命中与触发条件，导致：

1. 已有 `AGENTS.md` 与既有需求文档难以被“默认语义重组”。
2. 语义入口未命中时容易静默回退，缺少“先尝试语义”的硬约束。
3. 文档迁移、合并、拆分等结构性动作，尚未形成统一的语义优先执行口径。

V2.7 的定位是将策略从“模板兜底为主，语义可选”升级为“语义优先，规则兜底”。

## 2. 目标

1. 让 skill 在文档生成、更新、迁移、合并、拆分与结构重组场景中，默认优先尝试 Agent 语义分析与生成。
2. 仅在语义不可用、语义门禁失败或策略明确禁止时，才回退到规则模板。
3. 保持 SoR 可审计、可追溯、可回滚，避免语义路径引入不可控漂移。

## 3. 范围与非目标

### 3.1 范围

1. `doc_plan.py` 的动作规划与触发策略。
2. `doc_apply.py` 对 `AGENTS.md` 与 managed docs 的语义优先执行路径。
3. `doc_semantic_runtime.py` 的 runtime 可用性判定、动作匹配与失败语义。
4. `docs/.doc-policy.json` 的语义策略默认值与 fallback 策略。
5. 文档结构动作：`migrate_legacy`、`update_section`、`semantic_rewrite`，新增/扩展 `merge_docs`、`split_doc` 语义动作契约。

### 3.2 非目标

1. 不将外部 LLM API 设为强依赖。
2. 不取消 deterministic 规则路径；规则路径仅作为 fallback。
3. 不在 V2.7 内重做全部历史文档内容，仅覆盖策略与执行机制。

## 4. 核心需求（R14-R19）

## R14：语义优先默认策略（全动作域）

1. 对以下动作默认先走语义通道：
   - `agents_generate`
   - `update_section`
   - `fill_claim`
   - `semantic_rewrite`
   - `migrate_legacy`
   - `merge_docs`（新增）
   - `split_doc`（新增）
2. 语义尝试必须在执行报告中留痕：`attempted=true/false`、失败原因、fallback 决策。

## R15：AGENTS.md 语义重生触发前置

1. 即使 `AGENTS.md` 已存在，只要本轮存在文档结构变更或语义候选命中，必须评估 `agents_generate` 语义更新。
2. `agents_generation.mode` 不得再是“仅配置不生效”，需参与执行分支。
3. `AGENTS.md` 语义候选命中优先级高于模板渲染。

## R16：语义失败后的规则兜底

1. fallback 仅在下列条件同时满足时允许：
   - `allow_fallback_template=true`
   - 非 `agent_strict`
   - 失败类型属于可回退类型（如 runtime 缺失、候选缺失、门禁失败）
2. fallback 必须记录标准化原因码：
   - `runtime_unavailable`
   - `runtime_entry_not_found`
   - `runtime_gate_failed`
   - `path_denied`
3. `agent_strict` 下禁止 fallback，必须返回 `error`。

## R17：语义驱动文档结构操作

1. 新增 `merge_docs` 动作契约：
   - 输入：源文档集合、目标文档、证据映射。
   - 输出：结构化合并结果（保留来源追踪）。
2. 新增 `split_doc` 动作契约：
   - 输入：源文档、拆分规则、目标路径映射。
   - 输出：分拆后的目标文档与索引链接补丁。
3. `migrate_legacy` 在语义可用时优先生成结构化摘要与迁移映射，而非模板占位。

## R18：Plan 阶段语义动作显式化

1. `doc_plan` 必须显式产出语义相关动作，禁止仅依赖“manifest_changed”间接触发。
2. 对已有文档的重组场景，至少产出一种动作：
   - `agents_generate`
   - `semantic_rewrite`
   - `merge_docs`
   - `split_doc`
3. 每个语义动作需附带 `reason + evidence`，满足 SoR 审计要求。

## R19：可观测性与门禁

1. `doc_apply` 报告新增指标：
   - `semantic_attempt_count`
   - `semantic_success_count`
   - `fallback_count`
   - `fallback_reason_breakdown`
2. `doc_validate` 增加语义优先策略检查：
   - 当策略为语义优先时，若大量动作未尝试语义且无豁免原因，应告警或失败。
3. `doc_garden` 报告输出“语义路径命中率”，作为后续优化基线。

## 5. 策略与配置变更（建议）

`docs/.doc-policy.json` 在 `semantic_generation` 与 `agents_generation` 增加/强化如下语义：

```json
{
  "semantic_generation": {
    "enabled": true,
    "mode": "hybrid",
    "prefer_agent_semantic_first": true,
    "require_semantic_attempt": true,
    "allow_fallback_template": true,
    "actions": {
      "agents_generate": true,
      "update_section": true,
      "fill_claim": true,
      "semantic_rewrite": true,
      "migrate_legacy": true,
      "merge_docs": true,
      "split_doc": true
    }
  },
  "agents_generation": {
    "enabled": true,
    "mode": "dynamic",
    "regenerate_on_semantic_actions": true,
    "sync_on_manifest_change": true
  }
}
```

说明：`prefer_agent_semantic_first=true` 与 `require_semantic_attempt=true` 是 V2.7 的策略核心。

## 6. 执行流程（目标态）

1. `repo_scan`：采集事实。
2. `doc_plan`：显式产出语义动作（含 `agents_generate/merge_docs/split_doc`）。
3. `doc_apply`：先尝试语义候选；失败后按策略判定是否 fallback。
4. `doc_validate`：校验结构、漂移、语义策略执行痕迹。
5. `doc_garden`：输出语义命中率与 fallback 统计。

## 7. 验收标准（DoD）

1. 已有 `AGENTS.md` 的仓库，在存在语义候选时可被更新，且优先语义内容。
2. 在无 runtime 报告场景，`hybrid` 模式可按策略 fallback，`agent_strict` 必须失败。
3. 至少一条 `merge_docs` 与一条 `split_doc` 用例可通过端到端测试。
4. 报告中可追溯每个语义动作的尝试、命中、失败与 fallback 原因。
5. `doc_validate --fail-on-drift --fail-on-freshness` 可通过，且不引入新增门禁回归。

## 8. 里程碑

1. M1（策略落地）：完成 policy 字段与执行分支接线。`[已完成，见 V2.7 M1 验收报告]`
2. M2（动作扩展）：完成 `merge_docs/split_doc` 规划与应用通道。`[已完成，见 V2.7 M2 验收报告]`
3. M3（门禁与观测）：完成 validate/garden 指标与失败策略。`[已完成，见 V2.7 M3 验收报告]`
4. M4（验收收口）：完成测试矩阵、验收报告与 closeout 文档。`[已完成，见 V2.7 M4 验收报告]`

## 9. 风险与缓解

1. 风险：语义输出不稳定导致文档波动。
   - 缓解：保留 gate + fallback + 审计报告三层保护。
2. 风险：新增动作导致复杂度提升。
   - 缓解：动作契约最小化，先覆盖 merge/split 基线能力。
3. 风险：历史仓库缺乏 runtime 工件。
   - 缓解：`hybrid` 默认可回退，逐步提高语义命中率。

## 10. 下一步

1. 先提交 V2.7 策略与动作契约变更的测试用例。
2. 再实施 `doc_plan/doc_apply/doc_validate/doc_garden` 的代码改造。
3. 完成一次真实仓库演练，产出 V2.7 验收报告与 closeout。

## 11. M1 执行记录（2026-02-26）

1. M1 验收结果：`PASS`
2. 验收报告：`docs/exec-plans/active/docs-sor-roadmap-v2.7-m1-acceptance-report.md`

## 12. M2 执行记录（2026-02-26）

1. M2 验收结果：`PASS`
2. 验收报告：`docs/exec-plans/active/docs-sor-roadmap-v2.7-m2-acceptance-report.md`

## 13. M3 执行记录（2026-02-26）

1. M3 验收结果：`PASS`
2. 验收报告：`docs/exec-plans/active/docs-sor-roadmap-v2.7-m3-acceptance-report.md`

## 14. M4 执行记录（2026-02-26）

1. M4 验收结果：`PASS`
2. 测试矩阵：`docs/exec-plans/active/docs-sor-roadmap-v2.7-m4-test-matrix.md`
3. 验收报告：`docs/exec-plans/active/docs-sor-roadmap-v2.7-m4-acceptance-report.md`
4. 收口文档：`docs/exec-plans/completed/docs-sor-roadmap-v2.7-closeout-2026-02-26.md`
