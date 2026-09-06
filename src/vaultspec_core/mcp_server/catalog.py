"""The gateway verb catalog parsed from the shipped CLI reference.

The stateless ``discover`` / ``invoke`` gateway needs one closed, drift-free
inventory of every verb the installed binary declares, so that discovery can
never advertise, and invocation can never accept, a verb the binary lacks. That
inventory is machine-generated between the ``vaultspec:generated`` markers in
``.vaultspec/reference/cli.md`` (the same block the ``spec reference generate``
verb owns), and it ships in the same wheel as the binary, so it cannot fall out
of step with the installed command surface. This module reads that marker block
into an in-memory :class:`CommandCatalog`.

The marker block is the authoritative verb-existence source per the accepted
ADR (Q7): the set of valid verb paths and their curated help text come from it,
and its absence is raised loudly rather than silently yielding an empty catalog.
The block carries no structured per-verb flag data, so each verb's flag schema
and its ``--json`` support are enriched from the installed Typer command tree -
the very source the marker block is generated from, introspected read-only at
build time - giving :func:`~vaultspec_core.mcp_server.tools.gateway` accurate
parameter schemas for ``discover`` and an accurate ``--json`` signal for
``invoke``. Both sources live in the same wheel and regenerate together, so the
single-source-of-truth guarantee the ADR relies on is preserved.

A small static denylist (``uninstall``, ``sync``, the hook lifecycle verbs,
MCP-registry mutation, and index hand-authoring) is removed at build time and
additionally queryable via :meth:`CommandCatalog.is_denied`, so the gateway
enforces it at both ``discover`` and ``invoke``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    import typer
    from typer._click.core import Command as ClickCommand
    from typer._click.core import Context as ClickContext

__all__ = [
    "DENYLIST",
    "CatalogEntry",
    "CatalogParseError",
    "CommandArgument",
    "CommandCatalog",
    "CommandFlag",
    "build_catalog",
]

#: Fence around the machine-generated command inventory in the CLI reference.
_MARKER_BEGIN = "vaultspec:generated:begin command-inventory"
_MARKER_END = "vaultspec:generated:end command-inventory"

#: The CLI executable name that prefixes every verb path in the inventory.
_EXECUTABLE = "vaultspec-core"

#: Matches the first inline code span in a bullet, carrying the full
#: ``vaultspec-core <verb path>`` invocation.
_COMMAND_SPAN = re.compile(r"`" + re.escape(_EXECUTABLE) + r"\s+([^`]+)`")

#: Verb paths removed from the catalog entirely and rejected at both gateway
#: tools. Per ADR Q7 and the reconciliation reference: ``uninstall`` (tears down
#: the framework), MCP-registry mutation (owned by the ``spec mcps`` lifecycle,
#: not the tool surface), and index hand-authoring (``index`` documents stay
#: uncreatable and uneditable via MCP). Read-only ``spec mcps list`` / ``spec
#: mcps status`` are intentionally *not* denied.
#:
#: The hook lifecycle verbs and ``sync`` are denied for a different reason, and
#: a security one (GHSA-w5xf-54cr-fxcq). A workspace hook declares a shell
#: command, so ``spec hooks add``, ``spec hooks run``, ``spec hooks trust`` and
#: the all-provider ``sync`` that fires the ``config.synced`` event are the only
#: cataloged verbs whose *declared purpose* is to spawn a command the caller
#: chose. Every other gateway defence is about argv hygiene and cannot help
#: here: a well-formed, fully declared invocation of those verbs is exactly the
#: dangerous one. Because ``discover`` and ``invoke`` are driven by a model
#: whose context can contain text from a cloned repository, that pairing must
#: not be reachable from the tool surface at all. Denying ``spec hooks trust``
#: matters just as much as denying the runner: consent is an operator decision
#: taken at a terminal, and a tool call is not one. Read-only ``spec hooks
#: list`` / ``spec hooks show`` / ``spec hooks status`` stay available, so an
#: agent can still read and explain a workspace's hooks.
DENYLIST: frozenset[tuple[str, ...]] = frozenset(
    {
        ("uninstall",),
        ("sync",),
        ("spec", "hooks", "add"),
        ("spec", "hooks", "run"),
        ("spec", "hooks", "trust"),
        ("spec", "mcps", "add"),
        ("spec", "mcps", "remove"),
        ("spec", "mcps", "sync"),
        ("spec", "mcps", "uninstall"),
        ("vault", "feature", "index"),
    }
)

#: The ``--json`` structured-output flag; presence in a verb's declared options
#: is what lets ``invoke`` request parsed JSON from that verb.
_JSON_FLAG = "--json"

#: Flags the gateway manages itself and therefore never accepts from a caller's
#: argument object: the server injects ``--target`` and appends ``--json``, and
#: ``--help`` would suppress the command.
RESERVED_FLAGS: frozenset[str] = frozenset({"--target", _JSON_FLAG, "--help"})


class CatalogParseError(ValueError):
    """The shipped CLI reference carries no usable command inventory.

    Distinct from a bare :class:`ValueError` so the gateway can tell this one
    anticipated, remediable failure apart from any other ``ValueError`` the
    Typer introspection in :func:`build_catalog` might raise, and translate
    only this one into a caller-visible refusal. Subclasses ``ValueError`` so
    the raise stays a value error to every caller that does not care about the
    distinction.
    """


@dataclass(frozen=True)
class CommandFlag:
    """One declared option of a cataloged verb.

    Attributes:
        name: The canonical long-form flag, e.g. ``--feature``.
        takes_value: ``True`` when the option consumes a following value,
            ``False`` for a boolean/count switch. This drives ``invoke``'s
            argv construction (``--flag value`` versus a bare ``--flag``).
        help: The option's help text, surfaced in the ``discover`` payload.
    """

    name: str
    takes_value: bool
    help: str = ""


@dataclass(frozen=True)
class CommandArgument:
    """One declared positional argument of a cataloged verb.

    Positional arguments are the ordered operands a verb consumes after its
    options - ``vault add <TYPE>``, ``vault plan status <TARGET>``,
    ``vault plan step check <PLAN> <STEP>``, ``vault feature rename <OLD>
    <NEW>``. ``invoke`` renders the caller's ordered ``positionals`` list into
    exactly these slots, so verbs that need operands are callable.

    Attributes:
        name: The argument's declared metavar/name (lower-cased), for the
            ``discover`` payload; positional order, not name, drives argv.
        required: ``True`` when the verb declares the argument as required.
        variadic: ``True`` when the argument consumes the rest (``nargs == -1``);
            a verb with a variadic tail accepts any number of trailing
            positionals.
    """

    name: str
    required: bool
    variadic: bool = False


@dataclass(frozen=True)
class CatalogEntry:
    """A single cataloged verb: its path, description, and parameter schema.

    Attributes:
        verb_path: The verb path as a tuple of segments, e.g.
            ``("vault", "list")``.
        verb: The space-joined verb path, e.g. ``"vault list"``, as callers
            address it through ``discover`` and ``invoke``.
        description: The curated help text from the CLI reference marker block.
        flags: The verb's declared options, in name order.
        arguments: The verb's declared positional arguments, in declaration
            (left-to-right) order.
        supports_json: Whether the verb accepts ``--json`` for structured
            output; when ``True`` ``invoke`` appends it and parses stdout as
            JSON.
    """

    verb_path: tuple[str, ...]
    verb: str
    description: str
    flags: tuple[CommandFlag, ...] = ()
    arguments: tuple[CommandArgument, ...] = ()
    supports_json: bool = False

    @property
    def accepts_positionals(self) -> bool:
        """Report whether the verb declares any positional argument."""
        return bool(self.arguments)

    @property
    def has_variadic_argument(self) -> bool:
        """Report whether the verb declares a rest-consuming argument."""
        return any(arg.variadic for arg in self.arguments)

    def max_positionals(self) -> int | None:
        """Return the positional-count ceiling, or ``None`` when unbounded.

        A verb with a variadic (``nargs == -1``) argument accepts any number of
        trailing positionals; otherwise the ceiling is the declared count.

        Returns:
            The maximum accepted positional count, or ``None`` when unbounded.
        """
        if self.has_variadic_argument:
            return None
        return len(self.arguments)

    def flag(self, name: str) -> CommandFlag | None:
        """Return the declared :class:`CommandFlag` for *name*, or ``None``.

        Args:
            name: The canonical long-form flag, e.g. ``--feature``.

        Returns:
            The matching flag, or ``None`` when the verb does not declare it.
        """
        for flag in self.flags:
            if flag.name == name:
                return flag
        return None


@dataclass(frozen=True)
class CommandCatalog:
    """The in-memory verb catalog backing both gateway tools.

    Attributes:
        entries: Every cataloged verb keyed by its verb-path tuple, with the
            denylist already removed.
        denied: The denylisted verb paths, retained so the gateway can reject
            a denied verb explicitly rather than as a generic unknown.
    """

    entries: dict[tuple[str, ...], CatalogEntry]
    denied: frozenset[tuple[str, ...]] = field(default_factory=frozenset)

    def declares(self, verb_path: tuple[str, ...]) -> bool:
        """Report whether the catalog declares *verb_path* (denylist excluded).

        Args:
            verb_path: A verb path as a tuple of segments.

        Returns:
            ``True`` when the verb is cataloged and not denied.
        """
        return verb_path in self.entries

    def is_denied(self, verb_path: tuple[str, ...]) -> bool:
        """Report whether *verb_path* is on the static denylist.

        Args:
            verb_path: A verb path as a tuple of segments.

        Returns:
            ``True`` when the verb is explicitly out of scope for the gateway.
        """
        return verb_path in self.denied

    def get(self, verb_path: tuple[str, ...]) -> CatalogEntry | None:
        """Return the :class:`CatalogEntry` for *verb_path*, or ``None``.

        Args:
            verb_path: A verb path as a tuple of segments.

        Returns:
            The cataloged entry, or ``None`` when undeclared or denied.
        """
        return self.entries.get(verb_path)

    def search(
        self, query: str, *, limit: int = 10
    ) -> list[tuple[float, CatalogEntry]]:
        """Rank cataloged verbs against *query*, best match first.

        The ranking is deliberately simple and deterministic - token overlap
        across the verb path and description plus substring bonuses - so the
        gateway owns no opaque relevance model. Entries with a zero score are
        dropped; ties break on the verb string so ordering is stable.

        Args:
            query: The free-text search string.
            limit: The maximum number of ranked entries to return.

        Returns:
            Up to *limit* ``(score, entry)`` pairs sorted by descending score
            then ascending verb string.
        """
        tokens = _tokenize(query)
        scored: list[tuple[float, CatalogEntry]] = []
        for entry in self.entries.values():
            score = _score_entry(entry, query, tokens)
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda pair: (-pair[0], pair[1].verb))
        return scored[:limit]


def _tokenize(text: str) -> list[str]:
    """Split *text* into lowercased alphanumeric tokens for ranking."""
    return [tok for tok in re.split(r"[^a-z0-9]+", text.lower()) if tok]


def _score_entry(entry: CatalogEntry, query: str, tokens: list[str]) -> float:
    """Score one catalog entry against a query and its pre-split tokens.

    Verb-path matches weigh heaviest (the caller is usually reaching for a
    known verb), then description token overlap, with a whole-query substring
    bonus so multi-word intents rank their literal match first.

    Args:
        entry: The candidate catalog entry.
        query: The raw query string, for the substring bonus.
        tokens: The query pre-split into lowercased tokens.

    Returns:
        The non-negative relevance score.
    """
    if not tokens:
        return 0.0
    verb_segments = set(_tokenize(entry.verb))
    description_tokens = set(_tokenize(entry.description))
    score = 0.0
    for token in tokens:
        if token in verb_segments:
            score += 3.0
        elif any(token in segment for segment in verb_segments):
            score += 2.0
        if token in description_tokens:
            score += 1.0
        elif any(token in word for word in description_tokens):
            score += 0.5
    query_lower = query.strip().lower()
    if query_lower and query_lower in entry.verb:
        score += 2.0
    return score


def _iter_inventory_bullets(lines: list[str]) -> list[str]:
    """Reassemble the wrapped bullet lines inside the marker block.

    The reference wraps long bullets across indented continuation lines. This
    joins each ``- ``-prefixed bullet with its continuations into one logical
    line and ignores everything outside the ``vaultspec:generated`` markers.

    Args:
        lines: The reference file split into physical lines.

    Returns:
        One reassembled string per inventory bullet, in document order.
    """
    inside = False
    bullets: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            bullets.append(" ".join(part.strip() for part in current))
            current.clear()

    for line in lines:
        if _MARKER_BEGIN in line:
            inside = True
            continue
        if _MARKER_END in line:
            flush()
            inside = False
            continue
        if not inside:
            continue
        stripped = line.lstrip()
        if stripped.startswith("- "):
            flush()
            current.append(stripped[2:])
        elif current and stripped:
            current.append(stripped)
        elif not stripped:
            flush()
    flush()
    return bullets


def _parse_inventory(reference_path: Path) -> dict[tuple[str, ...], str]:
    """Parse the marker block into a verb-path to description mapping.

    Args:
        reference_path: Path to the CLI reference file.

    Returns:
        Each declared verb path mapped to its curated one-line description.

    Raises:
        CatalogParseError: When the reference has no ``vaultspec:generated``
            command-inventory marker block, which would silently empty the
            catalog; the marker-format contract is surfaced loudly instead.
    """
    text = reference_path.read_text(encoding="utf-8")
    if _MARKER_BEGIN not in text or _MARKER_END not in text:
        msg = (
            f"no vaultspec:generated command-inventory markers found in "
            f"{reference_path}; the gateway catalog cannot be parsed"
        )
        raise CatalogParseError(msg)

    descriptions: dict[tuple[str, ...], str] = {}
    for bullet in _iter_inventory_bullets(text.splitlines()):
        command_match = _COMMAND_SPAN.search(bullet)
        if command_match is None:
            continue
        verb_path = tuple(command_match.group(1).split())
        if not verb_path:
            continue
        descriptions[verb_path] = _bullet_description(bullet)
    return descriptions


def _bullet_description(bullet: str) -> str:
    """Extract the help text following the ``` `command` - ``` prefix."""
    _, sep, tail = bullet.partition("` - ")
    if sep:
        return tail.strip()
    return bullet.strip()


def _collect_command_schemas(
    typer_app: typer.Typer,
) -> dict[tuple[str, ...], tuple[tuple[CommandFlag, ...], tuple[CommandArgument, ...]]]:
    """Introspect the installed Typer app for each leaf verb's parameter schema.

    Walks the Click command tree the CLI builds - the same tree the marker
    block is generated from - collecting every leaf command's long-form
    options and its ordered positional arguments. This is read-only and runs
    once at catalog build.

    Args:
        typer_app: The root Typer application to introspect.

    Returns:
        Each leaf verb path mapped to a ``(flags, arguments)`` pair, flags in
        name order and arguments in declaration order.
    """
    import typer.main
    from typer.core import TyperGroup

    root = typer.main.get_command(typer_app)
    root_ctx = root.context_class(root, info_name=_EXECUTABLE)
    schemas: dict[
        tuple[str, ...], tuple[tuple[CommandFlag, ...], tuple[CommandArgument, ...]]
    ] = {}

    def walk(command: ClickCommand, ctx: ClickContext, prefix: tuple[str, ...]) -> None:
        if isinstance(command, TyperGroup):
            for name in command.list_commands(ctx):
                sub = command.get_command(ctx, name)
                if sub is None or getattr(sub, "hidden", False):
                    continue
                sub_ctx = sub.context_class(sub, info_name=name, parent=ctx)
                walk(sub, sub_ctx, (*prefix, name))
            return
        schemas[prefix] = (_flags_of(command, ctx), _arguments_of(command, ctx))

    walk(root, root_ctx, ())
    return schemas


def _flags_of(command: ClickCommand, ctx: ClickContext) -> tuple[CommandFlag, ...]:
    """Extract the long-form option flags of a resolved Click leaf command."""
    flags: list[CommandFlag] = []
    seen: set[str] = set()
    for param in command.get_params(ctx):
        if param.param_type_name != "option":
            continue
        long_opts = [opt for opt in param.opts if opt.startswith("--")]
        if not long_opts:
            continue
        takes_value = not (
            getattr(param, "is_flag", False) or getattr(param, "count", False)
        )
        help_text = getattr(param, "help", "") or ""
        for opt in long_opts:
            if opt in seen:
                continue
            seen.add(opt)
            flags.append(CommandFlag(name=opt, takes_value=takes_value, help=help_text))
    flags.sort(key=lambda flag: flag.name)
    return tuple(flags)


def _arguments_of(
    command: ClickCommand, ctx: ClickContext
) -> tuple[CommandArgument, ...]:
    """Extract the ordered positional arguments of a resolved Click leaf command.

    Preserves declaration order (the order the operands must be supplied on the
    command line), recording each argument's name, whether it is required, and
    whether it is the rest-consuming variadic tail (``nargs == -1``). Options
    are ignored here; :func:`_flags_of` owns them.

    Args:
        command: The resolved Click leaf command.
        ctx: The command's Click context.

    Returns:
        The declared positional arguments in left-to-right order.
    """
    arguments: list[CommandArgument] = []
    for param in command.get_params(ctx):
        if param.param_type_name != "argument":
            continue
        name = str(getattr(param, "name", "") or "").lower()
        required = bool(getattr(param, "required", False))
        variadic = getattr(param, "nargs", 1) == -1
        arguments.append(
            CommandArgument(name=name, required=required, variadic=variadic)
        )
    return tuple(arguments)


def build_catalog(
    reference_path: Path,
    *,
    typer_app: typer.Typer | None = None,
) -> CommandCatalog:
    """Build the gateway verb catalog from the CLI reference and Typer app.

    The verb-existence set and descriptions come from the ``vaultspec:generated``
    marker block in *reference_path* (the ADR-authoritative source), with the
    static :data:`DENYLIST` removed. Each surviving verb is enriched with the
    option schema, its ordered positional arguments, and ``--json`` support
    introspected from *typer_app* so the gateway can present accurate parameter
    schemas and build correct argv (flags and positionals alike).

    Args:
        reference_path: Path to the shipped CLI reference (``cli.md``).
        typer_app: The root Typer application to introspect for flag schemas.
            Defaults to the installed ``vaultspec_core.cli.app``.

    Returns:
        The populated :class:`CommandCatalog`.

    Raises:
        CatalogParseError: When *reference_path* has no command-inventory
            markers.
    """
    if typer_app is None:
        from vaultspec_core.cli import app as typer_app

    descriptions = _parse_inventory(reference_path)
    command_schemas = _collect_command_schemas(typer_app)

    entries: dict[tuple[str, ...], CatalogEntry] = {}
    for verb_path, description in descriptions.items():
        if verb_path in DENYLIST:
            continue
        flags, arguments = command_schemas.get(verb_path, ((), ()))
        supports_json = any(flag.name == _JSON_FLAG for flag in flags)
        entries[verb_path] = CatalogEntry(
            verb_path=verb_path,
            verb=" ".join(verb_path),
            description=description,
            flags=flags,
            arguments=arguments,
            supports_json=supports_json,
        )

    return CommandCatalog(entries=entries, denied=DENYLIST)
