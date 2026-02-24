---
tags:
  - "#exec"
  - "#hooks-maturity"
date: "2026-02-23"
related:
  - "[[2026-02-23-hooks-maturity-plan]]"
  - "[[2026-02-23-hooks-maturity-adr]]"
  - "[[2026-02-23-hooks-maturity-research]]"
---
# hooks-maturity code review

**Status:** `PASS`

## Audit Context

- **Plan:** `[[2026-02-23-hooks-maturity-plan]]`
- **Scope (this review pass — Phase 2 wiring, Phase 3a tests, Phase 3b docs):**
  - `src/vaultspec/vault_cli.py` — lifecycle trigger wiring
  - `src/vaultspec/spec_cli.py` — sync-all trigger wiring
  - `src/vaultspec/hooks/__init__.py` — `fire_hooks` re-export
  - `src/vaultspec/hooks/tests/test_hooks.py` — Phase 3a test suite
  - `README.md` — Hooks section
  - `.vaultspec/docs/hooks-guide.md` — dedicated guide
  - `.vaultspec/docs/cli-reference.md` — expanded hooks section
  - `.vaultspec/docs/concepts.md` — hooks subsection
  - `.vaultspec/rules/hooks/example-audit-on-create.yaml` — improved example

---

## Requirement Verification Checklist

### Phase 2 — Auto-Trigger Wiring

**`vault_cli.py:handle_create` fires `vault.document.created` with context `{path, root, event}` after `create_vault_doc()` succeeds.**

- VERIFIED. `vault_cli.py` lines 181-183: `from .hooks import fire_hooks` is inside the function body, placed after the two `except` blocks that call `sys.exit(1)`. The call is only reached when `create_vault_doc()` returns without raising. Context dict: `{"path": str(doc_path), "root": str(args.root), "event": "vault.document.created"}` — all three required keys are present.

**`vault_cli.py:handle_index` fires `vault.index.updated` with context `{root, event}` after `index()` succeeds.**

- VERIFIED. `vault_cli.py` lines 372-374: import and call are placed after the `try/except` block that calls `sys.exit(1)` on `index()` failure, so the hook is only reachable on success. Context dict: `{"root": str(root_dir), "event": "vault.index.updated"}` — correct keys (no `path` key, consistent with the plan for this event).

**`vault_cli.py:handle_audit` fires `audit.completed` with context `{root, event}` at end of audit.**

- VERIFIED. `vault_cli.py` lines 325-327: `fire_hooks("audit.completed", {"root": str(root_dir), "event": "audit.completed"})` is the last statement in `handle_audit`, placed unconditionally after the final `if args.json:` output block. Both required context keys are present.

**`spec_cli.py` sync-all fires `config.synced` with context `{root, event}` after all syncs complete.**

- VERIFIED. `spec_cli.py` lines 373-377: the import and call are inside the `elif args.resource == "sync-all":` branch, placed after `config_sync(args)` (the final sync call) and before `logger.info("Done.")`. Context: `{"root": str(_t.ROOT_DIR), "event": "config.synced"}` — correct keys.

**All wiring uses lazy imports (inside function body, not at module top).**

- VERIFIED. In `vault_cli.py`, all three `from .hooks import fire_hooks` statements appear inside their respective handler function bodies (lines 181, 325, 372). In `spec_cli.py`, the import appears inside the `elif args.resource == "sync-all":` branch (line 373). No `fire_hooks` import appears at module scope in either file.

---

### Phase 3a — Test Requirements

**`test_failing_command` uses `sys.executable` (not bare `python` or `exit 1`).**

- VERIFIED. `test_hooks.py` lines 263-279: `test_failing_command` writes a `fail.py` script to `tmp_path` with content `"import sys; sys.exit(1)"` and constructs the command string as `f"{sys.executable} {script}"`. No bare `python` string literal and no `exit 1` shell builtin. Writing the script to a file avoids shell quoting issues with inline `-c` arguments on Windows — a correct and robust approach.

**`test_expected_events` expects exactly 4 events (no `vault.document.modified`).**

