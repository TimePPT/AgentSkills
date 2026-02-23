<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-23 -->
<!-- doc-review-cycle-days: 90 -->

# Docs SoR Roadmap V2.5 收口报告（2026-02-23）

## 1. 目标与范围

本收口文档覆盖 V2.5（模板兜底 + Agent runtime 语义增益）交付闭环，验收范围包括：

1. managed docs 语义 runtime 契约与消费链路。
2. `doc_plan -> doc_apply -> doc_garden -> doc_validate/doc_quality` 的语义门禁闭环。
3. 外部 LLM API 非必选依赖约束与 deterministic fallback。
4. active/completed 收口治理与索引可追溯性。

## 2. 执行结果与证据摘要

### 2.1 代码交付

1. runtime 契约与解析：

- 引入 `doc_semantic_runtime` 并统一 `semantic_generation` 配置解析与 runtime report 读取。
- 保留 `allow_external_llm_api=false` 的默认策略，语义入口统一为 `source=invoking_agent`。

2. 动作接入：

- `update_section` 新增 runtime 内容消费与 gate，失败时回退 section scaffold。
- `fill_claim` 支持 runtime 证据陈述（`CLAIM`）与 gate 失败回退 `TODO`。
- `agents_generate` 支持 runtime 候选覆盖，缺失或 gate 失败时保持 deterministic 生成。

3. 维护与门禁：

- 新增 `semantic_rewrite` 动作类型并纳入 `repair` 可执行集合。
- `doc_garden` 修复回路识别 `semantic_rewrite`，支持与 `repair_plan_mode` 组合执行。
- `doc_quality/doc_validate` 输出并门禁 `fallback_auto_migrate_count`、denylist migration 与 structured completeness 指标。

### 2.2 测试与验收结果

1. 单测：

- `python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'` 通过。

2. 门禁链路：

- `repo_scan -> doc_plan(audit) -> doc_validate --fail-on-drift --fail-on-freshness` 通过。
- drift action 为 0、metadata stale docs 为 0、semantic gate 通过。

## 3. 验收结论

V2.5 验收 Checklist 全部满足，计划状态由 `active` 变更为 `completed`。

## 4. 偏差与遗留风险

1. `semantic_rewrite` 当前默认仍是保守执行策略：缺 runtime 候选时转人工/运行时流程，不强制自动改写。
2. 语义质量依赖 invoking agent 输入质量，需继续通过 quality gate 与定期 gardening 维护收敛。

## 5. 后续行动

1. 启动下一阶段（V2.6）规划：聚焦 `semantic_rewrite` 自动修复策略与指标闭环细化。
2. 保持 CI 固定门禁：`doc_validate --fail-on-drift --fail-on-freshness` + 全量 `test_*.py`。
3. 维持 `docs/` 为 SoR，持续更新运行手册与收口索引，避免文档漂移。

## 6. 关联文档

1. 主计划：`docs/exec-plans/active/docs-sor-roadmap-v2.5-hybrid-template-llm-governance.md`
2. 运行手册：`docs/runbook.md`
3. 文档索引：`docs/index.md`
