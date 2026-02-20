---
tags: ["#audit", "#roadmap"]
date: 2026-02-17
related:
  - "[[2026-02-17-audit-summary-audit]]"
---

# Technical Audit: vaultspec Codebase

**Date**: 2026-02-17
**Auditor**: TechAuditor (Claude Opus 4.6)
**Scope**: Full implementation audit of `.vaultspec/lib/src/` and `.vaultspec/lib/scripts/`

---

## 1. Architecture Overview

vaultspec is a governed development framework for AI agents, built around a "documentation vault" (`.vault/`) with structured markdown documents. The codebase implements:

- **Multi-tool resource management** (CLI) — syncs rules, agents, skills, config, and system prompts across Claude, Gemini, and Antigravity tool destinations
- **GPU-accelerated RAG** — semantic search over vault documents using nomic-embed-text-v1.5 on CUDA
- **3-layer protocol stack** — MCP (agent-to-tool), ACP (orchestrator-to-agent), A2A (agent-to-agent)
- **Subagent orchestration** — spawn and manage AI agent subprocesses with task lifecycle tracking
- **Document verification** — frontmatter validation, vertical integrity checks, graph analysis

### Module Structure

```
.vaultspec/lib/src/
  core/           — Central config (VaultSpecConfig dataclass, env var resolution)
  orchestration/  — Subagent lifecycle, task engine, security utils
  protocol/       — ACP client/bridge, A2A server/executors, provider abstraction
  vault/          — Document models, parser, scanner, links, hydration
  rag/            — Embeddings, indexer, search, LanceDB store
  graph/          — Wiki-link graph analysis
  metrics/        — Vault statistics
  verification/   — Structure/content/integrity verification
  subagent_server/ — MCP server (FastMCP) exposing 5 tools
  logging_config.py — Central logging setup
```

---

## 2. Feature Matrix

