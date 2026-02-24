---
tags:
  - "#research"
  - "#cli-ecosystem-factoring"
date: "2026-02-22"
related:
  - "[[2026-02-22-codebase-audit-research]]"
---
# cli-ecosystem-factoring research: CLI module decomposition and shared infrastructure

The goal of this research is to prepare for a refactoring of all four CLI
modules: `cli.py`, `subagent_cli.py`, `team_cli.py`, and `vault_cli.py`. The
refactoring will extract duplicated boilerplate into a shared foundation module,
decompose the 2460-line `cli.py` monolith into cohesive domain sub-modules, and
bring consistency to workspace resolution, logging setup, version reading, async
execution, and error handling across the entire CLI ecosystem.

This document provides a comprehensive inventory of each module, catalogs every
instance of duplication and inconsistency, assesses what `vaultspec.core` already
provides versus what it lacks, maps the internal dependency graph, and proposes a
phased factoring strategy that covers all four CLI entry points.

## Findings

### 1. Module Inventory

#### 1.1 cli.py -- 2460 lines (the monolith)

**Entry point**: `vaultspec` (via `pyproject.toml` `[project.scripts]`)

**Stdlib imports**: `argparse`, `logging`, `os`, `re`, `shutil`, `subprocess`,
`sys`, `dataclasses`, `pathlib`, `typing`

**Conditional imports**: `html`, `skills_ref.prompt.to_prompt`, `yaml` (with
full fallback YAML parser), `vaultspec.protocol.providers`

**Core imports**: `vaultspec.core.WorkspaceLayout`, `vaultspec.core.resolve_workspace`,
`vaultspec.logging_config.configure_logging`, `vaultspec.vaultcore.parse_frontmatter`

**Module-level globals** (13 mutable `Path` globals + `TOOL_CONFIGS` dict):
`ROOT_DIR`, `RULES_SRC_DIR`, `AGENTS_SRC_DIR`, `SKILLS_SRC_DIR`,
`SYSTEM_SRC_DIR`, `TEMPLATES_DIR`, `FRAMEWORK_CONFIG_SRC`, `PROJECT_CONFIG_SRC`,
`HOOKS_DIR`, `TOOL_CONFIGS`, `PROVIDERS`, `PROTECTED_SKILLS`, `CONFIG_HEADER`

**Functional domains** (grouped by responsibility):

| Domain | Functions | Lines (approx) |
|:---|:---|:---|
| YAML handling | `_yaml_load`, `_yaml_dump`, `_LiteralStr`, `_literal_representer` | 60-110 (fallback) |
| Path init | `init_paths` | 85 |
| Version | `_get_version` | 8 |
| Utility | `build_file`, `ensure_dir`, `atomic_write`, `_launch_editor` | 20 |
| Model resolution | `resolve_model` | 10 |
| Rules CRUD | `collect_rules`, `transform_rule`, `rules_list`, `rules_add`, `rules_sync` | ~100 |
| Agents CRUD | `collect_agents`, `transform_agent`, `agents_list`, `agents_add`, `agents_set_tier`, `agents_sync` | ~130 |
| Skills CRUD | `collect_skills`, `transform_skill`, `skill_dest_path`, `skills_list`, `skills_add`, `skills_sync` | ~130 |
| Generic resource ops | `resource_show`, `resource_edit`, `resource_remove`, `resource_rename` | ~120 |
| Sync engine | `sync_files`, `sync_skills`, `print_summary`, `SyncResult` | ~140 |
| Config generation | `_collect_rule_refs`, `_xml_to_heading`, `_generate_agents_md`, `_generate_config`, `_is_cli_managed`, `config_show`, `config_sync` | ~160 |
| System prompt gen | `collect_system_parts`, `_collect_agent_listing`, `_collect_skill_listing`, `_generate_system_prompt`, `_generate_system_rules`, `system_show`, `system_sync` | ~200 |
| Diagnostics | `test_run`, `doctor_run`, `readiness_run` | ~310 |
| Init | `init_run` | ~55 |
| Hooks | `hooks_list`, `hooks_run` | ~55 |
| Parser/dispatch | `add_sync_flags`, `main` | ~335 |

**Key dataclasses**: `ToolConfig`, `SyncResult`

