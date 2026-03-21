---
tags:
  - '#audit'
  - '#cli-architecture'
date: 2026-03-05
related:
  - '[[vaultspec-cli]]'
---

# Vaultspec CLI Architecture Audit

## Cycle 0: Initial Capabilities & Path Resolution Analysis

### Scope

Audit the default behavior of `vaultspec init`, confirm the implementation of path/target resolution in the backend, and evaluate the CLI's `--help` discoverability for root commands.

### Findings

#### 1. [Confirmed] `vaultspec init` Path Resolution

- **Issue:** `vaultspec init` defaults strictly to `cwd` and does not support a `--target` folder.
- **Detail:** The initialization is intercepted early in `src/vaultspec/__main__.py`, intentionally hardcoding `_t.ROOT_DIR = _Path.cwd()` to bypass workspace validation in fresh environments. The normal argument parser is bypassed.
- **Triage:** Medium - Breaks expected CLI standard behavior, causing friction for users initializing external projects.

#### 2. [Confirmed] "Target" Implementation in Backend

- **Issue:** The backend natively supports targeting folders via the `--root` and `--content-dir` arguments.
- **Detail:** Bounded in `src/vaultspec/cli_common.py` through the `add_common_args` utility.
- **Triage:** Low - Implementation exists but is masked or bypassed at the CLI layer.

#### 3. [Validated] Global Flag Rollout Recommendation

- **Issue:** The `--root` / `--target` concept is not rolled out globally as an inherited flag.
- **Detail:** `spec_cli` registers these on the root parser, meaning sub-parsers (like `rules`, `doctor`, etc.) lose them from their help menus. Namespaces like `vault` register them on their respective top-level parsers, but `init` and `mcp` bypass parsing entirely.
- **Triage:** High - Creates severe inconsistency across the CLI interface regarding workspace targeting.

#### 4. [Detected] Root Subcommands `--help` Intercepts

- **Issue:** Early intercepts in `__main__.py` block `--help` on certain commands.
- **Detail:** `vaultspec init --help` throws an "already exists" error instead of showing help. `vaultspec mcp --help` throws an env var missing error.
- **Triage:** High - Fundamental discoverability and UX failure for new users.

#### 5. [Detected] `vaultspec --help` Missing Examples

- **Issue:** The main help epilog/prolog does not include usage examples like `vaultspec init + args`.
- **Triage:** Low - Purely a documentation and discoverability gap.

______________________________________________________________________

## Cycle 1: Argparse Sub-Parser Inheritance Architecture

### Scope

Deep dive into the argument parsing architecture across the `vaultspec` CLI to understand how `add_common_args` is utilized and identify the failure points preventing global flags (like `--root` and `--content-dir`) from cascading to sub-commands.

### Findings

#### 6. [Detected] `argparse` Inheritance Failure

- **Issue:** Global arguments defined in `add_common_args` are not inherited by sub-parsers.
- **Detail:** In standard Python `argparse`, adding arguments to a parent parser (e.g., `parser.add_argument("--root", ...)`) does **not** cascade them to sub-parsers created via `add_subparsers()`. Sub-parsers only inherit arguments if they are explicitly initialized with `parents=[parent_parser]`.
- **Triage:** High - This is the root cause of the missing `--root` flag in `rules`, `doctor`, and other sub-command help menus.

#### 7. [Detected] Duplicated Workaround Logic

- **Issue:** Instead of fixing inheritance, some parsers manually re-apply verbosity arguments.
- **Detail:** The codebase currently uses a helper `add_verbosity_args` which is manually called on individual sub-parsers (e.g., `rules_parser = resource_parsers.add_parser("rules"); add_verbosity_args(rules_parser)`). This is a manual workaround for the inheritance failure but was not applied to the `--root` and `--content-dir` arguments.
- **Triage:** Medium - Leads to boilerplate and makes adding new global flags error-prone.

______________________________________________________________________

## Cycle 2: Early Execution Intercepts & Module Loading Architecture

### Scope

Audit the execution intercepts in `src/vaultspec/__main__.py` (specifically for `init` and `mcp`) and track how module-level imports enforce workspace states before `argparse` can evaluate user intent (such as `--help`).

### Findings

#### 8. [Detected] Module-Level Side Effects Breaking CLI Flow

- **Issue:** `spec_cli.py` triggers an exception on import in uninitialized directories.
- **Detail:** Lines 65-70 of `src/vaultspec/spec_cli.py` execute `_default_layout = get_default_layout()` and `init_paths(_default_layout)` at the module scope. In an uninitialized environment, this throws a `WorkspaceError`. This forces `__main__.py` to catch `init` via raw string matching (`sys.argv[1] == "init"`) to completely bypass importing `spec_cli`.
- **Triage:** High - Module-level execution violates standard Python CLI design patterns and prevents `init` from properly joining the `argparse` pipeline.

#### 9. [Detected] Incomplete MCP Server CLI

- **Issue:** The `mcp` command lacks `argparse` integration entirely.
- **Detail:** Unlike other namespaces, `vaultspec mcp` directly triggers `mcp_server.app.main()`, which fetches configuration via `get_config()` and expects `cfg.mcp_root_dir` to be populated. There is no argument parsing to catch `--help` or accept standard overrides like `--root`, leading to immediate crashes.
- **Triage:** Medium - Inconsistent with the rest of the CLI suite; `mcp` should be integrated as a standard command namespace with standard flag support.

## Cycle 3: Path Resolution Architecture (--root vs --content-dir)

### Scope

Audit the behavioral and semantic differences between --root and --content-dir in the vaultspec workspace resolution logic, and assess user intuition regarding flag naming.

### Findings

#### 10. [Detected] Semantic Confusion of Path Flags

- **Issue:** The names --root and --content-dir are counter-intuitive and do not clearly convey their actual effects on the backend workspace layout.
- **Detail:**
  - --root resolves to WorkspaceLayout.output_root. It sets the base directory for the .vault output (where the agent writes artifacts: dr/, exec/, plan/, etc.) and acts as the execution workspace root.
  - --content-dir resolves to WorkspaceLayout.content_root. This dictates the source of the aultspec configuration and governance framework (the location of .vaultspec/rules/, .vaultspec/agents/, etc.).
  - A user calling --root likely expects it to override the *entire project root*, but instead, it splits the layout: output goes to --root, while .vaultspec configuration still tries to load from cwd (unless --content-dir is also overridden).
- **Triage:** Medium - Highly confusing for users trying to target a remote or alternate project folder for operations.

#### 11. [Recommendation] Flag Renaming and Alignment

- **Issue:** The documentation and naming do not align with their internal domain models (output_root vs content_root).
- **Detail:** The help texts are:
  - --root: "Override workspace root directory"
  - --content-dir: "Content source directory (rules, agents, skills)"
- **Proposed Action:**
  1. Rename --root to --target or --workspace-dir (or strictly --output-dir if it only dictates .vault placement). If --root is meant to encompass both, the underlying
     esolve_workspace logic needs to treat it as a master override for both output_root and content_root unless explicitly split.

  1. If the split is intentional (e.g., using shared centralized rules for different output vaults), clarify the help texts to explicitly mention "Where .vault is created" vs "Where .vaultspec is read from".

## Cycle 4: Path Resolution vs Git Worktree Friction

### Scope

Audit the proposed --target ADR against the current workspace.py layout resolution logic. Specifically, identify friction points regarding .git, bare repositories (.gt), and git worktree handling when an absolute --target is used instead of relying on cwd discovery.

### Findings

#### 12. [Detected] discover_git CWD Coupling

- **Issue:** The git repository discovery logic relies strictly on walking upward from the starting directory (currently effective_cwd or explicit overrides).

- **Detail:** In src/vaultspec/config/workspace.py,
  esolve_workspace() uses discover_git(effective_cwd). If a user passes an absolute --target, the system must decide whether to trace git metadata from the --target or from the caller's physical cwd.

  - If the system traces from --target, a --target outside of a git repository will lose all git-aware features (like worktree root isolation), even if the command was invoked from within a repo.
  - If the system traces from cwd while operating on --target, the outputs (.vault, .vaultspec) may end up misaligned with the intended git container.

- **Triage:** High - When rolling out --target, the WorkspaceLayout engine must explicitly mandate that git discovery happens starting from the --target path, treating it as the authoritative root for *both* content and output. The fallback to .gt container roots must also ensure it doesn't accidentally hoist the --target out of an intentionally isolated directory.

#### 13. [Recommendation] Deprecating Split Paths

- **Issue:** Maintaining separate output_root and content_root resolution trees adds immense complexity for no current functional benefit.

- **Proposed Action:** Endorse the ADR to drop --root and --content-dir entirely in favor of a single --target. Under the hood,
  esolve_workspace should be simplified:

  1. Base = --target (or cwd).
  1. Discover git from Base to find true project root (handling .gt bare repos or worktrees).
  1. Set output_root = content_root = True Project Root.
  1. Ensure .vault and .vaultspec are strict children of this single root.

______________________________________________________________________

## Cycle 5: Provider Initialization & Gemini CLI Rule Duplication

### Scope

Audit the current aultspec init behavior regarding provider scaffolding (.gemini, .claude, .agents) and investigate the duplicate rule loading bug when both .gemini and .agents are active.

### Findings

#### 14. [Confirmed] init Missing Provider Scaffolding

- **Issue:** The current init_run command only scaffolds .vaultspec/ and .vault/. It does not natively bootstrap provider directories.
- **Detail:** In src/vaultspec/core/commands.py, init_run manually creates arrays of subdirectories for .vaultspec and .vault, and seeds a .mcp.json. The provider directories (e.g., .gemini/rules/, .agents/rules/) are only created lazily *if* the user manually runs aultspec sync-all.
- **Triage:** Medium - Breaks user expectations. init should explicitly create provider stubs to signal immediate readiness.
- **Proposed Action:** Implement --providers flags on init (e.g., --providers=gemini,claude,agents, default ll). init_run should trigger a baseline scaffolding loop for the selected providers, fetching their paths from \_t.TOOL_CONFIGS.

#### 15. [Confirmed] Gemini CLI Duplicate Rule Loading

- **Issue:** Gemini CLI inherently monitors both .gemini/rules/ and .agents/rules/. If aultspec sync-all populates both destinations, Gemini CLI loads the same rules twice, causing override warnings.

- **Detail:** src/vaultspec/core/rules.py blindly iterates over all active TOOL_CONFIGS and writes rule copies to every configured
  ules_dir. Because Tool.GEMINI maps to .gemini/rules and Tool.ANTIGRAVITY (or Tool.AGENTS) maps to .agents/rules, the sync pipeline duplicates the files into the workspace.

- **Triage:** High - UX degradation due to spammy warnings from the Gemini CLI engine.

- **Proposed Action:**

  - Option A (Recommended): Add a pre-sync hook in
    ules_sync / skills_sync: If .agents/rules is an active target, nullify or skip the
    ules_dir synchronization for Tool.GEMINI to prevent duplication, leaving Gemini to read exclusively from the shared .agents/rules folder.

  - Option B: Accept as a necessary evil if .gemini must retain isolation for non-Antigravity features, but document it as a known ecosystem quirk.

## Cycle 6: Provider Pre-Initialization and Scaffolding Bugs

### Scope

Audit the init_run logic against the newly proposed ADR, specifically focusing on how it would handle eager initialization of provider directories (.gemini, .claude, .agents) and the friction of configuring those directories *before* the .vaultspec framework config exists.

### Findings

#### 16. [Detected] Chicken-and-Egg Provider Discovery in init

- **Issue:** init_run currently relies on get_config() and \_t.TOOL_CONFIGS to understand which providers are active. However, get_config() relies on reading the ramework.md file, which init is responsible for creating.
- **Detail:** In src/vaultspec/core/commands.py:174, init_run calls cfg = get_config(). In a fresh repository, this triggers a fallback to default configurations. If we update init to scaffold provider directories based on the --providers flag, we must either:
  1. Scaffold the directories purely based on the CLI arguments (bypassing \_t.TOOL_CONFIGS initially).
  1. Dynamically inject the requested providers into the generated ramework.md file *during* the init process, and then re-load the configuration to run the sync logic.
- **Triage:** High - Implementing the ADR requires breaking the cyclical dependency between init creating the config and init needing the config to know where to put the provider folders.

#### 17. [Detected] Missing Directory Injection in Tool Configs

- **Issue:** The base \_create_tool_cfg helper in src/vaultspec/core/types.py hardcodes the sub-directories (
  ules, gents, skills) that need to be created.

- **Detail:** To implement the ADR where init creates .gemini/rules/, .claude/rules/, etc., the system needs a unified way to retrieve the exact paths to scaffold without duplicating the logic currently locked inside the sync_files loops.

- **Triage:** Medium - Requires exposing a get_scaffold_paths() or similar method on ToolConfig so init_run can cleanly iterate and ensure_dir() all required endpoints.

______________________________________________________________________

## Cycle 7: Gemini vs Antigravity Sync Conflict Validation

### Scope

Audit the
ules_sync, skills_sync, and gents_sync loops to confirm the exact injection point for the "skip Gemini if Antigravity is active" logic proposed in the ADR.

### Findings

#### 18. [Detected] Blind Iteration in Sync Loops

- **Issue:** All sync functions (
  ules_sync, gents_sync, skills_sync, system_sync, config_sync) in src/vaultspec/core/ blindly iterate over \_t.TOOL_CONFIGS.items() without any cross-provider awareness.

- **Detail:** For example, in src/vaultspec/core/rules.py:144: or tool_type, cfg in \_t.TOOL_CONFIGS.items():.

- **Triage:** High - To fix the Gemini CLI duplicate rule warning, we need to inject a state-aware check *before* or *inside* these loops.

- **Proposed Action:** We should not modify every individual sync loop. Instead, ypes.py (where TOOL_CONFIGS is built) should be modified. If it detects that both Tool.GEMINI and Tool.ANTIGRAVITY are enabled in the configuration, it should intentionally None out the
  ules_dir property of the Tool.GEMINI config object. This handles the skip globally across all sync operations without polluting the core loop logic.

