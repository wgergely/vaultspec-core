---
tags:
  - '#plan'
  - '#test-project-removal'
date: 2026-04-12
related:
  - '[[2026-04-12-test-project-removal-adr]]'
  - '[[2026-04-12-test-project-removal-research]]'
---

# `test-project-removal` implementation plan

Phased plan to delete `test-project/` from `vaultspec-core`, replace it with a synthetic vault generator lifted from `vaultspec-rag`, refactor every dependent test, and bundle the issue `#67` housekeeping deletions in the same PR. Grounded in the accepted ADR.

## Proposed Changes

The accepted ADR mandates: lift `synthetic.py` from the sibling `vaultspec-rag` repo into `src/vaultspec_core/testing/synthetic.py` (no attribution, no runtime dependency), extend it with 14 named pathology presets and a `named_docs` parameter, introduce a `tmp_path_factory`-backed `synthetic_vault` pytest fixture, refactor nine consumer test modules to use it, delete the `_vault_snapshot_reset` git-checkout smell from `tests/conftest.py`, and bundle the issue `#67` housekeeping deletions (`test-project/`, `rsc/`, `.geminiignore`, `extension.toml`) along with the precise `.gitignore` and `.pre-commit-config.yaml` cleanups required for the deletions to land cleanly. The refactor must leave zero git remnant after any test run, zero mocks/stubs/skips, and pass the full pytest suite plus `prek` and `ty` gates.

## Tasks

### Phase 1 - Lift and extend the synthetic vault generator

1. **Step 1.1 - Create the `testing` subpackage**. Create `src/vaultspec_core/testing/__init__.py` re-exporting the public API (`build_synthetic_vault`, `build_multi_project_fixture`, `CorpusManifest`, `GeneratedDoc`, and the `Pathology` enum / string-flag set). Confirm the package is picked up by Hatchling without changes to `pyproject.toml`.

1. **Step 1.2 - Lift the upstream module verbatim**. Copy `synthetic.py` from `wgergely/vaultspec-rag/src/vaultspec_rag/synthetic.py` (HEAD) into `src/vaultspec_core/testing/synthetic.py`. No attribution comment, no `vaultspec-rag` dependency added to `pyproject.toml`. The file uses stdlib only (`random`, `dataclasses`, `pathlib`).

1. **Step 1.3 - Drop `include_malformed`**. Remove the `include_malformed` flag and the `_add_malformed_docs` helper since this repo has no callers to keep alive. The replacement is the new `pathologies` parameter introduced in the next step.

1. **Step 1.4 - Add the `pathologies` parameter and the 14 presets**. Extend `build_synthetic_vault` with a `pathologies: Iterable[str] | None = None` parameter and implement each preset as a private helper that mutates the generated corpus after the well-formed pass:

   - `dangling`, `orphan`, `missing_frontmatter`, `wrong_directory_tag`, `stale_index`, `cycle`, `wrong_tag_count`, `stem_collision`, `phantom_only_links`, `invalid_date_format`, `malformed_related_entry`, `body_link`, `bad_filename`, `unreferenced_research`.
     Each preset returns the affected `GeneratedDoc`(s) which are recorded on the manifest under a new `pathologies: dict[str, list[GeneratedDoc]]` field so tests can assert on the exact docs that were broken without hardcoding paths.

   Each preset must additionally record any pathology-specific detail the consumer tests need to assert on, via a new `pathology_details: dict[str, Any]` field on `CorpusManifest`. Specifically:

   - `dangling` records `{"target_stem": "<the injected broken wiki-link stem>", "source_path": <Path>}` per affected doc, so `test_fix_removes_related_entry` can assert the specific broken target was removed without hardcoding `[[event-handling-guide]]`.
   - `phantom_only_links` records `{"plan_doc": <GeneratedDoc>, "phantom_targets": [list of phantom stems]}` so `test_check_schema_ignores_phantom_adr_references` can look up the phantom-only plan via the manifest without hardcoding `2026-02-04-displaymap-integration-plan`.
   - `stem_collision` records the colliding stem and the two doc paths.
   - `cycle` records the ordered cycle node list.
     The manifest schema is part of the public API of the lifted module and the self-tests in Step 1.8 enforce the presence of these fields.

