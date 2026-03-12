# Vault Query Guide

`vaultspec-mcp` exposes `query_vault(...)` as the live retrieval surface for
vault documents.

Use it from an MCP client when you need to find vault records by content,
feature, type, relationships, or recency.

## What `query_vault` Supports

- `query`: case-insensitive substring matching over vault file content
- `feature`: filter by vault feature tag
- `type`: filter by vault document type tag
- `related_to`: follow `related:` frontmatter links
- `recent`: return recent documents grouped one per feature by `date`
- `limit`: cap the number of returned documents

## Examples

Find documents whose content includes a phrase:

```python
query_vault(query="searchable content")
```

Filter by feature and document type:

```python
query_vault(feature="my-feat", type="adr")
```

Find documents related to a specific vault artifact:

```python
query_vault(related_to=".vault/adr/2026-03-06-target-adr.md")
```

Get a recent cross-feature view:

```python
query_vault(recent=True, limit=10)
```

## Behavior Notes

- `query` matches content using case-insensitive substring search.
- `feature` and `type` use vault tags to narrow results.
- `related_to` returns documents linked through `related:` frontmatter.
- `recent=True` returns recent documents grouped one per feature by `date`.

## Scope

This guide documents the live MCP retrieval surface.

There is no shipped CLI `search` or `index` command in the current product
surface.

See also:

- [CLI Reference](./cli-reference.md)
