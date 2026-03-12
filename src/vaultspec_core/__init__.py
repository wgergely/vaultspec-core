"""vaultspec_core packages the vaultspec runtime, vault model, and user-facing
surfaces.

The package is organized around a few stable layers: `config` resolves runtime
settings and workspace layout, `core` manages synced framework resources and
bootstrap state, and `vaultcore` implements the `.vault/` document kernel.
Higher layers such as `graph`, `verification`, `metrics`, `mcp_server`,
`protocol`, `hooks`, and the CLI modules build on those foundations.
"""
