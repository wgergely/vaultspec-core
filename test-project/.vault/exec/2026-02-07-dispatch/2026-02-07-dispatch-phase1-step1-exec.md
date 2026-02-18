---
tags:
  - "#exec"
  - "#uncategorized"
date: 2026-02-07
---
# Step 1: Research MCP Python SDK Patterns

## Findings

### SDK Version & Installation

- **Package:** `mcp` v1.26.0 (official Anthropic/ModelContextProtocol package)
- **Install:** `pip install "mcp[cli]"`
- **Python requirement:** >= 3.10

### Server Creation (FastMCP)

The SDK provides `FastMCP` as the high-level server API:

```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("server-name")
```

### Tool Registration

Tools are registered via the `@mcp.tool()` decorator. Python type hints and docstrings automatically generate JSON schemas:

```python
@mcp.tool()
async def my_tool(param1: str, param2: int = 0) -> str:
    """Tool description from docstring.

    Args:
        param1: Description of param1
        param2: Description of param2
    """
    return "result"
```

### Tool Return Values

- Simple types (str, int, dict) are auto-wrapped
- For explicit control, return `CallToolResult` with `TextContent` items
- Error responses: raise exceptions or return error text

### Stdio Transport

```python
if __name__ == "__main__":
    mcp.run(transport="stdio")
```

Or async:

```python
await mcp.run_stdio_async()
```

### Critical: No stdout in stdio servers

- `print()` corrupts JSON-RPC messages
- Must use `logging` to stderr or files

### Server Lifecycle

- `mcp.run()` blocks and handles the full lifecycle
- Lifespan hooks available via `@asynccontextmanager` pattern
- Server responds to `initialize`, `tools/list`, and `tools/call` automatically

### Error Handling

- Exceptions raised in tool handlers are caught and returned as MCP error responses
- `Context` object provides logging: `ctx.info()`, `ctx.debug()`, `ctx.report_progress()`

## Key Design Decisions for Implementation

1. Use `FastMCP` (not low-level `MCPServer`) for simplicity
2. Use `transport="stdio"` for `.mcp.json` compatibility
3. Use `logging` module (to stderr) instead of `print()`
4. async tool handlers to avoid blocking
5. `sys.path` manipulation needed to import `acp_dispatch` as sibling module
