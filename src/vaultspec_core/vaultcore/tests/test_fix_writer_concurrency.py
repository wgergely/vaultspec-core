"""Concurrency-safety tests for the ``--fix`` and ``repair`` document writers.

Every writer that reads a vault document, computes a replacement, and writes it
back must hold that document's per-document advisory lock
(:func:`~vaultspec_core.vaultcore.edit_engine.document_lock_target`) across the
WHOLE cycle, exactly as :func:`~vaultspec_core.vaultcore.edit_engine.execute_edit`
does. Locking only the write is worthless: the replacement was already derived
from a revision a concurrent editor may have superseded, so it lands as an
individually-atomic overwrite of content that was never read - a silent lost
update, with no error on either side and a success report from the writer whose
work was discarded.

These tests prove the commitment the same way ``test_rename_concurrency`` proves
the docs-domain one: a holder thread takes the sentinel and the writer under test
must be unable to complete until the holder releases. That proof is deterministic
and mock-free - the only timed wait is a bounded ``Event.wait`` used to assert the
writer is blocked WHILE the holder still holds the lock, and the holder releases
only after that assertion, so a pass cannot be a timing fluke.

:func:`test_concurrent_edit_survives_a_fix_pass` adds the end-to-end statement of
the bug itself: an editor writing under the document lock, contending with a fix
pass, never has its revision discarded. Its interleaving is genuinely racy rather
than sequenced, so it is a probabilistic detector of a regression, not a
deterministic one; the serialization proofs above are the deterministic half.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import pytest

from ...config import reset_config
from ...core.helpers import advisory_lock, atomic_write
from ..checks.adr_status import check_adr_status
from ..checks.annotations import check_annotations
from ..checks.body_links import check_body_links
from ..checks.frontmatter import check_frontmatter
from ..checks.links import check_links
from ..checks.markdown import check_markdown
from ..checks.modified_stamp import check_modified_stamp
from ..checks.references import check_schema
from ..edit_engine import document_lock_target
from ..models import DocumentMetadata
from ..repair import _restamp_modified

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from pathlib import Path

    from ..checks._base import VaultSnapshot

pytestmark = [pytest.mark.unit]


# Bounded wait used to confirm the writer is blocked while the holder holds the
# lock. The holder releases only after this window elapses, so the probe cannot
# pass by luck - the writer genuinely cannot complete.
_BLOCKED_PROBE_SECONDS = 0.5
# Generous ceiling for an unblocked writer to finish once the lock is free.
_COMPLETION_SECONDS = 10.0
# Iterations of the racy end-to-end probe. Against the pre-fix writers this
# loop discarded 199 of 300 committed edits, and a standalone run driving the
# editor through the full `execute_edit` pipeline discarded 9 of 300, so a few
# hundred iterations catch a regression with overwhelming probability while the
# loop still finishes in tens of seconds.
_RACE_ITERATIONS = 300


@pytest.fixture(autouse=True)
def reset_cfg() -> Generator[None]:
    """Reset the process-global config to defaults around every test."""
    reset_config()
    yield
    reset_config()


def _write(path: Path, text: str) -> None:
    """Write *text* to *path*, creating parents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _vault(tmp_path: Path) -> Path:
    """Return a project root with the lock-sentinel directory materialised."""
    (tmp_path / ".vault" / "data").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _prove_serialized_by(lock_target: Path, writer: Callable[[], None]) -> None:
    """Assert *writer* blocks on *lock_target* until a holder releases it.

    Spawns a holder thread that acquires ``advisory_lock(lock_target)`` and
    holds it, then runs *writer* in a worker thread. The worker is asserted to
    be unable to finish while the holder holds the lock, and to finish once the
    holder releases.

    Args:
        lock_target: The sentinel both the holder and *writer* contend on.
        writer: A zero-arg callable performing the lock-protected work.
    """
    # ``advisory_lock`` deliberately no-ops when its sentinel's parent is
    # absent, so the holder must materialise it before acquiring: a holder that
    # silently held nothing would let the writer through and the probe would
    # report the exact failure it is meant to detect for the wrong reason.
    lock_target.parent.mkdir(parents=True, exist_ok=True)

    holder_acquired = threading.Event()
    release_holder = threading.Event()
    worker_done = threading.Event()
    errors: list[BaseException] = []

    def _holder() -> None:
        with advisory_lock(lock_target):
            holder_acquired.set()
            assert release_holder.wait(timeout=_COMPLETION_SECONDS)

    def _worker() -> None:
        try:
            assert holder_acquired.wait(timeout=_COMPLETION_SECONDS)
            writer()
            worker_done.set()
        except BaseException as exc:  # surfaced via the post-join assertion
            errors.append(exc)

    holder = threading.Thread(target=_holder, name="lock-holder")
    worker = threading.Thread(target=_worker, name="fix-writer")
    holder.start()
    assert holder_acquired.wait(timeout=_COMPLETION_SECONDS)

    worker.start()
    assert not worker_done.wait(timeout=_BLOCKED_PROBE_SECONDS), (
        "the fix writer completed while the document lock was held - it is "
        "deriving and writing a replacement outside the per-document lock, so "
        "a concurrent edit can be silently overwritten"
    )

    release_holder.set()
    assert worker_done.wait(timeout=_COMPLETION_SECONDS), (
        "the fix writer never completed after the document lock was released"
    )

    holder.join(timeout=_COMPLETION_SECONDS)
    worker.join(timeout=_COMPLETION_SECONDS)
    assert not errors, f"fix writer raised: {errors!r}"


