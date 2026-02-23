<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-22 -->
<!-- doc-review-cycle-days: 90 -->
<!-- exec-plan-status: completed -->
<!-- exec-plan-closeout: docs/exec-plans/completed/docs-sor-legacy-migration-automation-closeout-2026-02-22.md -->

# Docs SoR Legacy 继承与集中归档自动化规划

## 1. 目标

在保持 `docs/` 为 system of record 的前提下，新增两项能力：

- 自动化继承旧文件内容（需求/进度/开发日志等）并沉淀到 `docs/` 受管文档。
- 自动集中归档历史文件，归档范围覆盖 `docs/` 内外，不再只处理 `docs/**/*.md`。

## 2. 现状与差距

当前 `docs-sor-maintainer` 已具备 scan/plan/apply/validate/garden 闭环，但对 legacy 场景仍有边界：

- stale 候选扫描范围仅限 `docs/**/*.md`。
- `archive` 动作仅从上述范围生成。
- 无 `migrate_legacy` 动作，无法把旧文件内容自动抽取到新的 SoR 文档。
- `validate` 未检查“legacy 是否已迁移或豁免”，存在遗漏风险。

## 3. 设计原则

- 最小侵入：保留现有 `add/update/archive/manual_review` 行为，不破坏已有工作流。
- 可追溯：每个迁移动作必须记录来源文件、目标文档、归档路径与证据摘要。
- 安全优先：先落地新文档再归档旧文件，失败不允许出现“已删未迁”。
- 渐进演进：默认先 `audit + manual_review`，确认映射后再执行 `apply-with-archive`。

## 4. 目标能力设计

### 4.1 Policy 扩展（legacy source contract）

在 `docs/.doc-policy.json` 增加 `legacy_sources`：

- `enabled`: 是否启用 legacy 纳管。
- `include_globs`: 旧文件扫描范围（支持 `requirements/**`、`logs/**`、`notes/**` 等）。
- `exclude_globs`: 排除规则（例如临时目录、二进制产物）。
- `archive_root`: 统一归档根目录，默认 `docs/archive/legacy`。
- `mapping_strategy`: `path_based | tag_based | manual_table`。
- `allow_non_markdown`: 是否允许 `.txt/.rst/.adoc` 等输入。

### 4.2 Plan 动作扩展

在 `doc_plan.py` 增加新动作类型：

- `migrate_legacy`: 将 legacy 内容迁移到目标 SoR 文档或 `docs/history/` 页面。
- `archive_legacy`: 将迁移完成的源文件移动到 `docs/archive/legacy/...`。
- `legacy_manual_review`: 映射不确定或内容冲突时人工处理。

动作最小字段：

- `source_path`
- `target_path`
- `archive_path`
- `content_blocks`（标题、摘要、时间、原文片段）
- `mapping_reason`
- `evidence`

### 4.3 Apply 执行扩展

在 `doc_apply.py` 增加 legacy 执行器：

1. 读取 `migrate_legacy`，按模板将内容追加或合并到目标文档。
2. 写入来源追踪标记（`source_path` + `migrated_at`）。
3. 迁移成功后执行 `archive_legacy`（文件移动，不做硬删除）。
4. 目标冲突或解析失败时，降级为 `legacy_manual_review` 并保留源文件。

### 4.4 Validate 扩展

在 `doc_validate.py` 增加 legacy gate：

- legacy 文件覆盖率：`migrated + exempted == discovered`。
- 归档一致性：`archive_path` 可追溯到 `source_path`。
- 链接完整性：迁移文档中的引用路径必须存在。
- 失败策略：按 policy 决定 warning 或 error。

## 5. 迁移流程（建议）

1. 配置 `legacy_sources.include_globs/exclude_globs`。
2. 执行 `repo_scan -> doc_plan --mode audit`，生成迁移清单。
3. 审阅 `legacy_manual_review` 项，确认映射和保留策略。
4. 执行 `doc_apply --mode apply-with-archive`。
5. 执行 `doc_validate --fail-on-drift --fail-on-freshness`，并开启 legacy gate。

## 6. 交付拆分与工作量

### 6.1 P1（1-2 人日）

- Policy 增量字段定义与解析。
- planner 支持 `docs/` 外 legacy 发现与 `legacy_manual_review` 输出。
- 不落地自动迁移，仅产出清单与建议归档路径。

### 6.2 P2（2-3 人日）

- 新增 `migrate_legacy` 与 `archive_legacy` 执行逻辑。
- 引入迁移追踪标记与幂等保护（避免重复迁移）。
- 加入冲突降级策略（自动转 `legacy_manual_review`）。

### 6.3 P3（1-2 人日）

- validate 增加 legacy 覆盖率与归档一致性门禁。
- 补充测试矩阵（正向/冲突/回滚/重复执行）。
- 接入 `doc_garden`，支持定期治理 legacy backlog。

总评估：约 4-7 人日，可按 P1 -> P2 -> P3 渐进上线。

## 7. 验收标准

- 能识别并纳管 `docs/` 外 legacy 文件。
- 迁移后 SoR 文档含来源追踪，且内容可检索。
- 迁移成功后源文件归档到 `docs/archive/legacy`，无硬删除。
- `doc_validate` 可对 legacy 覆盖率给出可执行 gate 结果。
- 连续两次执行结果幂等，无重复迁移与路径漂移。
