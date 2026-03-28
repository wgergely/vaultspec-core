---
tags:
  - '#research'
  - '#mcp-installation'
date: '2026-03-28'
related:
  - '[[2026-02-22-mcp-consolidation-research]]'
  - '[[2026-02-22-mcp-testing-research]]'
---

# `mcp-installation` research: industry patterns for MCP server registration

Researched how MCP servers across the ecosystem handle their own
installation and registration into client configuration files
(`.mcp.json`, `claude_desktop_config.json`, etc.). Goal: determine whether
vaultspec-core's approach of auto-writing `.mcp.json` during `init` is
unusual, standard, or somewhere in between.

## Findings

### 1. The dominant pattern is manual copy-paste

The overwhelming majority of MCP servers - including all Anthropic reference
servers (filesystem, postgres, puppeteer, brave-search, github, google-maps)
and popular community servers (context7, sequential-thinking) - instruct
users to manually copy a JSON snippet into their client's configuration file.

The typical installation flow is:

- Server README provides a JSON block with the `mcpServers` entry
- User opens their config file (`claude_desktop_config.json`,
  `.cursor/mcp.json`, `.vscode/mcp.json`, etc.)
- User pastes the snippet, adjusts paths/credentials, saves
- User restarts the client application

No reference server auto-writes configuration during `npm install` or
`pip install`. Package managers install the server binary; registration is
a separate, user-driven step.

### 2. CLI-assisted registration exists but is always user-initiated

Several tools provide CLI commands that write config on the user's behalf,
but all require explicit invocation - none run automatically as post-install
hooks:

- **Claude Code CLI**: `claude mcp add <name> -- <command>` writes to the
  Claude Code configuration. This is the closest thing to an official
  registration command. It is always user-initiated.

- **FastMCP**: `fastmcp install <server.py>` generates configuration and
  can write it into `claude_desktop_config.json`. User-initiated, not
  triggered by `pip install fastmcp`.

- **add-mcp** (by Neon): `npx add-mcp <url>` detects installed coding
  agents and writes configuration to each one. Explicitly opt-in; the user
  runs the command.

- **Codex CLI**: `codex mcp add context7 -- npx -y @upstash/context7-mcp`
  registers a server. User-initiated.

- **Junie CLI** (JetBrains): Interactive `mcp add` that searches the
  official MCP Registry, prompts for secrets, writes config. User-initiated.

- **@mcpmarket/mcp-auto-install**: npm package for bulk server setup from
  a JSON manifest. User-initiated.

### 3. The MCP specification does not define a registration mechanism

The core MCP specification (2025-11-25 revision, now governed by the Agentic
AI Foundation under the Linux Foundation) defines the wire protocol between
clients and servers but is deliberately silent on how servers get registered
with clients. Key points:

- **No standard registration command** exists in the spec.
- **No post-install hook convention** is defined.
- **Server discovery** is handled by a separate system - the MCP Registry
  (backed by Anthropic, GitHub, Microsoft) and proposed `.well-known/mcp`
  endpoints (SEP-1649, SEP-1960) - but these are for remote/HTTP servers
  and catalog browsing, not local stdio server auto-registration.
- The spec treats registration as a client concern, not a server concern.

### 4. No MCP server auto-writes config during package installation

Across the surveyed ecosystem, zero MCP servers modify `.mcp.json` or
`claude_desktop_config.json` as a side effect of `pip install` or
`npm install`. The reasons are both practical and security-driven:

- **Config file locations vary by client** (Claude Desktop, Cursor, VS Code,
  Codex, Gemini CLI all use different paths and formats).
- **Post-install hooks in npm/pip are a known supply chain attack vector**.
  The MCP security landscape already includes high-profile incidents
  (CVE-2025-6514 in mcp-remote, configuration poisoning via
  `.claude/settings.json` reverse shells, Supabase Cursor agent compromise).
- **User consent is expected** before granting an AI tool access to system
  resources. Auto-registration bypasses that consent boundary.

### 5. Emerging pattern: project-scoped `.mcp.json` written by scaffolding tools

A newer pattern is emerging where project scaffolding or initialization
commands (not package install) write a project-local `.mcp.json`:

- **vaultspec-core** (`vaultspec init`): writes `.mcp.json` with the
  `vaultspec-core` server entry during workspace initialization. This is
  the pattern under evaluation.
- **FastMCP**: `fastmcp install` can target project-level config.
- **add-mcp**: supports both global and project-level installation.

The key distinction is that these are explicit initialization commands, not
silent post-install side effects. The user runs `init` or `install`
knowing it will scaffold project files.

### 6. Security risks of auto-writing `.mcp.json`

Research into MCP security (2025-2026) reveals significant concerns:

- **Configuration poisoning**: Check Point Research (Feb 2026) demonstrated
  that project-scoped config files can execute with real consequences before
  trust dialogs render. Malicious `.claude/settings.json` files were shown
  to spawn reverse shells.
- **Supply chain attacks**: 43% of analyzed MCP servers are vulnerable to
  command injection. A compromised package auto-writing config could inject
  a malicious server entry.
- **Consent boundary violation**: Writing to `.mcp.json` without explicit
  user action grants tool access that the user did not consciously approve.
- **Config corruption risk**: Merging into an existing `.mcp.json` can
  corrupt user entries if the merge logic has bugs.

### 7. Classification of vaultspec-core's approach

vaultspec-core's `_scaffold_mcp_json()` in `core/commands.py`:

- Writes `.mcp.json` during `vaultspec init` (explicit user command)
- Merges into existing `.mcp.json` preserving other entries
- Provides surgical cleanup during `vaultspec uninstall`
- Is NOT a post-install hook - it requires the user to run `init`

This places vaultspec-core in the "scaffolding tool" category alongside
FastMCP's install command and add-mcp. It is more aggressive than the
manual copy-paste pattern but less dangerous than a post-install hook.

## Summary matrix

| Approach                    | Examples                                 | User consent            | Risk level   |
| --------------------------- | ---------------------------------------- | ----------------------- | ------------ |
| Manual copy-paste from docs | All reference servers, context7          | Explicit                | Lowest       |
| User-initiated CLI command  | `claude mcp add`, `codex mcp add`        | Explicit                | Low          |
| User-initiated scaffolding  | vaultspec-core `init`, `fastmcp install` | Implicit (part of init) | Low-moderate |
| Post-install hook           | None found in ecosystem                  | None                    | High         |
| Silent background write     | None found in ecosystem                  | None                    | Highest      |

## Conclusions

- vaultspec-core's approach is **uncommon but not unprecedented**. It sits
  in a small category of scaffolding tools that write `.mcp.json` as part
  of an explicit initialization command.
- The approach is **defensible** because `init` is a deliberate user action
  with clear expectations of file creation. It is not a hidden side effect.
- The main risk is **config corruption during merge** and
  **user surprise** if they do not expect `.mcp.json` to be modified.
- A **--skip mcp** flag (already implemented on this branch) is the
  industry-aligned mitigation - it gives users an opt-out.
- No MCP server in the ecosystem auto-registers via package install hooks.
  vaultspec-core should not adopt that pattern.
