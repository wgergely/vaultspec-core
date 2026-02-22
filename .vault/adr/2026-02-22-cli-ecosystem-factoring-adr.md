---
# ALLOWED TAGS - DO NOT REMOVE
# REFERENCE: #adr #audit #exec #plan #reference #research #{feature}
tags:
  - "#adr"
  - "#cli-ecosystem-factoring"
date: "2026-02-22"
related:
  - "[[2026-02-22-cli-ecosystem-factoring-research]]"
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# cli-ecosystem-factoring adr: module hierarchy restructuring | (**status:** accepted)

## Problem Statement

The vaultspec package has a naming inversion at its foundation that misleads
developers, obscures architectural intent, and makes the central business logic
untestable in isolation.

**`vaultspec.core` is not core.** The package contains exactly two modules:
`config.py` (623 lines -- `VaultSpecConfig` singleton, env-var registry,
`CONFIG_REGISTRY`, parsing helpers) and `workspace.py` (406 lines --
`WorkspaceLayout`, `GitInfo`, `resolve_workspace`). These are configuration
infrastructure and workspace resolution. They are consumed by every other
module, but they do not implement any vaultspec domain logic. Calling this
package "core" claims a level of centrality that does not match its contents.

**`cli.py` is the actual core.** At 2460 lines, `cli.py` contains the entire
vaultspec resource management engine: collecting, transforming, and syncing
rules, agents, and skills; generating `CLAUDE.md`, `GEMINI.md`, `AGENTS.md`,
and `SYSTEM.md`; assembling system prompts with ordered parts and agent/skill
listings; the `ToolConfig` and `SyncResult` dataclasses; the sync engine; and
all YAML handling. None of this is CLI-specific -- it is the domain library
that happens to be entombed inside an argparse wrapper.

This inversion causes concrete problems:

- **Untestable domain logic.** Testing any resource management function (e.g.,
  `collect_rules`, `transform_agent`, `sync_files`) requires importing the
  entire 2460-line `cli.py`, which triggers import-time workspace resolution,
  provider instantiation, and mutable global initialization via `init_paths()`.
  There is no way to import the library without its CLI side effects.

- **Deceptive import paths.** `from vaultspec.core import get_config` reads as
  "import from the core of the system," but it is actually importing from a
  configuration utility module. Meanwhile, the real core logic lives in
  `from vaultspec.cli import collect_rules` -- an import path that suggests
  CLI code, not library code.

- **Monolith resistance.** Adding a new resource type (e.g., templates,
  snippets) means adding more functions to a 2460-line file. There is no
  natural place to put new domain logic because the only domain module is the
  CLI module itself.

- **Duplicated boilerplate.** As documented in
  [[2026-02-22-cli-ecosystem-factoring-research]] sections 2.1--2.7, the four
  CLI entry points (`cli.py`, `subagent_cli.py`, `team_cli.py`, `vault_cli.py`)
  duplicate `_get_version()` (4 copies), workspace resolution (4 copies),
  logging setup (4 copies with variations), common argparse arguments (4
  copies), post-parse workspace re-resolution (3 copies), and async error
  handling scaffolds (7+ copies).

- **Import-fallback antipatterns.** `cli.py` contains fallback import guards
  around core dependencies (`yaml`, `protocol.providers`) that are always
  installed, producing dead code, silent degradation, and a `NameError` bug
  where `logger` is referenced before definition (see
  [[2026-02-22-cli-ecosystem-factoring-research]] section 3.6).

## Considerations

### Rename cascade scope

Renaming `vaultspec.core` to `vaultspec.config` touches every file that imports
from it. The research identified **57 import occurrences across 34 files** in
`src/vaultspec/` and 2 more in `tests/`. The imports follow two patterns:

- **Top-level imports** (`from vaultspec.core import WorkspaceLayout,
  resolve_workspace`) -- found in all 4 CLI modules plus
  `tests/cli/test_integration.py` and `core/tests/test_workspace.py`.

- **Deferred/lazy imports** (`from vaultspec.core import get_config`) -- found
  in 30+ files across `rag/`, `protocol/`, `orchestration/`, `vaultcore/`,
  `hooks/`, `server.py`, and the CLI modules. These are function-level imports
  that defer the config singleton access until runtime.

