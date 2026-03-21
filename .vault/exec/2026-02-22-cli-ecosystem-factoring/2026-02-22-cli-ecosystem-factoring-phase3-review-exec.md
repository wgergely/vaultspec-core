---
tags:
  - '#exec'
  - '#cli-ecosystem-factoring'
date: '2026-02-22'
related:
  - '[[2026-02-22-cli-ecosystem-factoring-plan]]'
  - '[[2026-02-22-cli-ecosystem-factoring-phase3-step1]]'
---

# cli-ecosystem-factoring phase3 code review

## reviewer

vaultspec-code-reviewer (inline — subagent CLI unavailable due to pre-existing
`run_subagent` export gap in `vaultspec.orchestration.__init__`)

## verdict

**PASS — no violations found**

## checks performed

### 1. behavioral fidelity

- `sync_files()`, `sync_skills()`, `print_summary()` in `core/sync.py`: logic
  identical to original cli.py. Prune logic, dry-run branching, error
  accumulation, result counting all preserved.

- `transform_rule`, `transform_agent`, `transform_skill`: match originals exactly.

- `collect_rules`, `collect_agents`, `collect_skills`, `collect_system_parts`:
  correctly reproduce original collection logic.

- `_generate_config`, `_generate_agents_md`, `_generate_system_prompt`,
  `_generate_system_rules`: logic preserved faithfully in config_gen.py / system.py.

### 2. mutable globals pattern

- All submodules use `from . import types as _t` and access globals as
  `_t.SYMBOL` — correct live-binding.

- `helpers.py resolve_model` uses a function-local import for `PROVIDERS` which
  is set at module import time (not by `init_paths()`). Correct.

### 3. backward compat via `__getattr__`

- `cli.py __getattr__` covers all 13 path globals.

- Private helpers re-exported explicitly: `_generate_config`, `_is_cli_managed`,
  `_collect_agent_listing`, `_collect_skill_listing`, `_generate_system_prompt`,
  `_generate_system_rules`, `to_prompt`, `parse_frontmatter`.

- `sync_skills_fn as sync_skills` correctly exposed.

### 4. no mock usage

- All test files use real filesystem operations only.
- `resolve_fn=lambda *_args, **_kw: None` is a real callable parameter, not a patch.
- No `unittest.mock`, `pytest-mock`, or `monkeypatch.setattr` found.

### 5. print_summary uses print()

- `core/sync.py:180`: `print(f"  {resource}: {summary}")` — correct.

### 6. to_prompt error handling

- try/except around `to_prompt(skill_dirs)` catches `Exception` broadly and
  falls through to Markdown fallback. Appropriate for `skills_ref`
  `ValidationError`/`ParseError` on malformed skill frontmatter.

## test results at review time

```
168 passed, 4 warnings
```

4 pre-existing failures in `test_integration.py` confirmed unrelated to Phase 3.

## status

approved — Phase 3 complete
