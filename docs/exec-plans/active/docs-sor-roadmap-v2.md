<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-22 -->
<!-- doc-review-cycle-days: 90 -->
<!-- exec-plan-status: completed -->
<!-- exec-plan-closeout: docs/exec-plans/completed/docs-sor-roadmap-v2-closeout-2026-02-22.md -->

# Docs SoR Maintainer V2 需求与功能设计

## 1. 目标与边界

本设计文档用于定义下一阶段可落地改造，范围严格限定为：

- `R2`：章节级写作契约（doc-spec）
- `R5`：质量门槛策略（doc_quality_gates）
- `R6`：section-level 维护计划（content gap planning）
- `R7`：doc_garden 自愈循环（plan/apply/validate/repair）
- `R8`：动态 AGENTS 生成机制（bootstrap/sync_manifest 触发）
- `F3`：证据驱动生成引擎算法框架（synthesis）
- `F4`：内容可信校验器算法框架（quality validator）
- `F5`：AGENTS 质量校验算法框架（agents quality validator）

不在本期范围：

- 外部系统接入（Jira/Linear/监控平台）的真实账号权限治理
- 组织审批制度本身（仅定义技术接口与门禁点）

## 2. 当前基线（As-Is）

当前仓库已具备：

- scan/plan/apply/validate/garden 基础闭环
- policy/manifest/language/metadata 护栏
- add/update/archive/manual_review/sync_manifest 动作机制

当前不足：

- 生成内容仍以模板补全为主，缺少 claim-evidence 约束
- 计划粒度停留在 file-level，无法定位章节缺口
- validate 以结构漂移为主，缺少内容质量分与冲突检查
- garden 在失败时直接结束，不做定向 repair
- `AGENTS.md` 由静态模板生成，未根据 manifest/index/facts 动态收敛

## 3. 需求定义（To-Be）

### 3.1 R2：doc-spec（章节级写作契约）

新增 `docs/.doc-spec.json`，定义每个受管文档的章节、claim 与证据约束。

关键要求：

- 每个 section 必须有唯一 `section_id`
- 每个 claim 必须声明：
  - `claim_id`
  - `statement_template`
  - `required_evidence_types`
  - `allow_unknown`（证据不足时是否允许 UNKNOWN）
- 允许按文档定义 `render_order` 与 `required_sections`

### 3.2 R5：doc_quality_gates（质量门槛）

扩展 `docs/.doc-policy.json`：

- `doc_quality_gates.enabled`
- `doc_quality_gates.min_evidence_coverage`
- `doc_quality_gates.max_conflicts`
- `doc_quality_gates.max_unknown_claims`
- `doc_quality_gates.max_unresolved_todo`
- `doc_quality_gates.max_stale_metrics_days`
- `doc_quality_gates.fail_on_quality_gate`

### 3.3 R6：section-level 计划

`doc_plan.py` 需支持以 section 为主的动作，而非仅 file 级动作。

新增动作类型：

- `update_section`：章节缺失或章节结构不合规
- `fill_claim`：claim 未满足或证据不足
- `refresh_evidence`：证据过期需重采样
- `quality_repair`：质量门槛失败后的修复动作

### 3.4 R7：doc_garden 自愈循环

`doc_garden.py` 新增 repair loop：

1. scan -> plan -> apply -> validate
2. 若 validate 失败且失败原因为可修复（`update_section/fill_claim/refresh_evidence`），进入 repair
3. 最多迭代 `max_repair_iterations` 次
4. 仍失败则退出非零并输出失败原因归类

### 3.5 F3：证据驱动生成算法框架

新增 `doc_synthesize.py`，输入 plan + spec + evidence pack，输出候选文档段落与证据映射。

目标：

- 禁止无证据自由生成
- 证据不足时强制 `UNKNOWN` 或 `TODO`（按 spec/policy 决策）
- 输出 `docs/.doc-evidence-map.json`

### 3.6 F4：内容可信校验算法框架

新增 `doc_validate_quality.py`（或并入 `doc_validate.py`）：

- claim-evidence 覆盖率校验
- citation 可解析与可追溯校验
- 跨文档冲突检测（同一 claim_id 多值冲突）
- TODO/UNKNOWN 计数与门槛校验
- 输出质量分和 gate 判定

### 3.7 R8：动态 AGENTS 生成机制

将 `AGENTS.md` 从静态模板升级为动态生成：

- 触发时机：
  - `bootstrap` 首次生成
  - `sync_manifest` 后自动重渲染
  - `doc_garden` 完成后可选重渲染
- 输入来源：
  - `docs/.doc-policy.json`
  - `docs/.doc-manifest.json`
  - `docs/index.md`
  - `docs/.repo-facts.json`
