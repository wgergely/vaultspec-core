---
tags:
  - "#research"
  - "#uncategorized"
date: 2026-02-18
---
# Gemini A2A/ACP Code Analysis: Dispatch Integration Deep Dive

**Date:** 2026-02-07
**Author:** code-analyst
**Scope:** Structural analysis of how `acp_dispatch.py` and supporting modules interface with the Gemini CLI via ACP, identifying protocol misalignments and configuration gaps.

---

## 1. Executive Summary

Our dispatch system uses the ACP (Agent Client Protocol) to spawn and communicate with Gemini CLI sub-agents. The integration is **mechanically functional** for simple one-shot tasks but exhibits several protocol misalignments, configuration gaps, and architectural tensions that limit reliability. This report documents each area with code references, severity ratings, and specific findings.

**Severity scale:** CRITICAL (likely to cause failures), HIGH (causes degraded behavior), MEDIUM (correctness gap, works by luck), LOW (missed optimization or future risk).

---

## 2. GeminiDispatchClient Analysis

### 2.1 Class Structure

**File:** `acp_dispatch.py:213-483`

`GeminiDispatchClient` implements the `acp.interfaces.Client` protocol, providing the ACP client-side callbacks that the Gemini CLI agent invokes during execution.

**Implemented methods:**

| Method | Lines | Purpose |
|---|---|---|
| `request_permission()` | 231-262 | Auto-approves all tool calls |
| `session_update()` | 264-311 | Handles streaming protocol updates |
| `read_text_file()` | 332-352 | Workspace-scoped file reading |
| `write_text_file()` | 354-367 | Workspace-scoped file writing |
| `create_terminal()` | 371-412 | Subprocess spawning |
| `terminal_output()` | 414-429 | Terminal output retrieval |
| `wait_for_terminal_exit()` | 431-441 | Wait for process completion |
| `kill_terminal()` | 443-451 | Process termination |
| `release_terminal()` | 453-468 | Terminal cleanup |
| `ext_method()` | 472-475 | Extension method handler |
| `ext_notification()` | 477-479 | Extension notification handler |
| `on_connect()` | 481-482 | Connection callback (no-op) |

### 2.2 Permission Handling

**File:** `acp_dispatch.py:231-262`
**Severity:** MEDIUM

```python
async def request_permission(
    self, options: Any, session_id: str, tool_call: Any, **kwargs: Any
) -> Dict[str, Any]:
    selected_id = "allow"
    if options:
        for opt in options:
            opt_kind = getattr(opt, "kind", None)
            if opt_kind in ("allow_once", "allow_always"):
                selected_id = getattr(opt, "option_id", selected_id)
                break
        else:
            selected_id = getattr(options[0], "option_id", selected_id)
    return {"outcome": {"outcome": "selected", "optionId": selected_id}}
```

**What this does:** Unconditionally auto-approves every tool call permission request. Iterates options looking for an `allow_once` or `allow_always` kind; if none found, selects the first option regardless of kind.

**What Gemini CLI expects:** The ACP protocol defines that the client (us) should present options to a human for review. Gemini CLI sends permission requests for file writes, terminal commands, and potentially destructive operations.

**Misalignment:** This "YOLO mode" approach means:

- The `read-only` permission mode from the MCP layer (`mcp_dispatch.py:82-110`) is only enforced via prompt injection (natural language instruction), not via protocol-level rejection.
- The `write_text_file` handler (`acp_dispatch.py:354-367`) enforces workspace boundaries but not permission-mode boundaries. A `read-only` agent could still write to `src/` through the ACP file write callback.
- No path is ever `reject_once` or `reject_always` -- the permission system is vestigial.

### 2.3 Session Update Handler

**File:** `acp_dispatch.py:264-311`
**Severity:** LOW

Handles all ACP `session/update` notification types:

- `AgentMessageChunk` / `AgentThoughtChunk` -> accumulated into `response_text` (line 321-328)
- `UserMessageChunk` -> printed to stderr in yellow (line 276-281)
- `AvailableCommandsUpdate` / `CurrentModeUpdate` / `SessionInfoUpdate` -> debug-only logging (line 283-287)
- `ToolCallStart` -> printed to stderr in blue (line 289-294)
- `ToolCallProgress` -> status printed to stderr (line 296-303)
- `AgentPlanUpdate` -> plan entries printed to stderr (line 305-311)

