<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-26 -->
<!-- doc-review-cycle-days: 90 -->

# V2.7 M3 验收报告（2026-02-26）

## 1. 结论

- 验收结果：`PASS`
- 验收范围：`Docs SoR Roadmap V2.7 / M3（门禁与观测）`
- 判定依据：`doc_apply/doc_validate/doc_garden` 指标闭环、语义优先门禁策略、端到端命令链与全量测试通过

## 2. M3 交付清单

1. `doc_apply.py` 指标补齐：
   - `summary` 新增 `semantic_attempt_count`、`semantic_success_count`、`fallback_count`、`fallback_reason_breakdown`；
   - 同步产出 `semantic_action_count`、`semantic_hit_rate`、`semantic_unattempted_without_exemption` 等审计字段；
   - Markdown 报告新增语义观测摘要。
2. `doc_validate.py` 门禁增强：
   - 新增 `check_semantic_observability`，读取 `docs/.doc-apply-report.json` 并执行语义优先覆盖率门禁；
   - 支持 `semantic_generation.observability` 阈值配置（比例/数量/失败策略）；
   - `metrics` 与报告正文新增语义观测统计与 gate 状态。
3. `doc_garden.py` 可观测收敛：
   - 报告新增 `semantic_observability` 节点；
   - Markdown 报告新增 `Semantic path hit rate` 输出，作为持续优化基线。
4. 测试与策略文档同步：
   - 新增 `test_doc_validate_semantic_observability.py`；
   - 扩展 `test_doc_apply_section_actions.py` 与 `test_doc_garden_repair_loop.py`；
   - 同步 `language_profiles.py`、`docs/.doc-policy.json` 与 `doc_policy_schema.md` 的 observability 字段。

## 3. 验收命令与结果

执行链路：

1. `python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_apply_section_actions`
2. `python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_validate_semantic_observability`
3. `python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_garden_repair_loop`
4. `python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'`
5. `python3 -m py_compile skills/docs-sor-maintainer/scripts/doc_apply.py skills/docs-sor-maintainer/scripts/doc_validate.py skills/docs-sor-maintainer/scripts/doc_garden.py skills/docs-sor-maintainer/scripts/language_profiles.py`
6. `repo_scan -> doc_plan(audit) -> doc_apply(apply-safe) -> doc_synthesize -> doc_validate --fail-on-drift --fail-on-freshness`
7. `doc_garden --plan-mode audit --apply-mode apply-safe --fail-on-drift --fail-on-freshness`

结果摘要：

1. 相关专项测试通过：`PASS`。
2. 全量单测：`93/93 passed`。
3. 语法自检：`PASS`。
4. 文档门禁：`errors=0`、`warnings=0`、`drift=0`。
5. Garden 报告：`status=passed`，并输出 `Semantic path hit rate` 字段。

## 4. DoD 对照（M3）

1. `doc_apply` 报告新增语义尝试/成功/fallback 指标：`PASS`
2. `doc_validate` 语义优先策略检查与失败策略：`PASS`
3. `doc_garden` 输出语义路径命中率：`PASS`
4. `doc_validate --fail-on-drift --fail-on-freshness` 无回归：`PASS`

## 5. 下一里程碑

1. 进入 V2.7 M4：完成最终验收收口（测试矩阵、总体验收报告、closeout 文档与 active/completed 状态迁移）。
