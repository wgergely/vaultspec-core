---
tags:
  - '#adr'
  - '#test-project-removal'
date: 2026-04-12
related:
  - '[[2026-04-12-test-project-removal-research]]'
---

# `test-project-removal` adr: `synthetic-vault-fixture-and-housekeeping` | (**status:** `accepted`)

## Problem Statement

The repository root contains `test-project/`, a 474-file (~3.7 MB) `.vault/` corpus that was originally seeded from the sibling `vaultspec-rag` project and then reused ad-hoc as a shared pytest fixture by ten test modules in `vaultspec-core`. Carrying foreign-project corpus data inside this repo is a structural mistake: it bloats history, couples tests to the artifacts of an unrelated project's lifecycle, and produces a session-scoped `git checkout` reset hack in `tests/conftest.py` that exists solely because some tests mutate the tracked corpus. The directory must be deleted entirely, no committed corpus must replace it, and every dependent test must be rewritten to generate the corpus it needs on-the-fly into a `tmp_path`, run, and auto-clean. The same PR also resolves issue `#67` housekeeping (`rsc/`, `.geminiignore`, `extension.toml`).

## Considerations

The research artifact enumerates ten consumer test modules and characterises what each one actually needs from the corpus: minimum doc counts per type, tag taxonomy, wiki-link graph density, orphans, dangling references, generated `.index.md` files, and feature folders under `exec/`. A synthetic fixture must satisfy the union of these requirements while remaining parameterisable so individual tests can request only the shape they care about.

The sibling repository `vaultspec-rag` has already solved this problem. Its `src/vaultspec_rag/synthetic.py` (~250 LOC, single file, dataclass-based) ships:

- `build_synthetic_vault(root, *, n_docs, include_malformed, graph_density, seed)` returning a `CorpusManifest`
- `build_multi_project_fixture(base, *, n_projects, docs_per_project, seed)` for cross-project scenarios
- `CorpusManifest` and `GeneratedDoc` dataclasses exposing the generated graph, needles, and per-doc metadata for assertions
- Deterministic generation via a seed
- A small `_add_malformed_docs` helper that injects three pathology variants (missing frontmatter, empty body, broken-tags-string)
- A `tmp_path_factory`-backed pytest fixture pattern that produces zero git remnant

The user has approved lifting this module verbatim into `vaultspec-core` with no attribution and no runtime dependency on `vaultspec-rag`. The two copies will diverge as each repo's needs evolve. This eliminates the green-field design risk and lets the work focus on the gap: extending the malformed-doc helper with the additional pathologies the `vaultspec-core` checker tests require (dangling links, orphan documents, missing required frontmatter fields, wrong directory tag, mismatched feature tag count, stale `.index.md` counts, related-graph cycles).

The existing `WorkspaceFactory` at `src/vaultspec_core/tests/cli/workspace_factory.py` handles `.vaultspec/` install/sync state and provider directories. It does not generate `.vault/` corpus and should not be extended to do so; the two factories are orthogonal and tests that need both compose them by passing the same `root`.

The housekeeping items in issue `#67` are independently confirmed by the research: `rsc/svg/*.svg` is unreferenced, `.geminiignore` is a 0-byte file referenced nowhere, and `extension.toml` is an abandoned companion-project manifest with no Python imports - the user has explicitly approved deletion.

## Constraints

- No mocks, patches, stubs, fakes, or skips. Tests must use real filesystem assertions against real generated documents per the project's testing standards.
- No test may mutate any path outside its own `tmp_path`. The `_vault_snapshot_reset` fixture must be deleted, not preserved as a safety net.
- No corpus data may be committed to the repository, including under `tests/fixtures/`. The synthetic generator is the only sanctioned source of corpus for tests.
- The synthetic generator must be importable from production code, not only from tests. The upstream module is consumed by `cli.py handle_quality` in `vaultspec-rag`; the equivalent location in this repo must keep that door open even if no production code imports it on day one.
- Every generated document must conform to the vault tag taxonomy: exactly one directory tag plus exactly one feature tag, valid `date`, valid `related` wiki-links.
- All ten consumer test modules must pass after the refactor. No test may be skipped, deleted, or marked xfail to make the refactor land.
- `pre-commit` (`prek`) and `ty` must pass on every modified file.
- The PR must not rewrite git history; deleting `test-project/` from the working tree and tracking is sufficient. Past commits retain the data.

