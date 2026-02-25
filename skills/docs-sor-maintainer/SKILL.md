---
name: docs-sor-maintainer
description: Maintain repository documentation as the system of record by scanning codebase facts, generating evidence-backed plans, and applying mode-gated updates under `docs/`. Use when user asks to bootstrap or repair docs governance, align `docs/.doc-policy.json` and `docs/.doc-manifest.json` with implementation, run drift/freshness gates with `doc_validate.py`, or schedule docs gardening with `doc_garden.py` in CI/automation. Do NOT use for copy-editing-only tasks, translation-only tasks, README/blog writing, or non-repository content.
---

# Docs SoR Maintainer

## Overview

Use this skill to keep `docs/` as the repository system of record. Execute a constrained workflow: scan facts, generate a traceable plan, apply mode-gated updates, and validate drift/structure/link quality, plus ownership/freshness metadata health.

Manifest behavior is adaptive by default: if `docs/.doc-manifest.json` is missing, the planner derives a minimal baseline from repository signals and policy goals; as the repository grows, manifest requirements are expanded additively.
Agent capability is enabled by default: `semantic_generation.enabled=true` with `mode=hybrid`, and `agents_generation.enabled=true`; when runtime semantics are unavailable, apply flow falls back to constrained templates under policy gates.

## Path Conventions

- Always define repository root first, then resolve skill root with fallback:

```bash
REPO_ROOT="/absolute/path/to/repo"
PYTHON_BIN="${PYTHON_BIN:-python3}"
command -v "$PYTHON_BIN" >/dev/null || { echo "python not found: $PYTHON_BIN" >&2; exit 2; }
CODEX_HOME_RESOLVED="${CODEX_HOME:-$HOME/.codex}"

if [ -n "${SKILL_DIR:-}" ]; then
  [ -d "$SKILL_DIR/scripts" ] || {
    echo "invalid SKILL_DIR: $SKILL_DIR (expected scripts/ under this path)" >&2
    exit 2
  }
elif [ -d "$REPO_ROOT/.agents/skills/docs-sor-maintainer/scripts" ]; then
  SKILL_DIR="$REPO_ROOT/.agents/skills/docs-sor-maintainer"
elif [ -d "$CODEX_HOME_RESOLVED/skills/docs-sor-maintainer/scripts" ]; then
  SKILL_DIR="$CODEX_HOME_RESOLVED/skills/docs-sor-maintainer"
else
  echo "docs-sor-maintainer not found. Set SKILL_DIR or install under .agents/skills or \$HOME/.codex/skills." >&2
  exit 2
fi
```

