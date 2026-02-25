<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-22 -->
<!-- doc-review-cycle-days: 90 -->

# Phase D 测试矩阵与回归清单

## 范围

- 来源计划：`docs/exec-plans/active/docs-sor-roadmap-v2.1-semantic-structured-generation.md`
- 目标阶段：`Phase D`
- 关注场景：误迁移、低置信、冲突、幂等、结构化完整度

## 自动化矩阵

| 用例 ID | 场景 | 自动化入口 | 关键断言 |
| --- | --- | --- | --- |
| D-01 | denylist 误迁移防护 | `test_plan_never_auto_migrates_denylist_sources` | `AGENTS.md/README.md` 不进入 `migrate_legacy`，语义决策为 `skip` |
| D-02 | 低置信分流 | `test_plan_routes_manual_review_and_skip_for_semantic_decision` | 中置信进入 `legacy_manual_review`，低置信为 `skip` |
| D-03 | 语义冲突门禁 | `test_validate_reports_semantic_conflict_gate_failure` | 冲突被计数并触发 `semantic gate failed: semantic conflicts exceed threshold` |
| D-04 | 幂等（迁移） | `test_apply_structured_migration_and_registry_semantic_fields` | 同一来源二次 `migrate_legacy` 返回 `skipped`，无重复结构化块 |
| D-05 | 低置信/skip gate 行为 | `test_validate_treats_semantic_skip_sources_as_exempted` | `semantic=skip` 来源不再计入 unresolved |
| D-06 | 结构化完整度门禁 | `test_validate_reports_semantic_gate_failures` | 缺失结构化段落时完整度低于阈值并触发语义 gate |

## 运行命令

```bash
python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_legacy_migration
python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'
```

## 回归通过标准

1. `skills/docs-sor-maintainer/tests/test_doc_legacy_migration.py` 全绿。
2. 全量 `test_*.py` 全绿。
3. `doc_validate --fail-on-drift --fail-on-freshness` 在仓库主流程中通过。
