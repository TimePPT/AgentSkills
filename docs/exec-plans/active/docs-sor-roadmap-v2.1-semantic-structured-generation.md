<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-22 -->
<!-- doc-review-cycle-days: 90 -->

# Docs SoR Maintainer V2.1 需求策划：语义判定与结构化生成

## 1. 背景与问题定义

当前仓库已完成 V2 与 legacy 迁移基线，具备如下能力：

- 规则边界下的候选发现与归档迁移（`legacy_sources` + `migrate_legacy/archive_legacy`）。
- 文档结构、漂移与新鲜度门禁（`doc_validate`）。
- claim/evidence 级别的基础质量评估（`doc_quality` + `doc_synthesize`）。

现存核心缺口：

- legacy 迁移仍以 pattern 为主，缺少语义分类与置信度分流。
- 迁移生成仍以“原文附加”为主，缺少结构化摘要与关键事实归纳。
- validate 对 legacy 仅校验覆盖率/归档一致性，未形成语义质量门禁。

本期目标是让 LLM 在“硬边界内”承担语义判断与结构化生成，而不是替代安全边界。

## 2. As-Is 代码基线（关键锚点）

- 候选发现：`skills/docs-sor-maintainer/scripts/doc_legacy.py`
- 迁移规划：`skills/docs-sor-maintainer/scripts/doc_plan.py`
- 迁移执行：`skills/docs-sor-maintainer/scripts/doc_apply.py`
- 覆盖率校验：`skills/docs-sor-maintainer/scripts/doc_validate.py`
- 证据合成：`skills/docs-sor-maintainer/scripts/doc_synthesize.py`
- 质量门禁：`skills/docs-sor-maintainer/scripts/doc_quality.py`

## 3. V2.1 目标与边界

### 3.1 目标

- 在 `include_globs/exclude_globs` 硬边界内，新增语义分类与决策分流。
- 将 legacy 迁移输出升级为结构化文档片段（摘要、关键事实、决策项、来源证据）。
- 为语义迁移建立可审计门禁指标与失败回退路径。

### 3.2 非目标

- 不引入“全仓库无边界语义扫描”。
- 不移除现有规则边界与 denylist。
- 不在本期接入外部知识库或组织审批系统。

## 4. 设计原则

- 安全优先：硬边界先过滤，语义仅在边界内发挥作用。
- 可追溯：每次语义决策必须写入 `why/confidence/model`。
- 可回退：语义引擎异常时降级到 `legacy_manual_review`，禁止盲目自动迁移。
- 可验证：语义质量与迁移质量必须进入 validate gate。

## 5. 目标能力设计

### 5.1 语义判定层（Semantic Decision Layer）

在 legacy pipeline 中新增语义分类：

- 分类标签：
  - `requirement`
  - `plan`
  - `progress`
  - `worklog`
  - `agent_ops`
  - `not_migratable`
- 每个候选输出：
  - `category`
  - `confidence`（0-1）
  - `rationale`
  - `signals`（关键词、标题、时间线、行动项密度）
  - `decision`（`auto_migrate|manual_review|skip`）

决策规则（建议）：

- `confidence >= auto_migrate_threshold` -> `auto_migrate`
- `review_threshold <= confidence < auto_migrate_threshold` -> `manual_review`
- `< review_threshold` -> `skip`
- 命中 denylist（如 `README.md`、根 `AGENTS.md`）-> 强制 `skip`

### 5.2 结构化生成层（Structured Generation Layer）

对 `auto_migrate` 文件输出统一结构：

- `摘要`：文档目的与上下文
- `关键事实`：时间、责任人、系统/模块、里程碑
- `决策与结论`：已决定事项与约束
- `待办与风险`：未决项、阻塞项、风险项
- `来源追踪`：`source_marker` + 归档路径 + 证据引用

保留规则：

- 原文不丢失，统一归档到 `docs/archive/legacy/**`。
- SoR 侧默认写结构化内容，不直接复制全文（必要时可附短摘录）。

### 5.3 门禁与质量层（Semantic Quality Gate）

在 `doc_validate` 与 `doc_quality` 追加语义指标：

- `semantic_auto_migrate_count`
- `semantic_manual_review_count`
- `semantic_skip_count`
- `semantic_low_confidence_count`
- `semantic_conflict_count`（分类冲突或输出冲突）
- `structured_section_completeness`（结构化字段完整度）

