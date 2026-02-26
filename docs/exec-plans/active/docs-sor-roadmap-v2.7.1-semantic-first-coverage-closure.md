<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-26 -->
<!-- doc-review-cycle-days: 90 -->
<!-- exec-plan-status: completed -->
<!-- exec-plan-closeout: docs/exec-plans/completed/docs-sor-roadmap-v2.7.1-closeout-2026-02-26.md -->

# Docs SoR Roadmap V2.7.1 需求文档（Semantic-First Coverage Closure）

## 状态变更（2026-02-26）

本计划已完成并通过验收，收口文档：
`docs/exec-plans/completed/docs-sor-roadmap-v2.7.1-closeout-2026-02-26.md`。

## 1. 背景与输入基线

### 1.1 输入前提

1. V2.7 已于 2026-02-26 收口，语义优先策略已进入默认策略层。
2. 已人工将 `skills/docs-sor-maintainer` 同步到 `.agents/skills/docs-sor-maintainer`。
3. 本文档以当前 codebase 与现有 SoR 文档为唯一依据，目标是指导下一轮可执行开发、测试、验收。

### 1.2 关键现状（代码与文档一致性视角）

1. `semantic_generation` 已支持 `prefer_agent_semantic_first`、`require_semantic_attempt` 与 observability 配置。
2. `merge_docs/split_doc` 已具备 plan 与 apply 的 runtime-first + fallback 路径。
3. 仍存在关键收敛点：
   - `doc_plan` 会产出 `topology_repair/navigation_repair`，但 `doc_apply` 目前无执行分支，导致动作落到 `unsupported action type`。
   - `migrate_legacy` 在 apply 阶段未走 runtime semantic 内容生成，当前以结构化模板迁移为主。
   - 仓库存在 `skills/` 与 `.agents/` 双副本，仍需制度化防漂移。

## 2. 问题定义

V2.7 已完成“语义优先框架化”，但尚未做到“动作域全闭环”。V2.7.1 需要解决的是：

1. **动作闭环缺口**：计划产出的部分动作无法被执行器消费，形成假阳性 drift 与人工兜底负担。
2. **迁移语义深度不足**：legacy 迁移缺少 runtime semantic 内容重写能力，语义优先在该场景未闭环。
3. **副本治理不足**：双副本同步依赖人工流程，存在后续回归风险。

## 3. 目标与非目标

### 3.1 目标

1. 补齐 `topology_repair/navigation_repair` 的 apply 执行路径，做到“可计划、可执行、可验证”。
2. 将 `migrate_legacy` 升级为 runtime semantic first，规则模板仅作为受控 fallback。
3. 固化 `skills/` 与 `.agents/` 一致性门禁，防止语义策略倒退。
4. 保持 SoR 原则：证据可追溯、策略可审计、变更可回滚。

### 3.2 非目标

1. 不引入外部 LLM API 强依赖。
2. 不做历史文档全量重写。
3. 不在本轮重构整体 roadmap 体系命名与归档策略。

## 4. 范围

1. 代码范围：
   - `skills/docs-sor-maintainer/scripts/doc_plan.py`
   - `skills/docs-sor-maintainer/scripts/doc_apply.py`
   - `skills/docs-sor-maintainer/scripts/doc_semantic_runtime.py`
   - `skills/docs-sor-maintainer/scripts/doc_legacy.py`
   - `skills/docs-sor-maintainer/scripts/doc_validate.py`
2. 文档范围：
   - `docs/runbook.md`（必要命令与门禁补充）
   - `docs/index.md`、`AGENTS.md`（导航与执行入口同步）
3. 测试范围：
   - `skills/docs-sor-maintainer/tests/test_doc_apply_section_actions.py`
   - `skills/docs-sor-maintainer/tests/test_doc_plan_section_actions.py`
   - `skills/docs-sor-maintainer/tests/test_doc_legacy_migration.py`
   - 新增针对 topology/navigation apply 分支的单测文件（若现有文件不适配）。

## 5. 功能需求（FR）

### FR-1：Topology/Navigation 动作执行闭环

1. `doc_apply` 必须支持 `topology_repair` 与 `navigation_repair`。
2. 两类动作至少支持：
   - 写入明确结果状态（`applied/skipped/error`）；
   - 输出结构化 `details` 与失败原因；
   - 在 `report.summary` 中可计数。
3. `navigation_repair` 必须具备最小可执行能力：对 `parent_path` 缺失的子链接进行可控补齐（幂等）。

### FR-2：`migrate_legacy` 语义优先升级

1. 当 `semantic_generation.actions.migrate_legacy=true` 时，必须先尝试 runtime semantic candidate。
2. runtime candidate 门禁通过时，应优先采用语义内容生成迁移条目（含来源追踪）。
3. runtime 缺失或门禁失败时，可按策略 fallback 到现有结构化模板迁移。
4. `agent_strict` 模式下 runtime 不可用必须失败，不得静默 fallback。

### FR-3：语义观测与门禁增强

1. `doc_apply` 对 FR-1、FR-2 新增分支也要计入 `semantic_attempt_count/semantic_success_count/fallback_count`。
2. `doc_validate` 的 semantic observability 需覆盖新动作类型，避免遗漏统计。

### FR-4：双副本一致性门禁

1. 在 runbook 与 CI 建议命令中增加副本一致性检查步骤（至少文件级 diff）。
2. 当检测到 `skills/` 与 `.agents/` 差异时，给出明确阻断或 manual review 建议。

## 6. 非功能需求（NFR）

