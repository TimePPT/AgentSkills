<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-24 -->
<!-- doc-review-cycle-days: 90 -->
<!-- exec-plan-status: completed -->
<!-- exec-plan-closeout: docs/exec-plans/completed/docs-sor-roadmap-v2.6-closeout-2026-02-24.md -->

# Docs SoR Maintainer V2.6 需求与实施方案（Topology + 渐进披露 + 语义治理）

## 状态变更（2026-02-24）

本计划已完成并通过验收，收口文档：
`docs/exec-plans/completed/docs-sor-roadmap-v2.6-closeout-2026-02-24.md`。

## 1. 目标与结果定义

V2.6 的目标不是继续扩展模板，而是把文档系统升级为可被 LLM/Agent 高效消费的结构化知识面，确保：

1. 任意受管文档在 `docs/index.md` 起点下最多 3 层可达（archive 除外）。
2. 文档内容既简略又有效，满足渐进披露：每次加载都能获得关键事实与下一步动作。
3. 语义生成从“长文本候选”收敛到“结构化槽位候选”，以降低噪音与漂移。
4. 开发前即具备可执行测试与验收标准，后续交付以通过门禁为唯一目标。

## 2. As-Is 基线（结合当前代码与文档）

## 2.1 已具备能力

1. `scan -> plan -> apply -> validate -> garden` 主链路稳定可用。
2. `semantic_generation`、`legacy semantic`、`agent_strict`、`fail_closed` 已接入执行路径。
3. `doc_quality` 与 `doc_validate` 已有质量/结构门禁基础。

## 2.2 关键缺口

1. 缺少文档拓扑契约与深度门禁：
   - 当前仅检查 index 是否提及 required 文件，不校验拓扑可达性与深度上限。
2. 缺少渐进披露质量契约：
   - 质量门禁覆盖 evidence/conflict/TODO，但未检查“摘要/关键事实/下一步”槽位完整性。
3. 文本膨胀风险仍高：
   - 证据摘要对列表直接拼接，`runbook` claim 容易增长为超长段落。
4. 性能仍有可压缩空间：
   - garden 每轮存在两次 scan；在无实际写入时仍执行第二次 scan。
5. 双副本运行口径仍有历史风险：
   - `skills/**` 与 `.agents/**` 存在内容差异，需要明确“开发主路径 + 同步策略”。

## 2.3 本仓库基线快照（2026-02-24）

1. `docs` 下 markdown 数量：`28`。
2. 从 `docs/index.md` 可达 markdown：`25/28`（不可达样例为报告类与 archive 深层文档）。
3. 当前 index 到可达文档最大点击深度：`1`（尚未失控，但没有硬约束保证未来稳定）。
4. 最近一轮 `doc_garden` 总耗时约 `0.879s`，其中 scan 两次合计约 `0.633s`。

## 3. V2.6 需求（R9-R13）

## R9：文档拓扑契约（3 层可达）

1. 新增拓扑契约文件：`docs/.doc-topology.json`。
2. 受管文档必须映射到固定层级：`root -> section -> leaf`（最大深度 3，root 深度记为 0）。
3. `docs/archive/**` 独立作为 archive 域，不纳入主可达深度判定。
4. `doc_validate` 新增拓扑门禁指标：
   - `topology_reachable_ratio`
   - `topology_orphan_count`
   - `topology_max_depth`
5. 默认硬门槛：
   - `topology_max_depth <= 3`
   - `topology_orphan_count == 0`
   - `topology_reachable_ratio == 1.0`（archive 除外）

## R10：渐进披露内容契约（有效且简略）

1. 对受管文档关键 section 增加结构化槽位要求：
   - `summary`
   - `key_facts`
   - `next_steps`
2. 每个槽位具备可量化预算：
   - `summary`：单段，建议 <= 160 字符（中文语境）。
   - `key_facts`：1-5 条。
   - `next_steps`：1-3 条可执行动作（命令、路径或文档跳转）。
3. `doc_quality` 新增门禁指标：
   - `progressive_slot_completeness`
   - `next_step_presence`
   - `section_verbosity_over_budget_count`

## R11：语义输入契约 V2（面向 invoking Agent）