**Finding:** All streaming data is consumed and displayed to stderr/stdout, but never forwarded to the MCP layer. The MCP `get_task_status` tool only sees the final accumulated `response_text` string. Real-time visibility into sub-agent work is lost at this boundary.

### 2.4 File I/O

**File:** `acp_dispatch.py:332-367`
**Severity:** HIGH

**`read_text_file()`** (line 332-352):

- Resolves the path and validates it's within `ROOT_DIR`.
- Supports `line` (1-indexed start) and `limit` (number of lines) parameters.
- Returns `{"content": content}`.

**`write_text_file()`** (line 354-367):

- Resolves the path and validates it's within `ROOT_DIR`.
- Creates parent directories if needed.
- Writes content with UTF-8 encoding.
- Logs the operation and appends to `written_files`.

**Misalignment with read-only mode:** When `mode="read-only"` is set via MCP dispatch, the prompt tells the agent "You MUST only write files within the `.docs/` directory." However, `write_text_file()` does NOT enforce this. If Gemini CLI ignores the prompt instruction and attempts to write `src/main.rs`, the write succeeds. The advisory lock system (`task_engine.py:143-276`) logs warnings but does not block writes.

**What Gemini CLI likely expects:** The ACP client should enforce file access boundaries. If the client declares limited filesystem capabilities, the agent should respect those declarations. But our `client_capabilities` declare full `write_text_file=True` without path restrictions.

### 2.5 Terminal Management

**File:** `acp_dispatch.py:371-468`
**Severity:** MEDIUM

Implements full terminal lifecycle:

- `create_terminal()`: Spawns subprocess via `asyncio.create_subprocess_exec`, tracks in `_terminals` dict by UUID.
- `terminal_output()`: Returns buffered output with truncation support.
- `wait_for_terminal_exit()`: Awaits process completion.
- `kill_terminal()`: Sends kill signal.
- `release_terminal()`: Cleanup with cancellation of reader task.

**Finding:** Terminal commands are executed without validation. In read-only mode, the agent could execute `git commit`, `cargo build`, or other mutation commands through the terminal API. The permission auto-approval at line 231-262 means these are never blocked.

**Finding:** The `byte_limit` parameter (default 1MB at line 392) may be insufficient for large build outputs. Gemini CLI may generate significant terminal output during code compilation tasks.

---

## 3. GeminiProvider Analysis

### 3.1 Process Preparation

**File:** `agent_providers/gemini.py:138-177`
**Severity:** HIGH (multiple sub-findings)

```python
def prepare_process(self, agent_name, agent_meta, agent_persona,
                    task_context, root_dir, model_override=None) -> ProcessSpec:
    rules = self.load_rules(root_dir)
    system_prompt = self.construct_system_prompt(agent_persona, rules)

    tf = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8")
    tf.write(system_prompt)
    tf.close()
    temp_path = pathlib.Path(tf.name)

    env = os.environ.copy()
    env["GEMINI_SYSTEM_MD"] = str(temp_path)

    executable = shutil.which("gemini") or "gemini"
    cmd_args = ["--experimental-acp"]

    target_model = model_override or agent_meta.get("model")
    if target_model:
        cmd_args.extend(["--model", target_model])

    return ProcessSpec(
        executable=executable,
        args=cmd_args,
        env=env,
        cleanup_paths=[temp_path]
    )
```

**3.1a -- `--experimental-acp` flag** (line 166)
**Severity:** HIGH

This is the sole flag that enables ACP mode in Gemini CLI. Without it, Gemini runs in interactive terminal mode. The flag is undocumented and experimental -- its behavior may change between Gemini CLI versions.

**Reference:** Zed IDE uses the same flag at `ref/zed/crates/project/src/agent_server_store.rs:1379`:

```rust
command.args.push("--experimental-acp".into());
```

