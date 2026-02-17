# Environment Audit Task #2: Hardcoded Constants Report

**Date**: 2026-02-16
**Status**: Complete
**Scope**: Python codebase in `.vaultspec/lib/src/`, `.vaultspec/scripts/`, protocol modules

---

## Executive Summary

Found **38+ hardcoded configuration values** across 15+ files that should be environment-configurable. Most critical findings:

- **Port Numbers**: 10+ hardcoded test/dev ports (10010, 10001-10093 range) with no production configuration
- **File Paths**: Directory constants hardcoded (`.lance`, `.vault`, `.claude`, `.vaultspec`, `.gemini`)
- **Timeouts/TTLs**: Three timeout values hardcoded (3600s, 300s, 8192 bytes)
- **Batch Sizes**: Embedding batch size fixed at 64 docs, max embed chars at 8000
- **Buffer Sizes**: I/O buffer hardcoded to 8192 bytes
- **Host/Port Defaults**: Test infrastructure uses localhost:10010 baseline

### Risk Assessment

- **HIGH**: TTL configurations (no way to tune task retention without code change)
- **HIGH**: Port numbers in discovery/A2A modules (deployment conflicts)
- **MEDIUM**: Batch sizes and buffer limits (performance tuning blocked)
- **MEDIUM**: Directory paths (multi-project layouts not supported)
- **LOW**: Most timeouts (test-only values)

---

### 1. PORT NUMBERS (High Risk for Deployment)

#### 1.1 A2A Agent Card Default Port

- **File**: `.vaultspec/lib/src/protocol/a2a/agent_card.py:10`

- **Context**: Default port for A2A agent card URL generation

- **Usage**: `agent_card_from_definition(agent_name, agent_meta, host="localhost", port=10010)`
- **Env Var**: `VAULTSPEC_A2A_DEFAULT_PORT` (default: 10010)

- **Risk**: MEDIUM - hardcoded in function signature, affects all A2A deployments
- **Note**: Also appears as discovery endpoint base

#### 1.2 A2A Discovery Default Port

- **File**: `.vaultspec/lib/src/protocol/a2a/discovery.py:48`
- **Value**: `port: int = 10010`

- **Context**: Gemini CLI agent discovery markdown generation

- **Usage**: `write_agent_discovery(root_dir, agent_name, host="localhost", port=10010)`
- **Env Var**: `VAULTSPEC_A2A_DISCOVERY_PORT` (default: 10010)

- **Risk**: MEDIUM - CLI agents won't be discoverable if port changes

#### 1.3 Subagent MCP Server Port

- **File**: `.vaultspec/scripts/subagent.py:265`

- **Context**: MCP server listen port
- **Current**: Already parameterized via `--port` CLI arg, defaults to 10010
- **Env Var**: `VAULTSPEC_MCP_PORT` (default: 10010)

- **Risk**: LOW - already CLI-configurable, but should add env var fallback
- **Code**: `uvicorn.run(app, host="0.0.0.0", port=port)` (line 181)

#### 1.4 Test Port Range (10001-10093)

- **Files**: Multiple test files in `.vaultspec/lib/src/protocol/a2a/tests/`
  - `test_integration_a2a.py`: ports 10001-10093 (14+ unique values)
  - `test_e2e_a2a.py`: ports 10020-10093 (10+ unique values)
  - `test_unit_a2a.py`: port 10020

- **Risk**: LOW - test-only, but should use dynamic port allocation (port=0)

### 2. HOST ADDRESSES (Medium Risk)

#### 2.1 Localhost Default

- **File**: `.vaultspec/lib/src/protocol/a2a/discovery.py:47`

- **Value**: `host: str = "localhost"`
- **Context**: A2A agent discovery host

- **Env Var**: `VAULTSPEC_A2A_HOST` (default: "localhost")
- **Risk**: MEDIUM - prevents external agent discovery in multi-host deployments

#### 2.2 Agent Card Host

- **File**: `.vaultspec/lib/src/protocol/a2a/agent_card.py:9`
- **Value**: `host: str = "localhost"`

- **Context**: Agent card URL generation

- **Env Var**: `VAULTSPEC_A2A_HOST` (shared with discovery)
- **Risk**: MEDIUM - same as above

#### 2.3 MCP Server Host

- **File**: `.vaultspec/scripts/subagent.py:181`

- **Value**: `host="0.0.0.0"`

- **Context**: uvicorn binding address

- **Env Var**: `VAULTSPEC_MCP_HOST` (default: "0.0.0.0")

- **Risk**: LOW - 0.0.0.0 is appropriate for servers, but should be configurable

