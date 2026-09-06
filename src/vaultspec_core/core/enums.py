"""Define the canonical enum vocabulary shared across core configuration.

This module holds the stable symbolic names for tools, resource kinds,
filenames, directory names, and model capability tiers. It serves as a schema
layer for the rest of the package rather than a workflow or execution module.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum


class CapabilityLevel(IntEnum):
    """Tiered capability levels used to select an appropriate model."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3

    @classmethod
    def from_tier(cls, tier: str | None) -> CapabilityLevel:
        """Resolve a persona ``tier:`` frontmatter string to a capability level.

        Agent personas author a coarse ``tier`` (``LOW``, ``STANDARD``,
        ``HIGH``) rather than a numeric level. ``STANDARD`` is the persona
        vocabulary for the middle tier and maps to :attr:`MEDIUM`; the legacy
        ``MEDIUM`` spelling is accepted for backwards compatibility. The match
        is case-insensitive and whitespace-tolerant.

        Args:
            tier: Raw ``tier`` value from persona frontmatter, or ``None``.

        Returns:
            The corresponding :class:`CapabilityLevel`; defaults to
            :attr:`MEDIUM` for any missing or unrecognized value.
        """
        normalized = (tier or "").strip().upper()
        aliases = {
            "LOW": cls.LOW,
            "STANDARD": cls.MEDIUM,
            "MEDIUM": cls.MEDIUM,
            "HIGH": cls.HIGH,
        }
        return aliases.get(normalized, cls.MEDIUM)


class AdrStatus(StrEnum):
    """Canonical lifecycle status for an Architecture Decision Record.

    Single source of truth for ADR status across the project: the ADR template,
    the :func:`~vaultspec_core.core.adr.adr_supersede` writer, and the
    ``adr-status`` vault check all derive their vocabulary from these members.
    Status is recorded in an ADR's body H1 (for example
    ``... | (**status:** `accepted`)``), so this enum is a validation vocabulary
    and writer constant rather than a frontmatter field.

    Members:
        PROPOSED: Drafted but not yet ratified; the scaffold default.
        ACCEPTED: Ratified and governing the codebase.
        REJECTED: Considered and declined; retained for the record.
        SUPERSEDED: Replaced by a specific successor ADR; the superseded
            document carries ``superseded_by``. Written by
            :func:`~vaultspec_core.core.adr.adr_supersede`.
        DEPRECATED: Retired without a direct successor ADR.
    """

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    DEPRECATED = "deprecated"

    @classmethod
    def from_token(cls, token: str | None) -> AdrStatus | None:
        """Resolve a raw status token to a canonical member, leniently.

        The match is case-insensitive and tolerant of surrounding whitespace and
        backtick quoting, so ``accepted``, ``Accepted``, and `` `accepted` `` all
        resolve to :attr:`ACCEPTED`.

        Args:
            token: Raw status token parsed from an ADR body, or ``None``.

        Returns:
            The matching :class:`AdrStatus`, or ``None`` when *token* is missing
            or falls outside the canonical set.
        """
        if token is None:
            return None
        normalized = token.strip().strip("`").strip().lower()
        try:
            return cls(normalized)
        except ValueError:
            return None


class _TieredModelRegistry(StrEnum):
    """Base for per-provider model registries keyed by capability tier.

    Each concrete registry declares ``HIGH``, ``MEDIUM``, and ``LOW`` members
    whose values are the provider's current model identifier strings. Members
    are named after :class:`CapabilityLevel` members so :meth:`from_level` can
    resolve a level to a model by name without a per-registry mapping table.
    """

    @classmethod
    def from_level(cls, level: CapabilityLevel) -> _TieredModelRegistry:
        """Return the model identifier for a given :class:`CapabilityLevel`.

        Args:
            level: Desired capability tier.

        Returns:
            The registry member whose name matches *level*; defaults to
            ``MEDIUM`` for any level without a matching member.
        """
        try:
            return cls[level.name]
        except KeyError:
            return cls["MEDIUM"]