1. **Step 1.5 - Add the `named_docs` parameter**. Extend `build_synthetic_vault` with `named_docs: dict[str, str] | None = None` mapping a logical key to a literal filename stem (e.g. `{"editor_demo_adr": "2026-02-05-editor-demo-architecture-adr"}`). The generator emits these docs in addition to the per-type baseline so tests like `test_scanner.py` can ask for specific filenames without coupling the whole corpus to them.

   **Critical: named docs must participate in the wiki-link graph.** The injection pass for `named_docs` runs before the edge-building pass so each named doc has a non-zero probability of receiving inbound and outbound edges per the configured `graph_density`. A named doc with zero edges would silently break `test_graph.py::test_out_links_populated` and `test_in_links_populated`. The generator must wire each named doc into the graph as a first-class node, not as an isolated post-pass addition. The manifest exposes named docs via `manifest.named_docs: dict[str, GeneratedDoc]` so consumers look them up by logical key rather than by literal stem.

   The doc type for each named doc is inferred from the stem suffix (`-adr`, `-plan`, `-research`, `-reference`, `-audit`) and the doc is placed in the corresponding `.vault/<type>/` subdirectory. If the stem suffix is ambiguous, the caller must pass an explicit `doc_type` via a tuple form `(stem, doc_type)`.

1. **Step 1.6 - Add the `feature_names` parameter**. Add `feature_names: list[str] | None = None` so callers can override the default `FEATURES` list. `test_graph.py` requires a feature literally named `editor-demo`; this is how it requests one.

1. **Step 1.7 - Confirm `graph_density` default**. Verify the default is non-zero (upstream uses `0.3`) so `test_graph.py::test_networkx_digraph_has_edges` passes against the baseline corpus. Document the constraint inline in the docstring.

1. **Step 1.8 - Synthetic-generator self-tests**. Add `src/vaultspec_core/testing/tests/test_synthetic.py` covering:

   - Deterministic output for a fixed seed (same seed -> identical corpus).
   - Tag-taxonomy compliance of every well-formed doc (exactly two tags, ISO date, quoted wiki-links).
   - Each pathology produces at least one affected doc and records it in `manifest.pathologies`.
   - `dangling` pathology records `target_stem` and `source_path` in `manifest.pathology_details["dangling"]`.
   - `phantom_only_links` pathology records the affected plan doc and its phantom target list in `manifest.pathology_details["phantom_only_links"]`.
   - `named_docs` produces the requested filenames in the correct doc-type subdirectory.
   - Each named doc participates in the wiki-link graph: with `graph_density >= 0.3`, every named doc has at least one inbound or outbound edge across a sufficient seed sample.
   - `feature_names` overrides the default `FEATURES` list.
   - Interaction between `pathologies` and `named_docs`: a named doc may also be the target of a pathology (e.g. `cycle` may include a named doc) without breaking the manifest invariants.
   - `build_multi_project_fixture` produces non-overlapping doc stems across projects and independent root paths.
     These tests guard the factory itself against regression and are the structural enforcement of the manifest schema being part of the public API.

### Phase 2 - Pytest fixture wiring and the conftest smell

1. **Step 2.1 - Delete `_vault_snapshot_reset` and dead helpers**. From `tests/conftest.py`:

   - Remove the session-scoped `_vault_snapshot_reset` fixture and the `subprocess.run(["git", "checkout", "--", "test-project/.vault/"], ...)` block at lines 31-39.
   - Remove the dead `_cleanup_test_project` helper at lines 20-28. It is never registered as a fixture and references the deleted directory structure.
   - Remove the `import subprocess` statement (now orphaned).
   - Remove the `PROJECT_ROOT` import from `tests.constants` if no remaining code in `tests/conftest.py` references it after the deletions. Verify with a final read of the file before moving on; leaving an orphaned import would fail the `ruff` gate via `prek`.

1. **Step 2.2 - Introduce the baseline `synthetic_vault` fixture**. Add a session-scoped `synthetic_vault` fixture in `tests/conftest.py` that calls `build_synthetic_vault(tmp_path_factory.mktemp("vault"), n_docs=24, seed=42)` and yields the `CorpusManifest`. This is the read-only baseline shared across tests that do not need pathologies.