1. **可维护性**：新增逻辑保持函数职责单一，禁止引入跨模块隐式耦合。
2. **幂等性**：重复执行 `doc_apply` 不得产生重复链接、重复迁移段、重复结构补丁。
3. **可追溯性**：每个非 keep 动作必须具备 `reason + evidence`；fallback 必须有标准原因码。
4. **兼容性**：保留现有 `hybrid/agent_strict/deterministic` 语义，不破坏既有测试语义。

## 7. 方案设计（收敛版）

### 7.1 `topology_repair` 执行语义

1. 输入：`orphan_docs/unreachable_docs/over_depth_docs/topology_metrics`。
2. 输出：以 `details` 明确修复建议与风险摘要；必要时更新 `docs/.doc-topology.json` 的最小补丁（仅当策略允许）。
3. 默认策略：先生成可执行修复建议，再最小化改动；避免大规模自动重写 topology。

### 7.2 `navigation_repair` 执行语义

1. 输入：`parent_path/missing_children`。
2. 行为：对 parent 文档增加缺失链接，链接格式统一、相对路径正确、重复检查严格。
3. 边界：parent 不存在或路径受保护时，返回 `skipped/error` 并保留证据，不做隐式创建。

### 7.3 `migrate_legacy` runtime-first

1. 优先读取 runtime entry（匹配 `path/source_path/action_type`）。
2. runtime 门禁通过：
   - 使用 runtime 内容或 slots 生成迁移段；
   - 更新 registry 并记录 `decision_source=semantic`。
3. runtime 门禁失败：
   - 按现有结构化模板 fallback；
   - 记录 `fallback_used=true` 与 `fallback_reason`。

## 8. 伪代码（开发参考）

```text
function apply_action(action):
  runtime_candidate, failures = attach_runtime_candidate(action)

  if action.type == "navigation_repair":
    if runtime_required_but_missing(action, runtime_candidate):
      return error("runtime_required")
    if failures and not fallback_allowed(failures):
      return skipped("fallback_blocked")
    return apply_navigation_patch(parent_path, missing_children)

  if action.type == "topology_repair":
    if runtime_required_but_missing(action, runtime_candidate):
      return error("runtime_required")
    return apply_topology_patch_or_emit_repair_details(action)

  if action.type == "migrate_legacy":
    payload = build_runtime_legacy_payload(runtime_candidate)
    if payload.valid:
      return migrate_with_runtime_payload(payload)
    if runtime_required_for_action("migrate_legacy"):
      return error("runtime_required")
    if failures and not fallback_allowed(failures):
      return skipped("fallback_blocked")
    return migrate_with_structured_fallback(action)
```

```text
function validate_semantic_observability(report):
  actions = enabled_semantic_actions(policy)
  metrics = summarize_attempt_success_fallback(report.results, actions)
  if metrics.unattempted_without_exemption is large_gap:
    fail_or_warn_by_policy()
```

## 9. 开发任务分解（WP）

1. WP1：`doc_apply` 新增 `topology_repair/navigation_repair` 执行分支与幂等补丁逻辑。
2. WP2：`migrate_legacy` 接入 runtime semantic payload 解析与门禁。
3. WP3：观测计数与 validate 门禁补齐（新动作类型纳入统计）。
4. WP4：runbook/CI 增加 `skills vs .agents` 一致性检查命令与处理策略。
5. WP5：单测与回归用例补齐，完成端到端验收。

## 10. 测试策略与验收矩阵

### 10.1 单元测试（必须）

1. `navigation_repair`：
   - 缺失链接可补齐；
   - 重复执行不重复追加；
   - parent 缺失时返回合理状态。
2. `topology_repair`：
   - 动作可被执行器消费，不再出现 `unsupported action type`。
3. `migrate_legacy`：
   - runtime 命中优先；
   - runtime 失败 fallback；
   - `agent_strict` 阻断 fallback。

### 10.2 集成测试（必须）

1. `repo_scan -> doc_plan(audit) -> doc_apply(apply-safe) -> doc_validate` 全链路 PASS。
2. 含 `topology_repair/navigation_repair` 的 plan 在 apply 后无未消费动作。
3. 含 `migrate_legacy` 的 plan 在 runtime 可用与不可用两种场景均可解释。

### 10.3 验收 Checklist（DoD）

1. `doc_plan` 产出的 `topology_repair/navigation_repair` 在 `doc_apply` 可执行、可追踪。
2. `migrate_legacy` 满足 runtime-first，且 fallback 行为完全受策略约束。
3. `doc_apply` 报告中 `semantic_attempt_count`、`fallback_reason_breakdown` 与实际行为一致。
4. `doc_validate --fail-on-drift --fail-on-freshness` 通过，无新增漂移与新告警。
5. `skills/` 与 `.agents/` 一致性检查有明确执行入口与结果判定标准。
6. 文档体系同步完成：`docs/index.md`、`AGENTS.md`、manifest/topology 均已更新且互不矛盾。

## 11. 回滚与应急

1. 若新分支引发门禁回归：
   - 立即切回仅保留现有稳定动作（禁用新增动作开关）；
   - 保留失败报告与样本用于复盘。
2. 若 runtime 路径异常：
   - `hybrid` 下按策略 fallback；
   - `agent_strict` 下明确失败并转 manual review。

## 12. 交付物

1. 代码变更 PR（含测试）。
2. 测试矩阵与验收报告（建议命名：`docs-sor-roadmap-v2.7.1-m1-acceptance-report.md`）。
3. V2.7.1 收口文档（完成后放入 `docs/exec-plans/completed/`）。
