# doc_manifest schema

`docs/.doc-manifest.json` defines the target documentation structure.

> Use `docs/.doc-manifest.json` as the only manifest file format.

## Recommended schema

```json
{
  "version": 1,
  "required": {
    "files": [
      "docs/index.md"
    ],
    "dirs": []
  },
  "optional": {
    "files": []
  },
  "archive_dir": "docs/archive"
}
```

> Note: this is the minimal adaptive baseline for tiny repositories.  
> `docs/architecture.md`, `docs/runbook.md`, `docs/exec-plans/*`, `docs/tech-debt`, `docs/glossary.md`, `docs/incident-response.md`, `docs/security.md`, and `docs/compliance.md` are added incrementally when repository signals and policy goals require them.

## Field semantics

- `required.files`: files that must exist.
- `required.dirs`: directories that must exist.
- `optional.files`: managed but not mandatory files.
- `archive_dir`: archive destination for stale docs.

## Migration guidance

1. Map existing docs into required/optional buckets.
2. Keep extra existing docs in `manual_review` until migrated.
3. Move obsolete pages to `archive_dir` instead of deleting.
4. For existing repositories, allow additive evolution to append newly required docs rather than rewriting the manifest wholesale.