1. **Step 2.3 - Introduce the `synthetic_project` fixture**. Add a function-scoped `synthetic_project` fixture in `src/vaultspec_core/tests/cli/conftest.py` that builds a synthetic vault under `tmp_path` and runs the `WorkspaceFactory(tmp_path).install()` step on top, returning a small dataclass exposing `path`, `manifest`, and `factory`. This is the replacement for the current `test_project` fixture (which copies the real `test-project/` corpus).

1. **Step 2.4 - Delete `tests/constants.py` corpus constants**. Remove `TEST_PROJECT` and `TEST_VAULT` from `tests/constants.py`. Leave the file in place if other constants exist; otherwise delete the file. Run a grep across `src/` and `tests/` afterwards to confirm no straggling import remains.

### Phase 3 - Refactor the consumer test modules

Each step refactors one module. After each step the test file must pass in isolation before moving on; this keeps the blast radius bounded.

1. **Step 3.1 - `src/vaultspec_core/tests/cli/conftest.py`**. Replace `_TEST_PROJECT_SRC` and the `test_project` fixture with the `synthetic_project` fixture from Step 2.3. Update any helper functions that previously copied from the real corpus.

1. **Step 3.2 - `src/vaultspec_core/tests/cli/test_cli_live.py`**. Remove the inline `_TEST_PROJECT_SRC` constant (line 28) and the local `project` fixture (line 35). Update all 50+ tests in the file to request `synthetic_project` from `conftest.py`. Tests that asserted on specific corpus filenames are rewritten to assert on `manifest.docs[*].path` properties or to request the filename explicitly via `named_docs`.

1. **Step 3.3 - `src/vaultspec_core/tests/cli/test_integration.py` and `test_main_cli.py`**. Swap direct `test_project` references for `synthetic_project`. These tests care about CLI plumbing, so the smallest useful corpus is fine - the baseline 24-doc fixture is sufficient.

1. **Step 3.3b - `src/vaultspec_core/tests/cli/test_collectors.py`**. This file requests the `test_project` fixture by name in multiple tests (lines 136, 202, 207, 214, 287, 302, and others). After Step 3.1 renames the fixture to `synthetic_project`, every reference here will fail with "fixture not found". Rename each `test_project` parameter to `synthetic_project` and confirm the tests still exercise the same collector behaviour against the synthetic corpus. If any test asserts on a specific historical filename, route it through `named_docs` the same way `test_scanner.py` does.

1. **Step 3.4 - `src/vaultspec_core/vaultcore/tests/test_scanner.py`**. Replace `TEST_PROJECT` with a fixture that calls `build_synthetic_vault` with `named_docs={"adr": "2026-02-05-editor-demo-architecture-adr", "plan": "2026-02-05-editor-demo-phase1-plan", "research": "2026-02-05-editor-demo-research", "reference": "2026-02-05-editor-demo-core-reference"}`. The test assertions on those filenames keep their literal form.

1. **Step 3.5 - `src/vaultspec_core/vaultcore/tests/test_query.py`**. Replace `TEST_PROJECT` with a synthetic vault sized to satisfy `list_documents`, `get_stats`, and filter assertions. Add `dangling` and `orphan` pathologies if any test asserts on them.

1. **Step 3.6 - `src/vaultspec_core/vaultcore/checks/tests/conftest.py`**. Replace the `vault_root` fixture so it returns a freshly generated synthetic vault root instead of `TEST_PROJECT`.

1. **Step 3.7 - `src/vaultspec_core/vaultcore/checks/tests/test_dangling.py`**. Request a synthetic vault with the `dangling` pathology preset. Replace the hardcoded path `2026-02-04-editor-event-handling/2026-02-04-editor-event-handling-execution-summary.md` with `manifest.pathologies["dangling"][0].path`. Replace the hardcoded broken target string `[[event-handling-guide]]` with `manifest.pathology_details["dangling"][0]["target_stem"]` (wrapped in `[[ ]]` if the test asserts on the wiki-link form). Keep the test that runs the fix path against an isolated tmp_path copy - it is already correct, only its corpus source changes. Confirm the synthetic generator produces the `exec/<feature>/` subdirectory shape that `check_dangling`'s fix path needs.

