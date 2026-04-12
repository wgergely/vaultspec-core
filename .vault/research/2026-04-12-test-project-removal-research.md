---
# REQUIRED TAGS (minimum 2): one directory tag + one feature tag
# DIRECTORY TAGS: #adr #audit #exec #plan #reference #research
# Directory tag (hardcoded - DO NOT CHANGE - based on .vault/research/ location)
# Feature tag (replace test-project-removal with your feature name, e.g., #editor-demo)
# Additional tags may be appended below the required pair
tags:
  - '#research'
  - '#test-project-removal'
# ISO date format (e.g., 2026-02-06)
date: '2026-04-12'
# Related documents as quoted wiki-links
# (e.g., "[[2026-02-04-feature-plan]]")
related:
  - '[[2026-03-23-test-quality-research]]'
  - '[[2026-03-23-cli-test-coverage-research]]'
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

<!-- LINK RULES:
     - [[wiki-links]] are ONLY for .vault/ documents in the related: field above.
     - NEVER use [[wiki-links]] or markdown links in the document body.
     - NEVER reference file paths in the body. If you must name a source file,
       class, or function, use inline backtick code: `src/module.py`. -->

# `test-project-removal` research: `test-project-corpus-removal-and-synthetic-fixture-strategy-research`

Brief description of what was researched, why, and how it relates to
`test-project-removal`.

## Findings

Adapt format based on content.

## Context

## Overview

The `test-project/` directory at the repository root contains 474 committed files (~3.7MB) of fixture corpus data that originated as RAG training material for a sibling vaultspec-rag project. It has been reused ad-hoc as a shared fixture by approximately 10 test modules across the codebase. The user mandate is threefold:

1. Delete `test-project/` entirely and prevent re-commitment to the repository.
1. Rewrite all dependent tests to synthesize fixture corpus on-the-fly using a reusable fixture/factory pattern, avoiding git-tracked corpus data.
1. Execute broader issue #67 housekeeping scope: remove unreferenced SVGs (`rsc/`), empty files (`.geminiignore`), and decide on the companion-project manifest (`extension.toml`).

This research characterizes the consumer landscape, existing factory infrastructure, and options for synthetic corpus generation to feed a subsequent Architecture Decision Record.

______________________________________________________________________

## 1. Test-Project Consumer Inventory

### Files and Fixtures Using test-project

