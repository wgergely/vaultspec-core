---
tags:
  - '#research'
  - '#install-cmds'
date: '2026-03-16'
related:
  - '[[2026-03-15-install-cmds-plan]]'
  - '[[2026-03-15-claude-code-provider-research]]'
  - '[[2026-03-15-gemini-cli-provider-research]]'
---

# Antigravity provider grounding research

User-approved grounding research for Google Antigravity provider
configuration. Findings verified against official codelabs, Google AI
Developers Forum, and community sources on 2026-03-16.

## Root config file

- **Filename:** `GEMINI.md` — shared with Gemini CLI

- **Project-level:** `GEMINI.md` at project root (same file Gemini CLI reads)

- **Global:** `~/.gemini/GEMINI.md` (shared with Gemini CLI — known
  conflict per github.com/google-gemini/gemini-cli/issues/16058)

- **No `AGENTS.md`** — Antigravity does NOT use AGENTS.md. AGENTS.md is
  Codex-only.

- **Source:** https://codelabs.developers.google.com/getting-started-google-antigravity,
  https://github.com/google-gemini/gemini-cli/issues/16058

## Workspace directory

- **Canonical path:** `.agents/` (plural)

- **Legacy `.agent/` (singular) is NOT supported by vaultspec** — any
  references to `.agent/` in the codebase are erroneous and must be
  removed. vaultspec does not maintain backward compatibility with the
  deprecated singular form.

- **Confirmed by Google staff:** "Going forward, `.agents` (plural) should
  be used as Antigravity team has moved towards that."

- **Subdirectories:** `rules/`, `workflows/`, `skills/`

- **Source:** https://discuss.ai.google.dev/t/new-folder-for-rules/126165

## Rules

- **Path:** `.agents/rules/*.md` (workspace/project level)
- **Global:** Via `~/.gemini/GEMINI.md` (injected as global rules)
- **Format:** Markdown files — behavioral guidelines
- **Behavior:** Always-on, passive constraints injected into system prompt
- **No YAML frontmatter documented** for rules (unlike skills)
- **Source:** https://codelabs.developers.google.com/getting-started-google-antigravity

## Workflows

- **Path:** `.agents/workflows/*.md` (workspace/project level)

- **Global:** `~/.gemini/antigravity/global_workflows/*.md`

- **Format:** Markdown files — saved prompts

- **Behavior:** User-triggered on demand with `/` prefix (not agent-triggered)

- **Note:** This is a new resource type that vaultspec does not currently
  model. `Resource.WORKFLOWS` does not exist in enums.py.

- **Source:** https://codelabs.developers.google.com/getting-started-google-antigravity

## Skills

- **Workspace:** `.agents/skills/<name>/SKILL.md`

- **Global:** `~/.gemini/antigravity/skills/<name>/SKILL.md`

- **Format:** `SKILL.md` with YAML frontmatter (`name`, `description`),
  optional subdirectories: `scripts/`, `references/`, `assets/`

- **Behavior:** Agent-triggered via progressive disclosure — metadata
  loaded first, full SKILL.md on activation

- **Shared:** Same `.agents/skills/` directory used by Gemini CLI (alias)
  and Codex CLI

- **Source:** https://codelabs.developers.google.com/getting-started-with-antigravity-skills

## Agents

- **No user-managed agent definition directory documented**

- Antigravity has built-in agent modes (autopilot, review-driven,
  agent-assisted) but no `.agents/agents/` folder for custom definitions

- **No `.agents/agents/` should be scaffolded**

## System prompt

- **No user-facing system prompt file**
- Rules in `.agents/rules/` serve this purpose (injected into system prompt)
- `GEMINI.md` content also injected as context
- No equivalent to Gemini CLI's `.gemini/system.md`

## Hooks

- **No hooks system documented** for Antigravity
- Antigravity is an IDE, not a CLI — different lifecycle model

## .agents/ relationship with other providers

- `.agents/skills/` is shared across Antigravity, Gemini CLI (as alias),
  and Codex CLI (as primary path)

- `.agents/rules/` is Antigravity-specific — Gemini CLI does NOT read
  rules from `.agents/rules/` (it uses `.gemini/policies/*.toml`)

- `.agents/workflows/` is Antigravity-specific

- `GEMINI.md` at project root is shared between Antigravity and Gemini CLI

## Capability matrix

| Capability  | Supported    | Notes                                                      |
| ----------- | ------------ | ---------------------------------------------------------- |
| RULES       | Yes          | `.agents/rules/*.md`, always-on behavioral guidelines      |
| SKILLS      | Yes          | `.agents/skills/<name>/SKILL.md`, shared with Gemini/Codex |
| WORKFLOWS   | Yes          | `.agents/workflows/*.md`, user-triggered saved prompts     |
| AGENTS      | No           | No user-managed agent definitions                          |
| ROOT_CONFIG | Yes (shared) | `GEMINI.md` at root, shared with Gemini CLI                |
| SYSTEM      | No           | Rules serve this purpose                                   |
| HOOKS       | No           | IDE, not CLI                                               |

## Path summary

| Artifact    | Project Path                       | User Path                                 |
| ----------- | ---------------------------------- | ----------------------------------------- |
| Root config | `./GEMINI.md` (shared with Gemini) | `~/.gemini/GEMINI.md` (shared, conflict)  |
| Rules       | `.agents/rules/*.md`               | Via `~/.gemini/GEMINI.md`                 |
| Skills      | `.agents/skills/<name>/SKILL.md`   | `~/.gemini/antigravity/skills/`           |
| Workflows   | `.agents/workflows/*.md`           | `~/.gemini/antigravity/global_workflows/` |

## Known issues for vaultspec

### Shared GEMINI.md between Gemini and Antigravity

Both providers read/write the same `GEMINI.md` file at project root.
They cannot have independent root configs. This validates the current
design where Antigravity's `config_file` points to root `GEMINI.md` and
sync target `gemini` includes Antigravity.

### Workflows resource type not modeled

`.agents/workflows/` is scaffolded by `init_run()` but there is no
`Resource.WORKFLOWS` in enums.py and no sync pipeline for workflows.
This should be added as a capability in the enum even if sync is deferred.

### Remove all `.agent/` (singular) references

Any references to `.agent/` in the codebase are erroneous. vaultspec
does not maintain backward compatibility with the deprecated singular
form. Only `.agents/` (plural) is supported.
