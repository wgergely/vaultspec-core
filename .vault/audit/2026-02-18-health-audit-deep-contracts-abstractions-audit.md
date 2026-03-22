---
tags:
  - '#audit'
  - '#health-audit'
date: '2026-02-18'
---

# Deep Audit: API Contracts, Dead Code, and Abstraction Quality

**Auditor:** Investigator3
**Date:** 2026-02-18
**Scope:** Production code in `lib/src/` — API surface, type hints, abstractions, dead code, import graph, YAML parser architecture, provider ABC hierarchy, and deferred CLI test issues.

______________________________________________________________________

## Executive Summary

The codebase has a well-organized layer structure with clear module boundaries. The most significant findings are: `VaultConstants.DOCS_DIR` is dead code replaced by `_get_docs_dir()` but never removed; `handle_create` in `vault.py` hardcodes `".vault"` rather than using `get_config().docs_dir`; `_delete_by_ids` uses a different and weaker escaping strategy than `_sanitize_filter_value`; `get_document` and `get_status` create bare `VaultStore` instances that violate the singleton principle; `supported_models` and `get_model_capability` are defined on the `AgentProvider` base but never called from production code; and `construct_system_prompt` is abstract in the base but has identical implementations in both concrete providers — a copy-paste abstraction. The CLI test issues are non-trivial: `TestArgumentParsing` is genuinely divergent from production (missing `--fix` on audit), and `test_create_generates_correct_filename` exercises zero production code paths.

______________________________________________________________________

## 1. Dead Code Detection

### 1.1 `VaultConstants.DOCS_DIR` — orphaned class attribute

**File:** `vault/models.py:109`

```python
DOCS_DIR = ".vault"  # Backwards-compat default; prefer _get_docs_dir()
```

The comment acknowledges this is superseded by `_get_docs_dir()`. A search of the entire `lib/` tree finds **zero production callsites** of `VaultConstants.DOCS_DIR`. All callers instead use `get_config().docs_dir` directly (via `_get_docs_dir()` or inline). The class attribute is dead code. Its continued presence creates confusion: a reader encountering it could rely on it for the docs dir name and get a hardcoded string rather than the configurable value.

**Dead callers:** 0 production callers found. The attribute appears only in `models.py` itself.

### 1.2 `AgentProvider.supported_models` and `get_model_capability` — never called from production

**File:** `protocol/providers/base.py:148-156`

```python
@property
def supported_models(self) -> list[str]:
    return self.models.ALL

def get_model_capability(self, model: str) -> CapabilityLevel:
    ...
```

A search of `lib/src/` shows these methods are called only from tests (`test_providers.py`), never from production code. `prepare_process()` in both `ClaudeProvider` and `GeminiProvider` uses `get_best_model_for_capability()` (which IS production-used), but `supported_models` and `get_model_capability` are test-only utilities promoted to the ABC surface. This inflates the public API contract without production justification.

### 1.3 `construct_system_prompt` — abstract method with identical concrete implementations

**File:** `protocol/providers/base.py:171-177` (abstract), `claude.py:58-72`, `gemini.py:78-92`

The abstract method forces both providers to implement `construct_system_prompt`. The implementations in `ClaudeProvider` and `GeminiProvider` are **byte-for-byte identical**:

```python
def construct_system_prompt(self, persona, rules, system_instructions=""):
    parts = []
    if system_instructions.strip():
        parts.append(f"# SYSTEM INSTRUCTIONS\n{system_instructions}")
    if persona.strip():
        parts.append(f"# AGENT PERSONA\n{persona}")
    if rules.strip():
        parts.append(f"# SYSTEM RULES & CONTEXT\n{rules}")
    return "\n\n".join(parts)
```

This is a copy-paste abstraction anti-pattern: the method is `@abc.abstractmethod` but both concrete implementations are identical, making the abstraction provide zero differentiation. The method should be a concrete implementation on `AgentProvider` base class, not abstract. Any future divergence in behavior can override at that point.

### 1.4 `VaultRAG.close()` — `_model` teardown does nothing

**File:** `rag/api.py:68-75`

```python
def close(self) -> None:
    if self._store is not None:
        self._store.close()
    self._model = None  # no actual cleanup on EmbeddingModel
    ...
```

`EmbeddingModel` holds a GPU-loaded `SentenceTransformer` model. Setting `self._model = None` releases the Python reference but does not call any cleanup method on the model object. If the only reference is via `_engine`, this works correctly via garbage collection. However, if anything else holds a reference to the model (e.g., if a test caches it), the VRAM is not freed. This is a latent issue, not a defect in current usage, but worth noting.

