<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-26 -->
<!-- doc-review-cycle-days: 90 -->

# V2.7 M2 验收报告（2026-02-26）

## 1. 结论

- 验收结果：`PASS`
- 验收范围：`Docs SoR Roadmap V2.7 / M2（merge_docs + split_doc 动作扩展）`
- 判定依据：planner 显式动作产出、apply 语义执行与 fallback、端到端测试与门禁通过

## 2. M2 交付清单

1. `doc_plan.py` 动作扩展：
   - 质量语义 backlog 支持显式解析 `merge_docs` 与 `split_doc`；
   - 动作包含 `reason + evidence` 与结构化输入字段（`source_paths/split_rules/target_paths/index_path`）。
2. `doc_apply.py` 执行扩展：
   - 新增 `merge_docs` 语义执行分支（runtime 优先 + fallback + `agent_strict` 约束）；
   - 新增 `split_doc` 语义执行分支（runtime 输出多目标文档 + `docs/index.md` 链接补丁）；
   - fallback 统一原因码沿用 `runtime_unavailable/runtime_entry_not_found/runtime_gate_failed/path_denied`。
3. `doc_semantic_runtime.py` 契约扩展：
   - 默认语义动作补齐 `merge_docs=true` 与 `split_doc=true`；
   - runtime report 支持结构化字段：`source_paths`、`split_outputs`、`index_links`、`evidence_map`。
4. 策略默认值同步：
   - `language_profiles.py` 与 `docs/.doc-policy.json` 同步 `merge_docs/split_doc` 动作开关。

## 3. 验收命令与结果

执行链路：

1. `python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_semantic_runtime`
2. `python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_plan_section_actions`
3. `python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_apply_section_actions`
4. `python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'`
5. `python3 -m py_compile skills/docs-sor-maintainer/scripts/*.py`
6. `repo_scan -> doc_plan(audit) -> doc_apply(apply-safe) -> doc_validate --fail-on-drift --fail-on-freshness`

结果摘要：

1. M2 相关专项测试通过（新增 merge/split 场景均 `PASS`）。
2. 全量单测：`89/89 passed`。
3. 语法自检：`PASS`。
4. 文档门禁：`errors=0`、`drift=0`、`freshness=0`。

## 4. DoD 对照（M2）

1. `merge_docs` 规划与应用通道打通：`PASS`
2. `split_doc` 规划与应用通道打通：`PASS`
3. 至少一条 `merge_docs` 与一条 `split_doc` 端到端用例通过：`PASS`
4. 未引入文档门禁回归：`PASS`

## 5. 下一里程碑

1. 进入 V2.7 M3：补齐 `doc_validate/doc_garden` 的语义优先可观测指标与策略门禁。