The rename is mechanical (find-and-replace `vaultspec.core` with
`vaultspec.config`) but the sheer number of touch points means it must be
executed carefully in a single atomic commit to avoid half-migrated states.

### Backward compatibility via re-exports

To prevent breakage for any external consumers or scripts that import
`vaultspec.core`, a compatibility shim can be maintained:

```python
# src/vaultspec/core/__init__.py (deprecated shim)
"""Deprecated: use vaultspec.config instead."""
import warnings
warnings.warn(
    "vaultspec.core is deprecated, use vaultspec.config",
    DeprecationWarning,
    stacklevel=2,
)
from vaultspec.config import *  # noqa: F401,F403
```

This shim should be removed after one release cycle. All first-party code
must use `vaultspec.config` from the start -- the shim exists only for
hypothetical external consumers.

### Test impact

- **`src/vaultspec/core/tests/test_config.py`** and
  **`src/vaultspec/core/tests/test_workspace.py`** move to
  `src/vaultspec/config/tests/`. Their internal imports
  (`from vaultspec.core.config import ...`, `from vaultspec.core.workspace
  import ...`) become `from vaultspec.config.config import ...` and
  `from vaultspec.config.workspace import ...`.

- **8 `conftest.py` files** across `graph/`, `metrics/`, `orchestration/`,
  `rag/`, `vaultcore/`, and `verification/` import `reset_config` from
  `vaultspec.core`. These are one-line changes.

- **`tests/conftest.py`** imports `VaultSpecConfig`, `get_config`, and
  `reset_config` from `vaultspec.core`. Single-line change.

- **`src/vaultspec/tests/cli/test_integration.py`** imports
  `LayoutMode`, `WorkspaceError`, `WorkspaceLayout`, and `resolve_workspace`
  from `vaultspec.core.workspace`. These become
  `from vaultspec.config.workspace import ...`.

No test logic changes -- only import paths.

### Entry point stability

The `pyproject.toml` entry points are:

```toml
vaultspec = "vaultspec.cli:main"
vaultspec-mcp = "vaultspec.server:main"
vaultspec-vault = "vaultspec.vault_cli:main"
vaultspec-team = "vaultspec.team_cli:main"
vaultspec-subagent = "vaultspec.subagent_cli:main"
```

Decision 3 (extracting business logic from `cli.py`) does **not** convert
`cli.py` into a package. The file remains `src/vaultspec/cli.py` and the
entry point `vaultspec.cli:main` continues to resolve without change. The
extracted domain modules live under `src/vaultspec/core/` -- the new core
package. The CLI file becomes a thin argparse wrapper that imports from
`vaultspec.core`.

If a future phase converts `cli.py` into a `cli/` package, the entry point
`vaultspec.cli:main` will still resolve because `cli/__init__.py` can
re-export `main`. This is deferred and not part of this ADR.

### Module naming: why `core` and not `engine` or `lib`

The extracted domain library is named `vaultspec.core` because it is the
core of the system -- the resource management engine that everything else
depends on. Alternative names considered:

- `vaultspec.engine` -- implies a single long-running process; the resource
  management library is stateless and synchronous.
- `vaultspec.lib` -- too generic; does not communicate that this is the
  primary domain logic.
- `vaultspec.resources` -- too narrow; the library also handles config
  generation, system prompt assembly, and sync orchestration.

`core` is the correct name precisely because the current `vaultspec.core`
package is *not* core -- it is config. Reclaiming the name for the actual
core logic restores semantic accuracy.

## Constraints

- **No behavioral changes.** This is a structural refactoring only. Every
  function must produce identical output before and after the restructuring.
  The test suite is the verification mechanism.

- **Single-commit rename.** The `vaultspec.core` to `vaultspec.config` rename
  must land in one commit. Partial migration (some files using old path, some
  using new) creates import failures.

- **Import-time side effects persist (for now).** The `cli.py` module
  currently calls `resolve_workspace()` at import time and stores the result
  in `_default_layout`. The extracted `vaultspec.core` modules will inherit
  this pattern initially. Deferring workspace resolution to `main()` is a
  desirable future improvement but is out of scope for this refactoring to
  limit churn.

