"""Shared identity-field normalization for the CLI and MCP surfaces.

A vaultspec feature handle and every additional ``#tag`` is a kebab-case
token: lowercase letters, digits, and hyphens, opening on an alphanumeric.
That rule was written three times over - in ``vaultspec-core vault add``, in
the MCP ``create`` tool, and in the per-tag loop each shares - which is
exactly the divergence risk the ``mcp-tool-schema`` reconciliation removes.
This module is the one owner: :func:`normalize_feature_tag` strips a leading
``#``, lowercases and trims, rejects path-traversal, and validates the
canonical pattern, returning a typed :class:`NormalizeResult` instead of
printing or raising, so both a Typer verb and an MCP tool can render the
outcome in their own idiom.

:func:`normalize_vault_date` is the same contract for the one identity field
that is not a kebab-case handle. Together the two cover every value that
reaches a scaffolded document's path: the feature handle, the narrative
topic infix, each ``#tag``, and the date prefix.

The normalizers never fabricate a value they cannot validate: on any failure
they return ``ok=False`` with a human-readable ``error`` and a ``None``
value, and the caller decides how to surface it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "KEBAB_CASE_PATTERN",
    "WINDOWS_RESERVED_NAMES",
    "NormalizeResult",
    "normalize_feature_tag",
    "normalize_vault_date",
]

#: The canonical kebab-case token: opens on an alphanumeric, then any run of
#: lowercase letters, digits, and hyphens. Shared by the feature handle and
#: every additional ``#tag``.
KEBAB_CASE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")

#: Path-traversal characters stripped/rejected before pattern validation, so
#: a normalized token can never escape a directory or inject a separator.
_TRAVERSAL_CHARS = re.compile(r"[/\\]")

#: Windows reserved device base names (case-insensitive; the comparison
#: below is against an already-lowercased token). A feature handle or tag
#: with one of these names produces a scaffolded filename - ``con.index.md``,
#: ``nul.md`` - that Windows treats as a device rather than a regular file,
#: so the create would fail or behave unpredictably on that OS. Shared with
#: :mod:`.query_rename`, which enforces the same set for a rename target;
#: this is the one owner both now defer to.
#:
#: A trailing dot or space is separately invalid in a Windows filename, but
#: needs no dedicated check here: :data:`KEBAB_CASE_PATTERN` already rejects
#: every ``.`` and ``normalize_feature_tag`` already strips surrounding
#: whitespace before validating, so neither can survive into a normalized
#: token in the first place.
WINDOWS_RESERVED_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


@dataclass(frozen=True)
class NormalizeResult:
    """The typed outcome of normalizing one feature handle or tag token.

    Attributes:
        ok: ``True`` when *value* is a valid kebab-case token.
        value: The normalized token (no ``#`` prefix, lowercased) on
            success; ``None`` on failure.
        error: A human-readable failure summary on ``ok is False``; ``None``
            on success.
    """

    ok: bool
    value: str | None = None
    error: str | None = None


def normalize_feature_tag(raw: str, *, label: str = "feature tag") -> NormalizeResult:
    """Normalize and validate a kebab-case feature handle or ``#tag``.

    Strips a single leading ``#``, trims surrounding whitespace, lowercases,
    and folds any path-separator into a hyphen, then validates the canonical
    kebab-case pattern (:data:`KEBAB_CASE_PATTERN`) and rejects a Windows
    reserved device base name (:data:`WINDOWS_RESERVED_NAMES`). A traversal
    token such as ``..`` is *rejected*, not silently repaired: the pattern
    forbids ``.`` so a residual dot (e.g. ``a..b`` or ``a.b``) fails
    validation rather than being deleted into a valid-but-different token
    that could mask a typo. The returned :class:`NormalizeResult` carries
    the ``#``-free token on success (the caller re-applies ``#`` where a
    stored tag needs it) and a rendered *label*-scoped message on failure.

    Args:
        raw: The user-supplied handle or tag (with or without a leading
            ``#``; case- and whitespace-insensitive).
        label: The noun used in the failure message (e.g. ``"feature tag"``
            or ``"tag"``), so a caller can scope the diagnostic to its
            surface.

    Returns:
        A :class:`NormalizeResult`: ``ok=True`` with the normalized value,
        or ``ok=False`` with an ``error`` and a ``None`` value.
    """
    cleaned = raw.lstrip("#").strip().lower()
    cleaned = _TRAVERSAL_CHARS.sub("-", cleaned)

    if not cleaned:
        return NormalizeResult(
            ok=False,
            error=f"{label} is required (e.g. my-feature)",
        )

    if KEBAB_CASE_PATTERN.match(cleaned) is None:
        return NormalizeResult(
            ok=False,
            error=(
                f"Invalid {label} '{raw}'. "
                "Must be kebab-case (lowercase, digits, hyphens)."
            ),
        )

    if cleaned in WINDOWS_RESERVED_NAMES:
        return NormalizeResult(
            ok=False,
            error=(
                f"Invalid {label} '{raw}'. "
                f"'{cleaned}' is a reserved device name on Windows (CON, PRN, "
                "AUX, NUL, COM1-COM9, LPT1-LPT9); choose a different value."
            ),
        )

    return NormalizeResult(ok=True, value=cleaned)


def normalize_vault_date(raw: object, *, label: str = "date") -> NormalizeResult:
    """Normalize a document date into the canonical ``yyyy-mm-dd`` token.

    Companion to :func:`normalize_feature_tag` for the one identity field
    that is not a kebab-case handle. A vault date is the ``date:``
    frontmatter value and the leading segment of every scaffolded filename,
    so - exactly like the feature handle - it decides a path. This function
    is the single owner of that admission: it parses the value into a real
    :class:`datetime.date` through the vault's canonical lenient parser and
    returns the date re-rendered from that parsed value, never a substring
    of the caller's input.

    Parsing rather than pattern-matching is the point. A value that survives
    is a calendar date by construction, so the token handed back can only
    ever be ten characters of digits and hyphens: it cannot carry a path
    separator, a relative segment, a drive letter, or a leading root, and it
    therefore cannot steer the directory a document lands in. A value that
    does not parse is refused here, before any path is composed.

    The accepted input set is deliberately not narrowed: it is whatever
    :func:`~vaultspec_core.vaultcore.models.parse_lenient_date` accepts, so
    hand-authored frontmatter in any of the tolerated forms keeps working
    and is simply canonicalized on the way through.

    Args:
        raw: The candidate date - a string, a :class:`datetime.date`, a
            :class:`datetime.datetime`, or any other object (which fails).
        label: The noun used in the failure message, so a caller can scope
            the diagnostic to its surface.

    Returns:
        A :class:`NormalizeResult`: ``ok=True`` with the canonical
        ``yyyy-mm-dd`` string, or ``ok=False`` with an ``error`` and a
        ``None`` value.
    """
    from .models import parse_lenient_date

    parsed = parse_lenient_date(raw)
    if parsed is None:
        rendered = raw if isinstance(raw, str) else repr(raw)
        return NormalizeResult(
            ok=False,
            error=(
                f"Invalid {label} '{rendered}'. "
                "Must be a calendar date in (or normalizable to) YYYY-MM-DD form."
            ),
        )
    return NormalizeResult(ok=True, value=parsed.isoformat())