# ---------------------------------------------------------------------------
# Per-writer serialization proofs
# ---------------------------------------------------------------------------


def test_frontmatter_fix_serializes_on_the_document_lock(tmp_path: Path) -> None:
    """``check_frontmatter(fix=True)`` blocks on the document it rewrites."""
    root = _vault(tmp_path)
    doc = root / ".vault" / "research" / "2026-01-01-probe-research.md"
    _write(
        doc,
        "---\ntags:\n  - research\n  - probe\n"
        "date: '2026-01-01'\nmodified: '2026-01-01'\nrelated: []\n---\n\n# Probe\n",
    )
    snapshot: VaultSnapshot = {
        doc: (
            DocumentMetadata(tags=["research", "probe"], date="2026-01-01", related=[]),
            "\n# Probe\n",
        )
    }

    def _run() -> None:
        assert check_frontmatter(root, snapshot=snapshot, fix=True).fixed_count == 1

    _prove_serialized_by(document_lock_target(doc, root), _run)
    assert '"#research"' in doc.read_text(encoding="utf-8")


def test_links_fix_serializes_on_the_document_lock(tmp_path: Path) -> None:
    """``check_links(fix=True)`` blocks on the document it rewrites."""
    root = _vault(tmp_path)
    doc = root / ".vault" / "research" / "2026-01-01-probe-research.md"
    _write(
        doc,
        "---\ntags:\n  - '#research'\n  - '#probe'\n"
        "date: '2026-01-01'\nmodified: '2026-01-01'\nrelated: []\n---\n"
        "\n# Probe\n\n[[2026-01-01-other-research.md]]\n",
    )
    snapshot: VaultSnapshot = {
        doc: (
            DocumentMetadata(
                tags=["#research", "#probe"], date="2026-01-01", related=[]
            ),
            "\n# Probe\n\n[[2026-01-01-other-research.md]]\n",
        )
    }

    def _run() -> None:
        assert check_links(root, snapshot=snapshot, fix=True).fixed_count == 1

    _prove_serialized_by(document_lock_target(doc, root), _run)
    assert "[[2026-01-01-other-research]]" in doc.read_text(encoding="utf-8")


def test_adr_status_fix_serializes_on_the_document_lock(tmp_path: Path) -> None:
    """``check_adr_status(fix=True)`` blocks on the ADR it rewrites."""
    root = _vault(tmp_path)
    doc = root / ".vault" / "adr" / "2026-01-01-probe-adr.md"
    body = "\n# Probe | (**status:** accepted)\n"
    _write(
        doc,
        "---\ntags:\n  - '#adr'\n  - '#probe'\n"
        "date: '2026-01-01'\nmodified: '2026-01-01'\nrelated: []\n---\n" + body,
    )
    snapshot: VaultSnapshot = {
        doc: (
            DocumentMetadata(tags=["#adr", "#probe"], date="2026-01-01", related=[]),
            body,
        )
    }

    def _run() -> None:
        assert check_adr_status(root, snapshot=snapshot, fix=True).fixed_count == 1

    _prove_serialized_by(document_lock_target(doc, root), _run)
    assert "(**status:** `accepted`)" in doc.read_text(encoding="utf-8")