- **No new dependencies.** The refactoring must not introduce any new
  third-party dependencies.

- **`cli_common.py` must be importable without side effects.** Unlike the
  current CLI modules, the shared foundation module must not trigger workspace
  resolution or logging configuration at import time. All initialization must
  be explicit via function calls.

## Implementation

The restructuring proceeds in four phases. Each phase is independently
committable and testable. Phases 1 and 2 have no ordering dependency on each
other and can execute in parallel. Phases 3 and 4 depend on Phase 1.

### Phase 1: Rename `vaultspec.core` to `vaultspec.config`

**Goal:** Restore semantic accuracy to the configuration package.

**Steps:**

- Rename `src/vaultspec/core/` to `src/vaultspec/config/`.
- Rename `src/vaultspec/core/tests/` to `src/vaultspec/config/tests/`.
- Update all 57 import sites in `src/` and 2 in `tests/` from
  `vaultspec.core` to `vaultspec.config`.
- Update `src/vaultspec/config/__init__.py` docstring.
- Place a deprecation shim at `src/vaultspec/core/__init__.py` that re-exports
  everything from `vaultspec.config` with a `DeprecationWarning`.
- Run the full test suite to verify zero behavioral change.

**Concrete path changes:**

| Before | After |
|:---|:---|
| `src/vaultspec/core/__init__.py` | `src/vaultspec/config/__init__.py` |
| `src/vaultspec/core/config.py` | `src/vaultspec/config/config.py` |
| `src/vaultspec/core/workspace.py` | `src/vaultspec/config/workspace.py` |
| `src/vaultspec/core/tests/` | `src/vaultspec/config/tests/` |

**Import change pattern (all 36 files):**

```python
# Before:
from vaultspec.core import WorkspaceLayout, resolve_workspace
from vaultspec.core import get_config
from vaultspec.core import reset_config
from vaultspec.core.config import VaultSpecConfig, CONFIG_REGISTRY
from vaultspec.core.workspace import LayoutMode, WorkspaceError, resolve_workspace

# After:
from vaultspec.config import WorkspaceLayout, resolve_workspace
from vaultspec.config import get_config
from vaultspec.config import reset_config
from vaultspec.config.config import VaultSpecConfig, CONFIG_REGISTRY
from vaultspec.config.workspace import LayoutMode, WorkspaceError, resolve_workspace
```

### Phase 2: Extract shared CLI foundation (`vaultspec.cli_common`)

**Goal:** Eliminate boilerplate duplication across the four CLI entry points.

**Module:** `src/vaultspec/cli_common.py`

**Extracted functions** (based on
[[2026-02-22-cli-ecosystem-factoring-research]] sections 2.1--2.7):

| Function | Replaces | Source modules |
|:---|:---|:---|
| `get_version(root_dir=None) -> str` | 4 copies of `_get_version()` | all 4 CLIs |
| `add_common_args(parser) -> None` | 4 copies of `--root`, `--verbose`, etc. | all 4 CLIs |
| `setup_logging(args, default_format=None) -> None` | 4 copies of logging dance | all 4 CLIs |
| `resolve_args_workspace(args, default_layout) -> WorkspaceLayout` | 3 copies of post-parse resolution | cli, subagent_cli, team_cli |
| `run_async(coro, *, debug=False) -> T` | 7+ copies of async scaffold | subagent_cli, team_cli |
| `cli_error_handler(debug) -> ContextManager` | 7+ copies of try/except + traceback | subagent_cli, team_cli |

**Estimated impact:** +120 lines (new module), -130 lines (removed
duplication) = net -10 lines. More importantly, all four CLI modules shrink
to thin parser+dispatch wrappers and behavioral consistency is enforced.

### Phase 3: Extract business logic from `cli.py` into `vaultspec.core`

**Goal:** Make the resource management library independently importable and
testable, separate from the CLI layer.

**Package:** `src/vaultspec/core/` (reclaiming the name from Phase 1)

**Module decomposition** (based on
[[2026-02-22-cli-ecosystem-factoring-research]] section 1.1 functional
domains):