- 目标约束：
  - 保持短小（控制面），不承载细节知识正文
  - 必须包含 SoR 导航入口、关键命令、失败升级边界
  - 与 `docs/index.md` 互补，不重复承载全量索引

### 3.8 F5：AGENTS 质量校验算法框架

新增 AGENTS 专项质量检查（可并入 `doc_validate.py`）：

- 长度与结构约束检查（标题、导航、命令、guardrail 四段）
- 必备链接检查（`docs/index.md`、policy、manifest、运行手册）
- 命令可执行性检查（脚本路径存在、参数模板合法）
- 死链与重复内容比例检查（与 `docs/index.md` 的重叠率阈值）
- 失败时按 `policy` 决定 warning 或 error

## 4. 功能设计

### 4.1 新增文件与脚本

- `references/doc_spec_schema.md`
- `scripts/doc_spec.py`（解析/校验 doc-spec）
- `scripts/doc_synthesize.py`
- `scripts/doc_quality.py`（质量评分与冲突检测，可被 validate/garden 复用）
- `scripts/doc_agents.py`（动态生成 AGENTS.md）
- `scripts/doc_agents_validate.py`（AGENTS 结构/链接/命令质量检查）

### 4.2 数据结构设计

`docs/.doc-spec.json` 结构（摘要）：

```json
{
  "version": 1,
  "documents": [
    {
      "path": "docs/architecture.md",
      "required_sections": ["module_inventory", "dependency_manifests"],
      "sections": [
        {
          "section_id": "module_inventory",
          "claims": [
            {
              "claim_id": "modules.top_level",
              "required_evidence_types": ["repo_scan.modules"],
              "allow_unknown": false
            }
          ]
        }
      ]
    }
  ]
}
```

`docs/.doc-policy.json` 新增片段（摘要）：

```json
{
  "doc_quality_gates": {
    "enabled": true,
    "min_evidence_coverage": 0.9,
    "max_conflicts": 0,
    "max_unknown_claims": 0,
    "max_unresolved_todo": 0,
    "max_stale_metrics_days": 7,
    "fail_on_quality_gate": true
  },
  "doc_gardening": {
    "max_repair_iterations": 2
  },
  "agents_generation": {
    "enabled": true,
    "mode": "dynamic",
    "max_lines": 140,
    "required_links": [
      "docs/index.md",
      "docs/.doc-policy.json",
      "docs/.doc-manifest.json",
      "docs/runbook.md"
    ],
    "sync_on_manifest_change": true,
    "fail_on_agents_drift": true
  }
}
```

### 4.3 计划器执行逻辑（R6）

1. 读取 manifest + policy + spec + facts。
2. 先做 file-level 缺失检查（保持向后兼容）。
3. 对 managed files 逐文档逐 section 评估：
   - section 缺失 -> `update_section`
   - claim 无证据 -> `fill_claim` 或 `manual_review`
   - 证据过期 -> `refresh_evidence`
4. 生成 `summary.action_counts` 并附 section/claim 维度统计。

### 4.4 生成引擎逻辑（F3）

1. 读取 `fill_claim/update_section` 动作。
2. 从 evidence pack 按 `required_evidence_types` 取证并规范化。
3. 若证据满足，渲染 claim 文本并写 citation。
4. 若证据不足：
   - `allow_unknown=true` -> 产出 UNKNOWN 段落
   - 否则输出 `manual_review` 并不自动写入
5. 产出 evidence map 与变更报告。

### 4.5 校验器逻辑（F4 + R5）

1. 解析文档中的 claim/citation 标记。
2. 计算：
   - `evidence_coverage = covered_claims / total_claims`
   - `unknown_claims`
   - `todo_count`
   - `conflict_count`
3. 按 `doc_quality_gates` 判定 pass/fail。
4. 与结构校验结果合并为统一报告，作为 CI gate。

### 4.6 doc_garden 自愈逻辑（R7）

流程：

1. `scan -> plan -> apply -> validate`
2. 若失败原因属于可修复质量问题，自动重跑：
   - 再 scan
   - 带 repair mode 重新 plan
   - apply targeted actions
   - validate
3. 达到最大重试次数后输出最终失败报告与剩余阻塞项。

### 4.7 AGENTS 动态生成逻辑（R8）

1. 汇总 `policy/manifest/index/facts` 生成导航上下文。
2. 渲染 AGENTS 控制面内容：
   - Purpose（SoR 原则）
   - Navigation（指向 index 与关键专题）
   - Standard Commands（最小可执行命令集）
   - Guardrails（升级人工审查边界）