1. `docs/.semantic-runtime-report.json` 升级为结构化候选优先：
   - 支持 `slots.summary` / `slots.key_facts` / `slots.next_steps`。
2. `doc_apply` 消费语义候选时必须执行槽位级 gate：
   - 引用前缀合法；
   - 槽位长度不过预算；
   - 必填槽位完整。
3. `agent_strict` 下，若 runtime 缺失或槽位 gate 失败，直接失败，不得 fallback 写入。

## R12：执行性能与增量化

1. `repo_scan` 支持快照缓存与增量扫描。
2. `doc_garden` 在 `apply.applied=0` 时跳过 `scan-post-apply`。
3. `doc_validate/doc_quality` 支持按变更文件集进行 scoped 校验。
4. 新增性能报告指标：
   - `scan_duration_ms`
   - `plan_duration_ms`
   - `validate_duration_ms`
   - `garden_total_duration_ms`
   - `scoped_validation_file_count`

## R13：验收治理前置

1. 先测试后开发：V2.6 相关测试骨架先入库，再进入实现。
2. 所有阶段必须输出：
   - 测试结果
   - gate 报告
   - 验收 checklist 勾选状态

## 4. 关键设计

## 4.1 `docs/.doc-topology.json`（新增契约）

建议结构：

```json
{
  "version": 1,
  "root": "docs/index.md",
  "max_depth": 3,
  "nodes": [
    {
      "path": "docs/index.md",
      "layer": "root",
      "parent": null,
      "domain": "core"
    },
    {
      "path": "docs/runbook.md",
      "layer": "section",
      "parent": "docs/index.md",
      "domain": "operations"
    },
    {
      "path": "docs/exec-plans/active/docs-sor-roadmap-v2.6-topology-progressive-disclosure-governance.md",
      "layer": "leaf",
      "parent": "docs/index.md",
      "domain": "planning"
    }
  ],
  "archive": {
    "root": "docs/archive",
    "excluded_from_depth_gate": true
  }
}
```

## 4.2 Policy 扩展（建议）

`docs/.doc-policy.json` 增加：

```json
{
  "doc_topology": {
    "enabled": true,
    "path": "docs/.doc-topology.json",
    "enforce_max_depth": true,
    "max_depth": 3,
    "fail_on_orphan": true,
    "fail_on_unreachable": true
  },
  "progressive_disclosure": {
    "enabled": true,
    "required_slots": ["summary", "key_facts", "next_steps"],
    "summary_max_chars": 160,
    "max_key_facts": 5,
    "max_next_steps": 3,
    "fail_on_missing_slots": true
  },
  "performance_gates": {
    "enabled": true,
    "max_garden_total_seconds": 2.0,
    "max_scan_seconds": 0.5,
    "fail_on_performance_regression": false
  }
}
```

## 4.3 Runtime 语义报告 V2（建议）

```json
{
  "version": 2,
  "generated_at": "2026-02-24T00:00:00+00:00",
  "source": "invoking_agent",
  "entries": [
    {
      "entry_id": "runbook-dev_commands-v2",
      "path": "docs/runbook.md",
      "action_type": "update_section",
      "section_id": "dev_commands",
      "status": "ok",
      "slots": {
        "summary": "开发主链路以 scan-plan-apply-validate 为准。",
        "key_facts": [
          "事实来源统一为 docs/.repo-facts.json",
          "计划文件统一为 docs/.doc-plan.json"
        ],
        "next_steps": [
          "执行 repo_scan 生成事实",
          "执行 doc_plan --mode audit",
          "执行 doc_validate --fail-on-drift --fail-on-freshness"
        ]
      },
      "citations": [
        "evidence://runbook.dev_commands",
        "evidence://repo_scan.modules"
      ],
      "risk_notes": [
        "若命令路径变更，需同步 runbook 与 AGENTS"
      ]
    }
  ]
}
```

## 4.4 核心伪代码

### 4.4.1 拓扑门禁

