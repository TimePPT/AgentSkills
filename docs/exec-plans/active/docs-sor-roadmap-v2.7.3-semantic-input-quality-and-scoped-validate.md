<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-26 -->
<!-- doc-review-cycle-days: 90 -->
<!-- exec-plan-status: completed -->
<!-- exec-plan-closeout: docs/exec-plans/completed/docs-sor-roadmap-v2.7.3-closeout-2026-02-26.md -->

# Docs SoR Roadmap V2.7.3 需求文档（Semantic Input Quality Grading + Scoped Validate）

## 状态变更（2026-02-26）

本计划已完成并通过验收，收口文档：
`docs/exec-plans/completed/docs-sor-roadmap-v2.7.3-closeout-2026-02-26.md`。

## 1. 背景与目标

### 1.1 输入背景

1. V2.7.1 已完成语义优先执行闭环（`topology_repair/navigation_repair/migrate_legacy`）。
2. 当前剩余主要矛盾不在“是否支持语义优先”，而在：
   - 语义输入质量波动时，执行策略与可观测性不够稳定；
   - 全量 `doc_validate` 在规模增长后会成为反馈瓶颈。
3. 依据当前决策：`skills` 与 `.agents` 一致性暂由人工同步保障，不纳入 V2.7.3 开发范围。

### 1.2 版本目标

V2.7.3 聚焦两项能力：

1. **Semantic Runtime 输入质量分级**：将 runtime entry 的“可用性与可信度”从隐式判断升级为显式分级与策略执行。
2. **Scoped Validate 自动化**：在不削弱 gate 有效性的前提下，支持按变更范围执行文档校验并降低反馈时延。

## 2. 范围与非目标

### 2.1 范围（In Scope）

1. `skills/docs-sor-maintainer/scripts/doc_semantic_runtime.py`
2. `skills/docs-sor-maintainer/scripts/doc_apply.py`
3. `skills/docs-sor-maintainer/scripts/doc_validate.py`
4. `skills/docs-sor-maintainer/scripts/doc_quality.py`（如需补指标聚合）
5. `docs/runbook.md`、`docs/index.md`、`AGENTS.md` 的执行入口与导航同步
6. 对应测试目录 `skills/docs-sor-maintainer/tests/`

### 2.2 非目标（Out of Scope）

1. 不引入外部 LLM API 强依赖。
2. 不重构 SoR 主流程（`repo_scan -> doc_plan -> doc_apply -> doc_validate`）。
3. 不将双副本一致性改造为自动同步系统（延续人工同步策略）。

## 3. 需求定义

### FR-1：Semantic Runtime 输入质量分级

1. 对 runtime entry 增加质量分级结果（建议：`A/B/C/D`），并可追溯评分依据。
2. 分级至少覆盖以下维度：
   - 结构完整性（必需字段、action/path/source_path 一致性）；
   - 语义可消费性（content/slots/citations 满足动作 gate）；
   - 证据合规性（citation token、evidence prefix）；
   - 冲突与风险信号（字段冲突、超预算、空载荷等）。
3. `doc_apply` 执行策略必须按等级分流：
   - `A/B`：允许优先消费 runtime；
   - `C`：允许降级（fallback 或 manual_review，受策略控制）；
   - `D`：默认阻断自动消费。
4. `agent_strict` 模式下，低于阈值（建议 `<B`）必须失败，不得静默 fallback。
5. apply/report/validate 必须输出分级指标（数量、命中率、降级原因）。

### FR-2：Scoped Validate 自动化

1. `doc_validate` 支持 scoped 执行模式（按变更文件集校验）。
2. scoped 校验必须包含依赖扩展：
   - 链接依赖（反向/正向）；
   - topology 相关节点；
   - manifest/policy/spec 变更触发的受影响文档集合。
3. 高风险变更自动升级为全量校验（例如：`docs/.doc-policy.json`、`docs/.doc-manifest.json`、`docs/.doc-topology.json`、`doc_validate.py` 本身）。
4. scoped 模式输出必须明确：
   - 作用域输入；
   - 扩展后的最终校验集合；
   - 升级为全量的触发原因（若发生）。

### FR-3：质量门禁与可观测性对齐

1. `doc_validate` 报告中新增：
   - runtime quality grade 分布；
   - scoped/full 运行模式与覆盖统计；
   - 升级触发原因统计。
2. `doc_garden` 与 CI 消费路径不破坏现有字段兼容性（新增字段仅增量添加）。

## 4. 非功能需求（NFR）

1. **Determinism**：同一输入在同一策略下必须产出相同等级与相同 gate 决策。
2. **Backward Compatibility**：新增字段不破坏已有报告解析逻辑。
3. **Performance**：scoped validate 在典型 PR 场景下相较全量有可测收益。
4. **Maintainability**：评分规则与阈值可配置，禁止硬编码散落多处。
5. **Traceability**：每次降级/阻断必须有标准 reason code 与 evidence。

## 5. 方案设计（收敛版）

### 5.1 语义输入质量分级模型

1. 建议新增策略配置（示意）：
   - `semantic_generation.input_quality.enabled`
   - `semantic_generation.input_quality.grade_thresholds`
   - `semantic_generation.input_quality.agent_strict_min_grade`
2. 建议等级语义：
   - `A`：结构完整、证据合规、可直接消费；
   - `B`：轻微缺陷但可安全消费；
   - `C`：可解释但不稳定，需降级；
   - `D`：不可用，需阻断或人工审查。
3. 每个 runtime entry 输出：
   - `quality_grade`
   - `quality_score`
   - `quality_findings[]`
   - `quality_decision`

