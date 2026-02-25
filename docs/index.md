<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-24 -->
<!-- doc-review-cycle-days: 90 -->

# 文档索引

## 核心文档

- [docs/.doc-policy.json](./.doc-policy.json)
- [docs/.doc-manifest.json](./.doc-manifest.json)
- [docs/.doc-spec.json](./.doc-spec.json)
- [docs/.doc-topology.json](./.doc-topology.json)
- [docs/references/doc_spec_schema.md](./references/doc_spec_schema.md)
- [docs/references/doc_topology_schema.md](./references/doc_topology_schema.md)
- [docs/architecture.md](./architecture.md)
- [docs/runbook.md](./runbook.md)
- [docs/references/legacy-semantic-migration-acceptance-template.md](./references/legacy-semantic-migration-acceptance-template.md)
- [docs/references/exec-plan-closeout-template.md](./references/exec-plan-closeout-template.md)

## 执行中计划（active）

- 当前无进行中计划（下一阶段待立项）

## 已完成但保留在 active 的历史计划（标记 completed）

- [docs/exec-plans/active/docs-sor-roadmap-v2.6-topology-progressive-disclosure-governance.md](./exec-plans/active/docs-sor-roadmap-v2.6-topology-progressive-disclosure-governance.md)
- [docs/exec-plans/active/docs-sor-roadmap-v2.5-hybrid-template-llm-governance.md](./exec-plans/active/docs-sor-roadmap-v2.5-hybrid-template-llm-governance.md)
- [docs/exec-plans/active/docs-sor-roadmap-v2.5-remediation-agent-strict-policy-enforcement.md](./exec-plans/active/docs-sor-roadmap-v2.5-remediation-agent-strict-policy-enforcement.md)
- [docs/exec-plans/active/docs-sor-roadmap-v2.4-dual-replica-sync-ci-convergence.md](./exec-plans/active/docs-sor-roadmap-v2.4-dual-replica-sync-ci-convergence.md)
- [docs/exec-plans/active/docs-sor-roadmap-v2.md](./exec-plans/active/docs-sor-roadmap-v2.md)
- [docs/exec-plans/active/docs-sor-legacy-migration-automation-plan.md](./exec-plans/active/docs-sor-legacy-migration-automation-plan.md)
- [docs/exec-plans/active/docs-sor-roadmap-v2.1-semantic-structured-generation.md](./exec-plans/active/docs-sor-roadmap-v2.1-semantic-structured-generation.md)
- [docs/exec-plans/active/docs-sor-roadmap-v2.1-phase-e-delivery-preacceptance-anti-drift.md](./exec-plans/active/docs-sor-roadmap-v2.1-phase-e-delivery-preacceptance-anti-drift.md)
- [docs/exec-plans/active/docs-sor-roadmap-v2.2-phase-f-agent-runtime-semantic-hardening.md](./exec-plans/active/docs-sor-roadmap-v2.2-phase-f-agent-runtime-semantic-hardening.md)

## 历史验收证据（active）

- [docs/exec-plans/active/docs-sor-roadmap-v2.6-acceptance-report.md](./exec-plans/active/docs-sor-roadmap-v2.6-acceptance-report.md)
- [docs/exec-plans/active/docs-sor-roadmap-v2.1-phase-d-test-matrix.md](./exec-plans/active/docs-sor-roadmap-v2.1-phase-d-test-matrix.md)
- [docs/exec-plans/active/docs-sor-roadmap-v2.1-phase-d-acceptance-report.md](./exec-plans/active/docs-sor-roadmap-v2.1-phase-d-acceptance-report.md)

## 已完成计划

- [docs/exec-plans/completed/README.md](./exec-plans/completed/README.md)
- [docs/exec-plans/completed/docs-sor-roadmap-v2-closeout-2026-02-22.md](./exec-plans/completed/docs-sor-roadmap-v2-closeout-2026-02-22.md)
- [docs/exec-plans/completed/docs-sor-legacy-migration-automation-closeout-2026-02-22.md](./exec-plans/completed/docs-sor-legacy-migration-automation-closeout-2026-02-22.md)
- [docs/exec-plans/completed/docs-sor-roadmap-v2.1-closeout-2026-02-22.md](./exec-plans/completed/docs-sor-roadmap-v2.1-closeout-2026-02-22.md)
- [docs/exec-plans/completed/docs-sor-roadmap-v2.1-phase-e-closeout-2026-02-22.md](./exec-plans/completed/docs-sor-roadmap-v2.1-phase-e-closeout-2026-02-22.md)
- [docs/exec-plans/completed/docs-sor-roadmap-v2.2-phase-f-closeout-2026-02-22.md](./exec-plans/completed/docs-sor-roadmap-v2.2-phase-f-closeout-2026-02-22.md)
- [docs/exec-plans/completed/docs-sor-roadmap-v2.3-phase-f5-closeout-2026-02-22.md](./exec-plans/completed/docs-sor-roadmap-v2.3-phase-f5-closeout-2026-02-22.md)
- [docs/exec-plans/completed/docs-sor-roadmap-v2.4-closeout-2026-02-23.md](./exec-plans/completed/docs-sor-roadmap-v2.4-closeout-2026-02-23.md)
- [docs/exec-plans/completed/docs-sor-roadmap-v2.5-closeout-2026-02-23.md](./exec-plans/completed/docs-sor-roadmap-v2.5-closeout-2026-02-23.md)
- [docs/exec-plans/completed/docs-sor-roadmap-v2.5-remediation-closeout-2026-02-24.md](./exec-plans/completed/docs-sor-roadmap-v2.5-remediation-closeout-2026-02-24.md)
- [docs/exec-plans/completed/docs-sor-roadmap-v2.6-closeout-2026-02-24.md](./exec-plans/completed/docs-sor-roadmap-v2.6-closeout-2026-02-24.md)

## 操作流程

1. 使用 `skills/docs-sor-maintainer/scripts/repo_scan.py` 生成仓库事实。
2. 使用 `doc_plan.py` 生成计划，并优先审阅 `update/manual_review/sync_manifest` 动作。
3. 使用 `doc_apply.py --mode apply-safe` 落地低风险变更。
4. 使用 `doc_validate.py --fail-on-drift --fail-on-freshness` 作为合并前门禁。

## 当前仓库范围说明

- 本仓库是 Skill 资产仓库，当前主模块为 `skills/docs-sor-maintainer`。
- `.agents/skills/docs-sor-maintainer` 是阶段性人工同步副本，不作为开发阶段实时门禁依据。
- 本轮文档目标：
  - 固化当前 codebase 的结构与操作约束；
  - 历史计划（V2/V2.1/Phase E/F/F5）已补齐 completed 收口标记与收口文档。
  - V2.5（模板兜底 + Agent 语义增益）与 remediation（agent_strict + semantic policy 执行语义）均已完成收口。
  - V2.6（WP1-WP5）已完成验收并收口，详见：
    `docs/exec-plans/completed/docs-sor-roadmap-v2.6-closeout-2026-02-24.md`。
  - V2.4 已按策略变更收口并废弃开发，详见：
    `docs/exec-plans/completed/docs-sor-roadmap-v2.4-closeout-2026-02-23.md`。
