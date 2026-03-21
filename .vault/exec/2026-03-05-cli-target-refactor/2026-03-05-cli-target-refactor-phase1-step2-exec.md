---
tags:
  - "#cli"
  - "#refactor"
  - "#phase1"
date: 2026-03-05
title: "Phase 1 Step 2: Global Reference Updates & Config Registry Cleanup"
---
# Global Reference Updates & Config Registry Cleanup

**Context:** Following the reorientation of `WorkspaceLayout` towards a single `target_dir`, all remaining usage of the older variables (`_t.ROOT_DIR`, `args.root`, `args.content_dir`) throughout the codebase needed to be replaced to solidify the unified path mechanism.

**Changes Made:**
1. Replaced `_t.ROOT_DIR` with `_t.TARGET_DIR` universally across files like `spec_cli.py`, `core/sync.py`, `core/commands.py`, and `core/config_gen.py`.
2. Cleaned up `args.root` and `args.content_dir` into `args.target_dir` in CLI entry points like `vault_cli.py` and `spec_cli.py`.
3. Updated tests in `tests/cli/test_vault_cli.py` and `tests/cli/test_spec_cli.py` to assert against `target_dir`.
4. Fixed up `tests/test_config.py` by removing validation and fallback testing for the deleted environment variables `VAULTSPEC_ROOT_DIR` and `VAULTSPEC_CONTENT_DIR`, successfully completing test execution.

**Impact:** The entire execution and configuration graph has been successfully decoupled from the overloaded `root` concept. All CLI tasks now act reliably inside their targeted operation envelope (`target_dir`).