```python
def validate_topology(index_path, topology, managed_docs):
    graph = build_graph(topology.nodes)
    depth = bfs_depth(graph, start=index_path)

    orphan_docs = [d for d in managed_docs if d not in graph]
    unreachable_docs = [d for d in managed_docs if depth.get(d) is None]
    max_depth = max(depth.values()) if depth else 0

    return {
        "orphan_count": len(orphan_docs),
        "unreachable_count": len(unreachable_docs),
        "max_depth": max_depth,
        "reachable_ratio": reachable_ratio(managed_docs, unreachable_docs)
    }
```

### 4.4.2 渐进披露门禁

```python
def evaluate_progressive_slots(doc, section_rules):
    slots = extract_slots(doc)
    missing = []
    if not slots.summary:
        missing.append("summary")
    if not slots.key_facts:
        missing.append("key_facts")
    if not slots.next_steps:
        missing.append("next_steps")

    over_budget = count_budget_violations(slots, section_rules)
    return {"missing_slots": missing, "over_budget": over_budget}
```

### 4.4.3 garden 优化路径

```python
def run_cycle():
    scan()
    plan()
    apply_report = apply()
    if apply_report.applied == 0:
        synthesize()
        return validate()   # skip second scan
    scan_post_apply()
    synthesize()
    return validate()
```

## 5. 面向调用 Skill 的 LLM/Agent Prompt 契约（建议）

## 5.1 拓扑分类 Prompt

```text
System:
You are the invoking agent for Docs SoR Maintainer.
Classify docs into topology nodes under max depth 3.
Do not invent files that do not exist.

User:
Input:
- Docs file list: {docs_file_list_json}
- Current index links: {index_links_json}
- Existing topology (optional): {topology_json}

Output strict JSON:
{
  "status": "ok|manual_review",
  "nodes": [
    {
      "path": "docs/...",
      "layer": "root|section|leaf|archive",
      "parent": "docs/..." | null,
      "domain": "core|planning|operations|reference|archive",
      "rationale": "..."
    }
  ],
  "issues": ["..."]
}
```

## 5.2 Section 渐进披露生成 Prompt

```text
System:
Generate concise progressive-disclosure content in zh-CN.
Use only provided evidence. No unsupported claims.

User:
Task: Generate structured slots for one section.
Document: {doc_path}
Section: {section_id}
Evidence: {evidence_pack_json}
Constraints:
- summary <= 160 chars
- key_facts: 1..5
- next_steps: 1..3 actionable items
- citations must be evidence:// tokens

Output strict JSON:
{
  "status": "ok|manual_review",
  "slots": {
    "summary": "...",
    "key_facts": ["..."],
    "next_steps": ["..."]
  },
  "citations": ["evidence://..."],
  "risk_notes": ["..."]
}
```

## 5.3 质量修复 Prompt

```text
System:
Repair only failed slots. Keep unaffected content unchanged.

User:
Failed checks: {failed_checks_json}
Current section content: {section_content}
Evidence: {evidence_pack_json}

Return strict JSON:
{
  "status": "ok|manual_review",
  "patched_slots": {
    "summary": "...",
    "key_facts": ["..."],
    "next_steps": ["..."]
  },
  "citations": ["evidence://..."]
}
```

## 6. 开发分解与 DoD

## WP1：契约与配置（Topology + Progressive）

范围：

1. 新增 `docs/.doc-topology.json` 与 schema 说明。
2. 扩展 policy 结构并提供默认兼容值。

DoD：

1. `doc_plan/doc_validate` 能加载新契约。
2. 老仓库缺失 topology 时维持兼容，不直接崩溃。

### WP1 实施结果（2026-02-24）

- [x] 新增 `docs/.doc-topology.json` 与 `docs/references/doc_topology_schema.md`。
- [x] `docs/.doc-policy.json` 完成 `doc_topology` 与 `progressive_disclosure` 配置扩展。
- [x] `doc_plan.py` 接入 topology/progressive 配置解析，并对启用但缺失/非法契约输出 `manual_review`。
- [x] `doc_validate.py` 接入 topology 契约检查并输出 `doc_topology` 报告字段。
- [x] 新增 `test_doc_topology_schema.py`，覆盖默认兼容、缺失契约、非法契约、合法契约路径。

## WP2：Planner/Validator 能力接入

范围：

