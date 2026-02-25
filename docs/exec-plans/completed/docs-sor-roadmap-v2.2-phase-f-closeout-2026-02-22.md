<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-22 -->
<!-- doc-review-cycle-days: 90 -->

# Docs SoR Roadmap V2.2 Phase F 预验收收口报告（2026-02-22）

## 1. 目标与范围

本收口文档覆盖 Phase F 的 F2/F3/F4 交付闭环，重点验证：

1. `repair_plan_mode` 独立生效并可追溯。
2. `provider=agent_runtime` 语义注入与保守降级可用。
3. 发布前语义门禁断言固化：`fallback_auto_migrate_count==0`、`denylist_migration_count==0`。
4. active/completed 收口规则进入 validate 主链路并可阻断异常。

## 2. 执行结果与证据摘要

### 2.1 代码交付

1. Runtime 语义注入：

- `doc_legacy` 支持按 `source_path` 消费 `docs/.legacy-semantic-report.json`。
- runtime 报告缺字段与候选缺席时，默认保守降级到 `manual_review/skip`。
- 显式开启 `allow_fallback_auto_migrate=true` 且命中 `mapping_table` 时，允许受控 fallback auto。

2. 门禁固化：

- `doc_quality` 新增 `max_fallback_auto_migrate` 阈值（默认 0）并接入 gate failed checks。
- `doc_validate` 同步执行 fallback auto 阈值判定，形成发布前阻断能力。
- denylist 误迁移继续维持硬阻断（`denylist_migration_count`）。

3. 收口治理：

- `doc_validate` 新增 active/completed 校验：active 文档标记 `completed` 时，必须声明并指向可达的 completed 收口文档。

### 2.2 测试与门禁结果

1. 单测：

- `python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'` 通过（43/43）。

2. 预验收链路：

- `repo_scan -> doc_plan(audit) -> doc_validate --fail-on-drift --fail-on-freshness -> doc_quality` 全部通过。

3. 核心指标：

- `fallback_auto_migrate_count=0`
- `denylist_migration_count=0`
- `errors=0`
- `drift=0`

## 3. 偏差与遗留风险

1. 运行环境中 `.agents/skills/docs-sor-maintainer` 当前不可写，导致本轮代码实现与测试仅在 `skills/docs-sor-maintainer` 路径落地并验收。
2. 若后续运行入口强依赖 `.agents/skills/...`，需补做一次目录同步并复验，以避免双副本漂移。

## 4. 后续行动

1. 若环境权限恢复，补齐 `skills/` 与 `.agents/skills/` 同步策略，避免执行路径分叉。
2. 在 CI 中固定执行：

- `doc_validate --fail-on-drift --fail-on-freshness`
- `doc_quality`
- 全量 `test_*.py`

3. 进入下一阶段（F5）前，优先处理历史 active 文档的收口标注一致性，持续压缩 active 文档存量。

## 5. 关联证据

1. 主方案：`docs/exec-plans/active/docs-sor-roadmap-v2.2-phase-f-agent-runtime-semantic-hardening.md`
2. V2 主收口：`docs/exec-plans/completed/docs-sor-roadmap-v2-closeout-2026-02-22.md`
3. 运行手册：`docs/runbook.md`

## 6. 补充说明（2026-02-23）

1. 本文第 3 节中的“双副本漂移风险”已按策略变更收口，V2.4 不再进入开发。  
   参考：`docs/exec-plans/completed/docs-sor-roadmap-v2.4-closeout-2026-02-23.md`。
2. 后续执行口径为 `skills/**` 优先，`.agents/skills/**` 由阶段验收后人工同步。