def test_modified_stamp_fix_serializes_on_the_document_lock(tmp_path: Path) -> None:
    """``check_modified_stamp(fix=True)`` blocks on the document it stamps."""
    root = _vault(tmp_path)
    doc = root / ".vault" / "research" / "2026-01-01-probe-research.md"
    body = "\n# Probe\n\nSome prose that has never been fingerprinted.\n"
    _write(
        doc,
        "---\ntags:\n  - '#research'\n  - '#probe'\n"
        "date: '2026-01-01'\nmodified: '2026-01-01'\nrelated: []\n---\n" + body,
    )
    snapshot: VaultSnapshot = {
        doc: (
            DocumentMetadata(
                tags=["#research", "#probe"], date="2026-01-01", related=[]
            ),
            body,
        )
    }

    def _run() -> None:
        assert check_modified_stamp(root, snapshot=snapshot, fix=True).fixed_count == 1

    _prove_serialized_by(document_lock_target(doc, root), _run)
    assert "body_hash:" in doc.read_text(encoding="utf-8")


def test_schema_grounding_fix_serializes_on_the_document_lock(tmp_path: Path) -> None:
    """``check_schema(fix=True)`` blocks on the document whose ``related:`` it edits."""
    from ...graph import VaultGraph

    root = _vault(tmp_path)
    adr = root / ".vault" / "adr" / "2026-01-01-probe-adr.md"
    research = root / ".vault" / "research" / "2026-01-01-probe-research.md"
    _write(
        adr,
        "---\ntags:\n  - '#adr'\n  - '#probe'\n"
        "date: '2026-01-01'\nmodified: '2026-01-01'\nrelated: []\n---\n"
        "\n# Probe | (**status:** `accepted`)\n",
    )
    _write(
        research,
        "---\ntags:\n  - '#research'\n  - '#probe'\n"
        "date: '2026-01-01'\nmodified: '2026-01-01'\nrelated: []\n---\n\n# Probe\n",
    )
    graph = VaultGraph(root)

    def _run() -> None:
        assert check_schema(root, graph=graph, fix=True).fixed_count >= 1

    _prove_serialized_by(document_lock_target(adr, root), _run)
    assert "[[2026-01-01-probe-research]]" in adr.read_text(encoding="utf-8")


def test_repair_restamp_serializes_on_the_document_lock(tmp_path: Path) -> None:
    """``repair._restamp_modified`` blocks on each document it restamps."""
    root = _vault(tmp_path)
    doc = root / ".vault" / "research" / "2026-01-01-probe-research.md"
    _write(
        doc,
        "---\ntags:\n  - '#research'\n  - '#probe'\n"
        "date: '2026-01-01'\nmodified: '2020-01-01'\nrelated: []\n---\n\n# Probe\n",
    )
    rel = doc.relative_to(root).as_posix()

    def _run() -> None:
        assert _restamp_modified(root, [rel]) is True

    _prove_serialized_by(document_lock_target(doc, root), _run)
    assert "modified: '2020-01-01'" not in doc.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# End-to-end: the lost update itself
# ---------------------------------------------------------------------------


_RACE_FRONTMATTER = (
    "---\ntags:\n  - '#research'\n  - '#probe'\n"
    "date: '2026-01-01'\nmodified: '2026-01-01'\nrelated: []\n---\n"
)


def _race_body(marker: str) -> str:
    """Return the body the editor commits, carrying *marker* and a fixable link."""
    return f"\n# Probe\n\n{marker}\n\n[[2026-01-01-other-research.md]]\n"


