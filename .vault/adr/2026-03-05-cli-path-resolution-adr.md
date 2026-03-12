---
tags:
  - "#adr"
  - "#cli-architecture"
date: 2026-03-05
related:
  - "[[2026-03-05-cli-architecture-audit]]"
---

# ADR: CLI Path Resolution & Provider Initialization Overhaul

## Status
Accepted

## Context
The current VaultSpec CLI utilizes split paths for resolving its execution environment: --root (which maps to where outputs like .vault are stored) and --content-dir (which maps to where configuration like .vaultspec is read from). This terminology is highly confusing to users and creates complex backend logic. Furthermore, there is no master --target flag that allows a user to point the CLI at a specific project folder globally.

Additionally, the initialization command (init) fails to scaffold the necessary provider directories (.gemini, .claude, .agents), relying on lazy creation during sync-all. 

Finally, a known conflict exists: Gemini CLI reads from both .gemini/rules/ and .agents/rules/. When VaultSpec syncs rules to both destinations, Gemini CLI triggers duplicate rule override warnings.

## Decisions

### 1. Deprecate --root and --content-dir in Favor of --target
We will completely drop support for the split --root and --content-dir flags across the entire CLI. They will be replaced by a single, global --target <absolute_path> flag.

* **Behavior:**
  * If --target is set, the CLI will resolve both the output root (.vault) and the content root (.vaultspec) as direct children of {target}.
  * If --target is omitted, it will default to Path.cwd().
  * The backend workspace resolution engine (src/vaultspec/config/workspace.py) will be simplified to enforce that .vault and .vaultspec are mandated to live side-by-side within the target directory. 
  * Git discovery (.gt bare repos, linked worktrees) will originate from the --target path, not the physical cwd, ensuring git-aware features continue to work against remote targets.

### 2. Eager Provider Initialization in init
The aultspec init command must be updated to fully bootstrap the ecosystem, not just the VaultSpec internals.

* **Behavior:**
  * init will create the .vaultspec framework folder, the .vault scaffold folder, AND the provider folders (.gemini, .claude, .agents etc.).
  * We will introduce a --providers flag to init (e.g., --providers=gemini,claude,agents). The default behavior will be ll.

### 3. Mitigate Gemini CLI Duplicate Rule Loading
We will implement an active suppression mechanism during the synchronization phase to prevent duplicate rules in Gemini CLI.

* **Behavior:**
  * The sync pipeline (e.g., src/vaultspec/core/rules.py) will include a check: If the .agents/rules directory (Antigravity provider) is configured and active for the workspace, the sync engine will deliberately skip populating .gemini/rules. 
  * This guarantees that Gemini CLI will only read the rules once (via the .agents fallback pathway), eliminating the spammy console warnings while preserving full functionality.

## Consequences

* **Positive:** Massive reduction in cognitive load for end-users regarding CLI targeting. A much more reliable and complete "first run" experience out of the box via init. A cleaner, warning-free console experience for Gemini users.
* **Negative:** Breaking change for any external scripts or CI/CD pipelines that previously relied on the split --root or --content-dir architecture. They must be updated to use --target.