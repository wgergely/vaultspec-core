---
tags:
  - "#research"
  - "#install-cmds"
  - "#provider-grounding"
  - "#gemini"
date: "2026-03-15"
related:
  - "[[2026-03-15-install-cmds-plan]]"
  - "[[2026-03-15-claude-code-provider-research]]"
---

# Gemini CLI provider grounding research

User-approved grounding research for Gemini CLI (Google) provider
configuration. All findings verified against official documentation at
geminicli.com on 2026-03-15.

## Root config file

- **Filename:** `GEMINI.md` (customizable via `context.fileName` in settings.json)
- **Project-level:** `GEMINI.md` at project root, discovered via upward traversal from cwd to `.git` boundary
- **User-level:** `~/.gemini/GEMINI.md`
- **System-level:** OS-specific (`/etc/gemini-cli/`, `/Library/Application Support/GeminiCli/`, `C:\ProgramData\gemini-cli\`)
- **JIT loading:** When tools access a directory, scans for `GEMINI.md` up ancestors to trusted root
- **Concatenation:** All discovered files are concatenated, NOT override-based
- **Custom filenames:** `context.fileName` accepts array: `["AGENTS.md", "CONTEXT.md", "GEMINI.md"]`
- **IMPORTANT:** Does NOT look inside `.gemini/GEMINI.md` — only `~/.gemini/GEMINI.md` (user global) and project root traversal
- **Source:** https://geminicli.com/docs/cli/gemini-md/, https://geminicli.com/docs/reference/configuration/

## Rules / Policies

- **No `.gemini/rules/` directory** in official docs
- Rules/policies use `.gemini/policies/*.toml` (TOML format, not markdown)
- Policy engine controls tool execution (allow/deny/ask_user) with priority-based rule matching
- **Project-level:** `.gemini/policies/*.toml`
- **User-level:** `~/.gemini/policies/*.toml`
- **Admin-level:** OS-specific (`/etc/gemini-cli/policies`, `/Library/Application Support/GeminiCli/policies`, `C:\ProgramData\gemini-cli\policies`)
- **This is fundamentally different from Claude's markdown rules** — these are security/execution policies, not behavioral instructions
- **Source:** https://geminicli.com/docs/reference/policy-engine/

## Skills

- **Workspace:** `.gemini/skills/<name>/SKILL.md` OR `.agents/skills/<name>/SKILL.md` (alias)
- **User:** `~/.gemini/skills/<name>/SKILL.md` OR `~/.agents/skills/<name>/SKILL.md` (alias)
- **Extension:** Bundled with installed extensions
- **Precedence:** Workspace > User > Extension. Within same tier, `.agents/skills/` takes precedence over `.gemini/skills/`
- **Format:** `SKILL.md` with YAML frontmatter (`name`, `description`), optional `scripts/`, `references/`, `assets/`
- **Activation:** Agent autonomously decides via `activate_skill` tool based on description match; user gets confirmation prompt
- **Source:** https://geminicli.com/docs/cli/skills/, https://geminicli.com/docs/cli/creating-skills/

## Agents (subagents)

- **Project-level:** `.gemini/agents/*.md`
- **User-level:** `~/.gemini/agents/*.md`
- **Format:** Markdown with YAML frontmatter (`name`, `description`, `kind`, `tools`, `model`, `temperature`, `max_turns`, `timeout_mins`)
- **Body = system prompt** for the subagent
- **Built-in:** codebase_investigator, cli_help, generalist_agent, browser_agent (experimental)
- **Experimental:** Requires `experimental.enableAgents: true` in settings
- **Subagents cannot spawn other subagents**
- **Source:** https://geminicli.com/docs/core/subagents/

## System prompt

- **File:** `.gemini/system.md` (project-level)
- **Env var:** `GEMINI_SYSTEM_MD` pointing to a file path
- Both mechanisms confirmed in configuration reference
- **Source:** https://geminicli.com/docs/reference/configuration/

## Hooks

- **Location:** `hooks` object in `.gemini/settings.json` (project) or `~/.gemini/settings.json` (user)
- **Events:** BeforeTool, AfterTool, BeforeAgent, AfterAgent, BeforeModel, BeforeToolSelection, AfterModel, SessionStart, SessionEnd, Notification, PreCompress
- **Type:** `command` only (shell commands)
- **Matchers:** Regex for tool hooks, exact string for lifecycle hooks
- **I/O:** JSON via stdin/stdout
- **Enabled by default** since v0.26.0+
- **Source:** https://geminicli.com/docs/hooks/reference/

## .agents/ relationship

- `.agents/skills/` is an **alias** for `.gemini/skills/` — takes precedence within same tier
- `.agents/` is NOT a replacement for `.gemini/` — they coexist
- No `.agents/agents/` or `.agents/rules/` documented for Gemini CLI itself
- The alias exists for cross-tool compatibility

## Other .gemini/ contents

- `.gemini/settings.json` — project settings (highest precedence among settings files)
- `.gemini/extensions/` — CLI extensions
- `.gemini/.env` — project-specific environment variables
- `.gemini/sandbox-macos-*.sb` — custom Seatbelt sandbox profiles
- `.gemini/sandbox.Dockerfile` — custom Docker sandbox config
- `.gemini/tmp/` — session history and shell command history

## Capability matrix

| Capability | Supported | Notes |
|-----------|-----------|-------|
| RULES | No (policies are TOML, not markdown rules) | `.gemini/policies/*.toml` |
| SKILLS | Yes | `.gemini/skills/` or `.agents/skills/` alias |
| AGENTS | Yes (experimental) | `.gemini/agents/*.md` |
| ROOT_CONFIG | Yes | `GEMINI.md` at root, upward traversal |
| SYSTEM | Yes | `.gemini/system.md` or `GEMINI_SYSTEM_MD` env |
| HOOKS | Yes | In settings.json |

## Path summary

| Artifact | Project Path | User Path |
|----------|-------------|-----------|
| Root config | `./GEMINI.md` (upward traversal) | `~/.gemini/GEMINI.md` |
| Policies | `.gemini/policies/*.toml` | `~/.gemini/policies/*.toml` |
| Skills | `.gemini/skills/<name>/SKILL.md` OR `.agents/skills/<name>/SKILL.md` | `~/.gemini/skills/` OR `~/.agents/skills/` |
| Agents | `.gemini/agents/*.md` | `~/.gemini/agents/*.md` |
| System prompt | `.gemini/system.md` | N/A (env var) |
| Hooks | `.gemini/settings.json` | `~/.gemini/settings.json` |
| Settings | `.gemini/settings.json` | `~/.gemini/settings.json` |
| Extensions | `.gemini/extensions/` | `~/.gemini/extensions/` |

## Known issues

### CRITICAL: `.gemini/GEMINI.md` is not a valid read location

The current vaultspec Gemini `ToolConfig` sets `config_file` to
`.gemini/GEMINI.md`. This is wrong. Gemini CLI reads `GEMINI.md` via
upward traversal from project root — it does NOT look inside `.gemini/`
for the context file. The config must point to `./GEMINI.md` at project
root.

### POTENTIAL: Duplicate skill loading when both Gemini and Antigravity installed

If both Gemini and Antigravity are installed as providers, vaultspec syncs
skills to both `.gemini/skills/` and `.agents/skills/`. Since Gemini CLI
reads from both locations (with `.agents/skills/` taking precedence),
identical skills would be loaded twice — once from each directory. This
could cause duplicate context injection or unexpected precedence behavior.

**Mitigation options:**
- Only sync skills to `.agents/skills/` when both providers are installed
  (since it takes precedence anyway)
- Skip `.gemini/skills/` sync entirely and always use `.agents/skills/`
- Track co-installed providers and conditionally skip the lower-precedence
  path
