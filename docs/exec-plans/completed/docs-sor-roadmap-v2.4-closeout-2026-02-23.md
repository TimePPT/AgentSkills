<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-23 -->
<!-- doc-review-cycle-days: 90 -->

# Docs SoR Roadmap V2.4 收口报告（2026-02-23）

## 1. 目标与范围

V2.4 原计划目标是解决 `skills/docs-sor-maintainer` 与 `.agents/skills/docs-sor-maintainer` 的双副本实时同步与门禁收敛。

## 2. 执行结果与证据摘要

本阶段按策略变更收口，开发工作包废弃，不进入实现：

1. 治理口径调整为：`skills/**` 作为开发与验收阶段的权威实现路径。
2. `.agents/skills/**` 作为阶段性人工同步副本，不纳入实时一致性 gate。
3. 因此 V2.4 中 `doc_replica_sync/doc_replica_validate/replica gate` 相关开发与 CI 改造不再执行。

相关计划文档已标记收口：

1. `docs/exec-plans/active/docs-sor-roadmap-v2.4-dual-replica-sync-ci-convergence.md`
2. `docs/index.md`

## 3. 偏差与遗留风险

1. 人工同步路径依赖流程纪律；若同步遗漏，`.agents/skills/**` 可能短期滞后于 `skills/**`。
2. 该风险已从“代码门禁问题”降级为“阶段性发布流程问题”，通过验收清单与人工检查控制。

## 4. 后续行动

1. 继续推进 V2.5（Agent runtime 语义增强）主线开发与验收。
2. 在 runbook 与 CI 中统一 `skills/**` 优先执行口径，减少路径歧义。
3. 阶段验收完成后执行人工同步至 `.agents/skills/**` 并记录操作证据。