#### 2.4 E2E Test Host

- **File**: `.vaultspec/lib/src/protocol/a2a/tests/test_e2e_a2a.py:138`
- **Value**: `host="0.0.0.0"`

- **Context**: Test A2A server binding

- **Risk**: LOW - test-only

### 3. FILE PATHS & DIRECTORIES (Medium Risk)

#### 3.1 Lance Database Path

- **File**: `.vaultspec/lib/src/rag/store.py:122`
- **Value**: `".lance"` (relative to root_dir)

- **Full**: `self.db_path = self.root_dir / ".lance"`

- **Env Var**: `VAULTSPEC_LANCE_DIR` (default: ".lance")

- **Risk**: MEDIUM - multi-project layouts need different paths
- **Impact**: Only 1 vector store per root_dir; can't have side-by-side .lance-test variants

#### 3.2 Index Metadata Path

- **File**: `.vaultspec/lib/src/rag/indexer.py:118`

- **Value**: `".lance/index_meta.json"`
- **Full**: `self._meta_path = root_dir / ".lance" / "index_meta.json"`
- **Status**: Depends on LANCE_DIR above

- **Env Var**: `VAULTSPEC_INDEX_METADATA_FILE` (default: "index_meta.json")

- **Risk**: MEDIUM - tied to lance location

#### 3.3 Vault Docs Directory

- **File**: `.vaultspec/lib/src/vault/models.py:106` (VaultConstants)
- **Value**: `DOCS_DIR = ".vault"`
- **Usage**: Throughout RAG, indexing, search modules

- **Env Var**: `VAULTSPEC_DOCS_DIR` (default: ".vault")

- **Risk**: HIGH - used across entire RAG pipeline
- **Files**: ~15 references across codebase

#### 3.4 Vaultspec Framework Dirs

- **File**: `.vaultspec/scripts/cli.py:145-151`

- **Values**: All relative to `.vaultspec/`:
  - `.vaultspec/rules`
  - `.vaultspec/rules-custom`

  - `.vaultspec/agents`

  - `.vaultspec/skills`
  - `.vaultspec/system`
  - `.vaultspec/FRAMEWORK.md`

  - `.vaultspec/PROJECT.md`
- **Current**: Hardcoded in `init_paths(root: Path)`

- **Env Var**: All should use `VAULTSPEC_FRAMEWORK_DIR` (default: ".vaultspec")

- **Risk**: LOW - rarely changed, but framework should be relocatable

#### 3.5 Tool Config Dirs

- **File**: `.vaultspec/scripts/cli.py:170-190`
- **Values**:
  - `.claude/rules`, `.claude/agents`, `.claude/skills`, `.claude/CLAUDE.md`

  - `.gemini/rules`, `.gemini/agents`, `.gemini/skills`, `.gemini/settings.json`

- **Current**: Hardcoded per tool in `TOOL_CONFIGS` dict

- **Env Var**: `VAULTSPEC_CLAUDE_DIR`, `VAULTSPEC_GEMINI_DIR`, etc.

- **Risk**: MEDIUM - multi-tool setups need layout flexibility

- **File**: `.vaultspec/lib/src/protocol/a2a/discovery.py:58`

- **Value**: `.gemini/agents/` directory

- **Full**: `agents_dir = root_dir / ".gemini" / "agents"`

- **Env Var**: Covered by `VAULTSPEC_GEMINI_DIR`

- **Risk**: MEDIUM - same as tool config above

#### 3.7 Test Lance Directories

- **File**: `.vaultspec/lib/src/rag/tests/conftest.py:104`

- **Pattern**: `f".lance{lance_suffix}"` for different test scopes

- **Env Var**: `VAULTSPEC_TEST_LANCE_SUFFIX` (default: "-fast", "-full", "-fast-unit")

- **Risk**: LOW - test-only, but helps avoid collision

### 4. TIMEOUTS & DELAYS (High Risk for Operations)

#### 4.1 MCP Task TTL (Task Retention)

- **File**: `.vaultspec/lib/src/subagent_server/server.py:85,612`

- **Value**: `3600.0` seconds (1 hour)

- **Context**: Task retention period before automatic cleanup

- **Current**: Partially configurable via env var
  - Line 612: `ttl = float(os.environ.get("VS_MCP_TTL_SECONDS", "3600.0"))`
  - Line 85: Default param in function signature
- **Env Var**: `VS_MCP_TTL_SECONDS` (ALREADY EXISTS, default: "3600.0")
- **Risk**: HIGH - no way to change retention without env var knowledge

- **Note**: Good pattern! Should replicate for other timeouts