class ClaudeModels(_TieredModelRegistry):
    """Single source of truth for Claude model identifiers.

    Verified against Anthropic's published model lineup (2026-07-28): Opus 5
    is the current flagship and Sonnet 5 the mid tier, both superseding the
    Claude 4 series (``claude-opus-4-8``, ``claude-sonnet-4-6``). Haiku 4.5
    remains the current fast tier - the Claude 5 family ships no Haiku.
    """

    HIGH = "claude-opus-5"
    MEDIUM = "claude-sonnet-5"
    LOW = "claude-haiku-4-5"


class GeminiModels(_TieredModelRegistry):
    """Single source of truth for Gemini model identifiers.

    Verified against Google's published Gemini API model list (2026-07-28).
    ``gemini-3.6-flash`` is the current stable mid tier and
    ``gemini-3.5-flash-lite`` the current lite tier, superseding
    ``gemini-3.5-flash`` and ``gemini-3.1-flash-lite`` respectively.
    ``gemini-3.1-pro-preview`` remains the flagship for the hardest reasoning
    work; the earlier ``gemini-3-pro-preview`` and ``-3-flash-preview`` are
    shut down, and ``gemini-2.5-flash`` is deprecated (shutdown 2026-10-16).
    """

    HIGH = "gemini-3.1-pro-preview"
    MEDIUM = "gemini-3.6-flash"
    LOW = "gemini-3.5-flash-lite"


class CodexModels(_TieredModelRegistry):
    """Single source of truth for OpenAI Codex model identifiers.

    Verified against OpenAI's published Codex model list (2026-07-28). The
    GPT-5.6 generation replaced the single-flagship-plus-effort-knob shape of
    ``gpt-5.5`` with a tiered family, each variant occupying its own
    cost-performance envelope: ``sol`` for the hardest coding work, ``terra``
    for everyday tasks, ``luna`` for fast, low-cost runs. Reasoning depth is
    still tuned independently via the Codex ``model_reasoning_effort`` setting.
    The ``gpt-5.5``/``gpt-5.4`` line remains selectable but is previous
    generation; ``gpt-5-codex`` is deprecated (API shutdown 2026-07-23).
    """

    HIGH = "gpt-5.6-sol"
    MEDIUM = "gpt-5.6-terra"
    LOW = "gpt-5.6-luna"


class AntigravityModels(_TieredModelRegistry):
    """Reference registry of model identifiers for Google Antigravity.

    Antigravity is model-optional and multi-vendor: the active model is chosen
    at runtime (``agy --model`` or the in-editor model picker), not codified in
    synced agent or skill files. Its subagent frontmatter does accept a
    ``model`` key, but over a three-value tier vocabulary (``inherit``,
    ``flash``, ``pro``) rather than over model identifiers, so these values
    are never emitted into provider artifacts either way. The registry stays
    reference-only: the values mirror Antigravity's default Gemini-class
    lineup so a single source of truth still exists for tooling that wants to
    display or validate a default tier.
    """

    HIGH = "gemini-3.1-pro-preview"
    MEDIUM = "gemini-3.6-flash"
    LOW = "gemini-3.5-flash-lite"


ModelRegistry = (
    type[ClaudeModels]
    | type[GeminiModels]
    | type[CodexModels]
    | type[AntigravityModels]
)


class Tool(StrEnum):
    """Supported AI tool destinations."""

    CLAUDE = "claude"
    GEMINI = "gemini"
    ANTIGRAVITY = "antigravity"
    CODEX = "codex"


class McpScope(StrEnum):
    """Native host scope for an MCP server enrollment."""

    PROJECT = "project"
    LOCAL = "local"
    USER = "user"


class McpTargetFormat(StrEnum):
    """Serialization format consumed by an MCP host target."""

    JSON = "json"
    TOML = "toml"