3. 写入 `AGENTS.md`，并输出 `docs/.agents-report.json`（生成来源与哈希）。
4. 当 `manifest_changed=true` 且 `sync_on_manifest_change=true` 时自动重生成。

### 4.8 AGENTS 校验逻辑（F5）

1. 解析 `AGENTS.md`，检查段落结构与必备链接。
2. 提取命令块并校验路径存在性（至少静态可达）。
3. 计算与 `docs/index.md` 文本重叠率，超过阈值则告警。
4. 生成 `docs/.agents-validate-report.json` 并合并进总 validate 结果。

## 5. 开发拆解（建议顺序）

### Phase 1：契约与配置

- 增加 `doc_spec` schema 与解析器
- 扩展 `doc_policy` 的 `doc_quality_gates`
- 扩展 `doc_policy` 的 `agents_generation` 配置
- 为旧仓库提供默认兼容路径（无 spec 时仅执行现有逻辑）

### Phase 2：计划与生成

- 实现 section-level actions（`update_section/fill_claim/refresh_evidence`）
- 接入 `doc_synthesize.py` 与 evidence map 输出
- 实现 `doc_agents.py`，在 bootstrap/sync_manifest 阶段动态生成 AGENTS

#### Phase 2 前置确认（Go/No-Go）

- `docs/.doc-spec.json` 已存在且通过解析器校验
  - 原因：分段规划与证据合成必须以稳定规格作为唯一判断依据
- `scripts/doc_spec.py` 已实现并在 `audit/validate` 中被调用
  - 原因：下游工具必须使用统一解析入口，避免规则分叉
- `docs/.doc-policy.json` 已扩展 `doc_quality_gates` 与 `agents_generation`
  - 原因：Phase 2 的规划动作与 AGENTS 动态生成均依赖 policy 门槛
- `doc_plan.py` / `doc_validate.py` 已加载 `doc-spec` 且在基线仓库无报错
  - 原因：Phase 2 为增量升级，需在无错误基线上执行以保证可追溯性
- Phase 1 生成的 `audit` / `validate` 报告为 0 error/0 warning
  - 原因：若基线不稳，Phase 2 的结果会引入系统性噪声并降低可信度

### Phase 3：校验与自愈

- 实现质量评分与 gate
- 实现 `doc_agents_validate.py` 并接入统一 validate 报告
- 实现 `doc_garden` repair loop
- 输出聚合报告（含每轮失败原因与收敛情况）

## 6. 测试策略

### 6.1 单元测试

- `doc_spec` 解析合法/非法输入
- claim 证据匹配与覆盖率计算
- conflict 检测与 gate 判定
- repair loop 终止条件
- AGENTS 渲染器字段缺失/超长/缺链接处理

### 6.2 集成测试

- 无 spec（兼容模式）回归
- 有 spec 的 section/claim 生成
- quality gate fail -> repair -> pass
- quality gate fail -> repair exhausted -> fail
- manifest 变化后 AGENTS 自动重生成
- AGENTS 缺必备链接时 validate 失败（或按 policy 降级 warning）

### 6.3 端到端测试

- 在示例仓库执行 `doc_garden` 一次收敛
- 在故意缺证据仓库验证 `manual_review` 与非零退出
- 在示例仓库验证 `AGENTS.md` 与 `docs/index.md` 分工：链接互通、内容不重复膨胀

## 7. 验收标准（必须全部满足）

1. `R2`：存在 `doc-spec` 并可被解析，非法 schema 明确报错。
2. `R5`：quality gates 可配置，`fail_on_quality_gate=true` 时可阻断。
3. `R6`：plan 输出 section-level actions，且 action 证据可追溯。
4. `R7`：garden 可执行有界 repair loop，并输出每轮结果。
5. `F3`：生成内容可追溯到 evidence map；证据不足不允许“臆写”。
6. `F4`：validate 报告包含覆盖率、冲突、TODO/UNKNOWN 指标与总判定。
7. `R8`：`AGENTS.md` 可由动态生成器产出，并在 manifest 变更后自动同步。
8. `F5`：validate 报告包含 AGENTS 结构/链接/命令检查结果与 gate 判定。
9. 回归要求：原有 bootstrap/apply-safe/validate 流程可继续运行，不破坏现有仓库。

## 8. 验收 Checklist