| Consumer                             | Module/File                                                      | Fixture/Constant                                | How It References Corpus                                                                     | Assertions on Corpus Properties                                                                                                                                                                      | Minimal Synthetic Equivalent                                                                            |
| ------------------------------------ | ---------------------------------------------------------------- | ----------------------------------------------- | -------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| **Indirect session-level mutation**  | `tests/conftest.py`                                              | `_vault_snapshot_reset()` (session-scoped)      | Hardcoded `git checkout -- test-project/.vault/` after session                               | Tests mutate the committed corpus and rely on git to reset it back                                                                                                                                   | DELETE: No test should mutate git state; replace with isolated tmp_path copies                          |
| **CLI test fixture**                 | `src/vaultspec_core/tests/cli/conftest.py`                       | `test_project` fixture                          | Copies real `_TEST_PROJECT_SRC` to `tmp_path`, installs vaultspec                            | Requires 80+ docs, all 6 doc types (adr, audit, exec, plan, reference, research), working wiki-link graph                                                                                            | Synthetic corpus factory that generates N docs per type with configurable wiki-links                    |
| **CLI integration tests (50 tests)** | `src/vaultspec_core/tests/cli/test_cli_live.py`                  | `project` fixture (local to file)               | Copies `_TEST_PROJECT_SRC` to `tmp_path`                                                     | Requires 80+ docs with realistic document names and frontmatter                                                                                                                                      | Same synthetic factory                                                                                  |
| **CLI integration tests (2 tests)**  | `src/vaultspec_core/tests/cli/test_integration.py`               | `test_project` parameter                        | Direct path reference to real `test-project/`                                                | Tests that `--target` flag works; corpus shape irrelevant to intent                                                                                                                                  | Can use WorkspaceFactory or empty synthetic vault                                                       |
| **Vault scanner tests**              | `src/vaultspec_core/vaultcore/tests/test_scanner.py`             | `TEST_PROJECT` constant (path only)             | Direct path reference; tests `scan_vault()` and `get_doc_type()`                             | Requires specific documents: `2026-02-05-editor-demo-architecture-adr.md`, `2026-02-05-editor-demo-phase1-plan.md`, `2026-02-05-editor-demo-research.md`, `2026-02-05-editor-demo-core-reference.md` | Synthetic docs with matching names and correct directory placement                                      |
| **Vault query tests**                | `src/vaultspec_core/vaultcore/tests/test_query.py`               | `TEST_PROJECT` constant                         | Direct path reference; tests `list_documents()`, `get_stats()`, filtering                    | Requires 80+ docs across all types, identifiable features, orphaned and dangling docs                                                                                                                | Synthetic factory with specific feature tags and graph pathologies                                      |
| **Dangling-link checker tests**      | `src/vaultspec_core/vaultcore/checks/tests/test_dangling.py`     | `vault_root` fixture                            | Passed via fixture; test copies corpus to tmp_path                                           | Requires corpus with known dangling links (e.g., `[[event-handling-guide]]` in related: of `2026-02-04-editor-event-handling-execution-summary.md`)                                                  | Synthetic docs with injected dangling refs in specific files                                            |
| **Index-safety checker tests**       | `src/vaultspec_core/vaultcore/checks/tests/test_index_safety.py` | Some unit tests; others synthetic VaultSnapshot | Most are unit tests with synthetic metadata; requires real corpus only for integration tests | Requires real corpus for `test_warns_when_no_index_exists` (needs feature folder structure)                                                                                                          | Most tests already synthetic; integration tests need corpus with feature folders                        |
| **Metrics tests**                    | `src/vaultspec_core/metrics/tests/test_metrics.py`               | `vault_root` fixture                            | Fixture returns real `TEST_PROJECT` path                                                     | Requires >80 docs, >5 features, all 6 doc types represented, empty vault edge case tests                                                                                                             | Synthetic factory with configurable doc count and feature distribution                                  |
| **Graph tests**                      | `src/vaultspec_core/graph/tests/test_graph.py`                   | `vault_root` fixture                            | Fixture returns real `TEST_PROJECT` path                                                     | Graph construction from real corpus, networkx metrics, node/link serialization                                                                                                                       | Unit tests mostly synthetic; integration tests need corpus with connected/disconnected nodes and cycles |

### Critical Smell: tests/conftest.py Session-Level Git Reset

**File**: `tests/conftest.py:31-39`

```python
@pytest.fixture(scope="session", autouse=True)
def _vault_snapshot_reset():
    """Reset test-project/.vault/ to git HEAD after the full test session."""
    yield
    subprocess.run(
        ["git", "checkout", "--", "test-project/.vault/"],
        cwd=PROJECT_ROOT,
        check=False,
    )
```

**Issue**: This fixture runs once per session after all tests complete. It assumes that some tests have mutated the committed `test-project/.vault/` corpus and need to restore it. This is fundamentally problematic:

- Tests should never mutate the git-tracked corpus.
- Relying on session cleanup creates hidden coupling between tests.
- The fixture is fragile (git command is not checked for success).
- It prevents the ability to delete `test-project/` from git entirely.

**Mutation Tests Identified**: The `test_dangling.py::test_fix_removes_related_entry` test explicitly copies the vault to tmp_path and runs the fix operation, which is correct isolation. However, the session-level reset suggests other tests historically mutated the corpus. The fixture should be deleted; all tests should use isolated tmp_path copies.

______________________________________________________________________

## 2. Existing Fixture Infrastructure

### WorkspaceFactory Capabilities

**File**: `src/vaultspec_core/tests/cli/workspace_factory.py` (510 lines)

**Current Design**:

- Compositional builder pattern with chainable methods (every method returns `self`).
- Operates on an empty or pre-installed `.vaultspec/` workspace directory (installed via `install_run`).
- Creates/mutates manifest, provider directories, config files, gitignore/gitattributes blocks, MCP config, and framework state.
- Does NOT generate `.vault/` corpus documents; it is purely a framework-and-provider mutation tool.

**Key Methods**:

