---
tags: [#research, #configuration]
date: 2026-02-16
related: []
---

# Environment Variable Patterns Analysis — vaultspec

## Executive Summary

The vaultspec codebase has **fragmented environment variable (env var) management** across multiple modules with **no unified standardization**. 15+ env vars are scattered throughout the codebase with **inconsistent naming patterns**, **duplicate constants**, and **ad-hoc defaults**. The project uses a **prefix-based convention** (`VS_*` for Claude bridge, `GEMINI_*` for Gemini, `VS_MCP_*` for MCP server) but lacks a centralized registry.

---

## 1. Existing Configuration Patterns

### 1.1 Current Approaches

#### Pattern A: Direct `os.environ` Access

**Files affected:**

- `.vaultspec/lib/src/protocol/providers/claude.py` (env copy + writes)

- `.vaultspec/lib/src/protocol/providers/gemini.py` (env copy + writes)
- `.vaultspec/lib/src/protocol/acp/client.py` (env copy)
- `.vaultspec/lib/src/subagent_server/server.py` (2 env vars read)
- `.vaultspec/scripts/cli.py` (env copy in provider)

**Characteristic patterns:**

```python

# Default + fallback pattern
self._root_dir: str = os.environ.get("VS_ROOT_DIR", os.getcwd())



if "VS_MAX_TURNS" in os.environ

    value = int(os.environ["VS_MAX_TURNS"])



os.environ["VS_ALLOWED_TOOLS"].split(",")



# No validation or standardized type conversion

```

`.vaultspec/scripts/_paths.py` provides manual path setup (not env vars, but related):

```python
_SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT_DIR: Path = _SCRIPTS_DIR.parent.parent
LIB_SRC_DIR: Path = ROOT_DIR / ".vaultspec" / "lib" / "src"


```

All 3 CLI entry points (cli.py, subagent.py, docs.py) accept `--root` parameter with `ROOT_DIR` fallback from `_paths.py`.

#### Pattern C: No Centralized Configuration Objects

- **No `config.py` module** — configuration is dispersed

- **No Pydantic models** — for structured config with validation
- **No dataclass usage** — for default management
- **No `.env` file support** — dotenv is not used anywhere

#### Pattern D: Test-Specific Constants in conftest.py

Multiple conftest files define their own constants:

- `.vaultspec/tests/conftest.py` — `TEST_PROJECT`, `GPU_FAST_CORPUS_STEMS`, `HAS_RAG`
- `.vaultspec/lib/src/rag/tests/conftest.py` — duplicate constants
- No mechanism to inherit or override from parent conftest

---

## 2. Complete Environment Variable Inventory

### 2.1 Claude Bridge Variables (`VS_*` prefix)

**File:** `.vaultspec/lib/src/protocol/acp/claude_bridge.py`

| Env Var | Type | Default | Purpose | Usage Pattern |
|---------|------|---------|---------|---|
| `VS_ROOT_DIR` | str | `os.getcwd()` | Workspace root directory | Read via `os.environ.get()` |
| `VS_AGENT_MODE` | str | `"read-write"` | Permission sandbox mode | Read via `os.environ.get()` |
| `VS_SYSTEM_PROMPT` | str | `None` | Initial system instructions | Read via `os.environ.get()` |
| `VS_MAX_TURNS` | int | `None` | Maximum turns for agent | Checked + parsed with try/except |
| `VS_BUDGET_USD` | float | `None` | Cost budget limit | Checked + parsed with try/except |
| `VS_ALLOWED_TOOLS` | csv-list | `[]` | Allowed MCP tools | Split on "," + filtered |
| `VS_DISALLOWED_TOOLS` | csv-list | `[]` | Forbidden MCP tools | Split on "," + filtered |
| `VS_EFFORT` | str | `None` | Agent effort level | Read via `os.environ.get()` |
| `VS_OUTPUT_FORMAT` | str | `None` | Output format (text/json) | Read via `os.environ.get()` |
| `VS_FALLBACK_MODEL` | str | `None` | Secondary model | Read via `os.environ.get()` |
| `VS_INCLUDE_DIRS` | csv-list | `[]` | Additional include paths | Split on "," + filtered |

**Writer:** `ClaudeProvider.prepare_process()` sets these as `env` dict passed to subprocess.

**Validation:** Only `VS_MAX_TURNS` and `VS_BUDGET_USD` have basic range validation (must be > 0).

---

### 2.2 Gemini Provider Variables (`GEMINI_*` prefix)

**File:** `.vaultspec/lib/src/protocol/providers/gemini.py`

| Env Var | Type | Default | Purpose | Usage Pattern |
|---------|------|---------|---------|---|
| `GEMINI_SYSTEM_MD` | path | — | Temp system prompt file | Written by provider, cleaned up after |

**Context:** Gemini CLI doesn't support `--system` flag, so system prompt is written to a temp file and passed via `GEMINI_SYSTEM_MD`. File is created in `.vaultspec/.tmp/` and tracked for cleanup.

---

### 2.3 MCP Server Variables (`VS_MCP_*` prefix)

**File:** `.vaultspec/lib/src/subagent_server/server.py`

| Env Var | Type | Default | Purpose | Usage Pattern |
|---------|------|---------|---------|---|
| `VS_MCP_ROOT_DIR` | str | — | Workspace root (required) | Read via `os.environ.get()` |
| `VS_MCP_TTL_SECONDS` | float | `3600.0` | Task cache TTL | Read via `os.environ.get()` + float conversion |

**Usage Context:** Only read in `main()` function to initialize server globals.

---

### 2.4 Deprecated/Cleaned Env Vars

| Env Var | Location | Note |
|---------|----------|------|
| `CLAUDECODE` | `protocol/providers/claude.py:114` | **Explicitly removed**: `env.pop("CLAUDECODE", None)` |

---

## 3. Hardcoded Constants by Module

### 3.1 Vault & Storage Constants

**File:** `.vaultspec/lib/src/vault/models.py`

```python
class VaultConstants:
    DOCS_DIR = ".vault"  # Central vault directory name
    SUPPORTED_DIRECTORIES: set = {"adr", "exec", "plan", "reference", "research"}
```

**Usage:** Read directly as class attributes; no env var override.

---

### 3.2 Embedding & RAG Constants

**File:** `.vaultspec/lib/src/rag/embeddings.py`

class EmbeddingModel:
    MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"  # Hardcoded model ID
    DIMENSION = 768                                 # Vector dimension
    DOCUMENT_PREFIX = "search_document: "          # Prefix for docs
    QUERY_PREFIX = "search_query: "                # Prefix for queries
    DEFAULT_BATCH_SIZE = 64                        # GPU batch size
    MAX_EMBED_CHARS = 8000                         # Truncation limit

```

**Performance Implication:** `MAX_EMBED_CHARS=8000` is empirically tuned to balance coverage (~2000 words) vs padding overhead. No env var override.

---

### 3.3 Subagent Server Constants


**File:** `.vaultspec/lib/src/subagent_server/server.py`

```python
_POLL_INTERVAL = 5.0                              # Agent file polling frequency
_ARTIFACT_PATTERN = re.compile(...)               # File path extraction regex
```

**Directory Structure (hardcoded):**

```python
AGENTS_DIR = ROOT_DIR / ".vaultspec" / "agents"
```

---

**File:** `.vaultspec/lib/src/protocol/providers/gemini.py`

```python
_MIN_VERSION_WINDOWS = (0, 9, 0)     # v0.9.0 fixes Windows ACP hang
_MIN_VERSION_RECOMMENDED = (0, 27, 0) # v0.27.0 has stable agent skills
```

**Cache:** `_cached_version` global prevents repeated version checks

### 3.5 CLI Framework Constants

**File:** `.vaultspec/scripts/cli.py`

```python

PROTECTED_SKILLS = {"fd", "rg", "sg", "sd"}      # Reserved skill names
CONFIG_HEADER = "<!-- AUTO-GENERATED by cli.py config sync. -->"

# Directory structure (hardcoded):
RULES_SRC_DIR = root / ".vaultspec" / "rules"
AGENTS_SRC_DIR = root / ".vaultspec" / "agents"
SKILLS_SRC_DIR = root / ".vaultspec" / "skills"
SYSTEM_SRC_DIR = root / ".vaultspec" / "system"
```

---

### 3.6 Test Fixtures & Constants

**File:** `.vaultspec/tests/conftest.py` and `.vaultspec/lib/src/rag/tests/conftest.py`

```python
# Duplicated in multiple conftest.py files:


TEST_PROJECT = <path> / "test-project"
GPU_FAST_CORPUS_STEMS = frozenset([...])  # 13 representative docs
HAS_RAG = <bool>                          # Check if RAG deps available

# LanceDB directory names (hardcoded):
lance_name = f".lance{lance_suffix}"      # ".lance-fast", ".lance-full", etc.
```

**Issue:** `GPU_FAST_CORPUS_STEMS` is defined in **two places** with same content:

- `.vaultspec/tests/conftest.py` (lines 37-58)
- `.vaultspec/lib/src/rag/tests/conftest.py` (lines 31-47)

---

### 3.7 Directory Structure Convention (Implicit)

project-root/

├── .vaultspec/
│   ├── agents/           # Sub-agents
│   ├── rules-custom/     # Custom rules
│   ├── skills/           # Dispatch skills
│   ├── system/           # System prompts
│   ├── .tmp/             # Temp files (Gemini system MD)

│   ├── .logs/            # Session logs
│   └── scripts/          # CLI entry points

├── .vault/               # Documentation vault
├── .claude/              # Claude tool sync destination
├── .gemini/              # Gemini tool sync destination
└── test-project/         # Test fixture root
    └── .vault/           # Git-tracked seed corpus (224 files)

**No centralized registry** — paths are hardcoded in multiple modules.

---

## 4. Import Patterns & Circular Dependency Issues

### 4.1 No Circular Dependencies Today

Since there's no centralized config module, circular imports are **not currently an issue**. Each module imports only what it needs from stdlib + third-party.

### 4.2 Test Infrastructure Path Bootstrap

All test conftest files manually add `lib/src` to `sys.path`:

```python
_LIB_SRC = Path(__file__).resolve().parent.parent.parent
if str(_LIB_SRC) not in sys.path:
    sys.path.insert(0, str(_LIB_SRC))
```

**Pattern:** Done independently in:

- `.vaultspec/tests/conftest.py` (top-level)

- `.vaultspec/lib/src/*/tests/conftest.py` (per-module)
- `.vaultspec/lib/src/rag/tests/conftest.py` (RAG-specific)

---

## 5. Test Isolation & Cleanup Patterns

### 5.1 Current Test Fixtures

**Session-scoped RAG fixtures:**

```python
@pytest.fixture(scope="session")

def rag_components():  # Uses .lance-fast/
    ...

@pytest.fixture(scope="session")
def rag_components_full():  # Uses .lance-full/ (full corpus)
    ...



**Issue:** Separate lance directories prevent corruption but add complexity.

### 5.2 Cleanup Patterns


**Vault reset (session cleanup):**

```python
@pytest.fixture(scope="session", autouse=True)
def _vault_snapshot_reset():
    yield
    subprocess.run(["git", "checkout", "--", "test-project/.vault/"])
```

**Lance cleanup (fixture teardown):**

```python

@pytest.fixture(scope="session")
def rag_components():
    yield components

```

---

## 6. Naming Convention Analysis

| Prefix | Context | Count | Example |
|--------|---------|-------|---------|
| `VS_` | Claude bridge + MCP | 13 | `VS_ROOT_DIR`, `VS_MAX_TURNS` |
| `GEMINI_` | Gemini provider | 1 | `GEMINI_SYSTEM_MD` |
| (module-level) | Test constants | N/A | `TEST_PROJECT`, `GPU_FAST_CORPUS_STEMS` |

### 6.2 Inconsistencies

1. **No prefix for test constants** — `TEST_PROJECT`, `HAS_RAG` are global, not namespaced

4. **Comma-separated list convention** — For `VS_ALLOWED_TOOLS`, `VS_DISALLOWED_TOOLS`, `VS_INCLUDE_DIRS` (ad-hoc)

---

## 7. Type Conversion & Validation Issues

### 7.1 Unsafe Type Conversions

| Env Var | Current Pattern | Issue |
|---------|-----------------|-------|

| `VS_MAX_TURNS` | `int(os.environ[...])` in try/except | No bounds checking; invalid values silently ignored |
| `VS_BUDGET_USD` | `float(os.environ[...])` in try/except | No bounds checking; invalid values silently ignored |
| `VS_ALLOWED_TOOLS` | `.split(",")` + `.strip()` | No validation of tool names |

### 7.2 Range Validation (Partial)

```python
if self._max_turns is not None and self._max_turns <= 0:
    self._max_turns = None  # Silently ignored
    self._budget_usd = None  # Silently ignored
```

**Gap:** No logging when values are silently discarded.

---

## 8. Documentation & Discovery

### 8.1 Current Documentation

**Documented in docstrings:**

- `.vaultspec/lib/src/protocol/acp/claude_bridge.py` — Lists 11 `VS_*` vars

- `.vaultspec/lib/src/subagent_server/server.py` — Lists 2 `VS_MCP_*` vars
- No centralized reference document

### 8.2 Discovery Mechanisms

**For developers:**

1. Search for `os.environ` in codebase
2. Read docstrings in claude_bridge.py

**For tests:**

1. Fixtures read from conftest.py
2. Constants are duplicated (GPU_FAST_CORPUS_STEMS)

---

## 9. Summary of Pain Points

### Critical Issues

1. **Fragmented env var reads** — 13+ scattered across 5+ files

2. **Duplicate test constants** — `GPU_FAST_CORPUS_STEMS` defined in 2 files
3. **No centralized registry** — Hard to audit what env vars exist

4. **No validation framework** — Type conversions are manual + error-prone
5. **Silent failures** — Invalid values are discarded without logging

### Medium Issues

6. **Inconsistent naming** — `VS_*` vs `GEMINI_*` vs module-level globals
7. **No `.env` support** — dotenv not integrated
8. **No Pydantic validation** — No structured config objects
9. **Path bootstrap duplication** — `_paths.py` logic repeated in every conftest

### Minor Issues

10. **No log level controls** — Logging hardcoded to INFO in MCP server
11. **No config example** — No `.env.example` or schema

12. **Version cache global** — `_cached_version` in gemini.py is module-scoped

---

## 10. Recommendations for Standardization

### High Priority

1. **Create `.vaultspec/lib/src/core/config.py`** — Centralized config module
   - Define `VaultSpecConfig` dataclass or Pydantic model
   - All env var names as class attributes (VaultSpecConstants)
   - Type converters and validators

2. **Consolidate test constants** — Create `.vaultspec/tests/constants.py`
   - Define `TEST_PROJECT`, `GPU_FAST_CORPUS_STEMS`, etc.
   - Import in all conftest files

3. **Create config registry** — Document all env vars in one place
   - `.env.example` file
   - ADR on env var naming scheme

### Medium Priority

4. **Add structured logging** — Support `VS_LOG_LEVEL` env var
5. **Migrate to Pydantic** — Type validation + serialization
6. **Create helpers** — `get_config()`, `validate_config()` functions

### Low Priority

7. Add dotenv support (if needed for local dev)
8. Metrics collection on config overrides

---

## Conclusion

The vaultspec project has **ad-hoc environment variable management** with **no unified approach**. There are **15+ env vars** scattered across multiple files, **duplicate constants in tests**, and **manual type conversions**. A centralized `config.py` module with structured defaults, validation, and a registry would:

- Improve discoverability and maintainability
- Reduce bugs from manual type conversions
- Enable better logging and debugging
- Support future env var growth

---