### 5.2 Scoped Validate 执行模型

1. 增加 validate 参数（示意）：
   - `--scope-files <path1,path2,...>` 或 `--scope-file-list <file>`
   - `--scope-mode changed|explicit`
2. 构建 scope 流程：
   - 读取输入变更集；
   - 依赖扩展；
   - 风险判定（是否升级全量）；
   - 执行 scoped 或 full validate；
   - 输出覆盖与升级证据。
3. CI 推荐策略：
   - PR：默认 scoped，命中高风险规则时自动 full；
   - 主干/定时任务：固定 full validate。

## 6. 伪代码（开发参考）

```text
function evaluate_runtime_quality(entry, action, policy):
  findings = []
  score = 100

  if missing_required_fields(entry, action):
    findings += ["missing_required_fields"]
    score -= 40
  if citation_invalid(entry, policy):
    findings += ["invalid_citation"]
    score -= 20
  if action_gate_failed(entry, action):
    findings += ["action_gate_failed"]
    score -= 30
  if has_conflict_signals(entry):
    findings += ["semantic_conflict_signal"]
    score -= 20

  grade = score_to_grade(score)   # A/B/C/D
  decision = grade_to_decision(grade, policy, mode)
  return {grade, score, findings, decision}
```

```text
function run_validate_with_scope(changed_files, policy, manifest, topology):
  scope = expand_dependencies(changed_files, manifest, topology)
  if touches_high_risk_files(changed_files):
    return run_full_validate(reason="high_risk_upgrade")
  return run_scoped_validate(scope)
```

## 7. 开发任务分解（WP）

1. **WP1（策略与契约）**
   - 补 policy schema 与默认配置；
   - 定义 grade/reason code 词典。
2. **WP2（Runtime 质量评分）**
   - 在 `doc_semantic_runtime` 输出质量评估；
   - 为 `select_runtime_entry` 增加质量优先级排序。
3. **WP3（Apply 决策接线）**
   - 在 `doc_apply` 按 grade 决策消费/降级/阻断；
   - 统一报告字段与 fallback 追踪。
4. **WP4（Scoped Validate）**
   - 在 `doc_validate` 实现 scope 解析、依赖扩展、高风险升级；
   - 输出 scoped 覆盖与升级证据。
5. **WP5（文档与 CI）**
   - 更新 runbook、index、AGENTS；
   - 定义 PR scoped + scheduled full 的执行指引。
6. **WP6（测试与验收）**
   - 单测、集成、回归、性能对比；
   - 输出验收报告与收口文档。

## 8. 测试策略

### 8.1 单元测试（必须）

1. 质量分级：
   - 同输入同策略得到稳定 grade；
   - `agent_strict` 最小等级阈值生效；
   - grade 与 reason code 对齐。
2. scoped 扩展：
   - 仅改普通文档时 scope 收敛；
   - 改 policy/manifest/topology 时升级 full。
3. 执行分流：
   - `A/B` 走 runtime；
   - `C` 走 fallback/manual_review；
   - `D` 阻断。

### 8.2 集成测试（必须）

1. `repo_scan -> doc_plan -> doc_apply -> doc_validate(scope)` 可通过。
2. `repo_scan -> doc_plan -> doc_apply -> doc_validate(full)` 可通过。
3. scoped 与 full 在同一变更样本上的关键错误检测结果一致。

### 8.3 回归测试（必须）

1. 全量 `test_*.py` 通过。
2. 既有 V2.7.1 行为不回归（语义优先、fallback、topology/navigation）。

## 9. 验收 Checklist（DoD）

1. runtime entry 质量分级可追溯、可配置、可测试。
2. `doc_apply` 按 grade 正确执行消费/降级/阻断。
3. scoped validate 能正确扩展依赖，并在高风险变更自动升级 full。
4. validate 报告新增 grade/scoped 指标，且与执行事实一致。
5. PR 场景下 scoped 路径可用，主干 full 路径可用。
6. `doc_validate --fail-on-drift --fail-on-freshness` 在 full 模式通过。
7. 文档体系同步完成：index/AGENTS/manifest/topology/policy 无互相矛盾。

## 10. 验收命令参考

```bash
REPO_ROOT="/absolute/path/to/repo"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SKILL_DIR="$REPO_ROOT/skills/docs-sor-maintainer"

"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode audit --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan-v2.7.3.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_apply.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan-v2.7.3.json" --mode apply-safe"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --facts "$REPO_ROOT/docs/.repo-facts.json" --scope-files "docs/index.md,docs/runbook.md" --fail-on-drift --fail-on-freshness --output "$REPO_ROOT/docs/.doc-validate-report-scoped.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --facts "$REPO_ROOT/docs/.repo-facts.json" --fail-on-drift --fail-on-freshness --output "$REPO_ROOT/docs/.doc-validate-report.json"
python3 -m unittest discover -s "$REPO_ROOT/skills/docs-sor-maintainer/tests" -p 'test_*.py'
```

## 11. 风险与回退

1. 风险：评分阈值过严导致 runtime 命中率骤降。
   - 缓解：先灰度开启，保留可配置阈值与观测看板。
2. 风险：scoped 依赖扩展不完整导致漏检。
   - 缓解：高风险升级 full + 定时 full 对账。
3. 回退策略：
   - 评分模块可降级为“仅观测不门禁”；
   - scoped validate 可临时关闭并退回 full validate。

## 12. 交付物

1. 代码变更 PR（含测试）。
2. V2.7.3 验收报告（active）。
3. V2.7.3 收口文档（completed）。
