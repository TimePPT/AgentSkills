<!-- doc-owner: docs-maintainer -->
<!-- doc-last-reviewed: 2026-02-21 -->
<!-- doc-review-cycle-days: 90 -->

# Doc Spec Schema

## 目的

`docs/.doc-spec.json` 用于约束文档的章节结构与 claim-evidence 契约，确保后续生成与质量校验均有可追溯依据。

## 顶层结构

```json
{
  "version": 1,
  "documents": [
    {
      "path": "docs/architecture.md",
      "required_sections": ["module_inventory"],
      "render_order": ["module_inventory"],
      "sections": [
        {
          "section_id": "module_inventory",
          "claims": [
            {
              "claim_id": "architecture.modules.top_level",
              "statement_template": "仓库的顶层模块包括：{modules}",
              "required_evidence_types": ["repo_scan.modules"],
              "allow_unknown": true
            }
          ]
        }
      ]
    }
  ]
}
```

## 字段说明

- `version`：schema 版本号，当前固定为 `1`。
- `documents`：受管文档数组。
- `documents[].path`：文档相对路径，使用 POSIX 风格。
- `documents[].required_sections`：必须存在的章节 ID 列表。
- `documents[].render_order`：生成时的章节顺序；未提供时由脚本决定。
- `documents[].sections`：章节定义数组。
- `documents[].sections[].section_id`：章节唯一标识。
- `documents[].sections[].claims`：章节 claim 列表。
- `documents[].sections[].claims[].claim_id`：claim 唯一标识。
- `documents[].sections[].claims[].statement_template`：渲染模板，允许占位符。
- `documents[].sections[].claims[].required_evidence_types`：必需证据类型列表。
- `documents[].sections[].claims[].allow_unknown`：证据不足时是否允许输出 UNKNOWN。
