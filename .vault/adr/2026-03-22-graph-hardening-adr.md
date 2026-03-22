---
tags:
  - '#adr'
  - '#graph-hardening'
date: '2026-03-22'
related:
  - '[[2026-03-22-graph-hardening-research]]'
---

# `graph-hardening` adr: phantom nodes and dangling-link resolution | (**status:** `accepted`)

## Problem Statement

The vault graph silently drops 151 edges to non-existent targets. No checker
reports dangling wiki-links. Obsidian shows them as "not created" nodes -
the CLI shows `links: clean`. A healthy vault must have **zero dangling
links** - every `[[wiki-link]]` must resolve to a real document.

## Considerations

- Obsidian treats unresolved links as first-class graph nodes, styled
  distinctly and offering to create the file on click.
- The graph already tracks broken pairs in `_invalid_links` and exposes
  them via `get_invalid_links()` and `GraphMetrics.invalid_link_count`,
  but no checker or pre-commit hook consumes them.
- `check_schema` and `check_references` silently skip unresolved targets
  because `graph.nodes.get()` returns `None` - correct but invisible.
- Pre-commit hooks need a simple numeric gate: "N dangling links found,
  refusing commit."

## Constraints

- Must not break existing snapshot-based checkers (structure, frontmatter,
  features, links) which operate on real files only.
- Must preserve backward compatibility of `GraphMetrics` fields.
- Phantom nodes must be clearly distinguishable from real nodes everywhere
  they appear (graph, tree, JSON, metrics).

## Decisions

**Decision 1 - Phantom nodes as first-class graph citizens.**
Unresolved wiki-link targets become lightweight `DocNode` instances with
`phantom=True`. Real DiGraph edges connect source to phantom. This mirrors
Obsidian's model: the graph shows intended structure, not just what exists
on disk.

**Decision 2 - New `check_dangling` checker at ERROR severity.**
A healthy vault is fully resolved - zero dangling links. Dangling references
are ERROR, not WARNING. The checker reports each broken `(source, target)`
pair. Supports `--fix` to remove the dead link from `related:` frontmatter.

**Decision 3 - `GraphMetrics.invalid_link_count` remains the authoritative
counter.**
This field is the single source of truth for how many dangling links exist.
Pre-commit hooks and linters gate on this number: if `invalid_link_count > 0`,
refuse the commit with a message like "N dangling links found". The counter
is derived from phantom node count but lives on `GraphMetrics` for direct
access without graph traversal. It must be cheap to compute and unambiguous
in meaning.

**Decision 4 - Phantom-aware guards on existing checkers.**
After phantom nodes enter `self.nodes`, checkers that do
`graph.nodes.get(target)` will find them. `check_schema`,
`check_references`, and `check_orphans` must filter on `node.phantom`
to avoid treating phantoms as real documents.

**Decision 5 - Distinct rendering for phantom nodes.**
Tree renderer: phantom nodes styled distinctly with `(not created)` label.
JSON export: `phantom: true` flag on node dict. Metrics: `phantom_count`
field in `GraphMetrics` alongside `invalid_link_count`.

**Decision 6 - `to_snapshot()` excludes phantoms.**
Snapshot-based checkers (structure, frontmatter, features, links) operate
on real files only. Phantoms have no path and no content to lint.

## Implementation

- Add `phantom: bool = False` field to `DocNode`.
- In `_build_graph()` pass 2, create phantom `DocNode` for each unresolved
  target. Add real DiGraph edges to phantom nodes.
- `to_nx_attrs()` includes `phantom` flag.
- `GraphMetrics` gains `phantom_count` field. `invalid_link_count` is
  derived as the count of edges whose target is a phantom node - remains
  the gating value for pre-commit hooks and linters.
- Guard `get_orphaned()`, `to_snapshot()` to exclude phantoms.
- Guard `check_schema`, `check_references` to skip phantom targets.
- Add `check_dangling` checker: ERROR severity, uses
  `graph.get_invalid_links()`, supports `--fix`.
- Wire `check_dangling` into `run_all_checks()` and CLI `check` subgroup.
- Update tree renderer and JSON serialization for phantom styling.
- Tests covering phantom node creation, edge existence, rendering,
  metrics accuracy, checker guards, and pre-commit hook gating.

## Rationale

- Mirrors Obsidian - the tool users already rely on for vault visualization.
- A single `phantom` flag on `DocNode` is the minimal change that makes
  phantom nodes distinguishable everywhere.
- ERROR severity enforces the user's requirement: a healthy vault is fully
  resolved with zero dangling links.
- Keeping `invalid_link_count` as the authoritative counter ensures
  pre-commit hooks have a simple, reliable gate without needing to traverse
  the graph or understand phantom node internals.

## Consequences

- `check all` output gains a new `dangling` section. Total error count
  will increase for vaults with broken links.
- Pre-commit hooks can gate on `invalid_link_count > 0` with a clear
  error message reporting the exact count.
- Existing tests that assert `len(graph.nodes) == file_count` must account
  for phantom nodes (filter on `not node.phantom`).
- `_invalid_links` list continues to be populated during build for the
  checker, but phantom nodes are the canonical graph representation.
