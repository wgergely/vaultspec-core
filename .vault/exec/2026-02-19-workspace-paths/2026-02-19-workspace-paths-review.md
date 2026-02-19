---
tags:
  - "#exec"
  - "#workspace-paths"
date: "2026-02-19"
related:
  - "[[2026-02-19-workspace-path-decoupling-adr]]"
  - "[[2026-02-19-workspace-paths-implementation-plan]]"
---

# `workspace-paths` code review

**Status:** `REVISION REQUIRED`

## Audit Context

- **Plan:** `[[2026-02-19-workspace-paths-implementation-plan]]`
- **Scope:**
  - `.vaultspec/lib/src/core/workspace.py` (new, 381 lines)
  - `.vaultspec/lib/src/core/tests/test_workspace.py` (new, 341 lines)
  - `.vaultspec/lib/src/core/config.py` (modified)
  - `.vaultspec/lib/scripts/_paths.py` (modified)
  - `.vaultspec/lib/scripts/cli.py` (modified)
  - `.vaultspec/lib/scripts/subagent.py` (modified)
  - `.vaultspec/lib/scripts/docs.py` (modified)
  - `requirements.txt` (modified)
  - `extension.toml` (new)

## Findings

### Critical / High (Must Fix)

- **[HIGH]** `cli.py:2249-2254` — `resolve_workspace()` called from `main()` without `framework_root`. When `--content-dir` is provided, EXPLICIT mode falls back to `fw_root = framework_root or (content_root / framework_dir_name)`, producing a nested path like `<content_dir>/.vaultspec` which is almost certainly wrong. The structurally-known `_FRAMEWORK_ROOT` from `_paths.py` is available as `_PATHS_LAYOUT.framework_root` but is not forwarded.

  ```python
  # cli.py main() — missing framework_root
  layout = resolve_workspace(
      root_override=args.root,
      content_override=getattr(args, "content_dir", None),
      # framework_root NOT passed — falls to content_root / ".vaultspec"
  )
  ```

  Fix: pass `framework_root=_PATHS_LAYOUT.framework_root` in all three CLI `main()` call sites (cli.py, subagent.py, docs.py `_resolve_root()`).

- **[HIGH]** `subagent.py:331-336` — `resolve_workspace()` called without `framework_root`, same issue as cli.py. Additionally, `args.root` is already `.resolve()`'d on line 328, but `args.root` still defaults to `ROOT_DIR` (the `_paths.py` bootstrap output). When only `--content-dir` is provided and `--root` defaults to `ROOT_DIR`, the intent (EXPLICIT mode) requires both overrides to be explicitly set. The current code silently enters EXPLICIT mode with the bootstrapped `ROOT_DIR` as `root_override`, which may produce a non-obvious layout. This diverges from the ADR's principle of "explicit env vars override everything" — the user intended only to override content, not both.

  The ADR states row 2 of the matrix (only `ROOT_DIR` set) is STANDALONE mode, which would be correct if content_override were None. But with a content_override and a non-None root (the default), EXPLICIT mode triggers.

- **[HIGH]** `workspace.py:355-365` — Structural fallback when `framework_root` is provided sets `content_root = framework_root` (line 357). This means `content_root` equals the `.vaultspec/` directory itself. However, `init_paths()` then computes `content / "rules" / "rules"`, yielding `.vaultspec/rules/rules` — which is correct for the current structure. But the ADR's validation rule (`content_root must be a directory`) will fail here unless `.vaultspec/` exists, which it does in normal deployment. This is structurally correct but the semantics of `content_root = framework_root` vs `content_root = framework_root / "rules"` is surprising and undocumented. Not a bug in practice but risks misuse. Flagged HIGH because the ADR's description of `content_root` ("where rules/, agents/, skills/ live") implies it should be the parent of those directories — i.e., `framework_root` is already that parent, so `content_root = framework_root` is semantically correct.

### Medium / Low (Recommended)