1. **Step 3.8 - `src/vaultspec_core/vaultcore/checks/tests/test_index_safety.py`**. **Verified by ADR review: NO REFACTOR REQUIRED**. Every test in this file already uses synthetic `VaultSnapshot` objects with `Path("/fake/root")`. Skip this file.

1. **Step 3.9 - `src/vaultspec_core/metrics/tests/conftest.py` and `test_metrics.py`**. Replace the `TEST_PROJECT`-backed `vault_root` fixture with a synthetic equivalent. Where assertions hardcode counts like `total_docs > 80`, parameterise the fixture to produce a corpus of that size at the call site rather than depending on whatever the historical corpus happened to contain.

1. **Step 3.10 - `src/vaultspec_core/graph/tests/conftest.py` and `test_graph.py`**. Replace `TEST_PROJECT` with a synthetic vault built with:

   - `feature_names=["editor-demo", "displaymap-integration", ...]` so the literal feature assertions at lines 257-305 keep working without rewrite.
   - `named_docs={"editor_demo_adr": "2026-02-05-editor-demo-architecture-adr", "editor_demo_research": "2026-02-05-editor-demo-research"}` so the node-lookup assertions at lines 178-220 (`graph.nodes["2026-02-05-editor-demo-architecture-adr"]`), 219 (`graph.nodes.get("2026-02-05-editor-demo-research")`), 233 (`test_get_node_existing`), and 314 (`test_neighbors_out`) keep working. Because Step 1.5 wires named docs into the graph before the edge-building pass, the assertions at lines 215 (`test_out_links_populated`) and 221 (`test_in_links_populated`) on the named research doc are satisfied.
   - `pathologies=["cycle", "orphan", "stem_collision", "phantom_only_links"]` to power the tests at lines 124-144 (`test_colliding_stems_get_qualified_keys`, `test_stem_index_maps_collisions`) and 576-594 (`test_check_schema_ignores_phantom_adr_references`).
   - A non-zero `graph_density` (default `0.3`).

   For `test_check_schema_ignores_phantom_adr_references` (line 576), rewrite the test to look up the phantom-only-links plan via `manifest.pathology_details["phantom_only_links"][0]["plan_doc"]` instead of hardcoding `2026-02-04-displaymap-integration-plan`. This is the cleaner of the two options because the literal stem is incidental to the test's intent (it asserts on phantom-link handling, not on the specific plan name).

1. **Step 3.11 - Cross-tree `TEST_PROJECT` sweep**. After all per-module steps, grep `src/` and `tests/` for `TEST_PROJECT`, `TEST_VAULT`, `_TEST_PROJECT_SRC`, and `test-project` (case-insensitive). Anything remaining is an unintentional leftover and must be addressed before phase 4.

### Phase 4 - Housekeeping deletions

1. **Step 4.1 - Delete `test-project/`**. Run `git rm -r test-project/`. Verify the working tree no longer contains it.

1. **Step 4.2 - Edit `.gitignore`**. Delete the existing block at lines 187-189 (`test-project/*`, `!test-project/.vault/`, `!test-project/README.md`) and replace it with a single defensive line `test-project/`.

1. **Step 4.3 - Edit `.pre-commit-config.yaml`**. Remove the `exclude: ^test-project/` line from the `mdformat-check` hook (line 39) and from the `pymarkdown` hook (line 47). With `test-project/` deleted these excludes are dangling and would silently mask future issues.

1. **Step 4.4 - Delete `rsc/`**. Run `git rm -r rsc/`. The directory contains three unreferenced SVG files confirmed dead by both research and ADR review.

1. **Step 4.5 - Delete `.geminiignore`**. Run `git rm .geminiignore`. The file is 0 bytes and referenced nowhere.

1. **Step 4.6 - Delete `extension.toml`**. Run `git rm extension.toml`. The user has explicitly approved this. The only references are in `CHANGELOG.md` (historical commit message) and `.vault/` ADR/plan archives, neither of which require updates.