### 1.5 `reset_engine` — not exported, undiscoverable

**File:** `rag/api.py` — there is no `reset_engine()` function. Tests reset the singleton by directly setting `api_mod._engine = None`. This works but is an undocumented internal pattern. There is no public `reset_engine()` function despite tests needing one. Compare to `core/config.py` which has the clean pair `get_config()` / `reset_config()`.

______________________________________________________________________

## 2. API Contract Consistency

### 2.1 `_delete_by_ids` uses weaker escaping than `_sanitize_filter_value`

**File:** `rag/store.py:332`

Two different escaping strategies exist in the same file:

```python

# _sanitize_filter_value (line 42): proper SQL double-quoting escape

sanitized = value.replace("'", "''")

# _delete_by_ids (line 332): strips single quotes entirely

escaped = ", ".join(f"'{i.replace(chr(39), '')}'" for i in ids)
```

`_sanitize_filter_value` correctly escapes `'` as `''` (standard SQL escape). `_delete_by_ids` instead **removes** single quotes entirely by replacing them with empty string. This is inconsistent and, while it prevents injection, it silently corrupts document IDs containing apostrophes (e.g., a doc named `it's-a-test` becomes `its-a-test` in the DELETE predicate, potentially matching the wrong row or matching nothing). Since document IDs come from file stems, apostrophes are unlikely in practice, but the inconsistency represents a design flaw. `_delete_by_ids` should call `_sanitize_filter_value` for consistency.

### 2.2 `handle_create` in `vault.py` hardcodes `".vault"`

**File:** `lib/scripts/vault.py:179`

```python
target_dir = root_dir / ".vault" / doc_type.value
```

Every other consumer of the docs directory uses `get_config().docs_dir`. `handle_create` hardcodes the string `".vault"` directly. If `VAULTSPEC_DOCS_DIR` is set to a custom value (e.g., in a test or alternate configuration), the `create` subcommand will create files in `.vault/` regardless. This is a configuration bypass — the only place in the codebase where `docs_dir` is not dynamically resolved at runtime.

### 2.3 `get_document` and `get_status` create raw `VaultStore` instances

**File:** `rag/api.py:170-171`, `rag/api.py:290-291`

```python
store = VaultStore(root_dir)  # in get_document
store = VaultStore(root_dir)  # in get_status
```

These functions instantiate `VaultStore` directly, bypassing the `get_engine()` singleton. This means:

The pattern is inconsistent with the singleton design in `VaultRAG`. Both functions should either use `get_engine().store` or ensure their `VaultStore` instances are properly guarded and closed (e.g., via the context manager `__enter__`/`__exit__`).

### 2.4 Return type accuracy: `get_related` returns `dict | None` but callers must handle `None`

**File:** `rag/api.py:225-262`

