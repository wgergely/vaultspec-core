---
tags:
  - "#research"
  - "#install-cmds"
  - "#provider-grounding"
  - "#claude"
date: "2026-03-15"
related:
  - "[[2026-03-15-install-cmds-plan]]"
  - "[[2026-03-11-codex-integration-research]]"
---

# Claude Code provider grounding research

User-approved grounding research for Claude Code (Anthropic) provider
configuration. All findings verified against official documentation at
code.claude.com on 2026-03-15.

## Root config file

- **Filename:** `CLAUDE.md`
- **Project-level:** `./CLAUDE.md` OR `./.claude/CLAUDE.md` (both valid)
- **User-level:** `~/.claude/CLAUDE.md`
- **Managed policy:** OS-specific (`/Library/Application Support/ClaudeCode/CLAUDE.md`, `/etc/claude-code/CLAUDE.md`, `C:\Program Files\ClaudeCode\CLAUDE.md`)
- **Hierarchy:** Walks UP directory tree from cwd, loading from each ancestor. Subdirectory CLAUDE.md files load on-demand.
- **Precedence:** More specific locations override broader ones.
- **Source:** https://code.claude.com/docs/en/memory

## Rules

- **Path:** `.claude/rules/*.md` (project), `~/.claude/rules/*.md` (user)
- **Format:** Markdown with optional YAML frontmatter (`paths:` for glob-scoped loading)
- **Discovery:** Recursive within rules directory, subdirectories supported
- **Loading:** Unconditional rules load at session start. Path-scoped rules load when Claude reads matching files.
- **Symlinks:** Supported for cross-project sharing.
- **Source:** https://code.claude.com/docs/en/memory

## Skills

- **Path:** `.claude/skills/<skill-name>/SKILL.md` (project), `~/.claude/skills/<skill-name>/SKILL.md` (user)
- **Enterprise:** Via managed settings
- **Plugin:** `<plugin>/skills/<skill-name>/SKILL.md`
- **Precedence:** enterprise > personal > project
- **Format:** YAML frontmatter (`name`, `description`, `disable-model-invocation`, `allowed-tools`, `model`, `context`, `agent`, `hooks`, `user-invocable`, `argument-hint`)
- **Standard:** Follows Agent Skills open standard (https://agentskills.io)
- **Legacy:** `.claude/commands/*.md` still works but skills take precedence
- **Source:** https://code.claude.com/docs/en/skills

## Agents (subagents)

- **Path:** `.claude/agents/<agent-name>.md` (project), `~/.claude/agents/<agent-name>.md` (user)
- **Plugin:** `<plugin>/agents/*.md`
- **CLI-defined:** `--agents '{JSON}'` (session-only)
- **Precedence:** CLI flag > project > user > plugin
- **Format:** Markdown with YAML frontmatter (`name`, `description`, `tools`, `disallowedTools`, `model`, `permissionMode`, `maxTurns`, `skills`, `mcpServers`, `hooks`, `memory`, `background`, `isolation`)
- **Body = system prompt** for the subagent
- **Built-in agents:** Explore (haiku, read-only), Plan (inherited, read-only), general-purpose (inherited, all tools), Bash, statusline-setup, Claude Code Guide
- **Source:** https://code.claude.com/docs/en/sub-agents

## System prompt

- **No user-facing system prompt file.** System prompt controlled by Anthropic.
- Users influence via CLAUDE.md and .claude/rules/
- Programmatic: `--append-system-prompt` CLI flag
- **Source:** https://code.claude.com/docs/en/memory

## Hooks

- **Project:** `.claude/settings.json` under `"hooks"` key
- **Project-local:** `.claude/settings.local.json` (gitignored)
- **User:** `~/.claude/settings.json`
- **Managed:** Organization-wide policy
- **Also in:** skill/agent YAML frontmatter (scoped to component lifecycle)
- **Events:** SessionStart, SessionEnd, InstructionsLoaded, UserPromptSubmit, Stop, SubagentStop, PreToolUse, PostToolUse, PostToolUseFailure, PermissionRequest, Notification, SubagentStart, TeammateIdle, TaskCompleted, ConfigChange, WorktreeCreate, WorktreeRemove, PreCompact, PostCompact, Elicitation, ElicitationResult
- **Source:** https://code.claude.com/docs/en/hooks

## Agent teams (experimental)

- **Feature flag:** `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` in settings or env
- **Config storage:** `~/.claude/teams/{team-name}/config.json`
- **Task list storage:** `~/.claude/tasks/{team-name}/`
- **No file-based team definitions** — teams created dynamically via natural language
- Components: team lead, teammates (separate Claude instances), shared task list, mailbox
- Display modes: in-process (default) or split-pane (tmux/iTerm2)
- **Source:** https://code.claude.com/docs/en/agent-teams

## Scheduled tasks

- **Session-scoped only** — no persistent file configuration
- `/loop` skill + CronCreate/CronList/CronDelete tools
- 5-field standard cron syntax
- Max 50 tasks per session, 3-day auto-expiry on recurring
- For durable scheduling: Desktop scheduled tasks or GitHub Actions
- Disable: `CLAUDE_CODE_DISABLE_CRON=1`
- **Source:** https://code.claude.com/docs/en/scheduled-tasks

## .agents/ relationship

- Claude Code does NOT interact with `.agents/` directory
- `.agents/` is a Google/OpenAI convention
- Claude Code uses `.claude/agents/` for its own agent definitions

## Capability matrix

| Capability | Supported | Notes |
|-----------|-----------|-------|
| RULES | Yes | `.claude/rules/*.md` |
| SKILLS | Yes | `.claude/skills/<name>/SKILL.md` |
| AGENTS | Yes | `.claude/agents/<name>.md` |
| ROOT_CONFIG | Yes | `CLAUDE.md` at root or `.claude/CLAUDE.md` |
| SYSTEM | No | No native system file |
| HOOKS | Yes | In settings.json, not a directory |
| TEAMS | Yes (experimental) | Dynamic, not file-synced |
| SCHEDULED_TASKS | Yes | Session-scoped, not file-synced |

## Path summary

| Artifact | Project Path | User Path |
|----------|-------------|-----------|
| Root config | `./CLAUDE.md` or `./.claude/CLAUDE.md` | `~/.claude/CLAUDE.md` |
| Rules | `.claude/rules/*.md` | `~/.claude/rules/*.md` |
| Skills | `.claude/skills/<name>/SKILL.md` | `~/.claude/skills/<name>/SKILL.md` |
| Agents | `.claude/agents/<name>.md` | `~/.claude/agents/<name>.md` |
| Hooks | `.claude/settings.json` | `~/.claude/settings.json` |
| Teams | N/A (dynamic) | `~/.claude/teams/` |
| Scheduled tasks | N/A (session-scoped) | N/A |
