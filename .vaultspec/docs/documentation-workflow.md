# Documentation Workflow

This guide defines the documentation writing process for vaultspec workspaces.
It separates research, drafting, and editorial review so documentation remains
accurate, auditable, and stable over time.

## Scope

Use this workflow for documentation surfaces such as:

- markdown guides and references
- architecture notes
- command help text and user-facing copy
- explanatory documentation blocks where explanation is the primary purpose

## Required Inputs

Before any writing starts, define all three inputs:

- `topic`
- `audit surface`
- `rewrite scope`

Keep these explicit and narrow enough to bound both discovery and writing.

## Role Separation

The workflow uses two specialist roles followed by editorial review:

- Researcher: gathers context only
- Author: writes from the Researcher brief only
- Editor: performs final editorial review and applies minimal corrections

Do not collapse these roles into a single pass.

## Process

### 1) Bound the task

Set the `topic`, `audit surface`, and `rewrite scope` in explicit terms.

### 2) Researcher pass

The Researcher inspects the bounded surface and returns a context brief with:

- live behavior and surface facts
- terminology constraints
- contradictions or drift
- required references
- file list with evidence anchors

The Researcher does not draft final documentation text.

### 3) Wait for Researcher completion

Do not start drafting until the Researcher brief is complete.

### 4) Author pass

The Author writes from the Researcher brief and cited sources.
The Author should not reopen full discovery unless a critical gap is identified.

### 5) Wait for Author completion

Do not apply or relay unfinished draft text.

### 6) Editor pass

Review the Author output for:

- style and readability
- information density
- terminology consistency
- semantic alignment with the Researcher brief

Treat the Author substance as correct unless there is a clear mismatch with
source evidence.

### 7) Apply minimal corrections

Apply only the minimum editorial changes needed for clarity and consistency.
Do not silently improvise beyond the bounded scope.

## Alignment With Vaultspec Pipeline

This workflow governs documentation authoring discipline. It complements the
broader vaultspec pipeline:

- Research -> Specify -> Plan -> Execute -> Verify

For significant changes, maintain pipeline artifacts in `.vault/` and keep
references consistent with framework rules.

## Documentation Hygiene

- Use existing project terminology from the target surface.
- Prefer exact language and low-ambiguity phrasing.
- Keep internal references coherent with framework structure in `.vaultspec/`
  and durable records in `.vault/`.

## See Also

- [Concepts](./concepts.md)
- [CLI Reference](./cli-reference.md)
- [Framework Manual](../README.md)
