---
tags:
  - "#plan"
  - "#a2a-server-management"
date: 2026-02-24
related:
  - "[[2026-02-24-a2a-adr]]"
---

# A2A Server Management CLI & Daemonization Plan

This plan addresses a critical architectural paradox in our transition to the A2A protocol: A2A requires that all agent interactions occur over a network server, yet we currently lack a foundational layer to manage these servers safely.

The existing `ServerProcessManager` is an ephemeral, in-memory Python class. If the orchestrator process crashes or exits, spawned A2A servers become orphaned, lingering indefinitely. To build a rock-solid A2A architecture, we must first build a robust server management layer.

## Proposed Architecture

We will implement a daemon-like tracking system and a dedicated `vaultspec server` CLI group to manage the lifecycle of A2A agent servers across the workspace.

### 1. Centralized State Registry

- **Directory**: `.vault/logs/teams/` for both process state (PIDs/Ports) and logs.
- **Behavior**: When an A2A server is spawned, it drops a JSON state file (e.g., `[session_id].json`) recording its PID, selected Port, Model, Provider, and spawn timestamp.
- **Orphan Prevention**: The registry allows subsequent CLI commands (or orchestration managers) to query active servers and cleanly reap them. We will also implement a rigorous SIGTERM/SIGKILL cascade for process trees left behind by `claude-code` or `gemini`.

### 2. `vaultspec server` CLI Commands

We will introduce a top-level `server` subcommand group with the following tools:

- `vaultspec server start --executor <name> --model <model> [--port <port>]`:
  Spawns an agent server in the background (detached), writes its configuration to the state registry in `.vault/logs/teams/`, and outputs the Session ID and Port.
- `vaultspec server list`:
  Reads the state registry, pings the ports to verify liveness, and prints a formatted table of active servers, cleaning up entries for processes that have died.
- `vaultspec server stop <session_id>`:
  Looks up the PID in the registry, sends a graceful shutdown signal, and forcefully kills the process tree if it fails to exit. Removes the registry entry.
- `vaultspec server logs <session_id>`:
  Streams `stdout` and `stderr` from the server's log file in `.vault/logs/teams/`.

### 3. Orchestration Integration

Once the daemonization foundation is laid, `ServerProcessManager` (used by `run_subagent` and eventually `teams`) will be refactored. Rather than just wrapping `subprocess.Popen` directly, it will coordinate with this state registry, ensuring that all spawned servers are tracked.

## Implementation Steps

1. **State Registry Module**: Create `protocol/a2a/server_registry.py` to handle reading/writing the JSON definitions and managing log files in `.vault/logs/teams/`.
2. **Refactor ServerProcessManager**: Update `server_manager.py` to decouple the concept of an *in-memory process handle* from the *persistent server state*. It should use the registry to track what it spawns.
3. **CLI Group**: Create `server_cli.py` and register it in `vault_cli.py`. Implement `start`, `stop`, `list`, and `logs`.
4. **Daemonization/Detachment**: Ensure the `start` command correctly detaches the `a2a-serve` subprocess from the invoking terminal so it continues running in the background.

## Testing Constraints

> [!CRITICAL]
> **No Mocks, Patches, or Stubs:** All testing for the server manager (`test_server_manager.py`) MUST use real processes and real file I/O. We will not use `unittest.mock`, `pytest.MonkeyPatch`, skips, or stubs for testing the server manager's ability to spawn, track, and kill processes. It must be tested integration-style against real subprocess behavior to guarantee robustness.
