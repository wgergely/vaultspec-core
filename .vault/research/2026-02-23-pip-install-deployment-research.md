---
# ALLOWED TAGS - DO NOT REMOVE
# REFERENCE: #adr #audit #exec #plan #reference #research #{feature}
tags:
  - "#research"
  - "#pip-install-deployment"
date: "2026-02-23"
related:
  - "[[2026-02-21-packaging-restructure-research]]"
  - "[[2026-02-19-workspace-path-decoupling-research]]"
---

# `pip-install-deployment` research: `pip-install-vs-source-deployment`

Audit of vaultspec's behavior when installed as a pip package into a target
project's venv versus running from the repository's `src/` layout. Three
questions are addressed: path resolution correctness, MCP server configuration,
and CLI entry point design.

## Findings

### Q1: Path Resolution -- Complete Inventory

The codebase uses **zero** `Path(__file__)` or `__file__` references anywhere
in `src/vaultspec/`. This is a significant architectural strength. All path
resolution flows through one of two mechanisms:

**Mechanism A: Workspace Resolution (`config/workspace.py`)**

`resolve_workspace()` determines all four root paths (`content_root`,
`output_root`, `vault_root`, `framework_root`) using only runtime context:
environment variables, git detection (walking up from `cwd`), or `cwd`-based
fallback. The package installation location is never consulted.

**Mechanism B: Global Path Initialization (`core/types.py:init_paths()`)**

Called at `spec_cli.py:67` module load time, `init_paths()` takes a
`WorkspaceLayout` and sets module-level globals (`ROOT_DIR`, `RULES_SRC_DIR`,
`AGENTS_SRC_DIR`, `SKILLS_SRC_DIR`, `SYSTEM_SRC_DIR`, `TEMPLATES_DIR`,
`HOOKS_DIR`, `TOOL_CONFIGS`). All of these are derived from
`layout.output_root` and `layout.content_root` -- never from the package
installation path.

**Line-by-line Inventory:**

| File:Line | Path Expression | Classification | Notes |
|---|---|---|---|
| `config/workspace.py:346` | `Path.cwd()` | SAFE | Runtime cwd, not package path |
| `config/workspace.py:416` | `discover_git(effective_cwd)` | SAFE | Walks up from cwd to find `.git` |
| `config/workspace.py:423-424` | `root / framework_dir_name` | SAFE | Derives from git root or cwd |
| `config/workspace.py:454` | `root / framework_dir_name` | SAFE | Last-resort: cwd + `.vaultspec` |
| `config/config.py:141` | `Path.cwd` (default factory) | SAFE | Default for `root_dir` config field |
| `core/types.py:66-74` | Module globals (`Path()`) | SAFE | Placeholders, overwritten by `init_paths()` |
| `core/types.py:117-125` | `root / ...`, `content / ...` | SAFE | All relative to workspace layout |
| `core/types.py:148-180` | `root / claude_dir / ...` etc. | SAFE | Tool config paths derived from layout |
| `spec_cli.py:66-67` | `get_default_layout()`, `init_paths()` | SAFE | Resolves workspace at CLI entry |
| `subagent_cli.py:356` | `resolve_args_workspace(args, ...)` | SAFE | Resolves workspace at CLI entry |
| `vault_cli.py:145` | `resolve_args_workspace(args, ...)` | SAFE | Resolves workspace at CLI entry |
| `team_cli.py:476-477` | `get_default_layout()`, `resolve_args_workspace()` | SAFE | Same pattern |
| `mcp_server/app.py:96-97` | `cfg.mcp_root_dir` | SAFE | Env-var driven, not package-relative |
| `mcp_server/subagent_tools.py:100-104` | `root_dir`, `CONTENT_ROOT`, `AGENTS_DIR` | SAFE | Set via `initialize_server()` |
| `orchestration/subagent.py:141-144` | `content_root / "rules" / "agents"` | SAFE | From workspace layout |
| `cli_common.py:68-73` | `get_version()` reads `pyproject.toml` | FRAGILE | See below |
| `core/commands.py:61-64` | `ROOT_DIR / "src" / "vaultspec"` | BROKEN | Hardcoded `src/` path for test runner |
| `core/commands.py:22-33` | `MODULE_PATHS` dict with `src/vaultspec/...` | BROKEN | Hardcoded `src/` paths |