- Resolution priority: explicit `SKILL_DIR` -> `"$REPO_ROOT/.agents/skills/docs-sor-maintainer"` -> `"${CODEX_HOME:-$HOME/.codex}/skills/docs-sor-maintainer"`.
- Always execute scripts with `"$PYTHON_BIN" "$SKILL_DIR/scripts/<script>.py"`.
- Do not use relative script paths unless current directory is the skill folder.
- Before running workflow commands, verify path resolution:

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --help >/dev/null
```

## Language Behavior

- Default primary descriptive language is `zh-CN`.
- Keep programming identifiers and technical terms in English where appropriate (`module`, `class`, `function`, parameter names, CLI flags, config keys, paths).
- During bootstrap, you may set another primary language via `doc_apply.py --init-language <lang>`.
- After initialization, follow `docs/.doc-policy.json -> language` for all future updates.
- If `language.locked=true`, ignore subsequent language override attempts unless user explicitly requests language migration.

## Workflow Decision Tree

1. If repository has no documentation baseline, run `bootstrap`.
2. If repository has docs and you need impact visibility first, run `audit`.
3. If plan only contains low-risk additions or section updates, run `apply-safe`.
4. If plan includes stale docs cleanup, run `apply-with-archive`.
5. If you want scheduled maintenance, run `doc_garden.py` as automation task.
6. In CI, run `audit` and `validate` only. Never push doc rewrites directly to default branch from CI.

## Modes

### `bootstrap`

Goal: initialize minimal documentation baseline and language policy.

Typical actions:
1. Derive required docs from current repo facts (`adaptive`) or use fixed baseline (`fixed` strategy).
2. Create only necessary `docs/` files/directories and policy/manifest files.
3. Create minimal `AGENTS.md` only when missing and policy allows it.
4. Initialize `docs/.doc-policy.json` language settings (`language.primary`, `language.profile`, `language.locked`).

### `audit`

Goal: generate plan and drift signal without changing files.

Typical actions:
1. Collect facts from codebase.
2. Compare against `docs/.doc-manifest.json` and `docs/.doc-policy.json`.
3. Output `add/update/archive/manual_review/sync_manifest` actions with evidence.
4. When `legacy_sources.enabled=true`, emit legacy actions (`legacy_manual_review` in audit, `migrate_legacy/archive_legacy` in migration mode).
5. Include fine-grained capabilities when signals/goals require them (`incident.response`, `security.posture`, `compliance.controls`).

### `apply-safe`

Goal: apply low-risk updates.

Typical actions:
1. Add missing required docs.
2. Append required sections in managed docs using policy language.
3. Upsert missing doc metadata (`doc-owner`, `doc-last-reviewed`, `doc-review-cycle-days`) for managed markdown docs.
4. Never hard-delete documents.

### `apply-with-archive`

Goal: migrate/cleanup mature repositories.

Typical actions:
1. Run all `apply-safe` behaviors.
2. Move stale docs into `docs/archive/` (never direct delete).
3. When `legacy_sources.enabled=true`, migrate legacy files into SoR docs then archive to `docs/archive/legacy/**`.

## Standard Execution Flow

Use this section as orchestration guidance. Keep full executable command recipes in `references/workflow_examples.md`.

1. Define roots and run the preflight check command from `Path Conventions`.

2. Choose workflow mode from decision tree (`bootstrap`, `audit`, `apply-safe`, `apply-with-archive`).
3. Execute the corresponding recipe from `references/workflow_examples.md`.
4. In CI pipelines, run only `audit` and `validate`; route any apply flow through PR.
5. For scheduled maintenance, run `doc_garden.py` recipe from `references/workflow_examples.md`.

## Reference Loading Rules

Load only the reference file needed by the current task:

- Policy boundaries, language lock, metadata governance: `references/doc_policy_schema.md`.
- Target docs shape, additive evolution, archive rules: `references/doc_manifest_schema.md`.
- Managed-doc semantic slot contract and report input fields: `references/semantic_runtime_report_schema.md`.
- Executable command recipes for bootstrap/migration/CI/gardening: `references/workflow_examples.md`.

Release-quality evidence is maintainer-only process data and should live outside the runtime skill folder (for example CI artifacts or maintainer workspace docs).

## Required Guardrails

- Keep source-of-record content in `docs/`, not in `AGENTS.md`.
- Treat `AGENTS.md` as navigation and execution guardrails only.
- Require `reason + evidence` for every non-keep action.
- Convert delete intent into archive moves under `docs/archive/`.
- Never auto-overwrite protected paths (default includes `docs/adr/**`).
- Emit `TODO` or `UNKNOWN` when facts are uncertain.
- In CI, allow `audit`/`validate`; route `apply` through PR workflow.
- Keep manifest evolution additive by default (`manifest_evolution.allow_additive=true`) to avoid contract churn.
- Use `doc_goals` and `adaptive_manifest_overrides` to steer capability decisions explicitly.
- Keep ownership/freshness metadata checks enabled via `doc_metadata`; stale docs should be reviewed instead of silently ignored.
- Use `doc_gardening` policy defaults for automation behavior and reports.
- Use narrow `legacy_sources.include_globs`; avoid enabling broad repository-wide legacy scans without review.

## Runtime Components

Primary entrypoints:

- `scripts/repo_scan.py`: collect codebase facts.
- `scripts/doc_plan.py`: build deterministic action plan.
- `scripts/doc_apply.py`: apply mode-gated actions with language lock.
- `scripts/doc_validate.py`: validate required structure, links, drift, and metadata freshness.
- `scripts/doc_garden.py`: run scan/plan/apply/validate as one automation task and emit gardening reports.

Supporting components (usually invoked transitively by primary entrypoints; call directly only for targeted debugging or CI checks):

- `scripts/doc_capabilities.py`: derive doc capability profile and required document targets from facts/policy goals.
- `scripts/doc_spec.py`: centralize section/spec contracts used by plan/apply/validate.
- `scripts/doc_topology.py`: compute section topology and deterministic section ordering.
- `scripts/doc_synthesize.py`: synthesize section-level actions and content candidates from facts/spec.
- `scripts/doc_semantic_runtime.py`: ingest semantic runtime reports and map entries to managed-doc slots.
- `scripts/doc_quality.py`: evaluate managed-doc quality checks and progressive slot coverage.
- `scripts/doc_agents.py`: generate and update `AGENTS.md` navigation content under policy gates.
- `scripts/doc_agents_validate.py`: validate `AGENTS.md` guardrail and topology constraints.
- `scripts/doc_metadata.py`: parse and upsert ownership/freshness metadata.
- `scripts/doc_legacy.py`: resolve legacy migration policy, path mapping, and migration registry helpers.
- `scripts/language_profiles.py`: language templates, marker aliases, and policy language helpers.

## On-Demand References

- `references/doc_policy_schema.md`: policy contract.
- `references/doc_manifest_schema.md`: target structure contract.
- `references/semantic_runtime_report_schema.md`: semantic runtime input contract for slot filling.
- `references/workflow_examples.md`: bootstrap/migration/CI examples.

## Examples

Full runnable examples live in `references/workflow_examples.md`.

Example intents:
1. Bootstrap with default Chinese: "为这个新仓库生成 docs 基线并加上最小 AGENTS 导航。"
2. Bootstrap with explicit English: "初始化 docs，并把主描述语言改成英文。"
3. CI drift gate: "把文档漂移作为 PR 的必过检查。"

## Maintainer Release Validation (Out of Runtime Scope)

Run this protocol before publishing or updating the skill. Store evidence outside the runtime skill folder (for example CI artifacts or maintainer workspace documentation).

1. Trigger matrix gate: keep at least 20 cases across positive/negative/paraphrase and require zero `FAIL`.
2. Functional gate: record bootstrap baseline, bootstrap with explicit language, and one-command `doc_garden.py` runs.
3. Failure-path gate: record missing plan file failure, invalid plan parse failure, and drift gate failure (`doc_garden --apply-mode none --fail-on-drift`).
4. Efficiency gate: compare `with skill` vs `without skill` on same repository class and record `command_count`, `retries`, `clarification_turns`, `completion_turns`, `wall_time_seconds`.
5. Release decision: mark accepted only when trigger/functional/failure/efficiency are all `PASS`.

## Troubleshooting

### Symptom -> Checks -> Recovery: plan file not found

Symptom: script exits with `Plan file not found`.

Checks:
1. Confirm `--plan` points to an existing `.json` file.
2. Confirm the plan path matches current `--root`.

Recovery:
1. Run `doc_plan.py` to regenerate the plan file.
2. Rerun `doc_apply.py` with the regenerated plan path.

### Symptom -> Checks -> Recovery: language override not taking effect

Symptom: passing `--init-language` does not change output language.

Checks:
1. Inspect `docs/.doc-policy.json` and verify `language.locked`.
2. Check `language.primary` and `language.profile` in policy.

Recovery:
1. If locked by design, keep current language.
2. Change policy language only in explicit migration workflow.

### Symptom -> Checks -> Recovery: invalid plan file

Symptom: `doc_apply.py` reports plan load error.

Checks:
1. Confirm `docs/.doc-plan.json` exists.
2. Run `doc_plan.py` again in `audit` mode.
3. Verify JSON syntax in policy/manifest files.

Recovery:
1. Regenerate plan from fresh repo scan.
2. Rerun apply using the new plan.

### Symptom -> Checks -> Recovery: protected file not updated

Symptom: expected update skipped.

Checks:
1. Inspect `protect_from_auto_overwrite` in policy.
2. Inspect action `risk` and `type` in plan.

Recovery:
1. Keep file protected and perform manual PR update.
2. If policy change is justified, update policy and rerun `audit`.