- **Base states**: `install()`, `sync()`, `uninstall()` — real CLI operations.
- **Manifest conditions**: `corrupt_manifest()`, `empty_manifest()`, `remove_provider_from_manifest()`, `add_phantom_provider()`, `set_old_vaultspec_version()`.
- **Provider directory conditions**: `delete_provider_dir()`, `empty_provider_dir()`, `add_user_content()`, `outdated_vaultspec_rules()`, `add_stale_rule()`.
- **Config file conditions**: `delete_root_config()`, `replace_root_config_with_user_content()`.
- **MCP conditions**: `add_user_mcp_servers()`, `create_user_only_mcp()`, `delete_mcp_json()`.
- **Gitignore/gitattributes conditions**: `corrupt_gitignore_block()`, `remove_gitignore_block()`, etc.
- **Framework conditions**: `delete_vaultspec_dir()`, `vaultspec_as_file()`, `delete_builtins()`.
- **Presets**: `preset_partially_managed()`, `preset_outdated_install()`, `preset_pre_existing_provider()`.

**Gap Analysis**:

- `WorkspaceFactory` does NOT generate `.vault/` documents or manage corpus structure.
- It focuses exclusively on framework and provider state (`.vaultspec/`, `.gitignore`, `.mcp.json`, provider config files).
- Extending it with corpus methods would conflate two concerns: workspace-framework state and document-corpus state.

**Recommendation**: Create a separate `CorpusFactory` or `SyntheticVault` utility rather than extending `WorkspaceFactory`.

### Other Conftest Fixtures

**Checked**:

- `src/vaultspec_core/config/tests/conftest.py` — config reset only.
- `src/vaultspec_core/protocol/tests/conftest.py` — protocol stubs.
- `src/vaultspec_core/vaultcore/tests/conftest.py` — does not exist; tests reference `TEST_PROJECT` constant directly.
- `src/vaultspec_core/vaultcore/checks/tests/conftest.py` — `vault_root` fixture returns real path.

**No existing corpus-generation fixtures found** in the codebase. All corpus tests reference the committed `test-project/`.

______________________________________________________________________

## 3. Synthetic Corpus Requirements Specification

The synthetic corpus fixture must satisfy all consumer tests listed in Section 1. Here is a unified spec:

### Corpus Structure and Contents

