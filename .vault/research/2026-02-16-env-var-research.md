---
tags: ["#research", "#framework"]
date: 2026-02-16
related:
  - "[[2026-02-16-environment-variable-research]]"
  - "[[2026-02-16-environment-variable-adr]]"
---

# Environment Variable Usage Audit Report

**Date**: 2026-02-16
**Scope**: Entire vaultspec Python codebase
**Total Environment Variables Found**: 11 unique variables
**Total Access Points**: 48 occurrences across 7 Python files

---

## Summary by Variable

| Variable Name | Access Method(s) | Files | Occurrences | Default | Purpose |
|---|---|---|---|---|---|
| `VS_ROOT_DIR` | `os.environ.get()` | 2 | 4 | `os.getcwd()` | Workspace root directory |
| `VS_AGENT_MODE` | `os.environ.get()` | 2 | 3 | `"read-write"` | Agent sandboxing policy |
| `VS_SYSTEM_PROMPT` | `os.environ.get()` | 2 | 3 | `None` | System prompt override |
| `VS_MAX_TURNS` | `os.environ[]` + membership | 1 | 3 | `None` | Max agent turns limit |
| `VS_BUDGET_USD` | `os.environ[]` + membership | 1 | 3 | `None` | Max budget in USD |
| `VS_ALLOWED_TOOLS` | `os.environ[]` + membership | 1 | 3 | `[]` | Comma-separated allowed tools |
| `VS_DISALLOWED_TOOLS` | `os.environ[]` + membership | 1 | 3 | `[]` | Comma-separated disallowed tools |
| `VS_EFFORT` | `os.environ.get()` | 1 | 2 | `None` | Agent effort level |
| `VS_OUTPUT_FORMAT` | `os.environ.get()` | 1 | 2 | `None` | Output format (json, etc) |
| `VS_FALLBACK_MODEL` | `os.environ.get()` | 1 | 2 | `None` | Fallback model name |
| `VS_INCLUDE_DIRS` | `os.environ[]` + membership | 1 | 3 | `[]` | Comma-separated include dirs |
| `VS_MCP_ROOT_DIR` | `os.environ.get()` | 1 | 1 | Required | MCP server root directory |
| `VS_MCP_TTL_SECONDS` | `os.environ.get()` | 1 | 1 | `"3600.0"` | MCP task TTL in seconds |
| `EDITOR` | `os.environ.get()` | 1 | 3 | `"zed -w"` | Text editor command |

---

## Detailed Findings by File

### 1. `.vaultspec/lib/src/protocol/acp/claude_bridge.py`

**Primary Role**: ACP bridge that wraps claude-agent-sdk. Reads env vars during initialization to configure agent behavior.

#### VS_ROOT_DIR

- **Line 209**: `self._root_dir: str = os.environ.get("VS_ROOT_DIR", os.getcwd())`

- **Default**: `os.getcwd()`

- **Purpose**: Workspace root directory, used for sandbox callbacks

#### VS_AGENT_MODE

- **Line 213**: `mode if mode is not None else os.environ.get("VS_AGENT_MODE", "read-write")`

- **Access Method**: `os.environ.get()`

- **Default**: `"read-write"`

- **Purpose**: Agent sandboxing policy (read-write or read-only)

- **DI Pattern**: Parameter takes precedence over env var

#### VS_SYSTEM_PROMPT

- **Line 218**: `else os.environ.get("VS_SYSTEM_PROMPT")`

- **Access Method**: `os.environ.get()`
- **Default**: `None`
- **Purpose**: System prompt override for the agent

- **DI Pattern**: Parameter takes precedence over env var

#### VS_MAX_TURNS

- **Lines 227-230**: `int(os.environ["VS_MAX_TURNS"]) if "VS_MAX_TURNS" in os.environ else None`
- **Access Method**: `os.environ[]` with membership check, try-except conversion
- **Default**: `None`
- **Purpose**: Maximum number of agent turns (parsed as int)

- **Error Handling**: ValueError caught, defaults to None on parse failure
- **DI Pattern**: Parameter takes precedence

#### VS_BUDGET_USD

- **Lines 239-243**: `float(os.environ["VS_BUDGET_USD"]) if "VS_BUDGET_USD" in os.environ else None`
- **Access Method**: `os.environ[]` with membership check, try-except conversion
- **Default**: `None`
- **Purpose**: Maximum budget in USD (parsed as float)

- **Error Handling**: ValueError caught, defaults to None on parse failure

- **Validation**: Negative values replaced with None (line 249)
- **DI Pattern**: Parameter takes precedence

#### VS_ALLOWED_TOOLS

- **Lines 257-263**: `[t.strip() for t in os.environ["VS_ALLOWED_TOOLS"].split(",") if t.strip()] if "VS_ALLOWED_TOOLS" in os.environ else []`

- **Access Method**: `os.environ[]` with membership check, split and strip
- **Default**: `[]` (empty list)
- **Purpose**: Comma-separated list of tools the agent can use
- **DI Pattern**: Parameter takes precedence