def _race_round(root: Path, doc: Path, lock_target: Path, marker: str) -> None:
    """Run one editor-versus-fixer round against *doc*, leaving the result on disk.

    The editor writes *marker* under *lock_target* - the same per-document
    sentinel ``execute_edit`` takes - while the fix pass rewrites the ``.md``
    wiki-link from a snapshot captured before that edit, which is the shape
    ``run_all_checks`` has: the graph build precedes every fixer by the width of
    a whole corpus scan.

    Args:
        root: Project root.
        doc: The contended document; its pre-edit revision is already on disk.
        lock_target: The document's advisory-lock sentinel.
        marker: The token the editor commits and the round then looks for.
    """
    previous = doc.read_text(encoding="utf-8")
    _, _, stale_body = previous.partition("---\n\n")
    snapshot: VaultSnapshot = {
        doc: (
            DocumentMetadata(
                tags=["#research", "#probe"], date="2026-01-01", related=[]
            ),
            "\n" + stale_body,
        )
    }
    start = threading.Barrier(2)
    committed = _RACE_FRONTMATTER + _race_body(marker)

    def _edit() -> None:
        start.wait(timeout=_COMPLETION_SECONDS)
        with advisory_lock(lock_target):
            atomic_write(doc, committed)

    def _fix() -> None:
        start.wait(timeout=_COMPLETION_SECONDS)
        check_links(root, snapshot=snapshot, fix=True)

    editor = threading.Thread(target=_edit, name="editor")
    fixer = threading.Thread(target=_fix, name="fixer")
    editor.start()
    fixer.start()
    editor.join(timeout=_COMPLETION_SECONDS)
    fixer.join(timeout=_COMPLETION_SECONDS)


def test_concurrent_edit_survives_a_fix_pass(tmp_path: Path) -> None:
    """A fix pass racing an editor never discards the editor's revision.

    The editor writes under the same per-document advisory lock ``execute_edit``
    takes, so this is the real contention the bug describes rather than a
    reconstruction of it. Against the unlocked writers the fix pass reads
    pre-edit bytes, the edit lands, and the fix pass writes its replacement over
    it: the marker the editor committed is simply gone, with both sides
    reporting success.

    The interleaving is racy by construction, so this is a probabilistic
    detector - the deterministic statement of the same contract is the per-writer
    serialization proof above.
    """
    root = _vault(tmp_path)
    doc = root / ".vault" / "research" / "2026-01-01-probe-research.md"
    lock_target = document_lock_target(doc, root)
    # Both sides must contend on a real sentinel: ``advisory_lock`` no-ops when
    # the parent is absent, and the editor here does not create it the way
    # ``execute_edit`` does.
    lock_target.parent.mkdir(parents=True, exist_ok=True)

    lost: list[str] = []
    for index in range(1, _RACE_ITERATIONS + 1):
        _write(doc, _RACE_FRONTMATTER + _race_body(f"MARKER-{index - 1}"))
        marker = f"MARKER-{index}"
        _race_round(root, doc, lock_target, marker)
        if marker not in doc.read_text(encoding="utf-8"):
            lost.append(marker)

    assert not lost, (
        f"{len(lost)} committed edit(s) discarded by the fix pass in "
        f"{_RACE_ITERATIONS} iterations ({lost[:5]}...): the fix writer is "
        f"deriving its replacement outside the per-document lock"
    )


# ---------------------------------------------------------------------------
# The three writers that needed a restructure rather than a `with` block
# ---------------------------------------------------------------------------