**Notable**: cli.py contains zero imports from `vaultspec.orchestration`,
`vaultspec.protocol` (except optional `providers`), `vaultspec.rag`, or any
async/network code. It is a purely synchronous, filesystem-oriented tool.

#### 1.2 subagent_cli.py -- 462 lines

**Entry point**: `vaultspec-subagent`

**Stdlib imports**: `argparse`, `asyncio`, `contextlib`, `json`, `logging`,
`pathlib`, `sys`, `warnings`

**Core imports**: `WorkspaceLayout`, `resolve_workspace`, `configure_logging`

**Runtime imports**: `vaultspec.orchestration.subagent.run_subagent`,
`vaultspec.protocol.acp.SubagentClient`,
`vaultspec.protocol.providers.{ClaudeModels, GeminiModels}`,
`vaultspec.subagent_server.server.main`

**Commands**: `run`, `serve`, `a2a-serve`, `list`

**Async pattern**: Manual event loop management (`asyncio.new_event_loop()` +
`set_event_loop()`) with Windows ProactorEventLoop workaround and explicit
`loop.close()` in `finally`.

#### 1.3 team_cli.py -- 588 lines

**Entry point**: `vaultspec-team`

**Stdlib imports**: `argparse`, `asyncio`, `json`, `logging`, `sys`, `warnings`

**Core imports**: `WorkspaceLayout`, `resolve_workspace`, `configure_logging`

**Runtime imports**: `vaultspec.orchestration.team.{MemberStatus, TeamCoordinator,
TeamMember, TeamSession, TeamStatus}`

**Commands**: `create`, `status`, `list`, `assign`, `broadcast`, `message`,
`spawn`, `dissolve`

**Session persistence**: Custom JSON serialization helpers (`_teams_dir`,
`_session_path`, `_save_session`, `_load_session`, `_delete_session`,
`_load_spawned_pids`, `_restore_coordinator`).

**Async pattern**: Uses `asyncio.run()` -- no manual loop management.
Each async command wraps its operation in a local `async def _fn()` closure
then calls `asyncio.run(_fn())`.

#### 1.4 vault_cli.py -- 469 lines

**Entry point**: `vaultspec-vault`

**Stdlib imports**: `argparse`, `json`, `logging`, `pathlib`, `sys`, `datetime`

**Core imports**: `WorkspaceLayout`, `resolve_workspace`, `configure_logging`

**Domain imports**: `vaultspec.graph.VaultGraph`,
`vaultspec.metrics.get_vault_metrics`, `vaultspec.vaultcore.{DocType,
get_template_path, hydrate_template}`, `vaultspec.verification.*`

**Commands**: `audit`, `create`, `index`, `search`

**Async pattern**: None -- entirely synchronous.

**Notable**: `_get_version()` signature differs from the other three; it
accepts an optional `root_dir` parameter.

### 2. Duplication Analysis

#### 2.1 `_get_version()` -- 4 copies

| Module | Signature | Root source |
|:---|:---|:---|
| `cli.py:263` | `_get_version() -> str` | `_default_layout.output_root` |
| `subagent_cli.py:29` | `_get_version() -> str` | `ROOT_DIR` |
| `team_cli.py:33` | `_get_version() -> str` | `ROOT_DIR` |
| `vault_cli.py:31` | `_get_version(root_dir: Path | None = None) -> str` | `root_dir or ROOT_DIR` |

All four parse `pyproject.toml` with the same line-scanning logic. The
`vault_cli.py` variant adds an optional `root_dir` parameter -- the most
flexible signature and the natural candidate for the shared version.

#### 2.2 Import-time workspace resolution -- 4 copies

Every CLI module executes this at module load:

```python
from vaultspec.core import WorkspaceLayout, resolve_workspace
_default_layout: WorkspaceLayout = resolve_workspace(framework_dir_name=".vaultspec")
ROOT_DIR = _default_layout.output_root
```

This is identical across `subagent_cli.py:19-26`, `team_cli.py:23-30`, and
`vault_cli.py:8-28`. `cli.py:113-118` adds the extra step of calling
`init_paths(_default_layout)`.

#### 2.3 Logging setup pattern -- 4 copies (with variations)

All four modules call `configure_logging()` at the start of `main()`, then
conditionally reconfigure based on `--debug`/`--verbose` flags. The
reconfiguration pattern is:

