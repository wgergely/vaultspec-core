"""Feature rename planning (``vaultspec-core vault feature rename``).

``rename_feature`` (in :mod:`.query_rename_apply`) atomically renames a
``#feature`` across every binding surface: authored document filenames, the
exec folder and exec record filenames, the ``#feature`` frontmatter tag,
``related:`` wiki-links, and the regenerated feature index. Free-form body
prose is never touched.

This module holds the side-effect-free half of that pipeline: request
validation, the anchored path-segment transforms, the frontmatter tag-block
rewriter, and full plan computation (with collision detection and the
dry-run preview predictors). :mod:`.query_rename_apply` holds the
transactional apply-with-rollback half and the public ``rename_feature``
entry point. Split out of :mod:`.query`, which re-exports both halves for
compatibility.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict, cast

from .models import DocType
from .normalize import WINDOWS_RESERVED_NAMES
from .query_listing import VaultDocument, list_documents
from .rename_ops import split_keepends

if TYPE_CHECKING:
    from pathlib import Path

    from .query_archive import FeatureCrossLink

logger = logging.getLogger(__name__)

# These names are consumed by :mod:`.query` (compatibility re-export) and
# :mod:`.query_rename_apply` (the transactional apply half of the rename
# pipeline); the explicit re-export marks that cross-module contract for the
# type checker.
__all__ = [
    "RenamePlan",
    "analyze_cross_feature_links",
    "assert_within_docs",
    "compute_rename_plan",
    "predict_rewrites",
    "rel",
    "rewrite_feature_tag_block",
    "validate_feature_rename",
]


class RenameCollision(TypedDict):
    """One destination collision detected while planning a feature rename."""

    destination: str
    sources: list[str]
    reason: str


#: Kebab-case gate for a rename target, mirroring ``vault add`` time
#: (``vault_cmd.py``) and the schema feature-tag form (``models.py``).
_FEATURE_KEBAB_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_FEATURE_TAG_FORM_RE = re.compile(r"^#[a-z0-9-]+$")

#: A single block-sequence ``tags:`` entry, capturing the dash/indent
#: prefix, an optional surrounding quote, the ``#tag`` value, and any
#: trailing whitespace so the rewrite can preserve the original style.
_FEATURE_TAG_LINE_RE = re.compile(r"^(\s*-\s*)(['\"]?)(#[\w-]+)\2(\s*)$")

#: A ``related:`` block-sequence wiki-link entry, used by the read-only
#: dry-run predictor to estimate how many incoming links would be rewritten.
_RELATED_LINK_RE = re.compile(r'^\s*-\s*["\']?\[\[(.+?)\]\]["\']?.*$')

#: Windows reserved device base names. A feature whose name is one of these
#: produces an index path (``<name>.index.md``) the OS treats as a device,
#: which would fail mid-apply; rename rejects them up front. Re-exported from
#: :mod:`.normalize`, the one owner of the set - ``vault add`` and every
#: other entry point reject it there too, via ``normalize_feature_tag``.
_WINDOWS_RESERVED_NAMES = WINDOWS_RESERVED_NAMES


def assert_within_docs(docs_dir: Path, path: Path) -> Path:
    """Return *path* iff its real location is inside *docs_dir*, else raise.

    Thin docs-scoped wrapper over the root-generalized
    :func:`~vaultspec_core.vaultcore.rename_engine.assert_within`; retained as
    a stable import surface for callers and tests that bind the containment
    guard to the vault document root.

    Args:
        docs_dir: The vault document root (``<root>/<docs_dir>``).
        path: A candidate source or destination path inside the rename plan.

    Returns:
        *path* unchanged when it is contained.

    Raises:
        VaultSpecError: When *path* resolves outside *docs_dir*.
    """
    from .rename_engine import assert_within

    return assert_within(docs_dir, path)


@dataclass
class RenamePlan:
    """A fully-computed rename plan that mutates nothing on its own.

    Attributes:
        file_renames: ``(src, dst)`` pairs for every authored document and
            exec record whose filename carries the feature segment.
        exec_dir_renames: ``(old_folder, new_folder, plan_date)`` triples
            for every ``.vault/exec/{plan_date}-{feature}/`` folder.
        index_old_path: Path to the existing feature index, or ``None``.
        index_new_path: Path the regenerated index will occupy.
        stem_renames: ``(old_stem, new_stem)`` pairs fed to the
            ``related:`` wiki-link cascade.
        collisions: Per-file destination collisions that force a refusal.
    """

    file_renames: list[tuple[Path, Path]]
    exec_dir_renames: list[tuple[Path, Path, str]]
    index_old_path: Path | None
    index_new_path: Path
    stem_renames: list[tuple[str, str]]
    collisions: list[RenameCollision]


def rel(path: Path, root_dir: Path) -> str:
    """Return *path* relative to *root_dir*, or its string form on failure."""
    try:
        return str(path.relative_to(root_dir))
    except ValueError:
        return str(path)


def _same_file(a: Path, b: Path) -> bool:
    """Return ``True`` when *a* and *b* identify the same on-disk file."""
    try:
        return a.samefile(b)
    except OSError:
        return False


# -- S05: validation helpers ------------------------------------------------


def validate_feature_rename(
    root_dir: Path, old: str, new: str, *, force: bool
) -> tuple[str, str, list[VaultDocument]]:
    """Validate a feature rename request before any plan is computed.

    Enforces: non-empty source and target (after ``strip().lstrip('#')``);
    a target distinct from the source; a kebab-case, schema-valid target
    tag; a target that is not a reserved :class:`DocType` value; a source
    that matches at least one non-archived document; and - unless *force* -
    a target that currently owns zero documents.

    Args:
        root_dir: Project root directory.
        old: Raw source feature tag (leading ``#`` tolerated).
        new: Raw target feature tag (leading ``#`` tolerated).
        force: When ``True``, permit merging into an existing feature.

    Returns:
        ``(old_clean, new_clean, src_docs)`` - the normalised feature names
        and the source feature's documents.

    Raises:
        VaultSpecError: When any guard fails.
    """
    from ..core.exceptions import VaultSpecError

    old_clean = old.strip().lstrip("#").strip()
    new_clean = new.strip().lstrip("#").strip()

    if not old_clean:
        raise VaultSpecError(
            "A source feature tag is required to rename. Refusing to run with "
            "an empty tag, which would match every document."
        )
    if not new_clean:
        raise VaultSpecError(
            "A target feature tag is required to rename. Refusing to run with "
            "an empty target tag."
        )
    if old_clean == new_clean:
        raise VaultSpecError(
            f"Source and target feature are identical ('{old_clean}'); there "
            "is nothing to rename."
        )
    # Shape-gate the SOURCE too (defense in depth): a well-formed feature tag is
    # kebab-case by schema, so a source carrying path separators, ``..``, control
    # characters, or other metacharacters is never a real feature and must be
    # rejected explicitly rather than relying on it incidentally matching zero
    # documents.
    if not _FEATURE_KEBAB_RE.match(old_clean):
        raise VaultSpecError(
            f"Source feature '{old_clean}' is not a valid feature tag. It must "
            "be kebab-case matching ^[a-z0-9][a-z0-9-]*$."
        )
    if not _FEATURE_KEBAB_RE.match(new_clean) or not _FEATURE_TAG_FORM_RE.match(
        f"#{new_clean}"
    ):
        raise VaultSpecError(
            f"Target feature '{new_clean}' is not a valid feature tag. It must "
            "be kebab-case matching ^[a-z0-9][a-z0-9-]*$ (e.g. 'editor-demo')."
        )
    reserved = {dt.value for dt in DocType}
    if new_clean in reserved:
        raise VaultSpecError(
            f"Target feature '{new_clean}' is a reserved document-type name "
            f"({', '.join(sorted(reserved))}). A feature tag with that name is "
            "invisible to the feature scanner; choose a different name."
        )
    if new_clean in _WINDOWS_RESERVED_NAMES:
        raise VaultSpecError(
            f"Target feature '{new_clean}' is a reserved device name on Windows; "
            "the regenerated index filename would be invalid. Choose another name."
        )

    src_docs = list_documents(root_dir, feature=old_clean)
    if not src_docs:
        raise VaultSpecError(f"Source feature '{old_clean}' matches zero documents.")

    if not force:
        dst_docs = list_documents(root_dir, feature=new_clean)
        if dst_docs:
            raise VaultSpecError(
                f"Target feature '{new_clean}' already has {len(dst_docs)} "
                "document(s). Re-run with --force to merge the source feature "
                "into it."
            )

    return old_clean, new_clean, src_docs


# -- S06: anchored, date-keyed feature-segment path transforms --------------


def _swap_authored_filename(name: str, old: str, new: str) -> str | None:
    """Swap only the feature segment of an authored-doc filename.

    Anchored on the ``YYYY-MM-DD`` date prefix and the ``-{old}-`` boundary,
    so a prefix collision (``old`` is a prefix of another feature) cannot
    over-match.  Any suffix after the feature segment - the type token and,
    for audits, an optional narrative topic infix - is preserved verbatim.

    Args:
        name: Bare filename (e.g. ``2026-06-26-old-adr.md`` or
            ``2026-06-26-old-perf-audit.md``).
        old: Current feature name (without ``#``).
        new: Replacement feature name (without ``#``).

    Returns:
        The rewritten filename, or ``None`` when *name* does not carry the
        ``{date}-{old}-`` feature segment.
    """
    pattern = rf"^(\d{{4}}-\d{{2}}-\d{{2}})-{re.escape(old)}(-.+\.md)$"
    m = re.match(pattern, name)
    if m is None:
        return None
    return f"{m.group(1)}-{new}{m.group(2)}"


def _match_exec_folder_date(folder_name: str, old: str) -> str | None:
    """Return the plan date of a ``{plan_date}-{old}`` exec folder, or ``None``."""
    m = re.match(rf"^(\d{{4}}-\d{{2}}-\d{{2}})-{re.escape(old)}$", folder_name)
    return m.group(1) if m else None


def _swap_exec_filename(name: str, plan_date: str, old: str, new: str) -> str | None:
    """Swap the feature segment of an exec record, preserving *plan_date*.

    The ``{plan_date}`` prefix is the parent plan's date - which may differ
    from the record's own ``date:`` frontmatter - and is held fixed; only
    the ``{old}`` token immediately after it is replaced.

    Args:
        name: Bare exec record filename
            (e.g. ``2026-06-26-old-P01-S01.md``).
        plan_date: The exec folder's date prefix.
        old: Current feature name (without ``#``).
        new: Replacement feature name (without ``#``).

    Returns:
        The rewritten filename, or ``None`` when *name* does not start with
        the ``{plan_date}-{old}-`` prefix.
    """
    prefix = f"{plan_date}-{old}-"
    if not name.startswith(prefix):
        return None
    return f"{plan_date}-{new}-{name[len(prefix) :]}"


# -- S07: feature tag-block rewriter ----------------------------------------


def _parse_inline_tags(after: str) -> list[str]:
    """Parse an inline (flow) ``tags:`` value into a list of tag strings.

    Args:
        after: The text following ``tags:`` on the key line, already
            stripped (e.g. ``"['#adr', '#old']"`` or ``"'#adr'"``).

    Returns:
        The tag strings in source order.

    Raises:
        VaultSpecError: When *after* is not a parseable YAML scalar or
            sequence of strings - raising here forces a refusal rather than
            writing corrupt YAML.
    """
    import yaml

    from ..core.exceptions import VaultSpecError

    try:
        parsed: object = yaml.safe_load(f"tags: {after}")
    except yaml.YAMLError as exc:
        raise VaultSpecError(
            f"Cannot parse inline tags value {after!r}: {exc}"
        ) from exc

    value = (
        cast("dict[str, object]", parsed).get("tags")
        if isinstance(parsed, dict)
        else None
    )
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(t) for t in cast("list[object]", value)]
    raise VaultSpecError(f"Inline tags value is not a sequence: {after!r}")


def rewrite_feature_tag_block(content: str, old: str, new: str) -> tuple[str, bool]:
    """Rewrite the single ``#old`` feature tag to ``#new`` in ``tags:``.

    Operates strictly on the YAML ``tags:`` block inside the leading
    frontmatter fence; the directory tag, every other line, body prose, the
    CRLF/LF line-ending convention, and a leading UTF-8 BOM are preserved.
    A flow-style ``tags: ['#a', '#b']`` value is first normalised to block
    form (borrowing the approach in :mod:`.related_surgery`) so the rewrite
    is robust on imperfect inputs.

    Args:
        content: Full document text including frontmatter.
        old: Current feature name (without ``#``).
        new: Replacement feature name (without ``#``).

    Returns:
        ``(new_content, changed)`` where *changed* indicates whether the
        ``#old`` tag was present and rewritten.
    """
    old_tag = f"#{old}"
    new_tag = f"#{new}"

    bom = ""
    body = content
    if body.startswith("\ufeff"):
        bom = "\ufeff"
        body = body[1:]
    # Model each line as a mutable ``[content, ending]`` pair so the rewrite
    # replaces only the content of the single tag line it targets while every
    # other byte - including mixed/CR-only endings, an absent trailing
    # terminator, and exotic in-line separators in body prose - survives
    # verbatim. Splitting on \r\n / \r / \n only (never the exotic Unicode
    # separators) is what fixes the corruption.
    pairs = split_keepends(body)

    out: list[list[str]] = []
    changed = False
    in_frontmatter = False
    closed = False
    fence = 0
    i = 0
    n = len(pairs)

    while i < n:
        line, ending = pairs[i]
        stripped = line.strip()

        if stripped == "---":
            fence += 1
            out.append([line, ending])
            i += 1
            if fence == 1:
                in_frontmatter = True
                continue
            # Closing fence reached: copy the remainder of the file verbatim.
            closed = True
            out.extend(pairs[i:])
            break

        if not in_frontmatter:
            out.append([line, ending])
            i += 1
            continue

        if stripped.startswith("tags:"):
            after = line.split("tags:", 1)[1].strip()
            indent = line[: len(line) - len(line.lstrip())]
            if after and after != "[]":
                # Inline / flow form: normalise to block form, swapping the
                # feature tag in the process. Every synthesized block line
                # inherits the original ``tags:`` line's ending so a CRLF doc
                # yields CRLF block entries (``ending or "\n"`` guards the
                # degenerate case of the tag line lacking a terminator).
                tag_list = _parse_inline_tags(after)
                new_list = [new_tag if t == old_tag else t for t in tag_list]
                if new_list != tag_list:
                    changed = True
                synth = ending or "\n"
                out.append([f"{indent}tags:", synth])
                out.extend([f"{indent}  - '{t}'", synth] for t in new_list)
                i += 1
                continue
            # Block form: walk the indented dash entries and rewrite the one
            # carrying the feature tag.
            out.append([line, ending])
            i += 1
            while i < n:
                entry, entry_ending = pairs[i]
                if entry.startswith((" ", "\t")) and entry.lstrip().startswith("-"):
                    m = _FEATURE_TAG_LINE_RE.match(entry)
                    if m is not None and m.group(3) == old_tag:
                        quote = m.group(2)
                        out.append(
                            [
                                f"{m.group(1)}{quote}{new_tag}{quote}{m.group(4)}",
                                entry_ending,
                            ]
                        )
                        changed = True
                    else:
                        out.append([entry, entry_ending])
                    i += 1
                    continue
                break
            continue

        out.append([line, ending])
        i += 1

    # Refuse to persist a rewrite of a document whose frontmatter never closed:
    # an opening ``---`` with no terminating fence is malformed, and treating the
    # whole file as frontmatter could mutate body lines that merely look like
    # tag entries. Mirror the closing-fence guard in ``rewrite_incoming_refs``.
    if in_frontmatter and not closed:
        return content, False

    # Reassemble from the pairs: each line carries its own original terminator,
    # so the trailing newline (or its absence) and every mixed ending are
    # reproduced exactly. The BOM is re-prepended.
    result = bom + "".join(c + e for c, e in out)
    return result, changed


# -- S08: plan computation + collision detection ----------------------------


def compute_rename_plan(
    root_dir: Path, old: str, new: str, src_docs: list[VaultDocument]
) -> RenamePlan:
    """Build the full rename plan without mutating anything on disk.

    Args:
        root_dir: Project root directory.
        old: Normalised source feature name.
        new: Normalised target feature name.
        src_docs: The source feature's documents (from
            :func:`list_documents`).

    Returns:
        A :class:`RenamePlan` describing every file rename, exec-folder
        rename, the index plan, the wiki-link stem map, and any per-file
        destination collisions.

    Raises:
        VaultSpecError: When a document or exec folder does not match the
            expected feature-segment shape and so cannot be transformed.
    """
    from ..config import get_config
    from ..core.exceptions import VaultSpecError

    cfg = get_config()
    index_dir = root_dir / cfg.docs_dir / cfg.index_dir

    authored_renames: list[tuple[Path, Path]] = []
    exec_docs: list[VaultDocument] = []
    index_old_path: Path | None = None

    for doc in src_docs:
        if doc.doc_type == "index" or doc.name.endswith(".index"):
            index_old_path = doc.path
            continue
        if doc.doc_type == "exec":
            exec_docs.append(doc)
            continue
        new_name = _swap_authored_filename(doc.path.name, old, new)
        if new_name is None:
            date_seg = f"{doc.date}-" if doc.date else ""
            raise VaultSpecError(
                f"Cannot rename feature '{old}': document '{doc.path.name}' is "
                f"tagged '#{old}' but its filename does not begin with the "
                f"feature segment '{date_seg}{old}-' (its filename uses a "
                "narrative segment). 'vault feature rename' currently only "
                "renames features whose document filenames encode the feature "
                "tag; rename is refused to avoid a partial rename."
            )
        authored_renames.append((doc.path, doc.path.with_name(new_name)))

    # Discover each distinct exec folder, then rename every record inside it.
    exec_folder_dates: dict[Path, str] = {}
    for doc in exec_docs:
        folder = doc.path.parent
        if folder in exec_folder_dates:
            continue
        plan_date = _match_exec_folder_date(folder.name, old)
        if plan_date is None:
            raise VaultSpecError(
                f"Exec folder '{folder.name}' does not match the expected "
                f"'{{date}}-{old}' shape; refusing to rename."
            )
        exec_folder_dates[folder] = plan_date

    exec_dir_renames: list[tuple[Path, Path, str]] = []
    exec_record_renames: list[tuple[Path, Path]] = []
    for folder, plan_date in exec_folder_dates.items():
        new_folder = folder.with_name(f"{plan_date}-{new}")
        exec_dir_renames.append((folder, new_folder, plan_date))
        for record in sorted(folder.glob("*.md")):
            if not record.is_file():
                continue
            new_name = _swap_exec_filename(record.name, plan_date, old, new)
            if new_name is None:
                raise VaultSpecError(
                    f"Cannot derive a renamed exec record filename for "
                    f"'{record.name}' in folder '{folder.name}'."
                )
            exec_record_renames.append((record, new_folder / new_name))

    file_renames = authored_renames + exec_record_renames

    # Collision detection: two sources mapping to one destination, or a file
    # already sitting at a destination (the merge hazard under --force).
    collisions: list[RenameCollision] = []
    # Key on the normalised-case path so two sources whose destinations differ
    # only by case (which collide to one file on a case-insensitive filesystem)
    # are detected up front rather than only at apply time.
    seen_dest: dict[str, Path] = {}
    for src, dst in file_renames:
        dkey = os.path.normcase(str(dst))
        if dkey in seen_dest:
            collisions.append(
                {
                    "destination": rel(dst, root_dir),
                    "sources": [rel(seen_dest[dkey], root_dir), rel(src, root_dir)],
                    "reason": "two source files map to the same destination",
                }
            )
        else:
            seen_dest[dkey] = src
        if dst.is_file() and not _same_file(src, dst):
            collisions.append(
                {
                    "destination": rel(dst, root_dir),
                    "sources": [rel(src, root_dir)],
                    "reason": "a file already exists at the destination",
                }
            )

    index_new_path = index_dir / f"{new}.index.md"

    stem_renames: list[tuple[str, str]] = [
        (src.stem, dst.stem) for src, dst in file_renames
    ]
    if index_old_path is not None:
        stem_renames.append((f"{old}.index", f"{new}.index"))

    return RenamePlan(
        file_renames=file_renames,
        exec_dir_renames=exec_dir_renames,
        index_old_path=index_old_path,
        index_new_path=index_new_path,
        stem_renames=stem_renames,
        collisions=collisions,
    )


def analyze_cross_feature_links(
    root_dir: Path, docs: list[VaultDocument], feature: str
) -> list[FeatureCrossLink]:
    """Find incoming wiki-links from other features (mirrors ``archive``).

    Unlike archive (which can only warn that these may dangle), a rename
    actually rewrites them; the analysis is reported for parity and so a
    caller can show what the cascade touched.

    Args:
        root_dir: Project root directory.
        docs: The feature's documents.
        feature: The feature name being renamed (without ``#``).

    Returns:
        A list of ``{source, target, source_path}`` dicts.
    """
    cross_links: list[FeatureCrossLink] = []
    try:
        from ..graph import VaultGraph

        # ``use_cache=False`` so this read-only reporting pass never persists a
        # graph cache to disk - a dry-run must mutate nothing, and a real run
        # invalidates the cache from the CLI afterwards regardless.
        graph = VaultGraph(root_dir, use_cache=False)
        for doc in docs:
            node = graph.nodes.get(doc.name) or graph.nodes.get(
                f"{doc.doc_type}/{doc.name}"
            )
            if not node:
                continue
            for src_name in node.in_links:
                src_node = graph.nodes.get(src_name)
                if src_node and src_node.feature != feature:
                    cross_links.append(
                        {
                            "source": src_name,
                            "target": node.name,
                            "source_path": str(src_node.path.relative_to(root_dir))
                            if src_node.path
                            else src_name,
                        }
                    )
    except Exception as exc:
        logger.warning("Could not analyze cross-feature links: %s", exc)
    return cross_links


def predict_rewrites(
    root_dir: Path, plan: RenamePlan, old: str, new: str
) -> tuple[int, int]:
    """Predict tag and incoming-link rewrite counts without mutating.

    Used only for the ``dry_run`` plan preview.  The tag count is exact (it
    runs the real rewriter in memory against each source file); the related
    count is an estimate of how many ``related:`` entries reference a renamed
    stem.

    Args:
        root_dir: Project root directory.
        plan: The computed rename plan.
        old: Normalised source feature name.
        new: Normalised target feature name.

    Returns:
        ``(predicted_tag_rewrites, predicted_related_rewrites)``.
    """
    from ..config import get_config

    tag_rewrites = 0
    for src, _dst in plan.file_renames:
        # Never read through a symlinked source during the dry-run preview: the
        # apply path refuses it via ``assert_within_docs``, so the preview must
        # not read its out-of-bounds target either (mirrors the related-count
        # loop below and keeps dry-run and apply symmetric).
        if src.is_symlink():
            continue
        try:
            text = src.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        _new_text, changed = rewrite_feature_tag_block(text, old, new)
        if changed:
            tag_rewrites += 1

    old_stems = {o.lower() for o, n in plan.stem_renames if o != n}
    related_rewrites = 0
    if old_stems:
        docs_dir = root_dir / get_config().docs_dir
        if docs_dir.is_dir():
            for md in docs_dir.rglob("*.md"):
                rel_parts = md.relative_to(docs_dir).parts
                if any(p == "_archive" or p.startswith(".") for p in rel_parts):
                    continue
                if md.is_symlink() or not md.is_file():
                    continue
                related_rewrites += _count_related_refs(md, old_stems)

    return tag_rewrites, related_rewrites


def _count_related_refs(md_path: Path, old_stems_lower: set[str]) -> int:
    """Count ``related:`` wiki-link entries whose stem is in *old_stems_lower*."""
    try:
        text = md_path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return 0

    count = 0
    in_frontmatter = False
    in_related = False
    # Use the same canonical line-splitting as the cascade (only \r\n / \r / \n,
    # never the exotic Unicode separators) so the dry-run predicted count matches
    # what ``rewrite_incoming_refs`` would actually rewrite.
    for line, _ending in split_keepends(text):
        stripped = line.strip()
        if stripped == "---":
            if not in_frontmatter:
                in_frontmatter = True
                continue
            break
        if not in_frontmatter:
            continue
        if stripped.startswith("related:"):
            in_related = True
            continue
        if in_related and line and not line.startswith((" ", "\t", "-")):
            in_related = False
        if not in_related:
            continue
        m = _RELATED_LINK_RE.match(line)
        if m is None:
            continue
        target = m.group(1)
        for cut in ("#", "|"):
            idx = target.find(cut)
            if idx >= 0:
                target = target[:idx]
        if target.strip().lower() in old_stems_lower:
            count += 1
    return count
