---
date: 2026-03-05
tags:
  - '#reference'
  - '#cli-architecture'
---

# CLI Audit Notes

## Commands with clear mandates

- `sync`
- `install`
- `uninstall`

## Issues found

### install

- `install <path> --dry-run` — dry run is broken
  - Not reporting what already exists
  - Not reporting what would be updated
  - Not reporting what would be overridden
  - Not reporting what would be removed/deleted
- Path error message is deficient when path is wrong
- Path error message is deficient when path is missing
- Provider argument (core|all|providers...) does not mirror sync options
- Unclear if `install <path> gemini` automatically implies core + provider (gemini requires core, without it sync cannot execute)

### sync

- `sync core` must error — core is a no-op since the sync source is .vaultspec itself
- Unclear if only provider foo was installed, would sync respect only that provider
- Unclear where provider installation manifest is persisted in repo
- Folder checks alone are not safe — other tools can create and write provider folders
- Manifest must indicate what tools we're augmenting in this repo, not just what dirs exist

### init

- Looks obsolete — install/uninstall/sync covers the same ground

### readiness

- Command description and actual behavior make no sense for a normal user

### doctor

- Description is confusing — gives no clue what it targets or what it is doctoring

## Proposed CLI structure

Two controlled folders: `.vaultspec` and `.vault`. Mirror CLI so commands group by domain.

### install <path> [provider] [--upgrade] [--dry-run] [--force]

- provider: all (default), core, claude, gemini, antigravity, codex
- `core` = .vaultspec folder only
- Any provider implies core + provider (gemini requires core, without it sync cannot execute)
- `--force` to override contents if already exists
- `--dry-run` must produce verbose visual tree representation (typer+rich coloured output)
  - "would" wording explicitly rejected
  - Must show what exists, what is new, what gets updated, what gets overridden, what gets deleted

### uninstall <path> [provider] [--keep-vault] [--dry-run] [--force]

- provider: all (default), core, claude, gemini, antigravity, codex
- `core` must unroll all providers (uninstalling core means everything goes)
- Must fail by default — requires `--force` to execute

### sync [provider] [--prune] [--dry-run] [--force]

- provider: all (default), claude, gemini, antigravity, codex
- `core` is not a valid target (errors: sync source is .vaultspec itself)
- Must respect installed provider manifest, not folder existence

### vault

- `vault add adr|research|plan` `--feature "feature-tag"` `[--date YYYY-MM-DD]` `[--title]` `[--content]`
  - Creates empty templates
  - `--feature` required
  - `--date` defaults to today
  - `--title`, `--content` support depends on type
- `vault stats` `[--feature]` `[--date]` `[--type]` `[--invalid]` `[--orphaned]`
- `vault list adr|research|audit|plan|invalid|orphaned|exec` `[--date YYYY-MM-DD]` `[--feature TAG]`
- `vault feature list` `[--date]` `[--orphaned]` `[--type adr|research|audit|plan|etc]`
- `vault feature archive "feature-tag"`
- `vault doctor` — autofix issues

### spec

- `spec rules|skills|agents|system list|add|remove|edit|revert`
- CLI suite responsible for authoring and modifying the .vaultspec firmware contents
- `revert` — how would we restore original contents after destructive edits?
- `spec hooks` — hooks nested under spec?

### dev

- Development-specific commands, not user-facing
- `dev test unit`
- `dev test integration`
- `dev test` (all)

## Unclear

- `readiness` — purpose unclear
- `--install-completion` / `--show-completion` — completely perplexing
- Why both `--verbose` and `--debug` exist — keep only `--debug`

## General notes

- User documentation and user-facing descriptions are poor and badly worded
- Often sounds like word salad instead of clearly indicating what a command does and what it changes
- Example: `--target` should say "Select installation destination folder. Use '.' for current working directory."
