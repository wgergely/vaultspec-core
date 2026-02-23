"""Vaultspec: spec-driven development framework for agentic workflows.

Vaultspec governs AI-assisted development through documented, auditable
pipelines.  It manages rules, agents, skills, and tool configs across
Claude, Gemini, and other AI tooling, and provides orchestration primitives
for multi-agent teams via the A2A and ACP protocols.

Architecture:
    core/          Resource management (rules, agents, skills, config, system).
    orchestration/ Sub-agent dispatch, team coordination, and task engines.
    protocol/      A2A and ACP protocol bridges and executors.
    mcp_server/    MCP tool server exposing vaultspec capabilities.
    vaultcore/     .vault/ document parsing and template expansion.
    verification/  Structural and integrity checks for .vault/ documents.
    graph/         Wiki-link graph analysis for .vault/ documents.

CLI entry points (invoked via ``vaultspec <command>``)::

    vault     -- .vault/ document management
    team      -- multi-agent team lifecycle
    subagent  -- sub-agent dispatch and A2A serving
    mcp       -- MCP tool server
    rules     -- rule management
    agents    -- agent management
    skills    -- skill management
    config    -- tool config management
    system    -- system prompt management
"""

from .printer import Printer

__all__ = ["Printer"]
