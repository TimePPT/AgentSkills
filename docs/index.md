<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-22 -->
<!-- doc-review-cycle-days: 90 -->

# 文档索引

## 核心文档

- [docs/.doc-policy.json](./.doc-policy.json)
- [docs/.doc-manifest.json](./.doc-manifest.json)
- [docs/.doc-spec.json](./.doc-spec.json)
- [docs/references/doc_spec_schema.md](./references/doc_spec_schema.md)
- [docs/architecture.md](./architecture.md)
- [docs/runbook.md](./runbook.md)
- [docs/exec-plans/active/docs-sor-roadmap-v2.md](./exec-plans/active/docs-sor-roadmap-v2.md)
- [docs/exec-plans/active/docs-sor-legacy-migration-automation-plan.md](./exec-plans/active/docs-sor-legacy-migration-automation-plan.md)
- [docs/exec-plans/active/docs-sor-roadmap-v2.1-semantic-structured-generation.md](./exec-plans/active/docs-sor-roadmap-v2.1-semantic-structured-generation.md)
- [docs/exec-plans/active/docs-sor-roadmap-v2.1-phase-d-test-matrix.md](./exec-plans/active/docs-sor-roadmap-v2.1-phase-d-test-matrix.md)
- [docs/exec-plans/active/docs-sor-roadmap-v2.1-phase-d-acceptance-report.md](./exec-plans/active/docs-sor-roadmap-v2.1-phase-d-acceptance-report.md)
- [docs/references/legacy-semantic-migration-acceptance-template.md](./references/legacy-semantic-migration-acceptance-template.md)

## 操作流程

1. 使用 `.agents/skills/docs-sor-maintainer/scripts/repo_scan.py` 生成仓库事实。
2. 使用 `doc_plan.py` 生成计划，并优先审阅 `update/manual_review/sync_manifest` 动作。
3. 使用 `doc_apply.py --mode apply-safe` 落地低风险变更。
4. 使用 `doc_validate.py --fail-on-drift --fail-on-freshness` 作为合并前门禁。

## 当前仓库范围说明

- 本仓库是 Skill 资产仓库，当前主模块为 `skills/docs-sor-maintainer`。
- `.agents/skills/docs-sor-maintainer` 是运行期同步副本，供当前 Agent 执行脚本时优先引用。
- 本轮文档目标：
  - 固化当前 codebase 的结构与操作约束；
  - 输出下一阶段增强（R2/R5/R6/R7/R8 与 F3/F4/F5）的需求与功能设计，直接指导开发、测试、验收。
  - Phase D 已补齐语义迁移回归矩阵与验收模板，可直接复用到后续迭代。