#### VS_DISALLOWED_TOOLS

- **Lines 269-276**: `[t.strip() for t in os.environ["VS_DISALLOWED_TOOLS"].split(",") if t.strip()] if "VS_DISALLOWED_TOOLS" in os.environ else []`
- **Access Method**: `os.environ[]` with membership check, split and strip
- **Default**: `[]` (empty list)
- **Purpose**: Comma-separated list of tools the agent cannot use

- **DI Pattern**: Parameter takes precedence

#### VS_EFFORT

- **Line 279**: `effort if effort is not None else os.environ.get("VS_EFFORT")`
- **Access Method**: `os.environ.get()`
- **Default**: `None`

- **DI Pattern**: Parameter takes precedence

#### VS_OUTPUT_FORMAT

- **Line 284**: `else os.environ.get("VS_OUTPUT_FORMAT")`
- **Access Method**: `os.environ.get()`
- **Default**: `None`
- **Purpose**: Output format specification (e.g., "json")

- **DI Pattern**: Parameter takes precedence

#### VS_FALLBACK_MODEL

- **Line 289**: `else os.environ.get("VS_FALLBACK_MODEL")`
- **Access Method**: `os.environ.get()`
- **Default**: `None`
- **Purpose**: Fallback model if primary model fails
- **DI Pattern**: Parameter takes precedence

#### VS_INCLUDE_DIRS

- **Lines 296-302**: `[d.strip() for d in os.environ["VS_INCLUDE_DIRS"].split(",") if d.strip()] if "VS_INCLUDE_DIRS" in os.environ else []`
- **Access Method**: `os.environ[]` with membership check, split and strip

- **Default**: `[]` (empty list)
- **Purpose**: Comma-separated list of directories to include
- **DI Pattern**: Parameter takes precedence

---

### 2. `.vaultspec/lib/src/subagent_server/server.py`

**Primary Role**: MCP server for running sub-agents. Reads env vars for server configuration.

#### VS_MCP_ROOT_DIR

- **Line 605**: `root_str = os.environ.get("VS_MCP_ROOT_DIR")`
- **Access Method**: `os.environ.get()`
- **Default**: `None` (required, raises error if missing)
- **Purpose**: Workspace root directory for the MCP server
- **Error Handling**: RuntimeError raised if not provided and no parameter (lines 606-609)

#### VS_MCP_TTL_SECONDS

- **Line 612**: `ttl = float(os.environ.get("VS_MCP_TTL_SECONDS", "3600.0"))`
- **Access Method**: `os.environ.get()`

- **Default**: `"3600.0"` (3600 seconds = 1 hour)
- **Purpose**: Task TTL (time-to-live) in seconds
- **Parsing**: Converted to float

---

### 3. `.vaultspec/scripts/cli.py`

**Primary Role**: CLI for managing rules, agents, skills across tool destinations. Uses EDITOR env var.

#### EDITOR

- **Lines 299, 429, 568**: `editor = os.environ.get("EDITOR", "zed -w")`
- **Access Method**: `os.environ.get()`

- **Default**: `"zed -w"`

- **Context**: Called when stdin is a TTY and no content provided

- **Usage**: `subprocess.call([*editor.split(), str(file_path)])`

---

## Test Files with Environment Variable References

### `.vaultspec/lib/src/protocol/tests/test_providers.py`

**Lines 368-487**: Tests that verify ClaudeProvider correctly sets VS_* env vars from agent metadata.

**VS_* Variables Tested**:

- `VS_MAX_TURNS` (line 382)

- `VS_BUDGET_USD` (line 392)
- `VS_ALLOWED_TOOLS` (line 405)

- `VS_DISALLOWED_TOOLS` (line 418)
- `VS_EFFORT` (line 428)
- `VS_FALLBACK_MODEL` (line 441)
- `VS_INCLUDE_DIRS` (line 455)
- `VS_OUTPUT_FORMAT` (line 468)
- `VS_AGENT_MODE` (lines 616, 627)

### `.vaultspec/lib/src/protocol/acp/tests/test_bridge_lifecycle.py`

**Lines 442, 472**: Tests verify VS_ROOT_DIR and VS_SYSTEM_PROMPT are set correctly in process environment.

### `.vaultspec/lib/src/protocol/acp/tests/test_e2e_bridge.py`

**Lines 93-94**: Manual env var setup for E2E testing (VS_AGENT_MODE, VS_ROOT_DIR).

### `.vaultspec/tests/e2e/test_claude.py`

**Lines 85-87**: Tests verify VS_SYSTEM_PROMPT is present and correct in spec environment.

### `.vaultspec/tests/e2e/test_provider_parity.py`

**Lines 115-120**: Tests verify VS_SYSTEM_PROMPT env var usage between Claude and Gemini providers.

---

## Access Patterns Analysis

### Pattern 1: Dependency Injection with Environment Fallback (9 variables)