class GeminiBuiltinTool(StrEnum):
    """Canonical Gemini CLI built-in tool identifiers.

    Each member's string value is the verbatim constant exported from
    ``packages/core/src/tools/definitions/base-declarations.ts`` in
    `google-gemini/gemini-cli`. The Gemini agent definition validator
    (`packages/core/src/agents/agentLoader.ts`) calls
    ``isValidToolName`` against these strings; any drift causes
    ``Invalid tool name`` errors at agent load time.

    These values are FROZEN against gemini-cli ``v0.47.0``, the last
    release verified against this repository, and NOTHING re-checks them
    against upstream. The live source-pin test that once did was removed
    after its ref was pinned to a tag: comparing an immutable ref to an
    unchanged enum has a constant result and cannot detect drift. Upstream
    Gemini CLI is discontinued, so no successor guard was added.
    Revalidate by hand before trusting these against any newer release.
    """

    GLOB = "glob"
    GREP_SEARCH = "grep_search"
    READ_FILE = "read_file"
    RUN_SHELL_COMMAND = "run_shell_command"
    WRITE_FILE = "write_file"
    REPLACE = "replace"
    GOOGLE_WEB_SEARCH = "google_web_search"
    WEB_FETCH = "web_fetch"


class ProviderCapability(StrEnum):
    """Capabilities a provider can declare support for."""

    RULES = "rules"
    SKILLS = "skills"
    AGENTS = "agents"
    ROOT_CONFIG = "root_config"
    SYSTEM = "system"
    HOOKS = "hooks"
    TEAMS = "teams"
    SCHEDULED_TASKS = "scheduled_tasks"
    WORKFLOWS = "workflows"
    MCPS = "mcps"


class Resource(StrEnum):
    """Managed spec resource types."""

    RULES = "rules"
    AGENTS = "agents"
    SKILLS = "skills"
    SYSTEM = "system"
    TEMPLATES = "templates"
    HOOKS = "hooks"
    WORKFLOWS = "workflows"
    MCPS = "mcps"


class FileName(StrEnum):
    """Canonical filenames for framework documentation and configuration."""

    CONFIG_TOML = "config.toml"
    CLAUDE = "CLAUDE.md"
    GEMINI = "GEMINI.md"
    AGENTS = "AGENTS.md"
    SKILL = "SKILL.md"
    SYSTEM = "SYSTEM.md"
    MCP_CONFIG = "mcp_config.json"


class DirName(StrEnum):
    """Reserved directory names within the workspace.

    The names prefixed with ``.`` are top-level workspace directories
    (``.vault``, ``.vaultspec``, provider directories). :attr:`INDEX` is
    a child directory under :attr:`VAULT` that holds auto-generated
    feature index files.
    """

    VAULT = ".vault"
    VAULTSPEC = ".vaultspec"
    CLAUDE = ".claude"
    GEMINI = ".gemini"
    ANTIGRAVITY = ".agents"
    CODEX = ".codex"
    INDEX = "index"


class ManagedState(StrEnum):
    """Desired state of a managed workspace artifact."""

    PRESENT = "present"
    ABSENT = "absent"


class CliAction(StrEnum):
    """CLI action passed to the resolver and preflight engine."""

    INSTALL = "install"
    UPGRADE = "upgrade"
    SYNC = "sync"
    UNINSTALL = "uninstall"
    DOCTOR = "doctor"