**FRAGILE: `cli_common.py:get_version()` (line 57-73)**

```python
def get_version(root_dir: Path | None = None) -> str:
    search_root = root_dir if root_dir is not None else Path.cwd()
    toml_path = search_root / "pyproject.toml"
```

This function reads the version by scanning `pyproject.toml` from `cwd()`. When
vaultspec is pip-installed into a target project, `pyproject.toml` in `cwd()`
belongs to the **target project**, not vaultspec. If the target project has its
own `pyproject.toml` with a `version` field, `get_version()` returns the wrong
version. If there is no `pyproject.toml` (or no `version` line), it returns
`"unknown"`.

The correct approach for an installed package is `importlib.metadata.version("vaultspec")`,
falling back to `pyproject.toml` scanning only when running from source
(development mode).

**BROKEN: `core/commands.py` test runner paths (lines 22-33, 61-64)**

```python
MODULE_PATHS = {
    "cli": ["src/vaultspec/tests/cli"],
    "rag": ["src/vaultspec/rag/tests"],
    ...
}
```

And:

```python
cmd.append(str(_t.ROOT_DIR / "src" / "vaultspec"))
cmd.append(str(_t.ROOT_DIR / "tests"))
```

These hardcode `src/vaultspec/...` paths that only exist in the development
repository layout. When pip-installed, these paths do not exist under the
target project's root. The `vaultspec test` command will fail completely.

This is arguably acceptable since `vaultspec test` is a developer tool meant to
test the framework itself, not the user's project. However, it could be
confusing if exposed as a command in the installed CLI. Consider either:
(a) guarding these commands behind a development-mode check, or (b) having them
locate test paths via `importlib.resources` or package metadata.

**Summary of Classification:**

- **SAFE (39+ path expressions)**: The entire workspace resolution system,
  all resource management paths, all MCP server paths, all orchestration paths.
  The architecture correctly resolves paths from runtime context (cwd, git, env
  vars) rather than package location.
- **FRAGILE (1)**: `get_version()` in `cli_common.py` -- returns wrong version
  or `"unknown"` when pip-installed.
- **BROKEN (2)**: `test_run()` and `MODULE_PATHS` in `core/commands.py` --
  hardcode `src/` layout paths that do not exist when pip-installed.

---

### Q2: MCP Server Configuration

**Current Design:**

The `vaultspec-mcp` console_scripts entry point (`vaultspec.mcp_server.app:main`)
requires `VAULTSPEC_MCP_ROOT_DIR` to be set as an environment variable. The
`main()` function at `mcp_server/app.py:85-115` reads this from config, raises
`RuntimeError` if unset, then passes it to `initialize_server()`.

**Analysis for Target Projects:**

A user who `pip install vaultspec` into their project venv would configure
Claude's `.mcp.json` like:

```json
{
  "mcpServers": {
    "vaultspec-mcp": {
      "command": "vaultspec-mcp",
      "env": {
        "VAULTSPEC_MCP_ROOT_DIR": "/path/to/project"
      }
    }
  }
}
```

This design is **SAFE** because:

- The `vaultspec-mcp` console_scripts entry point will be available on `PATH`
  after `pip install`.
- The server correctly requires explicit root via environment variable rather
  than deriving it from package location.
- The `initialize_server()` function at `subagent_tools.py:75-115` sets up
  `ROOT_DIR`, `CONTENT_ROOT`, and `AGENTS_DIR` from the provided root, then
  defaults `CONTENT_ROOT` to `root_dir / framework_dir` (i.e.,
  `root_dir / ".vaultspec"`), which is exactly where the target project's
  `.vaultspec/` directory lives.