Zed also pins specific Gemini CLI versions (v0.9.0 on Windows due to a hang bug, v0.2.1+ on other platforms) at `agent_server_store.rs:1352-1357`. Our code does NOT pin versions, making it vulnerable to breaking changes in the Gemini CLI ACP implementation.

**3.1b -- `GEMINI_SYSTEM_MD` environment variable** (line 162)
**Severity:** MEDIUM

The system prompt is written to a temp file and its path passed via `GEMINI_SYSTEM_MD`. This appears to be an undocumented Gemini CLI feature for injecting system instructions. It is NOT part of the ACP protocol.

**Finding:** There is no verification that Gemini CLI actually reads this env var. If a Gemini CLI update removes or renames this feature, system prompts silently disappear and agents run without rules/persona.

**3.1c -- No `--sandbox` or `--no-sandbox` flag**
**Severity:** LOW

Gemini CLI may support sandbox modes that restrict file access. Our dispatch does not pass any sandbox configuration. The agent's file access is controlled only by the ACP client callbacks we implement.

**3.1d -- No `--cwd` argument**
**Severity:** MEDIUM

We set `cwd` via `conn.new_session(cwd=str(ROOT_DIR))` at the ACP protocol level (`acp_dispatch.py:649`), but we do NOT pass `--cwd` as a CLI argument to Gemini. Depending on Gemini CLI's implementation, the working directory may default to wherever `gemini` was invoked from, not the project root. The ACP session's `cwd` field should override this, but Gemini's behavior is unverified.

### 3.2 System Prompt Construction

**File:** `agent_providers/gemini.py:135-136`

```python
def construct_system_prompt(self, persona: str, rules: str) -> str:
    return f"# SYSTEM RULES & CONTEXT\n{rules}\n\n# AGENT PERSONA\n{persona}"
```

**Finding:** Rules come first, then persona. Compare with ClaudeProvider (`claude.py:124-127`):

```python
def construct_system_prompt(self, persona: str, rules: str) -> str:
    prompt = f"# AGENT PERSONA\n{persona}\n\n# SYSTEM RULES & CONTEXT\n{rules}"
    return prompt
```

The ordering is reversed between providers. This may affect how strongly each agent adheres to rules vs. persona depending on the model's attention patterns. Not a bug, but an inconsistency.

### 3.3 Rules Loading and Include Resolution

**File:** `agent_providers/gemini.py:57-133`
**Severity:** LOW

**`load_rules()`** (line 119-133):

- Reads `.gemini/GEMINI.md` from the workspace root.
- Passes to `resolve_includes()` for recursive `@path/to/file.md` expansion.

**`resolve_includes()`** (line 57-117):

- Recursively expands `@path/to/file.md` directives.
- Resolution order: base_dir (relative to including file) first, then root_dir.
- Security: resolved paths must be within `root_dir`.
- Error handling: missing files become `<!-- ERROR: Missing include -->` comments.

**Finding:** This is duplicated verbatim in `ClaudeProvider` (`claude.py:47-107`). A future refactor should extract this to a shared utility.

**Finding:** GEMINI.md contains `@rules/dev-git.md`, `@rules/rs-standards.md`, etc. These are resolved relative to `.gemini/` first, finding `.gemini/rules/dev-git.md`. The resolution works because `cli.py config sync` copies rules to both `.claude/rules/` and `.gemini/rules/`.

### 3.4 Model Mapping

**File:** `agent_providers/gemini.py:12-55`
**Severity:** LOW

Supported models:

```
gemini-3-pro-preview    -> HIGH
gemini-3-flash-preview  -> MEDIUM
gemini-2.5-pro          -> LOW
gemini-2.5-flash        -> LOW
```

**Finding:** `gemini-2.5-pro` is mapped to LOW, which seems incorrect -- it should likely be MEDIUM. The fallback mapping maps LOW to `gemini-2.5-pro` (line 49-50), which means a LOW-capability request gets a "pro" model. This is a minor capability mapping inconsistency.

---

## 4. Session Initialization

### 4.1 Connection and Initialize

**File:** `acp_dispatch.py:619-647`
**Severity:** HIGH (corrected from earlier compliance brief)