```python
if args.debug:
    from vaultspec.logging_config import reset_logging
    reset_logging()
    configure_logging(level="DEBUG")
elif args.verbose:
    from vaultspec.logging_config import reset_logging
    reset_logging()
    configure_logging(level="INFO")
```

This appears in `cli.py:2346-2354`, `subagent_cli.py:439-447`, and
`team_cli.py:571-579`.

`vault_cli.py:180-185` uses a simpler variant:
```python
if args.debug:
    configure_logging(level="DEBUG")
elif args.verbose:
    configure_logging(level="INFO")
else:
    configure_logging()
```

This works because `vault_cli.py` does not call `configure_logging()` at the
start of its `main()`, so the idempotency guard is not an issue. The other three
modules do call it early, requiring the `reset_logging()` dance.

`subagent_cli.py` further overrides with `log_format="%(message)s"` at the top
of `main()` (line 260), producing output without timestamps/level prefixes.

#### 2.4 Common argparse arguments -- 4 copies

Every module defines the same top-level arguments:

- `--root` (type=Path, default=None)
- `--content-dir` (type=Path, default=None)
- `--verbose` / `-v` (store_true)
- `--debug` (store_true)
- `--version` / `-V` (action="version")

#### 2.5 Workspace re-resolution after parse -- 3 copies

After `parser.parse_args()`, three modules re-resolve the workspace when
overrides are present:

```python
if args.root is not None or getattr(args, "content_dir", None) is not None:
    _layout = resolve_workspace(
        root_override=args.root,
        content_override=getattr(args, "content_dir", None),
        framework_dir_name=".vaultspec",
    )
    args.root = _layout.output_root
    args.content_root = _layout.content_root  # subagent_cli only
else:
    args.root = ROOT_DIR
```

This appears in `subagent_cli.py:424-434`, `team_cli.py:558-568`, and
`cli.py:2356-2362` (where `init_paths(layout)` is called instead of setting
`args.root`). `vault_cli.py` uses a different approach with a `_resolve_root()`
helper that is called per-command.

#### 2.6 Async error handling scaffold -- 7+ copies

The pattern in `team_cli.py` is repeated for every async command:

```python
try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        result = asyncio.run(_fn())
    # process result
except Exception as e:
    logger.error("Error: %s", e)
    if args.debug:
        import traceback
        traceback.print_exc()
    sys.exit(1)
```

This exact structure appears 6 times in `team_cli.py` (lines 201-216,
259-270, 284-296, 345-356, 379-392, 414-440) and once in `subagent_cli.py`
(lines 137-180, though with manual loop management).

#### 2.7 Windows asyncio workarounds -- 2 different implementations

**subagent_cli.py** (manual loop):
```python
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
# ... loop.run_until_complete(...)
# Finally:
if sys.platform == "win32":
    with contextlib.suppress(Exception):
        loop.run_until_complete(asyncio.sleep(0.250))
loop.close()
```

**team_cli.py** (asyncio.run):
```python
with warnings.catch_warnings():
    warnings.simplefilter("ignore", ResourceWarning)
    result = asyncio.run(_fn())
```

Also, `subagent_cli.py` main() applies a `warnings.filterwarnings("ignore",
category=ResourceWarning, message="unclosed transport")` at the top level
(line 452), which `team_cli.py` does not.

### 3. Inconsistency Catalog

#### 3.1 Logging format differences

| Module | Initial `configure_logging()` call | Format |
|:---|:---|:---|
| `cli.py` | `configure_logging()` | Default: `%(asctime)s [%(name)s] %(levelname)s: %(message)s` |
| `subagent_cli.py` | `configure_logging(log_format="%(message)s")` | Bare message only |
| `team_cli.py` | `configure_logging()` | Default |
| `vault_cli.py` | `configure_logging()` (conditional) | Default |

The `subagent_cli.py` format override (`%(message)s`) means subagent output
has no timestamps, no logger name, and no level indicator. This is intentional
for clean CLI output but diverges from all other modules.

#### 3.2 `_get_version()` signature inconsistency

`vault_cli.py` defines `_get_version(root_dir: pathlib.Path | None = None)`
while the other three use `_get_version() -> str` with a module-level global
for the root directory. The `vault_cli.py` variant is more flexible and
testable.