- VERIFIED. `test_hooks.py` lines 32-39: `TestSupportedEvents.test_expected_events` asserts the expected set is exactly `{"vault.document.created", "vault.index.updated", "config.synced", "audit.completed"}`. The string `vault.document.modified` does not appear anywhere in `test_hooks.py` or anywhere in the `src/vaultspec/` source tree (grep returns zero matches).

**`TestDeduplication` exists with yaml/yml precedence test.**

- VERIFIED. `test_hooks.py` lines 282-309: `TestDeduplication` class is present with two tests. `test_yaml_takes_precedence_over_yml` creates both `hook.yaml` and `hook.yml` in `tmp_path`, calls `load_hooks()`, asserts exactly one hook is loaded and that `hooks[0].source_path.suffix == ".yaml"`. `test_unique_stems_load_all` verifies two files with distinct stems both load. No mocking.

**`TestReentrantGuard` exists with guard and cleanup tests.**

- VERIFIED. `test_hooks.py` lines 312-347: `TestReentrantGuard` class is present with three tests. `test_reentrant_trigger_returns_empty` manually adds the event to the live `_triggering` set (imported from `engine` at line 21), calls `trigger()`, asserts `[]`, cleans up in `finally`. `test_non_reentrant_trigger_works` verifies the guard does not affect a clean state. `test_triggering_set_cleaned_up_after_execution` verifies the `finally` discard path runs after normal execution. All three use real code paths.

**`TestFireHooksIntegration` exists with real side-effect test.**

- VERIFIED. `test_hooks.py` lines 350-390: `TestFireHooksIntegration` is present. `test_shell_hook_side_effect` writes a Python helper script (`create_marker.py`) to a temp path, writes a real YAML hook file referencing it, calls `load_hooks(tmp_path) + trigger()`, and asserts a marker file was created on disk. This is a genuine end-to-end integration test with a real filesystem side-effect. The class docstring explains that `fire_hooks()` is not called directly because it requires workspace initialization — `load_hooks + trigger` exercises the same code path.

**Zero mocking anywhere (no `unittest.mock`, no `monkeypatch.setattr`, no `MagicMock`).**

- VERIFIED. Grep for `unittest.mock`, `MagicMock`, `monkeypatch.setattr`, `@patch`, `from unittest`, `import mock` in `test_hooks.py` returns zero matches. All tests use real subprocesses, real filesystem I/O, and real YAML parsing.

---

### Phase 3b — Documentation Requirements

**`README.md` has hooks section pointing to guide.**

- VERIFIED. `README.md` lines 69-78: `## Hooks` section is present after the existing feature sections. It describes what hooks are, where they live, which events fire them, both action types, use-cases, and includes a direct link to `.vaultspec/docs/hooks-guide.md`.

**`hooks-guide.md` exists.**

- VERIFIED. File exists at `.vaultspec/docs/hooks-guide.md`.

**`hooks-guide.md` covers YAML schema.**

- VERIFIED. `hooks-guide.md` lines 40-53: `## YAML Schema` section with a complete annotated YAML block covering `event`, `enabled`, `type: shell` with `command`, and `type: agent` with `name` and `task`. All fields are commented.

**`hooks-guide.md` covers both action types.**

- VERIFIED. `hooks-guide.md` lines 57-93: separate `## Shell Actions` and `## Agent Actions` sections, each with description, timeout, behavior notes, and a YAML code example.

**`hooks-guide.md` has 4-event table.**

- VERIFIED. `hooks-guide.md` lines 25-32: `## Supported Events` table lists exactly 4 events (`vault.document.created`, `vault.index.updated`, `config.synced`, `audit.completed`) with trigger commands and context variable columns. No 5th event present.

**`hooks-guide.md` covers timeouts (60s shell, 300s agent).**

- VERIFIED. `hooks-guide.md` line 62: "60 seconds" timeout for shell actions. Line 81: "300 seconds" timeout for agent actions. Both match ADR specification.

**`hooks-guide.md` covers error behavior.**

- VERIFIED. `hooks-guide.md` lines 97-115: `## Error Behavior` section enumerates shell failure, agent failure, YAML parse error, and unhandled exception in `fire_hooks()`, each with its log level. States that failures never interrupt the parent command.

