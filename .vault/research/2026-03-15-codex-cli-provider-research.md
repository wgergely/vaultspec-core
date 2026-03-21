---
tags:
  - '#research'
  - '#install-cmds'
date: '2026-03-15'
related:
  - '[[2026-03-15-install-cmds-plan]]'
  - '[[2026-03-15-claude-code-provider-research]]'
  - '[[2026-03-15-gemini-cli-provider-research]]'
---

# Codex CLI provider grounding research

User-approved grounding research for OpenAI Codex CLI provider
configuration. All findings verified against official documentation at
developers.openai.com/codex on 2026-03-15.

## Root instruction file (AGENTS.md)

- **Filename:** `AGENTS.md` (no `CODEX.md` exists)

- **Override:** `AGENTS.override.md` takes precedence at any level

- **Project-level:** Walks DOWN from git root toward cwd, checking each
  directory for `AGENTS.override.md` then `AGENTS.md` then fallbacks.
  Takes at most one file per directory. Concatenates with blank lines.

- **User-level:** `~/.codex/AGENTS.md` (or `$CODEX_HOME/AGENTS.md`).
  Checks `AGENTS.override.md` first, falls back to `AGENTS.md`. Uses
  only the first non-empty file at this level.

- **Fallback filenames:** Configurable via `project_doc_fallback_filenames`
  in `~/.codex/config.toml` (e.g. `["TEAM_GUIDE.md", ".agents.md"]`)

- **Max size:** 32 KiB default (`project_doc_max_bytes`)

- **Treatment:** AGENTS.md is equivalent to CLAUDE.md and GEMINI.md — a
  root instruction/config file that vaultspec generates with framework
  content and rule references. Same treatment applies.

- **Source:** https://developers.openai.com/codex/guides/agents-md/

## Config file (config.toml)

- **User-level:** `~/.codex/config.toml`

- **Project-level:** `.codex/config.toml` (only loaded for trusted projects)

- **System-level:** `/etc/codex/config.toml` (Unix)

- **Precedence (highest to lowest):** CLI flags > profile > project config
  (closest wins) > user config > system config > built-in defaults

- **Source:** https://developers.openai.com/codex/config-basic/,
  https://developers.openai.com/codex/config-reference/

## Rules (behavioral)

- **Supported:** Yes — via `AGENTS.md` content and `@rules/...`
  references, the same mechanism used by Claude and Gemini

- **Delivery:** Vaultspec's behavioral rules (coding conventions, style
  guides) are injected into `AGENTS.md` as rule references. Codex reads
  `AGENTS.md` as its primary instruction file.

- **This is NOT Codex's execution policy system.** Codex has a separate
  `.codex/rules/*.rules` system (Starlark `prefix_rule()` calls) for
  controlling command execution (allow/deny/prompt). That system manages
  security policies, not coding conventions. Vaultspec does not interact
  with Codex's execution policy system.

- **Source:** https://developers.openai.com/codex/guides/agents-md/

## Skills

- **Project:** `.agents/skills/<name>/SKILL.md` — scans from cwd UP to
  repo root, checking `.agents/skills/` in every directory along the path

- **User:** `~/.agents/skills/<name>/SKILL.md` AND `~/.codex/skills/`

- **Admin:** `/etc/codex/skills/`

- **System:** Bundled built-in skills (skill-creator, plan)

- **Format:** `SKILL.md` with YAML frontmatter (`name`, `description`),
  optional subdirectories: `scripts/`, `references/`, `assets/`,
  `agents/openai.yaml`

- **`agents/openai.yaml`:** Optional metadata controlling UI appearance,
  invocation policy (`allow_implicit_invocation`), and tool dependencies

- **Discovery:** Progressive disclosure — metadata loaded first, full
  SKILL.md loaded only on activation

- **Precedence:** No formal override — duplicate names across scopes both
  remain selectable

- **Symlinks:** Supported

- **Source:** https://developers.openai.com/codex/skills/

## Agents (multi-agent)

- **Experimental:** Requires `multi_agent = true` in `[features]` section
  of config.toml, or enable via `/experimental` CLI command

- **Defined in:** `config.toml` under `[agents.<name>]` tables — NOT
  markdown files in a directory

- **Fields:** `description`, `config_file` (path to role-specific TOML
  layer), `model`, `model_reasoning_effort`, `sandbox_mode`,
  `developer_instructions`, `nickname_candidates`

- **Global settings:** `[agents]` table with `max_threads` (default 6),
  `max_depth` (default 1), `job_max_runtime_seconds`