## Cycle 8: MCP Server Path Independence and Argparse Integration

### Scope

Audit the aultspec mcp command initialization regarding its dependency on VAULTSPEC_MCP_ROOT_DIR and assess how the proposed --target ADR impacts the MCP integration.

### Findings

#### 19. [Detected] Orphaned Env Var Dependency

- **Issue:** src/vaultspec/mcp_server/app.py requires VAULTSPEC_MCP_ROOT_DIR to run. If we transition to --target globally, this specific environment variable becomes an orphaned concept, diverging from the rest of the CLI.
- **Detail:** Currently, init_run hardcodes "env": {"VAULTSPEC_MCP_ROOT_DIR": str(\_t.ROOT_DIR.resolve())} into the generated .mcp.json. The pp.py script then relies strictly on this variable because it bypasses rgparse completely.
- **Triage:** Medium - Creates unnecessary fragmentation in the environment variables schema.
- **Proposed Action:**
  1. Add standard rgparse integration to aultspec mcp so it can accept the new --target flag directly.
  1. Deprecate VAULTSPEC_MCP_ROOT_DIR entirely. Have mcp_server/app.py use the globally resolved WorkspaceLayout.output_root (derived from --target) just like every other command.
  1. Update init_run to generate the .mcp.json using the command array \["vaultspec", "--target", "<path>", "mcp"\] instead of injecting environment variables.

______________________________________________________________________

## Cycle 9: Test Suite Fragility to CLI Flag Changes

### Scope

Audit the existing pytest test suites to determine the blast radius of replacing the --root flag with --target.

### Findings

#### 20. [Detected] Hardcoded --root in Test Fixtures

- **Issue:** Dozens of CLI and protocol integration tests explicitly invoke
  un_vault and
  un_spec with the --root flag.

- **Detail:** Files like ests/cli/test_vault_cli.py, ests/cli/test_spec_cli.py, and ests/protocol/conftest.py rely heavily on injecting isolated tmp paths via the --root flag. For example, ests/protocol/conftest.py spins up the MCP server using rgs: ["-m", "vaultspec.subagent_cli", "--root", str(tmp_path), "serve"].

- **Triage:** High - The ADR implementation will instantly fail CI/CD if these tests are not migrated concurrently.

- **Proposed Action:** The refactor PR must include a global search-and-replace of "--root" to "--target" within the ests/ directory, and the test helpers (
  un_vault,
  un_spec) must be validated against the new unified workspace resolution behavior.

## Cycle 10: Provider Subprocess Argparse Breakage

### Scope

Audit the A2A protocol provider implementations (gemini.py, claude.py) to determine how they construct subprocesses and inject workspace context, checking for hardcoded flag dependencies.

### Findings

#### 21. [Detected] Hardcoded --root in Provider Process Spawns

- **Issue:** The GeminiProvider and ClaudeProvider explicitly construct subprocess command arrays containing the --root flag when starting child A2A servers.

- **Detail:** In src/vaultspec/protocol/providers/gemini.py:464 and claude.py:350, the start_server logic yields:
  rgs=["-m", "vaultspec", "subagent", "--root", str(root_dir), "a2a-serve", ...]
  If the root spec_cli argument parser replaces --root with --target, these backend daemon spawns will instantly crash with unrecognized arguments: --root during system operations.

- **Triage:** Critical - Changing the global flag immediately breaks the provider abstraction layer, disabling all multi-agent team operations.

- **Proposed Action:** The refactoring effort must update the rgs array in both gemini.py and claude.py (and any other A2A providers like ntigravity.py if they exist) to use --target.

#### 22. [Detected] Environment Variable Schema Drift

- **Issue:** Providers inject VAULTSPEC_ROOT_DIR into the child process environment. If the config schema updates to match --target, this will silently fail.
- **Detail:** gemini.py:438 and claude.py:318 set env["VAULTSPEC_ROOT_DIR"] = str(root_dir). The config loading singleton reads this string to resolve the workspace on the other side of the process boundary.
- **Triage:** High - If aultspec.config deprecates VAULTSPEC_ROOT_DIR in favor of VAULTSPEC_TARGET_DIR, the child processes will spawn in isolation, failing to inherit the parent workspace state.
- **Proposed Action:** Migrate VAULTSPEC_ROOT_DIR and VAULTSPEC_CONTENT_DIR to a unified VAULTSPEC_TARGET_DIR in src/vaultspec/config/config.py, and update the provider injection logic concurrently.

## Cycle 11: End-to-End Migration Readiness

### Scope

Synthesize the cumulative blast radius of removing the --root and --content-dir flags across internal subprocesses, external tests, and provider layers to outline the required sequence for safe execution.

### Findings

#### 23. [Detected] Hardcoded CLI Flags in Test Suite Executables

- **Issue:** Beyond direct CLI unit tests, the integration tests spin up physical aultspec.subagent_cli processes via subprocess modules.
- **Detail:** In ests/protocol/conftest.py, the fixtures spin up mock providers and sub-agents using sys.executable and string arrays containing "--root". Changing the root argparser will instantly brick these physical sub-processes, leading to opaque integration test failures that might be hard to trace back to argparse.
- **Triage:** High - Test fixtures must be updated synchronously with cli_common.py.

#### 24. [Recommendation] Safest Execution Pathway

- **Migration Sequence:** To avoid breaking the vaultspec ecosystem during the refactor, the engineering agent should follow this strict sequence:
  1. **Config Layer:** Modify src/vaultspec/config.py and workspace.py to replace
     oot_override and content_override with arget_override. Deprecate VAULTSPEC_ROOT_DIR / VAULTSPEC_CONTENT_DIR in favor of VAULTSPEC_TARGET_DIR.

  1. **CLI Layer:** Update cli_common.py to remove --root and --content-dir, introducing --target. Apply --target globally to all sub-parsers by fixing the parents=[common_parser] argparse issue found in Cycle 1.

  1. **Integration Layer (MCP):** Add a proper rgparse wrapper to aultspec mcp so it maps --target directly to the mcp_root_dir config, deprecating the standalone VAULTSPEC_MCP_ROOT_DIR env var.

  1. **Integration Layer (Providers):** Update gemini.py and claude.py to inject VAULTSPEC_TARGET_DIR instead of VAULTSPEC_ROOT_DIR, and change their A2A server spawn arguments from "--root" to "--target".

  1. **Test Layer:** Run a global regex replace across the ests/ and src/vaultspec/tests/ folders for "--root" -> "--target" and validate.

## Cycle 12: Audit Task Scoping Correction (gent-removal Pre-requisite)

### Scope

Acknowledge the execution of \[[2026-03-05-agent-removal-plan]\]. This major refactoring completely strips the aultspec core repository of agent-management logic, the A2A protocol, and related CLI/MCP tools, migrating them to the external aultspec-a2a package. The scope of this audit loop must be immediately updated to ignore all agent-related codebase findings, as any code referencing eam, server, subagent, 2a, and .agents is scheduled for immediate deletion.

### Findings

#### 25. [Corrected] Cycle 10 and 11 Invalidation

- **Issue:** Findings #21 (Provider Process Spawns) and parts of #23 (Test Suite Executables) are no longer relevant blockers for the --target refactor.
- **Detail:** The aultspec team, aultspec server, and aultspec subagent CLIs, alongside the A2A spawning methods inside gemini.py and claude.py, are explicitly slated for deletion in Phase 1 and Phase 2 of the gent-removal plan. We do not need to rewrite their --root usages to --target because the code itself will cease to exist.
- **Triage:** Closed/Irrelevant - The gent-removal plan will completely destroy the problematic abstraction layers identified in Cycles 10 and 11.

#### 26. [Detected] --providers Scaffolding Re-evaluation