#### 3.3 Error message style inconsistency

- `subagent_cli.py`: `logger.error("Error: --agent is required for 'run'")`
  (prefixed with "Error: ")
- `team_cli.py`: `logger.error("Error: --agents must specify at least one agent")`
  (prefixed with "Error: ")
- `vault_cli.py`: `logger.error("Error: No template found for type '%s'", ...)`
  (prefixed with "Error: ")
- `cli.py`: `logger.error("Error: Rule '%s' exists. Use --force to overwrite.", ...)`
  (prefixed with "Error: ")

All modules prefix error messages with "Error: " -- this is consistent but
redundant since the logging format already includes `%(levelname)s`.

#### 3.4 Workspace attribute naming

After parsing, modules set different attribute names on the `args` namespace:

- `subagent_cli.py`: Sets both `args.root` and `args.content_root`
- `team_cli.py`: Sets only `args.root` (no `content_root`)
- `cli.py`: Calls `init_paths()` instead of setting args attributes
- `vault_cli.py`: Uses `_resolve_root()` per-command, never sets on args

#### 3.5 debug/traceback guarding

`subagent_cli.py` and `team_cli.py` guard `traceback.print_exc()` behind
`if args.debug:`. `cli.py` and `vault_cli.py` do not use `traceback.print_exc()`
at all because they have no try/except blocks around their command dispatch
(errors propagate as normal Python exceptions).

#### 3.6 Import-fallback antipattern — defining replacements on ImportError

This project uses `uv` with a locked `pyproject.toml` that declares explicit
dependencies. `PyYAML>=6.0` is a core dependency (line 25). The protocol
providers (`ClaudeProvider`, `GeminiProvider`) are first-party modules inside
the same package. There is no legitimate scenario where these imports fail in a
properly installed environment. Despite this, `cli.py` contains multiple
`try/except ImportError` blocks that define fallback behavior, silently degrade
functionality, or redefine entire modules inline.

**Severity: Must fix during refactoring.**

##### 3.6.1 50-line fallback YAML parser (cli.py:34-110)

```python
try:
    import yaml
    # ... _yaml_load, _yaml_dump, _LiteralStr definitions (~25 lines)
except ImportError:
    # ... ENTIRE REIMPLEMENTATION of _yaml_load and _yaml_dump (~50 lines)
```

`PyYAML>=6.0` is declared in `pyproject.toml` `dependencies` (line 25). It is
always installed. The fallback is a minimal 2-level parser that handles a
fraction of valid YAML. This is 50 lines of dead code that can never execute in
a properly installed environment — and if it somehow did, it would silently
produce wrong results for any non-trivial frontmatter.

**Action**: Delete the `except ImportError` branch entirely. Import `yaml`
unconditionally.

##### 3.6.2 Silent provider degradation (cli.py:120-131)

```python
try:
    from vaultspec.protocol.providers import ClaudeProvider, GeminiProvider
    PROVIDERS: dict[str, Any] = {"claude": ClaudeProvider(), "gemini": GeminiProvider()}
except ImportError:
    PROVIDERS = {}
    logger.warning("Warning: agent_providers not found. Tier resolution unavailable.")
```

These are first-party imports from the same package. If they fail, the
installation is broken. Silently falling back to `PROVIDERS = {}` means every
`agents sync` operation will skip all agents without explanation (because
`resolve_model()` returns `None` and `transform_agent()` returns `None`).

This block also contains a **bug**: `logger.warning(...)` on line 129
references `logger` which is not defined until line 136. If the import actually
fails, this raises `NameError`, not the intended warning.

**Action**: Import unconditionally. If the installation is broken, let the
`ImportError` propagate — that is the correct signal.

##### 3.6.3 Optional `skills_ref.prompt` fallback (cli.py:28-32)

```python
try:
    import html
    from skills_ref.prompt import to_prompt
except ImportError:
    to_prompt = None
```

`skills_ref` is NOT in `pyproject.toml` dependencies (neither core nor
optional). This is a genuinely optional third-party package. The `to_prompt =
None` fallback is checked at call sites (`_collect_skill_listing`). This
pattern is acceptable for a truly optional dependency, but the `import html`
bundled inside the same `try` block is wrong — `html` is stdlib and can never
fail. It should be a top-level import.