## Implementation

### Module placement

Lift `synthetic.py` from `vaultspec-rag` into a new subpackage at `src/vaultspec_core/testing/synthetic.py`. Create `src/vaultspec_core/testing/__init__.py` re-exporting the public API (`build_synthetic_vault`, `build_multi_project_fixture`, `CorpusManifest`, `GeneratedDoc`). The `testing` subpackage sits inside the production package so the generator can be imported by both production code (future quality / diagnostic commands) and the test suite, matching the upstream pattern. No attribution comment, no `vaultspec-rag` dependency in `pyproject.toml`.

### Pathology extension

Add a `pathologies` parameter to `build_synthetic_vault` that accepts an iterable of named presets. Drop the upstream `include_malformed` flag entirely since this repo has no callers to break. New named pathologies:

- `dangling` - inject `[[nonexistent-target]]` references into the `related:` field of selected docs
- `orphan` - generate isolated documents with no inbound or outbound links
- `missing_frontmatter` - emit a doc whose body is markdown only, no YAML
- `wrong_directory_tag` - place a doc in `.vault/adr/` tagged `#plan` (and analogues for each type)
- `stale_index` - emit a `<feature>.index.md` whose `related:` count disagrees with the actual file count
- `cycle` - introduce a wiki-link cycle (A -> B -> C -> A) for cycle-detection coverage
- `wrong_tag_count` - emit a doc with one tag, or three+ tags
- `stem_collision` - emit two documents that share an identical filename stem under different type directories (required by `test_graph.py::test_colliding_stems_get_qualified_keys` and `test_stem_index_maps_collisions`)
- `phantom_only_links` - emit a plan whose `related:` entries all point to non-existent target stems (required by `test_graph.py::test_check_schema_ignores_phantom_adr_references`)
- `invalid_date_format` - emit a doc whose `date:` is not ISO 8601 (covers `frontmatter.py` date validation)
- `malformed_related_entry` - emit a doc whose `related:` contains a non-wiki-link string (covers `frontmatter.py` related-entry validation)
- `body_link` - emit a doc whose body contains a wiki-link or filesystem path (covers `body_links.py`)
- `bad_filename` - emit a doc with a non-conforming filename or place a stray file at `.vault/` root (covers `structure.py`)
- `unreferenced_research` - emit a research doc that no plan or ADR links to (covers `references.py`)

Each pathology is a small private function that mutates or augments the generated corpus after the well-formed pass. The `CorpusManifest` exposes a `pathologies` field listing which were applied so tests can assert on injected breakage without hard-coding paths. Where a test needs to know exactly which file was broken, the pathology function returns the affected `GeneratedDoc` and the manifest records it.

### Pytest fixture

Add a `synthetic_vault` fixture in a top-level `tests/conftest.py` (replacing the deleted `_vault_snapshot_reset` block) and module-local conftests where needed. The fixture is built on `tmp_path_factory` and is parameterisable via fixture composition or direct factory calls inside the test:

```python
@pytest.fixture
def synthetic_vault(tmp_path) -> CorpusManifest:
    return build_synthetic_vault(tmp_path, n_docs=24, seed=42)
```

Tests that need pathologies request a specialised fixture or call `build_synthetic_vault` directly with the pathology list. Session-scoped fixtures are reserved for cases where corpus generation is expensive enough to dominate the test run; the upstream `vaultspec-rag` uses session scope for its 24-doc default and that scope is appropriate here too for the read-only baseline corpus.

### Test refactor scope

Each of the ten consumers in Section 1 of the research is rewritten:

- `tests/conftest.py` - delete `_vault_snapshot_reset`; keep any unrelated session fixtures; introduce the `synthetic_vault` baseline.
- `tests/constants.py` - delete `TEST_PROJECT` and `TEST_VAULT` constants. Anything still importing them is a refactor target.
- `src/vaultspec_core/tests/cli/conftest.py` - replace the `_TEST_PROJECT_SRC` copy with `build_synthetic_vault(tmp_path, ...)`. The `test_project` fixture (now misnamed) becomes `synthetic_project` or similar.
- `src/vaultspec_core/tests/cli/test_cli_live.py` - this file declares its own inline `_TEST_PROJECT_SRC` constant (line 28) and its own `project` fixture (line 35) independent of the shared conftest. Both must be removed and replaced with a request for the new `synthetic_project` fixture from `conftest.py`. 50+ tests in this file then run against the synthetic corpus.
- `src/vaultspec_core/tests/cli/test_integration.py` and `test_main_cli.py` - swap direct `test-project` references for the synthetic equivalent. These tests care about CLI plumbing, not corpus shape, so the smallest reasonable corpus is fine.
- `src/vaultspec_core/vaultcore/tests/test_scanner.py` and `test_query.py` - replace `TEST_PROJECT` with a synthetic vault sized to the assertions. Where tests assert on specific filenames (`2026-02-05-editor-demo-architecture-adr.md` and friends), the synthetic generator produces docs with those exact names by accepting an optional `named_docs` parameter; the corpus filenames remain explicit at the call site, not hardcoded across the test files.
- `src/vaultspec_core/vaultcore/checks/tests/conftest.py` and `test_dangling.py` - request a synthetic vault with the relevant pathology preset(s). The dangling test asserts on `manifest.pathologies["dangling"]` rather than a hardcoded summary file. The synthetic generator must produce the `exec/<feature>/<feature>-<phase>-summary.md` directory shape since `check_dangling`'s fix path operates on real paths.
- `src/vaultspec_core/vaultcore/checks/tests/test_index_safety.py` - **NO REFACTOR REQUIRED**. Verified by review: every test in this file already uses synthetic `VaultSnapshot` objects with `Path("/fake/root")` and never reads from `test-project/`. The earlier inclusion in the consumer list was incorrect; this file can be left alone.
- `src/vaultspec_core/metrics/tests/conftest.py` and `test_metrics.py` - request a synthetic vault sized to satisfy the metrics assertions; if an assertion is `total_docs > 80`, the test parameterises the fixture to produce that count rather than depending on the historical count.
- `src/vaultspec_core/graph/tests/conftest.py` and `test_graph.py` - request a synthetic vault with `cycle`, `orphan`, `stem_collision`, and `phantom_only_links` pathologies as appropriate. The generator must also produce a feature literally named `editor-demo` for the tests at lines 257-305 that assert on `get_feature_rankings()`, `get_features()`, `get_hotspots()`, and `subgraph()`. The tests at lines 178-220 keep their property-based shape but the literal feature name `editor-demo` is preserved as a generator parameter to keep the assertions readable.

Tests that hardcode filenames from the rag corpus (e.g. `editor-event-handling-execution-summary.md`) are rewritten to assert on properties (doc type, tag presence, related-link count) rather than identity. Where a test genuinely needs a specific named doc, it generates one with that name via the factory's `named_docs` parameter. Stem collisions and phantom-only-links are produced through their dedicated pathology presets, not through ad-hoc test setup.

`graph_density` defaults to a value greater than zero so `test_networkx_digraph_has_edges` (which asserts `graph._digraph.number_of_edges() > 0`) passes against the baseline corpus. Tests that need a denser or sparser graph override the default at the call site.

### Deletions

- Remove `test-project/` from the working tree and from tracking via `git rm -r test-project/`.
- Edit `.gitignore`: delete the existing block at lines 187-189 (`test-project/*`, `!test-project/.vault/`, `!test-project/README.md`) and replace it with a single defensive line `test-project/` so a stray local checkout never re-enters the index.
- Edit `.pre-commit-config.yaml`: remove the `exclude: ^test-project/` lines from the `mdformat-check` hook (line 39) and the `pymarkdown` hook (line 47). With `test-project/` deleted these excludes are dangling and would silently mask future issues.
- `git rm -r rsc/`
- `git rm .geminiignore`
- `git rm extension.toml`