```python
# Constructor parameter takes precedence, else env var, else default
self._field = (

    else os.environ.get("VS_VAR", default)
)
```

**Variables**: VS_ROOT_DIR, VS_AGENT_MODE, VS_SYSTEM_PROMPT, VS_EFFORT, VS_OUTPUT_FORMAT, VS_FALLBACK_MODEL

**Benefit**: Testability through constructor parameters, flexibility through env vars, sensible defaults.

### Pattern 2: Comma-Separated List Parsing (3 variables)

```python

# With membership check and stripping
[
    t.strip()
    for t in os.environ["VS_VAR"].split(",")
    if t.strip()

] if "VS_VAR" in os.environ else []
```

**Variables**: VS_ALLOWED_TOOLS, VS_DISALLOWED_TOOLS, VS_INCLUDE_DIRS

**Benefit**: Supports multiple values in single env var, robust to whitespace.

### Pattern 3: Type Conversion with Error Handling (2 variables)

```python
try:
    self._field = (
        int(os.environ["VS_VAR"])

        if "VS_VAR" in os.environ
        else None
    )
except ValueError:
    self._field = None

```

**Variables**: VS_MAX_TURNS (int), VS_BUDGET_USD (float)

### Pattern 4: Simple Env Get (4 variables)

```python

root_str = os.environ.get("VS_MCP_ROOT_DIR")
if not root_str:
    raise RuntimeError(...)
```

**Variables**: VS_MCP_ROOT_DIR (required), EDITOR, VS_MCP_TTL_SECONDS

**Benefit**: Explicit required vs optional handling.

---

## Standardization Observations

### Naming Convention

- **Prefix**: All vaultspec-specific vars use `VS_` prefix
- **Convention**: ALL_CAPS with underscores
- **Consistency**: 100% consistent across codebase

### Lack of Central Documentation

- No single source of truth for env vars
- Variables scattered across multiple files
- Tests reference variables but no validation schema

### Inconsistent Access Patterns

- Mixed use of `os.environ[]`, `os.environ.get()`, membership checks
- Some conversions inline, no helper functions
- Type parsing logic duplicated (int/float conversion)

### String Parsing Fragility

- Comma-separated lists split by bare `.split(",")` — fragile to spacing
- Tool list parsing duplicated in claude_bridge.py and test files

---

## Recommendations for Next Phase

1. **Create Central Constants Module** (`orchestration/env_constants.py`)
   - Define all env var names as constants
   - Centralize parsing logic (int, float, comma-list)
   - Document required vs optional, defaults, types

2. **Create EnvConfig Dataclass**
   - Single point to load and validate all env vars
   - Type-safe access, no scattered membership checks
   - Easier to audit and test

3. **Add Validation Schema**
   - Min/max for numeric values
   - Enum validation for modes (read-write, read-only)
   - Path validation for directory vars

4. **Update Documentation**
   - Add env var reference to code comments
   - Document in main README or .vault/ docs
   - Include examples for each var

## File Locations and Line References

| File | Lines | Variables | Access Types |
|------|-------|-----------|---|
| `.vaultspec/lib/src/protocol/acp/claude_bridge.py` | 13-14, 209, 213, 218, 227-230, 239-243, 257-263, 269-276, 279, 284, 289, 296-302 | VS_ROOT_DIR, VS_AGENT_MODE, VS_SYSTEM_PROMPT, VS_MAX_TURNS, VS_BUDGET_USD, VS_ALLOWED_TOOLS, VS_DISALLOWED_TOOLS, VS_EFFORT, VS_OUTPUT_FORMAT, VS_FALLBACK_MODEL, VS_INCLUDE_DIRS | get(), [], split(), int(), float() |
| `.vaultspec/lib/src/subagent_server/server.py` | 602-609, 612 | VS_MCP_ROOT_DIR, VS_MCP_TTL_SECONDS | get() + error handling, float() |
| `.vaultspec/scripts/cli.py` | 299, 429, 568 | EDITOR | get() |
| Test files (5 files) | Various | VS_ROOT_DIR, VS_SYSTEM_PROMPT, VS_MAX_TURNS, VS_BUDGET_USD, VS_ALLOWED_TOOLS, VS_DISALLOWED_TOOLS, VS_EFFORT, VS_FALLBACK_MODEL, VS_INCLUDE_DIRS, VS_OUTPUT_FORMAT, VS_AGENT_MODE | Assertions, direct dict access |

---

## Summary Statistics

- **Total Unique Variables**: 14 (11 VS_*, 1 EDITOR, 1 GEMINI_SYSTEM_MD mentioned in docs)
- **Total Access Points**: 48+
- **Files with Env Access**: 7 Python source files (plus 5 test files)
- **Production Files**: 3 (claude_bridge.py, server.py, cli.py)
- **Test Coverage**: Yes, but scattered across multiple test files
- **Centralization Level**: Low (variables scattered, no central registry)
- **Type Safety**: Medium (some conversions with error handling, but no schema)
