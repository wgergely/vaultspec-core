# vaultspec-subagents

## Interpretation rule

When framework materials say to invoke `vaultspec-subagent`, interpret that instruction semantically: delegate bounded work to an identified specialist role.

## Always true

- `vaultspec-subagent` is an internal framework convention for delegated specialist execution.
- Delegation transport is environment-dependent.
- Agent names are framework identities or personas, not guaranteed runnable endpoints.

## Required delegation contract

Any invocation of `vaultspec-subagent` must carry:

- `agent`
- `goal`
- `constraints`
- `expected result`

## Transport rule

Use the host environment's native delegation mechanism when one exists. Do not assume a shipped CLI, MCP dispatch surface, process model, stdout contract, or session-log behavior.

## Prohibited assumptions

- Do not write or rely on `vaultspec subagent run ...` examples.
- Do not claim that `vaultspec-mcp` exposes `list_agents` or `dispatch_agent` unless the current host explicitly proves it.
- Do not treat framework agent names as automatically executable targets.

## Fallback rule

If the host provides no delegation mechanism, execute the task directly while preserving the requested role separation, constraints, and expected result.
