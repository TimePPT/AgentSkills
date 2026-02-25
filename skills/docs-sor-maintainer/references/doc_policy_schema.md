# doc_policy schema

`docs/.doc-policy.json` controls automation boundaries and language lock.

> Use `docs/.doc-policy.json` as the only policy file format.

## Table of Contents

- [Recommended schema](#recommended-schema)
- [Field semantics](#field-semantics)
- [language fields](#language-fields)
- [Guardrail guidance](#guardrail-guidance)

## Recommended schema

```json
{
  "version": 1,
  "mode_default": "audit",
  "require_evidence": true,
  "delete_behavior": "archive",
  "bootstrap_manifest_strategy": "adaptive",
  "bootstrap_agents_md": true,
  "doc_goals": {
    "include": [],
    "exclude": []
  },
  "manifest_evolution": {
    "allow_additive": true,
    "allow_pruning": false
  },
  "adaptive_manifest_overrides": {
    "include_files": [],
    "include_dirs": [],
    "exclude_files": [],
    "exclude_dirs": []
  },
  "doc_metadata": {
    "enabled": true,
    "require_owner": true,
    "require_last_reviewed": true,
    "require_review_cycle_days": true,
    "default_owner": "TODO-owner",
    "default_review_cycle_days": 90,
    "ignore_paths": [
      "docs/archive/**"
    ],
    "stale_warning_enabled": true
  },
  "doc_topology": {
    "enabled": false,
    "path": "docs/.doc-topology.json",
    "enforce_max_depth": true,
    "max_depth": 3,
    "fail_on_orphan": true,
    "fail_on_unreachable": true
  },
  "progressive_disclosure": {
    "enabled": false,
    "required_slots": [
      "summary",
      "key_facts",
      "next_steps"
    ],
    "summary_max_chars": 160,
    "max_key_facts": 5,
    "max_next_steps": 3,
    "fail_on_missing_slots": true
  },
  "doc_gardening": {
    "enabled": true,
    "apply_mode": "apply-safe",
    "repair_plan_mode": "audit",
    "fail_on_drift": true,
    "fail_on_freshness": true,
    "max_repair_iterations": 2,
    "report_json": "docs/.doc-garden-report.json",
    "report_md": "docs/.doc-garden-report.md"
  },
  "doc_quality_gates": {
    "enabled": false,
    "min_evidence_coverage": 0.9,
    "max_conflicts": 0,
    "max_unknown_claims": 0,
    "max_unresolved_todo": 0,
    "max_stale_metrics_days": 7,
    "min_progressive_slot_completeness": 0.95,
    "min_next_step_presence": 1.0,
    "max_section_verbosity_over_budget": 0,
    "max_semantic_conflicts": 0,
    "max_semantic_low_confidence_auto": 0,
    "max_fallback_auto_migrate": 0,
    "min_structured_section_completeness": 0.95,
    "fail_on_quality_gate": true,
    "fail_on_semantic_gate": true
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
  },
  "semantic_generation": {
    "enabled": true,
    "mode": "hybrid",
    "source": "invoking_agent",
    "runtime_report_path": "docs/.semantic-runtime-report.json",
    "fail_closed": true,
    "allow_fallback_template": true,
    "allow_external_llm_api": false,
    "max_output_chars_per_section": 4000,
    "required_evidence_prefixes": [
      "repo_scan.",
      "runbook.",
      "semantic_report."
    ],
    "deny_paths": [
      "docs/adr/**"
    ],
    "actions": {
      "update_section": true,
      "fill_claim": true,
      "migrate_legacy": true,
      "agents_generate": true
    }
  },
  "legacy_sources": {
    "enabled": false,
    "include_globs": [],
    "exclude_globs": [
      "docs/**",
      "docs/archive/**",
      ".git/**",
      ".agents/**",
      "skills/**",
      "**/__pycache__/**",
      "**/*.pyc"
    ],
    "archive_root": "docs/archive/legacy",
    "mapping_strategy": "path_based",
    "target_root": "docs/history/legacy",
    "target_doc": "docs/history/legacy-migration.md",
    "registry_path": "docs/.legacy-migration-map.json",
    "allow_non_markdown": true,
    "exempt_sources": [],
    "mapping_table": {},
    "fail_on_legacy_drift": true,
    "semantic_report_path": "docs/.legacy-semantic-report.json",
    "semantic": {
      "enabled": false,
      "engine": "llm",
      "provider": "agent_runtime",
      "model": "agent-runtime-report-v1",
      "auto_migrate_threshold": 0.85,
      "review_threshold": 0.6,
      "max_chars_per_doc": 20000,
      "categories": [
        "requirement",
        "plan",
        "progress",
        "worklog",
        "agent_ops",
        "not_migratable"
      ],
      "denylist_files": [
        "README.md",
        "AGENTS.md"
      ],
      "fail_closed": true,
      "allow_fallback_auto_migrate": false
    }
  },
  "allow_auto_update": [
    "docs/index.md",
    "docs/architecture.md",
    "docs/runbook.md",
    "docs/glossary.md",
    "docs/incident-response.md",
    "docs/security.md",
    "docs/compliance.md"
  ],
  "protect_from_auto_overwrite": [
    "docs/adr/**"
  ],
  "language": {
    "primary": "zh-CN",
    "profile": "zh-CN",
    "locked": true,
    "preserve_english_terms": true,
    "english_only_contexts": [
      "code_identifiers",
      "config_keys",
      "cli_flags",
      "file_paths"
    ]
  }
}
```

## Field semantics

- `version`: schema version.
- `mode_default`: fallback mode for missing CLI mode.
- `require_evidence`: if true, action must contain evidence before apply.
- `delete_behavior`: only `archive` is recommended.
- `bootstrap_manifest_strategy`: `adaptive` (default) derives minimal manifest from repository signals; `fixed` keeps a static baseline template.
- `bootstrap_agents_md`: allow creating minimal `AGENTS.md` in bootstrap.
- `doc_goals`: explicit include/exclude capability goals (e.g. `architecture`, `runbook`, `planning`, `glossary`, `incident`, `security`, `compliance`).
- `manifest_evolution`: controls whether existing manifest can be expanded additively from newly discovered signals.
- `adaptive_manifest_overrides`: force include/exclude specific files or directories after capability decision.
- `doc_metadata`: ownership/freshness metadata policy for managed markdown docs.
- `doc_topology`: topology contract switch and guard defaults (`path`, `max_depth`, orphan/unreachable failure mode).
- `progressive_disclosure`: section slot contract defaults (`summary/key_facts/next_steps`) and budget constraints.
- `doc_gardening`: automation defaults used by `doc_garden.py`.
  - `repair_plan_mode`: dedicated plan mode for repair rounds.
  - `max_repair_iterations`: upper bound for automatic repair retries.
- `doc_quality_gates`: content quality gate thresholds used by validators.
  - `min_progressive_slot_completeness`: minimum slot completeness ratio for progressive sections.
  - `min_next_step_presence`: minimum ratio of sections that include `next_steps`.
  - `max_section_verbosity_over_budget`: max allowed count of slot budget overruns.
  - `max_semantic_conflicts`: max allowed semantic conflict count.
  - `max_semantic_low_confidence_auto`: max allowed auto-migrated low-confidence items.
  - `max_fallback_auto_migrate`: max allowed fallback auto migrations (recommended `0` for release gates).
  - `min_structured_section_completeness`: minimum completeness ratio for structured migration sections.
  - `fail_on_semantic_gate`: when true, semantic gate failures are treated as errors.
- `agents_generation`: dynamic AGENTS.md generation settings.
- `semantic_generation`: managed-doc semantic generation policy.
  - `mode`: `hybrid` (default), `deterministic`, or `agent_strict`.
  - `source`: semantic producer identifier; recommended `invoking_agent`.
  - `runtime_report_path`: runtime semantic report consumed by apply flow.
  - runtime report v2 entry for section actions supports `slots.summary/key_facts/next_steps`; `doc_apply` enforces slot completeness, verbosity budget, and citation prefix gate before write.
  - `allow_external_llm_api`: must stay `false` by default to avoid provider lock-in.
  - `actions`: explicit allowlist of action types that may consume runtime semantics.
- `legacy_sources`: legacy files discovery/migration policy for non-SoR historical files.
  - `legacy_sources.semantic`: semantic classifier policy for legacy candidates, including threshold routing and denylist.
  - `legacy_sources.semantic.provider`: use `agent_runtime` to consume runtime-injected semantic entries; keep `deterministic_mock` for local testing only.
  - `legacy_sources.semantic.allow_fallback_auto_migrate`: when false (default), semantic absence degrades to `manual_review/skip` only.
  - `legacy_sources.semantic_report_path`: semantic report path consumed by planner and emitted as normalized report.
- `allow_auto_update`: auto-update whitelist.
- `protect_from_auto_overwrite`: protected glob patterns.

### `language` fields

- `language.primary`: primary descriptive language chosen at initialization.
- `language.profile`: template profile used by scripts (`zh-CN` / `en-US`).
- `language.locked`: when true, future runs must follow initialized language.
- `language.preserve_english_terms`: keep technical English terms and identifiers.
- `language.english_only_contexts`: contexts that remain English only.

## Guardrail guidance

- Default to `language.primary=zh-CN` and `language.locked=true`.
- Keep `docs/adr/**` protected.
- Keep `delete_behavior: archive` as hard default.
- Prefer `bootstrap_manifest_strategy: adaptive` for small/new repositories.
- Keep `manifest_evolution.allow_additive=true` to let docs baseline evolve with repository growth.
- Keep `doc_metadata.enabled=true` so validate can enforce ownership/freshness governance.
- Keep `doc_gardening.enabled=true` and run it on schedule for continuous docs gardening.
- Enable `legacy_sources` only after defining strict `include_globs` to avoid accidental broad migration.
- Use `allow_auto_update` as explicit allowlist.
- Prefer manual review for strategy docs and policy docs.