class InstallMode(StrEnum):
    """How vaultspec-core is provisioned into a governed workspace.

    Vaultspec-core is development-harness tooling, not a runtime dependency of
    the projects it governs, so provisioning is an explicit choice between two
    equally first-class launch shapes rather than a single baked-in assumption.
    The resolved mode is the source of truth every downstream renderer reads:
    the builtin MCP definition, the four canonical pre-commit hook entries, and
    the doctor's canonical-entry and version-skew checks all branch on it.

    Members:
        TOOL: The default. The CLI, hooks, and MCP server launch through an
            ephemeral ``uvx`` invocation, so ``vaultspec-core`` never enters the
            governed project's own dependency set.
        DEPENDENCY: The explicit opt-in that this repository itself exercises
            by self-hosting. The CLI, hooks, and MCP server resolve through the
            target project's own venv via ``uv run``, so ``vaultspec-core`` is a
            declared dependency of the project.
        DEV: Dev-scoped placement in the default :pep:`735` ``dev`` dependency
            group. Renders byte-identically to :attr:`DEPENDENCY` - ``uv sync``
            installs the default group on every invocation, so the launch shape
            is the same ``uv run`` resolution - but declares distinct
            bookkeeping: the harness is a development dependency that will *not*
            leak into built distributions, versus :attr:`DEPENDENCY`'s runtime
            dependency that will. The distinction is a sharper doctor label and
            an honest committed declaration, never a second render path; every
            renderer collapses ``DEV`` onto :attr:`DEPENDENCY` through the single
            :func:`render_mode` aliasing helper.
    """

    TOOL = "tool"
    DEPENDENCY = "dependency"
    DEV = "dev"

    @classmethod
    def from_token(cls, token: str | None) -> InstallMode | None:
        """Resolve a raw mode token to a canonical member, leniently.

        The match is case-insensitive and tolerant of surrounding whitespace,
        so ``tool``, ``Tool``, and `` tool `` all resolve to :attr:`TOOL`.

        Args:
            token: Raw mode token parsed from a declaration or flag, or
                ``None``.

        Returns:
            The matching :class:`InstallMode`, or ``None`` when *token* is
            missing or falls outside the canonical set.
        """
        if token is None:
            return None
        normalized = token.strip().lower()
        try:
            return cls(normalized)
        except ValueError:
            return None


def render_mode(mode: InstallMode) -> InstallMode:
    """Collapse a declared mode to the mode its artifacts render as.

    The single rendering-time comparator for the three-mode model.
    :attr:`~InstallMode.DEV` is a bookkeeping distinction only - dev-scoped
    placement in the default :pep:`735` ``dev`` group installs on every
    ``uv sync`` and therefore launches through the same ``uv run`` resolution as
    a full :attr:`~InstallMode.DEPENDENCY` - so every renderer (the MCP launch
    command, the pre-commit hook entries) must treat ``DEV`` as
    :attr:`~InstallMode.DEPENDENCY` and never grow a third branch.
    :attr:`~InstallMode.TOOL` and :attr:`~InstallMode.DEPENDENCY` pass through
    unchanged. Doctor labeling and the committed declaration keep reading the
    declared mode directly, since there the ``DEV`` versus ``DEPENDENCY``
    distinction is exactly the point.

    Args:
        mode: The declared :class:`InstallMode`.

    Returns:
        :attr:`~InstallMode.DEPENDENCY` when *mode* is
        :attr:`~InstallMode.DEV`, otherwise *mode* unchanged.
    """
    return InstallMode.DEPENDENCY if mode is InstallMode.DEV else mode


class PrecommitHook(StrEnum):
    """Canonical pre-commit hook IDs managed by vaultspec-core.

    ``VAULT_FIX`` runs all vault checkers as a pure gate, reporting naming,
    frontmatter, annotation, link, dangling, reference, schema, and
    body-link findings and blocking the commit on them. It does not repair:
    the hook's ``pass_filenames: false`` scope makes the whole corpus its
    blast radius regardless of what the commit touches, so a hook-time fix
    writes changes nobody reviewed into commits that are not about them.
    Repair is an operator-run ``vault check all --fix``, committed visibly.
    The member keeps its historical ``vault-fix`` id so existing installs
    are updated in place rather than growing a second, near-duplicate hook.

    ``VAULT_SANITIZE_ANNOTATIONS`` runs the explicit annotation sanitizer so
    generated vault documents do not commit template-only guidance.

    ``SPEC_CHECK`` runs the workspace doctor, diagnosing framework,
    provider, and tooling health.

    ``CHECK_PROVIDER_ARTIFACTS`` prevents provider artifacts and
    installation manifests from being committed to git.
    """

    VAULT_FIX = "vault-fix"
    VAULT_SANITIZE_ANNOTATIONS = "vault-sanitize-annotations"
    SPEC_CHECK = "spec-check"
    CHECK_PROVIDER_ARTIFACTS = "check-provider-artifacts"
