---
tags:
  - '#research'
  - '#graph-hardening'
date: '2026-03-22'
related:
---

# `graph-hardening` research: phantom nodes and broken-link visibility

The vault graph tracks 151 invalid (dangling) links internally but no checker
surfaces them. Obsidian highlights unresolved links as "not created" - the CLI
should match that behavior. This research grounds the problem, traces the code
paths, and identifies the gaps.

## Findings

### Problem statement

The document `2026-02-21-claude-a2a-overhaul-impl-plan` has six `related:`
entries. Three targets do not exist as files:

- `2026-02-22-claude-team-management-reference`
- `2026-02-22-claude-team-management-adr`
- `2026-02-22-claude-team-management-plan`

Obsidian renders these as "not created" links. The CLI reports
`links: clean` and no checker flags them.

### How the graph handles unresolved targets today

In `VaultGraph._build_graph()` pass 2 (api.py:350-380):

- For each document, wiki-links and `related:` entries are extracted.
- Each target is resolved via `_resolve_link()`. When no node key matches,
  the raw target string is returned.
- The target string lands in `node.out_links` regardless of whether the
  target exists as a real node.
- If the target is **not** in `self.nodes`, it is appended to
  `self._invalid_links` and **no edge** is added to the networkx DiGraph.

Consequences:

- `_invalid_links` contains 151 broken pairs in the live vault.
- `GraphMetrics.invalid_link_count` correctly reports 151.
- `get_invalid_links()` returns the list.
- **No checker ever calls `get_invalid_links()`**.
- The `links` checker (`checks/links.py`) only validates `.md` extension
  convention - it does not check target resolution.
- `check_schema` correctly ignores broken targets when computing
  `linked_types` (it does `graph.nodes.get(target_name)` which returns
  `None` for phantoms).

### The Obsidian model

Obsidian treats unresolved wiki-links as first-class graph citizens:

- They appear in the graph view as nodes (typically grayed out or
  differently styled).
- They are visually distinct from resolved nodes.
- Clicking them offers to create the file.

This model is valuable because:

- The graph shows the *intended* structure, not just what exists.
- Broken links are immediately visible without running a separate check.
- It naturally surfaces documents that were planned but never created.

### Gap 1: No broken-link checker

The check suite has seven checkers. None reports dangling wiki-links
(targets that don't resolve to existing vault documents). The `links`
checker is purely syntactic (`.md` extension).

A `check_dangling` (or extending `check_links`) should:

- Use `graph.get_invalid_links()` to enumerate broken pairs.
- Report each as a WARNING-level diagnostic with the source document and
  the unresolved target.
- Support `--fix` to either remove the broken link or offer `vault add`.
- Severity: WARNING (not ERROR) - broken links degrade quality but don't
  block the pipeline.

### Gap 2: Graph does not represent phantom nodes

The graph silently drops edges to non-existent targets. This means:

- The tree renderer can only show `(broken)` for targets in `out_links`
  that aren't in `self.nodes` - and it does, but only cosmetically.
- The networkx DiGraph has no edges to phantom targets, so graph algorithms
  (centrality, components, density) ignore the intended structure.
- JSON export omits phantom nodes entirely.

Mirroring Obsidian requires creating lightweight "phantom" nodes:

- `DocNode` gains a `phantom: bool = False` field.
- During pass 2, when a target is unresolved, a phantom `DocNode` is
  created with minimal data (name, `phantom=True`, no path, no body).
- Edges to phantom nodes are real DiGraph edges.
- `to_nx_attrs()` includes the `phantom` flag.
- Phantom nodes appear in the tree (styled distinctly), in JSON output,
  and in metrics.
- `get_orphaned()` must exclude phantom nodes.
- `metrics()` should separately count phantom vs real nodes.
- `to_snapshot()` must exclude phantom nodes (they have no file to lint).

### Gap 3: `out_links` conflation

Today, `node.out_links` contains both resolved and unresolved targets
mixed together. Downstream consumers (check_schema, check_references)
must `graph.nodes.get()` each target to tell them apart. This works but
is fragile - if phantom nodes are added to `self.nodes`, those consumers
will treat phantoms as real.

Options:

- **Option A**: Keep `out_links` as-is, add `phantom` flag to DocNode.
  Consumers check `node.phantom` to distinguish.
- **Option B**: Split into `out_links` (resolved) and
  `out_links_broken` (unresolved). Explicit separation.
- **Recommended**: Option A - matches Obsidian's unified model. Phantom
  nodes are real graph citizens, just not backed by files.

### Impact on existing checkers

- `check_schema`: Currently correct - `graph.nodes.get()` returns phantom
  nodes after the change, but checking `target.phantom` or `target.path`
  will distinguish. Must be updated to skip phantoms.
- `check_references`: Same pattern - must skip phantom nodes when checking
  if research is referenced.
- `check_orphans`: Must exclude phantom nodes (no file = not orphaned).
- `check_features`: Works from snapshot, not graph - unaffected.
- `check_frontmatter`: Works from snapshot - unaffected.
- `check_links`: Syntactic only - unaffected.
- `check_structure`: Works from snapshot - unaffected.

### Proposed implementation order

- Add `phantom` field to `DocNode`
- Create phantom nodes in `_build_graph()` pass 2 for unresolved targets
- Add real DiGraph edges to phantoms
- Update tree renderer to style phantom nodes distinctly
- Update JSON serialization to include phantom flag
- Update `metrics()` with phantom count
- Guard `get_orphaned()`, `to_snapshot()`, `check_schema`,
  `check_references` against phantoms
- Add `check_dangling` checker (or extend `check_links`)
- Wire new checker into `run_all_checks()` and CLI
- Tests for all of the above
