---
# ALLOWED TAGS - DO NOT REMOVE
# REFERENCE: #adr #audit #exec #plan #reference #research #builtins-build-strategy
# Directory tag (hardcoded - DO NOT CHANGE - based on .vault/adr/ location)
# Feature tag (replace builtins-build-strategy with your feature name, e.g., #editor-demo)
tags:
  - '#adr'
  - '#builtins-build-strategy'
# ISO date format (e.g., 2026-02-06)
date: '2026-03-21'
# Related documents as quoted wiki-links
# (e.g., "[[2026-02-04-feature-research]]")
related:
  - '[[2026-02-21-packaging-restructure-research]]'
  - '[[2026-02-21-packaging-restructure-adr]]'
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `builtins-build-strategy` adr: `builtins-build-strategy` | (**status:** `{accepted|rejected|deprecated}`)

______________________________________________________________________

tags:

- "#adr"

- "#builtins"

- "#packaging"
  date: "2026-03-21"
  related:

- "\[[2026-02-21-packaging-restructure-adr]\]"

______________________________________________________________________

## `builtins-build-strategy` adr: `wheel force-include for builtin content` | (**status:** `accepted`)

## Decision Problem Statement

The `src/vaultspec_core/builtins/` package directory ships builtin rules, agents, skills, system prompts, templates, and hooks that are seeded into target projects during `vaultspec-core install`. The canonical source of this content lives in `.vaultspec/rules/` at the repository root. Duplicating files in both locations creates drift risk, and committing generated content to the builtins directory pollutes the source tree.

## Decision Considerations

- **Single source of truth**: `.vaultspec/rules/` is the canonical location for builtin content. The framework itself runs against these files during development. Duplicating them into `src/` means two copies that can diverge.
- **Editable installs**: `_builtins_root()` already handles editable installs by walking up to the repo root and resolving `.vaultspec/rules/` directly. No content needs to exist in `src/vaultspec_core/builtins/` during development.
- **Wheel builds**: Installed (non-editable) builds probe for a `templates/` subdirectory alongside `__init__.py`. Without content in the package directory, the probe fails and the fallback cannot find a repo root. Wheel builds must ship content.
- **Hatch build hooks vs force-include**: A custom `hatch_build.py` hook adds a file to the repo root and a class that duplicates what hatchling already supports natively. The `[tool.hatch.build.targets.wheel.force-include]` directive maps arbitrary paths into the wheel at build time with zero custom code.

## Decision Implementation

1. Add `force-include` to `pyproject.toml`:

   ```toml
   [tool.hatch.build.targets.wheel.force-include]
   ".vaultspec/rules" = "vaultspec_core/builtins"
   ```

   This copies the entire `.vaultspec/rules/` tree into `vaultspec_core/builtins/` inside the wheel. The existing `__init__.py` is preserved because hatchling merges force-included content with the package source.

1. `.gitignore` excludes generated content:

   ```gitignore
   src/vaultspec_core/builtins/*
   !src/vaultspec_core/builtins/__init__.py
   ```

   Only `__init__.py` is committed. All other content in the directory is a build artifact.

1. No changes to `_builtins_root()`. The existing dual-path logic is correct:

   - Wheel builds find `templates/` in the package directory and return it.
   - Editable installs fall through to `.vaultspec/rules/` at the repo root.

1. No changes to runtime sync. All sync operations read from `TARGET_DIR/.vaultspec/rules/<category>/`, never from the installed package. The builtins module is only consulted during `install` and `install --upgrade`.

## Decision Rationale

- **Zero custom build code.** `force-include` is a declarative, one-line configuration. No `hatch_build.py`, no shell scripts, no Makefile targets.
- **No source tree pollution.** Generated content is gitignored. The builtins directory in source contains only `__init__.py`.
- **Precedence is simple.** Builtins are a seed bank for `install`. After seeding, the project's `.vaultspec/rules/` is the operative source. `install --upgrade` re-seeds with `force=True`. No runtime override logic.
- **Verified.** `uv build --wheel` produces a wheel containing all expected content (agents, hooks, rules, skills, system, templates) under `vaultspec_core/builtins/`.

## Decision Consequences

**Positive**:

- Single source of truth for builtin content (`.vaultspec/rules/`).
- Clean source tree with no duplicated or generated files committed.
- Standard hatchling feature, no custom build infrastructure.

**Negative**:

- Developers must run `uv build` to produce a wheel with content. Editable installs bypass the builtins directory entirely, which is the intended behavior but could confuse someone inspecting the package directory.