**`hooks-guide.md` covers debugging tips.**

- VERIFIED. `hooks-guide.md` line 110 references `--verbose`/`--debug` flags for observing hook output. Lines 117-148: `## Manual Testing` section explains `vaultspec hooks list` and `vaultspec hooks run` with example output and `--path` explanation.

**`cli-reference.md` hooks section expanded with event names and `--path`.**

- VERIFIED. `cli-reference.md` lines 519-574: the `### hooks` section contains a `**Supported events:**` table (all 4 events with trigger commands), `hooks list` with example output, `hooks run` with `--path` example and result output, and a flag table plus prose explanation of `--path` semantics.

**`concepts.md` has hooks subsection.**

- VERIFIED. `concepts.md` lines 365-375: `### Hooks` subsection present in the Core Concepts section. Explains what hooks are, where they live, which events fire them (all 4 named), that failures are transparent, and links to `hooks-guide.md`.

**`example-audit-on-create.yaml` has agent action example.**

- VERIFIED. `example-audit-on-create.yaml` lines 31-35: a commented-out agent action block is present with `type: agent`, `name: vaultspec-docs-curator`, and a `task:` string using `{path}` and `{event}` placeholders.

**`example-audit-on-create.yaml` lists only 4 events.**

- VERIFIED. `example-audit-on-create.yaml` lines 8-13: the comment block explicitly lists exactly 4 events. The string `vault.document.modified` does not appear in the file.

**`example-audit-on-create.yaml` has `enabled: false`.**

- VERIFIED. `example-audit-on-create.yaml` line 25: `enabled: false  # set to true to activate`. Both the correct value and clear activation instructions are present.

---

## Findings

### Critical / High (Must Fix)

None.

### Medium / Low (Recommended)

- **[LOW]** `vault_cli.py:handle_index` (lines 372-374): `fire_hooks` is called before the `if args.json:` stdout output block, meaning the hook fires before the CLI prints its completion message. `handle_audit` fires after its JSON output (line 325 is after line 322). The ordering difference is cosmetic and non-functional — hook failures cannot propagate — but the inconsistency across handlers is worth noting for future maintainability.

- **[LOW]** `test_hooks.py` lines 369-373: `TestFireHooksIntegration.test_shell_hook_side_effect` builds the hook YAML command as `f"    command: python {script}\n"` using the bare string `python`. On Python 3-only environments where the `python3` executable is present but `python` is not, this could fail. `test_failing_command` already demonstrates the correct pattern (`sys.executable`). Replacing `python` with `sys.executable` (already imported at line 5) would make this test more portable.

- **[LOW]** `test_hooks.py` lines 315-326: `TestReentrantGuard.test_reentrant_trigger_returns_empty` directly mutates the live module-level `_triggering` set. This is the correct no-mock approach, but a brief inline comment explaining why direct mutation of `_triggering` is used (rather than any workaround) would improve reader comprehension.

---

## Recommendations

No blocking recommendations. All Phase 2 wiring requirements and all Phase 3 test and documentation requirements are faithfully implemented. The three LOW findings above are optional improvements suitable for a follow-up.

Suggested follow-up actions (non-blocking):

- Standardize `fire_hooks` placement in `handle_index` to occur after all CLI output, consistent with `handle_audit`.
- In `test_shell_hook_side_effect`, replace the bare `python` string with `sys.executable` for cross-platform robustness.
- Add an inline comment to `test_reentrant_trigger_returns_empty` explaining the direct `_triggering` mutation pattern.

## Notes

- `vault.document.modified` is confirmed absent from `SUPPORTED_EVENTS`, from `test_expected_events`, and from the entire `src/vaultspec/` source tree — Task 2b is fully satisfied.
- `fire_hooks` is correctly re-exported from `src/vaultspec/hooks/__init__.py` (line 7) using the explicit `as` form, keeping it visible to type checkers and the public API surface intact.
- The prior review pass verified all Phase 1 engine-hardening requirements (1a–1f) and the Phase 2 `fire_hooks` implementation in `engine.py`. Those findings are confirmed unchanged.
