---
tags:
  - "#research"
  - "#codex-integration"
date: "2026-03-11"
related:
  - "[[2026-02-18-system-prompt-architecture-research]]"
  - "[[2026-02-22-cli-ecosystem-factoring-research]]"
---

# codex-integration research: codex and antigravity destination compatibility

This research corrects the earlier framing error. The compatibility question is
not whether vaultspec can copy markdown into another tool's folders. The real
question is whether each destination matches vaultspec's current sync pipeline:

- `transform_rule()` writes per-rule markdown files with YAML frontmatter
  (`name`, `trigger: always_on`) into `rules_dir`.
- `_generate_config()` writes a top-level config markdown file and injects
  `@rules/...` include references.
- `transform_skill()` writes directory-per-skill outputs ending in `SKILL.md`.
- `system.py` either writes a dedicated `SYSTEM.md` or writes a synthesized
  `vaultspec-system.builtin.md` rule into `rules_dir`.

That means Codex and Antigravity must be judged against the current
`rules_dir` + `config_file` + `skills_dir` model, not against a raw file copy
model.

## Primary sources

- OpenAI Codex config reference: <https://developers.openai.com/codex/config-reference>
- OpenAI Codex skills guide: <https://developers.openai.com/codex/skills>
- OpenAI Codex AGENTS.md guide: <https://developers.openai.com/codex/guides/agents-md>
- OpenAI Codex custom prompts guide: <https://developers.openai.com/codex/custom-prompts>
- OpenAI Codex repo docs:
  <https://raw.githubusercontent.com/openai/codex/main/docs/skills.md>
- OpenAI Codex config schema:
  <https://raw.githubusercontent.com/openai/codex/main/codex-rs/core/config.schema.json>
- Official Antigravity skills docs:
  <https://antigravity.google/docs/skills>
- Official Antigravity rules/workflows docs:
  <https://antigravity.google/docs/rules-workflows>
- Official Google Codelab for Antigravity rules, skills, and workflows:
  <https://codelabs.developers.google.com/codelabs/antigravity-rules-skills-and-workflows>

## Findings

### Destination fact table

| Question | Codex | Antigravity | Confidence |
| --- | --- | --- | --- |
| Primary config folder | `.codex/` with `config.toml` | Workspace customization is under `.agents/`; global customization is under `~/.gemini/antigravity/...` | High |
| Top-level config file | `config.toml`; no `CODEX.md` | `GEMINI.md` is still documented, and no `AGENTS.md` config file is documented | High |
| Rules mechanism | `AGENTS.md` and `AGENTS.override.md`, loaded hierarchically across parent directories; no `rules/` folder is documented | Workspace rules live in `.agents/rules/`; the rules docs place global rules in `~/.gemini/GEMINI.md` | High |
| Skills mechanism | `.agents/skills/<skill>/SKILL.md` with optional `scripts/`, `references/`, `assets/`, and optional skill-local agent metadata | `.agents/skills/<skill>/SKILL.md` with optional `scripts/`, `resources/`, `assets/` | High |
| Workflows | No separate workflow folder documented | `.agents/workflows/` in workspace; `~/.gemini/antigravity/global_workflows/` globally | High |
| Agent definitions | Supported through `[agents]` tables in `config.toml`; not a folder of markdown files | No primary-source documentation for a user-managed agent-definition folder | Medium |
| Frontmatter usage | `SKILL.md` uses YAML frontmatter; deprecated custom prompts also used frontmatter; `config.toml` and `AGENTS.md` do not | `SKILL.md` uses YAML frontmatter (`name`, `description`); no frontmatter shown for rules or workflows | High |
| Internal instruction document | `AGENTS.md` is the primary project instruction document | `GEMINI.md` remains the documented instruction file; workspace customizations are split across `.agents/*` | High |

### Codex: confirmed structure and expectations

1. Codex's tool-owned folder is **`.codex/`**, and its project config file is
   **`.codex/config.toml`**. The config reference documents instruction-bearing
   keys such as `instructions`, `developer_instructions`, and
   `model_instructions_file`.
2. Codex does **not** document a `CODEX.md` or a `.codex/rules/` directory.
   Instead, it reads **`AGENTS.md`** and **`AGENTS.override.md`**, walking up
   parent directories and also supporting global user-level files.
3. Codex skills are documented under **`.agents/skills/`**, not under
   `.codex/skills/`. The expected skill shape is directory-based:

   ```text
   .agents/skills/my-skill/
   - SKILL.md
   - scripts/
   - references/
   - assets/
   - agents/openai.yaml   (optional skill-local metadata)
   ```

4. Codex supports agent definitions, but the shape is **TOML config tables**
   inside `config.toml`, not a synced `agents_dir` of markdown files.
