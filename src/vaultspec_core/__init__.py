"""Runtime library for vaultspec-managed workspaces.

Provides the full stack from workspace resolution and resource sync through
vault document modelling, health checks, graph analysis, metrics, hook
execution, MCP server, and the user-facing CLI.

Subpackages:
    :mod:`vaultspec_core.config`: Runtime settings and workspace-layout
        resolution (:class:`~vaultspec_core.config.VaultSpecConfig`,
        :func:`~vaultspec_core.config.resolve_workspace`).
    :mod:`vaultspec_core.core`: Resource-management and sync engine  -
        agents, rules, skills, system, exceptions, dry-run, and I/O helpers.
    :mod:`vaultspec_core.vaultcore`: ``.vault/`` document kernel  - domain
        models, frontmatter parsing, wiki-link extraction, and query helpers.
    :mod:`vaultspec_core.builtins`: Bundled canonical resources seeded on
        ``vaultspec-core install``.
    :mod:`vaultspec_core.cli`: Typer CLI  - ``install``, ``uninstall``,
        ``sync``, ``vault``, and ``spec`` command groups.
    :mod:`vaultspec_core.graph`: Vault document relationship graph backed by
        ``networkx`` (:class:`~vaultspec_core.graph.VaultGraph`).
    :mod:`vaultspec_core.hooks`: Declarative lifecycle hook runtime for
        vault/spec-core events.
    :mod:`vaultspec_core.metrics`: Lightweight aggregate statistics over
        ``.vault/`` content (:class:`~vaultspec_core.metrics.VaultSummary`).
    :mod:`vaultspec_core.mcp_server`: FastMCP server exposing vault and
        spec-core tool surfaces over JSON-RPC/stdio.
    :mod:`vaultspec_core.protocol`: Model-provider abstraction for prompt
        execution (Claude, Gemini).
"""
