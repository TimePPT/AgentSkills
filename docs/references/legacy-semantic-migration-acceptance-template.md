<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-22 -->
<!-- doc-review-cycle-days: 90 -->

# Legacy 语义迁移验收报告模板

## 1. 基本信息

- 验收主题：
- 执行日期：
- 执行人：
- 仓库/分支：
- 关联计划：`docs/exec-plans/active/docs-sor-roadmap-v2.1-semantic-structured-generation.md`

## 2. 验收范围

- Phase 范围：`Phase D`
- 代码范围：
- 文档范围：

## 3. 验收前置

- 已完成 `repo_scan`。
- 已生成 `doc_plan`。
- policy 中 `legacy_sources.semantic.enabled=true`。
- 迁移 denylist 已配置（至少包含 `README.md`、`AGENTS.md`）。

## 4. 测试矩阵执行结果

| 用例 ID | 场景 | 命令/入口 | 预期 | 实际 | 结论 |
| --- | --- | --- | --- | --- | --- |
| D-01 | denylist 误迁移防护 |  | denylist 不产生 `migrate_legacy` |  |  |
| D-02 | 低置信分流 |  | 低置信仅 `manual_review` 或 `skip` |  |  |
| D-03 | 语义冲突 |  | 冲突被计数并触发 gate |  |  |
| D-04 | 幂等 |  | 二次执行不重复迁移/归档 |  |  |
| D-05 | 结构化完整度 |  | `structured_section_completeness >= 0.95` |  |  |

## 5. 迁移演练记录

- 演练环境：
- 样本输入：
- 首次执行结果：
- 二次执行结果：
- 回滚/清理结果：

## 6. Gate 结果

- `doc_validate --fail-on-drift --fail-on-freshness`：
- `semantic_low_confidence_count`：
- `semantic_conflict_count`：
- `semantic_missing_source_marker_auto_count`：
- `structured_section_completeness`：

## 7. 验收结论

- 总结：
- 是否通过：`PASS | FAIL`
- 阻塞项（如有）：

## 8. 后续动作

1. 
2. 
