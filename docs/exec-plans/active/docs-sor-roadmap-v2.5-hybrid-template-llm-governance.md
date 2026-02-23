<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-23 -->
<!-- doc-review-cycle-days: 90 -->
<!-- exec-plan-status: completed -->
<!-- exec-plan-closeout: docs/exec-plans/completed/docs-sor-roadmap-v2.5-closeout-2026-02-23.md -->

# Docs SoR Maintainer V2.5 方案设计（Agent 优先语义增强）

## 状态变更（2026-02-23）

本计划已完成并通过验收，进入收口状态。

收口文档：`docs/exec-plans/completed/docs-sor-roadmap-v2.5-closeout-2026-02-23.md`

## 1. 背景与目标

V2.5 的核心定位不是“做一个文档生成器”，而是“做一个可被 Agent 调用并稳定协作的 skill”。  
因此语义能力设计必须围绕如下事实：

- skill 在 Agent 执行链路内运行；
- 语义理解与生成优先由调用该 skill 的 Agent 完成；
- skill 脚本负责围栏、校验、落盘、审计与回退。

本期总目标：

1. 在创建、更新、迁移、维护全流程引入语义增强能力。
2. 不牺牲 SoR 可审计性、稳定性、可回滚性。
3. 始终具备 deterministic fallback，形成“模板兜底 + Agent 语义增益”。

## 2. 需求澄清（硬约束）

### 2.1 语义能力来源

所有“LLM/CodingAgent 语义输入、分析判断、文本生成”均指：

- 由调用本 skill 的当前 Agent 执行；
- 通过 runtime 工件与脚本交互；
- 不以“必须直连某个外部 LLM API”作为前提。

### 2.2 外部 API 约束

- 默认与推荐路径：`Agent runtime -> 本地语义工件 -> skill scripts`。
- 禁止将外部 LLM API 设为必选依赖。
- 即使未来允许扩展外部 API，也必须是可关闭的 optional adapter，且默认关闭。

### 2.3 失败与回退

- runtime 语义工件缺失、无效、门禁失败时：
  - 优先 fallback 到模板兜底；
  - 或按策略转 `manual_review`；
  - 不允许无证据臆写。

## 3. 设计原则

1. Agent-First：优先利用调用 skill 的 Agent，脚本不越权替代 Agent 决策。
2. Fail-Closed：证据不足或校验失败时，不自动写入高风险语义文本。
3. Deterministic Baseline：模板与结构化规则始终可独立运行。
4. SoR Auditable：所有自动改写必须可追溯到证据与报告。
5. Backward-Compatible：未启用语义增强时，行为保持现有稳定路径。

## 4. 现状与缺口（结合代码库）

当前已有能力：

- `AGENTS.md` 动态生成与校验链路（`doc_agents.py` + `doc_agents_validate.py`）。
- legacy 语义分类读取 runtime 语义报告（`doc_legacy.py`）。
- scan/plan/apply/validate/garden 治理闭环。

当前缺口：

1. managed docs 的 section 内容仍偏模板化；
2. `fill_claim` 仍以 TODO 占位为主；
3. legacy 迁移摘要存在 fallback 占位；
4. doc_garden repair 缺少语义重写路径；
5. 方案文本需从“provider 导向”收敛到“Agent runtime 导向”。

## 5. Agent 与 Skill 交互契约

## 5.1 运行时工件（建议）

- `docs/.semantic-runtime-report.json`：managed docs 语义生成输入工件。
- `docs/.legacy-semantic-report.json`：legacy 语义分类输入工件（现有机制沿用）。

## 5.2 职责分工

- 调用 skill 的 Agent：
  - 读取 repo/docs/facts；
  - 执行语义分析与文本候选生成；
  - 写入 runtime 工件（结构化 JSON）。

- skill scripts：
  - 读取 runtime 工件；
  - 执行结构/证据/质量/策略门禁；
  - 通过后落盘，失败则 fallback 或 manual_review；
  - 输出审计报告。

## 5.3 禁止事项

- 在脚本内直接耦合厂商 API 调用路径作为主流程。
- 未经门禁直接将语义候选写入 SoR 文档。

## 6. 总体架构（模板兜底 + Agent 增益）

### 6.1 双通道

- deterministic channel：模板骨架、section 规则、metadata、路径与链接校验。
- semantic channel：仅消费 Agent runtime 工件中的候选语义内容。