gate 失败条件（建议）：

- auto 迁移中存在 `missing_source_marker`
- `semantic_low_confidence_count` 超阈值且未进入 manual_review
- `structured_section_completeness` 低于阈值

## 6. Policy 扩展（V2.1）

在 `docs/.doc-policy.json` 的 `legacy_sources` 下新增 `semantic`：

```json
{
  "legacy_sources": {
    "semantic": {
      "enabled": true,
      "engine": "llm",
      "model": "gpt-5-codex",
      "auto_migrate_threshold": 0.85,
      "review_threshold": 0.60,
      "max_chars_per_doc": 20000,
      "categories": [
        "requirement",
        "plan",
        "progress",
        "worklog",
        "agent_ops",
        "not_migratable"
      ],
      "denylist_files": [
        "README.md",
        "AGENTS.md"
      ],
      "fail_closed": true
    }
  }
}
```

## 7. 数据契约

### 7.1 新增中间产物

- `docs/.legacy-semantic-report.json`
  - 每个候选文件的分类、置信度、决策、原因、模型信息。

### 7.2 扩展迁移注册表

`docs/.legacy-migration-map.json` 每条记录新增：

- `category`
- `confidence`
- `decision_source`（`semantic|manual|rule`）
- `semantic_model`
- `summary_hash`

## 8. 流程设计（V2.1）

1. `repo_scan`：采集事实。
2. `legacy discover`：规则边界筛选候选。
3. `semantic classify`：LLM 分类与置信度计算。
4. `doc_plan`：生成 `auto_migrate/manual_review/skip` 动作。
5. `doc_apply`：结构化生成并归档原文。
6. `doc_validate`：结构与语义双门禁。
7. `doc_garden`：将语义门禁失败项自动汇总为 repair/backlog。

## 9. 开发拆解与工作量

### Phase A（2 人日）

- 增加 `legacy_sources.semantic` 配置解析。
- 增加语义判定适配层（先支持 deterministic mock + provider 抽象）。
- planner 输出语义证据字段（不改变 apply 行为）。

### Phase B（2-3 人日）

- apply 实现结构化生成模板与摘要写入。
- registry 扩展语义字段。
- manual_review 分流稳定化。

### Phase C（2 人日）

- validate/doc_quality 增加语义门禁指标与失败策略。
- doc_garden 接入语义失败项回收。

### Phase D（1-2 人日）

- 测试矩阵与回归（误迁移、低置信、冲突、幂等）。
- 迁移演练与验收报告模板。

总评估：约 7-9 人日。

## 10. 验收标准（V2.1）

- 规则 denylist 文件（`README.md`、根 `AGENTS.md`）自动迁移命中率为 0。
- 低置信样本不会被自动迁移，均进入 `manual_review` 或 `skip`。
- 自动迁移产物结构化字段完整率 >= 95%。
- 二次执行幂等，无重复摘要块或重复归档。
- `doc_validate --fail-on-drift --fail-on-freshness` 与语义 gate 同时通过。

## 11. 风险与缓解

- 风险：语义误判导致错误迁移。
  - 缓解：阈值分流 + denylist + fail-closed。
- 风险：模型不可用导致流程阻塞。
  - 缓解：降级到 `manual_review`，不自动迁移。
- 风险：摘要“看似正确但事实丢失”。
  - 缓解：强制来源追踪与 evidence 引用；保留原文归档。

## 12. 里程碑输出

- M1：语义判定报告可用（`docs/.legacy-semantic-report.json`）。
- M2：结构化迁移可用（`auto_migrate` 正向链路打通）。
- M3：语义门禁可用（validate/quality/garden 闭环）。

## 13. Phase D 执行记录（2026-02-22）

- 状态：`已完成并验收通过`
- 交付：
  - `docs/exec-plans/active/docs-sor-roadmap-v2.1-phase-d-test-matrix.md`
  - `docs/exec-plans/active/docs-sor-roadmap-v2.1-phase-d-acceptance-report.md`
  - `docs/references/legacy-semantic-migration-acceptance-template.md`
- 新增回归能力：
  - denylist 误迁移防护（`AGENTS.md/README.md`）
  - 语义冲突 gate 触发与计数
  - `semantic skip` 来源 gate 豁免
  - 迁移幂等回归