**Action**: Move `import html` to top-level imports. Keep the `skills_ref`
try/except but add a comment documenting it as a genuinely optional dependency.

##### 3.6.4 Diagnostic probing in doctor_run/readiness_run (cli.py:1593-1625, 1930-1960)

These `ImportError` catches in `doctor_run()` and `readiness_run()` are
**legitimate**: the entire purpose of these functions is to probe optional
dependencies (`torch`, `lancedb`, `sentence_transformers`) and report their
installation status. These are in `[project.optional-dependencies]` under the
`rag` extra. The try/except pattern is the correct approach here.

**Action**: No change needed. These are the one legitimate use case.

##### 3.6.5 Fail-fast guards in subagent_cli.py and team_cli.py

```python
# subagent_cli.py:38-46
try:
    from vaultspec.orchestration.subagent import run_subagent, ...
    from vaultspec.protocol.acp import SubagentClient
    ...
except ImportError as e:
    logger.error("Failed to import subagent library: %s", e)
    sys.exit(1)

# team_cli.py:41-53
try:
    from vaultspec.orchestration.team import TeamCoordinator, ...
except ImportError as e:
    logger.error("Failed to import team library: %s", e)
    sys.exit(1)
```

These are first-party imports that should never fail in a proper installation.
The `sys.exit(1)` at least makes the failure visible, but it masks the real
traceback that would help diagnose the broken installation.

**Action**: Import unconditionally. Let `ImportError` propagate with its full
traceback.

##### 3.6.6 Lazy RAG imports in vault_cli.py (lines 377-383, 428-433)

```python
# vault_cli.py:377-383
try:
    from vaultspec.rag.api import index
    from vaultspec.rag.embeddings import get_device_info
except ImportError:
    logger.error("Error: RAG dependencies not installed.")
    logger.error("Run: pip install -e '.[rag]'")
    sys.exit(1)
```

These lazy imports guard against `[project.optional-dependencies] rag` not
being installed. The pattern is acceptable — RAG requires GPU dependencies
(`torch`, `lancedb`) that are intentionally optional. The user-facing error
message is helpful.

**Action**: Keep as-is. This is a legitimate optional-extras guard with a clear
error message. Consider extracting the repeated error message into a helper.

##### Summary table

| Location | Import | In deps? | Fallback behavior | Verdict |
|:---|:---|:---|:---|:---|
| cli.py:34 | `yaml` | Yes (core) | 50-line reimplementation | **Delete fallback** |
| cli.py:120 | `protocol.providers` | First-party | Silent `PROVIDERS = {}` + logger bug | **Delete fallback** |
| cli.py:28 | `skills_ref.prompt` | No | `to_prompt = None` | Acceptable (truly optional) |
| cli.py:28 | `html` | Stdlib | Bundled in wrong try block | **Move to top-level** |
| cli.py:1593+ | `torch`, `lancedb`, etc. | Optional (`rag`) | Diagnostic probing | **Legitimate** |
| subagent_cli.py:38 | `orchestration.*` | First-party | `sys.exit(1)` | **Delete guard** |
| team_cli.py:41 | `orchestration.team.*` | First-party | `sys.exit(1)` | **Delete guard** |
| vault_cli.py:377 | `rag.api`, `rag.embeddings` | Optional (`rag`) | User-facing error + exit | **Legitimate** |

### 4. Core Foundation Assessment

#### 4.1 What `vaultspec.core` already provides

The `vaultspec.core` package (`__init__.py` + `config.py` + `workspace.py`)
provides:

- **`VaultSpecConfig`**: Central configuration dataclass with env-var resolution,
  validation, and a module-level singleton via `get_config()`/`reset_config()`.
  Covers 50+ configuration variables across agent, MCP, A2A, storage, RAG,
  I/O, and editor domains.

- **`WorkspaceLayout`**: Frozen dataclass with `content_root`, `output_root`,
  `vault_root`, `framework_root`, `mode`, and `git` fields.

- **`resolve_workspace()`**: Git-aware workspace resolution that handles
  standard repos, linked worktrees, container mode, and explicit overrides.