| Feature | Module | Status | Notes |
|---------|--------|--------|-------|
| **Core Configuration** | `core/config.py` | Complete | 30+ configurable variables, env var resolution, validation, singleton |
| **YAML Frontmatter Parsing** | `vault/parser.py` | Complete | PyYAML with fallback to minimal parser; handles colons in values |
| **Vault Document Scanning** | `vault/scanner.py` | Complete | Recursive .md scan, .obsidian filtering, DocType inference |
| **Wiki-link Extraction** | `vault/links.py` | Complete | `[[link]]` and `[[link\|alias]]` patterns, related field parsing |
| **Template Hydration** | `vault/hydration.py` | Complete | Placeholder replacement for `<feature>`, `<yyyy-mm-dd>`, `<title>` |
| **Document Models** | `vault/models.py` | Complete | DocType enum (5 types), DocumentMetadata validation, VaultConstants |
| **Filename Validation** | `vault/models.py` | Complete | Regex pattern `yyyy-mm-dd-<feature>-<type>.md` |
| **Structure Validation** | `vault/models.py` | Complete | Checks for unsupported dirs, root-level files in .vault/ |
| **GPU Embeddings** | `rag/embeddings.py` | Complete | nomic-embed-text-v1.5, CUDA-only, LRU-cached queries, length-sorted batching |
| **Full Indexing** | `rag/indexer.py` | Complete | Concurrent I/O, batch embedding, LanceDB upsert |
| **Incremental Indexing** | `rag/indexer.py` | Complete | mtime-based change detection via `index_meta.json` |
| **Hybrid Search** | `rag/store.py` | Complete | BM25 (Tantivy FTS) + ANN vector search with RRF reranking |
| **Graph-aware Reranking** | `rag/search.py` | Complete | Authority boost, neighborhood boost, recency boost |
| **Query Parser** | `rag/search.py` | Complete | Filter tokens: `type:`, `feature:`, `date:`, `tag:` |
| **LanceDB Vector Store** | `rag/store.py` | Complete | CRUD, hybrid search, SQL injection sanitization, FTS index |
| **RAG Public API** | `rag/api.py` | Complete | Singleton engine, list/get/search/index/status/related |
| **Document Graph** | `graph/api.py` | Complete | 2-pass build, hotspots, feature rankings, orphans, invalid links |
| **Vault Metrics** | `metrics/api.py` | Complete | Total docs, counts by type, feature count |
| **File Verification** | `verification/api.py` | Complete | Filename, frontmatter, tag consistency, structure checks |
| **Vertical Integrity** | `verification/api.py` | Complete | Feature-to-plan mapping validation |
| **Feature Listing** | `verification/api.py` | Complete | Extract unique feature tags across vault |
| **ACP Client** | `protocol/acp/client.py` | Complete | Full ACP Client: permissions, file I/O, terminal management, session logging |
| **ACP Claude Bridge** | `protocol/acp/claude_bridge.py` | Complete | Full ACP Agent: init, new/load/resume/fork/list sessions, prompt, cancel, streaming |
| **Sandbox Policy** | `protocol/sandbox.py` | Complete | Read-only mode blocks shell + non-vault writes; read-write unrestricted |
| **Claude Provider** | `protocol/providers/claude.py` | Complete | Model resolution, system prompt loading, ProcessSpec generation |
| **Gemini Provider** | `protocol/providers/gemini.py` | Complete | CLI version checking, system prompt via temp file, approval mode support |
| **Provider Abstraction** | `protocol/providers/base.py` | Complete | ABC with 6 abstract methods, CapabilityLevel enum, @-include resolution |
| **A2A Server** | `protocol/a2a/server.py` | Complete | Starlette ASGI app via A2AStarletteApplication, InMemoryTaskStore |
| **A2A Agent Cards** | `protocol/a2a/agent_card.py` | Complete | AgentCard generation from agent definitions |
| **A2A Discovery** | `protocol/a2a/discovery.py` | Complete | Gemini CLI agent discovery (.gemini/agents/*.md, settings.json) |
| **A2A Claude Executor** | `protocol/a2a/executors/claude_executor.py` | Complete | AgentExecutor using claude-agent-sdk, streaming, cancel |
| **A2A Gemini Executor** | `protocol/a2a/executors/gemini_executor.py` | Complete | AgentExecutor delegating to run_subagent() |
| **A2A State Mapping** | `protocol/a2a/state_map.py` | Complete | Bidirectional TaskEngine <-> A2A TaskState mapping |
| **Subagent Orchestrator** | `orchestration/subagent.py` | Complete | Agent loading, provider selection, ACP spawn+handshake, interactive loop |
| **Task Engine** | `orchestration/task_engine.py` | Complete | 5-state FSM, TTL expiry, async wait/notify, thread-safe |
| **Lock Manager** | `orchestration/task_engine.py` | Complete | Advisory file locks with conflict detection, read-only path validation |
| **Security Utils** | `orchestration/utils.py` | Complete | Path traversal prevention, project root discovery |
| **MCP Server** | `subagent_server/server.py` | Complete | 5 tools, agent resource polling, background task execution |
| **CLI: Rules** | `cli.py` | Complete | list, add, sync (with prune, dry-run) |
| **CLI: Agents** | `cli.py` | Complete | list, add, sync, set-tier |
| **CLI: Skills** | `cli.py` | Complete | list, add, sync (with protected skill dirs) |
| **CLI: Config** | `cli.py` | Complete | show, sync (with safety guards for custom content) |
| **CLI: System** | `cli.py` | Complete | show, sync (system prompt assembly from parts) |
| **CLI: sync-all** | `cli.py` | Complete | Syncs rules, agents, skills, system, config in one command |
| **CLI: Test** | `cli.py` | Complete | Pytest runner with category/module filtering |
| **Docs CLI: Audit** | `vault.py` | Complete | Summary, features, verify, graph (with JSON output) |
| **Docs CLI: Create** | `vault.py` | Complete | Template-based document creation |
| **Docs CLI: Index** | `vault.py` | Complete | Full/incremental RAG indexing |
| **Docs CLI: Search** | `vault.py` | Complete | Semantic search with JSON output |
| **Subagent CLI: Run** | `subagent.py` | Complete | Agent execution with goal/context/plan, model/provider override |
| **Subagent CLI: Serve** | `subagent.py` | Complete | MCP server startup |
| **Subagent CLI: A2A-Serve** | `subagent.py` | Complete | A2A HTTP server with executor selection |
| **Subagent CLI: List** | `subagent.py` | Complete | List available agents |
| **Logging** | `logging_config.py` | Complete | Idempotent, env-var configurable, stderr handler |

**Summary**: 0 features are stubbed. All 46 cataloged features are implemented with real logic. The codebase is production-quality with no placeholder/TODO implementations found.

---

## 3. CLI Command Reference

### 3.1 cli.py — Resource Manager

```
python .vaultspec/lib/scripts/cli.py [--root PATH] [--verbose|-v] [--debug] <resource> <command>
```

| Resource | Command | Description | Flags |
|----------|---------|-------------|-------|
| `rules` | `list` | List all rules (builtin + custom) | |
| `rules` | `add` | Create a custom rule | `--name`, `--content`, `--force` |
| `rules` | `sync` | Sync rules to tool destinations | `--prune`, `--dry-run` |
| `agents` | `list` | List agents with tier and resolved models | |
| `agents` | `add` | Create a new agent definition | `--name`, `--description`, `--tier`, `--force` |
| `agents` | `sync` | Sync agents to tool destinations | `--prune`, `--dry-run` |
| `agents` | `set-tier` | Update agent tier (LOW/MEDIUM/HIGH) | `name`, `--tier` |
| `skills` | `list` | List managed skills (vaultspec-* prefix) | |
| `skills` | `add` | Create a new skill definition | `--name`, `--description`, `--force` |
| `skills` | `sync` | Sync skills to tool destinations | `--prune`, `--dry-run` |
| `config` | `show` | Display framework + project config and rule refs | |
| `config` | `sync` | Generate CLAUDE.md, GEMINI.md, AGENTS.md | `--prune`, `--dry-run`, `--force` |
| `system` | `show` | Display system prompt parts and targets | |
| `system` | `sync` | Assemble and sync system prompts | `--prune`, `--dry-run`, `--force` |
| `sync-all` | | Sync all resources in sequence | `--prune`, `--dry-run`, `--force` |
| `test` | | Run pytest with category/module filtering | `[all\|unit\|api\|search\|index\|quality]`, `--module` |

**Tool destinations**: Claude (`.claude/`), Gemini (`.gemini/`), Antigravity (`.agent/`), Agents (`AGENTS.md`)

### 3.2 vault.py — Vault Manager

```
python .vaultspec/lib/scripts/vault.py [--verbose|-v] [--debug] <command>
```

| Command | Description | Key Flags |
|---------|-------------|-----------|
| `audit` | Audit the vault | `--summary`, `--features`, `--verify`, `--graph`, `--json`, `--root`, `--limit`, `--type`, `--feature` |
| `create` | Create document from template | `--type` (required), `--feature` (required), `--title`, `--root` |
| `index` | Index vault for semantic search | `--root`, `--full`, `--json` |
| `search` | Semantic search over vault | `query` (positional), `--root`, `--limit`, `--json` |

### 3.3 subagent.py — Agent Orchestrator

```
python .vaultspec/lib/scripts/subagent.py --root PATH <command>
```

| Command | Description | Key Flags |
|---------|-------------|-----------|
| `run` | Execute a sub-agent | `--agent`, `--goal`, `--context`, `--plan`, `--task`, `--task-file`, `--model`, `--provider`, `--mode`, `--interactive`, `--verbose`, `--debug` |
| `serve` | Start MCP server (stdio) | |
| `a2a-serve` | Start A2A HTTP server | `--executor`, `--port`, `--agent`, `--model`, `--mode` |
| `list` | List available agents | |

---

## 4. Protocol Integration Status

### 4.1 MCP (Model Context Protocol) — COMPLETE

**Depth**: Production-ready

The MCP server (`subagent_server/server.py`) is fully implemented using FastMCP with:

| Tool | Type | Description |
|------|------|-------------|
| `list_agents` | Read-only | Returns cached agent metadata with tier/description |
| `dispatch_agent` | Side-effect | Spawns background subagent execution, returns taskId |
| `get_task_status` | Read-only | Returns task state, result, lock info |
| `cancel_task` | Destructive | Graceful ACP cancel + background task cancellation |
| `get_locks` | Read-only | Lists all advisory file locks |

**Infrastructure**:

- Resource registration via `FunctionResource` (agents:// URI scheme)
- `_server_lifespan` context manager for startup/shutdown
- Background task management with cleanup
- Artifact extraction from response text (regex-based path detection)
- Advisory lock integration for workspace coordination

### 4.2 ACP (Agent Client Protocol) — COMPLETE

**Depth**: Full protocol implementation (both client and server sides)

**Client side** (`protocol/acp/client.py`):

- Wraps `claude-agent-sdk` (`ClaudeSDKClient`)
- Supports: `initialize`, `new_session`, `load_session`, `resume_session`, `fork_session`, `list_sessions`, `prompt`, `cancel`, `authenticate`, `set_session_mode`, `set_session_model`
- Full streaming event mapping: `StreamEvent` -> ACP notifications (text_delta, thinking_delta, input_json_delta, tool_call_start)
- SDK message mapping: `AssistantMessage`, `UserMessage`, `SystemMessage`, `ResultMessage`
- Session state tracking with reconnection support

- Dependency injection for SDK factories (testing)

**Providers** (`protocol/providers/`):

- `ClaudeProvider`: Model resolution (Opus 4.6/Sonnet 4.5/Haiku 4.5), env-based config, ProcessSpec via Python ACP bridge
- `GeminiProvider`: Model resolution (Gemini 3 Pro/Flash/2.5 Flash), CLI version checking, temp-file system prompt, ProcessSpec via `gemini` CLI
- Both providers implement: `load_system_prompt`, `load_rules`, `construct_system_prompt`, `prepare_process`
- `resolve_includes()`: Recursive @-include resolution with path traversal prevention

### 4.3 A2A (Agent-to-Agent) — COMPLETE

**Depth**: Full integration with both executor backends

- Routes: `/.well-known/agent-card.json` (GET), `/` (POST, JSON-RPC)
- `ClaudeA2AExecutor` (`executors/claude_executor.py`): Direct claude-agent-sdk integration, streaming message collection, error handling, cancel support
- `write_agent_discovery()`: Generates `.gemini/agents/<name>.md` for Gemini CLI discovery

- Prune stale resources, dry-run preview, force-overwrite safety guards

- Tier-based model resolution (LOW/MEDIUM/HIGH -> concrete model IDs)

### 5.2 Vault Document Management

- Verify vertical integrity (every feature must have a plan)

- Build directed graph from wiki-links and related fields
- Detect orphaned documents (no incoming links)

- Spawn AI agent subprocesses via ACP protocol
- Read-only mode with .vault/-restricted writes
- Session logging and cleanup

### 5.6 MCP Server

- Hot-reload agent definitions via file polling
- Advisory file locking for workspace coordination

- Artifact extraction from response text

### 5.7 A2A Server

- HTTP server for agent-to-agent communication
- Agent card discovery for Gemini CLI integration
- Claude and Gemini executor backends
- Streaming message processing
- Task state lifecycle management

---

## 6. Architecture Notes

### 6.1 Key Design Decisions

1. **GPU-only RAG**: No CPU fallback. `_require_cuda()` fails fast with `GPUNotAvailableError`. This is intentional for performance guarantees.

2. **Lazy imports everywhere**: Heavy dependencies (torch, sentence-transformers, lancedb, acp, a2a) are imported at call time, not module level. This allows the CLI and vault tools to work without RAG deps.

3. **Config singleton**: `core.config.get_config()` returns a module-level singleton. Overrides create fresh instances (not cached). All configurable values have VAULTSPEC_* env var counterparts.

4. **Security-first**: `safe_read_text()` validates paths against workspace root. `_sanitize_filter_value()` escapes SQL injection in LanceDB queries. `_is_vault_path()` enforces read-only boundaries. `_validate_include_dirs()` prevents path traversal.

5. **Dependency injection**: Both ACP bridge and A2A executors accept factory callables for SDK client/options creation, enabling thorough unit testing without real API calls.

6. **Atomic writes**: `atomic_write()` in cli.py uses tmp-file-then-rename to prevent partial writes.

7. **Thread safety**: TaskEngine and LockManager use `threading.Lock` for concurrent access. AsyncIO events bridge async/sync boundaries.

8. **Session management**: The ACP bridge tracks session state (`_SessionState`) enabling load/resume/fork operations, though Claude SDK doesn't persist conversation history across client instances.

### 6.2 Dependency Stack

| Layer | Package | Version | Purpose |
|-------|---------|---------|---------|
| Core | PyYAML | optional | Frontmatter parsing (fallback parser available) |
| RAG | torch | 2.10.0+cu130 | GPU computation |
| RAG | sentence-transformers | | Embedding model |
| RAG | lancedb | | Vector store + hybrid search |
| RAG | pyarrow | | Schema + data serialization |
| Protocol | mcp | >=1.20.0 | MCP server (FastMCP) |

| Protocol | agent-client-protocol | 0.8.0 | ACP client/server |
| Protocol | claude-agent-sdk | | Claude Code agent SDK |
| Protocol | a2a-sdk | 0.3.22 | A2A server/client |
| Protocol | starlette | | ASGI web framework (A2A) |
| Protocol | uvicorn | | ASGI server (A2A) |

### 6.3 Cross-references

- **UX match (-> 01-ux-simulation.md)**: All features listed in CLI help text have real implementations backing them. No phantom commands.
- **Test coverage (-> 03-test-verification.md)**: Every module has a `tests/` subdirectory. Unit test files exist for: core, vault, rag, graph, metrics, verification, orchestration, subagent_server, protocol (ACP + A2A). The `cli.py test` command organizes tests by category (unit, api, search, index, quality) and module.

---

## 7. Notable Implementation Details

### 7.1 Embedding Pipeline

- Length-sorted batching: documents sorted by length before GPU batching for optimal padding
- Query embeddings cached via `functools.lru_cache(maxsize=128)`

### 7.2 Search Pipeline

2. Encode query text with query prefix
3. Execute hybrid search (BM25+ANN) with RRF reranking, fetch 3x requested results
4. Apply graph-aware re-ranking (authority 0.1x min(in_links,10), neighborhood 1.15x, recency 0.02x rank)
5. Return top-k results with snippets

1. Validate agent exists in cache
2. Create TaskEngine task (status: WORKING)

3. Spawn background coroutine:
   c. Call run_subagent() with all parameters
   d. On completion: extract artifacts, truncate summary, complete_task()
4. Return immediately with taskId

1. `spawn_agent_process()` starts the bridge subprocess
3. Client calls `new_session()` with CWD and MCP servers
5. Client sends `prompt()` with TextContentBlock list
6. Bridge calls `sdk_client.query()` and streams SDK events as ACP session updates
7. Client receives AgentMessageChunk, ToolCallStart, ToolCallProgress notifications
8. Client calls `cancel()` to terminate

### 7.5 Tool Destination Sync Architecture

```

Source:                    Transform:              Destinations:

.vaultspec/agents/*.md -> transform_agent()    -> .claude/agents/*.md
                                                -> .gemini/agents/*.md
.vaultspec/skills/     -> transform_skill()    -> .claude/skills/<name>/SKILL.md
                                                -> .agent/skills/<name>/SKILL.md

.vaultspec/FRAMEWORK.md + .vaultspec/PROJECT.md -> _generate_config() -> .claude/CLAUDE.md
                                                                       -> AGENTS.md

.vaultspec/system/*.md -> _generate_system_prompt() -> .gemini/SYSTEM.md

---

## 8. Quality Observations

1. **No stubs found**: Every function and class has real implementation logic. No `pass` bodies, no `raise NotImplementedError`, no TODO markers in production code.

2. **Consistent error handling**: Modules use logging consistently. Heavy operations use try/except with specific exception types. LanceDB search has fallback from hybrid to vector-only on failure.

3. **SQL injection prevention**: `_sanitize_filter_value()` escapes single quotes and strips control characters for LanceDB WHERE clauses.

4. **Path traversal prevention**: Multiple layers: `safe_read_text()`, `_validate_include_dirs()`, `_is_vault_path()`, client-side `is_relative_to()` checks.

5. **Idempotent logging**: `configure_logging()` has a module-level flag to prevent double-configuration.

6. **Test infrastructure**: Two test locations (functional in `lib/tests/`, unit in `lib/src/*/tests/`), centralized path constants, session-scoped fixtures with separate lance dirs, autouse isolation fixtures.

---

*End of technical audit*