| Category                        | Requirement                                                                                                                                  | Rationale                                                                                                                                                                |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Directory structure**         | `.vault/adr/`, `.vault/audit/`, `.vault/exec/`, `.vault/plan/`, `.vault/reference/`, `.vault/research/`                                      | All 6 doc types must exist; some tests assert on directory-level structure.                                                                                              |
| **Minimum document counts**     | adr: ≥3, audit: ≥2, exec: ≥3, plan: ≥3, reference: ≥3, research: ≥3 (total ≥80 for metrics tests)                                            | Metrics tests assert `total_docs > 80` and all types represented.                                                                                                        |
| **Feature folders under exec/** | exec feature folders (e.g., `2026-02-04-editor-event-handling/`) with 2–3 docs each                                                          | Some tests reference specific feature folder paths; `test_dangling.py` expects `2026-02-04-editor-event-handling/2026-02-04-editor-event-handling-execution-summary.md`. |
| **Document naming**             | `YYYY-MM-DD-feature-name-<doc_type>.md` or variant                                                                                           | Matches test-project convention; some tests hardcode filename checks.                                                                                                    |
| **Frontmatter format**          | `tags` (list of 2+: directory tag + feature tag), `date` (ISO 8601), `related` (list of wiki-link strings)                                   | All checkers validate frontmatter; graph tests depend on tag structure.                                                                                                  |
| **Wiki-link graph**             | Connected component (≥70% reachable), ≥5 isolated nodes (orphans), ≥3 dangling references (e.g., `[[nonexistent]]` in related:)              | Graph tests assert connectivity; orphan checker tests require orphaned docs; dangling checker tests require broken refs.                                                 |
| **Generated index files**       | `<feature-name>.index.md` at vault root for selected features, with frontmatter `tags: ["#feature-name"]`, `related: [list of feature docs]` | Index-safety tests verify presence/absence; feature checker tests validate counts.                                                                                       |
| **Specific pathologies**        | Dangling link to `[[event-handling-guide]]` in a specific exec summary doc; orphaned docs; docs with missing frontmatter or malformed tags   | Dangling checker test hardcodes filename and expected broken ref.                                                                                                        |

### Parametrizable Factory Options

A single `SyntheticVault` fixture should support:

- `doc_counts_by_type: dict[str, int]` — override default doc counts.
- `feature_count: int` — number of features (default 5–10).
- `include_dangling_refs: bool` — inject `[[nonexistent]]` refs (default True).
- `include_orphans: bool` — include isolated docs (default True).
- `include_generated_indexes: bool` — generate `.index.md` files (default True).
- `graph_shape: str` — "connected" (default), "star", "tree", "fragmented".

Example usage:

```python
def test_metrics_custom_corpus(tmp_path):
    corpus = SyntheticVault(tmp_path).generate(
        doc_counts_by_type={"adr": 5, "plan": 3, ...},
        feature_count=3,
        include_dangling_refs=True,
    )
    result = get_vault_metrics(corpus.root)
    assert result.total_docs == sum(doc_counts_by_type.values())
```

______________________________________________________________________

## 4. Design Options for Synthetic Corpus Fixture

### Option A: Extend WorkspaceFactory with Corpus Methods

**Approach**: Add methods like `generate_corpus()`, `add_feature_docs()`, `inject_dangling_refs()` to `WorkspaceFactory`.

**Pros**:

- Single factory object handles both workspace and corpus setup.
- Composable builder pattern already proven in codebase.
- Easier discovery for new contributors.

**Cons**:

- Couples unrelated concerns (framework state vs. document state).
- `WorkspaceFactory` already has 500+ LOC; bloats the class.
- Confuses the responsibility: is it a workspace builder or a corpus builder?
- Some tests only need corpus (scanner, graph), not workspace framework.

**Complexity**: HIGH (20–30 new methods, test coverage).

______________________________________________________________________

### Option B: Create Dedicated `CorpusFactory` (or `SyntheticVault`)

**Approach**: New module `src/vaultspec_core/tests/fixtures/corpus_factory.py` (or `synthetic_vault.py`). Separate factory for corpus-only generation.

**Interface**:

```python
class SyntheticVault:
    def __init__(self, root: Path):
        self.root = root
        self._config = {...}
    
    def generate(self, doc_counts_by_type=None, feature_count=10, ...) -> Self:
        """Generate all corpus documents and return self for chaining."""
        ...
    
    @property
    def vault_dir(self) -> Path:
        """Return .vault/ directory."""
        return self.root / ".vault"
    
    @property
    def doc_by_path(self) -> dict[Path, (Metadata, Body)]:
        """Return generated document manifest for inspection."""
        ...
```

**Composability with WorkspaceFactory**:

```python
def test_full_lifecycle(tmp_path):
    # Setup workspace framework
    workspace = WorkspaceFactory(tmp_path).install()
    
    # Setup corpus
    corpus = SyntheticVault(tmp_path).generate(doc_counts_by_type={...})
    
    # Now tmp_path has both framework and corpus
    result = runner.invoke(app, ["vault", "check", "all", "--target", str(tmp_path)])
    assert result.exit_code == 0
```

**Pros**:

- Clean separation of concerns.
- Corpus factory can be used standalone (scanner tests don't need workspace framework).
- Easier to test the factory itself in isolation.
- Smaller, focused responsibility.

**Cons**:

- Two factories to import and compose.
- Slightly more boilerplate for tests that need both.

**Complexity**: MEDIUM (300–400 LOC, medium test coverage).

______________________________________________________________________

### Option C: Per-Test Ad-Hoc Helpers

**Approach**: Small utility functions in module-local fixtures (e.g., `_make_test_vault()`, `_make_adr()`, `_make_dangling_link()`).

**Pros**:

- Minimal upfront investment; tests only build what they need.
- Each test's corpus requirements are explicit and local.

**Cons**:

- Corpus generation code scatters across 10 test files.
- High duplication (same tag format, frontmatter boilerplate, etc.).
- Difficult to maintain consistent corpus semantics.
- Regression risk: if corpus-generation logic changes, all tests must be reviewed.
- Violates DRY principle and the codebase's feedback-testing standards mandate (factory-based, not ad-hoc).

**Complexity**: LOW initial, HIGH long-term maintenance.

______________________________________________________________________

### Ranking and Recommendation

1. **Option B (CorpusFactory/SyntheticVault)** — RECOMMENDED

   - Aligns with codebase philosophy: "factory-based conditions, real filesystem assertions" (from `reference_workspace_factory.md`).
   - Cleanest separation of concerns.
   - Reusable across all consumer tests.
   - Easier to extend with new pathologies (dangling refs, malformed frontmatter, etc.) without bloating `WorkspaceFactory`.

1. **Option A (Extend WorkspaceFactory)** — ACCEPTABLE

   - If the team prefers a single factory API.
   - Requires clear documentation that methods fall into two groups: framework vs. corpus.

1. **Option C (Ad-Hoc Helpers)** — NOT RECOMMENDED

   - Violates the feedback-testing standards and feedback (DRY, factory-based).

______________________________________________________________________

## 5. Session-Level Git Mutation (tests/conftest.py)

### The \_vault_snapshot_reset Fixture

**Current Code**:

```python
@pytest.fixture(scope="session", autouse=True)
def _vault_snapshot_reset():
    """Reset test-project/.vault/ to git HEAD after the full test session."""
    yield
    subprocess.run(
        ["git", "checkout", "--", "test-project/.vault/"],
        cwd=PROJECT_ROOT,
        check=False,
    )
```

**Problem**: This fixture indicates that tests mutate the committed corpus during the session. Once `test-project/` is deleted and replaced with synthetic fixtures, this fixture becomes unnecessary and must be removed.

**Mutation Tests Identified**:

- `test_dangling.py::test_fix_removes_related_entry` — Explicitly copies vault to tmp_path before running fix, so it already isolates mutations. This test is correct.
- **No other tests explicitly mutate the corpus**, suggesting this fixture is either:
  - Defensive against future mutations (unneeded if we enforce synthetic fixtures).
  - A remnant from older test code that has since been refactored.

**Action**: Delete the fixture. Enforce that all tests use isolated tmp_path copies or synthetic fixtures, never mutate git state.

______________________________________________________________________

## 6. Housekeeping Decisions (Issue #67)

### 6.1 `rsc/` Directory (SVGs)

**Inventory**:

- `rsc/svg/vaultspec-agent-err.svg`
- `rsc/svg/vaultspec-agent-ok.svg`
- `rsc/svg/vaultspec-agent-stroll.svg`

**References Found**: NONE

- No grep matches in `src/`, `tests/`, or `.vault/` (excluding test-project).
- Not mentioned in `README.md`, `CHANGELOG.md`, justfile, or CI config.

**Decision**: SAFE TO DELETE. The SVG files are unreferenced and can be removed immediately.

______________________________________________________________________

### 6.2 `.geminiignore`

**Current State**:

- File exists at repository root.
- Content: 0 bytes (empty file).

**References Found**: NONE

- No grep matches in codebase.

**Decision**: SAFE TO DELETE. The empty file serves no purpose and should be removed.

______________________________________________________________________

### 6.3 `extension.toml`

**Current Content**:

```toml
[extension]
description = "A governed development framework for AI-assisted engineering"
name = "vaultspec-core"
version = "0.1.0"

[requires.python]
version = ">=3.13"

[runtime]
install = "uv pip install ."
type = "python"

[entry_points]
cli = "src/vaultspec_core/cli.py"
mcp = "vaultspec_core.mcp_server.app:main"

[provides]
content_types = ["rules", "skills", "system", "templates"]
mcp = ["vaultspec_core.mcp_server.app"]

[outputs]
claude_dir = ".claude"
gemini_dir = ".gemini"
```

**References Found**:

- **`.vault/` documentation**: Mentioned in ADR `2026-02-19-workspace-path-decoupling-adr.md` and exec `2026-02-19-workspace-paths/2026-02-19-workspace-paths-review-exec.md` as a "companion project discovery" manifest. Created as part of the workspace-paths implementation (Feb 2026).
- **`CHANGELOG.md`**: One entry: "drop dev extra from extension.toml install command" referencing commit `85cdc31` (recent).
- **Python imports**: Zero. No `.py` files import or parse `extension.toml`.

**Interpretation**: This file was created to satisfy a companion-project (likely an Anthropic internal repo manager or framework) integration requirement. It is not actively used by the vaultspec-core Python codebase itself; it is a manifest for external consumers.

**Decision**: UNCERTAIN — Requires user confirmation.

- If the companion project is still active or planned, keep the file.
- If the companion project is dead or deprioritized, delete the file.
- Recommendation: Ask the user whether the companion project will consume this manifest. If not, delete it as a ghost artifact from an abandoned integration.

______________________________________________________________________

### 6.4 Live Tool Configs (lychee.toml, taplo.toml, .mdformat.toml, .pymarkdown.json)

**References Found**:

- **lychee.toml**: Referenced in `justfile` (lint targets), `.pre-commit-config.yaml` (live hook).
- **taplo.toml**: Referenced in `justfile` (lint/fmt targets), `.pre-commit-config.yaml` (live hook).
- **.mdformat.toml**: Referenced in `.pre-commit-config.yaml` (live hook), `justfile` (fmt target).
- **.pymarkdown.json**: Referenced in `.pre-commit-config.yaml` (live hook), `justfile` (lint target).

**Decision**: ALL FOUR FILES ARE LIVE AND ACTIVELY WIRED. No changes needed; do not delete.

______________________________________________________________________

## 7. Risks and Open Questions for the ADR

### Risks

1. **Hardcoded Corpus References**: Some tests reference specific document paths or filenames (e.g., `test_scanner.py` asserts on `"2026-02-05-editor-demo-architecture-adr.md"`). The synthetic factory must generate documents with matching names, or tests must be updated to use wildcard assertions.

1. **Graph Topology Sensitivity**: Graph tests and metrics tests may depend on the specific graph topology of `test-project/` (e.g., a specific number of disconnected components, a particular cycle structure). The synthetic corpus must match these properties or tests will fail.

1. **Checker Pathology Injection**: Checker tests (dangling, orphan, etc.) inject intentional corruption into the corpus. The synthetic factory must allow fine-grained control over which docs are broken and how.

1. **Index File Generation**: The checker and feature tests depend on generated `.index.md` files. The factory must support optional index generation and stale-count detection.

1. **Vault Health Walkers**: Some internal functions may walk the real `.vault/` directory of a vaultspec-core repo (not just the test corpus). If any test invokes a real vault checker against the repo's own `.vault/`, synthetic fixtures won't suffice. Need to audit for this.

### Open Questions

1. **Corpus Size**: Should the synthetic corpus be minimal (5–10 docs per type) or realistic (80+ docs)? The metrics tests require >80 total; scanner tests require specific filenames but not specific counts. Recommendation: Support parameterization (default 100–150 docs).

1. **Feature Distribution**: Should features be evenly distributed across doc types, or should some features have only certain types (e.g., a feature with only ADRs)? Real projects have skewed distributions.

1. **Dangling Link Count**: How many dangling refs should the synthetic corpus include by default? `test_dangling.py` expects at least one. Recommendation: 3–5 per corpus.

1. **Orphan Count**: How many isolated (unreferenced) docs should exist? `test_query.py::test_list_orphaned` just asserts that the API returns a list; it doesn't assert a count. Recommendation: 5–10 per corpus.

1. **WorkspaceFactory Composition**: Should the CorpusFactory be designed to compose with `WorkspaceFactory`, or should they remain independent? Recommend independent with optional composition helpers.

______________________________________________________________________

## 8. Upstream Prior Art: vaultspec-rag synthetic.py

A complete synthetic vault corpus generator already exists in the sibling `vaultspec-rag` repository at `src/vaultspec_rag/synthetic.py` (~250 LOC, single file, dataclass-based). It is the original tool that was built to replace ad-hoc corpus fixtures and is the reason the rag repo no longer needs the `test-project/` data either. The user has approved lifting it directly into `vaultspec-core` with no attribution and no runtime coupling between the two repos (both repos evolve their copy independently).

### Public API of the upstream module

- `build_synthetic_vault(root, *, n_docs=24, include_malformed=False, graph_density=0.3, seed=42) -> CorpusManifest`
  - Creates `.vault/{adr,plan,research,exec,reference,audit}/` and a sibling `.vaultspec/` under `root`
  - Distributes `n_docs` evenly across the six doc types
  - Renders compliant frontmatter: two tags (`#{type}` + `#{feature}`), `date`, `related: [[wiki-links]]`
  - Builds a configurable wiki-link graph (`graph_density` controls edge probability)
  - Embeds unique `NEEDLE_<TYPE>_<NNN>` keywords in each doc body for precision retrieval/assertion
  - Fully deterministic via `seed`
  - `include_malformed=True` injects three pathology variants (missing frontmatter, empty body, broken-tags-string)
- `build_multi_project_fixture(base, *, n_projects=2, docs_per_project=12, seed=42) -> list[CorpusManifest]`
  - Generates multiple isolated project roots with non-overlapping seeds for cross-project test scenarios
- `CorpusManifest` dataclass exposes `root`, `docs`, `needles` (keyword -> doc_id), `graph_edges` for assertions
- `GeneratedDoc` dataclass exposes `doc_id`, `doc_type`, `feature`, `needle`, `date`, `path`, `related_ids`

### Upstream fixture pattern

The rag repo wires it into `pytest` via `tmp_path_factory`:

```python
@pytest.fixture(scope="session")
def synthetic_vault(tmp_path_factory) -> CorpusManifest:
    root = tmp_path_factory.mktemp("vault")
    return build_synthetic_vault(root, n_docs=24, seed=42)
```

This is exactly the auto-clean, zero-git-remnant pattern this refactor requires. `pytest`'s `tmp_path_factory` handles teardown; nothing ever lands in the repo working tree.

### Gap analysis: what the upstream module is missing for this repo

The upstream `_add_malformed_docs` only emits three pathology variants. The vaultspec-core checker tests need a richer pathology set per Section 3 of this research:

- Dangling wiki-links (target doc absent)
- Orphaned documents (no inbound or outbound links)
- Missing required frontmatter fields (only `tags`, only `date`, etc.)
- Wrong directory tag (file in `.vault/adr/` tagged `#plan`)
- Mismatched feature tag count (one tag, three tags)
- Stale `.index.md` counts vs actual file counts
- Cycle in the related-graph (for cycle-detection coverage)
- Path-traversal-shaped wiki-links
- Duplicate doc_ids across types

The `vaultcore.checks` test suite drives most of these requirements. The lift will need to extend `_add_malformed_docs` (or split it into a `PathologyBuilder` companion) to cover them as opt-in flags or named presets, e.g.:

```python
build_synthetic_vault(root, pathologies=["dangling", "orphan", "stale_index", "cycle"])
```

### Lift strategy

1. **Copy** `synthetic.py` verbatim into `vaultspec-core` at a location that lets both production code and tests import it. Recommended target: `src/vaultspec_core/testing/synthetic.py` (a new `testing` subpackage), with a thin re-export from `tests/fixtures/` if pytest layout requires it. The rag repo also imports its copy from production code (`cli.py handle_quality`), so a `src/`-rooted location is appropriate.
1. **Extend** `_add_malformed_docs` and the public signature with the additional pathology presets enumerated above. Each pathology should be an enum member or string flag so tests can request only what they need.
1. **No attribution comment**, no runtime dependency on `vaultspec-rag`, no shared package. The two copies will diverge as each repo's needs evolve. If a third sibling project ever needs the same code, the question of extracting a shared `vaultspec-testing` package can be revisited then.
1. **No `WorkspaceFactory` changes**. `WorkspaceFactory` handles `.vaultspec/` install/sync state; `synthetic.py` handles `.vault/` corpus state. They are orthogonal and tests that need both compose them by passing the same `root` to each.

This finding supersedes Section 4 Option B's "design from scratch" framing: the design exists, the work is now a port-and-extend, not a green-field factory build.

______________________________________________________________________

## 9. Recommendation Summary

Delete `test-project/` and lift `synthetic.py` from `vaultspec-rag` into `vaultspec-core` at `src/vaultspec_core/testing/synthetic.py` (no attribution, no runtime coupling). Extend its `_add_malformed_docs` with the additional checker pathology presets enumerated in Section 8 (dangling, orphan, missing-frontmatter, wrong-tag, stale-index, cycle). Refactor all ten `test-project/` consumer tests to use a `synthetic_vault` fixture backed by `tmp_path_factory` so cleanup is automatic and no git remnant is ever produced. Remove the session-level `_vault_snapshot_reset()` fixture from `tests/conftest.py` (the `git checkout` smell). Delete unreferenced artifacts (`rsc/`, `.geminiignore`). Confirm with the user whether `extension.toml` remains relevant; if not, delete it. Keep all four tool configs (`lychee.toml`, `taplo.toml`, `.mdformat.toml`, `.pymarkdown.json`) as they are live in pre-commit and justfile. This refactor aligns with the `feedback_testing_standards` mandate (factory-based, zero mocks/stubs/skips, real filesystem) and eliminates all git-tracked corpus data from the repository.
