<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-26 -->
<!-- doc-review-cycle-days: 90 -->

# Docs SoR Roadmap V2.7 收口报告（2026-02-26）

## 1. 目标与范围

1. 计划名称：`docs-sor-roadmap-v2.7-agent-first-semantic-priority-governance`
2. 收口日期：`2026-02-26`
3. 范围边界：
   - 包含：`doc_plan/doc_apply/doc_semantic_runtime/doc_validate/doc_garden` 的语义优先策略、动作扩展、可观测性门禁、验收收口
   - 不包含：外部 LLM API 强依赖改造、历史文档全量重写

## 2. 执行结果与证据摘要

1. 关键交付：
   - 完成 M1-M4 全里程碑，语义优先策略、`merge_docs/split_doc`、observability 门禁与收口治理均闭环。
   - 产出并落地 M4 测试矩阵、M4 验收报告、V2.7 closeout 文档。
2. 关键命令与结果：
   - `python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py' -> PASS (93/93)`
   - `python3 -m unittest -v <M4 聚焦套件> -> PASS (43/43)`
   - `repo_scan -> doc_plan(audit) -> doc_apply(apply-safe) -> doc_synthesize -> doc_validate --fail-on-drift --fail-on-freshness -> PASS`
   - `doc_garden --plan-mode audit --apply-mode apply-safe --fail-on-drift --fail-on-freshness -> PASS`
3. 关键 gate 指标：
   - `drift_action_count=0`
   - `errors=0`
   - `warnings=0`

## 3. 验收结论

1. 验收结果：`PASS`
2. 结论说明：V2.7 在当前仓库基线下完成“实现-测试-文档-收口”一致性闭环。语义优先策略已由默认策略、执行路径、回退语义、可观测性和门禁共同约束，且未引入新增漂移或门禁回归。
3. 对应 active 计划状态：`completed`

## 4. 偏差与遗留风险

1. 偏差项：无阻断偏差。
2. 风险项：语义路径命中率仍受 runtime 工件输入质量影响，若长期缺失可能导致 fallback 占比上升。
3. 回退策略：保留 `hybrid + fail_closed + observability gate` 组合，出现异常时优先回退到 `doc_plan(audit) + manual_review` 流程并阻断自动放行。

## 5. 后续行动

1. 下一阶段建议：启动 V2.8，聚焦语义输入质量分级与 scoped validate 自动化。
2. 长期治理动作：将 `doc_garden` 报告中的语义命中率与 fallback reason breakdown 纳入周期审查，持续压缩无效回退。

## 6. 关联文档

1. 主计划：`docs/exec-plans/active/docs-sor-roadmap-v2.7-agent-first-semantic-priority-governance.md`
2. 验收报告：`docs/exec-plans/active/docs-sor-roadmap-v2.7-m4-acceptance-report.md`
3. 测试矩阵：`docs/exec-plans/active/docs-sor-roadmap-v2.7-m4-test-matrix.md`
4. 运行手册：`docs/runbook.md`
5. 文档索引：`docs/index.md`
