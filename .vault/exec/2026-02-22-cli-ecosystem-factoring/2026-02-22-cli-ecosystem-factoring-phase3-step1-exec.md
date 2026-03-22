---
tags:
  - '#exec'
  - '#cli-ecosystem-factoring'
date: '2026-02-22'
related:
  - '[[2026-02-22-cli-ecosystem-factoring-plan]]'
  - '[[2026-02-22-cli-ecosystem-factoring-adr]]'
---

# cli-ecosystem-factoring phase3 step1 — core submodule extraction

## objective

Extract all domain business logic from `src/vaultspec/cli.py` into 9 submodules
under `src/vaultspec/core/`, reducing `cli.py` to a thin argparse wrapper.

## files created

- `src/vaultspec/core/types.py` — `ToolConfig`, `SyncResult`, Path globals, `init_paths()`
- `src/vaultspec/core/helpers.py` — yaml helpers, `build_file`, `atomic_write`, `ensure_dir`, `resolve_model`, `_launch_editor`
- `src/vaultspec/core/sync.py` — `sync_files()`, `sync_skills()`, `print_summary()`
- `src/vaultspec/core/rules.py` — `collect_rules`, `transform_rule`, rules CRUD
- `src/vaultspec/core/agents.py` — `collect_agents`, `transform_agent`, agents CRUD
- `src/vaultspec/core/skills.py` — `collect_skills`, `transform_skill`, skills CRUD
- `src/vaultspec/core/config_gen.py` — `_generate_config`, `_generate_agents_md`, `_is_cli_managed`, `config_show`, `config_sync`
- `src/vaultspec/core/system.py` — `_generate_system_prompt`, `_generate_system_rules`, `system_show`, `system_sync`
- `src/vaultspec/core/resources.py` — `resource_show`, `resource_edit`, `resource_remove`, `resource_rename`
- `src/vaultspec/core/__init__.py` — full public API re-exports

## files modified

- `src/vaultspec/cli.py` — reduced to ~980 lines (thin wrapper + argparse)
  - imports all domain functions from `vaultspec.core`
  - adds `__getattr__` to proxy mutable path globals live from `_core_types`
  - re-exports private helpers (`_generate_config`, `_is_cli_managed`, etc.) for test backward compat

## key technical decisions

### mutable globals pattern

All submodules use `from . import types as _t` and access globals as `_t.RULES_SRC_DIR`
etc. to ensure they always see post-`init_paths()` values.

### backward compat

- `import vaultspec.cli as cli; cli.ROOT_DIR` works via `__getattr__` proxy
- `from vaultspec.cli import main` works directly
- Private helpers accessible via `cli._generate_config` etc. via explicit re-export

### print_summary output

Uses `print()` (not `logger.info`) to preserve test capsys compatibility with original behavior.

### to_prompt error handling

`_collect_skill_listing()` wraps `to_prompt()` call in try/except to fall through
to Markdown fallback when skills have missing `name` frontmatter fields.

## test results

```
168 passed, 4 warnings in 9.77s
```

4 pre-existing failures in `test_integration.py` (missing `run_subagent` export
from `vaultspec.orchestration`) are unrelated to Phase 3 — confirmed by checking
HEAD state before changes.

## status

complete
