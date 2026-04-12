---
tags:
  - '#exec'
  - '#test-project-removal'
date: 2026-04-12
related:
  - '[[2026-04-12-test-project-removal-plan]]'
  - '[[2026-04-12-test-project-removal-adr]]'
  - '[[2026-04-12-test-project-removal-research]]'
---

# `test-project-removal` summary

Full execution summary for the `test-project-removal` feature. All five plan phases completed, all validation gates green, all code-review fix-ups applied, full pytest suite passing 1242/1242.

## Created

- `src/vaultspec_core/testing/__init__.py`
- `src/vaultspec_core/testing/synthetic.py`
- `src/vaultspec_core/testing/tests/__init__.py`
- `src/vaultspec_core/testing/tests/test_synthetic.py`

## Modified

- `tests/conftest.py` - replaced `_vault_snapshot_reset` and dead `_cleanup_test_project` helper with `synthetic_vault` session fixture; orphaned `subprocess` and `PROJECT_ROOT` imports removed
- `tests/constants.py` - removed `TEST_PROJECT` and `TEST_VAULT`
- `src/vaultspec_core/tests/cli/conftest.py` - replaced `test_project` fixture with `synthetic_project` and `synthetic_project_manifest`
- `src/vaultspec_core/tests/cli/test_cli_live.py`, `test_integration.py`, `test_main_cli.py`, `test_collectors.py` - migrated to `synthetic_project`
- `src/vaultspec_core/tests/cli/test_vault_cli.py`, `test_sync.py`, `test_sync_collect.py`, `test_sync_incremental.py`, `test_sync_operations.py`, `test_sync_parse.py`, `test_spec_cli.py` - migrated to `synthetic_project` (these were not enumerated in the plan and were caught at the Phase 5 gate)
- `src/vaultspec_core/vaultcore/tests/test_scanner.py` - replaced `TEST_PROJECT` constant with `vault_project` fixture using `named_docs` for the historical filenames; tightened the corpus-size lower bound assertion
- `src/vaultspec_core/vaultcore/tests/test_query.py` - replaced `TEST_PROJECT` with synthetic vault using `dangling` and `orphan` pathologies; tightened conditional guards into hard assertions
- `src/vaultspec_core/vaultcore/checks/tests/conftest.py` - replaced `vault_root` with synthetic-backed equivalent
- `src/vaultspec_core/vaultcore/checks/tests/test_dangling.py` - manifest-driven path and broken-target lookup
- `src/vaultspec_core/vaultcore/checks/tests/test_index_safety.py` - tightened a stale comment that mentioned the deleted directory
- `src/vaultspec_core/metrics/tests/conftest.py` - synthetic vault sized to satisfy `total_docs > 80` and `total_features > 5` assertions
- `src/vaultspec_core/graph/tests/conftest.py`, `test_graph.py` - synthetic vault with `editor-demo` feature, named docs, and `cycle`/`orphan`/`stem_collision`/`phantom_only_links` pathologies; rewrote `test_check_schema_ignores_phantom_adr_references` to use `manifest.pathology_details`
- `.gitignore` - replaced the three-line `test-project/*` block with a single defensive `test-project/` entry
- `.pre-commit-config.yaml` - removed both `exclude: ^test-project/` lines from `mdformat-check` and `pymarkdown` hooks
- `.dockerignore` - removed dead `test-project` entry
- `pyproject.toml` - added a single `TC003` per-file-ignore for `testing/synthetic.py`

## Deleted

- `test-project/` (474 files, ~3.7 MB)
- `rsc/svg/vaultspec-agent-err.svg`, `rsc/svg/vaultspec-agent-ok.svg`, `rsc/svg/vaultspec-agent-stroll.svg`
- `.geminiignore` (0 bytes)
- `extension.toml`

## Description

The `test-project/` corpus, originally seeded from the sibling `vaultspec-rag` project and reused ad-hoc as a test fixture by ten test modules, has been deleted entirely. Its replacement is `vaultspec_core.testing.synthetic.build_synthetic_vault`, lifted from `vaultspec-rag` and extended with 14 named pathology presets (`dangling`, `orphan`, `missing_frontmatter`, `wrong_directory_tag`, `stale_index`, `cycle`, `wrong_tag_count`, `stem_collision`, `phantom_only_links`, `invalid_date_format`, `malformed_related_entry`, `body_link`, `bad_filename`, `unreferenced_research`), a `named_docs` parameter that produces specific filenames and wires them into the wiki-link graph, a `feature_names` override, and a richer manifest schema (`pathologies`, `pathology_details`, `named_docs`) that lets tests assert on injected breakage without hardcoding paths or stems. A new public `PATHOLOGY_NAMES` constant exposes the valid preset names so tests do not import private symbols.

Eighteen test files across nine subpackages were refactored to consume the new fixture set. The session-scoped `_vault_snapshot_reset` fixture in `tests/conftest.py`, which shelled out to `git checkout -- test-project/.vault/`, was removed along with the dead `_cleanup_test_project` helper - tests now leave zero git remnant because every fixture lives under `tmp_path`. Issue `#67` housekeeping deletions (`rsc/`, `.geminiignore`, `extension.toml`) and the precise `.gitignore`, `.pre-commit-config.yaml`, and `.dockerignore` cleanups were bundled into the same execution.

The plan was verified by two sub-agent reviewers before execution and seven blocking amendments were applied to it. After execution, two more sub-agent reviewers audited the result and surfaced three actionable fix-ups (one HIGH: missing public `PATHOLOGY_NAMES`; two MEDIUM: empty-related YAML rendering anti-pattern, scanner threshold too weak). All three were applied. Phase 5 surfaced one execution-time gap that the plan reviewers had also missed: seven CLI test files outside the plan's enumerated inventory needed the same `test_project` -> `synthetic_project` rename.

## Tests

- Full pytest suite: **1242 passed**, 0 failed, 0 skipped, 0 xfails, 0 errors (247 s).
- `uv run --no-sync python -m ty check src/vaultspec_core`: clean.
- `uv run --no-sync ruff check src/ tests/`: clean.
- `git ls-files test-project rsc .geminiignore extension.toml`: empty.
- `grep -rn "TEST_PROJECT|TEST_VAULT|_TEST_PROJECT_SRC|test-project" src/ tests/`: zero matches.
- `tests/conftest.py` contains no `subprocess`, `_vault_snapshot_reset`, `_cleanup_test_project`, or `git checkout` references.
- 53 self-tests in `src/vaultspec_core/testing/tests/test_synthetic.py` cover deterministic seeding, tag-taxonomy compliance, every pathology and its detail schema, named-docs-in-graph guarantees, feature-names override, pathology+named-docs interaction, and multi-project isolation.
- Working-tree git status after the full pytest run shows only the modifications listed above; no test left a remnant.