`get_related()` is typed as returning `dict | None`. The test at `tests/rag/test_api.py:145-157` calls `get_related` without guarding the `None` case — it asserts `result` is not `None` but then directly accesses `result["outgoing"]`. If the doc_id is not in the graph (which is possible if the vault graph hasn't been indexed), the test would fail with `TypeError`. This is a test robustness issue, not a production type contract violation, but illustrates that callers must always guard the `None` return.

### 2.5 `parse_vault_metadata` does not strip content before matching

**File:** `vault/parser.py:73-116`

`parse_frontmatter` (line 55) calls `content.lstrip()` before matching `---`. `parse_vault_metadata` does NOT — it matches the raw content with `re.match(r"^---\s*\n...")`. This means content with a leading blank line or BOM will fail to parse frontmatter in `parse_vault_metadata` but would succeed in `parse_frontmatter`. The BOM case is handled by callers of `parse_vault_metadata` (e.g., `fix_violations` strips the BOM before calling it), but a leading newline would silently produce an empty `DocumentMetadata` with no error.

______________________________________________________________________

## 3. Abstraction Quality

### 3.1 Dual YAML parser architecture — clear and intentional

**File:** `vault/parser.py`

The two parsers serve distinct purposes:

- **`parse_frontmatter(content)`** — returns `dict[str, Any]`. Uses PyYAML (with fallback to simple splitter). Called by `cli.py` (sync engine, agent file loading), `orchestration/subagent.py` (reading plan files), `subagent_server/server.py` (reading agent definitions), and the e2e tests. Callers need a raw dict because agent YAML files have complex, non-rigid schemas.

- **`parse_vault_metadata(content)`** — returns `tuple[DocumentMetadata, str]`. Uses a hand-rolled line parser. Called by `verification/`, `graph/`, `rag/indexer.py`, and `rag/api.py`. Callers need a typed `DocumentMetadata` object because they validate against the rigid vault schema.

The split is **intentional and correct** — the two parsers serve different layers (framework-level agent configs vs vault document metadata). However, the duplication of the frontmatter regex pattern (`r"^---\s*\n(.*?)\n---\s*\n?(.*)"` with `re.DOTALL`) between both parsers is worth noting as a shared extraction point could be extracted. More importantly, `parse_vault_metadata` does not call `parse_frontmatter` internally — it reimplements the block extraction, meaning a change to how frontmatter delimiters work (e.g., allowing `---\r\n`) would need to be applied in both places.

### 3.2 `VaultConstants._get_docs_dir` vs `VaultConstants.DOCS_DIR` — fully resolved

As noted in §1.1: `_get_docs_dir()` is the live path (called by `validate_vault_structure`). `DOCS_DIR` is dead. The dual-path documented in the task description resolves to: only `_get_docs_dir()` is active. No bugs result from this because `DOCS_DIR` is never called. The bug risk is that a future developer might use `DOCS_DIR` believing it is authoritative.

### 3.3 Provider ABC — `prepare_process` enforced correctly; `construct_system_prompt` over-abstracted

**File:** `protocol/providers/base.py`

The ABC enforces four methods: `name`, `models`, `load_system_prompt`, `load_rules`, `construct_system_prompt`, and `prepare_process`. Of these:

- `name`, `models`, `load_system_prompt`, `load_rules`, `prepare_process` — correctly abstract; implementations differ meaningfully between Claude and Gemini.
- `construct_system_prompt` — implementations are byte-for-byte identical (§1.3). Should be concrete on base.

The `AgentProvider.prepare_process` base method has `pass` as its body (line 221). Python's `abc.abstractmethod` requires a body but ignores it; `pass` is correct here. However, the `# type: ignore` comment pattern previously noted elsewhere in the codebase suggests this might have caused linting noise.

The ABC does NOT enforce `check_version`, which is a `@staticmethod` on `GeminiProvider` only. This is appropriate — version checking is provider-specific.

### 3.4 `_GEMINI_ONLY_FEATURES` / `_CLAUDE_ONLY_FEATURES` — asymmetric coverage

**File:** `claude.py:23`, `gemini.py:28-34`

Claude warns on `approval_mode` (a Gemini-only feature). Gemini warns on `max_turns`, `budget`, `disallowed_tools`, `effort`, `fallback_model` (Claude-only features). But `allowed_tools` is handled by **both** providers and is NOT in either warning list — it's in `_CLAUDE_ONLY_FEATURES` exclusion only. This is correct (both handle it), but `output_format` appears in both: Claude handles it but doesn't put it in `_GEMINI_ONLY_FEATURES`, and Gemini handles it via `--output-format`. This is correct but the feature-to-provider mapping is only documented in two private tuples with no cross-referencing tests.

______________________________________________________________________

## 4. Import Graph Analysis

### 4.1 Layer boundaries

The module dependency graph respects a clean layering:

```
core/ (stdlib only, no project imports)
  ↑
vault/ (depends on core)
  ↑
graph/, metrics/, verification/ (depend on vault, core)
  ↑
rag/ (depends on vault, core, graph)
  ↑
protocol/ (depends on vault, core)
  ↑
orchestration/ (depends on protocol, vault, core)
  ↑
subagent_server/ (depends on orchestration, vault)
```

No circular imports were found. The `metrics.api` importing from `verification.api` (`list_features`) is a cross-sibling dependency that is appropriate given their relationship.

### 4.2 Deferred import pattern in `rag/api.py` — good for Tier 1/2 split

`rag/api.py` uses deferred imports inside function bodies for all `torch`, `lancedb`, and `sentence-transformers` usage. This correctly implements the Tier 1/2 split: `list_documents`, `get_related`, `get_status` work without RAG deps. The pattern is intentional and correct.

### 4.3 `vault.py` top-level imports include `VaultGraph` — eager load risk

**File:** `lib/scripts/vault.py:20`

```python
from graph.api import VaultGraph  # noqa: E402
```

This is a top-level import in `vault.py`. `VaultGraph` imports `vault.links`, `vault.models`, `vault.parser`, `vault.scanner` — all stdlib-safe. This is fine. However, it means that `vault.py index` and `vault.py search` incur the graph module load even though those subcommands don't use the graph. This is a minor startup cost, not a correctness issue.

### 4.4 `rag/store.py` imports `EmbeddingModel` at module top level

**File:** `rag/store.py:19`

```python
from rag.embeddings import EmbeddingModel
```

`rag/embeddings.py` imports `torch` at the top level (inside a `try/except ImportError`). This means importing `rag.store` will attempt to import `torch` immediately. For the "no RAG deps" case, the `_check_rag_deps()` guard in `VaultStore.__init__` catches the `ImportError` at construction time, but the module-level `EmbeddingModel` import runs before any guard. If `rag.embeddings` fails to import (no torch), `rag.store` itself will fail to import. This is only a problem if code tries to `import rag.store` without RAG deps — which is currently guarded by the `try: from rag.store import VaultStore ... except ImportError` pattern in callers. The chain is safe but fragile.

______________________________________________________________________

## 5. Deferred CLI Test Issues — Full Analysis

### 5.1 `TestArgumentParsing` — divergence from production confirmed

**Problem:** The `parser` fixture in `TestArgumentParsing` (lines 148-198) manually reconstructs the argparse configuration by copying it from `vault.py`. The reconstructed parser is **missing `--fix`** on the `audit` subcommand (present in production at `vault.py:79`).

**Production `audit` parser includes:**

**Impact:** Any future `--fix`-related argument changes in `vault.py` would not be caught by `TestArgumentParsing`. More fundamentally, testing argparse configuration by re-implementing it is the wrong approach. The correct fix is to extract `_make_parser()` from `main()` in `vault.py` and import it directly in the test:

## vault.py — extract parser construction

def \_make_parser() -> argparse.ArgumentParser:
parser = argparse.ArgumentParser(...)

```
# ... all parser setup ...

return parser
```

def main():
args = \_make_parser().parse_args()
...

````

```python

# test_docs_cli.py — import the real parser

@pytest.fixture()
def parser(self):
    import docs
    return docs._make_parser()
````

This would make `TestArgumentParsing` tests genuinely verify the production parser rather than a manually-maintained copy. The existing tests would continue to pass unchanged (same API), and any future parser changes would be automatically covered.

## 5.2 `test_create_generates_correct_filename` — exercises zero production code

**Current implementation (lines 424-447):**

```python
def test_create_generates_correct_filename(self, tmp_path):

    # Set up vault structure and template ...

    date_str = datetime.now().strftime("%Y-%m-%d")
    feature = "my-feature"
    doc_type_value = "adr"
    filename = f"{date_str}-{feature}-{doc_type_value}.md"
    target_path = tmp_path / ".vault" / doc_type_value / filename

    assert target_path.name == f"{date_str}-my-feature-adr.md"
    assert target_path.parent.name == "adr"
```

This test constructs a `Path` object in pure Python and asserts on the string it produces. It never calls `handle_create`, `vault.py` as a subprocess, or any production code. The assertions are tautologically true — they merely verify that Python f-string interpolation works.

**What `handle_create` actually does** (lines 162-188 in `vault.py`):

1. Calls `get_template_path(root_dir, doc_type)` — can return `None` if template missing
1. Reads template content and calls `hydrate_template(content, feature, date_str, args.title)`
1. Writes hydrated content to `target_path`
1. Prints `Created {target_path}`
   **What a proper integration test would look like:**

def test_create_generates_correct_filename(self, tmp_path):

```
# Create required template

template_dir = tmp_path / ".vaultspec" / "templates"
template_dir.mkdir(parents=True)
(template_dir / "adr.md").write_text(
    "---\ntags: [\"#adr\", \"#<feature>\"]\ndate: <yyyy-mm-dd>\n---\n# <title>\n",
    encoding="utf-8",
)
```

```

# Run the actual CLI command

result = run_docs(
    "create",
    "--type", "adr",
    "--feature", "my-feature",
    "--title", "My ADR Title",
    "--root", str(tmp_path),
)

assert result.returncode == 0

# Verify the file was created with the expected name pattern

date_str = datetime.now().strftime("%Y-%m-%d")
expected_filename = f"{date_str}-my-feature-adr.md"
expected_path = tmp_path / ".vault" / "adr" / expected_filename
assert expected_path.exists(), f"Expected file not created: {expected_path}"

# Verify content was hydrated

content = expected_path.read_text(encoding="utf-8")
assert "my-feature" in content
assert date_str in content
assert "My ADR Title" in content
```

````

This test would cover: `handle_create`, `get_template_path`, `hydrate_template`, the filename construction, directory creation (`target_dir.mkdir(parents=True, exist_ok=True)`), and the file write. It would also catch the hardcoded `".vault"` bug (§2.2) if `VAULTSPEC_DOCS_DIR` is set differently.

---

## 6. Type Hint Accuracy

### 6.1 `VaultStore.__exit__` return type — minor inaccuracy

**File:** `rag/store.py:146`

```python
def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
    self.close()
    return False
````

The return type is annotated as `bool` but should be `Literal[False]` or simply `None` (returning `False` from `__exit__` is the canonical "do not suppress exceptions" signal, equivalent to `None`). This is cosmetic but technically inaccurate: returning `None` and returning `False` both mean "don't suppress", but the type annotation `bool` implies it could return `True`. The canonical signature is `def __exit__(self, ...) -> bool | None`.

### 6.2 `_build_where` return type

**File:** `rag/store.py:338`

```python
@staticmethod
def _build_where(filters: dict[str, str] | None) -> str | None:
```

The return type correctly reflects the implementation (returns `None` when no filters). Callers check for `None` before using the WHERE clause. This is accurate.

### 6.3 `get_template_path` return — dead code path after None check

**File:** `lib/scripts/vault.py:169-173`

```python
template_path = get_template_path(root_dir, doc_type)
if template_path is None:
    print(f"Error: No template found for type '{doc_type.value}'")
    sys.exit(1)

assert template_path is not None  # narrowing for type checker
```

After the `sys.exit(1)`, `template_path` cannot be `None`. The `assert` on line 173 is unreachable in any non-exceptional code path (type checkers can't know `sys.exit` raises, hence the narrowing assertion). The assertion is a workaround for a type checker limitation — it is not harmful but is unnecessary noise. The cleaner pattern is to assign `template_path` after the guard:

```python
if template_path is None:
    print(f"Error: No template found for type '{doc_type.value}'")
    sys.exit(1)
content = template_path.read_text(encoding="utf-8")  # type checker knows not None
```

______________________________________________________________________

## Critical Findings Summary

| #   | Severity | Location                             | Finding                                                                                                                                             |
| --- | -------- | ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | High     | `rag/store.py:332`                   | `_delete_by_ids` strips quotes rather than escaping them — inconsistent with `_sanitize_filter_value`, silently corrupts IDs containing apostrophes |
| 2   | High     | `vault.py:179`                       | `handle_create` hardcodes `".vault"` instead of using `get_config().docs_dir` — configuration bypass                                                |
| 3   | Medium   | `rag/api.py:170,290`                 | `get_document` and `get_status` create raw `VaultStore` instances, bypassing the singleton and risking concurrent LanceDB connections               |
| 4   | Medium   | `vault/models.py:109`                | `VaultConstants.DOCS_DIR` is dead code with zero production callers — misleading to future developers                                               |
| 5   | Medium   | `protocol/providers/base.py:171`     | `construct_system_prompt` is abstract but both implementations are identical — should be concrete on base                                           |
| 6   | Medium   | `lib/tests/cli/test_docs_cli.py:148` | `TestArgumentParsing` fixture is missing `--fix` from audit parser — diverged from production                                                       |
| 7   | Medium   | `lib/tests/cli/test_docs_cli.py:424` | `test_create_generates_correct_filename` exercises no production code — only tests Python string interpolation                                      |
| 8   | Low      | `protocol/providers/base.py:148,151` | `supported_models` and `get_model_capability` are never called from production code — test-only utilities on the ABC surface                        |
| 9   | Low      | `vault/parser.py:77`                 | `parse_vault_metadata` does not strip leading whitespace before frontmatter match; `parse_frontmatter` does — behavioral gap                        |
| 10  | Low      | `rag/api.py`                         | No `reset_engine()` public function; tests reset via `_engine = None` directly                                                                      |

______________________________________________________________________

## Recommendations

**Immediate (High severity):**

- Fix `handle_create`: replace `root_dir / ".vault" / doc_type.value` with `root_dir / get_config().docs_dir / doc_type.value`.

- Wrap `VaultStore` creation in `get_document` and `get_status` with proper lifecycle management (either use `get_engine().store` or use the context manager pattern).

- Remove `VaultConstants.DOCS_DIR` class attribute.

- Make `construct_system_prompt` a concrete method on `AgentProvider` base class.

**Cleanup (Low severity):**

- Remove `supported_models` and `get_model_capability` from `AgentProvider` ABC surface if they have no production callers.