1. **Step 4.7 - Clean `.dockerignore`**. Remove the `test-project` entry from `.dockerignore` line 10. After `test-project/` is deleted from the working tree this entry is dead weight and silently misleads any reader about the repo layout.

### Phase 5 - Validation gate

1. **Step 5.1 - Full pytest run**. `uv run --no-sync pytest`. The full suite must pass with zero failures, zero new skips, zero new xfails, and zero new warnings introduced by this work.

1. **Step 5.2 - Pre-commit gate**. `uv run --no-sync prek run --all-files`. Must be clean across the modified file set and the rest of the repo.

1. **Step 5.3 - Type check**. `uv run --no-sync python -m ty check src/vaultspec_core`. Must be clean. Note this is the form used in `.pre-commit-config.yaml` and `justfile`; an unscoped `ty check` will not work.

1. **Step 5.4 - Repository hygiene checks**. Run the following and confirm each returns no output:

   - `git ls-files test-project rsc .geminiignore extension.toml`
   - `grep -rn TEST_PROJECT src/ tests/`
   - `grep -rn "test-project" src/ tests/`
   - `grep -n "test-project" .dockerignore .gitignore`
   - `grep -n "test-project" .pre-commit-config.yaml`
     Also confirm `tests/conftest.py` no longer contains `_vault_snapshot_reset`, `_cleanup_test_project`, `import subprocess`, or any `git checkout` shellout.

1. **Step 5.5 - Working-tree git remnant check**. Run the full pytest suite a second time and then run `git status`. Any modified or untracked file under `src/`, `tests/`, or the repo root means a test left a remnant; this is a hard fail and must be hunted down before proceeding.

## Parallelization

Phase 1 is sequential because every step builds on the previous one (`__init__.py` -> module copy -> drop flag -> add params -> self-tests). Phase 2 must follow phase 1 because the fixtures import from the new module. Phase 3 steps 3.1 through 3.10 are largely independent and can be parallelised across sub-agents if the executor supports it; phase 3.11 is the join point. Phase 4 must follow phase 3 (the deletions break any test that still imports `TEST_PROJECT`). Phase 5 is the final gate and runs after every other phase.

The lowest-risk serial path is: phase 1 -> phase 2 -> phase 3 in module order (3.1 -> 3.10) -> 3.11 sweep -> phase 4 -> phase 5. The parallel optimisation in phase 3 is optional and only worthwhile if the executor framework can run isolated test files concurrently without sharing the synthetic vault state between them.

## Verification

Mission success is defined by the ADR's validation gate, reproduced here as concrete pass criteria:

- The full `uv run --no-sync pytest` suite passes with no new skips, xfails, or warnings.
- `uv run --no-sync prek run --all-files` is clean.
- `uv run --no-sync python -m ty check src/vaultspec_core` is clean.
- `git ls-files test-project rsc .geminiignore extension.toml` returns nothing.
- `grep -rn TEST_PROJECT src/ tests/` returns nothing.
- `grep -rn "test-project" src/ tests/` returns nothing outside historical `.vault/` archives.
- `tests/conftest.py` contains no `_vault_snapshot_reset` and no `git checkout` shellout.
- After a full pytest run, `git status` shows no modified or untracked files anywhere in the working tree. This is the structural enforcement of the "no git remnant" mandate.
- `from vaultspec_core.testing import build_synthetic_vault` resolves at import time.
- The synthetic-generator self-tests in `src/vaultspec_core/testing/tests/test_synthetic.py` pass and exercise every named pathology at least once.

Beyond automated tests, the human reviewer should spot-check that:

- No test file contains an inline `TEST_PROJECT`-style constant or any path string referencing `test-project/`.
- No fixture mutates state outside its own `tmp_path`.
- No pathology preset is silently a no-op (each one must produce at least one affected doc and record it on the manifest).
- The lifted `synthetic.py` produces frontmatter that conforms to the vaultspec tag taxonomy (exactly two tags: one directory tag plus one feature tag, ISO date, quoted wiki-links in `related:`).

Tests can be cheated by trivially producing assertions that always pass; the self-tests in Step 1.8 are the safeguard against the synthetic generator drifting out of taxonomy compliance.