**Gap: No `.mcp.json` template or `vaultspec init` integration**

The `vaultspec init` command (`core/commands.py:148-208`) creates the
`.vaultspec/` and `.vault/` directory structures but does not scaffold a
`.mcp.json` file. Users must manually create this. A recommendation would be to
add `.mcp.json` scaffolding to `vaultspec init`.

**MCP Server Startup Trace:**

1. Claude invokes `vaultspec-mcp` (console_scripts entry point).
2. `mcp_server/app.py:main()` runs.
3. Reads `VaultSpecConfig.from_environment()` -- picks up `VAULTSPEC_MCP_ROOT_DIR`.
4. Validates root is set, calls `initialize_server(root_dir=root_dir, ...)`.
5. `initialize_server()` sets `ROOT_DIR`, `CONTENT_ROOT = root_dir / ".vaultspec"`,
   `AGENTS_DIR = CONTENT_ROOT / "rules" / "agents"`.
6. `set_team_root_dir(root_dir)` configures team tools.
7. `create_server()` builds the FastMCP instance, registers tools.
8. `mcp.run()` starts stdio transport.

All steps use runtime-provided paths. **No package-relative assumptions.**

The entry point itself does NOT call `get_default_layout()` or `init_paths()`
from `spec_cli.py` -- it has its own self-contained initialization via
`get_config()` and `initialize_server()`. This is correct.

**Potential Issue: `mcp_server/app.py:112-113` Windows Event Loop Policy**

```python
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
```

This is standard and works regardless of installation mode. No issue.

---

### Q3: CLI Entry Point Design

**`python -m vaultspec` Correctness:**

The `__main__.py` module at `src/vaultspec/__main__.py:117-118` contains:

```python
if __name__ == "__main__":
    main()
```

When pip-installed, `python -m vaultspec` invokes
`site-packages/vaultspec/__main__.py`, which calls `main()`. The `main()`
function uses only relative imports (`.cli_common`, `.vault_cli`, `.team_cli`,
`.subagent_cli`, `.mcp_server.app`, `.spec_cli`) which all resolve correctly
within the installed package.

**Classification: SAFE.** `python -m vaultspec` works correctly when
pip-installed.

**Console Scripts Entry Point:**

`vaultspec = "vaultspec.__main__:main"` invokes the same `main()` function.
Since it uses no `__file__` or package-relative paths, it works identically
whether invoked as `vaultspec`, `python -m vaultspec`, or from source.

**Classification: SAFE.**

**Multiple Entry Points Assessment:**

The current design defines 5 entry points:

| Entry Point | Module | Purpose |
|---|---|---|
| `vaultspec` | `vaultspec.__main__:main` | Unified CLI router |
| `vaultspec-mcp` | `vaultspec.mcp_server.app:main` | MCP stdio server |
| `vaultspec-vault` | `vaultspec.vault_cli:main` | Vault document management |
| `vaultspec-team` | `vaultspec.team_cli:main` | Team lifecycle |
| `vaultspec-subagent` | `vaultspec.subagent_cli:main` | Subagent dispatch |

The unified `vaultspec` CLI already routes to all four namespaces:

```python
# __main__.py
NAMESPACES = {
    "vault": ...,
    "team": ...,
    "subagent": ...,
    "mcp": ...,
}
```

So `vaultspec vault audit` and `vaultspec-vault audit` invoke the same code.

**Assessment:**

The multiple entry points are **not wrong** but create redundancy. The primary
value of separate entry points is:

- `vaultspec-mcp` is essential as a standalone entry point because Claude's
  `.mcp.json` needs a single executable command. `vaultspec mcp` could also
  serve this purpose, but `vaultspec-mcp` is a cleaner invocation for external
  tool configuration.
- `vaultspec-vault`, `vaultspec-team`, `vaultspec-subagent` add convenience
  but no functional capability beyond `vaultspec vault`, `vaultspec team`,
  `vaultspec subagent`.

