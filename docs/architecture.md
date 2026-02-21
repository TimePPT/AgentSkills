<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-21 -->
<!-- doc-review-cycle-days: 90 -->

# 仓库架构

## 概述

`AgentSkills` 用于集中维护可复用的 Agent Skill 资产。当前主能力为 `docs-sor-maintainer`，其职责是把仓库文档维护为 System of Record。
执行模型分为两层：

- 资产源：`skills/docs-sor-maintainer`（长期维护与版本演进）
- 运行副本：`.agents/skills/docs-sor-maintainer`（当前执行路径，已人工同步）

## 模块清单

- `skills`：Skill 源代码与说明文档。
  - `skills/docs-sor-maintainer/SKILL.md`：触发条件、流程、护栏与参考索引。
  - `skills/docs-sor-maintainer/scripts/*.py`：核心自动化脚本。
  - `skills/docs-sor-maintainer/references/*.md`：policy/manifest/workflow 参考契约。
- `.agents/skills/docs-sor-maintainer`：运行时生效版本，供本仓库内实际命令调用。
- `docs`：仓库文档 SoR（policy、manifest、plan、validate 报告、专题文档）。

## 依赖清单

- 运行时依赖：`python3`（标准库实现，无第三方依赖要求）。
- 脚本入口：
  - `repo_scan.py`：事实扫描。
  - `doc_plan.py`：维护计划生成（`bootstrap/audit/apply-safe/apply-with-archive`）。
  - `doc_synthesize.py`：基于 doc-spec + evidence 生成 claim 映射与候选陈述。
  - `doc_quality.py`：质量门槛计算与冲突/TODO/UNKNOWN 统计。
  - `doc_apply.py`：模式化执行（创建、更新、归档、manifest 同步）。
  - `doc_validate.py`：结构/链接/漂移/metadata 校验与 gate。
  - `doc_garden.py`：scan-plan-apply-validate 一体化自动流程。
- 目前仓库无 `pyproject.toml`、`requirements.txt`、CI pipeline；运行命令需显式使用脚本路径。

## 关键数据流

1. `repo_scan` 生成 `docs/.repo-facts.json`。
2. `doc_plan` 读取 facts + policy + manifest 产出 `docs/.doc-plan*.json`。
3. `doc_apply` 读取 plan 写入 `docs/` 与执行报告。
4. `doc_validate` 复算漂移并输出 `docs/.doc-validate-report.json` 作为门禁依据。