def _prove_rederives_under_lock(
    lock_target: Path,
    writer: Callable[[], None],
    doc: Path,
    superseding: str,
    *,
    warmup: Callable[[], object],
) -> None:
    """Assert *writer* both waits for *lock_target* and re-derives inside it.

    A writer that merely wraps its ``atomic_write`` in the lock passes the
    serialization probe above while still composing the bytes it writes from
    a revision read before the lock - the same lost update with extra steps.
    This probe separates the two commitments:

    1. a holder takes the sentinel and *writer* must not finish while it is
       held (the unlocked failure);
    2. the holder then commits *superseding* - a revision with nothing left
       for *writer* to fix - and only then releases, so a *writer* that
       re-reads under the lock finds nothing to do and leaves those bytes
       alone, while one working from its pre-lock read clobbers them (the
       locked-but-stale failure).

    Args:
        lock_target: The document's advisory-lock sentinel.
        writer: A zero-arg callable performing the lock-protected fix.
        doc: The contended document.
        superseding: The revision the holder commits under the lock; it must
            be free of the defect *writer* repairs.
        warmup: A non-mutating run of the same checker, executed before the
            threads start. Step 1 asserts *writer* does not finish inside a
            short window, and a checker's first call in a process pays for
            resolving its deferred imports and loading the config - latency
            that could carry it past that window on its own and let an
            unlocked writer pass. Paying it up front keeps the window a
            measure of the lock and nothing else.
    """
    warmup()
    lock_target.parent.mkdir(parents=True, exist_ok=True)

    holder_acquired = threading.Event()
    worker_started = threading.Event()
    worker_done = threading.Event()
    escaped: list[bool] = []
    errors: list[BaseException] = []

    def _holder() -> None:
        try:
            with advisory_lock(lock_target):
                holder_acquired.set()
                assert worker_started.wait(timeout=_COMPLETION_SECONDS)
                # The window in which an unlocked writer lands its stale write.
                escaped.append(worker_done.wait(timeout=_BLOCKED_PROBE_SECONDS))
                atomic_write(doc, superseding)
        except BaseException as exc:  # surfaced via the post-join assertion
            errors.append(exc)

    def _worker() -> None:
        try:
            assert holder_acquired.wait(timeout=_COMPLETION_SECONDS)
            worker_started.set()
            writer()
            worker_done.set()
        except BaseException as exc:  # surfaced via the post-join assertion
            errors.append(exc)

    holder = threading.Thread(target=_holder, name="lock-holder")
    worker = threading.Thread(target=_worker, name="fix-writer")
    holder.start()
    assert holder_acquired.wait(timeout=_COMPLETION_SECONDS)
    worker.start()

    holder.join(timeout=_COMPLETION_SECONDS)
    completed = worker_done.wait(timeout=_COMPLETION_SECONDS)
    worker.join(timeout=_COMPLETION_SECONDS)

    assert not errors, f"fix writer raised: {errors!r}"
    assert completed, (
        "the fix writer never completed after the document lock was released"
    )
    assert escaped and not escaped[0], (
        "the fix writer completed while the document lock was held - it is "
        "deriving and writing a replacement outside the per-document lock, so "
        "a concurrent edit can be silently overwritten"
    )
    assert doc.read_text(encoding="utf-8") == superseding, (
        "the fix writer overwrote a revision committed under the document "
        "lock with a replacement derived from bytes read before the lock - "
        "it must re-derive its replacement inside the critical section"
    )


_PROBE_FRONTMATTER = (
    "---\ntags:\n  - '#research'\n  - '#probe'\n"
    "date: '2026-01-01'\nmodified: '2026-01-01'\nrelated: []\n---\n"
)


def _probe_doc(root: Path) -> Path:
    """Return the standard contended document path under *root*."""
    return root / ".vault" / "research" / "2026-01-01-probe-research.md"


def _probe_snapshot(doc: Path, body: str) -> VaultSnapshot:
    """Build the single-document snapshot a snapshot-consuming checker takes."""
    return {
        doc: (
            DocumentMetadata(
                tags=["#research", "#probe"], date="2026-01-01", related=[]
            ),
            body,
        )
    }


def test_annotations_fix_rederives_under_the_document_lock(tmp_path: Path) -> None:
    """``check_annotations(fix=True)`` strips under the lock, from a fresh read."""
    root = _vault(tmp_path)
    doc = _probe_doc(root)
    _write(doc, _PROBE_FRONTMATTER + "\n# Probe\n\n<!-- template guidance -->\n")

    def _run() -> None:
        check_annotations(root, fix=True)

    _prove_rederives_under_lock(
        document_lock_target(doc, root),
        _run,
        doc,
        _PROBE_FRONTMATTER + "\n# Probe\n\nCommitted while the lock was held.\n",
        warmup=lambda: check_annotations(root, fix=False),
    )


def test_markdown_fix_rederives_under_the_document_lock(tmp_path: Path) -> None:
    """``check_markdown(fix=True)`` rewrites under the lock, from a fresh read."""
    root = _vault(tmp_path)
    doc = _probe_doc(root)
    _write(doc, _PROBE_FRONTMATTER + "\n# Probe\n\nTrailing whitespace here.   \n")

    def _run() -> None:
        check_markdown(root, fix=True)

    _prove_rederives_under_lock(
        document_lock_target(doc, root),
        _run,
        doc,
        _PROBE_FRONTMATTER + "\n# Probe\n\nCommitted while the lock was held.\n",
        warmup=lambda: check_markdown(root, fix=False),
    )