The recommended approach is to keep `vaultspec` and `vaultspec-mcp` as
entry points and consider removing `vaultspec-vault`, `vaultspec-team`, and
`vaultspec-subagent` to reduce the surface area. The unified `vaultspec`
CLI already handles all routing. Fewer entry points means less for users to
discover and less to maintain.

However, removing them is a minor concern -- having them does no harm and they
may be useful for tab-completion or scripting.

**`spec_cli.py` Module-Level Side Effects:**

A noteworthy design consideration is `spec_cli.py:65-70`:

```python
try:
    _default_layout = get_default_layout()
    init_paths(_default_layout)
except _WorkspaceError as _e:
    logger.error("%s", _e)
    sys.exit(1)
```

This runs at **import time** when `spec_cli.py` is imported. Since `__main__.py`
conditionally imports `spec_cli` only when the command falls through to it (line
108), this is acceptable -- the import only happens when needed. However, it
means that if workspace resolution fails (e.g., no `.vaultspec/` directory),
`spec_cli.py` cannot even be imported, and the CLI exits with an error.

This is actually **correct behavior** for a pip-installed deployment: if a user
runs `vaultspec rules list` in a project that does not have `.vaultspec/`, it
should fail with a clear error telling them to run `vaultspec init`.

BUT: If workspace resolution fails, `vaultspec init` would also fail because
it routes through `spec_cli.py` which would call `sys.exit(1)` at import
time. This is a **latent bug**: `vaultspec init` cannot be run in a project
that has no `.vaultspec/` because the import-time workspace resolution will
fail before `init_run` is ever called.

Looking at the validation logic in `workspace.py:298-310`:

```python
def _validate(layout: WorkspaceLayout) -> None:
    if not layout.content_root.is_dir():
        raise WorkspaceError(...)
```

`content_root` defaults to `cwd / ".vaultspec"`. If `.vaultspec/` does not
exist, `WorkspaceError` is raised at `spec_cli.py` import time, making
`vaultspec init` unreachable.

**Classification: BROKEN for first-time setup.** A new user who
`pip install vaultspec` and runs `vaultspec init` in a fresh project will get a
`WorkspaceError` because `.vaultspec/` does not yet exist. The `init` command
needs to be handled before workspace resolution, or workspace resolution needs
a "lenient" mode that skips validation when the target command is `init`.

---

## Summary of All Issues

### BROKEN

1. **`vaultspec init` unreachable in fresh projects** (`spec_cli.py:65-70`,
   `config/workspace.py:298-310`). The import-time workspace validation rejects
   projects without `.vaultspec/`, preventing the `init` command from ever
   running. This is the most critical deployment issue.

2. **`vaultspec test` hardcodes `src/` layout** (`core/commands.py:22-33`,
   `core/commands.py:61-64`). Test paths reference `src/vaultspec/...` which
   does not exist in pip-installed deployments. Low priority since this is a
   developer-facing command.

### FRAGILE

3. **`get_version()` reads wrong `pyproject.toml`** (`cli_common.py:57-73`).
   Returns the target project's version or `"unknown"` instead of vaultspec's
   version. Should use `importlib.metadata.version("vaultspec")`.

### GAPS

4. **No `.mcp.json` scaffolding in `vaultspec init`**
   (`core/commands.py:148-208`). Users must manually create `.mcp.json` to
   enable the MCP server integration. This should be part of the init scaffold.

5. **Redundant entry points** (`pyproject.toml` console_scripts). The three
   namespace entry points (`vaultspec-vault`, `vaultspec-team`,
   `vaultspec-subagent`) duplicate what the unified `vaultspec` CLI already
   provides. Consider removing them for a cleaner install surface.

### SAFE

Everything else. The workspace resolution architecture is well-designed for
the dual-mode (source vs. pip-installed) deployment model. The key architectural
decision that makes this work is: **paths are resolved from runtime context
(cwd, git detection, environment variables), never from `__file__` or package
location.** This is a deliberate and correct design.
