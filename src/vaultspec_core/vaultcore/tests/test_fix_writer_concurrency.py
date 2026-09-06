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
from ..checks.frontmatter import check_frontmatter
from ..checks.links import check_links
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
