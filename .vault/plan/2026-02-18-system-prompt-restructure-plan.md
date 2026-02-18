---
# ALLOWED TAGS - DO NOT REMOVE - REFERENCE: #adr #audit #exec #plan #reference #research #<feature>
# Directory tag (hardcoded - DO NOT CHANGE - based on .vault/plan/ location)
# Feature tag (replace <feature> with your feature name, e.g., #editor-demo)
tags:
  - "#plan"
  - "#system-prompt"
# ISO date format (e.g., 2026-02-06)
date: 2026-02-18
# Related documents as quoted wiki-links (e.g., "[[2026-02-04-feature-adr]]")
related:
  - "[[2026-02-18-system-prompt-restructure-adr]]"
  - "[[2026-02-18-system-prompt-architecture-research]]"
---
<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields outside the YAML frontmatter above -->

# system-prompt restructure plan

Restructure `.vaultspec/system/` files for tool-agnostic composition, add Claude
behavioral rule generation, support explicit assembly ordering, and reduce shell
example bloat. Implements [[2026-02-18-system-prompt-restructure-adr]].

## Proposed Changes

The system/ directory currently contains 6 files, 2 of which (`base.md`,
`operations.md`) leak Gemini-specific tool names into what should be shared
content. Claude receives zero behavioral instructions. The assembled Gemini
SYSTEM.md is graded C+ due to ordering issues, bloat, and contradictions.

This plan addresses all P0 and P1 issues from the research audit by:

1. Splitting Gemini-specific content into properly tagged files
2. Adding Claude behavioral rule generation to the sync pipeline
3. Supporting explicit `order:` frontmatter for assembly control
4. Relocating verbose shell examples from system prompt to skill files
5. Fixing all small defects (typos, allcaps, forward-references)

## Tasks