def test_body_links_fix_rederives_under_the_document_lock(tmp_path: Path) -> None:
    """``check_body_links(fix=True)`` rewrites under the lock, from a fresh read."""
    root = _vault(tmp_path)
    doc = _probe_doc(root)
    stale_body = "\n# Probe\n\nSee [[2026-01-01-other-research]] for detail.\n"
    _write(doc, _PROBE_FRONTMATTER + stale_body)
    snapshot = _probe_snapshot(doc, stale_body)

    def _run() -> None:
        check_body_links(root, snapshot=snapshot, fix=True)

    _prove_rederives_under_lock(
        document_lock_target(doc, root),
        _run,
        doc,
        _PROBE_FRONTMATTER + "\n# Probe\n\nCommitted while the lock was held.\n",
        warmup=lambda: check_body_links(root, snapshot=snapshot, fix=False),
    )


def test_annotations_fix_does_not_count_a_repair_it_did_not_make(
    tmp_path: Path,
) -> None:
    """A finding superseded before the lock is not reported as fixed."""
    root = _vault(tmp_path)
    doc = _probe_doc(root)
    clean = _PROBE_FRONTMATTER + "\n# Probe\n\nNothing to strip.\n"
    _write(doc, _PROBE_FRONTMATTER + "\n# Probe\n\n<!-- template guidance -->\n")
    counts: list[int] = []

    def _run() -> None:
        counts.append(check_annotations(root, fix=True).fixed_count)

    _prove_rederives_under_lock(
        document_lock_target(doc, root),
        _run,
        doc,
        clean,
        warmup=lambda: check_annotations(root, fix=False),
    )
    assert counts == [0], (
        "the annotations fixer counted a repair for a document that had "
        "nothing left to strip once it held the lock"
    )


def test_markdown_fix_does_not_count_a_repair_it_did_not_make(tmp_path: Path) -> None:
    """A finding superseded before the lock is not reported as fixed."""
    root = _vault(tmp_path)
    doc = _probe_doc(root)
    clean = _PROBE_FRONTMATTER + "\n# Probe\n\nNothing to tidy.\n"
    _write(doc, _PROBE_FRONTMATTER + "\n# Probe\n\nTrailing whitespace.   \n")
    counts: list[int] = []

    def _run() -> None:
        counts.append(check_markdown(root, fix=True).fixed_count)

    _prove_rederives_under_lock(
        document_lock_target(doc, root),
        _run,
        doc,
        clean,
        warmup=lambda: check_markdown(root, fix=False),
    )
    assert counts == [0], (
        "the markdown fixer counted a repair for a document that had nothing "
        "left to tidy once it held the lock"
    )


def test_body_links_fix_does_not_count_a_repair_it_did_not_make(
    tmp_path: Path,
) -> None:
    """A finding superseded before the lock is not reported as fixed."""
    root = _vault(tmp_path)
    doc = _probe_doc(root)
    stale_body = "\n# Probe\n\nSee [[2026-01-01-other-research]] for detail.\n"
    clean = _PROBE_FRONTMATTER + "\n# Probe\n\nNo wiki-links left.\n"
    _write(doc, _PROBE_FRONTMATTER + stale_body)
    snapshot = _probe_snapshot(doc, stale_body)
    counts: list[int] = []

    def _run() -> None:
        counts.append(check_body_links(root, snapshot=snapshot, fix=True).fixed_count)

    _prove_rederives_under_lock(
        document_lock_target(doc, root),
        _run,
        doc,
        clean,
        warmup=lambda: check_body_links(root, snapshot=snapshot, fix=False),
    )
    assert counts == [0], (
        "the body-links fixer counted a repair for a document that had no "
        "body wiki-link left once it held the lock"
    )


# ---------------------------------------------------------------------------
# End-to-end: the lost update, for each of the three
# ---------------------------------------------------------------------------