```python
async with spawn_agent_process(
    client,
    spec.executable,
    *spec.args,
    env=spec.env,
    transport_kwargs={
        "limit": 100 * 1024 * 1024,      # 100MB
        "shutdown_timeout": 5.0,
    },
) as (conn, _proc):
    await conn.initialize(
        protocol_version=1,
        client_capabilities=ClientCapabilities(
            fs=FileSystemCapability(
                read_text_file=True,
                write_text_file=True,
            ),
            terminal=True,
        ),
        client_info=Implementation(
            name="pp-dispatch",
            version="0.5.0",
        ),
    )
```

**Correction:** The earlier compliance brief (`2026-02-07-acp-protocol-compliance-brief.md:294`) stated "We don't send `client_capabilities` or `client_info`." This is **incorrect** -- the current code DOES send both. The brief may have been written against an older version of the code.

**What we send:**

- `protocol_version=1` -- correct, matches ACP spec.
- `client_capabilities.fs.read_text_file=True` -- correct, we implement `read_text_file()`.
- `client_capabilities.fs.write_text_file=True` -- correct but overly permissive for read-only mode.
- `client_capabilities.terminal=True` -- correct, we implement full terminal lifecycle.
- `client_info.name="pp-dispatch"` -- identifies us as the dispatch system.
- `client_info.version="0.5.0"` -- current version.

**What we don't do:**

- We don't inspect the `InitializeResponse` for agent capabilities. Gemini CLI returns its supported features (image support, embedded context, MCP capabilities, load session support) but we ignore all of it.
- We don't adjust our behavior based on what the agent advertises.

**Misalignment for read-only mode:** When dispatching in `read-only` mode, we still declare `write_text_file=True`. Gemini CLI sees this and assumes it can write files anywhere. A protocol-correct approach would either:

1. Send `write_text_file=False` (but then the agent can't write `.docs/` either), or
2. Keep `write_text_file=True` but enforce path restrictions in `write_text_file()` callback.

Option 2 is the pragmatic choice, but our callback doesn't implement path restrictions for read-only mode.

### 4.2 Session Creation

**File:** `acp_dispatch.py:649`

```python
session = await conn.new_session(
    cwd=str(ROOT_DIR),
    mcp_servers=[],
    **getattr(spec, "session_meta", {})
)
```

**What we send:**

- `cwd`: Workspace root directory (absolute path). This tells Gemini CLI where to operate.
- `mcp_servers`: Empty list. Sub-agents get no MCP tools from us.
- `**session_meta`: Only populated by ClaudeProvider (with `systemPrompt`). GeminiProvider's ProcessSpec has no `session_meta`, so this is `{}` for Gemini dispatches.

**What Gemini CLI likely does with `cwd`:** Uses it as the working directory for tool operations and file path resolution. Critical for correct operation.

**What Gemini CLI likely does with `mcp_servers=[]`:** The agent operates with only its built-in tools (Google Search, file operations via our callbacks, terminal via our callbacks). It cannot access external MCP servers like our `rust-quality` or `pp-dispatch` servers.

**Missing:** We could pass through the MCP servers configured in `.gemini/settings.json:34-45` (the `mcpServers` block), giving sub-agents access to the same tooling as the interactive Gemini CLI. Currently, sub-agents are tool-impoverished compared to interactive usage.

---

## 5. MCP Dispatch Server Integration

### 5.1 How dispatch_agent Calls run_dispatch

**File:** `mcp_dispatch.py:389-468`

The MCP `dispatch_agent` tool:

1. Resolves effective permission mode (`_resolve_effective_mode`, line 409).
2. Reads task file if the task string is a file path (line 420-426).
3. Creates a task in the engine (line 429-431).
4. Acquires advisory lock (line 437-442).
5. Injects read-only permission prompt if needed (line 445).
6. Spawns background coroutine `_run_dispatch_background()` (line 453-456).
7. Returns immediately with `{taskId, status: "working"}` (line 462-468).

**Parameters passed to `run_dispatch()`** (via `_run_dispatch_background`, line 471-488):

```python
await run_dispatch(
    agent_name=agent,
    initial_task=task_content,    # May have read-only prompt prepended
    model_override=model,
    interactive=False,             # Always one-shot
    debug=False,
    quiet=True,                    # Suppress stdout for JSON-RPC safety
)
```

**Key finding:** The `provider_override` parameter of `run_dispatch()` is NOT exposed through the MCP tool. MCP callers cannot force a specific provider -- only model override is available. Provider selection is always automatic based on model name prefix.

### 5.2 Task Lifecycle Management

**File:** `mcp_dispatch.py:471-546` + `task_engine.py`

The background coroutine `_run_dispatch_background()`:

1. Calls `run_dispatch()` and awaits completion.
2. On success: extracts artifacts from response text, merges with file write log, calls `task_engine.complete_task()`.
3. On cancellation (`asyncio.CancelledError`): no-op (engine state already set by `cancel_task`).
4. On dispatch errors: calls `task_engine.fail_task()`.
5. Lock release: handled automatically by `TaskEngine` on terminal state transitions (line 544-546 comment).

**Graceful cancellation gap:** When `cancel_task` is called (line 594-631):

1. The task engine transitions to CANCELLED state.
2. The background asyncio.Task is cancelled via `bg_task.cancel()`.
3. However, the ACP `session/cancel` notification is NOT sent to the Gemini process.
4. The Gemini subprocess may continue running until the `spawn_agent_process` context manager exits and kills it.

This means cancellation is **not graceful** -- the agent doesn't get a chance to clean up, save progress, or acknowledge the cancellation through the ACP protocol.

---

## 6. Subprocess Lifecycle

### 6.1 Process Spawning

**File:** `acp_dispatch.py:619-628`

The `spawn_agent_process()` function (from the `acp` SDK) handles:

- Launching the subprocess with stdio pipes.
- Setting up the JSON-RPC transport layer.
- Returning `(conn, proc)` for protocol communication and process management.

**Transport configuration:**

```python
transport_kwargs={
    "limit": 100 * 1024 * 1024,    # 100MB buffer for large outputs
    "shutdown_timeout": 5.0,         # 5s grace period
}
```

The 100MB buffer is generous but may still be insufficient for very long-running tasks that produce continuous output.

### 6.2 Stderr Consumption

**File:** `acp_dispatch.py:600-616`

A dedicated `_read_stderr` task drains the subprocess's stderr to prevent buffer saturation:

```python
async def _read_stderr(proc, debug):
    if proc.stderr:
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            if debug:
                print(f"[AGENT-STDERR] {line.decode().strip()}", file=sys.stderr)
```

**Finding:** Stderr output is only visible in debug mode. In production dispatch, all agent diagnostic output is silently consumed and discarded. This makes debugging dispatch failures difficult without re-running with `--debug`.

### 6.3 Process Cleanup (Windows-Specific)

**File:** `acp_dispatch.py:668-700`
**Severity:** MEDIUM (Windows-specific)

Extensive Windows cleanup:

1. Cancel stderr reader task (line 669-671).
2. Close `_transport` on the process (line 675-677).
3. Close individual pipe transports (line 680-684).
4. Sleep 0.1s for event processing (line 687).
5. GC collect (line 688).
6. Wait for process with 5s timeout (line 692-697).
7. Another GC collect and 0.5s sleep (line 699-700).

**Finding:** The multiple GC collections and sleeps are workarounds for Windows Proactor event loop issues with `asyncio.subprocess`. These are band-aids for `ResourceWarning: unclosed transport` warnings that can cause issues on Windows. The warnings are also suppressed at module level (line 60-62) and in `main()` (line 947).

---

## 7. Configuration Analysis

### 7.1 `.gemini/settings.json`

**File:** `.gemini/settings.json`

Key settings relevant to ACP dispatch:

```json
{
  "tools": {
    "autoAccept": true,
    "discoveryCommand": "cmd /c python .gemini/tools/repo_tools.py list",
    "callCommand": "cmd /c python .gemini/tools/repo_tools.py call"
  },
  "experimental": {
    "enableAgents": true
  },
  "mcpServers": {
    "rust": { "command": "rust-mcp-server", "args": [], "trust": true },
    "pp-dispatch": { "command": "python", "args": [".rules/scripts/mcp_dispatch.py"], "trust": true }
  }
}
```

**Finding:** These settings affect **interactive** Gemini CLI usage but NOT ACP-dispatched sub-agents. When Gemini CLI runs in `--experimental-acp` mode:

- `tools.autoAccept` is irrelevant (permissions go through ACP `request_permission`).
- `tools.discoveryCommand`/`callCommand` may or may not be available (unclear if ACP mode uses custom tools).
- `mcpServers` are NOT forwarded to the ACP session (we pass `mcp_servers=[]`).
- `experimental.enableAgents` may be required for ACP mode to work.

**Critical gap:** The `mcpServers` configuration includes `rust-mcp-server` and `pp-dispatch`. Interactive Gemini can use these, but dispatched sub-agents cannot. This means sub-agents lose access to:

- Cargo build/check/clippy/test tools (from `rust-mcp-server`).
- Nested dispatch capabilities (from `pp-dispatch`).

### 7.2 `.mcp.json`

**File:** `.mcp.json`

```json
{
  "mcpServers": {
    "pp-dispatch": {
      "command": "python",
      "args": [".rules/scripts/mcp_dispatch.py"],
      "env": {}
    }
  }
}
```

This configures the MCP dispatch server for Claude Code. The server runs as a child process of Claude Code, communicating via stdio JSON-RPC. It wraps `acp_dispatch.py` as MCP tools.

---

## 8. Identified Misalignments Summary

### 8.1 CRITICAL

None found. The system is mechanically functional for basic dispatch.

### 8.2 HIGH

| # | Finding | Location | Description |
|---|---|---|---|
| H1 | No Gemini CLI version pinning | `gemini.py:165` | Zed pins versions (v0.9.0 Win, v0.2.1+ other). We use whatever `gemini` is on PATH. Breaking changes in `--experimental-acp` behavior go undetected. |
| H2 | Read-only mode not enforced at protocol level | `acp_dispatch.py:354-367` | `write_text_file()` allows all writes within workspace, regardless of permission mode. Only prompt-level enforcement exists. |
| H3 | MCP servers not forwarded to sub-agents | `acp_dispatch.py:649` | `mcp_servers=[]` means sub-agents lack tools configured in `.gemini/settings.json`. |
| H4 | `InitializeResponse` capabilities ignored | `acp_dispatch.py:634-647` | We don't check what the agent supports. Could lead to sending unsupported content types or using unavailable features. |

### 8.3 MEDIUM

| # | Finding | Location | Description |
|---|---|---|---|
| M1 | `GEMINI_SYSTEM_MD` is undocumented | `gemini.py:162` | No guarantee Gemini CLI reads this env var across versions. |
| M2 | No graceful ACP cancellation from MCP | `mcp_dispatch.py:594-631` | `cancel_task` kills asyncio task but doesn't send `session/cancel`. |
| M3 | Terminal commands unrestricted in read-only | `acp_dispatch.py:371-412` | Agents can execute arbitrary commands regardless of permission mode. |
| M4 | No `--cwd` CLI argument for Gemini | `gemini.py:166-167` | Relies solely on ACP session `cwd` parameter. |
| M5 | System prompt ordering inconsistent | `gemini.py:135-136` vs `claude.py:124-127` | Gemini: rules-first. Claude: persona-first. |
| M6 | `gemini-2.5-pro` mapped to LOW | `gemini.py:42` | Pro model mapped to low capability seems incorrect. |
| M7 | Existing compliance brief has stale data | `2026-02-07-acp-protocol-compliance-brief.md:294` | Claims we don't send `client_capabilities` -- this is wrong in current code. |

### 8.4 LOW

| # | Finding | Location | Description |
|---|---|---|---|
| L1 | `resolve_includes()` duplicated | `gemini.py:57-117`, `claude.py:47-107` | Identical code in both providers. |
| L2 | Stderr silently consumed | `acp_dispatch.py:600-616` | Agent diagnostics lost in non-debug mode. |
| L3 | Session logs never cleaned up | `acp_dispatch.py:185-199` | `.rules/logs/` grows indefinitely. |
| L4 | No Antigravity provider implementation | `acp_dispatch.py:84-88` | `AGENT_DIRS` includes antigravity, CLI accepts `--provider antigravity`, but no provider class exists. |
| L5 | `provider_override` not exposed via MCP | `mcp_dispatch.py:389-468` | MCP callers can only set model, not provider. |
| L6 | Windows cleanup heuristics fragile | `acp_dispatch.py:668-700` | Multiple GC passes and sleeps are workarounds, not fixes. |

---

## 9. What Gemini CLI Likely Expects (Gap Analysis)

Based on Zed IDE's integration (`ref/zed/crates/project/src/agent_server_store.rs`) and ACP protocol spec:

| Expectation | Our Implementation | Gap |
|---|---|---|
| Specific CLI version | Any version on PATH | No version pinning |
| `--experimental-acp` flag | Yes (line 166) | Compliant |
| Client capabilities declared | Yes (line 634-647) | Compliant |
| Agent capabilities inspected | Not done | We ignore the response |
| `cwd` set in session | Yes (line 649) | Compliant |
| MCP servers forwarded | No (empty list) | Sub-agents lack tools |
| System prompt via `GEMINI_SYSTEM_MD` | Yes (line 162) | Undocumented, fragile |
| Permission requests presented to human | Auto-approved | By design (headless dispatch) |
| `session/cancel` on abort | Not sent from MCP path | Non-graceful termination |
| Streaming updates forwarded | Consumed locally | MCP sees only final text |

---

## 10. Recommendations (Prioritized)

1. **[HIGH] Enforce read-only in `write_text_file()`**: Add path validation in the ACP callback when mode is read-only. Reject writes outside `.docs/`.

2. **[HIGH] Forward MCP servers to sub-agents**: Read `.gemini/settings.json` mcpServers configuration and pass them in `conn.new_session(mcp_servers=...)`. This gives sub-agents access to build tools.

3. **[HIGH] Pin or validate Gemini CLI version**: At minimum, check `gemini --version` during `prepare_process()` and warn if the version is below a known-good baseline.

4. **[MEDIUM] Send `session/cancel` on task cancellation**: Before killing the asyncio task, send `await conn.cancel(session_id=session_id)` to give the agent a chance to clean up.

5. **[MEDIUM] Inspect `InitializeResponse`**: Store agent capabilities and adjust behavior (e.g., don't use features the agent doesn't support).

6. **[MEDIUM] Extract `resolve_includes()` to shared utility**: Deduplicate between providers.

7. **[LOW] Expose `provider_override` in MCP tool**: Add optional `provider` parameter to `dispatch_agent`.

8. **[LOW] Add session log TTL**: Automatically clean up logs older than a configurable threshold.

---

## 11. Code Reference Index

| File | Key Lines | Description |
|---|---|---|
| `acp_dispatch.py` | 213-483 | GeminiDispatchClient implementation |
| `acp_dispatch.py` | 503-752 | `run_dispatch()` main orchestration |
| `acp_dispatch.py` | 754-841 | `_interactive_loop()` |
| `acp_dispatch.py` | 619-647 | ACP connection and initialization |
| `acp_dispatch.py` | 649 | Session creation |
| `agent_providers/gemini.py` | 138-177 | GeminiProvider.prepare_process() |
| `agent_providers/gemini.py` | 57-117 | resolve_includes() |
| `agent_providers/gemini.py` | 119-133 | load_rules() |
| `agent_providers/claude.py` | 129-183 | ClaudeProvider.prepare_process() |
| `mcp_dispatch.py` | 389-468 | dispatch_agent MCP tool |
| `mcp_dispatch.py` | 471-546 | _run_dispatch_background() |
| `mcp_dispatch.py` | 594-631 | cancel_task MCP tool |
| `task_engine.py` | 279-567 | TaskEngine lifecycle management |
| `task_engine.py` | 143-276 | LockManager advisory locks |
| `.gemini/settings.json` | 34-45 | MCP server configuration |
| `.mcp.json` | 1-9 | Claude Code MCP configuration |
| `ref/zed/.../agent_server_store.rs` | 1340-1385 | Zed's Gemini ACP integration reference |
