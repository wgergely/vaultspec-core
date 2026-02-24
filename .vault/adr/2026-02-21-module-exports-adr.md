---
tags:
  - "#adr"
  - "#module-exports"
date: "2026-02-21"
related:
  - "[[2026-02-21-module-exports-part1-research]]"
  - "[[2026-02-21-module-exports-part2-research]]"
  - "[[2026-02-21-module-exports-part3-research]]"
  - "[[2026-02-21-packaging-restructure-adr]]"
---
<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `module-exports` adr: `__all__ + __init__ re-exports + relative imports` | (**status:** `accepted`)

## Problem Statement

The `vaultspec` package (recently restructured into `src/vaultspec/`) uses absolute imports everywhere (`from vaultspec.core.config import get_config`). There are no `__all__` declarations, no `__init__.py` re-exports, and consumers reach deep into sub-module internals. This couples every consumer to the internal file structure -- renaming a file or moving a function between modules within a package breaks all external callers. There is no stable public API surface.

## Considerations

The [[2026-02-21-module-exports-part1-research]], [[2026-02-21-module-exports-part2-research]], and [[2026-02-21-module-exports-part3-research]] documents provide an exhaustive audit of the current import structure. Key findings that inform this decision:

- **Scale**: approximately 160 absolute `from vaultspec.*` imports exist in production code and approximately 224 in test files, totaling roughly 384 import statements that must be addressed. The work is mechanical but large.
- **Dependency DAG**: the package dependency graph is acyclic and well-ordered. `core` is a true leaf (zero internal dependencies). `vaultcore` depends only on `core` (all deferred). From there the graph fans out: `graph`, `metrics`, and `verification` depend on `vaultcore`; `rag` depends on `vaultcore`, `graph`, `metrics`, and `verification`; `orchestration` depends on `vaultcore`, `core`, and `protocol`; `protocol` depends on `core` and has a partial reverse dependency from `orchestration`. `subagent_server` sits at the top, consuming `orchestration`, `protocol`, `vaultcore`, and `core`. Execution order must follow this DAG bottom-up.
- **Three distinct re-export strategies are needed** based on package characteristics:
  - **Eager re-export**: the `__init__.py` imports from sub-modules at package load time. Safe and appropriate for `core`, `vaultcore`, `hooks`, `graph`, `metrics`, `verification`, and `subagent_server`. These packages have no heavy optional dependencies and no circular risk from eager loading.
  - **Selective re-export**: the `__init__.py` eagerly re-exports only the modules that have stdlib-only dependencies, leaving modules with heavy third-party dependencies (`acp`, `a2a-sdk`, `httpx`, `claude-agent-sdk`) as deep-import-only. This applies to `orchestration`, where `subagent.py` and `team.py` pull in SDK dependencies that most consumers do not need.
  - **Lazy re-export**: the `__init__.py` uses a `__getattr__`-based lazy loading pattern so that importing the package does not trigger import of torch, sentence-transformers, or lancedb. This applies exclusively to `rag`.
- **Entry points are excluded**: CLI modules (`cli.py`, `vault_cli.py`, `team_cli.py`, `subagent_cli.py`) and `server.py` are top-level entry points, not consumed by other packages. They should keep absolute imports but target package-level exports once those exist (e.g., `from vaultspec.core import get_config` rather than `from vaultspec.core.config import get_config`).
- **Bidirectional dependency**: `orchestration.subagent` imports from multiple `protocol.*` sub-modules at the top level, while `protocol.a2a.executors.gemini_executor` imports `run_subagent` from `orchestration.subagent`. This is currently safe because neither package's `__init__.py` eagerly re-exports the offending modules. The selective re-export strategy for `orchestration` and the shallow `__init__.py` for `protocol` preserve this safety -- as long as `protocol/__init__.py` does not eagerly import from `a2a/executors/`, the cycle cannot trigger.
- **No other circular risks**: the [[2026-02-21-module-exports-part3-research]] confirmed that `metrics -> verification` is one-way and lazy, `rag -> graph/metrics/verification` is one-way and lazy, and all paths through `core` and `vaultcore` are strictly inward.