def _run_race(
    root: Path,
    doc: Path,
    stale_body: Callable[[str], str],
    clean_body: Callable[[str], str],
    fixer: Callable[[Path, Path, str], None],
) -> list[str]:
    """Race an editor against *fixer* repeatedly; return the discarded markers.

    Each round leaves a fixable revision on disk, then starts an editor and a
    fix pass at a barrier. The editor commits a clean revision under the same
    per-document sentinel ``execute_edit`` takes; the fix pass repairs the
    defect it saw beforehand. A correct fixer re-reads under the lock, finds
    the defect gone, and writes nothing.

    Args:
        root: Project root.
        doc: The contended document.
        stale_body: Builds the fixable pre-edit body carrying a marker.
        clean_body: Builds the defect-free body the editor commits.
        fixer: Runs the fix pass, given ``(root, doc, stale_body_text)``.

    Returns:
        The markers the editor committed that were not on disk afterwards.
    """
    lock_target = document_lock_target(doc, root)
    lock_target.parent.mkdir(parents=True, exist_ok=True)
    lost: list[str] = []

    for index in range(1, _RACE_ITERATIONS + 1):
        stale_text = _PROBE_FRONTMATTER + stale_body(f"MARKER-{index - 1}")
        _write(doc, stale_text)
        marker = f"MARKER-{index}"
        committed = _PROBE_FRONTMATTER + clean_body(marker)
        start = threading.Barrier(2)

        def _edit(payload: str = committed, barrier: threading.Barrier = start) -> None:
            barrier.wait(timeout=_COMPLETION_SECONDS)
            with advisory_lock(lock_target):
                atomic_write(doc, payload)

        def _fix(text: str = stale_text, barrier: threading.Barrier = start) -> None:
            barrier.wait(timeout=_COMPLETION_SECONDS)
            fixer(root, doc, text)

        editor = threading.Thread(target=_edit, name="editor")
        fix_pass = threading.Thread(target=_fix, name="fixer")
        editor.start()
        fix_pass.start()
        editor.join(timeout=_COMPLETION_SECONDS)
        fix_pass.join(timeout=_COMPLETION_SECONDS)

        if marker not in doc.read_text(encoding="utf-8"):
            lost.append(marker)

    return lost


def _annotations_fixer(root: Path, _doc: Path, _text: str) -> None:
    """Run the annotations fix pass over *root*."""
    check_annotations(root, fix=True)


def _markdown_fixer(root: Path, _doc: Path, _text: str) -> None:
    """Run the markdown fix pass over *root*."""
    check_markdown(root, fix=True)


def _body_links_fixer(root: Path, doc: Path, text: str) -> None:
    """Run the body-links fix pass from the snapshot *text* was read into."""
    _, _, body = text.partition("---\n")
    _, _, body = body.partition("---\n")
    check_body_links(root, snapshot=_probe_snapshot(doc, body), fix=True)


def test_concurrent_edit_survives_an_annotations_fix_pass(tmp_path: Path) -> None:
    """The annotations fixer racing an editor never discards its revision."""
    root = _vault(tmp_path)
    doc = _probe_doc(root)
    lost = _run_race(
        root,
        doc,
        lambda marker: f"\n# Probe\n\n{marker}\n\n<!-- template guidance -->\n",
        lambda marker: f"\n# Probe\n\n{marker}\n",
        _annotations_fixer,
    )
    assert not lost, (
        f"{len(lost)} committed edit(s) discarded by the annotations fix pass "
        f"in {_RACE_ITERATIONS} iterations ({lost[:5]}...)"
    )


def test_concurrent_edit_survives_a_markdown_fix_pass(tmp_path: Path) -> None:
    """The markdown fixer racing an editor never discards its revision."""
    root = _vault(tmp_path)
    doc = _probe_doc(root)
    lost = _run_race(
        root,
        doc,
        lambda marker: f"\n# Probe\n\n{marker}   \n",
        lambda marker: f"\n# Probe\n\n{marker}\n",
        _markdown_fixer,
    )
    assert not lost, (
        f"{len(lost)} committed edit(s) discarded by the markdown fix pass in "
        f"{_RACE_ITERATIONS} iterations ({lost[:5]}...)"
    )


def test_concurrent_edit_survives_a_body_links_fix_pass(tmp_path: Path) -> None:
    """The body-links fixer racing an editor never discards its revision."""
    root = _vault(tmp_path)
    doc = _probe_doc(root)
    lost = _run_race(
        root,
        doc,
        lambda marker: f"\n# Probe\n\n{marker}\n\n[[2026-01-01-other-research]]\n",
        lambda marker: f"\n# Probe\n\n{marker}\n",
        _body_links_fixer,
    )
    assert not lost, (
        f"{len(lost)} committed edit(s) discarded by the body-links fix pass "
        f"in {_RACE_ITERATIONS} iterations ({lost[:5]}...)"
    )
