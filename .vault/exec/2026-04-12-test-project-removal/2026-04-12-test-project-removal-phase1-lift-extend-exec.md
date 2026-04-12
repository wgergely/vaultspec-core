---
tags:
  - '#exec'
  - '#test-project-removal'
date: 2026-04-12
related:
  - '[[2026-04-12-test-project-removal-plan]]'
---

# `test-project-removal` `phase-1` `lift-extend`

Lifted `synthetic.py` from `wgergely/vaultspec-rag`, dropped `include_malformed`, added 14 named pathology presets, `named_docs`, `feature_names` parameters, and created the `testing` subpackage with self-tests.

- Created: `src/vaultspec_core/testing/__init__.py`
- Created: `src/vaultspec_core/testing/synthetic.py`
- Created: `src/vaultspec_core/testing/tests/__init__.py`
- Created: `src/vaultspec_core/testing/tests/test_synthetic.py`
- Modified: `pyproject.toml` (added `TC003` per-file-ignore for `testing/synthetic.py`)

## Description

Step 1.1 - Created `src/vaultspec_core/testing/__init__.py` re-exporting `build_synthetic_vault`, `build_multi_project_fixture`, `CorpusManifest`, `GeneratedDoc`.

Step 1.2 - Lifted `synthetic.py` from `wgergely/vaultspec-rag` HEAD verbatim into `src/vaultspec_core/testing/synthetic.py`. No attribution comment, no `vaultspec-rag` import dependency.

Step 1.3 - Dropped `include_malformed` flag and `_add_malformed_docs` helper entirely.

Step 1.4 - Added `pathologies: Iterable[str] | None = None` parameter with 14 named presets: `dangling`, `orphan`, `missing_frontmatter`, `wrong_directory_tag`, `stale_index`, `cycle`, `wrong_tag_count`, `stem_collision`, `phantom_only_links`, `invalid_date_format`, `malformed_related_entry`, `body_link`, `bad_filename`, `unreferenced_research`. Added `pathologies: dict[str, list[GeneratedDoc]]` and `pathology_details: dict[str, list[dict[str, Any]]]` fields to `CorpusManifest`. The `dangling` pathology records `{"target_stem": str, "source_path": Path}` per affected doc and produces `exec/<feature>/<feature>-phase1-summary.md` subdirectory shape. `phantom_only_links` records `{"plan_doc": GeneratedDoc, "phantom_targets": list[str]}`. `stem_collision` records `{"stem": str, "path_a": Path, "path_b": Path}`. `cycle` records `{"cycle_nodes": list[str]}`.

Step 1.5 - Added `named_docs: dict[str, str] | None = None` parameter. Named docs are injected before the edge-building pass so they participate in the wiki-link graph. Doc type is inferred from stem suffix via `_infer_doc_type`. Exposed via `manifest.named_docs: dict[str, GeneratedDoc]`.

Step 1.6 - Added `feature_names: list[str] | None = None` overriding the default `FEATURES` list.

Step 1.7 - Confirmed `graph_density` defaults to `0.3` (non-zero). Documented constraint in module docstring and `build_synthetic_vault` docstring.

Step 1.8 - Created `src/vaultspec_core/testing/tests/test_synthetic.py` with 53 tests covering all 10 categories: deterministic output, tag-taxonomy compliance, all 14 pathologies produce affected docs and write files, `dangling` detail schema, `phantom_only_links` detail schema, `named_docs` filenames and subdirectories, named doc graph participation, `feature_names` override, pathology+named_docs interaction, `build_multi_project_fixture` independent roots.

Exec docs are now placed inside `exec/<feature>/` subdirectories (matching the `check_dangling` fix path expectation) rather than directly under `exec/`.

## Tests

All 4 validation commands passed:

- `uv run --no-sync python -c "from vaultspec_core.testing import ..."` - imports ok
- `uv run --no-sync python -m pytest src/vaultspec_core/testing/tests/test_synthetic.py -v` - 53 passed
- `uv run --no-sync python -m ty check src/vaultspec_core/testing` - All checks passed
- `uv run --no-sync ruff check src/vaultspec_core/testing` - All checks passed
