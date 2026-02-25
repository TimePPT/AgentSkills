<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-21 -->
<!-- doc-review-cycle-days: 90 -->

# Legacy 迁移记录

该文档由 docs-sor-maintainer 自动维护。

## Legacy Source `README.md`
<!-- legacy-source: README.md -->
<!-- legacy-migrated-at: 2026-02-21T15:08:48.791263+00:00 -->

- 来源路径：`README.md`
- 归档路径：`docs/archive/legacy/README.md`

````text
# AgentSkills

`AgentSkills` 是一个专门用于管理 **Agent Skills** 的 Git 仓库。  
仓库目标很直接：把可复用的技能能力沉淀为标准化资产，并统一放在 `skills/` 目录下持续演进。

## 仓库定位

- 作为 Agent 技能集合的单一代码仓库（single repo）
- 通过版本控制管理技能定义、脚本、参考资料与适配配置
- 为后续新增技能提供统一的目录约定与协作方式

## 目录结构（当前）

```text
.
└── skills/
    └── docs-sor-maintainer/
        ├── SKILL.md
        ├── agents/
        │   └── openai.yaml
        ├── references/
        │   ├── doc_manifest_schema.md
        │   ├── doc_policy_schema.md
        │   └── workflow_examples.md
        └── scripts/
            ├── repo_scan.py
            ├── doc_plan.py
            ├── doc_apply.py
            ├── doc_validate.py
            ├── doc_garden.py
            ├── doc_metadata.py
            ├── doc_capabilities.py
            └── language_profiles.py
```

## 当前已收录 Skills

### `docs-sor-maintainer`

用于把仓库文档维护为系统事实来源（System of Record, SoR），核心流程包括：

1. `repo_scan`：扫描代码仓库事实
2. `doc_plan`：生成可追溯维护计划
3. `doc_apply`：按模式执行安全更新
4. `doc_validate`：执行漂移与结构校验
5. `doc_garden`：一体化自动化流程（scan/plan/apply/validate）

适用场景：

- 初始化或修复仓库文档治理基线
- 对齐 `docs/.doc-policy.json` 与 `docs/.doc-manifest.json`
- 在 CI 中执行文档漂移与新鲜度检查
- 周期性文档整理（gardening）自动化任务

## 新增 Skill 约定

后续所有技能统一放在 `skills/` 下，推荐结构如下：

```text
skills/<skill-name>/
├── SKILL.md                # 技能说明、触发条件、执行流程
├── scripts/                # 自动化脚本（可选）
├── references/             # 参考资料与协议说明（可选）
└── agents/                 # Agent 适配配置（可选）
```

建议遵循以下原则：

- 命名清晰：`<skill-name>` 直接体现职责边界
- 最小实现：先可用，再演进，避免过度设计
- 可验证：脚本应支持显式输入输出与失败信号
- 可维护：文档中写清适用场景、前置条件、限制与示例

## 协作与提交流程（建议）

1. 在 `skills/` 下创建或更新对应技能目录
2. 明确更新 `SKILL.md` 的行为边界与使用方式
3. 如包含脚本，确保可运行并具备基础参数说明（`--help`）
4. 自检通过后提交 Pull Request 并进行评审

---

如果你要开始新增一个技能，直接从 `skills/<skill-name>/SKILL.md` 起步即可。
````