| New module | Functions moved from `cli.py` | Lines (approx) |
|:---|:---|:---|
| `core/__init__.py` | Public API re-exports | 20 |
| `core/types.py` | `ToolConfig`, `SyncResult`, `init_paths()`, path globals | 100 |
| `core/helpers.py` | `build_file`, `atomic_write`, `ensure_dir`, `resolve_model`, `_yaml_load`, `_yaml_dump` | 80 |
| `core/rules.py` | `collect_rules`, `transform_rule`, `rules_list`, `rules_add`, `rules_sync` | 100 |
| `core/agents.py` | `collect_agents`, `transform_agent`, `agents_list`, `agents_add`, `agents_set_tier`, `agents_sync` | 130 |
| `core/skills.py` | `collect_skills`, `transform_skill`, `skill_dest_path`, `skills_list`, `skills_add`, `skills_sync` | 130 |
| `core/config_gen.py` | `_collect_rule_refs`, `_xml_to_heading`, `_generate_agents_md`, `_generate_config`, `_is_cli_managed`, `config_show`, `config_sync` | 160 |
| `core/system.py` | `collect_system_parts`, `_collect_agent_listing`, `_collect_skill_listing`, `_generate_system_prompt`, `_generate_system_rules`, `system_show`, `system_sync` | 200 |
| `core/sync.py` | `sync_files`, `sync_skills`, `print_summary` | 140 |
| `core/resources.py` | `resource_show`, `resource_edit`, `resource_remove`, `resource_rename` | 120 |

**After extraction, `cli.py` contains only:**

- `argparse` parser construction (~200 lines)
- `add_sync_flags()` helper
- `main()` dispatch function
- `init_run()`, `hooks_list()`, `hooks_run()` (CLI-only operations)
- `test_run()`, `doctor_run()`, `readiness_run()` (diagnostic commands)

Estimated residual `cli.py` size: ~700 lines (down from 2460).

**The mutable globals problem:** The 13 module-level `Path` globals
(`ROOT_DIR`, `RULES_SRC_DIR`, `AGENTS_SRC_DIR`, etc.) and `TOOL_CONFIGS` dict
move to `core/types.py`. The `init_paths()` function moves there as well.
This preserves current behavior while consolidating the state into one module.
A future phase can replace these with a `CLIContext` dataclass (see Phase 4
in [[2026-02-22-cli-ecosystem-factoring-research]] section 6, Option C).

### Phase 4: Delete import-fallback antipatterns

**Goal:** Remove dead code and silent degradation paths that mask installation
errors.

**Changes** (based on
[[2026-02-22-cli-ecosystem-factoring-research]] section 3.6):

| Action | Location | Detail |
|:---|:---|:---|
| **Delete** | `cli.py:59-110` (after extraction: `core/helpers.py`) | 50-line fallback YAML parser. `PyYAML>=6.0` is a declared core dependency. Import `yaml` unconditionally. |
| **Delete** | `cli.py:120-131` (after extraction: `core/agents.py` or `core/types.py`) | Silent `PROVIDERS = {}` fallback + `logger` NameError bug. Import `ClaudeProvider`/`GeminiProvider` unconditionally. |
| **Move** | `cli.py:29` | Move `import html` to top-level stdlib imports. It is bundled inside a `try/except` for `skills_ref.prompt` but `html` is stdlib. |
| **Delete** | `subagent_cli.py:38-46` | `sys.exit(1)` guard around first-party `orchestration.*` imports. Let `ImportError` propagate with full traceback. |
| **Delete** | `team_cli.py:41-53` | `sys.exit(1)` guard around first-party `orchestration.team.*` imports. Let `ImportError` propagate with full traceback. |
| **Keep** | `cli.py:1593+` (`doctor_run`/`readiness_run`) | Legitimate diagnostic probing of optional `[rag]` extras. |
| **Keep** | `vault_cli.py:377-383` | Legitimate lazy-import guard for optional RAG dependencies with user-facing error message. |
| **Keep** | `cli.py:28-32` (after moving `html`) | `skills_ref.prompt` is a genuinely optional third-party dependency not in `pyproject.toml`. |