## Constraints

- All approximately 384 import statements must be rewritten across production and test code.
- The `rag/` package has GPU-dependent optional dependencies (torch, sentence-transformers, lancedb). Its `__init__.py` must not eagerly import any module that triggers these dependencies at load time.
- `orchestration/subagent.py` and `protocol/a2a/executors/gemini_executor.py` form a bidirectional dependency. Neither side's `__init__.py` may eagerly re-export the modules involved in this cycle.
- Tests should use public API imports (`from vaultspec.core import get_config`) to validate the API surface, except when explicitly testing private internals.
- `__all__` must be maintained going forward -- any new public symbol must be added to the relevant `__all__` list. This is a permanent maintenance obligation.
- The `mcp_tools/` package contains no-op stubs deferred to future phases of the packaging restructure. It should receive `__all__` and `__init__.py` re-exports now so that when stubs are implemented they follow the pattern from day one.

## Implementation

Implementation proceeds in seven phases, ordered by the dependency DAG so that each phase can be verified independently before the next begins. Each phase follows the same mechanical pattern: add `__all__` to every module, populate `__init__.py` with re-exports, convert intra-package imports to relative form, and rewrite all consumers to use package-level imports.

### Phase 1: Leaf packages -- `core/`, `vaultcore/`, `hooks/`

`core` is consumed by every other package in the codebase. Stabilizing its API first maximizes downstream impact. `vaultcore` and `hooks` depend only on `core` (all deferred), making them safe to process in the same phase.

- Add `__all__` to every module in `core/`, `vaultcore/`, and `hooks/` using the declarations from [[2026-02-21-module-exports-part1-research]] and [[2026-02-21-module-exports-part2-research]].
- Populate each package's `__init__.py` with eager re-exports from sub-modules using relative imports. For `core/__init__.py`: re-export `VaultSpecConfig`, `get_config`, `reset_config`, `WorkspaceLayout`, `resolve_workspace`. For `vaultcore/__init__.py`: re-export all 11 public symbols across its five modules. For `hooks/__init__.py`: re-export `SUPPORTED_EVENTS`, `Hook`, `HookAction`, `HookResult`, `load_hooks`, `trigger`.
- Convert all intra-package imports to relative form (e.g., `from .models import DocType` within `vaultcore/scanner.py`).
- Rewrite all consumers of these three packages across the entire codebase to use package-level imports (e.g., `from vaultspec.core import get_config` instead of `from vaultspec.core.config import get_config`).

### Phase 2: Mid-tier analytics -- `graph/`, `metrics/`, `verification/`

These are single-module packages that depend on `vaultcore` (now package-level importable from Phase 1). They follow the same eager re-export pattern.

- Add `__all__` to each package's `api.py` using the declarations from [[2026-02-21-module-exports-part3-research]].
- Populate each `__init__.py` with eager re-exports: `graph` re-exports `DocNode` and `VaultGraph`; `metrics` re-exports `VaultSummary` and `get_vault_metrics`; `verification` re-exports all eight public symbols.
- Rewrite consumers to use package-level imports (e.g., `from vaultspec.graph import VaultGraph`).
- No intra-package imports exist in these single-module packages, so no relative import conversion is needed.

### Phase 3: `rag/`

The `rag` package uses aggressive lazy loading to avoid pulling in torch and lancedb at import time. The `__init__.py` must preserve this behavior.