### Validation gate

The PR is ready when:

- `uv run --no-sync pytest` passes the full suite with zero skips, xfails, or warnings introduced by this work.
- `uv run --no-sync prek run --all-files` is clean.
- `uv run --no-sync python -m ty check src/vaultspec_core` is clean (matches the form used in `.pre-commit-config.yaml` and `justfile`).
- `git ls-files test-project rsc .geminiignore extension.toml` returns nothing.
- `grep -rn TEST_PROJECT src/ tests/` returns nothing.
- The session-scoped `git checkout` block is gone from `tests/conftest.py`.
- The synthetic generator is importable as `from vaultspec_core.testing import build_synthetic_vault`.

## Rationale

The research surfaced three competing design options for the fixture. Option A (extend `WorkspaceFactory`) couples two unrelated state spaces. Option C (per-test ad-hoc helpers) violates the project's factory-based testing standard and scatters generation logic across ten files. Option B (a dedicated synthetic-corpus factory) is the right shape, and the discovery of the pre-built `vaultspec-rag/synthetic.py` collapses Option B from a 300-400 LOC green-field build into a port-and-extend that touches one new file plus the pathology helpers. The lift saves design time, avoids reinventing the dataclass shapes and the `needle` indexing scheme, and aligns this repo's test infrastructure with the sibling repo without creating a runtime coupling.

Lifting rather than depending keeps the public package surface independent: `vaultspec-core` is public, `vaultspec-rag` is private; a runtime dependency would either leak `vaultspec-rag` into the public install or force a third shared package on day one. Both repos can evolve their copy independently and a shared package can be extracted later if a third sibling project needs the same generator.

Deleting the `_vault_snapshot_reset` fixture rather than retaining it as a safety net is deliberate: the fixture exists only because some test, somewhere, mutated tracked corpus state. Once `test-project/` is gone and every test runs against `tmp_path`, the fixture becomes meaningless and its presence would merely tempt future contributors to mutate state on the assumption that "session reset will clean it up". The mandate to leave no git remnant is enforced structurally, not defensively.

The housekeeping deletions (`rsc/`, `.geminiignore`, `extension.toml`) are bundled into this PR because issue `#67` scopes them together, the user explicitly requested the bundling, and each one was independently confirmed dead by the research.

## Consequences

### Positive

- The repository sheds ~3.7 MB of foreign-project artifacts and ~474 tracked files.
- Tests gain deterministic, parameterisable corpora that document their own requirements at the call site.
- Future corpus shapes (new pathologies, new doc types, new graph topologies) extend in one file rather than across ten test modules.
- The `git checkout` reset hack disappears, eliminating a class of hidden cross-test coupling.
- Production code gains an importable corpus generator at `vaultspec_core.testing.synthetic`, opening the door to future diagnostic / quality tooling that exercises the vault pipeline against synthetic input.
- Issue `#67` closes in a single PR.

### Negative

- Test refactors touch ten modules and at least 50 tests. The risk surface is wide; the mitigation is a verified plan with explicit per-module steps and code review by sub-agents before merge.
- Some tests historically relied on the exact shape of the rag corpus (specific filenames, specific dangling targets). Rewriting them to assert on properties rather than identity is the right move but may surface latent assumptions during the refactor.
- Past commits still contain `test-project/`. Cloning the repo with full history still pays the storage cost. The user has explicitly accepted this; history rewriting is a non-goal.
- The synthetic generator and the upstream `vaultspec-rag` copy will drift over time. This is by design but means future contributors should not assume the two are interchangeable.

### Neutral / future considerations

- If a third sibling project later needs the same generator, the right move is to extract `vaultspec_core.testing.synthetic` into a standalone `vaultspec-testing` package and have both consumers depend on it. That decision is deferred until the third consumer exists.
- The `WorkspaceFactory` is unchanged by this ADR and continues to own `.vaultspec/` install/sync state.

______________________________________________________________________

**Approved 2026-04-12. Status: accepted. Proceeding to `vaultspec-write-plan`.**
