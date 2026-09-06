"""Define the core domain model for `.vault/` documents and metadata.

This module captures document types, frontmatter structure, tag constraints,
filename validation, and related structural rules. It is the semantic heart of
the vault model on which parsing, scanning, verification, and higher-level
analysis depend.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

__all__ = [
    "DocType",
    "DocumentMetadata",
    "VaultConstants",
    "normalize_date",
    "parse_lenient_date",
    "refresh_modified_stamp",
    "vault_today",
]

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

#: Canonical vault date form: ``yyyy-mm-dd`` (ISO 8601 calendar date).
_CANONICAL_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: Slash-separated year-first form: ``yyyy/mm/dd``.
_YEAR_FIRST_SLASH_RE = re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$")

#: Two small components and a four-digit year, ``dd-mm-yyyy`` or
#: ``mm/dd/yyyy`` style, with a consistent ``-`` or ``/`` separator.
_YEAR_LAST_RE = re.compile(r"^(\d{1,2})([-/])(\d{1,2})\2(\d{4})$")


def _parse_canonical(text: str) -> tuple[bool, _dt.date | None]:
    """Parse a canonical ``yyyy-mm-dd`` string."""
    if not _CANONICAL_DATE_RE.match(text):
        return False, None
    try:
        return True, _dt.date.fromisoformat(text)
    except ValueError:
        return True, None


def _parse_iso_timestamp(text: str) -> tuple[bool, _dt.date | None]:
    """Parse an ISO 8601 timestamp, optionally zoned, 'T' or space separated.

    A zone-aware timestamp is converted to UTC before its calendar date is
    taken, matching the vault's single UTC clock (:func:`vault_today`) that
    every ``date:``/``modified:`` stamp and file-mtime comparison is
    anchored to. Taking the date from the timestamp's own literal
    wall-clock offset instead - as :meth:`datetime.datetime.date` does by
    default - silently disagrees with that clock for any offset that
    crosses a UTC calendar-day boundary: ``2026-02-08T23:00:00-05:00`` is
    ``2026-02-09`` in UTC but reads as ``2026-02-08`` unconverted, the same
    class of clock mismatch already fixed for file-mtime reads. A naive
    (unzoned) timestamp carries no offset to convert and is read as-is.
    """
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return False, None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(_dt.UTC)
    return True, parsed.date()


def _parse_year_first_slash(text: str) -> tuple[bool, _dt.date | None]:
    """Parse a slash-separated year-first ``yyyy/mm/dd`` string."""
    m = _YEAR_FIRST_SLASH_RE.match(text)
    if m is None:
        return False, None
    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return True, _dt.date(year, month, day)
    except ValueError:
        return True, None


def _parse_year_last(text: str) -> tuple[bool, _dt.date | None]:
    """Parse an unambiguous year-last ``dd-mm-yyyy`` / ``mm/dd/yyyy`` string."""
    m = _YEAR_LAST_RE.match(text)
    if m is None:
        return False, None
    first, second, year = int(m.group(1)), int(m.group(3)), int(m.group(4))
    if first > 12 and 1 <= second <= 12:
        day, month = first, second
    elif second > 12 and 1 <= first <= 12:
        month, day = first, second
    else:
        # Both components could be a month: ambiguous - reject
        # rather than guess (D3b).
        return True, None
    try:
        return True, _dt.date(year, month, day)
    except ValueError:
        return True, None


#: The string parsers in precedence order. Each reports whether it claims
#: the text and, when it does, the date it parsed - ``None`` standing for a
#: claimed but ambiguous or out-of-range value. The first claim wins, so a
#: malformed value in a recognised shape is rejected rather than reparsed
#: by a later, looser parser.
_STRING_PARSERS: tuple[Callable[[str], tuple[bool, _dt.date | None]], ...] = (
    _parse_canonical,
    _parse_iso_timestamp,
    _parse_year_first_slash,
    _parse_year_last,
)


def parse_lenient_date(value: object) -> _dt.date | None:
    """Parse a frontmatter date value leniently into a :class:`datetime.date`.

    This is the single canonical lenient-date helper mandated by the
    vault-orientation ADR (decision D3b). Every consumer of the
    ``date:`` / ``modified:`` stamps (validation, the check/fix
    reconciliation path, the backfill migration, and the status
    rollup's recency sort) parses through this function so hand-edited
    values in common formats survive, while genuinely ambiguous or
    unrecognisable values are rejected rather than guessed at.

    Accepted inputs:

    - :class:`datetime.date` / :class:`datetime.datetime` objects
      (YAML parses unquoted ``yyyy-mm-dd`` scalars into these).
    - Canonical ``yyyy-mm-dd`` strings.
    - ISO 8601 timestamps (``yyyy-mm-ddTHH:MM:SS`` with optional
      fractional seconds and zone offset; a space separator is also
      accepted). A zone offset (including ``Z``) is converted to UTC
      before the date is taken, so the offset can shift which calendar
      day is returned relative to the timestamp's own literal wall clock.
      A naive (unzoned) timestamp is read as-is.
    - Slash-separated year-first dates (``yyyy/mm/dd``).
    - Year-last forms (``dd-mm-yyyy``, ``mm/dd/yyyy``) **only when
      unambiguous**: one of the two leading components must exceed 12
      so day and month are distinguishable. Ambiguous values such as
      ``03-04-2026`` are rejected (return ``None``) rather than
      guessed.

    Surrounding whitespace and stray single/double quotes are stripped
    before parsing.

    Args:
        value: Raw frontmatter value - a string, a
            :class:`datetime.date`, a :class:`datetime.datetime`, or
            any other object (which fails parsing).

    Returns:
        The parsed :class:`datetime.date`, or ``None`` when the value
        is missing, ambiguous, or unrecognisable. Callers must treat
        ``None`` as a finding (per D3b a value no parser recognises is
        flagged, never silently dropped).

    See Also:
        :func:`normalize_date` for the canonical-string companion, and
        :meth:`DocumentMetadata.validate` for the validation policy
        built on this helper.
    """
    if isinstance(value, _dt.date):
        return value.date() if isinstance(value, _dt.datetime) else value
    if not isinstance(value, str):
        return None

    text = value.strip().strip("\"'").strip()
    if not text:
        return None

    for parser in _STRING_PARSERS:
        claimed, parsed = parser(text)
        if claimed:
            return parsed
    return None


def normalize_date(value: object) -> str | None:
    """Normalize a lenient date value to the canonical ``yyyy-mm-dd`` string.

    Companion to :func:`parse_lenient_date`: the check/fix
    reconciliation path and the backfill migration use this to rewrite
    whatever they parsed back to the canonical quoted ``yyyy-mm-dd``
    form mandated by the vault-orientation ADR (decision D3b).

    Args:
        value: Raw frontmatter value accepted by
            :func:`parse_lenient_date`.

    Returns:
        The canonical ``yyyy-mm-dd`` string, or ``None`` when the value
        cannot be parsed.
    """
    parsed = parse_lenient_date(value)
    return parsed.isoformat() if parsed is not None else None


def vault_today() -> _dt.date:
    """Return today's calendar day on the vault's single canonical clock.

    Every date a vault document carries - the ``date:`` frontmatter field
    stamped at scaffold time, the ``yyyy-mm-dd`` filename prefix, the
    ``modified:`` stamp :func:`refresh_modified_stamp` refreshes on every
    mutation, and the recency comparisons that read those fields back -
    is, by design, one shared clock. UTC is that clock, matching the
    scaffold-time stamping already done by
    :func:`vaultspec_core.cli.vault_cmd.cmd_add` and
    :func:`vaultspec_core.mcp_server.tools.documents.register_document_tools`.

    Calling :meth:`datetime.date.today` (or any other local-clock
    equivalent) directly anywhere a vault document's date is computed is
    the bug this helper exists to prevent: a document's ``date:`` (UTC,
    set once) and its ``modified:`` stamp (previously local, refreshed on
    every mutation) could disagree by a full calendar day for any
    contributor whose local day and UTC day differ at the moment of the
    call, which in turn let the ``modified:`` staleness checker and the
    recency-window comparisons misfire on nothing more than a timezone
    skew. Every site that needs "today" for a vault document routes
    through this one function so the clock can never drift back apart.

    Returns:
        The current UTC calendar date.
    """
    return _dt.datetime.now(_dt.UTC).date()


def refresh_modified_stamp(text: str, today: _dt.date) -> str:
    """Refresh (or add) the ``modified:`` stamp and re-attest ``body_hash:``.

    This is the single shared mutator-side helper mandated by the
    vault-orientation ADR (decision D3): every CLI verb that mutates a
    vault document refreshes that document's ``modified:`` frontmatter
    stamp to the day the mutation lands, so the status rollup's recency
    source travels with the document.

    The modified-stamp-provenance ADR extends that contract to the
    document's content fingerprint: the same write re-attests
    ``body_hash:`` from the text being stamped, so the stamp and the body
    it attests can never disagree after a mutating verb. Routing both
    fields through one helper is what makes the pairing structural rather
    than a discipline every call site has to remember - a verb that
    refreshed the date without re-attesting would leave the document
    reading as hand-edited the moment it landed. See
    :mod:`vaultspec_core.vaultcore.body_hash` for the fingerprint's
    canonical definition.

    The function operates on full document text and preserves every
    other byte:

    - When the frontmatter already carries a ``modified:`` field, its
      value is rewritten to ``'<today>'`` (canonical quoted
      ``yyyy-mm-dd``), keeping the field's original indentation and the
      surrounding line ending.
    - When the field is absent (a pre-backfill document) it is inserted
      directly after the ``date:`` line, matching that line's
      indentation and line ending, so the stamp lands in its canonical
      schema position.
    - When there is no YAML frontmatter, or the frontmatter carries no
      ``date:`` anchor and no ``modified:`` field, the text is returned
      unchanged: there is no canonical place to put the stamp and the
      caller's mutation is left to stand on its own.

    The stamp is only refreshed inside the leading frontmatter fence;
    body occurrences of ``modified:`` or ``date:`` are never touched.

    Args:
        text: Full document text, including any YAML frontmatter.
        today: The date to stamp; callers pass :func:`vault_today` so the
            stamp lands on the vault's single canonical UTC clock.

    Returns:
        The document text with its ``modified:`` stamp refreshed or added
        and its ``body_hash:`` re-attested, or the input unchanged when no
        canonical anchor exists.

    See Also:
        :func:`normalize_date` for the canonical-string companion,
        :func:`vaultspec_core.vaultcore.body_hash.set_body_hash` for the
        fingerprint half of the same write, and
        :func:`vaultspec_core.vaultcore.hydration._inject_modified` for
        the scaffold-time half of decision D3.
    """
    from .body_hash import document_body_digest, set_body_hash
    from .rename_ops import split_keepends

    # Match the leading frontmatter fence, tolerating LF, CRLF, and classic-Mac
    # CR line endings. A per-line regex scan with ``re.MULTILINE`` would silently
    # skip a CR-only document because Python only recognises ``\n`` as a line
    # boundary; instead, capture the frontmatter body (group 2) INCLUDING the
    # trailing EOL of its last line, then operate line-by-line via
    # ``split_keepends`` so every line's exact terminator is preserved.
    fence = re.match(
        r"^(﻿?)---[ \t]*(?:\r\n|\r|\n)(.*?(?:\r\n|\r|\n))---", text, re.DOTALL
    )
    if not fence:
        return text

    block_start = fence.start(2)
    block_end = fence.end(2)
    pairs = split_keepends(text[block_start:block_end])
    canonical = f"'{today.isoformat()}'"

    # The fingerprint is taken from the incoming text: this helper only ever
    # rewrites frontmatter, so the body it attests is the body the caller is
    # handing on, before or after this call alike.
    digest = document_body_digest(text)

    # Rewrite an existing ``modified:`` line in place, preserving its ending.
    for pair in pairs:
        m = re.match(r"^(?P<indent>[ \t]*)modified:.*$", pair[0])
        if m is not None:
            pair[0] = f"{m.group('indent')}modified: {canonical}"
            new_block = "".join(content + ending for content, ending in pairs)
            stamped = text[:block_start] + new_block + text[block_end:]
            return set_body_hash(stamped, digest)

    # Otherwise insert the stamp directly after the ``date:`` anchor line,
    # matching that line's indentation and line ending.
    for idx, pair in enumerate(pairs):
        dm = re.match(r"^(?P<indent>[ \t]*)date:.*$", pair[0])
        if dm is not None:
            indent = dm.group("indent")
            pairs.insert(idx + 1, [f"{indent}modified: {canonical}", pair[1] or "\n"])
            new_block = "".join(content + ending for content, ending in pairs)
            stamped = text[:block_start] + new_block + text[block_end:]
            return set_body_hash(stamped, digest)

    return text


class DocType(StrEnum):
    """Rigidly defined document types corresponding to .vault/ subdirectories."""

    ADR = "adr"
    AUDIT = "audit"
    EXEC = "exec"
    INDEX = "index"
    PLAN = "plan"
    REFERENCE = "reference"
    RESEARCH = "research"

    @property
    def tag(self) -> str:
        """The mandatory directory tag associated with this type.

        Returns:
            Hashtag string such as ``#adr`` or ``#exec``.
        """
        return f"#{self.value}"

    @classmethod
    def from_tag(cls, tag: str) -> DocType | None:
        """Return the DocType that owns the given ``#tag`` string.

        Args:
            tag: Hashtag string such as ``#adr`` or ``#exec``.

        Returns:
            Matching ``DocType``, or ``None`` if the tag is not recognised.
        """
        for dt in cls:
            if dt.tag == tag:
                return dt
        return None


@dataclass
class DocumentMetadata:
    """Rigid representation of YAML frontmatter for all .vault/ files.

    Attributes:
        tags: At least two tags - one directory tag and one feature tag.
            Additional freeform tags are allowed beyond the required pair.
        date: ISO 8601 creation date (``YYYY-MM-DD``).
        modified: CLI-maintained last-modified stamp (``YYYY-MM-DD``, same
            granularity as ``date``). Set equal to ``date`` at scaffold time
            and refreshed by every CLI verb that mutates the document; the
            status rollup reads it as the recency source.
        related: List of Obsidian-style ``[[wiki-link]]`` strings.
        supersedes: List of old ADR/Plan stems.
        superseded_by: Single new ADR/Plan stem.
        derived_from: List of audit/finding references.
        promoted_to: List of rules promoted.
        archived: ISO date (``YYYY-MM-DD``) set on archived documents.
        step_id: Canonical Step identifier (e.g. ``S01``) machine-filled on
            execution records by ``vaultspec-core vault add exec``; ``None`` on
            every other document type and on legacy exec records predating the
            field. Consumed by the exec-mapping health check to back-map a
            record to a live Step in its parent plan.
        body_schema: Immutable body-section contract identifier stamped on new
            scaffolds. ``None`` remains valid for historical documents until
            their hash-attested baseline is introduced.
        body_hash: Machine-filled content fingerprint of the document body,
            written beside ``modified`` by every stamping path and compared
            against the live body to detect unstamped hand edits. ``None``
            means the document makes no claim about its body and earns no
            staleness finding. See :mod:`vaultspec_core.vaultcore.body_hash`
            for the canonical definition.
    """

    tags: list[str] = field(default_factory=list)
    date: str | None = None
    modified: str | None = None
    related: list[str] = field(default_factory=list)
    supersedes: list[str] = field(default_factory=list)
    superseded_by: str | None = None
    derived_from: list[str] = field(default_factory=list)
    promoted_to: list[str] = field(default_factory=list)
    archived: str | None = None
    step_id: str | None = None
    body_schema: str | None = None
    body_hash: str | None = None

    @property
    def parsed_date(self) -> _dt.date | None:
        """Return ``date`` as a calendar date, or ``None`` when it is not one.

        ``date`` is retained as the raw authored string because the
        check/fix reconciliation path has to see the deviation it is asked
        to normalize; canonicalizing it at parse time would make that
        repair invisible. This property is the typed companion: every
        consumer that needs the *value* rather than the authored text -
        above all any consumer that would otherwise let the string decide a
        filesystem path - reads it here and gets a
        :class:`datetime.date` or nothing.

        A ``None`` means the stamp is unparseable. That is a finding, never
        a fatal read: a document with a broken date still parses, still
        lists, and is still repairable. Refusal belongs at the surfaces that
        would act on the value.

        Returns:
            The parsed :class:`datetime.date`, or ``None``.
        """
        return parse_lenient_date(self.date)

    def validate(self) -> list[str]:
        """Validate the metadata against the vault schema rules.

        The ``modified`` stamp follows the lenient policy from the
        vault-orientation ADR (decision D3b): a canonical
        ``yyyy-mm-dd`` value is valid; a value that
        :func:`parse_lenient_date` can parse but is not canonical is
        also accepted here (the ``vault check all --fix``
        reconciliation path normalizes it later rather than validation
        hard-failing on a permitted hand edit); only an unparseable
        value is a violation.

        Returns:
            A list of human-readable violation messages; empty list means valid.
        """
        errors: list[str] = []

        #  Tags: at least one directory tag and one feature tag (minimum 2)
        if len(self.tags) < 2:
            msg = f"Vault violation: At least 2 tags required, found {len(self.tags)}"
            errors.append(msg)

        #  Directory Tag (Type)
        dir_tags = [t for t in self.tags if DocType.from_tag(t)]
        if len(dir_tags) != 1:
            allowed = ", ".join(sorted(dt.tag for dt in DocType))
            msg = (
                "Vault violation: Exactly one directory tag required "
                f"({allowed}). Found: {dir_tags}"
            )
            errors.append(msg)

        #  Feature Tag (Kind)
        feature_tags = [t for t in self.tags if not DocType.from_tag(t)]
        if len(feature_tags) != 1:
            msg = (
                "Vault violation: Exactly one feature tag (#<feature>) required. "
                f"Found: {feature_tags}"
            )
            errors.append(msg)
        elif feature_tags and not re.match(r"^#[a-z0-9-]+$", feature_tags[0]):
            msg = (
                f"Vault violation: Invalid feature tag format '{feature_tags[0]}'. "
                "Must be kebab-case (e.g., #editor-demo)."
            )
            errors.append(msg)

        #  Date Format
        if not self.date:
            errors.append("Vault violation: 'date' field is required.")
        elif not re.match(r"^\d{4}-\d{2}-\d{2}$", self.date):
            msg = (
                f"Vault violation: Invalid date format '{self.date}'. "
                "Must be YYYY-MM-DD."
            )
            errors.append(msg)

        #  Modified Stamp: canonical ok; lenient-parseable noncanonical ok
        #  (normalized later by the check/fix path); unparseable is a
        #  violation (D3b: flagged, never silently dropped).
        if (
            self.modified
            and not _CANONICAL_DATE_RE.match(self.modified)
            and parse_lenient_date(self.modified) is None
        ):
            msg = (
                f"Vault violation: Unparseable modified date '{self.modified}'. "
                "Must be a date in (or normalizable to) YYYY-MM-DD form."
            )
            errors.append(msg)

        #  Related Wiki-links
        for link in self.related:
            if not (link.startswith("[[") and link.endswith("]]")):
                msg = (
                    f"Vault violation: Invalid related link '{link}'. "
                    "Must be a quoted [[wiki-link]]."
                )
                errors.append(msg)

        #  Archived Date Format
        if self.archived and not re.match(r"^\d{4}-\d{2}-\d{2}$", self.archived):
            msg = (
                f"Vault violation: Invalid archived date format '{self.archived}'. "
                "Must be YYYY-MM-DD."
            )
            errors.append(msg)

        return errors


class VaultConstants:
    """Static configuration and validation helpers for the ``.vault/`` structure.

    Class-level sets (:data:`SUPPORTED_DIRECTORIES`, :data:`SUPPORTED_TAGS`) enumerate
    the valid subdirectory names and their corresponding ``#tags``. Class methods
    validate directory layout, filename conventions, and tag-to-directory mapping.
    """

    @staticmethod
    def _get_docs_dir() -> str:
        """Return the configured docs directory name (e.g. ``.vault``).

        Returns:
            Directory name string such as ``".vault"``.
        """
        from ..config import get_config

        return get_config().docs_dir

    @staticmethod
    def _get_index_dir() -> str:
        """Return the configured index subdirectory name (e.g. ``index``).

        Returns:
            Directory name string such as ``"index"``.
        """
        from ..config import get_config

        return get_config().index_dir

    # Supported directories within .vault/ (one per DocType, including INDEX
    # which now lives in its own subfolder rather than at the vault root).
    SUPPORTED_DIRECTORIES: ClassVar[set[str]] = {dt.value for dt in DocType}

    # Non-document directories that are legitimate .vault/ content
    # (e.g. data stores, log output) but not document types.
    AUXILIARY_DIRECTORIES: ClassVar[set[str]] = {"data", "logs", "_archive"}

    # Supported directory tags (one per DocType, including #index).
    SUPPORTED_TAGS: ClassVar[set[str]] = {dt.tag for dt in DocType}

    @classmethod
    def is_supported_directory(cls, dirname: str) -> bool:
        """Return whether *dirname* is a recognized vault subdirectory.

        Checks both document directories (:data:`SUPPORTED_DIRECTORIES`) and
        non-document auxiliary directories (:data:`AUXILIARY_DIRECTORIES`).

        Args:
            dirname: Bare directory name (e.g. ``"adr"``, ``"data"``).

        Returns:
            ``True`` if the directory is recognized.
        """
        return (
            dirname in cls.SUPPORTED_DIRECTORIES or dirname in cls.AUXILIARY_DIRECTORIES
        )

    @classmethod
    def validate_vault_structure(cls, root_dir: Path) -> list[str]:
        """Ensure the docs directory only contains recognised subdirectories.

        The vault root must contain only the seven canonical document
        subdirectories (one per :class:`DocType`, including the
        :class:`DocType.INDEX` subfolder), the auxiliary data/log
        directories, and an optional ``readme.md``. Files at the docs
        root are violations: ``<feature>.index.md`` files at the root are
        legacy artifacts that should be relocated into the index
        subfolder.

        Args:
            root_dir: Project root containing the docs directory.

        Returns:
            List of violation message strings; empty when the structure is
            valid.
        """
        docs_dir_name = cls._get_docs_dir()
        index_dir_name = cls._get_index_dir()
        docs_dir = root_dir / docs_dir_name
        if not docs_dir.exists():
            return []

        errors: list[str] = []
        # Check for unsupported directories
        for item in docs_dir.iterdir():
            if item.is_dir():
                if item.name.startswith("."):
                    # Allow internal hidden folders like .obsidian
                    continue
                if not cls.is_supported_directory(item.name):
                    msg = (
                        "Vault violation: Unsupported directory found in "
                        f"{docs_dir_name}/: '{item.name}'"
                    )
                    errors.append(msg)
            elif item.is_file():
                if item.name.lower() == "readme.md":
                    continue
                if item.name.endswith(".index.md"):
                    msg = (
                        f"Vault violation: Legacy feature index '{item.name}' "
                        f"at {docs_dir_name}/ root. Index files now live in "
                        f"{docs_dir_name}/{index_dir_name}/. Run "
                        "'vaultspec-core migrations run' to apply the "
                        "registered schema migration."
                    )
                    errors.append(msg)
                    continue
                msg = (
                    f"Vault violation: File found in {docs_dir_name}/ root: "
                    f"'{item.name}'. Files should be in subdirectories."
                )
                errors.append(msg)

        return errors

    @classmethod
    def validate_filename(
        cls, filename: str, doc_type: DocType | None = None
    ) -> list[str]:
        """Validate a filename against the vault naming convention.

        Expected pattern: ``yyyy-mm-dd-<feature>-<type>.md`` for the six
        authored document types, and ``<feature>.index.md`` (no date
        prefix) for the auto-generated :class:`DocType.INDEX` files.

        Args:
            filename: Bare filename (no directory component) to validate.
            doc_type: When provided, also checks that the filename's type
                suffix matches this ``DocType``.

        Returns:
            List of violation message strings; empty when the filename is valid.
        """
        errors: list[str] = []

        if not filename.endswith(".md"):
            msg = f"Vault violation: Filename '{filename}' must have .md extension."
            errors.append(msg)
            return errors

        # Index files use a separate naming convention: <feature>.index.md
        # (no date prefix, no document-type suffix).
        if doc_type == DocType.INDEX or filename.endswith(".index.md"):
            index_pattern = r"^[a-z0-9-]+\.index\.md$"
            if not re.match(index_pattern, filename):
                msg = (
                    f"Vault violation: Index filename '{filename}' deviates "
                    "from standard <feature>.index.md pattern."
                )
                errors.append(msg)
            return errors

        # Execution records use the plan-hardening Step Record / Phase Summary
        # naming: uppercase canonical container ids (with an optional lowercase
        # alpha suffix on Wave / Phase) and no '-exec' type token, matching what
        # 'vault add exec --step' scaffolds and what the framework rules
        # document (issue #123). The legacy '...-exec' form is still accepted via
        # the generic pattern below for records authored before the convention.
        if doc_type == DocType.EXEC:
            date_feature = r"\d{4}-\d{2}-\d{2}-[a-z0-9-]+"
            step_record = (
                rf"^{date_feature}-(W\d{{2,}}[a-z]?-)?(P\d{{2,}}[a-z]?-)?"
                r"S\d{2,}\.md$"
            )
            phase_summary = (
                rf"^{date_feature}-(W\d{{2,}}[a-z]?-)?P\d{{2,}}[a-z]?-summary\.md$"
            )
            # One consolidated ledger per plan carries no container id at all:
            # the Step identity lives in its rows, not its filename. It must be
            # declared here beside the other exec conventions, or the generic
            # pattern below rejects it and `--fix` renames it to
            # '...-ledger-exec.md', which no longer reads as a ledger.
            ledger = rf"^{date_feature}-ledger\.md$"
            if (
                re.match(step_record, filename)
                or re.match(phase_summary, filename)
                or re.match(ledger, filename)
            ):
                return errors

        # Basic pattern: 2026-02-07-feature-name-adr.md
        # Or for exec: 2026-02-07-feature-name-phase1-step1.md
        pattern = (
            r"^\d{4}-\d{2}-\d{2}-[a-z0-9-]+-"
            r"(adr|audit|exec|plan|reference|research)(-[a-z0-9-]+)*\.md$"
        )
        if not re.match(pattern, filename):
            msg = (
                f"Vault violation: Filename '{filename}' deviates from "
                "standard yyyy-mm-dd-<feature>-<type>.md pattern."
            )
            errors.append(msg)
            return errors

        # If doc_type is provided, ensure it matches the filename suffix
        if doc_type:
            suffix = f"-{doc_type.value}"
            # Special case for exec records
            if doc_type == DocType.EXEC:
                if f"-{DocType.EXEC.value}" not in filename:
                    msg = (
                        f"Vault violation: Filename '{filename}' does not "
                        "contain expected type suffix '-exec'."
                    )
                    errors.append(msg)
            else:
                if not filename.endswith(f"{suffix}.md"):
                    msg = (
                        f"Vault violation: Filename '{filename}' does not "
                        f"match expected type suffix '{suffix}.md'."
                    )
                    errors.append(msg)

        return errors
