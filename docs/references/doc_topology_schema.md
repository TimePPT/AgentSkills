<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-24 -->
<!-- doc-review-cycle-days: 90 -->

# Topology 契约 Schema

`docs/.doc-topology.json` 定义 Docs SoR 的导航拓扑契约，用于约束主域文档的可达性与层级结构。

## 推荐结构

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
      "parent": "docs/runbook.md",
      "domain": "planning"
    }
  ],
  "archive": {
    "root": "docs/archive",
    "excluded_from_depth_gate": true
  }
}
```

## 字段语义

- `version`：契约版本，必须为正整数。
- `root`：拓扑根节点，默认 `docs/index.md`。
- `max_depth`：主域允许的最大深度，V2.6 默认 `3`。
- `nodes`：拓扑节点集合，按 `path` 唯一识别。
- `nodes[].layer`：层级枚举，允许 `root|section|leaf|archive`。
- `nodes[].parent`：父节点路径；根节点必须为 `null`。
- `nodes[].domain`：语义域标签（`core`、`planning`、`operations`、`reference`、`history` 等）。
- `archive`：归档域配置，默认不参与主深度门禁。

## 兼容性规则

- 当 `docs/.doc-policy.json -> doc_topology.enabled=false` 时，可缺失 topology 文件且不阻断执行。
- 当 `doc_topology.enabled=true` 时，`docs/.doc-topology.json` 必须存在且满足基本结构校验。
- topology 校验失败必须以可诊断错误输出，不允许因异常中断流程。