- **Built-in roles:** default, worker, explorer, monitor

- **User-defined roles override built-ins** with matching names

- **Orchestration:** Codex handles spawning, routing, result consolidation.
  `spawn_agents_on_csv` for batch processing.

- **Implication:** vaultspec cannot sync agents to Codex via markdown
  files. Needs a TOML adapter to write `[agents.<name>]` sub-tables
  into config.toml. Note: config.toml schema has
  `additionalProperties: false` at root, so custom top-level tables
  like `[vaultspec]` are rejected — but `[agents.<name>]` sub-tables
  for custom role names ARE allowed by the schema.

- **Source:** https://developers.openai.com/codex/multi-agent/

## System prompt

- **`model_instructions_file`** config key exists in config.toml but is
  minimally documented

- No `.codex/SYSTEM.md` or dedicated system file

- `AGENTS.md` is the primary instruction mechanism

- **Source:** https://developers.openai.com/codex/config-advanced/

## Hooks

- **No comprehensive hooks system in stable release**

- **`notify`** setting in config.toml triggers an external program on
  `agent-turn-complete` event only. Receives JSON via argv.

- **`tui.notifications`** for built-in TUI alerts, filterable by event type

- An experimental hooks PR (v0.114) added `hooks.json` in `.codex/` but
  this is NOT in official stable documentation

- **Source:** https://developers.openai.com/codex/config-advanced/

## .agents/ relationship

- Codex uses `.agents/skills/` as its PRIMARY skills directory
- Shared with Antigravity — both tools scan `.agents/skills/`
- No `.agents/rules/` or `.agents/agents/` for Codex
- User-level: `~/.agents/skills/` also scanned

## Capability matrix

| Capability  | Supported          | Format                               | Notes                                      |
| ----------- | ------------------ | ------------------------------------ | ------------------------------------------ |
| RULES       | Yes                | Via AGENTS.md rule references        | Same delivery as Claude/Gemini             |
| SKILLS      | Yes                | Markdown (SKILL.md)                  | `.agents/skills/`, shared with Antigravity |
| AGENTS      | Yes (experimental) | TOML (`[agents.*]` in config.toml)   | Needs TOML adapter for config.toml         |
| ROOT_CONFIG | Yes                | Markdown (AGENTS.md)                 | Same treatment as CLAUDE.md/GEMINI.md      |
| SYSTEM      | Minimal            | TOML key (`model_instructions_file`) | Not a standalone file                      |
| HOOKS       | Minimal            | TOML key (`notify`)                  | Single event only                          |

## Path summary

| Artifact         | Project Path                      | User Path                                 |
| ---------------- | --------------------------------- | ----------------------------------------- |
| Instruction file | `./AGENTS.md` (downward walk)     | `~/.codex/AGENTS.md`                      |
| Override file    | `./AGENTS.override.md`            | `~/.codex/AGENTS.override.md`             |
| Config           | `.codex/config.toml`              | `~/.codex/config.toml`                    |
| Rules            | Via `./AGENTS.md` rule references | Via `~/.codex/AGENTS.md`                  |
| Skills           | `.agents/skills/<name>/SKILL.md`  | `~/.agents/skills/` or `~/.codex/skills/` |
| Agents           | In `.codex/config.toml`           | In `~/.codex/config.toml`                 |
| System           | In `.codex/config.toml`           | In `~/.codex/config.toml`                 |

## Known issues for vaultspec

### TOML adapter required for agents

Codex agent definitions live in `config.toml` as `[agents.<name>]`
TOML sub-tables. The config.toml schema rejects unknown top-level
keys (`additionalProperties: false`) so vaultspec cannot add its own
namespace table. Agent roles must be written as standard
`[agents.<name>]` entries. Requires managed block markers
(`# <vaultspec type="agents">`) to delimit vaultspec-managed agent
entries from user-defined ones.

### `_generate_codex_agents_md()` audit finding

Current implementation in `config_gen.py:228` generates AGENTS.md content
but **does NOT include rule references** (`_collect_rule_refs`), unlike
`_generate_config()` which does. AGENTS.md should receive the same
treatment as CLAUDE.md and GEMINI.md — framework content + rule refs.
This function should be unified with or delegate to `_generate_config()`.

### Shared `.agents/skills/` with Antigravity

Both Codex and Antigravity scan `.agents/skills/`. Content is identical
(same vaultspec source), but pruning by one provider could remove files
expected by the other. Uninstalling one provider must not break the other.