- **[MEDIUM]** `workspace.py:291-308` — EXPLICIT mode condition `if content_override is not None and root_override is not None`. The ADR's matrix row 1 describes this case. However there is no guard against `content_override.resolve()` failing or `root_override.resolve()` failing on a non-existent path — `Path.resolve()` on Python 3.13 does not raise on missing paths (it resolves lexically), so this is not a crash risk, but the validation in `_validate()` will raise `WorkspaceError` with a clear message. Acceptable.

- **[MEDIUM]** `cli.py:155-240` — `init_paths()` backwards-compat branch (`isinstance(layout, Path)`) changes the old path semantics. Old code: `RULES_SRC_DIR = root / fw_dir / "rules"` (→ `.vaultspec/rules`). New code: `content = root / cfg.framework_dir`, then `RULES_SRC_DIR = content / "rules" / "rules"` (→ `.vaultspec/rules/rules`). This is a structural path change even in the compat branch. It reflects the actual current directory layout (`.vaultspec/rules/rules/` exists) and is correct — the old code pointed to the wrong location. But callers passing a bare `Path` will silently get the new deeper paths. Any external callers of `init_paths(some_path)` will need to be audited. Internal callers are only `test-project` fixtures — should be verified.

- **[MEDIUM]** `cli.py:184-185` — `FRAMEWORK_CONFIG_SRC = SYSTEM_SRC_DIR / "framework.md"` and `PROJECT_CONFIG_SRC = SYSTEM_SRC_DIR / "project.md"` are still hardcoded names. These are stable pre-existing conventions, not a regression. No action required.

- **[MEDIUM]** `test_workspace.py` — 11 of the 19 test cases cover `resolve_workspace()`. Missing explicit test for the EXPLICIT mode behaviour when `framework_root` is not provided (the HIGH issue above). The test `test_explicit_mode_both_overrides` always passes `framework_root=fw`, so the fallback path `(content_root / framework_dir_name)` is never exercised in tests.

- **[MEDIUM]** `test_workspace.py:280-290` — `test_framework_root_from_structural_not_env` uses `root_override=root` (STANDALONE, not EXPLICIT) to verify `framework_root` forwarding. The test correctly validates that a passed `framework_root` is preserved. But it does not test the more important case: that CLI `main()` should always forward `_PATHS_LAYOUT.framework_root`. This is a test coverage gap, not a code bug.

- **[LOW]** `workspace.py:62-67` — `_strip_unc()` checks `s.startswith("\\\\?\\")`. This is correct for Windows UNC paths. The ADR mentions `dunce::canonicalize()` as the Rust companion's approach; Python 3.13 on Windows will sometimes produce `\\?\` prefixes from `Path.resolve()`. The guard is correct and necessary.

- **[LOW]** `extension.toml:11` — `install = "pip install -e '.[dev]'"` installs dev extras at runtime. This is a companion-project integration concern — the companion reads this file to know how to install. Using `.[dev]` in the extension manifest will install test/lint tools in production deployments. Should be `pip install -e '.'` (runtime only). LOW because this is a manifest interpretation question and the companion project may filter extras, but it's worth clarifying.

- **[LOW]** `subagent.py:327-336` — `if args.root is not None: args.root = args.root.resolve()` runs before the content_dir check. But `args.root` defaults to `ROOT_DIR` (not `None`) on line 216, so `args.root is not None` is always `True`. The `resolve()` call is always executed. This is harmless but the check is dead code. The condition should be `if args.root != ROOT_DIR` or removed entirely.

## ADR Deliverables Compliance

