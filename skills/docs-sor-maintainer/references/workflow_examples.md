# workflow examples

## Table of Contents

- [Shared path setup (required)](#shared-path-setup-required)
- [Example A: bootstrap empty repo (adaptive minimal baseline, default Chinese)](#example-a-bootstrap-empty-repo-adaptive-minimal-baseline-default-chinese)
- [Example B: bootstrap with explicit language](#example-b-bootstrap-with-explicit-language)
- [Example C: additive evolution on existing repo](#example-c-additive-evolution-on-existing-repo)
- [Example D: force fixed baseline during bootstrap](#example-d-force-fixed-baseline-during-bootstrap)
- [Example E: mature repo migration with archive](#example-e-mature-repo-migration-with-archive)
- [Example F: CI drift check](#example-f-ci-drift-check)
- [Example G: Doc Gardening automation task](#example-g-doc-gardening-automation-task)
- [Example H: legacy migration and centralized archive](#example-h-legacy-migration-and-centralized-archive)
- [CI recommendation](#ci-recommendation)

## Shared path setup (required)

```bash
REPO_ROOT="/repo"
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
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --help >/dev/null
```

## Example A: bootstrap empty repo (adaptive minimal baseline, default Chinese)

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode bootstrap --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_apply.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan.json" --mode bootstrap
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --fail-on-drift --fail-on-freshness
```

Expected shape for tiny repo:

- required files: `docs/index.md`
- required dirs: none
- optional files: none

## Example B: bootstrap with explicit language

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode bootstrap --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_apply.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan.json" --mode bootstrap --init-language en-US
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --fail-on-drift --fail-on-freshness
```

## Example C: additive evolution on existing repo

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode audit --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_apply.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan.json" --mode apply-safe
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --fail-on-drift --fail-on-freshness
```

Expected behavior:

- if repo gains new signals (entrypoints, CI, module growth), plan includes `sync_manifest` and adds only newly required docs.
- manifest is evolved additively; existing contracts are preserved.

## Example D: force fixed baseline during bootstrap

```bash
# set docs/.doc-policy.json -> bootstrap_manifest_strategy: fixed
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode bootstrap --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan.json"
```

Expected behavior:

- bootstrap uses the fixed manifest template (index + architecture + runbook + exec-plans + tech-debt + glossary).

## Example E: mature repo migration with archive

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode apply-with-archive --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_apply.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan.json" --mode apply-with-archive
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --fail-on-drift --fail-on-freshness
```

## Example F: CI drift check

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode audit --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --fail-on-drift --fail-on-freshness
```

## Example G: Doc Gardening automation task

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_garden.py" \
  --root "$REPO_ROOT" \
  --apply-mode apply-safe \
  --fail-on-drift \
  --fail-on-freshness
```

Expected behavior:

- execute scan -> plan -> apply -> validate in one task.
- write report files (`docs/.doc-garden-report.json`, `docs/.doc-garden-report.md`).
- exit non-zero if drift/freshness gate fails.

## Example H: legacy migration and centralized archive

```bash
# set docs/.doc-policy.json -> legacy_sources.enabled=true and define include_globs/exclude_globs
"$PYTHON_BIN" "$SKILL_DIR/scripts/repo_scan.py" --root "$REPO_ROOT" --output "$REPO_ROOT/docs/.repo-facts.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_plan.py" --root "$REPO_ROOT" --mode apply-with-archive --facts "$REPO_ROOT/docs/.repo-facts.json" --output "$REPO_ROOT/docs/.doc-plan.json"
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_apply.py" --root "$REPO_ROOT" --plan "$REPO_ROOT/docs/.doc-plan.json" --mode apply-with-archive
"$PYTHON_BIN" "$SKILL_DIR/scripts/doc_validate.py" --root "$REPO_ROOT" --fail-on-drift --fail-on-freshness
```

Expected behavior:

- legacy files matched by policy globs are migrated to SoR target docs.
- source files are archived under `docs/archive/legacy/**` (no hard delete).
- migration status is tracked in `docs/.legacy-migration-map.json`.

## CI recommendation

- Block merge when drift exists or stale docs exceed review cycle.
- Let bot open PRs for `apply-safe` fixes.
- Do not push direct doc rewrites from CI to default branch.
