---
tags:
  - "#exec"
  - "#uncategorized"
date: 2026-02-07
related:
  - "[[2026-02-07-dispatch-phase3-plan]]"
---
# Step 2: Standardize Agent Frontmatter Schema

## Changes

Audited all 9 agent files in `.rules/agents/*.md` and standardized frontmatter to include the required fields for Phase 3 resource exposure.

### Fields Added

All agents already had `tier` and `description` (required). Added `mode` and `tools` (optional) to every agent:

| Agent | tier | mode | tools |
|---|---|---|---|
| adr-researcher | HIGH | read-only | Glob, Grep, Read, WebFetch, WebSearch, Bash |
| code-reviewer | HIGH | read-only | Glob, Grep, Read, Bash |
| complex-executor | HIGH | read-write | Glob, Grep, Read, Write, Edit, Bash |
| docs-curator | MEDIUM | read-write | Glob, Grep, Read, Write, Edit, Bash |
| french-croissant | LOW | read-only | Read |
| reference-auditor | MEDIUM | read-only | Glob, Grep, Read, Bash |
| simple-executor | LOW | read-write | Glob, Grep, Read, Write, Edit, Bash |
| standard-executor | MEDIUM | read-write | Glob, Grep, Read, Write, Edit, Bash |
| task-writer | HIGH | read-write | Glob, Grep, Read, Write, Edit, Bash |

### Additional Fix

- `docs-curator.md`: description value was unquoted YAML string; wrapped in double quotes for consistency with all other agents.

### Files Modified

- `.rules/agents/adr-researcher.md`
- `.rules/agents/code-reviewer.md`
- `.rules/agents/complex-executor.md`
- `.rules/agents/docs-curator.md`
- `.rules/agents/french-croissant.md`
- `.rules/agents/reference-auditor.md`
- `.rules/agents/simple-executor.md`
- `.rules/agents/standard-executor.md`
- `.rules/agents/task-writer.md`

No persona content was modified -- only frontmatter keys were added.