1. planner 输出拓扑相关动作：`topology_repair`、`navigation_repair`。
2. validate 输出拓扑与渐进披露指标并门禁。

DoD：

1. 新指标出现在 validate/quality 报告。
2. 越界时 gate 正确失败。

### WP2 实施结果（2026-02-24）

- [x] `doc_topology.py` 新增拓扑评估能力：`topology_reachable_ratio`、`topology_orphan_count`、`topology_max_depth` 与导航缺口统计。
- [x] `doc_plan.py` 新增拓扑动作类型：`topology_repair`、`navigation_repair`，并在 audit 阶段输出可修复证据。
- [x] `doc_validate.py` 接入拓扑硬门禁：orphan/unreachable/depth 越界按策略失败。
- [x] `doc_quality.py` 新增渐进披露指标：`progressive_slot_completeness`、`next_step_presence`、`section_verbosity_over_budget_count`，并纳入 quality gate。
- [x] 新增测试：`test_doc_validate_topology_depth.py`、`test_doc_quality_progressive_slots.py`；全量测试 `69/69` 通过。
- [x] 预验收链路通过：`doc_plan` action_count=0，`doc_validate` errors=0/warnings=0/drift=0。

## WP3：Apply 与语义输入 V2

范围：

1. `doc_apply` 支持 slots 写入。
2. runtime report v2 解析与 gate。

DoD：

1. `agent_strict` 场景严格阻断不合规 runtime。
2. `hybrid` 场景可 fallback 且保留审计信息。

### WP3 实施结果（2026-02-24）

- [x] `doc_semantic_runtime.py` 支持 runtime report v2 `slots.summary/key_facts/next_steps`，并兼容 slots-only entry。
- [x] `doc_apply.py` 为 `update_section/semantic_rewrite` 接入 slots gate：必填槽位、预算限制、citation 前缀合法性。
- [x] `agent_strict` 在 runtime 缺失或 slots gate 失败时返回 `error`，不写入 fallback 内容。
- [x] `hybrid` 在 slots gate 失败时保留 `semantic_runtime.gate` 审计信息，并按策略执行 fallback。
- [x] 新增测试 `test_doc_apply_semantic_slots_v2.py`，并补充 `test_doc_semantic_runtime.py` 的 slots-only 解析覆盖。
- [x] 预验收链路通过：`doc_plan` action_count=0，`doc_apply` Applied=0/Errors=0，`doc_validate` errors=0/warnings=0/drift=0，单测 `73/73` 通过。

## WP4：Garden 增量优化

范围：

1. apply 无写入时跳过二次 scan。
2. 输出性能指标。

DoD：

1. 报告可见 step 耗时与总耗时。
2. 无行为变化回归通过（功能语义不改变）。

### WP4 实施结果（2026-02-24）

- [x] `doc_garden.py` 在 `apply.applied=0` 时跳过 `scan-post-apply`，并在 `repair.cycles[*]` 记录 skip 原因。
- [x] 报告新增 step 级 `duration_ms` 与汇总 `performance` 指标（`scan_duration_ms`、`plan_duration_ms`、`validate_duration_ms`、`garden_total_duration_ms`）。
- [x] 新增测试 `test_doc_garden_skip_post_scan_when_no_apply.py`，并回归 `test_doc_garden_repair_loop.py`。
- [x] 预验收链路通过：`doc_garden` status=passed、applied=0、`run:scan-post-apply` 未出现，单测 `74/74` 通过。

## WP5：文档与索引收敛

范围：

1. index/manifest/runbook 同步 V2.6 入口与执行链路。
2. 防止新增文档变为 stale candidate。

DoD：

1. `doc_validate --fail-on-drift --fail-on-freshness` 通过。

### WP5 实施结果（2026-02-24）