- Add `__all__` to every module (`api.py`, `embeddings.py`, `indexer.py`, `search.py`, `store.py`) using the declarations from [[2026-02-21-module-exports-part2-research]].
- Implement `__init__.py` using a `__getattr__`-based lazy loading pattern. The `__all__` list declares the full public API, but no import statements execute at module load time. Instead, `__getattr__` intercepts attribute access and performs the import on first use.
- Convert intra-package imports to relative form (e.g., `from .store import VaultDocument` within `indexer.py`).
- Rewrite external consumers (only `vault_cli.py` in production) to use package-level imports where the lazy `__init__` supports it.

### Phase 4: `orchestration/`

`orchestration` requires selective re-exports because `subagent.py` depends on `acp` SDK and `team.py` depends on `a2a-sdk` and `httpx`. Eagerly re-exporting these modules would force every consumer to have these heavy packages installed.

- Add `__all__` to all six modules using the declarations from [[2026-02-21-module-exports-part1-research]].
- Populate `__init__.py` with eager re-exports from `constants`, `utils`, `session_logger`, and `task_engine` only. These modules have no heavy third-party dependencies.
- `subagent` and `team` remain deep-importable only (e.g., `from vaultspec.orchestration.subagent import run_subagent`). They are explicitly excluded from `__init__.py` re-exports.
- Convert the single intra-package import (`subagent.py` -> `utils.py`) to relative form.
- Rewrite consumers to use package-level imports for the eagerly re-exported symbols.

### Phase 5: `protocol/`

The deepest hierarchy in the codebase: `protocol/`, `protocol/providers/`, `protocol/acp/`, `protocol/a2a/`, `protocol/a2a/executors/`. Each sub-package gets its own `__init__.py` re-exports.

- Add `__all__` to every module using the declarations from [[2026-02-21-module-exports-part2-research]].
- `protocol/providers/__init__.py` already has re-exports (the only existing example in the codebase). Extend it to include `ClaudeProvider`, `GeminiProvider`, and the full `base.py` public API.
- `protocol/acp/__init__.py`: re-export `SubagentError`, `SubagentResult`, `SessionLogger`, `SubagentClient`, `ClaudeACPBridge`.
- `protocol/a2a/__init__.py`: re-export from `server`, `agent_card`, `discovery`, `state_map`. Do NOT re-export from `executors/` at this level.
- `protocol/a2a/executors/__init__.py`: re-export `ClaudeA2AExecutor` and `GeminiA2AExecutor`. This is safe because the executors `__init__` is only loaded when explicitly imported, not transitively from `protocol/__init__`.
- `protocol/__init__.py`: re-export the most commonly consumed symbols from `providers` and `acp`. Do NOT transitively re-export from `a2a/executors/` to avoid triggering the bidirectional dependency with `orchestration`.
- Convert all intra-package imports to relative form throughout the hierarchy.
- Rewrite consumers to use the appropriate package-level import (e.g., `from vaultspec.protocol.providers import ClaudeProvider`).

### Phase 6: `subagent_server/`

- Add `__all__` to `server.py` using the declaration from [[2026-02-21-module-exports-part3-research]].
- Populate `__init__.py` with eager re-exports of the primary integration API: `initialize_server`, `register_tools`, `subagent_lifespan`.
- Convert internal imports to relative form (currently a single-module package, so minimal work).
- Rewrite consumers (`server.py` at the top level and tests) to use package-level imports.

### Phase 7: Top-level entry points and tests

- CLI modules (`cli.py`, `vault_cli.py`, `team_cli.py`, `subagent_cli.py`) and `server.py`: keep absolute imports but retarget them to package-level exports (e.g., `from vaultspec.core import get_config` instead of `from vaultspec.core.config import get_config`). These are entry points, not library code -- relative imports provide no benefit here.
- `logging_config.py`: add `__all__` exporting `configure_logging` and `reset_logging`. No `__init__.py` changes needed (standalone top-level module).
- `__main__.py`: optionally convert `from vaultspec.cli import main` to `from .cli import main` (negligible benefit, low priority).
- Rewrite all test imports (approximately 224 statements) to use package-level imports where they target public API symbols. Tests that explicitly test private internals (e.g., `_parse_json_list`, `_extract_feature`) retain their deep imports.
- `mcp_tools/`: add `__all__` to each stub module and populate `__init__.py` with re-exports of the `register_tools` functions under disambiguated names (`register_vault_tools`, `register_team_tools`, `register_framework_tools`).

