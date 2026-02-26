<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-26 -->
<!-- doc-review-cycle-days: 90 -->

# V2.7 M1 验收报告（2026-02-26）

## 1. 结论

- 验收结果：`PASS`
- 验收范围：`Docs SoR Roadmap V2.7 / M1（策略落地）`
- 判定依据：策略字段接线、执行分支生效、回归测试与门禁通过

## 2. M1 交付清单

1. `semantic_generation` 策略字段落地：
   - 新增 `prefer_agent_semantic_first=true`；
   - 新增 `require_semantic_attempt=true`；
   - 默认动作补齐 `semantic_rewrite=true`。
2. `agents_generation` 执行分支落地：
   - 新增 `regenerate_on_semantic_actions=true`；
   - `mode` 进入执行分支：`dynamic` 语义优先、`deterministic` 跳过 runtime 候选。
3. fallback 决策标准化：
   - 统一 reason code：`runtime_unavailable` / `runtime_entry_not_found` / `runtime_gate_failed` / `path_denied`；
   - `agent_strict` 下禁止 fallback，按 error 处理。

## 3. 验收命令与结果

执行链路：

1. `repo_scan -> doc_plan(audit) -> doc_apply(apply-safe)`
2. `python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_semantic_runtime`
3. `python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_agents`
4. `python3 -m unittest -v skills.docs-sor-maintainer.tests.test_doc_apply_section_actions`
5. `python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'`
6. `doc_validate --fail-on-drift --fail-on-freshness`

结果摘要：

1. 语义与 AGENTS 专项测试：通过。
2. 全量单测：`84/84 passed`。
3. 文档门禁：`errors=0`、`drift=0`、`freshness=0`。

## 4. DoD 对照（M1）

1. policy 字段与默认值已落地：`PASS`
2. `agents_generation.mode` 进入执行分支：`PASS`
3. 语义动作可触发 AGENTS 再生成（无需 manifest 变化）：`PASS`
4. fallback 具备标准化 reason code 并可审计：`PASS`

## 5. 边界与下一里程碑

1. `merge_docs/split_doc` 动作契约与端到端能力属于 M2 范围，本次未纳入验收。
2. 下一阶段进入 V2.7 M2：扩展 planner/apply 的结构化动作通道并补齐端到端用例。