- [x] 已提交 `references/doc_spec_schema.md`，并有最小可用样例。
- [x] `doc_policy` 新字段在缺省情况下有稳定默认值。
- [x] `doc_plan` 新动作类型具备单元测试。
- [x] `doc_synthesize` 生成结果包含 citation 与 evidence map。
- [x] `doc_validate`（或质量子模块）输出 quality metrics。
- [x] `doc_garden` 在 `max_repair_iterations` 达到后可正确失败退出。
- [x] `doc_agents` 在 bootstrap/sync_manifest 下可稳定重生成 `AGENTS.md`。
- [x] `doc_agents_validate` 结果已并入总 validate 报告与 CI gate。
- [x] CI 中已新增 quality gate 步骤。
- [x] 示例仓库 E2E 报告包含 pass 与 fail 两类样例。
- [x] 文档中未残留未解释的 TODO（除明确允许的 UNKNOWN 占位）。

## 9. 风险与缓解

- 风险：证据源质量差导致生成质量波动。  
  缓解：在 spec 中强制 evidence 类型与 freshness 校验。
- 风险：计划粒度提升导致执行时间增长。  
  缓解：先按文档增量扫描，再对变更文档做 section 深度校验。
- 风险：repair loop 无限重试。  
  缓解：设置硬上限并记录每轮失败类别，禁止无界重跑。
- 风险：AGENTS 与 index 职责混淆导致重复膨胀。  
  缓解：将 AGENTS 固定为控制面，仅保留入口与命令；详细索引统一放在 `docs/index.md`。

## 10. 验收执行记录（2026-02-21 ~ 2026-02-22）

### 10.1 基线通过（Pass）

- 运行仓库质量门禁流程：`repo_scan -> doc_plan(audit) -> doc_synthesize -> doc_validate --fail-on-drift --fail-on-freshness -> unittest`
- 结果：
  - `doc_plan` 输出 action_count=0
  - `doc_validate` 输出 `errors=0 warnings=0 drift=0`
  - `python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p "test_*.py"` 通过（15 tests）
  - 在隔离副本 `/tmp/docs-sor-r8-agents-check-2` 人为制造 manifest 漂移后，`sync_manifest` 与 `agents_generate` 均自动执行成功

### 10.2 失败样例（Fail，验证门禁与自愈边界）

- 质量门禁失败样例：
  - 将 `doc_quality_gates.min_evidence_coverage` 临时设置为 `1.1`
  - `doc_plan` 产出 `quality_repair` 动作；`doc_apply` 可消费该动作
- repair 上限失败样例：
  - 在隔离副本 `/tmp/docs-sor-r7-repair-check-2` 注入不可满足证据 `repo_scan.nonexistent_signal`
  - `doc_garden` 结果：`status=failed`，`repair.attempts=2`，`max_iterations=2`，达到上限后非零退出

### 10.3 回归兼容样例

- 无 `doc-spec` bootstrap 仓库（隔离副本 `/tmp/docs-sor-regression-bootstrap2`）：
  - `doc_synthesize` 不再报错退出，输出空 evidence map 与告警 `doc-spec missing; synthesis skipped`
  - `doc_validate` 仍可通过：`passed=true`，`errors=0`

### 10.4 TODO 说明

- 文档元数据 owner 已从 `TODO-owner` 迁移为 `docs-maintainer`。
- 当前文档中的 `TODO` 仅出现在需求描述语义（如 `TODO/UNKNOWN` 指标定义）与显式占位规则中，不属于未解释的待办残留。

### 10.5 F5 追加验收（2026-02-22）

- 运行链路：`repo_scan -> doc_plan(audit) -> doc_garden(apply-safe, repair) -> doc_validate --fail-on-drift --fail-on-freshness -> doc_quality -> unittest`
- 结果：
  - `doc_plan` 输出 `action_count=0`
  - `doc_garden` 输出 `status=passed`
  - `doc_validate` 输出 `errors=0 warnings=0 drift=0`
  - `doc_quality` 输出 `gate=passed coverage=1.00 unknown=0 conflicts=0`
  - `python3 -m unittest discover -s skills/docs-sor-maintainer/tests -p 'test_*.py'` 通过（43 tests）

## 11. 收口与后续

- 收口文档：`docs/exec-plans/completed/docs-sor-roadmap-v2-closeout-2026-02-22.md`
- Phase F 收口：`docs/exec-plans/completed/docs-sor-roadmap-v2.2-phase-f-closeout-2026-02-22.md`
- Phase F5 收口：`docs/exec-plans/completed/docs-sor-roadmap-v2.3-phase-f5-closeout-2026-02-22.md`
- 历史建议：`建议进入 V2.4（双副本同步治理 + CI 门禁收敛自动化）`
- 状态更新（2026-02-23）：V2.4 已按策略变更收口并废弃开发，详见
  `docs/exec-plans/completed/docs-sor-roadmap-v2.4-closeout-2026-02-23.md`。