#### 4.2 Task Engine TTL

- **File**: `.vaultspec/lib/src/orchestration/task_engine.py:231`
- **Value**: `ttl_seconds: float = 3600.0`

- **Context**: TTL parameter in TaskEngine init
- **Current**: Not environment-configured directly

- **Env Var**: Should use `VS_TASK_ENGINE_TTL_SECONDS` (default: "3600.0")
- **Risk**: HIGH - orchestration layer TTL not tunable

#### 4.3 VaultSearcher Graph TTL

- **File**: `.vaultspec/lib/src/rag/search.py:163`

- **Value**: `graph_ttl_seconds: float = 300.0`
- **Context**: How long to cache VaultGraph before rebuilding
- **Current**: Not environment-configured
- **Env Var**: `VAULTSPEC_GRAPH_TTL_SECONDS` (default: "300.0")
- **Risk**: MEDIUM - affects search performance but not critical

#### 4.4 ACP Bridge Timeout (Read)

- **File**: `.vaultspec/lib/src/protocol/acp/tests/test_e2e_bridge.py:179`

- **Value**: `timeout: float = 10.0` seconds
- **Context**: Test helper for reading ACP messages
- **Risk**: LOW - test-only helper

#### 4.5 ACP Bridge Timeout (Full Message)

- **File**: `.vaultspec/lib/src/protocol/acp/tests/test_e2e_bridge.py:196`
- **Value**: `timeout: float = 30.0` seconds

- **Risk**: LOW - test-only

#### 4.6 Test Sleep Delays

- Multiple locations with hardcoded sleep values:
  - `.vaultspec/tests/subagent/test_mcp_protocol.py:277`: `asyncio.sleep(0.2)`
  - `.vaultspec/tests/e2e/test_mcp_e2e.py:129`: `asyncio.sleep(1.0)`
  - `.vaultspec/lib/src/protocol/acp/tests/test_e2e_bridge.py:248`: `asyncio.sleep(0.3)`

- **Risk**: LOW - test timing, but should use fixtures

### 5. BATCH SIZES & BUFFER LIMITS (Medium Risk for Performance)

#### 5.1 Embedding Batch Size

- **File**: `.vaultspec/lib/src/rag/embeddings.py:95`
- **Value**: `DEFAULT_BATCH_SIZE = 64`
- **Context**: Texts per encoding batch to GPU

- **Current**: Tunable via `batch_size` parameter in `encode_documents()`
- **Env Var**: `VAULTSPEC_EMBEDDING_BATCH_SIZE` (default: "64")
- **Risk**: MEDIUM - performance tuning blocked without code knowledge
- **Impact**: 64 docs/batch works for RTX 4080 SUPER, may fail on smaller GPUs

#### 5.2 Max Embed Characters

- **File**: `.vaultspec/lib/src/rag/embeddings.py:101`
- **Value**: `MAX_EMBED_CHARS = 8000`
- **Context**: Max characters to embed per document (truncation)

- **Comment**: "~8000 chars ≈ 2000 words ≈ 2600 tokens"
- **Env Var**: `VAULTSPEC_MAX_EMBED_CHARS` (default: "8000")
- **Risk**: MEDIUM - affects embedding quality vs. latency trade-off
- **Note**: Full text still stored in LanceDB for BM25 search

#### 5.3 I/O Read Buffer Size

- **File**: `.vaultspec/lib/src/protocol/acp/client.py:340`
- **Value**: `chunk = await proc.stdout.read(8192)`
- **Context**: ACP subprocess stdout read buffer
- **Env Var**: `VAULTSPEC_IO_BUFFER_SIZE` (default: "8192")
- **Risk**: MEDIUM - high-throughput ACP clients may need larger buffer

- **Impact**: 8192 bytes = 8KB chunks, could cause excessive wake-ups

#### 5.4 Output Byte Limit (Terminal Output)

- **File**: `.vaultspec/lib/src/protocol/acp/client.py:334`
- **Value**: `output_byte_limit or 1_000_000`
- **Context**: Max terminal output to capture (1MB default)
- **Current**: Already parameterized in function, but hardcoded default
- **Env Var**: `VAULTSPEC_TERMINAL_OUTPUT_LIMIT` (default: "1000000")

- **Risk**: LOW - already has parameter, needs env var fallback

### 6. PYTEST TIMEOUTS (Low Risk - Test Infrastructure)

Multiple pytest test markers with hardcoded timeouts:

- `.vaultspec/tests/e2e/test_gemini.py`: `@pytest.mark.timeout(60)`
- `.vaultspec/tests/e2e/test_full_cycle.py`: `@pytest.mark.timeout(180)`
- `.vaultspec/tests/e2e/test_claude.py`: `@pytest.mark.timeout(60)`
- `.vaultspec/lib/src/protocol/acp/tests/test_e2e_bridge.py`: `@pytest.mark.timeout(15)`

- `.vaultspec/lib/src/protocol/a2a/tests/test_e2e_a2a.py`: Multiple `@pytest.mark.timeout(180)`, `(300)`

**Risk**: LOW - test timeouts, but should use pytest.ini or environment variable

### 7. VERSION CONSTANTS (Low Risk - Reference Only)

#### 7.1 Gemini CLI Version Requirements

- **File**: `.vaultspec/lib/src/protocol/providers/gemini.py:36-37`
- **Values**:
  - `_MIN_VERSION_WINDOWS = (0, 9, 0)` - Windows ACP hang fix

  - `_MIN_VERSION_RECOMMENDED = (0, 27, 0)` - Stable agent skills
- **Env Var**: `VAULTSPEC_GEMINI_MIN_VERSION_WINDOWS`, `VAULTSPEC_GEMINI_MIN_VERSION_RECOMMENDED`
- **Risk**: LOW - rarely changes, reference values only
- **Note**: These represent Gemini CLI version constraints, not configurable at runtime

---

## Summary Table: Recommendations by Priority

| Category | Count | Env Vars Needed | Priority | Already Configurable |
|----------|-------|-----------------|----------|----------------------|
| Ports | 5 | 3 | HIGH | Partial (--port CLI) |

| Hosts | 4 | 2 | MEDIUM | No |
| Paths (dirs) | 7 | 7 | HIGH | No (hardcoded) |
| Paths (files) | 3 | 2 | MEDIUM | No |
| Timeouts/TTLs | 6 | 4 | HIGH | 1/6 (VS_MCP_TTL_SECONDS) |
| Batch/Buffer | 4 | 4 | MEDIUM | 1/4 (batch_size param only) |

| Version refs | 2 | 0 | LOW | N/A (reference only) |
| **TOTAL** | **31** | **22** | — | **2/31** |

---

## Recommended Environment Variables (VAULTSPEC_ Prefix Convention)

### Tier 1: CRITICAL (Deploy to production immediately)

```bash
# MCP Server Configuration

VAULTSPEC_MCP_PORT=10010                    # MCP listen port (default: 10010)
VAULTSPEC_MCP_HOST=0.0.0.0                  # MCP bind address (default: 0.0.0.0)
VAULTSPEC_MCP_TTL_SECONDS=3600.0            # Task retention (ALREADY EXISTS as VS_MCP_TTL_SECONDS)

# A2A Agent Configuration
VAULTSPEC_A2A_DEFAULT_PORT=10010            # A2A card port (default: 10010)

VAULTSPEC_A2A_HOST=localhost                # A2A discovery host (default: localhost)

# Framework Directories
VAULTSPEC_DOCS_DIR=.vault                   # Vault docs path (default: .vault)
VAULTSPEC_FRAMEWORK_DIR=.vaultspec          # Framework path (default: .vaultspec)
VAULTSPEC_LANCE_DIR=.lance                  # Vector store path (default: .lance)

```

### Tier 2: HIGH (Production + CI/CD flexibility)

```bash

# Task Engine Configuration
VAULTSPEC_TASK_ENGINE_TTL_SECONDS=3600.0    # Task cleanup TTL (default: 3600)

# RAG/Search Configuration
VAULTSPEC_EMBEDDING_BATCH_SIZE=64           # GPU batch size (default: 64)
VAULTSPEC_MAX_EMBED_CHARS=8000              # Max chars per embed (default: 8000)
VAULTSPEC_GRAPH_TTL_SECONDS=300.0           # VaultGraph cache TTL (default: 300)

# I/O Configuration
VAULTSPEC_IO_BUFFER_SIZE=8192               # Read buffer size (default: 8192)
VAULTSPEC_TERMINAL_OUTPUT_LIMIT=1000000     # Terminal output cap (default: 1MB)

```

### Tier 3: MEDIUM (Tool integration)

```bash
# Tool-specific Directories

VAULTSPEC_CLAUDE_DIR=.claude                # Claude config path (default: .claude)
VAULTSPEC_GEMINI_DIR=.gemini                # Gemini config path (default: .gemini)
VAULTSPEC_ANTIGRAVITY_DIR=.antigravity      # Antigravity config path (default: .antigravity)
```

### Tier 4: LOW (Reference, test configuration)

