---
tags:
  - "#adr"
  - "#provider-parity"
date: 2026-02-15
related:
  - "[[2026-02-08-vault-api-adr]]"
---

# provider-parity adr: Align Provider Feature Surface and Terminology | (**status:** accepted)

## Problem Statement

Feature asymmetry between the Claude and Gemini providers means agent behavior depends on which provider runs them. The same YAML configuration produces different capabilities: Claude supports 8 configurable features (max_turns, budget, allowed_tools, disallowed_tools, effort, output_format, fallback_model, include_dirs) while Gemini supports 4 (allowed_tools, approval_mode, output_format, include_dirs). Features configured for the wrong provider are silently dropped, and the two providers use inconsistent method names for identical operations.

## Considerations

- Claude SDK and Gemini CLI have fundamentally different capability surfaces.
- Some features are SDK-specific: max_turns and budget are ClaudeAgentOptions fields with no Gemini CLI equivalent.
- Some features are CLI-specific: approval_mode is a Gemini CLI flag with no Claude SDK equivalent.
- Forcing full parity where the underlying tool does not support it adds complexity without value.
- Silent feature drops (accepting config but ignoring it) are dangerous and confuse agent authors.
- Method naming inconsistency (`_build_system_context` vs `construct_system_prompt`) makes the codebase harder to maintain and extend.
- The VS_OUTPUT_FORMAT env var is read by the bridge but never passed to ClaudeAgentOptions, creating a silent gap.

## Constraints

- Cannot add features to the underlying SDK/CLI that do not exist.
- Must maintain backward compatibility with existing agent YAML definitions.
- Changes must not break the ACP bridge lifecycle or subprocess spawning.
- Line length max 88 characters per project style.

## Implementation

1. **Standardize abstract interface**: Add `load_system_prompt()`, `load_rules()`, and `construct_system_prompt()` as abstract methods on `AgentProvider` base class.
2. **Align Claude provider**: Rename `_build_system_context()` to `construct_system_prompt()`, add `load_system_prompt()` for `.claude/CLAUDE.md`, and add `system_instructions` parameter.
3. **Fix mode parameter**: Claude provider now sets `VS_AGENT_MODE` in env instead of discarding the mode parameter. Remove redundant set in `run_subagent()`.
4. **Fix VS_OUTPUT_FORMAT bridge gap**: Pass `output_format` through to `ClaudeAgentOptions` in `_build_options()`.
5. **Add provider warnings**: Log warnings when agent YAML configures features unsupported by the resolved provider.
6. **Extract include_dirs validation**: Move duplicated path traversal validation to `_validate_include_dirs()` on base class.

## Rationale

Documenting which features are provider-specific vs shared, and warning on misconfiguration, is preferred over forcing artificial parity. This approach respects the inherent differences between SDK and CLI while preventing silent config drops. Standardizing the abstract interface ensures new providers follow the same contract.

## Consequences

- Agent YAML authors must be aware of which features work with which provider.
- Warnings in logs surface misconfiguration early rather than silently dropping features.
- Both providers now share the same public API surface for system prompt construction.
- The VS_OUTPUT_FORMAT fix closes a gap where JSON output format was configured but never reached the SDK.