### 6.2 三阶段提交

1. Draft：生成候选（模板或 runtime 语义候选）。
2. Gate：证据、结构、质量、策略门禁。
3. Apply：仅 gate=pass 的内容可写入。

### 6.3 运行模式

- `deterministic`：只走模板路径。
- `hybrid`：默认，优先消费 runtime 语义，失败回退模板。
- `agent_strict`：必须有 runtime 语义且通过门禁，否则失败。

## 7. 配置扩展（建议）

`docs/.doc-policy.json` 增加：

```json
{
  "semantic_generation": {
    "enabled": true,
    "mode": "hybrid",
    "source": "invoking_agent",
    "runtime_report_path": "docs/.semantic-runtime-report.json",
    "fail_closed": true,
    "allow_fallback_template": true,
    "allow_external_llm_api": false,
    "max_output_chars_per_section": 4000,
    "required_evidence_prefixes": ["repo_scan.", "runbook.", "semantic_report."],
    "deny_paths": ["docs/adr/**"],
    "actions": {
      "update_section": true,
      "fill_claim": true,
      "migrate_legacy": true,
      "agents_generate": true
    }
  }
}
```

兼容规则：

- 缺失 `semantic_generation`：默认 deterministic。
- `allow_external_llm_api=false`：禁止启用外部 API 适配器。
- runtime 工件不可用：按 `allow_fallback_template` 执行 fallback 或 manual_review。

## 8. 核心流程设计

### 8.1 创建（bootstrap）

1. 生成 deterministic 骨架。
2. 若 runtime 工件可用，按 section 注入语义候选并门禁校验。
3. 失败则保留骨架并标注 `manual_review`。

### 8.2 更新（audit/apply-safe）

1. `doc_plan` 产出 `update_section/fill_claim/quality_repair`。
2. `doc_apply` 对可语义增强动作读取 runtime 候选。
3. gate 失败回退模板或转人工。

### 8.3 迁移（apply-with-archive）

1. legacy 先分类，再结构化摘要。
2. 摘要/决策/风险段可由 runtime 语义候选增强。
3. source marker 与 archive trace 强制保留。

### 8.4 维护（doc_garden）

1. `scan -> plan -> apply -> validate` 基线不变。
2. 新增 `semantic_rewrite` repair action。
3. 每轮 repair 后重验；超上限后带原因失败。

## 9. 关键伪代码

### 9.1 语义输入解析（Agent runtime）

```python
def load_runtime_semantics(policy, action, root):
    cfg = policy.semantic_generation
    if not cfg.enabled:
        return None, "disabled"
    if not cfg.actions.get(action.type, False):
        return None, "action_not_enabled"

    report = load_json(root / cfg.runtime_report_path)
    if not is_valid_runtime_report(report):
        return None, "runtime_missing_or_invalid"

    entry = select_entry(report, action)
    if not entry:
        return None, "runtime_entry_not_found"
    return entry, "ok"
```

### 9.2 通用生成入口

```python
def generate_content(action, context, policy):
    scaffold = deterministic_scaffold(action, context)
    runtime_entry, status = load_runtime_semantics(policy, action, context.root)

    if status != "ok":
        return fallback_or_review(scaffold, policy, status)

    merged = merge_with_scaffold(scaffold, runtime_entry["content"], action)
    gate = run_generation_gate(merged, action, context, policy)
    if gate.passed:
        return merged, "hybrid"
    return fallback_or_review(scaffold, policy, f"gate_failed:{gate.failed_checks}")
```

### 9.3 `fill_claim` 增强逻辑

```python
def fill_claim_with_runtime(claim, evidence, runtime_entry):
    if not evidence.satisfies(claim.required_evidence_types):
        if claim.allow_unknown:
            return render_unknown_claim(claim), "unknown"
        return None, "manual_review"

    statement = runtime_entry.get("statement", "").strip()
    citations = runtime_entry.get("citations", [])
    if not statement or not citations:
        return None, "manual_review"
    return render_claim(statement, citations), "supported"
```

## 10. Prompt 契约（供调用 skill 的 Agent 使用）

### 10.1 Section 语义增强 Prompt（结构化输出）