- [x] 新增 `docs/exec-plans/active/docs-sor-roadmap-v2.6-acceptance-report.md`，沉淀 WP5 验收证据与门禁结果。
- [x] 新增 `docs/references/exec-plan-closeout-template.md`，统一后续 exec-plan 收口文档编写模板。
- [x] 新增 `docs/exec-plans/completed/docs-sor-roadmap-v2.6-closeout-2026-02-24.md`，完成 `active(completed) -> completed(closeout)` 闭环。
- [x] 同步 `docs/index.md`、`docs/runbook.md`、`docs/.doc-manifest.json`、`docs/.doc-policy.json`、`docs/.doc-topology.json`，确保新增文档可达、可检索、受 freshness 治理。
- [x] 复验通过：`doc_plan action_count=0`，`doc_validate errors=0 warnings=0 drift=0`，并完成全量 `test_*.py` 回归。

## 7. 测试与验收标准（开发前锁定）

## 7.1 必备测试清单

单元测试新增（建议）：

1. `test_doc_topology_schema.py`
2. `test_doc_validate_topology_depth.py`
3. `test_doc_quality_progressive_slots.py`
4. `test_doc_apply_semantic_slots_v2.py`
5. `test_doc_garden_skip_post_scan_when_no_apply.py`

集成测试新增（建议）：

1. `IT-V26-01`：拓扑完整且深度 <=3，validate 通过。
2. `IT-V26-02`：存在 orphan 文档，validate 失败。
3. `IT-V26-03`：runtime slots 缺失，agent_strict 失败。
4. `IT-V26-04`：hybrid 模式 runtime 缺失，fallback 成功并标注审计状态。
5. `IT-V26-05`：garden 在 applied=0 时跳过 post-scan。

性能回归测试新增（建议）：

1. `PF-V26-01`：中等仓库连续 10 轮 garden，P95 总耗时不高于 V2.5 基线的 1.2 倍。
2. `PF-V26-02`：apply=0 场景下 garden 总耗时较旧路径下降 >= 20%。

## 7.2 预验收标准命令

```bash
REPO_ROOT="/Users/tompoet/AgentSkills"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SKILL_DIR="$REPO_ROOT/skills/docs-sor-maintainer"

"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode audit --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_apply.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan.json" --mode apply-safe
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_synthesize.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan.json" --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-evidence-map.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_quality.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.doc-quality-report.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --facts "$REPO_ROOT/docs/.repo-facts.json" --fail-on-drift --fail-on-freshness --output "$REPO_ROOT/docs/.doc-validate-report.json"
python3 -m unittest discover -s "$REPO_ROOT/skills/docs-sor-maintainer/tests" -p 'test_*.py'
```

## 7.3 验收硬门槛

1. 功能门槛：
   - topology gate 全部通过；
   - progressive slot gate 全部通过；
   - `agent_strict` 与 `hybrid` 路径均有覆盖。
2. 质量门槛：
   - `drift_action_count=0`
   - `errors=0`
   - `warnings=0`（验收场景）
3. 性能门槛：
   - `apply=0` 场景必须触发 skip-post-scan 优化路径。

## 8. 验收 Checklist（发布前必须逐项确认）

- [x] `docs/.doc-topology.json` 已落盘并通过 schema 校验
- [x] `doc_plan` 可输出拓扑/导航修复动作
- [x] `doc_apply` 支持 slots 写入与 gate 拦截
- [x] `doc_validate` 输出拓扑指标并按阈值阻断
- [x] `doc_quality` 输出渐进披露指标并按阈值阻断
- [x] `doc_garden` 在 `apply.applied=0` 场景跳过 post-scan
- [x] 新增单测与集成测试全部通过
- [x] 预验收命令链路跑通，`errors=0` 且 `drift_action_count=0`
- [x] V2.6 验收报告与 closeout 模板已准备完毕

## 9. 风险与回退

1. 风险：拓扑规则过严导致误阻断。
   - 回退：允许策略层临时降级为 warning，但保留报告指标。
2. 风险：slots 契约造成初期维护成本上升。
   - 回退：仅对 `allow_auto_update` 白名单文档先启用强制 slots。
3. 风险：性能优化改变现有执行语义。
   - 回退：保留 `doc_garden` 兼容开关，出现偏差时回退到旧执行顺序。

## 10. 交付与收口要求

1. 本文档作为 V2.6 开发唯一需求基线。
2. 开发期间若发生需求变更，必须先更新本文档与验收 checklist。
3. 完成后必须新增对应 closeout 文档，并将本计划标记为 completed 且挂接 closeout 链接。
