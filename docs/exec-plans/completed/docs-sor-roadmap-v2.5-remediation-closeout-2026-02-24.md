<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-24 -->
<!-- doc-review-cycle-days: 90 -->

# Docs SoR Roadmap V2.5 修复收口报告（2026-02-24）

## 1. 目标与范围

本收口文档对应 `docs-sor-roadmap-v2.5-remediation-agent-strict-policy-enforcement`，覆盖以下 3 个问题闭环：

1. `agent_strict` 未强失败的问题。
2. `semantic_generation` 中 `fail_closed`、`allow_fallback_template`、`deny_paths` 未执行生效的问题。
3. V2.5 文档结论与代码事实不一致的问题。

## 2. 修复结果

## 2.1 Issue-1：`agent_strict` 强约束

已完成：

1. `doc_apply` 在 `update_section`、`fill_claim`、`semantic_rewrite`、`agents_generate` 路径上统一落实 strict 失败语义。
2. 当 runtime 候选缺失或 gate 失败时，`agent_strict` 下返回 `error`，不再静默 fallback。

## 2.2 Issue-2：语义策略字段执行化

已完成：

1. `deny_paths` 命中时 runtime 语义候选被拒绝（`path_denied`）。
2. `allow_fallback_template` + `fail_closed` 参与 fallback 判定：
   - fallback 允许 -> 保持 hybrid 兜底行为；
   - fallback 禁止 -> 阻断自动写入（`skipped`/`error`，取决于 strict）。
3. `doc_apply` 结果中可追踪 `fallback_blocked`、`runtime_required` 等状态。

## 2.3 Issue-3：文档语义漂移修复

已完成：

1. 增补本次 remediation 计划与收口文档，形成 `active(标记 completed) -> completed(closeout)` 闭环。
2. 同步更新 `docs/index.md`、`docs/runbook.md`、`docs/.doc-manifest.json`、`docs/.doc-policy.json`，确保门禁可追溯。
3. 对既有 V2.5 收口文档追加补充说明，消除“结论先行”风险。

## 3. 测试与验收证据

## 3.1 单元测试

执行结果：

1. `python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_apply_section_actions` 通过（新增 strict/fallback/deny_paths/agents strict 用例）。
2. `python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_semantic_runtime` 通过。
3. `python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'` 通过（58 tests）。

## 3.2 门禁链路

执行结果：

1. `repo_scan -> doc_plan(audit) -> doc_quality -> doc_validate --fail-on-drift --fail-on-freshness` 通过。
2. `doc_garden.py --apply-mode apply-safe --repair-plan-mode repair --fail-on-drift --fail-on-freshness` 通过。
3. 验收时关键指标：
   - `drift_action_count=0`
   - `errors=0`
   - `warnings=0`
   - `doc_quality.gate=passed`

## 4. 验收结论

本 remediation 计划的 Checklist 全部满足，3 个 issue 均完成修复并通过测试与门禁验收。  
V2.5 在当前代码基线下达成“实现-测试-文档”一致性。

## 5. 后续建议

1. 后续新增 `semantic_generation` 策略字段时，必须同步新增执行分支和单测，禁止再次出现死配置。
2. `agent_strict` 场景应保持回归用例常驻，作为发布前必跑项。