- **`GitInfo`**: Git repository metadata (git_dir, repo_root, is_worktree,
  is_bare, etc.).

#### 4.2 What `vaultspec.core` does NOT provide (and should)

The following cross-cutting concerns are duplicated across CLI modules but
absent from the core package:

- **Version reading**: `_get_version()` -- no canonical implementation exists.
- **Logging bootstrap**: The `configure_logging()` + `reset_logging()` dance
  is in `vaultspec.logging_config` but the "initial call + conditional
  reconfigure" pattern is repeated in every CLI module.
- **Common argparse arguments**: `--root`, `--content-dir`, `--verbose`,
  `--debug`, `--version` are defined 4 times.
- **Post-parse workspace resolution**: The "if args.root or args.content_dir
  then re-resolve" block is repeated 3 times.
- **Async execution wrapper**: The `asyncio.run()` + ResourceWarning
  suppression + debug traceback pattern appears 7+ times.
- **Windows asyncio policy setup**: The ProactorEventLoop policy setting
  appears in 3+ files.

#### 4.3 `vaultspec.logging_config` analysis

The module provides `configure_logging()` and `reset_logging()`, both
operating on a module-level `_logging_configured` boolean flag.

The idempotency design causes a problem: CLI modules call `configure_logging()`
early in `main()` to ensure some default, but then need `reset_logging()` +
re-`configure_logging()` when `--debug`/`--verbose` flags are parsed. This
two-step dance could be eliminated by deferring the initial call until after
arg parsing.

### 5. Dependency Graph

```
cli.py
  from vaultspec.core           -> WorkspaceLayout, resolve_workspace, get_config
  from vaultspec.logging_config -> configure_logging, reset_logging
  from vaultspec.vaultcore      -> parse_frontmatter
  from vaultspec.protocol.providers -> ClaudeProvider, GeminiProvider (optional)
  from vaultspec.hooks          -> load_hooks, trigger (lazy)
  from skills_ref.prompt        -> to_prompt (optional)

subagent_cli.py
  from vaultspec.core           -> WorkspaceLayout, resolve_workspace
  from vaultspec.logging_config -> configure_logging, reset_logging
  from vaultspec.orchestration  -> subagent.run_subagent, READONLY_PERMISSION_PROMPT
  from vaultspec.protocol.acp   -> SubagentClient
  from vaultspec.protocol.providers -> ClaudeModels, GeminiModels
  from vaultspec.subagent_server    -> server.main
  from vaultspec.protocol.a2a  -> agent_card_from_definition, create_app (lazy)

team_cli.py
  from vaultspec.core           -> WorkspaceLayout, resolve_workspace
  from vaultspec.logging_config -> configure_logging, reset_logging
  from vaultspec.orchestration.team -> TeamCoordinator, TeamSession, etc.
  from a2a.types               -> AgentCard (external)

vault_cli.py
  from vaultspec.core           -> WorkspaceLayout, resolve_workspace
  from vaultspec.logging_config -> configure_logging
  from vaultspec.graph          -> VaultGraph
  from vaultspec.metrics        -> get_vault_metrics
  from vaultspec.vaultcore      -> DocType, get_template_path, hydrate_template
  from vaultspec.verification   -> fix_violations, get_malformed, list_features, etc.
  from vaultspec.rag.api        -> index, search (lazy)
```

**Shared across all four**:
- `vaultspec.core` (`WorkspaceLayout`, `resolve_workspace`)
- `vaultspec.logging_config` (`configure_logging`)
- `argparse`, `logging`, `sys`, `pathlib.Path`

**Shared across subagent + team (async modules)**:
- `asyncio`, `warnings`
- Windows ProactorEventLoop workaround
- ResourceWarning suppression
- try/except + traceback pattern

### 6. Factoring Strategy Options

#### Option A: Shared `cli_common.py` module (recommended)

Create `src/vaultspec/cli_common.py` containing all cross-cutting CLI
infrastructure.

**Contents**:

```
cli_common.py
  get_version(root_dir: Path | None = None) -> str
  add_common_args(parser: ArgumentParser) -> None
  resolve_args_workspace(args: Namespace, default_layout: WorkspaceLayout) -> WorkspaceLayout
  setup_logging(args: Namespace, default_format: str | None = None) -> None
  run_async(coro: Coroutine, *, debug: bool = False) -> T
  cli_error_handler(debug: bool) -> ContextManager
```

