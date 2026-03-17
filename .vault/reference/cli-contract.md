# vaultspec-core CLI Binding Contract

Date: 2026-03-16

This document defines the authoritative CLI surface for `vaultspec-core`. The Python CLI must conform to this contract. The justfile mirrors the Python CLI surface where applicable but extends beyond it to cover development environment concerns (linting, building, publishing, dependency management).

## Controlled domains

Two directories are managed:

- `.vaultspec/` — framework firmware (rules, skills, agents, system prompts, hooks, templates)
- `.vault/` — project documentation records (ADRs, research, plans, audits, references, exec)

## Global options

```
vaultspec-core [--target PATH] [--debug]
```

- `--target` — Select installation destination folder. Use "." for current working directory.
- `--debug` — Enable debug logging. (No separate `--verbose`.)

## Top-level commands

### install \<path\> [provider] [--upgrade] [--dry-run] [--force]

Providers: `all` (default), `core`, `claude`, `gemini`, `antigravity`, `codex`

- `core` = `.vaultspec/` folder only, no provider output directories.
- Any named provider implies `core` + that provider. A provider cannot function without core.
- `--force` — Override contents if installation already exists.
- `--upgrade` — Re-sync builtin firmware without re-scaffolding.
- `--dry-run` — Produce a verbose, coloured visual tree (typer+rich) showing:
  - What already exists
  - What is new
  - What gets updated
  - What gets overridden
  - What gets deleted
  - "Would" wording explicitly rejected.
- Path error messages must be clear when path is wrong or missing.

### uninstall \<path\> [provider] [--keep-vault] [--dry-run] [--force]

Providers: `all` (default), `core`, `claude`, `gemini`, `antigravity`, `codex`

- `core` unrolls all providers — uninstalling core means everything goes.
- Must fail by default. Requires `--force` to execute.
- `--keep-vault` — Preserve `.vault/` documentation directory.
- `--dry-run` — Same visual tree standard as install.

### sync [provider] [--prune] [--dry-run] [--force]

Providers: `all` (default), `claude`, `gemini`, `antigravity`, `codex`

- `core` is not a valid sync target. Must error — sync source is `.vaultspec/` itself.
- Must respect the installed provider manifest, not folder existence.
- Folder checks alone are not safe — other tools can create provider folders independently.
- The manifest indicates what tools we are augmenting in this repo.

## Domain command groups

### vault

Manages `.vault/` documentation records.

```
vault add adr|research|plan --feature "feature-tag" [--date YYYY-MM-DD] [--title TITLE] [--content CONTENT]
```
- Creates empty templates.
- `--feature` is required.
- `--date` defaults to today.
- `--title`, `--content` support depends on document type.

```
vault stats [--feature TAG] [--date YYYY-MM-DD] [--type TYPE] [--invalid] [--orphaned]
```
- Vault statistics and metadata: document counts per tag, per feature, per type.

```
vault list adr|research|audit|plan|invalid|orphaned|exec [--date YYYY-MM-DD] [--feature TAG]
```

```
vault feature list [--date YYYY-MM-DD] [--orphaned] [--type adr|research|audit|plan|etc]
vault feature archive "feature-tag"
```

```
vault doctor
```
- Autofix vault issues.

### spec

Manages `.vaultspec/` firmware contents.

```
spec rules list|add|remove|edit|revert
spec skills list|add|remove|edit|revert
spec agents list|add|remove|edit|revert
spec system list|add|remove|edit|revert
```

- `revert` — Restore original contents after destructive edits. Mechanism TBD.
- `spec hooks` — Hooks management nested under spec. Disposition TBD.

### dev

Development-specific commands. Not user-facing.

```
dev test [unit|integration|all]
```

## Open questions

- `readiness` — Purpose unclear. Disposition TBD.
- `--install-completion` / `--show-completion` — Disposition TBD.
- `revert` mechanism — How to restore original firmware contents after destructive edits.
- `spec hooks` — Confirmed nesting under spec?
- Provider installation manifest — Persistence location and format TBD.

## Justfile scope

The justfile mirrors the Python CLI for `install`, `uninstall`, and `sync`. Beyond that, the justfile owns development-environment recipes that are outside the Python CLI's domain:

- `just sync dependencies|dependency-upgrades` (uv)
- `just lock dependencies|dependency-upgrades` (uv)
- `just fix lint|markdown|vault`
- `just check all|lint|type|dependencies|links|toml|markdown|workflow|vault`
- `just test python|docker|all`
- `just build python|docker|all`
- `just publish docker-ghcr <tag>`

## Quality standards

- All user-facing descriptions must clearly state what the command does and what it changes. No word salad.
- Rich/typer coloured output for terminals that support it.
- Error messages must be specific and actionable.