```text
System:
You are the invoking coding agent for Docs SoR Maintainer.
You must output strict JSON for runtime report consumption.

User:
Task: Generate section candidate under SoR constraints.
Document Path: {doc_path}
Section ID: {section_id}
Claim Specs: {claim_specs_json}
Evidence Pack: {evidence_json}
Constraints:
- No facts outside evidence.
- Keep required headings/markers unchanged.
- Keep language profile: {language_profile}
- Include citation tokens: evidence://*

Return JSON:
{
  "status": "ok|manual_review",
  "content": "...markdown...",
  "citations": ["evidence://..."],
  "used_evidence_types": ["..."],
  "missing_evidence_types": ["..."],
  "risk_notes": ["..."]
}
```

### 10.2 Legacy 迁移 Prompt（结构化摘要）

```text
Generate structured migration summary with blocks:
Summary / Key Facts / Decisions / TODO & Risks / Source Trace.
Preserve source and archive markers.
If evidence is insufficient, return manual_review.
```

## 11. 开发拆解

### Phase A：契约与配置

- 增加 `semantic_generation.source/runtime_report_path/allow_external_llm_api`。
- 定义 runtime report schema 与校验器。
- 在文档中明确“Agent runtime first”。

### Phase B：动作接入

- `update_section` 消费 runtime 候选。
- `fill_claim` 从 TODO 升级为证据驱动陈述。
- `migrate_legacy` 与 `agents_generate` 支持 runtime 增强。

### Phase C：维护与门禁

- `doc_garden` 接入 `semantic_rewrite`。
- `doc_validate/doc_quality` 增加语义与回退指标。
- 失败分类标准化写入报告。

## 12. 测试策略

### 12.1 单元测试

- runtime report schema 合法/非法输入。
- runtime entry 缺失时 fallback/manual_review。
- gate 规则（无证据、缺 citation、冲突、超长）。
- `allow_external_llm_api=false` 的策略约束测试。

### 12.2 集成测试

- bootstrap/apply-safe/apply-with-archive/doc_garden 四场景覆盖。
- runtime 可用 -> 语义增强成功。
- runtime 不可用 -> 模板兜底或人工审查。
- agent_strict 模式下无 runtime -> 预期失败。

### 12.3 端到端测试

- 全链路通过：`scan -> plan -> apply -> validate -> agents validate`。
- 注入证据缺失：验证不会臆写。
- 禁用语义输入：deterministic 可独立通过。
- 静态检查：语义主流程脚本不出现外部 API 强依赖调用。

## 13. 验收标准（必须全部满足）

1. 四类场景均可由调用 skill 的 Agent 提供语义候选并被 skill 消费。
2. 不存在“必须调用外部 LLM API”才能运行的主流程路径。
3. runtime 工件缺失或无效时，fallback 行为符合 policy。
4. 所有自动写入内容具备 evidence 与报告追踪。
5. `AGENTS.md` 动态更新后通过 `agents gate`。
6. `doc_validate --fail-on-drift --fail-on-freshness` 可通过。
7. 对现有 deterministic 行为无破坏性回归。

## 14. 验收 Checklist

- [x] policy 已新增 `semantic_generation.source=invoking_agent`。
- [x] policy 已新增 `allow_external_llm_api=false` 且默认生效。
- [x] runtime report schema 与解析校验已落地。
- [x] `doc_apply` 已在目标动作消费 runtime 语义候选。
- [x] `doc_validate/doc_quality` 已输出语义与回退指标。
- [x] `doc_garden` 已支持 `semantic_rewrite` 修复动作。
- [x] runtime 缺失场景下 deterministic fallback 测试通过。
- [x] 语义主流程无外部 API 强依赖调用。
- [x] 文档与报告均通过 drift/freshness 门禁。

## 15. 风险与缓解

- 风险：Agent 语义输入质量波动。  
  缓解：骨架固定、门禁校验、失败回退、人工审查出口。
- 风险：runtime 工件格式漂移。  
  缓解：schema 校验、版本字段、兼容解析与告警。
- 风险：错误引入外部 API 依赖。  
  缓解：policy 禁用开关 + 静态扫描测试 + CI gate。
- 风险：修复循环收敛失败。  
  缓解：有界重试、失败分类、收口报告。

## 16. 交付物清单（V2.5）

- 方案文档：本文件（active plan）。
- 代码改造：runtime 语义契约、动作接入、门禁与回退扩展。
- 测试资产：单元/集成/E2E 与静态约束检查。
- 验收记录：通过后补充 completed closeout 并在索引收口。