| # | Deliverable | Status |
|---|---|---|
| 1 | `core/workspace.py` — all 5 symbols | PASS |
| 2 | `core/config.py` — `content_dir` + registry | PASS |
| 3 | `_paths.py` — two-step bootstrap | PASS |
| 4 | `cli.py` — `init_paths(WorkspaceLayout)` + `--content-dir` | PASS (with HIGH caveat) |
| 5 | `subagent.py`, `docs.py` — `--content-dir` | PASS (with HIGH caveat) |
| 6 | `core/tests/test_workspace.py` — all 6 matrix rows | PASS (coverage gap noted) |
| 7 | `requirements.txt` — aligned to pyproject.toml | PASS |
| 8 | `extension.toml` — companion manifest | PASS (LOW concern) |

## Resolution Matrix Verification

| ADR Row | Condition | Expected mode | Verified |
|---|---|---|---|
| 1 | Both CONTENT_DIR + ROOT_DIR set | EXPLICIT | PASS (workspace.py:291) |
| 2 | Only ROOT_DIR set | STANDALONE | PASS (workspace.py:311) |
| 3 | No env vars, classic git | STANDALONE | PASS (workspace.py:329-349) |
| 4 | No env vars, container git (.gt/) | STANDALONE | PASS (workspace.py:140-156) |
| 5 | No env vars, linked worktree (.git file) | STANDALONE | PASS (workspace.py:175-216) |
| 6 | No env vars, no git | STANDALONE | PASS (workspace.py:352-380) |

vault_root = output_root / ".vault" in ALL 6 rows: **PASS** (lines 302, 319, 344, 358, 375)

## Safety Checks

- **No `.unwrap()` / `panic!` / `todo!`**: N/A (Python). No equivalent `assert` in production paths outside tests. PASS.
- **No hardcoded paths**: `.vaultspec` appears as a default parameter value with `framework_dir_name: str = ".vaultspec"`, which is overridable. PASS.
- **No external dependencies in workspace.py**: stdlib only (os, logging, dataclasses, enum, pathlib). PASS.
- **WorkspaceLayout is frozen**: `@dataclass(frozen=True)`. PASS. Verified by `test_frozen_layout`.
- **LayoutMode has exactly 2 values**: `STANDALONE`, `EXPLICIT`. PASS.
- **`.git` checked with `.exists()` not `.is_dir()`**: `_walk_up_for_git()` line 105 uses `dot_git.exists()`. PASS.
- **Bootstrap ordering**: `_paths.py` adds `LIB_SRC_DIR` to `sys.path` before any library import. PASS.
- **`framework_root` never derived from env vars**: In `_paths.py`, `_FRAMEWORK_ROOT` is always computed from `Path(__file__).resolve().parent` chain. PASS.

## Recommendations

The two HIGH findings represent an architectural correctness gap: the `framework_root` that `_paths.py` computes structurally is not forwarded to CLI-level calls to `resolve_workspace()`. This means EXPLICIT mode deployments (the primary use case for the companion project, invoked via `--content-dir`) will have a `framework_root` pointing to a nested `.vaultspec/.vaultspec` path rather than the actual `.vaultspec/` directory. The validation check `framework_root / lib` will fail at runtime, causing a `WorkspaceError`. So this issue would surface immediately when tested — it is not a silent correctness bug but an immediate crash.

**Required fixes before merge:**

1. In `cli.py` `main()` (line 2249): add `framework_root=_PATHS_LAYOUT.framework_root` to the `resolve_workspace()` call.
2. In `subagent.py` `main()` (line 332): same fix.
3. In `docs.py` `_resolve_root()` (line 203): same fix.
4. Add a test case for EXPLICIT mode without `framework_root` to confirm the validation error message is actionable.
5. Consider the `extension.toml` install command (LOW) before companion project integration.

Once the three `framework_root` forwarding fixes are applied, the implementation is architecturally sound and complete.

## Notes

The core `workspace.py` module is well-designed: clean data types, no external dependencies, correct UNC stripping, proper walk-up termination, and actionable validation errors. The git detection logic correctly handles all five layout modes described in the ADR. The `_paths.py` two-step bootstrap is clean and correct. The test suite covers the primary scenarios well. The HIGH findings are limited to call-site omissions in the three CLI entry points, not in the core module itself.
