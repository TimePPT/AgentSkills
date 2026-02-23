# semantic runtime report schema

`docs/.semantic-runtime-report.json` is the managed-doc semantic input contract consumed by `doc_apply.py`.

## Recommended schema

```json
{
  "version": 1,
  "generated_at": "2026-02-23T00:00:00+00:00",
  "source": "invoking_agent",
  "entries": [
    {
      "entry_id": "runbook-dev-commands-1",
      "path": "docs/runbook.md",
      "action_type": "fill_claim",
      "section_id": "dev_commands",
      "claim_id": "runbook.dev_commands",
      "status": "ok",
      "statement": "开发流程以 repo_scan/repo_plan/doc_validate 作为标准链路。",
      "content": "- 使用 `repo_scan.py` 采集事实并落盘到 `docs/.repo-facts.json`。",
      "citations": [
        "evidence://repo_scan.modules"
      ],
      "risk_notes": [
        "command list requires review when runbook changes"
      ]
    }
  ]
}
```

## Field semantics

- `version`: report format version.
- `generated_at`: runtime report generation time.
- `source`: producer identity, recommended `invoking_agent`.
- `entries`: semantic candidates list.

Entry fields:

- `entry_id`: optional stable identifier.
- `path`: target managed document path.
- `action_type`: optional action scope (`update_section` / `fill_claim` / `migrate_legacy` / `agents_generate`).
- `section_id`: optional section scope.
- `claim_id`: optional claim scope.
- `status`: `ok` or `manual_review`.
- `statement`: optional concise claim statement (recommended for `fill_claim`).
- `content`: candidate markdown content (`update_section`/`agents_generate` preferred).
- `citations`: optional evidence token list (`fill_claim` should provide at least one token).
- `risk_notes`: optional risk notes for auditing.

For `fill_claim`, provide both `statement` and `citations`. If `statement` is absent, runtime loader will fallback to `content` but gate may reject consumption when citation constraints fail.

## Matching behavior

`doc_semantic_runtime.select_runtime_entry` matches entries in this order:

1. same `path` (required)
2. optional exact `action_type`
3. optional exact `section_id`
4. optional exact `claim_id`

When multiple entries match, higher-specificity entry wins.