**Function specifications**:

- **`get_version(root_dir=None)`**: The `vault_cli.py` signature, generalized.
  Reads `pyproject.toml` version, returns `"unknown"` on failure.

- **`add_common_args(parser)`**: Adds `--root`, `--content-dir`, `--verbose`,
  `--debug`, `--version` to any `ArgumentParser`. The `--version` action reads
  from `get_version()`.

- **`resolve_args_workspace(args, default_layout)`**: Encapsulates the
  post-parse workspace re-resolution. Returns a `WorkspaceLayout`. Sets
  `args.root` and `args.content_root` as side effects.

- **`setup_logging(args, default_format=None)`**: Replaces the
  `configure_logging()` + conditional `reset_logging()` pattern. Reads
  `args.debug` and `args.verbose`. Accepts optional format override (for
  `subagent_cli.py`'s `"%(message)s"` case).

- **`run_async(coro, debug=False)`**: Wraps `asyncio.run()` with Windows
  ProactorEventLoop policy, ResourceWarning suppression, and the
  `asyncio.sleep(0.250)` pipe cleanup workaround. Returns the coroutine result.
  On exception, logs error and optionally prints traceback if `debug=True`.

- **`cli_error_handler(debug)`**: A context manager that catches exceptions,
  logs them, prints traceback if `debug`, and calls `sys.exit(1)`.

**Impact per module**:

| Module | Current bootstrap lines | After factoring |
|:---|:---|:---|
| `subagent_cli.py` | ~45 (imports, workspace, version, logging, async) | ~10 |
| `team_cli.py` | ~40 (imports, workspace, version, logging) | ~10 |
| `vault_cli.py` | ~25 (imports, workspace, version, logging) | ~8 |
| `cli.py` | ~30 (imports, workspace, version, logging) | ~10 |

**Estimated deduplication**: ~100-130 lines of boilerplate eliminated across
the four modules.

#### Option B: Decompose `cli.py` into domain sub-modules

In addition to Option A, break `cli.py` into focused modules under
`src/vaultspec/cli/`:

```
src/vaultspec/cli/
  __init__.py        # re-exports main()
  __main__.py        # python -m vaultspec
  main.py            # parser construction + dispatch (~335 lines)
  rules.py           # rules CRUD + sync (~200 lines)
  agents.py          # agents CRUD + sync (~260 lines)
  skills.py          # skills CRUD + sync (~260 lines)
  config.py          # config generation + sync (~200 lines)
  system.py          # system prompt assembly + sync (~200 lines)
  sync.py            # SyncResult, sync_files, sync_skills, print_summary (~200 lines)
  resources.py       # Generic resource_show/edit/remove/rename (~120 lines)
  diagnostics.py     # test_run, doctor_run, readiness_run, init_run (~420 lines)
  hooks.py           # hooks_list, hooks_run (~55 lines)
  yaml_compat.py     # YAML load/dump with fallback (~110 lines)
  types.py           # ToolConfig, SyncResult dataclasses, module-level globals
```

**Benefits**:
- Each file is 100-420 lines (manageable, testable)
- Domain boundaries are clear
- New resource types (e.g., "templates") follow an established pattern
- `main.py` becomes a pure parser/dispatch layer

**Risks**:
- The 13 mutable module-level globals (`ROOT_DIR`, `RULES_SRC_DIR`, etc.)
  create coupling. They would need to live in `types.py` and be imported
  everywhere, or be refactored into a `CLIContext` dataclass.
- The `init_paths()` function mutates these globals and must be called before
  any resource operations. This init-order dependency is fragile.

#### Option C: Full refactor to context-passing (aspirational)

Replace all mutable module-level globals with a `CLIContext` dataclass:

```python
@dataclass
class CLIContext:
    layout: WorkspaceLayout
    tool_configs: dict[str, ToolConfig]
    rules_src_dir: Path
    agents_src_dir: Path
    skills_src_dir: Path
    # ... etc.

    @classmethod
    def from_layout(cls, layout: WorkspaceLayout) -> CLIContext:
        # replaces init_paths()
```

Every function currently reading module globals would accept `ctx: CLIContext`.
This eliminates the mutable-global anti-pattern and makes all functions
independently testable.

**Benefits**: Eliminates global mutable state, enables parallel test execution,
cleaner architecture.

**Risks**: Requires touching nearly every function signature in `cli.py`
(~60 functions). High churn for a refactor-only change.

### 7. Risk Assessment

#### 7.1 Entry point stability

`pyproject.toml` defines four entry points:
```toml
vaultspec = "vaultspec.cli:main"
vaultspec-vault = "vaultspec.vault_cli:main"
vaultspec-team = "vaultspec.team_cli:main"
vaultspec-subagent = "vaultspec.subagent_cli:main"
```

If `cli.py` is converted to a package (`cli/__init__.py`), the entry point
`vaultspec.cli:main` continues to work as long as `__init__.py` re-exports
`main`. However, `__main__.py` currently does `from .cli import main` and
would need updating to `from .cli import main` (which resolves to the
package's `__init__.py`).

#### 7.2 Import-time side effects

All four modules execute `resolve_workspace()` at import time (module level).
This means importing any CLI module triggers git detection and filesystem
traversal. This is a design choice for convenience but creates issues:
- Tests that import CLI modules get workspace resolution as a side effect
- Import order matters if globals are mutated
- `cli.py` goes further by calling `init_paths()` and attempting to import
  `ClaudeProvider`/`GeminiProvider` at module level (with `except ImportError`)

Any factoring should consider deferring workspace resolution to `main()`.

#### 7.3 YAML fallback parser

`cli.py` contains a 50-line fallback YAML parser for environments where
PyYAML is not installed. Since `PyYAML>=6.0` is now in `pyproject.toml`
`dependencies`, the fallback is dead code in normal installations. However,
`cli.py` was originally a standalone script (see docstring: "Usage:
python .vaultspec/lib/scripts/cli.py"). If standalone usage is still a
requirement, the fallback must be preserved. If not, it can be removed
(~50 lines).

#### 7.4 `logger` before `logging.getLogger`

In `cli.py`, there is a subtle bug: `PROVIDERS` initialization (line 128-131)
references `logger` before the `logger = logging.getLogger(__name__)` assignment
on line 136. This works because the `except ImportError` branch at line 128
only executes if the import fails, and by that time `logger` may or may not
exist. If the import fails *before* line 136 is reached during module loading,
this would raise a `NameError`. In practice this does not occur because
Python executes module-level statements sequentially and the try/except block
at lines 120-131 runs before line 136.

**This is actually a real bug**: If `from vaultspec.protocol.providers import
ClaudeProvider, GeminiProvider` raises `ImportError`, line 129 will execute
`logger.warning(...)` but `logger` is not defined until line 136.

#### 7.5 Mutable globals and `init_paths()` coupling

`cli.py` relies on `init_paths()` to populate 9+ `Path` globals. This function
is called once at module level (line 274) and again in `main()` if `--root` or
`--content-dir` is provided (line 2362). This double-initialization pattern is
fragile:
- Any function called between import time and `main()` sees the default layout
- Functions do not declare their dependency on these globals
- Tests must call `init_paths()` to set up correct state

### 8. Recommended Factoring Sequence

**Phase 1** -- Shared foundation (`cli_common.py`):
- Extract `get_version()`, `add_common_args()`, `setup_logging()`,
  `resolve_args_workspace()`
- Refactor all four CLI modules to use them
- Fix the `logger` bug in `cli.py`
- Estimated net line change: +120 (new module), -130 (removed duplication) = -10

**Phase 2** -- Async wrapper:
- Extract `run_async()` and `cli_error_handler()` into `cli_common.py`
- Refactor `subagent_cli.py` and `team_cli.py` to use them
- Unify Windows asyncio handling
- Estimated net line change: +40 (new functions), -80 (removed duplication) = -40

**Phase 3** -- Decompose `cli.py` into package:
- Create `src/vaultspec/cli/` package
- Move each domain into its own module
- Update entry point and `__main__.py`
- Estimated: ~2460 lines redistributed, no net line change but dramatically
  improved cohesion

**Phase 4** (optional) -- Context object:
- Replace module-level globals with `CLIContext`
- Update all ~60 functions to accept `ctx` parameter
- Highest-effort, highest-reward for testability
