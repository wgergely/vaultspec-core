---
tags:
  - '#research'
  - '#gemini-live-guards'
date: '2026-09-06'
modified: '2026-09-06'
body_schema: 'body-v2'
body_hash: 'sha256:6d2df4d0321d29025af317a40278e21a687e21f9c420681538373462ff8eb2eb'
related: []
---

# `gemini-live-guards` research: `The Gemini live test guards, the model-drift scope, and how far Antigravity actually shares Gemini's plumbing`

Two questions, measured against `149469a8` on `main`. First: what do the Gemini provider's live test and CI guards actually cost, and what do they still prove. Second: how much of the Gemini provider does Antigravity share, since Antigravity is Google's successor to the Gemini CLI and the answer bounds every option for the provider's future.

The picture on the first question is clean. Two live guards carry the whole recurring cost, one of them cannot detect what it claims to detect, and the CI workflow that looks Gemini-shaped is not.

The picture on the second is the opposite of clean, and it is the finding that matters. Antigravity and Gemini share exactly two on-disk artefacts and diverge on everything else, including one capability Antigravity does not have at all.

## Findings

### Upstream status

Google retired the Gemini CLI consumer service on 2026-06-18, transitioning that workflow to the Antigravity CLI, and declined to commit to the repository's long-term future. The last release verified against this repository is `v0.47.0`, published the same day. This was recorded in the repository before this investigation, in the comment block that pinned the upstream drift test's ref; that comment is removed here, so the fact is restated to survive it.

### Footprint: 187 files, but only 67 are library code

`git grep -il gemini` matches 187 files. 109 are under `.vault/`, a historical records corpus and not maintained surface. Outside `.vault/` the count is 78, of which 67 are under `src/vaultspec_core/`. The maintained footprint is roughly a third of the headline number.

### The renderer contract was verified twice against upstream, and one of the two could not fail informatively

`src/vaultspec_core/tests/cli/test_agents_render.py` carried two live guards on top of an otherwise offline module.

`TestGeminiCliLoadsRenderedAgents` resolved `gemini` on `PATH`, rendered every shipped source agent into a temporary `.gemini/agents/`, planted a deliberately invalid canary agent, and ran `gemini --skip-trust skills list` with a 180-second subprocess timeout, asserting the canary appears in the loader's error output and no rendered agent does. It is a well-built probe - the canary defends against a false green - and it depends entirely on a binary that will stop being installable.

`TestUpstreamGeminiToolPin` fetched `packages/core/src/tools/definitions/base-declarations.ts` from `google-gemini/gemini-cli` and asserted each `GeminiBuiltinTool` value equals the corresponding `*_TOOL_NAME` constant. Its URL was pinned to the **tag** `v0.47.0`, not to a branch. A pinned tag is immutable and the local enum is unchanged, so the comparison has a constant result: it cannot observe drift, and its only reachable failure modes are a network fault, a rate limit, or upstream archival.

### The marker gate is why the cost was being felt now

Before `#483` landed, `pyproject.toml` set `addopts = "-m 'not benchmark'"`, so the `gemini` and `network` markers appeared in no default selector and both live guards ran on every default invocation - where the load test's first statement hard-asserts the binary is present. `#483` bound the exclusion list to `dev.toolchain.EXCLUDED_MARKERS` (`dev/toolchain.py:51`) and the guard at `dev/guards/test_automation_contracts.py:663` now prevents it re-drifting.

After removing both classes, `gemini` and `network` have no remaining user; `claude` keeps one at `src/vaultspec_core/tests/cli/test_mcp_hosts.py:27`.

### `model-drift.yml` is not a Gemini workflow

