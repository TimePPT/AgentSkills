<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-22 -->
<!-- doc-review-cycle-days: 90 -->
<!-- exec-plan-status: completed -->
<!-- exec-plan-closeout: docs/exec-plans/completed/docs-sor-roadmap-v2.4-closeout-2026-02-23.md -->

# Docs SoR Roadmap V2.4 收尾计划：双副本同步治理与 CI 门禁收敛

## 状态变更（2026-02-23）

本计划按策略变更收口，不进入开发阶段。

变更依据：

1. `skills/docs-sor-maintainer` 与 `.agents/skills/docs-sor-maintainer` 在本仓库治理中属于同一 skill 的不同使用阶段载体。
2. `.agents/skills/**` 不再要求与 `skills/**` 维持实时一致，不作为发布前强制 gate。
3. 阶段验收完成后由人工执行同步，避免在开发链路中引入额外复杂度与误阻断。

收口文档：`docs/exec-plans/completed/docs-sor-roadmap-v2.4-closeout-2026-02-23.md`

## 1. 背景与问题

该项是历史阶段遗留的未收尾需求，不是文档组织问题。

明确证据：

1. `docs/exec-plans/completed/docs-sor-roadmap-v2.2-phase-f-closeout-2026-02-22.md` 记录 `.agents/skills/docs-sor-maintainer` 不可写，验收仅在 `skills/` 路径落地，存在执行路径分叉风险。
2. `docs/exec-plans/completed/docs-sor-roadmap-v2.3-phase-f5-closeout-2026-02-22.md` 将“双副本同步策略与校验门禁”列为下一阶段动作。
3. 当前代码库无独立的双副本同步执行器与一致性 gate（仅有 `AGENTS` 文档级 `sync_manifest`，不覆盖 `skills/` 与 `.agents/skills/` 目录内容一致性）。

## 2. 目标与完成定义

目标：消除 `skills/docs-sor-maintainer` 与 `.agents/skills/docs-sor-maintainer` 双副本漂移风险，统一发布前校验口径。

完成定义（全部满足才可收口）：

1. 新增双副本同步执行器，支持单向权威源（`skills/` -> `.agents/skills/`）同步。
2. 新增一致性校验器，覆盖 scripts/references/tests 关键路径的 hash 或内容一致性检查。
3. `doc_validate` 或 CI 脚本接入双副本一致性 gate，异常时阻断。
4. 提供一键命令链：`sync -> validate -> unittest`，并有 PASS/FAIL 样例证据。

## 3. 范围与非目标

范围：

1. `skills/docs-sor-maintainer/**` 与 `.agents/skills/docs-sor-maintainer/**` 的运行资产一致性。
2. 同步策略、校验门禁、运行手册与索引文档收敛。

非目标：

1. 不引入外部仓库或远端制品仓发布系统。
2. 不改动 V2.5 语义生成能力设计本身。

## 4. 实施方案

### 4.1 开发工作包

1. WP1（同步器）：新增 `scripts/doc_replica_sync.py`（或等效命令）实现受控同步。
2. WP2（一致性校验）：新增 `scripts/doc_replica_validate.py`，输出 mismatch 清单与摘要。
3. WP3（门禁接入）：在 `doc_validate` 主报告或 CI 流程增加 replica gate 结果。
4. WP4（文档收敛）：更新 `docs/runbook.md` 与 `docs/index.md`，沉淀标准执行链路。

### 4.2 测试工作包

1. 单测：同步器 dry-run、覆盖/跳过策略、冲突处理。
2. 集成：制造单文件偏差并验证 gate 阻断；同步后 gate 通过。
3. 回归：`python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'` 不回归。

## 5. 预验收链路（建议）

```bash
REPO_ROOT="/Users/tompoet/AgentSkills"
PYTHON_BIN="${PYTHON_BIN:-python3}"

"$PYTHON_BIN" "$REPO_ROOT/skills/docs-sor-maintainer/scripts/doc_replica_sync.py" --root "$REPO_ROOT" --source skills --target .agents/skills --mode apply
"$PYTHON_BIN" "$REPO_ROOT/skills/docs-sor-maintainer/scripts/doc_replica_validate.py" --root "$REPO_ROOT" --fail-on-mismatch
"$PYTHON_BIN" "$REPO_ROOT/.agents/skills/docs-sor-maintainer/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$REPO_ROOT/.agents/skills/docs-sor-maintainer/scripts/doc_validate.py" --root "$REPO_ROOT" --facts "$REPO_ROOT/docs/.repo-facts.json" --fail-on-drift --fail-on-freshness --output "$REPO_ROOT/docs/.doc-validate-report.json"
python3 -m unittest discover -s "$REPO_ROOT/skills/docs-sor-maintainer/tests" -p 'test_*.py'
```

## 6. 验收 Checklist

以下 checklist 作为原计划设计留档，不再作为执行门禁。

- [ ] 双副本同步执行器已落地并支持 dry-run/apply。
- [ ] 双副本一致性校验器已落地并可输出差异明细。
- [ ] CI 或 `doc_validate` 已接入 replica gate 且可阻断 mismatch。
- [ ] runbook/index 已更新并可按文档复现。
- [ ] 预验收链路具备 PASS 与 FAIL 双样例证据。

## 7. 与 V2.5 的关系

历史规划中，V2.4 与 V2.5 设计为并行推进。  
按 2026-02-23 的策略变更，V2.4 已收口并废弃开发；当前仅保留 V2.5 作为执行中主线。