## Rationale

- [[2026-02-21-module-exports-part1-research]] established that `core` is the true leaf dependency consumed by every other package. Stabilizing it first (Phase 1) ensures all subsequent phases can immediately use the new package-level imports, reducing the total number of intermediate states.
- [[2026-02-21-module-exports-part2-research]] identified the `protocol` package as the deepest hierarchy but confirmed that the `__init__.py` re-export pattern scales cleanly across nested sub-packages. It also identified the `rag` package's lazy-import discipline as a hard constraint requiring the `__getattr__` approach.
- [[2026-02-21-module-exports-part3-research]] quantified the total scope (approximately 384 imports), confirmed no circular risks exist with selective re-exports, and validated that leaf-first execution is the safest ordering.
- The `__all__` + `__init__.py` re-export pattern is standard Python practice. Major libraries (numpy, requests, FastAPI, pydantic) all use this approach to decouple their public API from their internal file structure.
- Relative imports within packages prevent the package from knowing its own absolute name, which supports future renaming or relocation without touching every internal import statement. This directly addresses the coupling problem identified in the problem statement.
- The three-strategy approach (eager, selective, lazy) is driven by concrete technical constraints rather than preference. Eager is the default. Selective exists solely because `orchestration.subagent` and `orchestration.team` pull in heavy SDKs that not all consumers need. Lazy exists solely because `rag` must not trigger torch/lancedb at import time.

## Consequences

**Positive outcomes**:

- A stable public API surface emerges for every package. Internal file reorganization within a package (splitting a module, renaming a file, moving a function between modules) no longer breaks external consumers as long as the `__init__.py` re-exports are maintained.
- `__all__` enforces intentional API design. Every public symbol is explicitly declared, making it clear what is part of the contract and what is an implementation detail.
- Consumer import statements become shorter and more uniform (`from vaultspec.core import get_config` rather than `from vaultspec.core.config import get_config`).
- Relative imports make packages self-contained and relocatable within the source tree.
- Tests that import from the public API surface serve as regression guards -- if a re-export is accidentally removed, the test suite catches it immediately.

**Negative outcomes**:

- Approximately 384 import statements must be rewritten. While mechanical, this is a large changeset that touches nearly every file in the codebase.
- `__all__` imposes a permanent maintenance burden. Every new public symbol must be added to the relevant `__all__` list, and the corresponding `__init__.py` re-export must be updated.
- The `__getattr__`-based lazy loading in `rag/__init__.py` adds a layer of indirection that makes the import mechanism less obvious to developers unfamiliar with the pattern.
- The selective re-export strategy in `orchestration` means some symbols (`run_subagent`, `TeamCoordinator`) require deep imports. This exception must be documented clearly so developers know which symbols are available at the package level and which require reaching into sub-modules.
- Developers joining the project must learn the "import from the package, not the module" convention. Linting or code review enforcement may be needed to maintain discipline.

**Future work**:

- Consider generating `__all__` declarations automatically via tooling. Ruff has experimental support for detecting missing `__all__` entries, and a custom pre-commit hook could enforce completeness.
- When the `mcp_tools/` stubs are implemented (Phases 3-5 of the [[2026-02-21-packaging-restructure-adr]]), they will follow this same `__all__` + `__init__.py` re-export pattern from day one, avoiding the retrofit cost that this ADR addresses for existing packages.
- The bidirectional `orchestration` <-> `protocol` dependency should be revisited. A potential resolution is to extract the `run_subagent` function signature into an abstract interface in `protocol` that `orchestration` implements, eliminating the reverse import entirely.
