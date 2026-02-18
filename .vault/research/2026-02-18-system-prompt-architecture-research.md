---
# ALLOWED TAGS - DO NOT REMOVE - REFERENCE: #adr #audit #exec #plan #reference #research #<feature>
# Directory tag (hardcoded - DO NOT CHANGE - based on .vault/research/ location)
# Feature tag (replace <feature> with your feature name, e.g., #editor-demo)
tags:
  - "#research"
  - "#system-prompt"
# ISO date format (e.g., 2026-02-06)
date: 2026-02-18
# Related documents as quoted wiki-links (e.g., "[[2026-02-04-feature-plan]]")
related:
  - "[[2026-02-17-tech-audit-audit]]"
---
<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields outside the YAML frontmatter above -->

# system-prompt research: architecture and tool-specific behavioral disparity

Research into how Claude Code and Gemini CLI consume system prompts, how
vaultspec's `.vaultspec/system/` composition pipeline maps to each tool's
configuration surface, and the quality of the current assembled outputs.
Three parallel investigations were conducted: Claude Code CLI mechanisms,
Gemini CLI mechanisms, and an internal cohesion audit of all system/ files.

## Findings

### 1. Claude Code system prompt mechanisms

Claude Code provides **four CLI flags** for system prompt control:

| Flag | Behavior | Modes |
|------|----------|-------|
| `--system-prompt "text"` | Replaces entire default system prompt | Interactive + Print |
| `--system-prompt-file path` | Replaces with file contents | Print only |
| `--append-system-prompt "text"` | Appends to default prompt | Interactive + Print |
| `--append-system-prompt-file path` | Appends file contents | Print only |

`--system-prompt` and `--system-prompt-file` are mutually exclusive. The append
flags can be combined with either replacement flag. There is **no equivalent
setting** in `settings.json` or `settings.local.json` -- system prompt
customization is CLI-flag-only (or via the Agent SDK programmatically).