- Phase 1: Content restructuring (system/ files)
    1. **Split `operations.md`**: Create `operations-gemini.md` with `tool: gemini`
       frontmatter. Move these Gemini-specific references out of `operations.md`:
       - Lines 7, 26, 32: `run_shell_command` -> generic "shell commands" in shared
       - Line 35: `save_memory` guidance -> move entirely to gemini file
       - Lines 41-42: `/help`, `/bug` commands -> move to gemini file
       - Line 64: `read_file` -> generic "file reading tool" in shared
       Keep in shared `operations.md`: Tone/Style (lines 14-22), Security (lines
       24-27 with generic language), Tool Usage parallelism note (line 31),
       Background Processes (line 33), Git Repository (lines 44-62), Final
       Reminder (lines 64-66 with generic language).
    2. **Clean `base.md`**: Remove "Jean-Claude" persona name from line 1.
       Replace with: "You are an interactive agent specializing in software
       engineering tasks." Move line 14 (`activate_skill` / `<activated_skill>`
       guidance) to `gemini.md`.
    3. **Add `order:` frontmatter** to `workflow.md`: `order: 20`. This ensures
       workflow routing appears early in assembly (after base + tool-specific).
    4. **Fix defects in `operations.md`**:
       - Remove `****` from line 33 ("If unsure, ask the user.****" -> "If
         unsure, ask the user.")
       - Replace line 5 allcaps with: "Follow these guidelines to avoid
         excessive token consumption."
       - Move "Do not use numbered lists" from base.md line 9 (buried in
         Comments rule) to operations.md Tone and Style section.
    5. **Fix forward-reference in `gemini.md`**: Line 64, change "per the
       Explain Critical Commands rule above" to "per the Explain Critical
       Commands rule" (remove "above").

- Phase 2: CLI pipeline changes (`cli.py`)
    1. **Update `_generate_system_prompt`** to support `order:` frontmatter.
       In step 5 (remaining shared parts), change the sort key from `name` to
       `(meta.get("order", 50), name)`. This sorts by order first (default 50),
       then alphabetically as tiebreaker. No changes needed for base.md (always
       first by hardcoded logic) or tool-specific parts (step 2).
    2. **Add `_generate_system_rules`** function. New function that assembles
       shared behavioral content (same parts that go into SYSTEM.md steps 1
       and 5, excluding tool-specific parts) into a single rule file. Returns
       the content as a string with rule-appropriate frontmatter:

       ```
       ---
       name: vaultspec-system
       trigger: always_on
       ---

       [assembled shared behavioral content]

       ```

    3. **Update `system_sync`** to also generate `.claude/rules/vaultspec-system.builtin.md`
       when a ToolConfig has `rules_dir` but no `system_file`. For each tool:
       - If `system_file` is set: generate SYSTEM.md (existing behavior)
       - If `system_file` is None AND `rules_dir` is set: generate the
         behavioral rule file into `rules_dir`
       This means Claude gets `vaultspec-system.builtin.md` in `.claude/rules/`
       and Gemini gets `SYSTEM.md` in `.gemini/` -- same content, different
       delivery mechanisms.
    4. **Update `sync_all`**: No changes needed -- `system_sync` already runs
       as part of `sync-all` and the new rule generation happens within it.

- Phase 3: Shell example relocation
    1. **Trim `gemini.md` shell examples**: Replace the detailed multi-line
       examples (lines 8-53, ~45 lines of code blocks) with concise one-line
       descriptions per tool. The section should be ~15 lines total:
       - `fd`: One-line description + key flags (`-e`, `-x`, `-X`, `-i`, `-s`)
       - `rg`: One-line description + key flags (`--type`, `-l`, `-0`, `-r`)
       - `sd`: One-line description + key flags (`-p`, `-s`, `$1/$2`)
       - `sg`: One-line description + key flags (`-p`, `-r`, `--interactive`)
       - Add note: "For detailed examples and usage patterns, activate the
         corresponding vaultspec skill (vaultspec-fd, vaultspec-rg, etc.)"
    2. **Enrich skill files**: Verify each skill file (`vaultspec-fd.md`,
       `vaultspec-rg.md`, `vaultspec-sd.md`, `vaultspec-sg.md`) contains the
       detailed examples currently in `gemini.md`. The `vaultspec-fd.md` skill
       already has good examples. Check and augment the others if needed with
       the pipeline examples (rg+sd combos, rg+sg combos) currently in gemini.md.

- Phase 4: Test updates
    1. **Update `test_sync_collect.py`** `TestGenerateSystemPrompt`:
       - `test_assembly_order`: Verify `order:` frontmatter affects ordering.
         Add a file with `order: 20` and verify it appears before the default
         (50) files.
       - Add `test_order_frontmatter_respected`: Create `workflow.md` with
         `order: 20` and `operations.md` with no order. Verify workflow content
         appears before operations content.
    2. **Update `test_sync_operations.py`** `TestSystemSync`:
       - Add `test_generates_behavioral_rule_for_claude`: Create system parts,
         run `system_sync`, verify `.claude/rules/vaultspec-system.builtin.md`
         exists with expected content.
       - Add `test_behavioral_rule_excludes_tool_specific`: Create base.md +
         gemini-tools.md (`tool: gemini`) + shared.md. Run system_sync. Verify
         the Claude rule file contains base + shared but NOT gemini-tools content.
       - Add `test_behavioral_rule_not_generated_without_rules_dir`: Verify
         ToolConfigs with no rules_dir and no system_file produce nothing.
    3. **Add `test_pipeline_config_excluded_from_rules`**: Verify files with
       `pipeline: config` are excluded from the behavioral rule generation
       (same as they are excluded from SYSTEM.md).
    4. **Run full test suite** to verify no regressions.

## Parallelization

- Phase 1 (content) and Phase 3 (skill enrichment) are independent and can
  be done in parallel.
- Phase 2 (CLI changes) depends on Phase 1 being complete (the new file
  structure must exist for testing).
- Phase 4 (tests) depends on Phase 2 being complete.
- Within Phase 1, steps 1-5 are independent and can be done in parallel.
- Within Phase 4, test writing can be parallelized across test files.

## Verification

**Success criteria:**

1. `cli.py system sync` generates:
   - `.gemini/SYSTEM.md` with tool-agnostic shared content + gemini-specific
     content, in correct order (base -> gemini -> workflow -> operations)
   - `.claude/rules/vaultspec-system.builtin.md` with tool-agnostic shared
     behavioral content only (no Gemini tool names)
2. Zero Gemini-specific tool names (`run_shell_command`, `save_memory`,
   `read_file`, `activate_skill`, `/help`, `/bug`) in any shared system/ file
   (files without `tool:` frontmatter).
3. All 87+ existing CLI tests pass.
4. New tests cover: order frontmatter, Claude rule generation, tool-specific
   exclusion from rules, pipeline:config exclusion from rules.
5. `gemini.md` shell section is <=15 lines (down from ~45).
6. No `****` typo, no allcaps warnings, no forward-references in assembled
   -utput.
7. Claude CLAUDE.md + rules contain: vaultspec pipeline bootstrap (frontmatter)
   - skill/subagent rules + behavioral mandates (new rule file).
8. `markdownlint` passes on all modified files.

**Manual verification:**

- Run `cli.py system show` and `cli.py config show` to inspect the assembly.
- Read the generated `.gemini/SYSTEM.md` to verify Frankenstein issues are
  resolved (coherent flow, no contradictions, workflow routing early).
- Read the generated `.claude/rules/vaultspec-system.builtin.md` to verify
  it contains meaningful behavioral instructions without Gemini-specific content.
- Diff the assembled outputs before/after to confirm no accidental content loss.