## Rationale

The restructuring is driven by three findings from
[[2026-02-22-cli-ecosystem-factoring-research]]:

**Naming accuracy matters for navigation.** When `vaultspec.core` contains
only config and workspace resolution, developers looking for the "core" of
the system are misdirected. The research (section 4) shows that `core`
provides none of the domain functions that other modules depend on for
resource management. Renaming it to `config` and reclaiming `core` for the
actual domain library aligns the package structure with the dependency graph.

**Monolithic CLI modules resist testing.** The research (section 1.1)
documents that `cli.py` is 2460 lines with 13 mutable module-level globals,
import-time side effects, and no separation between library logic and CLI
dispatch. Extracting the domain logic into `vaultspec.core` submodules makes
every function independently importable and testable without triggering
argparse construction or workspace resolution.

**Duplication breeds inconsistency.** The research (sections 2.1--2.7 and
3.1--3.5) catalogs 6 categories of duplication across the four CLI modules,
including 4 divergent implementations of `_get_version()`, 4 different logging
setup patterns, and 2 incompatible async execution strategies. The shared
`cli_common.py` module eliminates this duplication and enforces consistency.

The phased approach was chosen over a single large refactoring because each
phase is independently verifiable via the test suite, and phases 1 and 2
can execute in parallel to reduce calendar time.

## Consequences

### Import path changes (high-churn, low-risk)

Phase 1 touches **36 files** (34 in `src/`, 2 in `tests/`) to update
`vaultspec.core` to `vaultspec.config`. This is the highest-churn phase but
the lowest-risk because the change is purely mechanical -- a global
find-and-replace with no logic changes. The deprecation shim at
`vaultspec.core` provides a fallback for any missed references.

### `pyproject.toml` entry points (no change required)

All five entry points (`vaultspec`, `vaultspec-mcp`, `vaultspec-vault`,
`vaultspec-team`, `vaultspec-subagent`) reference top-level module paths
(`vaultspec.cli:main`, `vaultspec.server:main`, etc.) that are not affected
by the internal restructuring. The `cli.py` file remains at
`src/vaultspec/cli.py` -- it just becomes thinner. No `pyproject.toml` entry
point changes are needed.

### Risk: the rename cascade

The primary risk is an incomplete rename in Phase 1. If any file is missed,
the deprecation shim at `vaultspec.core` will catch it at runtime with a
warning rather than a hard failure. The mitigation strategy is:

- Use `rg "from vaultspec\.core" src/ tests/` to generate the exhaustive
  file list before starting.
- Execute the rename via scripted find-and-replace, not manual editing.
- Run the full test suite immediately after.
- The CI pipeline will catch any remaining references.

### Risk: mutable globals during Phase 3

Moving the 13 mutable `Path` globals and `TOOL_CONFIGS` dict from `cli.py`
to `core/types.py` preserves the current anti-pattern rather than fixing it.
This is an intentional trade-off: fixing the globals (replacing them with a
`CLIContext` dataclass) requires touching ~60 function signatures and is
deferred to a future phase. The risk is that the globals in `core/types.py`
become a new point of coupling, but this is no worse than the current state
where they live in `cli.py`.

### Benefits

- **Correct naming.** `vaultspec.config` contains config. `vaultspec.core`
  contains the domain engine. Import paths communicate architectural intent.

- **Testable library.** Resource management functions can be imported and
  tested without loading CLI infrastructure or triggering import-time side
  effects.

- **Consistent CLI modules.** All four entry points use shared boilerplate
  from `cli_common.py`, eliminating behavioral divergence in version reading,
  logging setup, workspace resolution, and async execution.

- **Smaller files.** `cli.py` drops from 2460 lines to ~700 lines. Each
  `core/` submodule is 80--200 lines. Code navigation and review become
  tractable.

- **Elimination of dead code.** Removing the import-fallback antipatterns
  deletes ~60 lines of dead code and fixes the `logger` NameError bug
  documented in
  [[2026-02-22-cli-ecosystem-factoring-research]] section 3.6.2.

- **Extensibility.** Adding new resource types follows the established
  `core/<resource>.py` pattern rather than appending to a monolith.