**CLAUDE.md is NOT part of the system prompt.** It is injected as the first user
message wrapped in `<system-reminder>` tags with a disclaimer that says "this
context may or may not be relevant to your tasks." This is a known issue
(anthropics/claude-code#7571). Content passed via `--append-system-prompt`
becomes part of the actual system prompt and has **strictly higher priority**
than any CLAUDE.md content.

`.claude/rules/*.md` files are injected the same way as CLAUDE.md -- as
`<system-reminder>` user context, not system prompt.

**Priority hierarchy** (highest to lowest):

1. `--system-prompt` / `--append-system-prompt` (actual system prompt)
2. Managed policy CLAUDE.md (`C:\Program Files\ClaudeCode\CLAUDE.md`)
3. `.claude/CLAUDE.md` (project, VCS-tracked)
4. `.claude/rules/*.md` (same priority as CLAUDE.md)
5. `~/.claude/CLAUDE.md` (personal global)
6. `CLAUDE.local.md` (personal project)
7. Auto memory (`~/.claude/projects/*/memory/MEMORY.md`, 200 lines)

**Sources:** [[claude-code-docs-memory]], [[claude-code-docs-cli-reference]],
[[anthropics/claude-code#6973]], [[anthropics/claude-code#7571]]

### 2. Gemini CLI system prompt mechanisms

Gemini CLI supports **full system prompt replacement** via the `GEMINI_SYSTEM_MD`
environment variable. There is **no `--system` or `--system-prompt` CLI flag**.

| Mechanism | Effect |
|-----------|--------|
| `GEMINI_SYSTEM_MD=true` or `=1` | Reads `.gemini/system.md` as full replacement |
| `GEMINI_SYSTEM_MD=/path/to/file` | Reads from specified path as full replacement |
| `GEMINI_WRITE_SYSTEM_MD=1` | Exports built-in system prompt to `.gemini/system.md` |

Custom system prompt files support **template variables**:

- `${AgentSkills}` -- injects all available agent skills
- `${SubAgents}` -- injects available sub-agents
- `${AvailableTools}` -- injects enabled tool names
- `${toolName_ToolName}` -- per-tool name injection

Visual indicator: `|sunglasses_ascii|` in the CLI footer when custom system prompt is active.

**GEMINI.md is additive context** (analogous to CLAUDE.md), with a three-tier
hierarchy: global (`~/.gemini/GEMINI.md`), workspace (project tree), and JIT
(on-demand when tools access directories). All discovered files are concatenated
into the system instructions -- they are part of the actual `systemInstruction`
API field, not user messages.

The `context.fileName` setting is configurable and supports arrays
(e.g., `["AGENTS.md", "GEMINI.md"]`).

**Design philosophy**: SYSTEM.md = "firmware" (non-negotiable operational rules),
GEMINI.md = "strategy" (persona, goals, project context).

**Sources:** [[geminicli-system-prompt]], [[gemini-cli-configuration]],
[[google-gemini/gemini-cli/discussions/1471]]

### 3. Current vaultspec system/ architecture

The `system/` directory contains 6 files. `cli.py` assembles them into two
separate outputs:

**Config sync** (CLAUDE.md frontmatter, GEMINI.md config):

- `framework.md` (`pipeline: config`) -- vaultspec identity and pipeline bootstrap
- `project.md` (`pipeline: config`) -- empty placeholder for user customization

**System sync** (`.gemini/SYSTEM.md` only -- Claude has no system_file):

Assembly order: `base.md` first, then `tool: gemini` parts, then auto-generated
agents/skills, then remaining shared parts in alphabetical order.

Final Gemini SYSTEM.md order:
`base.md` -> `gemini.md` -> [agents] -> [skills] -> `operations.md` -> `workflow.md`

### 4. Cohesion audit grades

| File | Grade | Key issues |
|------|-------|------------|
| `base.md` | B- | "Jean-Claude" persona in shared file; `activate_skill` / `<activated_skill>` are Gemini-specific refs with no `tool:` frontmatter |
| `gemini.md` | B | Correct `tool: gemini` frontmatter; ~35 lines of shell examples consuming ~40% of assembled prompt; forward-reference to "Explain Critical Commands rule above" which actually appears AFTER in assembly |
| `operations.md` | C+ | **8+ Gemini-specific tool names** (`run_shell_command`, `save_memory`, `read_file`, `/help`, `/bug`) but NO `tool:` frontmatter -- masquerades as shared; allcaps "IT IS CRITICAL" anti-pattern; `****` typo on line 33 |
| `workflow.md` | A- | Clean, tool-agnostic; references `system/framework.md` which is excluded from system prompt assembly |
| `framework.md` | B+ | Correct `pipeline: config`; well-structured XML tags; tool-agnostic |
| `project.md` | N/A | Empty placeholder |
| Assembled `.gemini/SYSTEM.md` | C+ | Frankenstein assembly; contradictory identity (Jean-Claude vs. vaultspec); wrong ordering (workflow routing placed last); shell examples disproportionate |
| Assembled `.claude/CLAUDE.md` | B | Correct config format; **missing ALL behavioral instructions** (base.md, operations.md, workflow.md never reach Claude) |

### 5. P0 issues (critical)

1. **operations.md is Gemini-specific but has no `tool:` frontmatter.** It
   contains `run_shell_command` (x3), `save_memory`, `read_file`, `/help`,
   `/bug` -- all Gemini CLI tool names. Any new tool added to the system sync
   pipeline would inherit these Gemini-specific instructions.

2. **base.md leaks Gemini-specific content.** Line 14 references
   `activate_skill` and `<activated_skill>` tags, which are Gemini CLI
   constructs. This is in a shared file with no `tool:` filter.

3. **Claude receives zero behavioral instructions.** Claude's ToolConfig has no
   `system_file`, so base.md, operations.md, and workflow.md are never assembled
   for Claude. The entire behavioral framework (core mandates, security rules,
   git workflow, tone guidelines) is invisible to Claude Code. Claude only
   receives the vaultspec pipeline bootstrap via CLAUDE.md frontmatter and the
   two rule references.

### 6. P1 issues (important)

4. `****` typo on operations.md line 33 (renders as visible garbage).
5. ALLCAPS "IT IS CRITICAL" on operations.md line 5 (prompt engineering anti-pattern).
6. "Jean-Claude" persona in base.md line 1 (tool-specific name in shared file;
   doesn't reach Claude anyway since base.md is excluded from CLAUDE.md).
7. Forward-reference in gemini.md line 64 ("rule above" but rule appears AFTER
   in assembly).
8. Shell tool examples consume ~40% of assembled system prompt. The `sg` examples
   alone are 32 lines of code. These are processed on every conversation turn
   regardless of task type.
9. Workflow routing (workflow.md) placed last in assembly due to alphabetical
   sort. Should appear earlier given its importance as a routing directive.

### 7. Architectural design options for Claude behavioral coverage

| Option | Mechanism | Pros | Cons |
|--------|-----------|------|------|
| A: `--append-system-prompt-file` | CLI flag on launch | Highest priority; actual system prompt; persistent across session | Not persistent across sessions without wrapper script; CLI-only |
| B: Add `system_file` to Claude ToolConfig | Assemble `.claude/SYSTEM.md` like Gemini | Symmetric architecture; reuses existing pipeline | Claude Code ignores files outside CLAUDE.md/rules; unclear if Claude Code would load a SYSTEM.md |
| C: Expand `.claude/rules/` | Generate behavioral rules from system/ parts | Leverages existing rules mechanism; always loaded | Rules have the `<system-reminder>` disclaimer; lower priority than system prompt |
| D: Embed in CLAUDE.md body | Put behavioral content below rule references | Simple; uses existing config sync | CLAUDE.md already has disclaimer issue; body content is user context |
| E: Use `project.md` body | Write behavioral content to project.md, which flows into CLAUDE.md body | Uses existing pipeline; no new mechanism | Same disclaimer issue as option D |

**Recommended approach**: Option C (expand `.claude/rules/`) as the primary
mechanism, with the behavioral instructions extracted into tool-agnostic shared
rules and Claude-specific rules. This is the most reliable persistent mechanism
that integrates with the existing sync pipeline.

### 8. Recommended restructuring

**R1: Split operations.md** into tool-agnostic `operations.md` and
`operations-gemini.md` (`tool: gemini`). All references to `run_shell_command`,
`save_memory`, `read_file`, `/help`, `/bug` move to the Gemini-specific file.
The shared file uses generic language ("your shell tool", "your file reading
tool") or omits tool-specific instructions entirely.

**R2: Move Gemini-specific content out of base.md.** Line 14
(`activate_skill` / `<activated_skill>`) moves to `gemini.md`. The "Jean-Claude"
persona is either removed or moved to a Gemini-specific identity line.

**R3: Generate Claude behavioral rules.** Extract shared behavioral mandates
(core mandates, security rules, git workflow, tone) into `.claude/rules/`
files via the sync pipeline. This gives Claude the same behavioral framework
that Gemini receives through SYSTEM.md.

**R4: Support explicit assembly ordering.** Add an `order:` frontmatter key
(integer) so workflow.md can appear before operations.md. Alphabetical fallback
when no order is specified.

**R5: Reduce shell example volume.** Move detailed `fd`/`rg`/`sd`/`sg` examples
from `gemini.md` into the corresponding skill files. The system prompt should
contain concise tool descriptions; detailed examples load on-demand when skills
are activated.

**R6: Fix small defects.** Remove `****` typo, replace allcaps directive,
fix forward-reference, relocate "no numbered lists" to tone/style section.

**R7: Reconcile overlapping mandates.** Establish a clear hierarchy: base.md
defines principles, operations.md defines procedures, workflow.md defines
routing. Currently these boundaries are blurred with principles mixed into
procedures and vice versa.