It reconciles four registries in `src/vaultspec_core/core/enums.py`: `ClaudeModels:123`, `GeminiModels:137`, `CodexModels:154`, `AntigravityModels:172`. `GeminiModels` holds Google **model API** identifiers (`gemini-3.1-pro-preview`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`), not Gemini CLI versions, and `AntigravityModels` mirrors those three values exactly - a mirror asserted by `src/vaultspec_core/core/tests/test_enums_models.py:94-96`. Antigravity is a current provider, so dropping the Google half would remove drift tracking Antigravity depends on.

It is dormant besides: `on:` is `workflow_dispatch` only, the `schedule:` block is commented out, and it requires an `ANTHROPIC_API_KEY` secret its own header documents as absent. It has never run.

One instruction had already gone stale independently: it directs the agent at "tier-resolution fixtures that assert concrete model strings" in `test_agents_render.py`, but that file's tier fixtures are Claude-only and it contains no `gemini-3.*` literal.

### Gemini models and the Gemini CLI are separate lifecycles

Stated explicitly because the two are easy to conflate. `GeminiModels` names identifiers served by Google's model API; it has no dependency on the CLI product and is consumed by `GeminiProvider.models` (`src/vaultspec_core/protocol/providers/gemini.py:55`) and mirrored by `AntigravityModels`. The model family is alive and is what Antigravity runs on. Nothing about the CLI's status bears on it.

Note also that neither the Gemini agent renderer nor the Antigravity path emits a model into a rendered artifact. `_resolve_tier_model` (`core/agents.py:107`) is called only with `ClaudeModels` and `CodexModels`; `_render_gemini_agent` emits `name`, `description` and `tools` and no `model` key.

### Antigravity does NOT share Gemini's plumbing

This is the load-bearing finding, and it contradicts the assumption that Antigravity is a renamed Gemini from Core's side. Comparing the two `ToolConfig` entries at `src/vaultspec_core/core/types.py:300-341`:

| Axis               | `Tool.GEMINI`                                     | `Tool.ANTIGRAVITY`                                 |
| ------------------ | ------------------------------------------------- | -------------------------------------------------- |
| Provider directory | `.gemini` (`DirName.GEMINI`)                      | `.agents` (`DirName.ANTIGRAVITY`)                  |
| `rules_dir`        | `.gemini/rules`                                   | `.agents/rules`                                    |
| `skills_dir`       | `.agents/skills`                                  | `.agents/skills` - **shared**                      |
| `agents_dir`       | `.gemini/agents`                                  | `None` - **no agents at all**                      |
| `config_file`      | `GEMINI.md`                                       | `GEMINI.md` - **shared**                           |
| `system_file`      | `.gemini/SYSTEM.md`                               | `None`                                             |
| `emit_system_rule` | default (on)                                      | `False`                                            |
| `workflows_dir`    | absent                                            | `.agents/workflows`                                |
| `mcp_config_file`  | absent                                            | `.agents/mcp_config.json`                          |
| `embed_rules`      | default (off)                                     | `True`                                             |
| Capabilities       | RULES, SKILLS, AGENTS, ROOT_CONFIG, SYSTEM, HOOKS | RULES, SKILLS, ROOT_CONFIG, WORKFLOWS, HOOKS, MCPS |

Two artefacts are shared - the `.agents/skills` tree and the `GEMINI.md` root config file - and nothing else is.

This was confirmed by installing each provider into a separate empty workspace with `install_run` and diffing the resulting trees, rather than by reading the config alone. Excluding `.vaultspec/` and `.vault/`, Gemini writes 34 files and Antigravity 23, of which 20 are shared - the 16 files under `.agents/skills/`, `GEMINI.md`, and the three managed git files. The 14 files only Gemini writes are `.gemini/SYSTEM.md`, three rules under `.gemini/rules/`, and ten rendered agents under `.gemini/agents/`. The three files only Antigravity writes are the same three rules under `.agents/rules/`.

The divergence is not only in paths. `_AGENT_RENDERERS` (`core/agents.py:224`) registers `Tool.GEMINI: _render_gemini_agent` and does **not** register Antigravity, which falls through to `_render_passthrough_agent`. The Gemini renderer maps every source tool from the Claude vocabulary into `GeminiBuiltinTool` via `_CLAUDE_TO_GEMINI_TOOLS` and drops unmapped ones with a warning; the passthrough renderer does none of that. At the execution-protocol layer the split repeats: `GeminiProvider` loads `.gemini/SYSTEM.md` and `.gemini/rules/*.md` (`protocol/providers/gemini.py`), `AntigravityProvider` has no system prompt and reads `.agents/rules/*.md` (`protocol/providers/antigravity.py`).

Antigravity is already a complete, first-class provider across every touchpoint a provider must satisfy - enums, types, config, config generation, provider sync, provider hooks, resolver, the doctor collector (`core/diagnosis/collectors_provider.py:33`), the managed-file policy, and the CLI surface. It is not missing; it is different.

### What that rules out, and what it leaves open

Aliasing `gemini` to `antigravity` is not a label change. For a workspace that installed Gemini it would silently relocate `rules/` from `.gemini/` to `.agents/`, drop `.gemini/agents/` entirely because Antigravity has no `AGENTS` capability, and drop `.gemini/SYSTEM.md`. Rendered agents would stop being emitted rather than being emitted elsewhere.

Whether a user *should* lose per-agent definitions when moving to Antigravity is a product question this repository cannot answer from its own code: it turns on whether Antigravity has an equivalent concept under another name. That was not determined here, and no claim is made about it.

The shared `GEMINI.md` is a second unresolved edge in the other direction: `core/gitignore.py:304-309` emits it for both tools, and `core/uninstall.py:53-80` maps `.agents/` to `antigravity`, `gemini` and `codex` jointly while mapping `GEMINI.md` to `gemini` alone. So removing the Gemini provider would strand a file Antigravity still writes.

### What was not investigated

Antigravity's on-disk configuration shape as documented by Google, as opposed to as modelled by this repository; the two could differ and only the latter was measured. Whether Antigravity has an agent-definition concept. Whether any Gemini CLI workspaces exist in the wild - no telemetry bears on it. Whether the frozen `GeminiBuiltinTool` vocabulary is still correct for `v0.47.0` beyond what the removed pin asserted when it last ran.

## Sources

- `src/vaultspec_core/core/types.py:300-341`
- `src/vaultspec_core/core/enums.py:123`, `:137`, `:154`, `:172`, `:201`, `:277-303`
- `src/vaultspec_core/core/agents.py:107`, `:224`
- `src/vaultspec_core/core/tests/test_enums_models.py:94-96`
- `src/vaultspec_core/core/gitignore.py:304-309`
- `src/vaultspec_core/core/uninstall.py:53-80`
- `src/vaultspec_core/core/diagnosis/collectors_provider.py:32-37`
- `src/vaultspec_core/protocol/providers/gemini.py`, `protocol/providers/antigravity.py`
- `src/vaultspec_core/tests/cli/test_mcp_hosts.py:27`
- `dev/toolchain.py:51`, `dev/guards/test_automation_contracts.py:663`
- `.github/workflows/model-drift.yml`
- Commit `149469a8` on `main`, the measurement baseline
- Upstream retirement date and the `v0.47.0` pin: recorded in this repository's own `test_agents_render.py` comment block prior to this change; not independently re-verified against a Google announcement during this investigation.
