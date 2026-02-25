<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-24 -->
<!-- doc-review-cycle-days: 90 -->

# Exec Plan 收口报告模板

> 适用范围：`docs/exec-plans/active/*.md` 完成后，在 `docs/exec-plans/completed/` 产出收口文档。

## 1. 目标与范围

1. 计划名称：`<plan-name>`
2. 收口日期：`<YYYY-MM-DD>`
3. 范围边界：
   - 包含：`<modules/features/docs>`
   - 不包含：`<out-of-scope>`

## 2. 执行结果与证据摘要

1. 关键交付：
   - `<deliverable-1>`
   - `<deliverable-2>`
2. 关键命令与结果：
   - `<command-1> -> <pass/fail + summary>`
   - `<command-2> -> <pass/fail + summary>`
3. 关键 gate 指标：
   - `drift_action_count=<value>`
   - `errors=<value>`
   - `warnings=<value>`

## 3. 验收结论

1. 验收结果：`PASS | FAIL`
2. 结论说明：`<one-paragraph summary>`
3. 对应 active 计划状态：`completed`

## 4. 偏差与遗留风险

1. 偏差项：`<if any>`
2. 风险项：`<risk + mitigation>`
3. 回退策略：`<rollback/containment>`

## 5. 后续行动

1. 下一阶段建议：`<next work package or roadmap item>`
2. 长期治理动作：`<quality/automation/freshness actions>`

## 6. 关联文档

1. 主计划：`docs/exec-plans/active/<plan-file>.md`
2. 验收报告（如有）：`docs/exec-plans/active/<acceptance-report>.md`
3. 运行手册：`docs/runbook.md`
4. 文档索引：`docs/index.md`
