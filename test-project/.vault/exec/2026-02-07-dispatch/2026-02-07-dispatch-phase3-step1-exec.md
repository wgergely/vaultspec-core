---
tags:
  - "#exec"
  - "#uncategorized"
date: 2026-02-07
related:
  - "[[2026-02-07-dispatch-phase3-plan]]"
---
# Step 1: Research FastMCP Resource API

## Findings

### Resource Registration

FastMCP provides two registration patterns via the `@mcp.resource()` decorator:

1. **Static resources** — `@mcp.resource("agents://list")` registers a concrete resource at a fixed URI.
2. **Resource templates** — `@mcp.resource("agents://{name}")` detects the `{param}` placeholder and registers a `ResourceTemplate` with regex-based URI matching.

Detection logic in `FastMCP._resource_decorator()`: if `{` is found in the URI string, it registers as a template via `_resource_manager.add_template()`. Otherwise, it registers as a concrete resource via `_resource_manager.add_resource()`.

### Resource Classes (mcp.server.fastmcp.resources)

- `Resource` (base, pydantic BaseModel): uri, name, title, description, mime_type, icons, annotations, meta. Abstract `read()` method.
- `FunctionResource`: wraps a callable (sync or async), calls it lazily on `read()`, returns str/bytes/JSON. This is what template-matched resources create.
- `ResourceTemplate`: stores `uri_template`, `fn`, `parameters`. `matches(uri)` uses regex (`{param}` -> `(?P<param>[^/]+)`). `create_resource(uri, params)` returns a `FunctionResource`.
- Other types: `TextResource`, `BinaryResource`, `FileResource`, `DirectoryResource`, `HttpResource`.

### ResourceManager (mcp.server.fastmcp.resources.resource_manager)

- `_resources: dict[str, Resource]` — concrete resources
- `_templates: dict[str, ResourceTemplate]` — URI template resources
- `get_resource(uri)` — checks concrete first, then iterates templates calling `matches(uri)`
- `list_resources()` — returns only concrete resources (templates are listed separately)
- `list_templates()` — returns all registered templates

### Protocol Methods

- `resources/list` -> `FastMCP.list_resources()` returns `list[MCPResource]` from concrete resources only.
- `resources/read` -> `FastMCP.read_resource(uri)` calls `resource_manager.get_resource(uri)` which checks concrete then templates, calls `resource.read()`.
- `resources/templates/list` -> `FastMCP.list_resource_templates()` returns registered templates.

### list_changed Notification

- `ServerSession.send_resource_list_changed()` sends `ResourceListChangedNotification`.
- Must advertise capability: `NotificationOptions(resources_changed=True)`.
- FastMCP defaults `NotificationOptions()` with all fields `False` — must explicitly enable.
- Server session accessible via `context.request_context.session` during request handling (from `FastMCP.get_context()`).
- Alternative: override `create_initialization_options()` on the low-level server, or configure at FastMCP construction.

### Implications for Phase 3

1. Use `@mcp.resource("agents://{name}")` to register a template for individual agent metadata.
2. The decorated function receives `name` as a keyword argument (extracted from URI by template matching).
3. `resources/list` only shows concrete resources, not templates. To make agents discoverable, either:
   - Register each agent as a concrete resource at startup (and re-register on file changes), or
   - Register a static `agents://` resource for listing + a template `agents://{name}` for reading individual agents.
4. For `list_changed`, need to enable `NotificationOptions(resources_changed=True)`. May need to set this via FastMCP server settings or low-level server configuration.
5. Caching: parse frontmatter once on startup and on file change, serve from cache. `FunctionResource` calls our function on each `read()`, so the function should read from cache.
