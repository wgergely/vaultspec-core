---
title: "Stale Path Audit: Old Hierarchy References in .vaultspec/lib/"
date: 2026-02-20
tags: [#reference, #audit]
status: complete
---

```
Crate(s): N/A (Python project)
File(s): See findings below
Related: N/A
```

## Summary

After the rules hierarchy migration (all content moved into `.vaultspec/rules/`), a subset
of files under `.vaultspec/lib/` retain references to the **pre-migration** flat layout:

- `.vaultspec/agents/`
- `.vaultspec/skills/`
- `.vaultspec/system/`
- `.vaultspec/templates/`
- `.vaultspec/constitution.md`

No references to `constitution` were found anywhere in `lib/`. All findings below are
broken into three categories: **STALE** (points to old non-`rules/`-prefixed path),
**UPDATED** (already uses `rules/` prefix), and **BORDERLINE** (docstring/comment only,
no functional impact).

---

## Category A — STALE: Test Fixtures Creating Old-Layout Directories

These create or reference `.vaultspec/<subdir>` directly without `rules/` nesting. The
production code now reads from `.vaultspec/rules/agents` etc., so these fixtures build
trees that the code under test will NOT find.

### `.vaultspec/lib/tests/cli/conftest.py`

| Line | Content | Status |
|------|---------|--------|
| 32 | `".vaultspec/agents"` — mkdir in `setup_rules_dir()` | STALE |
| 33 | `".vaultspec/skills"` — mkdir in `setup_rules_dir()` | STALE |
| 34 | `".vaultspec/system"` — mkdir in `setup_rules_dir()` | STALE |

The `setup_rules_dir()` helper creates the old flat layout alongside `.vaultspec/rules`.
Tests that write into `.vaultspec/agents/`, `.vaultspec/skills/`, or `.vaultspec/system/`
and expect `cli.py` to collect them will fail because `cli.py` resolves
`AGENTS_SRC_DIR = content / "rules" / "agents"` (line 182 of `cli.py`).

### `.vaultspec/lib/tests/cli/test_sync_parse.py`

| Line | Content | Status |
|------|---------|--------|
| 123 | `assert TEST_PROJECT / ".vaultspec" / "agents" == cli.AGENTS_SRC_DIR` | STALE |
| 124 | `assert TEST_PROJECT / ".vaultspec" / "skills" == cli.SKILLS_SRC_DIR` | STALE |
| 125 | `assert TEST_PROJECT / ".vaultspec" / "system" == cli.SYSTEM_SRC_DIR` | STALE |
| 127 | `TEST_PROJECT / ".vaultspec" / "system" / "framework.md" == cli.FRAMEWORK_CONFIG_SRC` | STALE |
| 131 | `TEST_PROJECT / ".vaultspec" / "system" / "project.md" == cli.PROJECT_CONFIG_SRC` | STALE |

These assertions directly contradict what `cli.py:init_paths()` now sets:
- `AGENTS_SRC_DIR = content / "rules" / "agents"` (i.e. `.vaultspec/rules/agents`)
- `SKILLS_SRC_DIR = content / "rules" / "skills"`
- `SYSTEM_SRC_DIR = content / "rules" / "system"`

These tests will FAIL against current production code.

### `.vaultspec/lib/tests/cli/test_sync_collect.py`

Massive block of stale references — all test methods write fixture data into
`.vaultspec/<subdir>` directly instead of `.vaultspec/rules/<subdir>`:

| Lines | Stale Path Pattern | Status |
|-------|--------------------|--------|
| 60, 71, 172, 343 | `TEST_PROJECT / ".vaultspec" / "agents" / ...` | STALE |
| 77, 80, 187, 357 | `TEST_PROJECT / ".vaultspec" / "skills" / ...` | STALE |
| 93, 96, 106, 203, 206, 216, 230, 246, 250, 254, 270, 279, 282, 285, 300, 307, 311, 315, 327, 330, 340, 354, 371, 374, 390, 393, 396, 408, 411, 429, 436, 439, 442 | `TEST_PROJECT / ".vaultspec" / "system" / ...` | STALE |

### `.vaultspec/lib/tests/cli/test_sync_incremental.py`

| Lines | Stale Path Pattern | Status |
|-------|--------------------| -------|
| 154, 186, 358 | `TEST_PROJECT / ".vaultspec" / "agents"` | STALE |
| 215, 359 | `TEST_PROJECT / ".vaultspec" / "skills"` | STALE |
| 257, 294, 315, 322, 333, 336, 343, 360, 381 | `TEST_PROJECT / ".vaultspec" / "system" / ...` | STALE |

### `.vaultspec/lib/tests/cli/test_sync_operations.py`

| Lines | Stale Path Pattern | Status |
|-------|--------------------| -------|
| 355, 434 | `TEST_PROJECT / ".vaultspec" / "agents" / ...` | STALE |
| 359 | `TEST_PROJECT / ".vaultspec" / "skills" / ...` | STALE |
| 209, 222, 233, 248, 251, 265, 268, 281, 296, 299, 311, 326, 337, 362, 365 | `TEST_PROJECT / ".vaultspec" / "system" / ...` | STALE |

### `.vaultspec/lib/tests/cli/test_docs_cli.py`

| Line | Content | Status |
|------|---------|--------|
| 378–379 | Comment + `template_dir = tmp_path / ".vaultspec" / "templates"` | STALE |

The `vault.py` script resolves templates via `TEMPLATES_DIR = content / "rules" / "templates"`.
This fixture builds at `.vaultspec/templates` (no `rules/` nesting) so the template will
not be found.

### `.vaultspec/lib/tests/e2e/test_full_cycle.py`

| Lines | Stale Path Pattern | Status |
|-------|--------------------| -------|
| 55 | `root / ".vaultspec" / "agents"` — mkdir in `pipeline_root` fixture | STALE |
| 57 | `root / ".vaultspec" / "templates"` — mkdir in `pipeline_root` fixture | STALE |
| 95 | `root / ".vaultspec" / "agents" / "vaultspec-researcher.md"` | STALE |
| 370, 372 | `root / ".vaultspec" / "agents"` / agent file | STALE |

### `.vaultspec/lib/tests/e2e/test_mcp_e2e.py`

| Lines | Stale Path Pattern | Status |
|-------|--------------------| -------|
| 48 | `root / ".vaultspec" / "agents"` — mkdir in fixture | STALE |
| 58 | `root / ".vaultspec" / "agents" / "tester.md"` | STALE |
| 94 | `agents_dir = root / ".vaultspec" / "agents"` — local scan in test body | STALE |

### `.vaultspec/lib/tests/e2e/test_claude.py`

| Lines | Stale Path Pattern | Status |
|-------|--------------------| -------|
| 45 | `root / ".vaultspec" / "agents"` — mkdir in fixture | STALE |
| 98, 131 | `test_project_root / ".vaultspec" / "agents" / "tester.md"` | STALE |

### `.vaultspec/lib/tests/e2e/test_gemini.py`

| Lines | Stale Path Pattern | Status |
|-------|--------------------| -------|
| 45 | `root / ".vaultspec" / "agents"` — mkdir in fixture | STALE |
| 123, 155 | `test_project_root / ".vaultspec" / "agents" / "tester.md"` | STALE |

---

## Category B — STALE: Unit Test Fixtures in `src/`

### `.vaultspec/lib/src/orchestration/tests/conftest.py`

| Line | Content | Status |
|------|---------|--------|
| 9 | `(tmp_path / ".vaultspec" / "agents").mkdir(parents=True)` | STALE |

The `test_root_dir` fixture creates `.vaultspec/agents/` (old path). `orchestration/subagent.py`
resolves `agents_base = root_dir / fw_dir / "rules" / "agents"` (`.vaultspec/rules/agents`).

### `.vaultspec/lib/src/orchestration/tests/test_load_agent.py`

| Lines | Content | Status |
|-------|---------|--------|
| 42, 43 | `test_root_dir / ".vaultspec" / "agents"` — mkdir + write | STALE |
| 51, 70 | `agents_dir = test_root_dir / ".vaultspec" / "agents"` | STALE |
| 88, 89 | `test_root_dir / ".vaultspec" / "agents"` — mkdir + write | STALE |

All `TestLoadAgent` test methods write agent files to `.vaultspec/agents/` but the
`load_agent()` function resolves to `.vaultspec/rules/agents/`. These tests will fail to
find any agent files.

### `.vaultspec/lib/src/protocol/tests/conftest.py`

| Line | Content | Status |
|------|---------|--------|
| 11 | `(tmp_path / ".vaultspec" / "agents").mkdir(parents=True)` | STALE |

### `.vaultspec/lib/src/protocol/acp/tests/test_bridge_lifecycle.py`

| Line | Content | Status |
|------|---------|--------|
| 452 | `agents_dir = tmp_path / ".vaultspec" / "agents"` | STALE |

### `.vaultspec/lib/src/protocol/acp/tests/test_e2e_bridge.py`

| Lines | Content | Status |
|-------|---------|--------|
| 79 | `agents_dir = tmp_path / ".vaultspec" / "agents"` | STALE |
| 323, 330, 341 | `project_root / ".vaultspec" / "agents" / "jean-claude.md"` | STALE |

### `.vaultspec/lib/src/protocol/tests/test_fileio.py`

| Line | Content | Status |
|------|---------|--------|
| 91 | `target = test_root_dir / ".vaultspec" / "agents" / "rogue.md"` | STALE |

---

## Category C — BORDERLINE: Comments / Docstrings (No Functional Impact)

These describe old-path layout in prose but do not construct paths at runtime.

### `.vaultspec/lib/src/core/workspace.py`

| Line | Content | Status |
|------|---------|--------|
| 237 | `f"rules/, agents/, skills/."` in error message string | BORDERLINE (misleading — old layout listed as if still flat) |

The error message says "the directory containing `rules/, agents/, skills/`" but post-migration
the structure is `rules/agents/`, `rules/skills/`, etc. The message is factually wrong.

### `.vaultspec/lib/src/core/config.py`

| Line | Content | Status |
|------|---------|--------|
| 600 | `description="Default editor command for creating rules/agents/skills."` | BORDERLINE (acceptable — uses `/` as separator, not literal path) |

### `.vaultspec/lib/tests/cli/test_sync_incremental.py`

| Line | Content | Status |
|------|---------|--------|
| 3 | Module docstring: `"multi-pass rule/agent/skill/system/config sync"` | BORDERLINE (prose only, not a path) |

### `.vaultspec/lib/scripts/cli.py`

| Lines | Content | Status |
|-------|---------|--------|
| 1891 | `recommendations.append("Complete .vaultspec/ structure with system/")` | BORDERLINE (user-facing hint missing `rules/` prefix) |

---

## Category D — ALREADY UPDATED (confirmed correct)

These already reference `rules/<subdir>` correctly.

### `.vaultspec/lib/scripts/cli.py`

| Lines | Correct Path |
|-------|--------------|
| 181 | `RULES_SRC_DIR = content / "rules" / "rules"` |
| 182 | `AGENTS_SRC_DIR = content / "rules" / "agents"` |
| 183 | `SKILLS_SRC_DIR = content / "rules" / "skills"` |
| 184 | `SYSTEM_SRC_DIR = content / "rules" / "system"` |
| 185 | `TEMPLATES_DIR = content / "rules" / "templates"` |
| 1557–1560 | `"rules/agents"`, `"rules/skills"`, `"rules/templates"`, `"rules/system"` dir creation list |
| 1643–1653 | All `fw_dir / "rules" / ...` path checks |
| 1677–1678, 1732–1733 | `fw_dir / "rules" / "agents"` |

### `.vaultspec/lib/scripts/subagent.py`

| Lines | Correct Path |
|-------|--------------|
| 54, 177 | `content_root / "rules" / "agents"` |

### `.vaultspec/lib/src/orchestration/subagent.py`

| Lines | Correct Path |
|-------|--------------|
| 86, 89 | `content_root / "rules" / "agents"` |

### `.vaultspec/lib/src/subagent_server/server.py`

| Lines | Correct Path |
|-------|--------------|
| 113 | `AGENTS_DIR = CONTENT_ROOT / "rules" / "agents"` |

### `.vaultspec/lib/src/vault/hydration.py`

| Lines | Correct Path |
|-------|--------------|
| 62 | `base / "rules" / "templates" / name` |

---

## Discrepancy Summary

The production path-resolution code (cli.py, subagent.py, orchestration/subagent.py,
subagent_server/server.py, vault/hydration.py) has been **fully updated** to use the
new `rules/` nesting.

The **entire test layer** — both functional tests under `lib/tests/` and unit tests
under `lib/src/*/tests/` — has **not been updated**. Every fixture that creates
or references agent/skill/system/template files still uses the old flat layout. This
means the majority of sync and e2e tests are building fixture trees that the production
code will not find.

**Highest-priority stale files** (functional breakage, not just cosmetic):

1. `.vaultspec/lib/tests/cli/test_sync_parse.py` — assertion mismatch against `cli.AGENTS_SRC_DIR` etc.
2. `.vaultspec/lib/src/orchestration/tests/test_load_agent.py` — `load_agent()` will always raise `AgentNotFoundError`
3. `.vaultspec/lib/tests/cli/conftest.py` — shared autouse fixture builds wrong tree for all sync tests
4. `.vaultspec/lib/tests/cli/test_sync_collect.py` — all collect tests write to wrong dirs
5. `.vaultspec/lib/tests/cli/test_sync_incremental.py` — all incremental tests write to wrong dirs
6. `.vaultspec/lib/tests/cli/test_sync_operations.py` — all operation tests write to wrong dirs
7. `.vaultspec/lib/tests/e2e/` (test_full_cycle, test_mcp_e2e, test_claude, test_gemini) — fixtures populate wrong agent dirs
8. `.vaultspec/lib/src/protocol/acp/tests/test_e2e_bridge.py` — agent files written to wrong location
9. `.vaultspec/lib/src/protocol/acp/tests/test_bridge_lifecycle.py` — same
10. `.vaultspec/lib/src/orchestration/tests/conftest.py` — shared fixture for orchestration unit tests
11. `.vaultspec/lib/src/protocol/tests/conftest.py` — shared fixture for protocol unit tests