5. Codex frontmatter use is narrow:
   - `SKILL.md`: yes
   - deprecated prompts in `~/.codex/prompts/`: yes
   - `AGENTS.md`: no documented frontmatter requirement
   - `config.toml`: no, pure TOML

### Antigravity: the singular/plural question is now settled

The current official Antigravity codelab documents the **workspace folder as
`.agents/` (plural)**:

- `.agents/rules/`
- `.agents/workflows/`
- `.agents/skills/`

It also documents **global** customizations separately from workspace folders:

- global rules: `~/.gemini/GEMINI.md`
- global skills: `~/.gemini/antigravity/skills/<skill-folder>/`

The rules and skills docs together show a mixed model:

- `GEMINI.md` for top-level instructions
- `.agents/*` for workspace rules, workflows, and skills

That means the current vaultspec assumption that Antigravity has an
`AGENTS.md`-style top-level config file is not supported by the primary
sources.

This matters because vaultspec currently hard-codes Antigravity as:

- directory name: `.agent`
- config file: `AGENTS.md`
- scaffolded subfolders: `rules`, `skills`, `agents`

The official docs instead point to:

- workspace directory: `.agents`
- config file: `GEMINI.md`
- documented subfolders: `rules`, `workflows`, `skills`

No primary source in this research documents a user-managed `.agents/agents/`
folder for Antigravity.

### Comparison against vaultspec's current sync model

| Capability | Claude/Gemini/Current model | Codex fit | Antigravity fit |
| --- | --- | --- | --- |
| `rules_dir` accepts per-file markdown rules with `trigger: always_on` frontmatter | Yes for Claude and Gemini | No documented equivalent; Codex uses root-level `AGENTS.md` instead | Partially: `.agents/rules/` exists, but the docs do not document vaultspec's current frontmatter convention |
| `config_file` is markdown that can embed `@rules/...` includes | Yes for `CLAUDE.md` and `GEMINI.md` | No; Codex uses TOML config and separate `AGENTS.md` loading | Likely yes for `GEMINI.md`, but this should be revalidated before implementation |
| `system_file` can be materialized separately | Gemini only | No native equivalent | No dedicated Antigravity system file documented |
| `skills_dir/<name>/SKILL.md` | Yes | Yes, but path is `.agents/skills/` | Yes, path is `.agents/skills/` |
| `agents_dir` folder sync | Assumed by current `ToolConfig` | No; agent roles are in TOML | No documented agent-definition folder |

## Implications for implementation

### Codex

Codex does **not** fit the current rules/config pipeline cleanly.

- The closest current fit is existing `AGENTS.md` sync, because Codex natively
  consumes `AGENTS.md`.
- A dedicated `Tool.CODEX` would only make sense if vaultspec also wants to:
  - sync skills to `.agents/skills/`
  - optionally merge settings into `.codex/config.toml`
- Reusing the current `rules_dir` + `_generate_config()` path would be a poor
  fit because Codex has neither a native `rules/` directory nor a markdown
  config file that includes rule references.

### Antigravity

Antigravity appears to be modeled incorrectly in the current CLI.

- `DirName.ANTIGRAVITY = ".agent"` is likely wrong against current docs.
- `ToolConfig(..., config=FileName.AGENTS)` is likely wrong; docs point to
  `GEMINI.md`.
- `init_run()` scaffolds `rules`, `skills`, and `agents`, but the docs point to
  `rules`, `workflows`, and `skills`.

Before adding Codex, Antigravity's destination model should be corrected so
that the provider matrix reflects current official conventions.

## Recommended ADR decisions

1. Decide whether Codex should be modeled as:
   - `AGENTS.md` support only, with no dedicated `Tool.CODEX`, or
   - a first-class tool that adds `.agents/skills/` sync and optional TOML
     config integration.
2. Decide whether vaultspec will support non-markdown config mutation for
   `.codex/config.toml`.
3. Correct Antigravity's local model from `.agent` to the officially documented
   `.agents` workspace layout unless contradictory primary-source evidence is
   found.
4. Decide whether Antigravity needs a dedicated `workflows` resource in
   vaultspec, since the current resource model has no equivalent.
5. Revalidate whether Antigravity rule files require or tolerate vaultspec's
   current YAML frontmatter convention before any rollout.

## Bottom line

The current research supports the following conclusions:

- **Codex**: use `AGENTS.md` as the native rules/instruction bridge; do not
  assume a `CODEX.md` or `.codex/rules/` model.
- **Codex skills**: target `.agents/skills/`, not `.codex/skills/`.
- **Antigravity**: the current official workspace path is **`.agents/`**,
  not `.agent`; workspace rules, workflows, and skills live there, while the
  documented top-level instruction file remains **`GEMINI.md`**.
- **CLI readiness**: Antigravity's existing model should be corrected before
  Codex is added, otherwise the provider matrix will encode two different
  `.agents`/`.agent` assumptions at the same time.
