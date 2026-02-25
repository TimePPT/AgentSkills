<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-22 -->
<!-- doc-review-cycle-days: 90 -->

# Docs SoR Roadmap V2.1 收口报告（2026-02-22）

## 1. 收口结论

V2.1（语义判定与结构化生成）需求已实现并验收通过，当前留在 `active/` 的主要问题是文档状态未统一标注，而非能力未落地。

## 2. 实现对照（需求 -> 代码）

1. 语义决策分流：`auto_migrate/manual_review/skip` 决策链路可执行。  
   对照：`skills/docs-sor-maintainer/scripts/doc_legacy.py`、`skills/docs-sor-maintainer/scripts/doc_plan.py`。
2. 结构化迁移与来源追踪：迁移动作可写入结构化块与 source marker。  
   对照：`skills/docs-sor-maintainer/scripts/doc_apply.py`。
3. 语义质量与风险门禁：低置信自动迁移、语义冲突、结构化完整度指标进入校验。  
   对照：`skills/docs-sor-maintainer/scripts/doc_quality.py`、`skills/docs-sor-maintainer/scripts/doc_validate.py`。

## 3. 测试与验收证据

1. Phase D 测试矩阵：`docs/exec-plans/active/docs-sor-roadmap-v2.1-phase-d-test-matrix.md`。
2. Phase D 验收报告：`docs/exec-plans/active/docs-sor-roadmap-v2.1-phase-d-acceptance-report.md`（`PASS`）。
3. 代码回归：`skills/docs-sor-maintainer/tests/test_doc_legacy_migration.py` 覆盖 denylist、防误迁移、幂等、冲突与完整度场景。

## 4. 偏差与遗留风险

1. V2.1 作为能力基线已闭环；后续风险主要在运行治理与发布门禁，已转入 V2.2/F 与 V2.4 路线继续治理。

## 5. 关联文档

1. 来源计划：`docs/exec-plans/active/docs-sor-roadmap-v2.1-semantic-structured-generation.md`
2. Phase E 方案：`docs/exec-plans/active/docs-sor-roadmap-v2.1-phase-e-delivery-preacceptance-anti-drift.md`
3. V2 主收口：`docs/exec-plans/completed/docs-sor-roadmap-v2-closeout-2026-02-22.md`

## 6. 补充说明（2026-02-23）

1. 本文中“转入 V2.4 路线继续治理”的描述已完成状态更新：V2.4 已收口且废弃开发。  
   参考：`docs/exec-plans/completed/docs-sor-roadmap-v2.4-closeout-2026-02-23.md`。