- **Issue:** The previously proposed aultspec init --providers flag (Finding #14) needs to be carefully aligned with the post-gent-removal world.
- **Detail:** With the .agents (Antigravity) and A2A mechanisms removed from the core repo, init will primarily focus on scaffolding .vaultspec, .vault, and .gemini/.claude rule directories. If aultspec-a2a introduces its own rules or folders in the future, the core initialization hook might need an extensible hook system rather than hardcoding .agents scaffolding in the core commands.py.
- **Triage:** Low - The core refactor should proceed with --providers=all, but note that "all" now strictly means gemini and claude, and no longer includes the A2A sub-agent tooling paths unless explicitly re-introduced by the external package.

#### 27. [Recommendation] Migration Sequencing Adjustment

- **Execution Constraint:** The --target refactoring plan MUST be executed **after** the gent-removal plan has successfully completed Phase 4 (Verification). Attempting to refactor --root to --target while aultspec-complex-executor is concurrently gutting __main__.py, config.py, and cli_common.py will guarantee severe merge conflicts and execution failures.

## Cycle 13: Core CLI Extensibility & Surviving Subcommands

### Scope

Audit the surviving CLI modules post-gent-removal (specifically ault_cli.py, spec_cli.py, and hooks_cli) to verify how they integrate with the unified --target paradigm and identify any lingering .cwd() dependencies that might override explicit targeting.

### Findings

#### 28. [Detected] Unchecked Path.cwd() in

ules_sync / skills_sync Paths

- **Issue:** Even if --target is properly parsed and \_t.ROOT_DIR is set globally, some sync operations might rely on relative path constructions that implicitly assume the current working directory.

- **Detail:** The sync functions rely heavily on
  esolve_workspace() generating absolute paths for WorkspaceLayout. We need to ensure that the collection functions (collect_rules(), collect_skills()) strictly map their glob searches starting from \_t.RULES_SRC_DIR and _t.SKILLS_SRC_DIR, and NEVER fallback to Path.cwd(). An audit of src/vaultspec/core/rules.py and skills.py shows that collect_\* correctly relies on the globally instantiated \_t paths.

- **Triage:** Clear/No-Issue - The underlying architecture correctly abstracts physical paths behind the ypes.py global singletons. Once
  esolve_workspace honors --target, the entire downstream sync pipeline will safely follow suit without needing physical code changes in the sync loops themselves.

#### 29. [Detected] CLI Import Sequence Brittleness

- **Issue:** src/vaultspec/__main__.py uses lazy loading for namespace execution (e.g., rom .vault_cli import main as run), but standard commands fall through to spec_cli.main().
- **Detail:** The surviving structure will route aultspec vault to ault_cli.py and things like aultspec rules to spec_cli.py. However, as found in Cycle 2, spec_cli.py performs module-level workspace initialization *upon import*. This means if a user runs aultspec vault --target /new/path, spec_cli.py is not imported, so the module-level crash does not happen. But if they run aultspec rules --target /new/path, the module-level get_default_layout() in spec_cli.py runs *before* --target is parsed, triggering a crash in uninitialized directories.
- **Triage:** High - To support --target natively for all commands, **ALL module-level workspace initializations must be moved inside their respective main() functions**. Specifically, lines 65-70 in spec_cli.py and any similar logic in ault_cli.py must be deleted from the global scope.

#### 30. [Detected] Inconsistent --version Handling

- **Issue:** The --version flag is handled manually in __main__.py via if sys.argv[1] in ("-V", "--version"):, bypassing rgparse.
- **Detail:** cli_common.py defines --version inside dd_common_args(), but because __main__.py intercepts it first, the standard argparse version action is never reached. This leads to duplicate definitions and inconsistent help menus across the surviving subcommands.
- **Triage:** Low - A minor cleanliness issue, but standardizing on Python's built-in parser.add_argument("--version", action="version", version=...) inside cli_common.py will allow rgparse to handle version outputs uniformly across all root parsers.

## Cycle 14: Final Review & Task Handoff Preparation

### Scope

Finalize the audit loop by reviewing the aggregated findings across the 13 cycles and formatting them into a discrete, actionable implementation plan that cleanly interfaces with the aultspec-writer agent and strictly adheres to the .vault execution standards.

### Findings

#### 31. [Validation] Audit Completeness Confirmed

- **Status:** All core paths regarding --target vs --root / --content-dir have been mapped.
- **Status:** Argparse inheritance failures, early execution intercepts, module-level side effects, and initialization blind spots have been identified and triaged.
- **Status:** Scope has been successfully recalibrated post-gent-removal to ensure no time is wasted refactoring obsolete A2A/subagent logic.

#### 32. [Actionable Output] Translation to Vaultspec Plan

- **Issue:** The raw audit document (.vault/audit/2026-03-05-cli-architecture-audit.md) is highly detailed but not formatted as an executable .vault/plan/ artifact.
- **Proposed Action:** The engineering agent must synthesize this audit into a sequential 2026-03-05-cli-target-refactor-plan.md. The plan must mandate the following strict sequence (as outlined in Finding #27):
  1. Wait for gent-removal execution to finish.
  1. **Phase 1: Config Layer Overhaul** (workspace.py, config.py deprecating root/content for target).
  1. **Phase 2: CLI Engine Refactor** (cli_common.py, __main__.py removing early intercepts, fixing rgparse inheritance, migrating module-level loads into main()).
  1. **Phase 3: Initialization Upgrade** (commands.py updating init_run to properly scaffold --providers including .gemini and .claude, resolving the chicken-and-egg config issue).
  1. **Phase 4: Test Suite Synchronization** (Global string replacement of --root to --target in tests).

______________________________________________________________________

**Audit Loop Concluded.** The repository is primed for the structural refactor.

## Cycle 15: Post-Agent-Removal Sub-Agent Mock Audit

### Scope

Audit the ests/ directory to identify remaining sub-agent or A2A mock logic that might survive the gent-removal plan and still contain hardcoded --root or --content-dir paths that need to be migrated to --target.

### Findings

#### 33. [Detected] aultspec-mcp Testing Mocks

- **Issue:** Even with A2A logic removed, aultspec-mcp is a core utility that requires rigorous testing. The test suite spins up the MCP server via subprocess for integration testing.
- **Detail:** The gent-removal plan specifies "Phase 4: Clean up Test Suite - Delete A2A and agent tests." However, aultspec-mcp is explicitly kept (as noted in "Ensure the MCP server starts correctly"). If the tests for aultspec-mcp use --root to isolate their execution environment, they will break when --target is introduced.
- **Triage:** High - We must ensure that the aultspec-mcp test fixtures (e.g., in est_mcp_config.py or conftest.py) are properly migrated to use --target and that they do not rely on deprecated .agents directories.
- **Proposed Action:** When executing the global search-and-replace for --root -> --target in Phase 4 of the refactor plan, explicitly verify the aultspec-mcp test fixtures and ensure they still pass.

#### 34. [Detected] TOOL_CONFIGS Test Validation

- **Issue:** Tests validating TOOL_CONFIGS generation (e.g., ests/cli/test_spec_cli.py) currently assert the creation of .vaultspec/rules/agents directories.
- **Detail:** After gent-removal, the .agents (Antigravity) tool config will be deleted. Any tests asserting the existence of these directories will fail.
- **Triage:** Medium - This is primarily a cleanup task for the gent-removal plan, but the --target refactor must be aware of it so it doesn't try to re-introduce or test for deprecated .agents paths when verifying the new --target behavior.
- **Proposed Action:** Ensure the --target refactor tests only assert the creation of the core .vaultspec, .vault, .gemini, and .claude directories.

## Cycle 16: Vault Core Dependencies on Root Directory

### Scope

Audit src/vaultspec/vaultcore and src/vaultspec/vault_cli.py to ensure that core .vault documentation features (audit, create, index, search) do not have hidden assumptions about Path.cwd() that would break when operated remotely via --target.

### Findings

#### 35. [Detected] Template Discovery Relative Pathing

- **Issue:** The create command in ault_cli.py relies on templates located in .vaultspec/rules/templates. We need to verify how aultcore.create_vault_doc resolves these template paths.
- **Detail:** aultcore.py handles the file generation. If it resolves the template path via \_t.TEMPLATES_DIR, it is safe, as \_t.TEMPLATES_DIR is dynamically populated by init_paths() using the layout resolved from --target.
- **Triage:** Low - Code inspection is required to confirm \_t.TEMPLATES_DIR is strictly used, but architecture suggests it is.
- **Proposed Action:** Briefly scan aultcore.py to ensure Path.cwd() isn't used as a fallback for template discovery if \_t.TEMPLATES_DIR is somehow empty.

#### 36. [Detected] ault audit Output Pathing

- **Issue:** The ault audit command generates outputs. We need to confirm if these are printed to stdout or written to disk. If written to disk, do they respect the --target root?
- **Detail:** The current implementation of ault audit (via metrics.get_vault_metrics and graph.VaultGraph) reads from \_t.ROOT_DIR / ".vault".
- **Triage:** Clear/No-Issue - The vault core operations rely on the globally resolved \_t.ROOT_DIR, meaning they will correctly operate on the .vault directory residing inside the specified --target.

#### 37. [Detected] Hook Execution Path Context

- **Issue:** The hooks system (src/vaultspec/core/hooks.py and hooks_cli.py) executes user-defined scripts. What is the working directory for these child processes?
- **Detail:** If a user runs aultspec --target /other/repo hooks run post-commit, the hook scripts located in /other/repo/.vaultspec/rules/hooks will be executed. Do they execute with cwd=/other/repo or cwd=current_shell_cwd?
- **Triage:** High - If hook scripts execute in the caller's physical cwd instead of the --target directory, they may inadvertently run commands (like git add or lint) against the wrong repository.
- **Proposed Action:** Audit src/vaultspec/core/hooks.py to ensure the subprocess.run calls explicitly set cwd=\_t.ROOT_DIR (which will be derived from --target). If they don't, this must be added to the refactor plan.

## Cycle 17: Post-Agent-Removal Sub-Agent Mock Audit

### Scope

Audit the ests/ directory to identify remaining sub-agent or A2A mock logic that might survive the gent-removal plan and still contain hardcoded --root or --content-dir paths that need to be migrated to --target.

### Findings

#### 33. [Detected] aultspec-mcp Testing Mocks

- **Issue:** Even with A2A logic removed, aultspec-mcp is a core utility that requires rigorous testing. The test suite spins up the MCP server via subprocess for integration testing.
- **Detail:** The gent-removal plan specifies "Phase 4: Clean up Test Suite - Delete A2A and agent tests." However, aultspec-mcp is explicitly kept (as noted in "Ensure the MCP server starts correctly"). If the tests for aultspec-mcp use --root to isolate their execution environment, they will break when --target is introduced.
- **Triage:** High - We must ensure that the aultspec-mcp test fixtures (e.g., in est_mcp_config.py or conftest.py) are properly migrated to use --target and that they do not rely on deprecated .agents directories.
- **Proposed Action:** When executing the global search-and-replace for --root -> --target in Phase 4 of the refactor plan, explicitly verify the aultspec-mcp test fixtures and ensure they still pass.

#### 34. [Detected] TOOL_CONFIGS Test Validation

- **Issue:** Tests validating TOOL_CONFIGS generation (e.g., ests/cli/test_spec_cli.py) currently assert the creation of .vaultspec/rules/agents directories.
- **Detail:** After gent-removal, the .agents (Antigravity) tool config will be deleted. Any tests asserting the existence of these directories will fail.
- **Triage:** Medium - This is primarily a cleanup task for the gent-removal plan, but the --target refactor must be aware of it so it doesn't try to re-introduce or test for deprecated .agents paths when verifying the new --target behavior.
- **Proposed Action:** Ensure the --target refactor tests only assert the creation of the core .vaultspec, .vault, .gemini, and .claude directories.

______________________________________________________________________

## Cycle 18: Vault Core Dependencies on Root Directory

### Scope

Audit src/vaultspec/vaultcore and src/vaultspec/vault_cli.py to ensure that core .vault documentation features (audit, create, index, search) do not have hidden assumptions about Path.cwd() that would break when operated remotely via --target.

### Findings

#### 35. [Detected] Template Discovery Relative Pathing

- **Issue:** The create command in ault_cli.py relies on templates located in .vaultspec/rules/templates. We need to verify how aultcore.create_vault_doc resolves these template paths.
- **Detail:** aultcore.py handles the file generation. If it resolves the template path via \_t.TEMPLATES_DIR, it is safe, as \_t.TEMPLATES_DIR is dynamically populated by init_paths() using the layout resolved from --target.
- **Triage:** Low - Code inspection is required to confirm \_t.TEMPLATES_DIR is strictly used, but architecture suggests it is.
- **Proposed Action:** Briefly scan aultcore.py to ensure Path.cwd() isn't used as a fallback for template discovery if \_t.TEMPLATES_DIR is somehow empty.

#### 36. [Detected] ault audit Output Pathing

- **Issue:** The ault audit command generates outputs. We need to confirm if these are printed to stdout or written to disk. If written to disk, do they respect the --target root?
- **Detail:** The current implementation of ault audit (via metrics.get_vault_metrics and graph.VaultGraph) reads from \_t.ROOT_DIR / ".vault".
- **Triage:** Clear/No-Issue - The vault core operations rely on the globally resolved \_t.ROOT_DIR, meaning they will correctly operate on the .vault directory residing inside the specified --target.

#### 37. [Detected] Hook Execution Path Context

- **Issue:** The hooks system (src/vaultspec/hooks/engine.py and hooks_cli.py) executes user-defined scripts. What is the working directory for these child processes?
- **Detail:** If a user runs aultspec --target /other/repo hooks run post-commit, the hook scripts located in /other/repo/.vaultspec/rules/hooks will be executed. In engine.py:367, subprocess.Popen is called without a cwd= kwarg. This means the hook script executes in the physical cwd of the terminal, NOT the --target workspace root.
- **Triage:** High - If hook scripts execute in the caller's physical cwd instead of the --target directory, they may inadvertently run commands (like git add or lint) against the wrong repository.
- **Proposed Action:** Refactor src/vaultspec/hooks/engine.py so that subprocess.Popen receives cwd=str(\_t.ROOT_DIR) or the context explicitly provides a working directory based on the resolved target layout.

______________________________________________________________________

## Cycle 19: Actionable Hand-off

### Scope

Translate findings into a final checklist for aultspec-writer.

### Findings

#### 38. [Recommendation] Translation to Vaultspec Plan

- **Action:** aultspec-writer must construct .vault/plan/2026-03-05-cli-target-refactor-plan.md using the following execution sequence:
  1. Wait for gent-removal to finish.
  1. **Phase 1: Config Layer Overhaul** (workspace.py, config.py deprecating root/content for target).
  1. **Phase 2: CLI Engine Refactor** (cli_common.py, __main__.py removing early intercepts, fixing rgparse inheritance, migrating module-level loads into main()).
  1. **Phase 3: Initialization Upgrade** (commands.py updating init_run to properly scaffold --providers including .gemini and .claude, resolving the chicken-and-egg config issue).
  1. **Phase 4: Hooks Path Correction** (hooks/engine.py to enforce --target isolation on subprocesses).
  1. **Phase 5: Test Suite Synchronization** (Global string replacement of --root to --target in surviving tests, verifying mcp_server mocks).

## Cycle 20: Comprehensive Global Root Dependencies

### Scope

Audit all remaining \_t.ROOT_DIR usages and test fixtures in the src/vaultspec codebase that survived the previous cycles, to guarantee no edge cases exist where cwd is inadvertently used or \_t.ROOT_DIR fails to provide the expected scoping under the new --target paradigm.

### Findings

#### 39. [Detected] CLI Hardcoded .vaultspec/lib/tests Paths

- **Issue:** In src/vaultspec/core/commands.py (for the
  eadiness command), the test discovery logic assumes tests live in .vaultspec/lib/tests or .vaultspec/lib/src relative to \_t.ROOT_DIR.

- **Detail:** Lines 425-426 construct est_dirs = [\_t.ROOT_DIR / ".vaultspec" / "lib" / "tests", \_t.ROOT_DIR / ".vaultspec" / "lib" / "src"]. While this uses the correct root, it hardcodes an internal structural assumption about where user tests reside for readiness scoring.

- **Triage:** Low - This won't break the CLI refactor, but it is a rigid assumption about the user's workspace structure. It correctly respects the new --target (via \_t.ROOT_DIR). No immediate action required for the --target refactor, but documented for future readiness metric improvements.

#### 40. [Detected] aultspec.core.types.init_paths Dependency

- **Issue:** The global state of \_t.ROOT_DIR relies entirely on init_paths() being called with a validated WorkspaceLayout.
- **Detail:** In src/vaultspec/core/types.py, init_paths takes the layout.output_root and sets \_t.ROOT_DIR. If the init command or mcp_server initializes the framework without properly passing a complete WorkspaceLayout (e.g., passing a raw Path which triggers the legacy fallback in ypes.py:135), it might misalign the ROOT_DIR from the true --target.
- **Triage:** Medium - The execution plan (Phase 1/2) must ensure that
  esolve_workspace() returns a strict WorkspaceLayout based on --target, and that ypes.init_paths only accepts this layout, deprecating the legacy Path fallback.

#### 41. [Detected] Hook Context Root Serialization

- **Issue:** The ctx = {"root": str(\_t.ROOT_DIR), "event": event} passed to hooks serializes the root as a string.
- **Detail:** This is correct behavior, but we must ensure that hooks/engine.py actually utilizes ctx["root"] as the cwd argument in subprocess.Popen when executing the shell commands (as noted in Finding 37).
- **Triage:** High - Directly supports Finding 37. The fix is simply modifying src/vaultspec/hooks/engine.py to use cwd=ctx.get("root", os.getcwd()) inside the subprocess.Popen call.

#### 42. [Validation] Test Suite aultspec-mcp Discovery

- **Status:** Verified that test files in src/vaultspec/tests/cli/ (like est_main_cli.py, est_spec_cli.py) make direct subprocess.run calls to aultspec.\*\_cli. When the --root string replacements are made (Phase 5), these will correctly pivot to --target without further structural changes needed.

## Cycle 21: Configuration Loading Singleton Fragility

### Scope

Audit the configuration singleton lifecycle in src/vaultspec/config/config.py to ensure that resetting the config (
eset_config()) and modifying environment variables during init does not lead to race conditions or stale configurations when running --target integration tests.

### Findings

#### 43. [Detected] Configuration Singleton Lifecycle in init_run

- **Issue:** init_run calls get_config() at the very beginning of its execution (before it creates any files). If init_run is subsequently tasked with writing the initial configuration file and then attempting to use it, the singleton will cache the *default/empty* state.

- **Detail:** In src/vaultspec/core/commands.py:174, cfg = get_config() is called. If the init command is updated to scaffold --providers (Finding #14), and it needs the updated configuration to fetch paths via TOOL_CONFIGS, it will fail unless it explicitly calls
  eset_config() and get_config() *after* writing the initial ramework.md.

- **Triage:** Medium - A hidden state bug that will cause init to silently skip provider scaffolding on the first run, only picking it up on subsequent sync-all runs.

- **Proposed Action:** Ensure Phase 3 of the implementation plan mandates calling aultspec.config.reset_config() immediately after init_run scaffolds the base .vaultspec/rules/system/framework.md file, before it attempts to generate provider directories.

#### 44. [Detected] aultspec.core.types Tool Config Initialization

- **Issue:** The global TOOL_CONFIGS dictionary in src/vaultspec/core/types.py is initialized exactly once when init_paths() is called.

- **Detail:** Even if
  eset_config() is called to refresh the config singleton, TOOL_CONFIGS will still hold the stale default paths unless init_paths() is explicitly called again with the newly generated WorkspaceLayout.

- **Triage:** High - If init_run tries to scaffold .gemini based on \_t.TOOL_CONFIGS right after creating .vaultspec, it will read the default in-memory state.

- **Proposed Action:** The init logic must explicitly re-invoke
  esolve_workspace() and pass it to init_paths() after generating the initial config file, effectively rebooting the in-memory state of the framework before proceeding to the provider scaffolding step.

______________________________________________________________________

**Cycle 21 Concluded.** All edge cases related to state mutation during initialization have been mapped.

## Cycle 22: Dead Code, Legacy Support, and Semantic Naming Standardization

### Scope

Audit the core path resolution layers and enumerations (src/vaultspec/core/types.py, enums.py, config/workspace.py, config/config.py) to identify legacy support elements, redundant dead code left over from previous iterations, and enforce a strict semantic naming convention that accurately reflects the physical directories (e.g., using ault_dir and aultspec_dir instead of abstract, confusing terms like
oot and content_root).

### Findings

#### 45. [Detected] Semantic Naming Inconsistencies in WorkspaceLayout

- **Issue:** The WorkspaceLayout dataclass in src/vaultspec/config/workspace.py uses abstract names (output_root, content_root) that confuse the actual physical directory structures they represent.
- **Detail:**
  - output_root was historically used to define "where outputs go" (the parent of .vault), but it is functionally just the **Target Root** or **Project Root**.
  - content_root was used to define "where configurations live" (the parent of .vaultspec/rules), but it is just the **Framework Root**.
  - ault_root explicitly points to .vault/, and ramework_root points to .vaultspec/.
- **Triage:** High - To successfully roll out the --target ADR, the internal nomenclature must be standardized to prevent future engineering confusion.
- **Proposed Action:** Refactor WorkspaceLayout properties:
  1. Rename output_root to arget_dir (the absolute base path of the project).
  1. Deprecate and remove content_root entirely. It is obsolete.
  1. Keep ault_dir (pointing to {target_dir}/.vault).
  1. Keep aultspec_dir (renamed from ramework_root, pointing to {target_dir}/.vaultspec).

#### 46. [Detected] Legacy Fallback in ypes.init_paths

- **Issue:** src/vaultspec/core/types.py:init_paths explicitly supports a legacy Path fallback.

- **Detail:** Lines 135-138 contain:
  \`python
  if isinstance(layout, Path):

  ```
  # Legacy path: treat as output root, derive content from it

  root = layout
  content = root / cfg.framework_dir
  ```

  \`

- **Triage:** Medium - This legacy block circumvents the rigorous WorkspaceLayout validation built into
  esolve_workspace. It allows parts of the system (or older tests) to inject unverified paths, potentially bypassing git-aware checks or container root constraints.

- **Proposed Action:** Delete the isinstance(layout, Path) block entirely. Enforce that init_paths strictly requires a validated WorkspaceLayout object. Update any tests that relied on passing raw Path objects to pass a mocked WorkspaceLayout instead.

#### 47. [Detected] Ambiguous Global Variables in ypes.py

- **Issue:** The global state variables exported by ypes.py retain legacy naming conventions.
- **Detail:** \_t.ROOT_DIR is currently mapped to output_root. \_t.FRAMEWORK_CONFIG_SRC and \_t.PROJECT_CONFIG_SRC are verbose.
- **Triage:** Medium - While functional, \_t.ROOT_DIR should be renamed to \_t.TARGET_DIR to align with the new CLI flag and prevent developers from confusing it with the literal system root or a random cwd.

#### 48. [Detected] Unused DirName Enums

- **Issue:** src/vaultspec/core/enums.py defines enums for DirName.VAULT and DirName.VAULTSPEC. However, these are inconsistently applied.
- **Detail:** In workspace.py, the default string ".vaultspec" is hardcoded in the function signature: ramework_dir_name: str = ".vaultspec", and ".vault" is hardcoded as ault_root=root / ".vault".
- **Triage:** Low - Dead code/magic string redundancy.
- **Proposed Action:** The WorkspaceLayout engine should import and use DirName.VAULT.value and DirName.VAULTSPEC.value instead of hardcoding strings, ensuring the system has a single source of truth for its core directory names.

#### 49. [Detected] Dead Code: Env Var Aliases in config.py

- **Issue:** src/vaultspec/config/config.py defines VAULTSPEC_ROOT_DIR and VAULTSPEC_CONTENT_DIR in the CONFIG_REGISTRY.
- **Detail:** As per the ADR, these concepts are being collapsed into a single --target. Therefore, the environment variables VAULTSPEC_ROOT_DIR and VAULTSPEC_CONTENT_DIR are dead code and must be aggressively purged from the dataclass VaultSpecConfig.
- **Triage:** High - Leaving these env vars in the registry will cause silent bugs where users try to set them, but the new WorkspaceLayout ignores them in favor of VAULTSPEC_TARGET_DIR.
- **Proposed Action:** Delete VAULTSPEC_ROOT_DIR and VAULTSPEC_CONTENT_DIR from CONFIG_REGISTRY. Introduce a single VAULTSPEC_TARGET_DIR.

## Cycle 23: Security and Path Escaping Vulnerabilities

### Scope

Audit the path resolution engine for potential directory traversal or security bypass vulnerabilities when a user provides a malicious --target payload or when WorkspaceLayout constructs paths.

### Findings

#### 50. [Detected] Unsafe Directory Construction in init_run

- **Issue:** src/vaultspec/core/commands.py iterates over static arrays to create directories (e.g., or subdir in \["adr", "audit", "exec"...\]: d = vault_dir / subdir).

- **Detail:** While the core loop uses safe, hardcoded string literals, the underlying ensure_dir() utility (or Path.mkdir(parents=True)) must be audited. More critically, the --target flag resolution in cli_common.py reads user input directly from the terminal without explicitly blocking directory traversal payloads (like ../).

- **Triage:** Medium - Standard Python Path(user_input).resolve() normalizes ../ safely, converting it to an absolute physical path. As long as
  esolve_workspace() enforces .resolve() immediately on the arget_override, traversal vulnerabilities are mitigated.

- **Proposed Action:** Ensure src/vaultspec/config/workspace.py enforces .resolve(strict=False) on the arget_override variable *before* it is passed into any Git discovery loops or folder assignment logic to guarantee an absolute, normalized path.

#### 51. [Detected] Fragile \_strip_unc Implementation

- **Issue:** Windows UNC paths (\\?) are stripped manually using a string-matching helper \_strip_unc in workspace.py.
- **Detail:** str(path).startswith("\\\\?\\"). This is a brittle mechanism for dealing with Windows long-path limits. If pathlib normalizes paths slightly differently in future Python versions, this string slicing could truncate legitimate network share paths (\\Server\\Share).
- **Triage:** Low - It currently works, but it's a code smell.
- **Proposed Action:** The --target refactor should retain it for now but encapsulate it strictly within the WorkspaceLayout dataclass constructor rather than scattering it throughout the path resolution logic, ensuring all exposed paths are uniformly stripped of UNC prefixes without cluttering the resolution algorithm.

## Cycle 24: aultspec doctor Path Awareness

### Scope

Audit the doctor command (src/vaultspec/core/commands.py:doctor_run) to ensure its diagnostic checks respect the --target paradigm and do not fall back to Path.cwd() or hardcoded global constants inappropriately.

### Findings

#### 52. [Detected] Doctor Env Fallbacks

- **Issue:** doctor_run evaluates the health of the workspace, including the presence of .vault and .lance directories.
- **Detail:** The logic utilizes \_t.ROOT_DIR / ".vault" / ".lance" to check for the vector index. This correctly utilizes the global singleton that will be hydrated via --target.
- **Triage:** Clear/No-Issue - The diagnostic routines correctly inherit the scoped directory context. No refactoring is necessary for doctor_run beyond ensuring \_t.ROOT_DIR is reliably populated (which is covered in earlier findings).

#### 53. [Recommendation] Doctor Target Diagnostics

- **Issue:** When the user provides a --target, aultspec doctor does not currently report what target directory it is evaluating.
- **Detail:** The output focuses on Python versions, Node versions, and .lance sizes, but it does not print the resolved workspace root.
- **Proposed Action:** Enhance doctor_run to print the resolved TARGET_DIR (e.g., Workspace Root: /path/to/target) as the very first line of its diagnostic output. This will dramatically improve debugging for users trying to understand why a remote --target execution is failing or picking up unexpected configurations.

## Cycle 25: Subcommand Targeting Completeness & Consistency

### Scope

Audit every active, surviving subcommand mapped in aultspec to ensure that standard global flags (especially --target) are properly exposed and consistently injected down to the execution handlers. This will also assess if any command *shouldn't* accept a target (like an absolute global operation) but currently does, or vice versa.

### Findings

#### 54. [Detected] Command Handlers Missing rgs.target Usage

- **Issue:** Even if rgparse exposes --target globally, not all commands explicitly pass or use the namespace resolution in their internal routines.

- **Detail:** Most spec_cli.py subcommands (e.g.,
  ules_list,
  ules_sync) don't actually read rgs.target from the parser; they rely on the side-effect of cli_common.resolve_args_workspace(args, ...) modifying the global \_t.ROOT_DIR state behind the scenes. This implicit state injection is technically functional but opaque.

- **Triage:** Low - Functional, but poor architecture.

- **Proposed Action:** The execution plan should ensure that
  esolve_args_workspace explicitly returns the validated WorkspaceLayout, and that the main() function of each CLI namespace (spec_cli, ault_cli, etc.) logs or acts upon this explicit layout rather than just trusting the invisible global state mutation.

#### 55. [Detected] Missing Target Argument in mcp_server

- **Issue:** mcp_server/app.py has no rgparse configuration whatsoever.
- **Detail:** As briefly noted in Cycle 8, if a user tries aultspec mcp --target /some/repo, the script __main__.py routes this to mcp_server.app.main(). Since pp.py does not use rgparse, it will completely ignore the --target flag in sys.argv, falling back to the VAULTSPEC_MCP_ROOT_DIR environment variable, or crashing.
- **Triage:** High - Breaks interface consistency entirely.
- **Proposed Action:** mcp_server/app.py must be wrapped in a standard rgparse setup that utilizes cli_common.add_common_args. It must parse the --target flag, resolve the workspace, and pass the resolved WorkspaceLayout.target_dir directly to the initialize_server() function.

#### 56. [Detected] ault_cli.py Local Root Re-Parsing

- **Issue:** ault_cli.py has its own redundant argument parsing logic.

- **Detail:** In src/vaultspec/vault_cli.py:145, main(argv) manually intercepts the arguments and conditionally calls
  esolve_args_workspace(args, \_default_layout). This duplicates the logic in spec_cli.py.

- **Triage:** Medium - This duplication will cause drift when --target is introduced unless both modules are strictly synchronized.

- **Proposed Action:** The --target refactoring should push the
  esolve_args_workspace call higher up the chain (ideally into __main__.py or a dedicated wrapper) so that the workspace layout is resolved *once*, uniformly, for all CLI entry points before the specific command handlers are invoked.

## Cycle 26: Vault Document Management Targets

### Scope

Audit the specific interactions of ault_cli.py (udit, create, index, search) to ensure they perfectly honor a non-cwd --target flag, focusing specifically on file writes (create) and LanceDB operations (index, search).

### Findings

#### 57. [Detected] Vault create Relative Pathing

- **Issue:** When creating a new document via aultspec vault create --feature XYZ, does the file successfully land in the remote --target/.vault folder, or does it drop into the local cwd?
- **Detail:** In src/vaultspec/vaultcore.py, the create_vault_doc function must be audited to verify it constructs the output path using \_t.ROOT_DIR / ".vault" / .... Looking at previous cycles, it's known that \_t.ROOT_DIR handles the resolution, but any hardcoded string paths inside the aultcore package could bypass this.
- **Triage:** Medium - If aultcore.py bypasses \_t.ROOT_DIR for file creation, documents will leak into the caller's directory instead of the --target.
- **Proposed Action:** The execution plan must include a line item to rigorously verify that src/vaultspec/vaultcore relies 100% on the renamed \_t.TARGET_DIR singleton for writing new Markdown artifacts.

#### 58. [Detected] RAG/LanceDB Target Resolution

- **Issue:** The vector index (.lance) must reside entirely within the --target folder so it doesn't pollute the local filesystem.

- **Detail:** The
  ag package (src/vaultspec/rag/store.py and indexer.py) relies on get_config().lance_dir. If the config singleton correctly inherited VAULTSPEC_TARGET_DIR, the vector DB should be localized. However, there's a risk that store.py uses Path.cwd() if the config is not hydrated yet.

- **Triage:** High - LanceDB will create a persistent binary directory. If --target is ignored, the vector cache will be generated in the user's terminal session cwd, causing massive confusion and failed searches on the remote target.

- **Proposed Action:** Ensure src/vaultspec/rag/store.py uses the properly hydrated config path for the database connection lancedb.connect(...).

## Cycle 27: Synchronization Interface Inconsistencies

### Scope

Audit the sync-all and individual
ules sync, gents sync, skills sync, system sync, and config sync commands to ensure their interface consistently handles the new --target paradigm without unintended side effects.

### Findings

#### 59. [Detected] Redundant Sync Commands Post-Removal

- **Issue:** With the removal of .agents (Antigravity) and the A2A toolings via gent-removal, the command aultspec agents sync becomes largely obsolete, as there will be no .agents directory to push configurations into.

- **Detail:** The sync-all command in spec_cli.py triggers gents_sync,
  ules_sync, skills_sync, etc. If the configuration engine strips the .agents pathing out, gents_sync will iterate over an empty list of targets and do nothing.

- **Triage:** Low - Functional, but confusing UX. A user running aultspec agents list or aultspec agents sync will see no action.

- **Proposed Action:** While removing the gents commands is technically part of the gent-removal scope, the --target refactor should verify that sync-all does not crash if a user specifies a target that happens to be completely missing expected agent directories.

#### 60. [Detected] aultspec doctor Hardcoded Path Checking

- **Issue:** Does aultspec doctor hardcode checks for .vaultspec/rules/agents?
- **Detail:** As found in Cycle 20 (Finding #39) regarding test files, commands.py:doctor_run evaluates the "Framework Structure" and "Agent Coverage". The doctor command currently explicitly counts \*.md files in w_dir / "rules" / "agents" to assign an gent_score.
- **Triage:** High (UX) - If the --target refactor is applied after gent-removal, doctor will permanently assign a low readiness score ("1/5 - No agents") to perfectly healthy repositories because it is explicitly looking for a deprecated feature.
- **Proposed Action:** The --target refactor must remove the "Agent Coverage" metric logic from doctor_run entirely, or replace it with a generalized "Tool Configuration" metric that evaluates the generic rules directories instead.

## Cycle 28: Output Formatting and Verbosity Consistency

### Scope

Audit how the CLI handles output formatting, specifically the interaction between verbosity flags (--verbose, --debug, --quiet), the printer utility, and the logging configuration, to ensure a consistent user experience across all subcommands.

### Findings

#### 61. [Detected] printer.py vs logging Duality

- **Issue:** The CLI uses both logger (from Python's logging module) and a custom Printer class (in src/vaultspec/printer.py) to emit output.
- **Detail:** Subcommands like doctor and init use rgs.printer.out() heavily, while operations like sync use logger.info() or logger.warning(). The Printer object respects the --quiet flag (silencing .out() and .err()), but it operates completely independently of the logging framework.
- **Triage:** Medium - This duality means that a user running --quiet will silence printer outputs but might still see logger.warning or logger.error messages depending on how logging_config.py interprets the quiet flag. Conversely, --verbose might increase logger output but has no effect on Printer.
- **Proposed Action:** The --target refactor is a good opportunity to evaluate if Printer should just be a wrapper around logger with a specific formatting, or if cli_common.setup_logging should explicitly bind the Printer instance to the log level to ensure --quiet, --verbose, and --debug affect *all* CLI output uniformly.

#### 62. [Detected] Inconsistent --json Support

- **Issue:** Some commands provide structured JSON output, while others do not, without a clear architectural reason.

- **Detail:** ault audit and
  eadiness support --json. ault search might output structured text, but no uniform JSON wrapper exists for generic queries (like
  ules list or hooks list). If aultspec is intended to be composed in pipelines, --json should be a standard mixin.

- **Triage:** Low - Feature request rather than a bug.

- **Proposed Action:** Document that --json support is fragmented. Not a blocker for the --target refactor, but it should be noted for future CLI UX passes.

## Cycle 29: Unhandled Exception Masking in Entry Points

### Scope

Audit how unhandled exceptions are caught and displayed at the highest execution levels (__main__.py) and verify if standard debug flags (--debug) correctly expose tracebacks when failures occur.

### Findings

#### 63. [Detected] Exception Swallowing in __main__.py

- **Issue:** Unhandled exceptions in the CLI are caught by a generic try/except block in __main__.py, which explicitly prints the exception string to sys.stderr and swallows the traceback, ignoring the --debug flag.
- **Detail:** At src/vaultspec/__main__.py:122 and 132, the code catches (ImportError, Exception) as exc: and just executes print(f"Error: {exc}", file=sys.stderr). If the user passes --debug expecting to see why a subcommand failed, they get zero traceback information, making the CLI incredibly hostile to debugging.
- **Triage:** High (UX/DevEx) - The --debug flag must be universally respected. If a command crashes, --debug should emit the full stack trace.
- **Proposed Action:** Refactor __main__.py to import and utilize the cli_error_handler context manager from src/vaultspec/cli_common.py, which is explicitly designed to handle unhandled exceptions cleanly and print tracebacks if the debug flag is present. Since --debug might not be parsed by rgparse at the __main__.py intercept layer yet, __main__.py should at least check sys.argv for --debug to pass into the handler, or better yet, push the exception handling down into the respective main() functions where the parsed arguments are available.

## Cycle 30: Unused Global Error Handling

### Scope

Audit the usage of cli_error_handler defined in src/vaultspec/cli_common.py across the various CLI entry points.

### Findings

#### 64. [Detected] Dead Code / Missing Implementation of cli_error_handler

- **Issue:** cli_common.py provides a cli_error_handler context manager specifically designed to cleanly catch unhandled exceptions, optionally print stack traces based on the --debug flag, and exit gracefully. However, it is never actually invoked in ault_cli.py, spec_cli.py, or mcp_server/app.py.
- **Detail:** The main() functions of the surviving CLIs simply call their command handlers (e.g., handle_create(args)). If any core logic throws an unexpected ValueError, KeyError, or internal assertion failure, the raw Python stack trace is vomited to the terminal regardless of whether --debug is set, degrading the CLI experience for regular users. Conversely, as found in Cycle 29, __main__.py catches *everything* and prints a blank string, breaking debugging.
- **Triage:** High (UX/DevEx) - The error handling architecture is defined but completely disconnected.
- **Proposed Action:** The execution plan (Phase 2) should wrap the command execution blocks inside ault_cli.py, spec_cli.py, and mcp_server/app.py within with cli_error_handler(debug=getattr(args, 'debug', False)): to enforce a unified, professional error boundary.

______________________________________________________________________

**Audit Complete.** The CLI layer consistency has been fully mapped, highlighting critical gaps in argument parsing, error formatting, and legacy nomenclature.

## Cycle 31: Subprocess Environment Injection & --target Inheritance

### Scope

Audit the hooks/engine.py subprocess logic and any remaining external integrations to confirm that any child processes spawned by Vaultspec properly inherit not just the cwd (fixed in Cycle 20), but the environment variables related to the workspace configuration (e.g., VAULTSPEC_TARGET_DIR).

### Findings

#### 65. [Detected] Hook Environment Isolation

- **Issue:** Hook scripts triggered by aultspec hooks run execute as arbitrary shell commands or external scripts. They may need to recursively invoke aultspec commands (e.g., a hook that runs aultspec sync-all).
- **Detail:** In src/vaultspec/hooks/engine.py:367, subprocess.Popen is called without an env= parameter. By default, this inherits the parent shell's physical environment variables. However, if a user specifies --target /remote without setting VAULTSPEC_TARGET_DIR in their shell, the parent aultspec process resolves the target internally, but the child hook script knows nothing about it. If the child hook runs aultspec ..., it will operate on cwd instead of /remote.
- **Triage:** High - Breaks composability. Hooks executed remotely via --target will fail or mutate the wrong workspace if they invoke the framework.
- **Proposed Action:** Refactor hooks/engine.py:execute_shell_action to clone os.environ, inject VAULTSPEC_TARGET_DIR=str(\_t.ROOT_DIR) into the cloned dict, and pass env=cloned_env to subprocess.Popen.

#### 66. [Detected] MCP Server Environment Inheritance

- **Issue:** As identified in Finding 19, aultspec-mcp is launched via .mcp.json by IDEs (like Claude Desktop). If init creates .mcp.json using CLI args (rgs: ["vaultspec", "--target", "/foo", "mcp"]), the IDE launches the server directly. However, does mcp_server spawn any further child processes that need this context?
- **Detail:** A quick review of mcp_server indicates it primarily serves tools over stdio and executes python functions (e.g., calling aultcore). It does not typically spawn detached subprocesses post-gent-removal.
- **Triage:** Clear/No-Issue - mcp_server internal function calls will safely respect \_t.ROOT_DIR initialized at startup.

## Cycle 32: sys.argv Manipulation Fragility

### Scope

Audit how sys.argv is modified in the early execution pipelines before hand-off to rgparse, which could potentially misroute or mangle flags like --target.

### Findings

#### 67. [Detected] Unsafe sys.argv Rewrite in __main__.py

- **Issue:** When routing namespace commands, __main__.py literally rewrites the system arguments to fake the program name for rgparse.

- **Detail:** In __main__.py:104, it does sys.argv = \[f"vaultspec {first_arg}", \*sys.argv[2:]\]. This attempts to merge the binary name and the first argument so rgparse prints usage: vaultspec vault ... instead of usage: python ....
  However, if a user specifies --target *before* the subcommand (e.g., aultspec --target /foo vault audit), sys.argv[1] is --target, NOT ault. The naive string matching (irst_arg = sys.argv[1]) totally collapses.

- **Triage:** Critical - The early intercept architecture assumes positional subcommands *always* come first. Standard CLI design allows global flags *before* subcommands. This breaks the --target refactor fundamentally if users type naturally.

- **Proposed Action:** The --target refactor in Phase 2 MUST eliminate __main__.py string-matching routing. It must use a unified root rgparse.ArgumentParser that defines the global flags, creates subparsers for the namespaces (ault,
  ules, hooks, mcp, etc.), and uses set_defaults(func=...) to route execution, allowing rgparse to handle flag positioning dynamically.

## Cycle 33: Argparse Global vs Subcommand Flag Binding

### Scope

Investigate the specific architectural mechanics required to resolve the sys.argv string-matching failure identified in Cycle 32. Specifically, audit how rgparse needs to be structured to support aultspec --target /foo vault audit versus aultspec vault --target /foo audit.

### Findings

#### 68. [Detected] Argparse Interleaved Parsing Requirement

- **Issue:** To safely implement global --target, rgparse must use parse_known_args() or a strictly interleaved parser hierarchy to allow the global parser to intercept flags regardless of where the user places them.
- **Detail:** Currently, cli_common.add_common_args(parser) is called on each *individual* sub-parser (ault_cli.py, spec_cli.py). This means --root is bound to the sub-command level (e.g., aultspec vault --root /foo audit), but passing it *before* the subcommand (aultspec --root /foo vault) causes the root string-matcher in __main__.py to crash.
- **Triage:** High - Moving to a unified root parser (as suggested in Finding #67) requires careful merging of the ault_cli, spec_cli, and hooks parsers into a single tree.
- **Proposed Action:** In Phase 2 of the execution plan, instruct the engineer to:
  1. Create a master ArgumentParser in __main__.py (or a dedicated cli.py).
  1. Call cli_common.add_common_args(master_parser) ONCE.
  1. Create subparsers on the master parser.
  1. Have ault_cli.\_make_parser(subparsers), spec_cli.add_resource_parsers(subparsers), and mcp register their commands *under* the master tree.
  1. This natively fixes the sys.argv string-matching bug, fixes --help intercepts, and fixes --version handling simultaneously.

## Cycle 34: CLI Parsing Ecosystem Analysis (Argparse vs Alternatives)

### Scope

In response to the critical sys.argv string-matching flaws identified in Cycle 32/33, research the Python ecosystem to determine if a third-party module (such as click or yper) is already available in the project to handle complex, multi-layered argument parsing natively, avoiding the need to "reinvent the wheel" with fragile rgparse workarounds.

### Findings

#### 69. [Detected] click is Currently Installed

- **Issue:** The standard library rgparse struggles inherently with nested subcommands and interleaved global flags (e.g., aultspec --target /foo vault audit), requiring complex workarounds like parse_known_args() or parent-parser inheritance chains.
- **Detail:** An audit of the project dependencies via uv pip list reveals that click (version 8.3.1) is already installed in the virtual environment. click is the industry standard for Python CLI applications precisely because it natively supports deeply nested command groups, inherited context objects (ideal for WorkspaceLayout), and interleaved options without resorting to sys.argv hacking.
- **Triage:** Strategic - If the project is already paying the dependency cost for click (likely pulled in via uvicorn or yper/ y), refactoring the CLI layer to use click would permanently resolve Findings 6-9, 29-30, and 67-68 in one unified sweep.
- **Proposed Action:** The engineering team must evaluate a strategic pivot:
  - **Option A (Incremental):** Stick with rgparse. Build the unified master tree utilizing parents=[common_parser] as outlined in Cycle 33. This keeps the framework stdlib only (if click is just an accidental transitive dependency), but requires meticulous manual wiring.
  - **Option B (Architectural Pivot):** Adopt click. Convert ault_cli, spec_cli, and hooks_cli into @click.group() decorators. This natively supports --target as a global option evaluated before the subcommand, passes the resolved WorkspaceLayout down via click.Context.obj, and automatically handles --help and --version universally.

#### 70. [Detected] aultspec Stdlib Policy Conflict

- **Issue:** Does aultspec have a strict "no external dependencies" policy for its core?
- **Detail:** The docstring at the top of src/vaultspec/config/workspace.py states: **Stdlib only** -- no external dependencies. If this architectural mandate applies to the entire CLI entrypoint layer, then migrating to click violates core design principles.
- **Triage:** High (Policy vs Ergonomics) - We cannot blindly recommend click without confirming the project's dependency constraints.
- **Proposed Action:** If the stdlib only rule is absolute, the implementation MUST proceed with the unified rgparse tree (Option A). If the CLI is allowed to use dependencies (since pydantic, httpx, etc., are in the env), Option B is vastly superior. The plan should document both paths and defer to the human engineer or ADR for final selection.

## Cycle 35: Re-evaluation of External Dependencies Policy

### Scope

Investigate the actual project dependencies (pyproject.toml) against the **Stdlib only** docstring mandate found in src/vaultspec/config/workspace.py to determine if a CLI refactor to click is structurally blocked by policy, or if the policy is just isolated to the workspace discovery module.

### Findings

#### 71. [Correction] aultspec is NOT a stdlib-only package

- **Issue:** The docstring in src/vaultspec/config/workspace.py stating **Stdlib only** -- no external dependencies is highly misleading regarding the overall project architecture.

- **Detail:** An audit of pyproject.toml reveals 11 hard dependencies in the base install, including pydantic, PyYAML,
  ich, httpx, and heavy frameworks like uvicorn and starlette.

- **Triage:** Architectural Pivot - The "stdlib only" rule strictly applies to *just* the workspace.py discovery file (likely to ensure early bootstrap path discovery doesn't fail before pydantic loads). It does *not* apply to the broader CLI interface.

- **Proposed Action:** Since the project already aggressively utilizes external dependencies, there is no structural reason we cannot introduce click or yper to fix the deeply flawed CLI parsing layer. However, click is currently *not* in pyproject.toml (it was installed transitively by uvicorn). The implementation plan should formally propose adding yper (which builds on click but integrates natively with pydantic and Python 3 type hints, matching the repository's modern style) to completely replace rgparse, permanently solving Findings 6-9, 29-30, and 67-68.

#### 72. [Detected] Orphaned CLI Dependencies

- **Issue:**
  ich is listed as a hard dependency in pyproject.toml, but aultspec/printer.py implements its own basic terminal output engine.

- **Detail:** The framework is carrying
  ich>=14.3.2 as a production dependency but the core CLI output (Finding #61) is split between standard logging and a custom Printer.

- **Triage:** Low - Codebase bloat.

- **Proposed Action:** If the CLI interface is refactored, printer.py should be overhauled to actually utilize
  ich for elegant console output, or
  ich should be removed from pyproject.toml to reduce the dependency footprint.

## Cycle 36: Typer Migration Dependencies and Test Fixtures

### Scope

Audit the impact of the newly accepted 2026-03-05-cli-engine-typer-adr.md on the existing test suite and verify exactly what components need to be replaced.

### Findings

#### 73. [Detected] CLI Test Helper Incompatibilities

- **Issue:** The existing test helpers (
  un_spec,
  un_vault,
  un_vaultspec) in ests/cli/test_main_cli.py and others execute the CLI by spinning up physical python subprocesses: subprocess.run([sys.executable, "-m", "vaultspec.spec_cli", ...]).

- **Detail:** While Typer commands *can* be executed via subprocesses, the idiomatic and significantly faster way to test Typer applications is using yper.testing.CliRunner. The current test architecture will remain technically functional if the entrypoints are preserved, but they will miss out on the massive performance and debugging benefits of in-memory Typer testing.

- **Triage:** Medium - The execution plan should include refactoring the test helpers in ests/cli/conftest.py to utilize yper.testing.CliRunner, which will drastically speed up the test suite by avoiding python interpreter boot times for every CLI test.

#### 74. [Detected] printer.py Deprecation Path

- **Issue:** The custom src/vaultspec/printer.py is deeply embedded in commands like aultspec init and aultspec doctor.

- **Detail:** The Typer ADR mandates deprecating printer.py in favor of
  ich.

- **Triage:** High - To prevent a fractured codebase, the execution plan must explicitly instruct the engineering agent to delete src/vaultspec/printer.py and replace all calls to rgs.printer.out() with
  ich.print() or yper.echo().

#### 75. [Recommendation] Actionable Hand-off Update (Final Plan Generation)

- **Action:** The aultspec-writer agent's task is now significantly expanded. The .vault/plan/2026-03-05-cli-target-refactor-plan.md must now encompass BOTH the --target path refactoring AND the yper migration simultaneously, as the yper migration is the designated architectural solution for the --target routing bugs.
  The sequence must be:

  1. Wait for gent-removal.

  1. **Phase 1: Config Layer Overhaul** (workspace.py renaming, config.py deprecations).

  1. **Phase 2: Typer Engine Bootstrap** (Install yper, create cli.py as the master Typer app, wire up --target as a global Typer callback).

  1. **Phase 3: Subcommand Porting** (Port ault_cli.py, spec_cli.py, hooks_cli, and mcp_server/app.py to @app.command(), replacing printer.py with
     ich).

  1. **Phase 4: Initialization Upgrade** (commands.py updating init_run for --providers and fixing the singleton bug).

  1. **Phase 5: Test Suite Migration** (Update ests/cli to use yper.testing.CliRunner and --target).

## Cycle 37: Argparse Type Hint Eradication

### Scope

Audit the core business logic files (src/vaultspec/core/\*.py) to identify where rgparse.Namespace is hardcoded as a type hint or expected payload, as this tightly couples the core engine to the rgparse CLI layer, violating separation of concerns and blocking the Typer migration.

### Findings

#### 76. [Detected] Core Logic Tightly Coupled to rgparse.Namespace

- **Issue:** Every single function in src/vaultspec/core/ (e.g., commands.py, gents.py, config_gen.py,
  ules.py, skills.py, system.py,
  esources.py) uses def function_name(args: argparse.Namespace) -> None: as its signature.

- **Detail:** The core execution functions (like init_run, doctor_run,
  ules_sync) expect an rgparse.Namespace object. They actively use getattr(args, "dry_run", False) or access properties like rgs.force and rgs.printer directly. Typer uses standard python function arguments (e.g., def rules_sync(dry_run: bool = False, prune: bool = False):), not a generic namespace object.

- **Triage:** Critical - If the CLI is ported to Typer, the core functions will instantly break unless they are refactored to accept explicit kwargs or a Pydantic settings model.

- **Proposed Action:** The execution plan (Phase 3: Subcommand Porting) must include refactoring all core/\*.py function signatures.

  - *From:* def init_run(args: argparse.Namespace) -> None:
  - *To:* def init_run(force: bool = False) -> None:
  - All internal getattr(args, "xyz") calls must be replaced with direct variable usage.

#### 77. [Detected] ault_cli.py Internal Coupling

- **Issue:** The aultcore handlers (e.g., handle_create, handle_audit in src/vaultspec/vault_cli.py) also rely on rgparse.Namespace.
- **Detail:** While these are technically part of the CLI layer, their signatures must be unpacked into native Typer @app.command() arguments.
- **Triage:** Medium - Standard refactoring task during the Typer port, but essential to document to ensure the executing agent knows to unpack the namespace.

## Cycle 38: Printer Deprecation Blast Radius

### Scope

Audit the codebase for usages of the printer.py module to fully define the scope of its removal as mandated by the Typer+Rich ADR.

### Findings

#### 78. [Detected] ault_cli.py JSON Output Dependency

- **Issue:** src/vaultspec/vault_cli.py relies heavily on rgs.printer.out_json() for the --json flags on udit, eatures, and erify commands.

- **Detail:** If printer.py is deleted, the Typer migration must provide a 1:1 replacement for structured JSON serialization to stdout.

- **Triage:** Medium - Standard
  ich.print_json(data=results) or standard json.dumps() with yper.echo() can trivially replace this, but the engineer must ensure standard out is strictly preserved without extraneous Rich formatting artifacts when --json is passed, so that jq/pipeline integrations don't break.

- **Proposed Action:** When removing printer.py, map .out() to
  ich.print() and .out_json() to
  ich.print_json(data=...) or json.dumps across commands.py and ault_cli.py.

#### 79. [Detected] Unclean Exit in est_printer.py

- **Issue:** The test suite contains a dedicated ests/cli/test_printer.py.
- **Detail:** With the deletion of printer.py, this entire test file becomes obsolete.
- **Triage:** Low - Easy cleanup, but must be explicitly added to Phase 5 (Test Suite Migration) of the execution plan so it isn't left rotting.

## Cycle 39: MCP Server Business Logic Bleed & Extensibility

### Scope

Audit src/vaultspec/mcp_server/app.py and its surrounding tool registries to identify business logic bleed (where the CLI wrapper accidentally houses core orchestration logic) and assess how the Typer refactor will integrate with the MCP FastMCP lifecycle.

### Findings

#### 80. [Detected] aultspec-mcp Lifespan and Initialization Fragility

- **Issue:** The MCP server uses FastMCP, which relies on synccontextmanager lifespans (e.g., \_lifespan in pp.py). Currently, initialize_server() and configuration loading happens *outside* of this lifespan, manually orchestrated inside def main():.

- **Detail:** In src/vaultspec/mcp_server/app.py, main() calls configure_logging(), get_config(), validates cfg.mcp_root_dir, manually calls initialize_server(), and *then* calls mcp.run_stdio_async().
  When the CLI is refactored to Typer, aultspec mcp will become a @app.command() function. If the Typer context is not cleanly passed into the MCP server initialization, or if pp.py attempts to re-initialize logging over Typer's global logging setup, it will create conflicts.

- **Triage:** Medium - Requires careful boundary management during the port.

- **Proposed Action:** In Phase 3 of the execution plan, mcp_server/app.py's main() should be converted into a Typer command def mcp_cmd(ctx: typer.Context):. It should extract the WorkspaceLayout directly from ctx.obj (the context passed by the global Typer callback) instead of relying on get_config().mcp_root_dir. This elegantly centralizes all path resolution into Typer and strips configuration lookup from the MCP wrapper.

#### 81. [Detected] Dead Tool Registries

- **Issue:** src/vaultspec/mcp_server/app.py:80 calls
  egister_team_tools(mcp).

- **Detail:** The gent-removal plan deletes the eam concept entirely.

- **Triage:** Low - Expected cleanup, but must be explicitly documented so the Typer migration doesn't try to port or maintain dead MCP endpoints.

#### 82. [Detected] CLI/MCP Shared Logic

- **Issue:** Are there tools exposed by MCP that bypass the core/ business logic and implement their own functionality?

- **Detail:** A review of ault_tools.py and ramework_tools.py shows they correctly import and call functions from aultcore.py and
  ag.api.py. There is no business logic bleed; the MCP tools act as clean RPC wrappers over the core library.

- **Triage:** Clear/No-Issue - The boundary between the CLI, MCP, and Core Library is structurally sound.

## Cycle 40: Logging Framework Injection & Typer Conflicts

### Scope

Audit the current custom logging_config.py against the yper /
ich integration to identify structural conflicts. The CLI currently manipulates the global Python logging hierarchy. When porting to
ich,
ich.logging.RichHandler is typically used to bridge standard logs to the terminal, but redundant configuration can lead to double-printing or swallowed logs.

### Findings

#### 83. [Detected] Redundant Logging Bootstraps

- **Issue:** src/vaultspec/cli_common.py calls setup_logging(args) which internally calls logging_config.configure_logging(...). At the same time, mcp_server/app.py makes its own explicit call to configure_logging().
- **Detail:** The current architecture manually attempts to control root logger propagation and format strings based on --verbose, --debug, and --quiet.
- **Triage:** High - If Typer/Rich is implemented, the existing logging_config.py will fight with RichHandler for control of stdout/stderr.
- **Proposed Action:** The Typer migration must completely replace src/vaultspec/logging_config.py. The global Typer callback (e.g. def cli(ctx, verbose: bool, debug: bool)) should instantiate logging.basicConfig(handlers=[RichHandler()]) and dynamically set the root log level based on the passed flags. The old configure_logging() calls scattered across the entrypoints must be deleted to enforce a single source of truth.

#### 84. [Detected] aultspec-mcp Logging Blackhole

- **Issue:** mcp_server/app.py contains the comment configure_logging() # Routes to stderr only; safe for MCP stdio transport.
- **Detail:** MCP servers communicating over stdio MUST NOT print arbitrary logs to stdout, as it breaks the JSON-RPC protocol. If the Typer migration globally injects RichHandler(console=Console(stderr=False)) or uses yper.echo (which defaults to stdout), the MCP server will instantly break.
- **Triage:** Critical - The Typer port for aultspec mcp must explicitly override the global logging handler to ensure ALL logs (and Rich formatting) are piped exclusively to sys.stderr when executing the MCP daemon.

## Cycle 41: Aggressive Hard-Exits (sys.exit)

### Scope

Audit the usage of sys.exit() across the codebase to identify rigid termination paths that conflict with Typer/Click's elegant
aise typer.Exit() architecture, particularly in testing environments.

### Findings

#### 85. [Detected] Hardcoded sys.exit in Core Commands

- **Issue:** src/vaultspec/core/commands.py contains bare sys.exit() calls.

- **Detail:** For example, when doctor_run fails, or tests run natively via commands.py, it issues a raw sys.exit(1). Similarly, ault_cli.py issues sys.exit(1) upon WorkspaceError or index failure.

- **Triage:** Medium - While functional in a standalone script, raw sys.exit() calls make unit testing a nightmare because they instantly kill the pytest runner unless explicitly caught via pytest.raises(SystemExit). Typer provides
  aise typer.Exit(code=1) which is safely caught by CliRunner.

- **Proposed Action:** The execution plan (Phase 3) must include scanning src/vaultspec/core/commands.py and the CLI handlers to replace sys.exit(code) with
  aise typer.Exit(code=code), allowing for isolated testing without killing the process tree.

## Cycle 42: Execution Plan Finalization

### Scope

Aggregate the critical additions from Cycles 37-41 to finalize the exact handoff instructions for the aultspec-writer agent, ensuring the Typer integration handles logging constraints, sys.exit deprecation, and rgparse type removal perfectly.

### Findings

#### 86. [Recommendation] Expanded Execution Sequence

- **Action:** The final handoff checklist for .vault/plan/2026-03-05-cli-target-refactor-plan.md must be updated with the following explicit constraints:
  1. Wait for gent-removal to finish.

  1. **Phase 1: Config Layer Overhaul**

     - Rename workspace.py layout vars ( arget_dir, ault_dir, aultspec_dir).
     - Delete VAULTSPEC_ROOT_DIR/CONTENT_DIR from config.py in favor of TARGET_DIR.
     - Remove Path legacy fallback in ypes.py:init_paths.

  1. **Phase 2: Typer Engine Bootstrap**

     - Create cli.py as the master Typer app.
     - Wire --target, --verbose, and --debug as a global Typer callback.
     - Implement
       ich.logging.RichHandler to unify logging globally.

  1. **Phase 3: Subcommand Porting & Type Stripping**

     - Remove rgparse.Namespace from all core/\*.py signatures and replace with kwargs.

     - Delete printer.py and replace .out() with
       ich.print().

     - Replace sys.exit() calls with
       aise typer.Exit().

     - Port ault,
       ules, hooks, and mcp to @app.command().

     - **CRITICAL:** Ensure mcp command forces RichHandler to output exclusively to sys.stderr to protect JSON-RPC stdio.

  1. **Phase 4: Hook Path Correction**

     - Refactor hooks/engine.py to enforce --target isolation (injecting cwd and VAULTSPEC_TARGET_DIR into cloned os.environ).

  1. **Phase 5: Test Suite Migration**

     - Implement yper.testing.CliRunner.
     - Global string replacement of --root to --target.
     - Delete est_printer.py.

## Cycle 43: Stdout/Stderr Pollution in Subcommands

### Scope

Audit explicit usages of sys.stdout and sys.stderr outside of standard logging paths to verify if any core commands hardcode output streams in ways that conflict with Typer's echo or Rich's Console routing.

### Findings

#### 87. [Detected] Clean IO Boundary

- **Issue:** Are there any hidden print() or sys.stdout.write() calls deep within the core library (src/vaultspec/core/\* or aultcore/\*) that might bypass Typer/Rich and accidentally pollute the terminal output (or worse, the MCP JSON-RPC stream)?
- **Detail:** A global regex search for sys.stdout and sys.stderr returned matches ONLY in logging_config.py and __main__.py. The core business logic correctly uses Python's logging.getLogger() or the printer.py wrapper (which we are already migrating to yper.echo/rich.print).
- **Triage:** Clear/No-Issue - The core business engine is surprisingly well-behaved regarding IO isolation. Once logging_config.py is refactored to use RichHandler(console=...) and the printer is swapped for yper.echo(..., err=True) inside the MCP context, the IO streams will be perfectly governed.

#### 88. [Detected] Unsafe print() in config_gen.py

- **Issue:** While sys.stdout isn't explicitly imported, raw print() statements might be used.
- **Detail:** A manual review of src/vaultspec/core/config_gen.py (which handles the config show command) and src/vaultspec/core/system.py (system show) reveals they use raw print(f"...") instead of rgs.printer.out() or logger.info().
- **Triage:** Medium - Raw print() statements bypass Typer's stream management. While fine for standard CLI usage, they cannot be easily redirected or captured natively by Typer's context if the application scales.
- **Proposed Action:** The execution plan (Phase 3) must replace all raw print() statements in src/vaultspec/core/config_gen.py and src/vaultspec/core/system.py with yper.echo().

## Cycle 44: Widespread Raw print() Abuses

### Scope

Following Finding #88, audit the entirety of src/vaultspec/core/ to identify all instances of the raw print() function that bypass the designated printer.py or logging framework, mapping the full scope of yper.echo replacements required for IO governance.

### Findings

#### 89. [Detected] Systemic print() Bleed

- **Issue:** The raw Python print() function is systematically used across src/vaultspec/core/ for CLI output instead of using the injected rgs.printer or the logger.
- **Detail:** A repository-wide regex search reveals raw print() statements heavily polluting:
  - gents.py (gents list)
  - config_gen.py (config show)

## esources.py ( esource_show)

ules.py (
ules list)

- skills.py (skills list)
- sync.py (various list/sync operations)
- system.py (system show)
- __main__.py (help/error intercepts)
- **Triage:** High - This completely defeats the --quiet flag. If a user runs aultspec rules list --quiet, printer.out() stays silent, but print() will forcefully write to the terminal. In an automated CI/CD pipeline, this makes aultspec spammy and uncontrollable. Furthermore, it completely bypasses Rich console formatting.
- **Proposed Action:** The execution plan (Phase 3) must mandate a global search-and-replace across src/vaultspec/core/\*.py to convert ALL print(...) calls to yper.echo(...) (or
  ich.print()), ensuring 100% of standard output respects Typer's stream routing and --quiet context suppression.

## Cycle 45: Consolidated Implementation Plan Update

### Scope

Synthesize the final layer of Typer-related IO bugs into the actionable hand-off plan.

### Findings

#### 90. [Recommendation] IO Governance Execution Blueprint

- **Action:** To permanently resolve the --quiet bypass, printer.py duality, and MCP stdio blackhole, the .vault/plan/2026-03-05-cli-target-refactor-plan.md must be updated with this strict Phase 3 mandate:
  - **Phase 3: Subcommand Porting, IO Governance & Type Stripping**
    - Refactor src/vaultspec/core/\*.py: Replace rgs: argparse.Namespace with typed kwargs.

    - Delete printer.py.

    - **IO Purge:** Run a global regex to replace print(...) and rgs.printer.out(...) with yper.echo(...) or
      ich.print(...) across the entire core/ folder.

    - Replace rgs.printer.out_json(data) with yper.echo(json.dumps(data)).

    - Convert raw sys.exit() calls to
      aise typer.Exit().

    - Port all command handlers (ault_cli, spec_cli, hooks_cli, mcp_server) to @app.command().

    - Ensure the mcp_cmd explicitly re-routes all
      ich and logging to sys.stderr to protect the JSON-RPC interface.

## Cycle 46: logging_config.py Idempotency vs Typer Integration

### Scope

Audit the current src/vaultspec/logging_config.py implementation against the proposed Typer CLI refactor to identify structural incompatibilities, specifically focusing on its idempotency locks, TTY detection, and handler routing.

### Findings

#### 91. [Detected] Premature Rich Integration

- **Issue:** logging_config.py *already* imports and uses
  ich.logging.RichHandler and
  ich.console.Console.

- **Detail:** The codebase is already halfway migrated to
  ich for its logging layer, but because printer.py and raw print() statements still exist, the terminal output is a fractured mix of Rich-styled logs and unstyled plain text.

- **Triage:** Architectural Advantage - The presence of RichHandler in logging_config.py means the project is already prepared for the Typer/Rich integration. The refactoring task is smaller than anticipated: we just need to delete printer.py and map its usages to get_console().print().

#### 92. [Detected] Idempotency Lock Blocking Re-configuration

- **Issue:** logging_config.py uses a module-level variable \_logging_configured = False to prevent multiple configurations.

- **Detail:** Lines 55-57: if \_logging_configured: return. This idempotency lock is dangerous in a Typer CLI environment where a master callback might configure basic logging, and a subcommand might need to elevate it (or vice versa). To change the log level dynamically after startup, a module must explicitly call
  eset_logging() first.

- **Triage:** Medium - While safe for isolated scripts, this lock creates friction in a composed CLI.

- **Proposed Action:** The Typer master callback (e.g., def cli_callback(ctx, debug: bool = False, quiet: bool = False)) must explicitly call
  eset_logging() before configure_logging(debug=debug, quiet=quiet) to guarantee that the CLI flags successfully override whatever initial state was established upon module import.

#### 93. [Detected] TTY Detection Suppressing Rich

- **Issue:** The logging config suppresses RichHandler if sys.stderr.isatty() is False.
- **Detail:** Lines 77-80 evaluate elif sys.stderr.isatty(): before attaching the RichHandler. If the CLI is run inside a subprocess (like in pytest fixtures using subprocess.run(capture_output=True)), the isatty() check fails, and it falls back to a plain StreamHandler.
- **Triage:** Low - This is generally good practice (don't send ANSI color codes into a pipe or log file). However, if Typer begins using Rich for help menus and standard output (via
  ich.print), Typer has its own TTY detection logic. We must ensure Typer's console and the logger's console agree on whether ANSI codes should be emitted to prevent garbled output in CI/CD.

## Cycle 47: Logging Integration in Tests vs Core Modules

### Scope

Following up on Cycle 46, audit the dependencies mapped to logging_config.py to ensure its deprecation or refactoring doesn't break initialization sequences outside of the immediate cli_common.py scope.

### Findings

#### 94. [Detected] CLI Common Implicit Delegation

- **Issue:** Currently, most CLI execution points (like ault_cli.main() and spec_cli.main()) never import logging_config directly; they call setup_logging(args) inside cli_common.py, which acts as the delegate wrapper.

- **Detail:** This centralization is good, but cli_common.setup_logging dynamically switches between a plain handler (if rgs.quiet is true) and standard config. As discovered in Cycle 46, this creates a state machine where
  eset_logging() must be explicitly tracked.

- **Triage:** Clear/No-Issue - The centralization in cli_common.py makes it straightforward to rewrite this single function to initialize Typer's global get_console() context.

#### 95. [Detected] Test Suite Logging Mocks

- **Issue:** src/vaultspec/tests/cli/test_vault_cli.py directly imports and mutates logging.getLogger().level.
- **Detail:** The tests currently assert that setup_logging correctly sets the root logger level (e.g., ssert logging.getLogger().level == logging.DEBUG).
- **Triage:** Low - When the CLI migrates to Typer and uses a centralized Typer callback to initialize logging, these test assertions will still pass as long as the underlying python logging.getLogger().setLevel(...) mechanism is preserved under the hood of the Typer integration.

______________________________________________________________________

**Audit Complete.** The interaction between the custom logging configuration, TTY detection, and Typer/Rich integration has been thoroughly decoded.

## Cycle 48: Subcommand Option Validation and Defaults

### Scope

Audit how the core rgparse options (e.g., --dry-run, --force, --prune) are validated and defaulted in spec_cli.py and ault_cli.py. This will identify logic that must be carefully translated to Typer Option() definitions to ensure behavior remains identical.

### Findings

#### 96. [Detected] Silent Defaults for Boolean Flags

- **Issue:** Many rgparse.ArgumentParser calls define flags using ction="store_true". When a user does *not* supply the flag, rgparse stores False (usually), but the core logic handles this loosely via getattr(args, "dry_run", False).

- **Detail:** For example, in src/vaultspec/spec_cli.py, --dry-run and --prune are defined globally on sync commands. The core functions (
  ules_sync, skills_sync) explicitly use getattr to extract them. Typer requires explicit default assignments in the function signature (e.g., dry_run: bool = typer.Option(False, "--dry-run")).

- **Triage:** Medium - If the Typer port simply specifies dry_run: bool without the yper.Option(False) wrapper, Typer will treat the boolean as a *required* argument, breaking the CLI flow.

- **Proposed Action:** The execution plan (Phase 3) must mandate that ALL boolean flags ported from rgparse are explicitly declared as ool = typer.Option(False, "--flag-name") to guarantee optionality.

#### 97. [Detected] Redundant Validation in aultcore

- **Issue:** The create command in ault_cli.py receives a --feature argument.
- **Detail:** In src/vaultspec/vault_cli.py, handle_create has no local validation. However, aultcore.create_vault_doc performs strict string sanitization on the eature parameter (enforcing kebab-case, removing special characters).
- **Triage:** Low - Good architecture. The validation is correctly placed in the business logic layer, not the CLI parsing layer. The Typer port will not need to reinvent custom validation for the --feature input.

## Cycle 49: Context and Dependency Lifecycles

### Scope

Audit the execution lifecycle of commands like sync-all or doctor to determine if Typer's dependency injection (Depends) can simplify or replace the manual get_config() and
esolve_args_workspace() bootstrapping currently polluting the handlers.

### Findings

#### 98. [Detected] Repetitive Bootstrapping in Core Handlers

- **Issue:** Functions in src/vaultspec/core/ (like commands.py:init_run or doctor_run) manually call rom vaultspec.config import get_config, then instantiate cfg = get_config().
- **Detail:** While functional, this tightly couples the core functions to the global singleton pattern. If we are moving to Typer, Typer encourages passing these contexts explicitly.
- **Triage:** Architectural Opportunity - While not a strict bug, relying on the get_config() singleton inside the core business logic makes unit testing harder (tests have to monkeypatch environment variables to mutate the singleton, as seen in est_config.py).
- **Proposed Action:** The execution plan (Phase 3) should direct the engineer to update the core function signatures to accept cfg: VaultSpecConfig directly as a keyword argument (e.g., def doctor_run(cfg: VaultSpecConfig, target_dir: Path, ...)). The Typer CLI layer should extract cfg = get_config() *once* in the global callback and pass it down via ctx.obj or explicit function calls, completely decoupling the core business logic from the aultspec.config singleton.

#### 99. [Detected] File Opening Resource Leaks

- **Issue:** When reading config files or writing updates during sync, are there unclosed file handlers that might break in a long-running process like mcp_server?
- **Detail:** An audit of src/vaultspec/core/sync.py and helpers.py:atomic_write reveals standard usage of pathlib.Path.read_text(encoding="utf-8") and mp.write_text(). These standard library functions automatically close the file handles upon completion.
- **Triage:** Clear/No-Issue - Safe file handling.

## Cycle 50: Async Command Execution Wrapping

### Scope

Audit how asynchronous operations (like MCP integrations or HTTP network calls if any exist in the core) are invoked by the synchronous CLI layer, and how Typer will handle them.

### Findings

#### 100. [Detected] Typer Async Incompatibility

- **Issue:** Typer (and Click) does not natively support sync def command functions. If an @app.command() is decorated with sync def, Typer will crash or fail to await it.
- **Detail:** The aultspec core commands (like ault_cli.py, spec_cli.py) are currently purely synchronous, but mcp_server/app.py:main is synchronous and explicitly triggers an async lifecycle using syncio.set_event_loop_policy and mcp.run_stdio_async(). Furthermore, if hooks or aultcore ever require async execution, the CLI boundary will shatter.
- **Triage:** High - When porting mcp_server/app.py:main to a Typer command (@app.command() def mcp_cmd(...)), the function MUST remain a synchronous wrapper (def mcp_cmd) that internally calls syncio.run(...) or uses the existing cli_common.run_async() helper.
- **Proposed Action:** The execution plan (Phase 3) must explicitly warn the engineer NOT to make the Typer commands sync def. They must use src/vaultspec/cli_common.py:run_async to bridge the synchronous CLI input to any async backend engines.

______________________________________________________________________

**Cycle 50 Concluded.** The continuous audit document now tracks 100 distinct architectural, implementation, and translation findings.

## Cycle 51: Direct Environment Variable Manipulation Isolation

### Scope

Audit any modules interacting directly with os.environ outside of the central src/vaultspec/config/config.py loading mechanism. This ensures that when the Typer CLI initializes the state via --target or other global flags, there are no "backdoor" environment reads that bypass the typed VaultSpecConfig singleton or Typer's context mechanism.

### Findings

#### 101. [Detected] Unsafe Editor Resolution

- **Issue:** src/vaultspec/core/resources.py reads os.environ.get("EDITOR", "vim") to launch text editors for the dd and edit commands.

- **Detail:** While standard for Unix tools to fallback to the $EDITOR environment variable, the VaultSpecConfig definition in config.py (Finding 49 shows the registry) already defines VAULTSPEC_EDITOR (which defaults to "zed -w"). If
  esources.py checks os.environ.get("EDITOR") directly, it ignores the central configuration paradigm.

- **Triage:** Medium - A violation of the centralized configuration architecture.

- **Proposed Action:** Refactor src/vaultspec/core/resources.py:\_launch_editor to receive the editor string as a parameter from the injected cfg: VaultSpecConfig object. The fallback logic should be: cfg.editor -> os.environ.get("EDITOR") -> "vim", handled strictly within the config module or the command invocation, not hardcoded in the utility function.

#### 102. [Detected] Logging Config Backdoor Read

- **Issue:** src/vaultspec/logging_config.py reads os.environ.get("VAULTSPEC_LOG_LEVEL") directly on line 50.
- **Detail:** As analyzed in Cycle 46, this logging config is flawed. By reading the environment variable directly rather than having the CLI engine pass it down, it circumvents Typer's argument parsing layer. If Typer supports an explicit --verbose flag, logging_config.py's manual os.environ check makes it harder to manage state deterministically.
- **Triage:** High - Reinforces the need for Phase 2 of the execution plan (Finding 86) to completely replace logging_config.py. The Typer master callback must evaluate VAULTSPEC_LOG_LEVEL (via VaultSpecConfig or Typer's Option(envvar=...)) and pass explicit level integers to the new RichHandler instantiation.

## Cycle 52: Standard Input (Stdin) Pipelining

### Scope

Audit components that read from sys.stdin to ensure they integrate correctly with Typer's file and stream reading mechanisms, allowing the CLI to be securely piped into.

### Findings

#### 103. [Detected] Unsafe Stdin Blocking in

ules_add

- **Issue:** src/vaultspec/core/rules.py reads from sys.stdin.read() for the
  ules add command when no explicit content is provided.

- **Detail:** The
  ules_add function allows a user to pipe content directly: cat my_rule.md | vaultspec rules add --name my-rule. It does this by checking if content was passed as an argument, and if not, it calls sys.stdin.read().
  However, if the user *forgets* to pipe content and just runs aultspec rules add --name my-rule interactively without an editor flag, sys.stdin.read() will block the terminal indefinitely waiting for EOF (Ctrl+D), making the CLI appear to hang.

- **Triage:** High (UX) - A classic Python CLI bug that causes severe user confusion.

- **Proposed Action:** When porting
  ules add to Typer, use Typer's native file handling. Typer can define an argument content: typer.FileText = typer.Argument("-") which natively handles reading from stdin if the user pipes it, or otherwise prompts/fails elegantly without locking the terminal into a silent block state. Alternatively, check sys.stdin.isatty() before attempting to read from it.

## Cycle 53: Comprehensive Final Review & Execution Strategy

### Scope

Aggregate the final edge-case findings from Cycles 51-52 regarding environment isolation and standard input blocking, finalizing the absolute bounds of the refactor.

### Findings

#### 104. [Validation] sys.argv Eradication

- **Issue:** Are there any hidden sys.argv hacks outside of __main__.py that would defeat the Typer migration?
- **Detail:** A final audit of sys.argv usage reveals it is only present in __main__.py (the router hack we are deleting), ault_cli.py (a default parameter rgv: list[str] | None = None mapping to sys.argv[1:] for tests), and est_hooks.py (mocking).
- **Triage:** Clear/No-Issue - The codebase is structurally clean enough to rip out rgparse and replace it entirely with Typer without uncovering hidden command-line hacks deep in the business logic.

#### 105. [Recommendation] Complete Plan Structure

- **Action:** The final execution plan handed to aultspec-writer is complete. The Typer migration will systematically fix 105 documented issues across:
  - Global WorkspaceLayout target injection (--target).
  - Terminal formatting and IO streaming (Rich + sys.stderr for MCP).
  - Centralized configuration propagation (killing os.environ backdoors).
  - Hard-exit eradication ( yper.Exit).
  - Test suite performance and robustness (CliRunner).

## Cycle 54: Handling Corrupted State During Refactoring

### Scope

Audit the repository state specifically for blocking issues created by other concurrent agent tasks (gent-removal) that might prevent aultspec-writer or the CLI tools from functioning during the drafting phase.

### Findings

#### 106. [Detected] gent-removal Branch Breakage

- **Issue:** The repository is currently in a broken state due to the gent-removal refactoring.
- **Detail:** The aultspec CLI currently fails to launch entirely. Attempting to run aultspec subagent run --agent vaultspec-writer throws ImportError: cannot import name 'AGENTS_SRC_DIR' from 'vaultspec.core.types'. This indicates that the gent-removal plan was executed partially or sloppily by the previous execution agent. They deleted AGENTS_SRC_DIR from core/types.py but failed to clean up the import statements in core/__init__.py.
- **Triage:** Critical Blocker - We cannot dispatch the aultspec-writer agent using the native aultspec subagent command because the framework itself is broken.
- **Proposed Action:** We must either pause and fix the ImportError manually (so the CLI boots), OR we must manually write the .vault/plan/2026-03-05-cli-target-refactor-plan.md artifact using standard file writing tools instead of relying on the broken aultspec-writer subagent to do it for us.

## Cycle 55: Un-bricking and Post-Agent-Removal Residue

### Scope

Audit the broken state of the repository caused by the gent-removal plan and identify all remaining "ghost" references to AGENTS and other deleted concepts that are causing the current ImportError and AttributeError.

### Findings

#### 107. [Detected] Core Un-bricking Requirements

- **Issue:** The repository is currently hard-broken. uv run vaultspec crashes on startup.
- **Detail:**
  1. src/vaultspec/core/__init__.py attempts to import AGENTS_SRC_DIR from .types, but it was deleted from ypes.py.
  1. src/vaultspec/core/types.py still references Resource.AGENTS.value in \_create_tool_cfg, but AGENTS was deleted from the Resource enum in enums.py.
  1. src/vaultspec/core/rules.py still references Tool.AGENTS in ransform_rule, but AGENTS was deleted from the Tool enum.
- **Triage:** Critical Blocker - The framework is non-functional.
- **Proposed Action:** (Immediately added to Phase 0 of the plan)
  - Remove AGENTS_SRC_DIR from src/vaultspec/core/__init__.py.
  - Delete the gents_dir line from src/vaultspec/core/types.py:\_create_tool_cfg.
  - Remove the Tool.AGENTS checks from src/vaultspec/core/rules.py:transform_rule.

#### 108. [Detected] Ghost Orchestration Imports

- **Issue:** src/vaultspec/core/types.py still contains a get_providers() function that attempts to import from ..protocol.providers.
- **Detail:** While protocol still exists, the gent-removal plan is supposed to strip orchestration. If get_providers remains in core, it maintains a heavy dependency link to the protocol layer.
- **Triage:** Medium - Cleanliness.
- **Proposed Action:** Ensure get_providers is moved or deleted if no longer needed by the core framework post-removal.

#### 109. [Detected] SyncResult and ToolConfig Cleanup

- **Issue:** ToolConfig in src/vaultspec/core/types.py still has an gents_dir: Path | None attribute.
- **Detail:** Since agents are removed, this attribute is dead code.
- **Triage:** Medium - Dead code.
- **Proposed Action:** Remove gents_dir from the ToolConfig dataclass definition in src/vaultspec/core/types.py.

## Cycle 56: Comprehensive Ghost Reference Cleanup (Post-Agent-Removal)

### Scope

Audit the entire codebase for soft references to gent, subagent, eam, and 2a concepts that were missed by the gent-removal plan. These stragglers pollute docstrings, error messages, logic branches, and metrics, creating a "zombie" architecture that confuses the new target-based system.

### Findings

#### 110. [Detected] Extensive Logic Bleed in commands.py

- **Issue:** The
  eadiness command is still 30% composed of agent-related scoring logic.

- **Detail:**
  eadiness_run explicitly checks for .vaultspec/rules/agents, counts agents, checks for tier assignments, and issues recommendations to "Add more agents" or "Run vaultspec agents sync".

- **Triage:** High (UX) - Users will receive incorrect readiness scores based on a deleted feature.

- **Proposed Action:** Completely strip the gent_coverage dimension from src/vaultspec/core/commands.py:readiness_run.

#### 111. [Detected] Residual Tool.AGENTS Logic in config_gen.py

- **Issue:** src/vaultspec/core/config_gen.py still contains a dedicated \_generate_agents_md function and logic to handle Tool.AGENTS.
- **Detail:** Since Tool.AGENTS was removed from the enum, this code is now un-reachable dead weight.
- **Triage:** Medium - Dead code.
- **Proposed Action:** Delete \_generate_agents_md and all Tool.AGENTS branch checks in config_gen.py.

#### 112. [Detected] Zombie Resource Handlers in

esources.py

- **Issue:** src/vaultspec/core/resources.py still has elif label == "Agent" branches in
  esource_show,
  esource_edit, and
  esource_remove.

- **Detail:** These branches attempt to access cfg.agents_dir which is slated for deletion from ToolConfig.

- **Triage:** High - Will cause AttributeError when those commands are invoked.

- **Proposed Action:** Delete all "Agent" label branches from
  esources.py.

#### 113. [Detected] Config Singleton Stale Entries

- **Issue:** VaultSpecConfig in config.py and its related tests in est_config.py still carry gent_mode, 2a_default_port, and 2a_host.
- **Detail:** These variables are no longer used by any surviving module.
- **Triage:** Medium - Registry bloat.
- **Proposed Action:** Purge all agent and A2A variables from CONFIG_REGISTRY in src/vaultspec/config/config.py and delete corresponding tests in ests/config/test_config.py.

#### 114. [Detected] Docstring Pollution

- **Issue:** Files like workspace.py, system.py, and
  ules.py have docstrings that still describe agent-syncing behavior.

- **Triage:** Low - Documentation debt.

- **Proposed Action:** Perform a final documentation sweep to ensure "agent" references are removed or updated to reflect the new "Tool/Provider" nomenclature.

## Cycle 57: Test Suite Decontamination (Post-Agent-Removal)

### Scope

Audit the ests/ and src/vaultspec/tests/ directories to identify all zombie test files, fixtures, and assertions related to gent, subagent, eam, and 2a concepts that were missed by the gent-removal plan.

### Findings

#### 115. [Detected] Massive Zombie Test Files

- **Issue:** Several high-level functional test files were completely overlooked by the gent-removal plan.
- **Detail:**
  - src/vaultspec/tests/cli/test_team_cli.py (Functional team CLI tests)
  - src/vaultspec/tests/cli/test_subagent_cli.py (Subagent CLI flag tests)
  - src/vaultspec/tests/cli/test_a2a_integration.py (A2A executor pipeline tests)
- **Triage:** Critical - These tests reference deleted modules and will fail or prevent the test suite from running.
- **Proposed Action:** (Immediately added to Phase 4 cleanup) Delete all three files mentioned above.

#### 116. [Detected] Infested conftest.py and Fixtures

- **Issue:** ests/protocol/conftest.py and src/vaultspec/tests/cli/conftest.py are full of agent-related directory scaffolding and server spawning logic.
- **Detail:** ests/protocol/conftest.py contains an gent_spawner fixture and echo_agent_def / state_agent_def helpers.
- **Triage:** High - These fixtures are expensive and initialize a "zombie" workspace structure during every test run.
- **Proposed Action:** Completely strip gent_spawner and all gent_def helpers from ests/protocol/conftest.py.

#### 117. [Detected] Residual Assertions in Core Sync Tests

- **Issue:** est_sync_collect.py and est_sync_incremental.py still contain hundreds of lines of code testing agent transformations and multi-pass syncs for agents.
- **Detail:** These files assert things like coder.md being synced to .claude/agents/.
- **Triage:** High - These tests will crash because the gents_sync command and AGENTS enum are being deleted.
- **Proposed Action:** Perform a surgical deletion of all TestCollectAgents, TestTransformAgent, and TestIncrementalAgents classes across the est_sync\_\*.py files.

#### 118. [Detected] Namespace Routing Tests Stale

- **Issue:** src/vaultspec/tests/cli/test_main_cli.py still asserts that aultspec team, aultspec subagent, and aultspec agents namespaces show help.
- **Triage:** High - These namespaces are being removed from __main__.py.
- **Proposed Action:** Remove these assertions.

## Cycle 58: Protocol Layer Semantic Alignment

### Scope

Audit the src/vaultspec/protocol/ directory to identify semantic inconsistencies between the current code (which heavily uses Agent terminology) and the new aultspec architecture (which should focus on Tool or Provider execution).

### Findings

#### 119. [Detected] Semantic Mismatch in Provider Classes

- **Issue:** The core interface for executing models is still called AgentProvider, and its output is SubagentResult.
- **Detail:** Classes like ClaudeProvider(AgentProvider) and GeminiProvider(AgentProvider) exist.
- **Triage:** Medium - While functional, keeping the name AgentProvider while deleting the gent command and orchestration creates an confusing internal API.
- **Proposed Action:** (As part of the general semantic renaming in the ADR)
  - Rename AgentProvider to ExecutionProvider or ToolProvider.
  - Rename SubagentResult to ExecutionResult.
  - Rename SubagentError to ExecutionError.
  - Update all references in src/vaultspec/protocol/.

#### 120. [Detected] Residual Agent Persona Logic

- **Issue:** src/vaultspec/protocol/providers/base.py still has logic to assemble # AGENT PERSONA blocks.
- **Triage:** Low - Functional, but the heading should probably be updated to something like # PROVIDER PERSONA or just # INSTRUCTIONS to reflect the tool-centric nature of the new system.