```bash
# Gemini CLI Version Requirements (reference, not configurable at runtime)
VAULTSPEC_GEMINI_MIN_VERSION_WINDOWS=0.9.0
VAULTSPEC_GEMINI_MIN_VERSION_RECOMMENDED=0.27.0


# Test Configuration (pytest)
PYTEST_TIMEOUT=180                          # Global pytest timeout
VAULTSPEC_TEST_LANCE_SUFFIX=-fast           # Test vector DB suffix
```

---

## Implementation Strategy

### Phase 1: Low-Risk Wins

1. Add `VAULTSPEC_MCP_PORT` env var fallback (already has CLI flag)
2. Add `VAULTSPEC_MCP_HOST` env var (currently hardcoded to 0.0.0.0)
3. Add `VAULTSPEC_EMBEDDING_BATCH_SIZE` env var (already parameterized)
4. Verify `VS_MCP_TTL_SECONDS` documentation

### Phase 2: Medium-Risk Refactors

1. Create `vaultspec/config.py` with centralized constants module
2. Refactor `.lance` path to use `VAULTSPEC_LANCE_DIR` env var
3. Refactor `.vault` path to use `VAULTSPEC_DOCS_DIR` env var
4. Add host/port configuration for A2A modules

### Phase 3: Framework Restructuring

1. Support `VAULTSPEC_FRAMEWORK_DIR` for relocatable framework
2. Support tool-specific directory env vars (`.claude`, `.gemini`, `.antigravity`)
3. Update CLI to use environment variables as fallback for all paths

### Phase 4: Documentation & Testing

1. Create `.env.example` with all Tier 1-2 env vars
2. Add env var reference to README
3. Add integration tests for env var fallback paths

---

## Code Changes Reference

### Key Files to Modify

1. **`.vaultspec/lib/src/subagent_server/server.py`**
   - Already reads `VS_MCP_TTL_SECONDS` (line 612)
   - Need to add: `VAULTSPEC_MCP_PORT`, `VAULTSPEC_MCP_HOST` fallback

2. **`.vaultspec/lib/src/rag/store.py`**
   - Hardcoded `.lance` at line 122
   - Change to: `os.environ.get("VAULTSPEC_LANCE_DIR", ".lance")`

3. **`.vaultspec/lib/src/rag/embeddings.py`**
   - Hardcoded `DEFAULT_BATCH_SIZE = 64` at line 95
   - Hardcoded `MAX_EMBED_CHARS = 8000` at line 101
   - Add env var fallback in class init or function calls

4. **`.vaultspec/lib/src/rag/search.py`**
   - Hardcoded `graph_ttl_seconds: float = 300.0` at line 163
   - Add env var fallback in `__init__`

5. **`.vaultspec/lib/src/protocol/a2a/agent_card.py`**
   - Hardcoded defaults `host="localhost"`, `port=10010` at lines 9-10
   - Add env var fallback in function signature

6. **`.vaultspec/lib/src/protocol/a2a/discovery.py`**
   - Hardcoded defaults `host="localhost"`, `port=10010` at lines 47-48
   - Add env var fallback in function signature

7. **`.vaultspec/scripts/subagent.py`**
   - Hardcoded `host="0.0.0.0"` at line 181
   - Add env var fallback before `uvicorn.run()`

---

## Metrics

- **Total Hardcoded Constants Found**: 38+
- **Already Environment-Configurable**: 2 (VS_MCP_TTL_SECONDS, batch_size parameter)
- **Partially Configurable (CLI only)**: 3 (--port, --root, context_files)
- **Requires Environment Variable Addition**: 22
- **Codebase Coverage**: ~15 files across 3 modules (rag, protocol, orchestration, scripts)

---

## Validation Checklist

- [ ] All Tier 1 env vars implemented and tested
- [ ] `.env.example` created with documentation
- [ ] README updated with env var reference section
- [ ] Integration tests verify env var fallback paths work
- [ ] Multi-project layout test with different VAULTSPEC_LANCE_DIR values
- [ ] Port conflict test with VAULTSPEC_MCP_PORT and VAULTSPEC_A2A_DEFAULT_PORT
- [ ] GPU memory pressure test with VAULTSPEC_EMBEDDING_BATCH_SIZE tuning
- [ ] Backward compatibility verified (all defaults match current hardcoded values)

---

## Next Steps

1. **Team Lead**: Review findings and prioritize by deployment needs
2. **Implementer**: Start with Phase 1 (MCP port/host) for quick wins
3. **QA**: Validate env var fallback paths don't break existing workflows
4. **DevOps**: Prepare deployment configuration with standardized env vars
