"""Tests for the ``exec_ledger_only`` migration (0.1.74).

The migration ships with the refusal that makes it safe: ``vault add exec``
no longer produces a per-Step record, so folding current-schema records can
no longer eat freshly authored ones. What must hold:

- every record carrying a ``step_id`` folds, ``body-v1`` and ``body-v2``
  alike, and a ``body-v2`` record keeps its operations, verify line, and
  notes;
- a flat pre-Step-aware record folds into the plan its ``related:`` names;
- a Phase Summary is removed only once every Step of its Phase has rows;
- a second run is a true no-op;
- every folded Step still resolves through the shared execution-record
  index.

All fixtures are real files; no mocks, patches, or skips.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from vaultspec_core.config import reset_config
from vaultspec_core.migrations.m_0_1_74_exec_ledger_only import migrate

if TYPE_CHECKING:
    from collections.abc import Generator

pytestmark = [pytest.mark.unit]

_FOLDER = "2026-05-17-demo"
_PLAN_STEM = "2026-05-17-demo-plan"


@pytest.fixture(autouse=True)
def reset_cfg() -> Generator[None]:
    reset_config()
    yield
    reset_config()


def _skeleton(root: Path, *, plan: bool = True) -> Path:
    folder = root / ".vault" / "exec" / _FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    (root / ".vaultspec" / "templates").mkdir(parents=True, exist_ok=True)
    src = (
        Path(__file__).resolve().parents[2]
        / "builtins"
        / "templates"
        / "exec-ledger.md"
    )
    (root / ".vaultspec" / "templates" / "exec-ledger.md").write_text(
        src.read_text(encoding="utf-8"), encoding="utf-8"
    )
    if plan:
        plan_dir = root / ".vault" / "plan"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / f"{_PLAN_STEM}.md").write_text(
            "---\ntags:\n  - '#plan'\n  - '#demo'\ndate: '2026-05-17'\n"
            "modified: '2026-05-17'\ntier: L2\nrelated: []\n---\n\n"
            "# `demo` plan\n\n## Description\n\nProse.\n\n"
            "### Phase `P01` - one\n\n"
            "- [x] `P01.S01` - first; `src/foo.py`.\n"
            "- [x] `P01.S02` - second; `src/bar.py`.\n\n"
            "### Phase `P02` - two\n\n"
            "- [ ] `P02.S03` - third; `src/baz.py`.\n\n"
            "## Parallelization\n\nProse.\n\n## Verification\n\nProse.\n",
            encoding="utf-8",
        )
    return folder


def _record(
    root: Path,
    name: str,
    *,
    step_id: str | None,
    schema: str = "body-v1",
    scope: tuple[str, ...] = ("src/foo.py",),
    changes: tuple[str, ...] = (),
    notes: str | None = None,
    flat: bool = False,
) -> Path:
    folder = root / ".vault" / "exec" if flat else root / ".vault" / "exec" / _FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.md"
    lines = ["---", "tags:", "  - '#exec'", "  - '#demo'", "date: '2026-05-17'"]
    lines.append(f"body_schema: '{schema}'")
    if step_id:
        lines.append(f"step_id: '{step_id}'")
    lines += ["related:", f"  - '[[{_PLAN_STEM}]]'", "---", "", "# did a thing", ""]
    if scope:
        lines += ["## Scope", "", *[f"- `{s}`" for s in scope], ""]
    if changes:
        lines += ["## Changes", "", *changes, ""]
    else:
        lines += ["## Description", "", "Prose no consumer reads.", ""]
    if notes:
        lines += ["## Notes", "", notes, ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _ledger(root: Path) -> Path:
    return root / ".vault" / "exec" / _FOLDER / f"{_FOLDER}-ledger.md"


def test_folds_every_schema(tmp_path: Path) -> None:
    _skeleton(tmp_path)
    legacy = _record(tmp_path, f"{_FOLDER}-P01-S01", step_id="S01")
    fresh = _record(
        tmp_path,
        f"{_FOLDER}-P01-S02",
        step_id="S02",
        schema="body-v2",
        changes=("- `M` `src/bar.py`", "- `verify:` `pytest` -> `pass`"),
        notes="left a scaffold.",
    )

    result = migrate(tmp_path)

    assert result.counts["folded"] == 2
    assert not legacy.exists() and not fresh.exists()
    text = _ledger(tmp_path).read_text(encoding="utf-8")
    assert "- `S01` `T` `src/foo.py`" in text
    assert "- `S02` `M` `src/bar.py`" in text
    assert "- `S02` `verify:` `pytest` -> `pass`" in text
    assert "- `S02` left a scaffold." in text
    assert result.counts["notes"] == 1


def test_summary_removed_once_its_steps_have_rows(tmp_path: Path) -> None:
    folder = _skeleton(tmp_path)
    _record(tmp_path, f"{_FOLDER}-P01-S01", step_id="S01")
    _record(tmp_path, f"{_FOLDER}-P01-S02", step_id="S02")
    summary = folder / f"{_FOLDER}-P01-summary.md"
    summary.write_text(
        "---\ntags:\n  - '#exec'\n  - '#demo'\ndate: '2026-05-17'\n"
        f"related:\n  - '[[{_PLAN_STEM}]]'\n---\n\n# summary\n\n## Changes\n\n"
        "- `M` `src/foo.py`\n",
        encoding="utf-8",
    )

    result = migrate(tmp_path)

    assert not summary.exists()
    assert result.counts["summaries"] == 1


def test_summary_kept_while_a_step_lacks_rows(tmp_path: Path) -> None:
    folder = _skeleton(tmp_path)
    _record(tmp_path, f"{_FOLDER}-P01-S01", step_id="S01")
    summary = folder / f"{_FOLDER}-P01-summary.md"
    summary.write_text(
        "---\ntags:\n  - '#exec'\n  - '#demo'\ndate: '2026-05-17'\n"
        f"related:\n  - '[[{_PLAN_STEM}]]'\n---\n\n# summary\n",
        encoding="utf-8",
    )

    result = migrate(tmp_path)

    assert summary.exists()
    assert result.counts["summaries"] == 0
    assert result.counts["skipped"] == 1


def test_summary_survives_a_migration_that_writes_nothing(tmp_path: Path) -> None:
    """A summary is never unlinked on a pass that leaves the ledger untouched.

    The workspace was already folded, so the ledger covers every Step of
    ``P01`` and no per-Step record remains. The summary yields no row and no
    note of its own, so removing it would destroy hand-authored prose while
    the ledger stays byte-identical.
    """
    folder = _skeleton(tmp_path)
    _ledger(tmp_path).write_text(
        "\n".join(
            (
                "---",
                "tags:",
                "  - '#exec'",
                "  - '#demo'",
                "date: '2026-05-17'",
                "modified: '2026-05-17'",
                "body_schema: 'body-v2'",
                "related:",
                f"  - '[[{_PLAN_STEM}]]'",
                "---",
                "",
                "# `demo` ledger",
                "",
                "## Changes",
                "",
                "- `S01` `M` `src/foo.py`",
                "- `S02` `M` `src/bar.py`",
                "",
            )
        ),
        encoding="utf-8",
    )
    before = _ledger(tmp_path).read_text(encoding="utf-8")
    prose = "The batch path is slower but correct; do not revisit."
    summary = folder / f"{_FOLDER}-P01-summary.md"
    summary.write_text(
        "\n".join(
            (
                "---",
                "tags:",
                "  - '#exec'",
                "  - '#demo'",
                "date: '2026-05-17'",
                "related:",
                f"  - '[[{_PLAN_STEM}]]'",
                "---",
                "",
                "# summary",
                "",
                "## Outcome",
                "",
                prose,
                "",
            )
        ),
        encoding="utf-8",
    )

    result = migrate(tmp_path)

    assert summary.exists(), "a summary was deleted while nothing was written"
    assert prose in summary.read_text(encoding="utf-8")
    assert _ledger(tmp_path).read_text(encoding="utf-8") == before
    assert result.counts["summaries"] == 0


def test_flat_record_folds_into_its_plan_folder(tmp_path: Path) -> None:
    _skeleton(tmp_path)
    flat = _record(tmp_path, "2026-05-22-demo-exec", step_id="S01", flat=True)

    result = migrate(tmp_path)

    assert not flat.exists()
    assert result.counts["folded"] == 1
    assert "- `S01` `T` `src/foo.py`" in _ledger(tmp_path).read_text(encoding="utf-8")


def test_record_without_step_id_is_left_intact(tmp_path: Path) -> None:
    _skeleton(tmp_path)
    orphan = _record(tmp_path, f"{_FOLDER}-orphan", step_id=None)

    result = migrate(tmp_path)

    assert orphan.exists()
    assert result.counts["folded"] == 0
    assert not _ledger(tmp_path).exists()


def test_second_run_is_a_true_no_op(tmp_path: Path) -> None:
    _skeleton(tmp_path)
    _record(tmp_path, f"{_FOLDER}-P01-S01", step_id="S01")
    migrate(tmp_path)
    before = _ledger(tmp_path).read_text(encoding="utf-8")
    listing = sorted(p.name for p in (tmp_path / ".vault" / "exec" / _FOLDER).iterdir())

    result = migrate(tmp_path)

    assert result.counts["folded"] == 0
    assert _ledger(tmp_path).read_text(encoding="utf-8") == before
    assert (
        sorted(p.name for p in (tmp_path / ".vault" / "exec" / _FOLDER).iterdir())
        == listing
    )


def test_folded_steps_resolve_through_the_index(tmp_path: Path) -> None:
    from vaultspec_core.plan.status import ExecRecordIndex

    _skeleton(tmp_path)
    _record(tmp_path, f"{_FOLDER}-P01-S01", step_id="S01")
    _record(
        tmp_path,
        f"{_FOLDER}-P01-S02",
        step_id="S02",
        schema="body-v2",
        changes=("- `A` `x.py`",),
    )
    migrate(tmp_path)

    index = ExecRecordIndex.build(tmp_path)

    assert index.record_for("demo", "S01") == f"{_FOLDER}-ledger"
    assert index.record_for("demo", "S02") == f"{_FOLDER}-ledger"
    evidence = index.evidence_for("demo", "S02")
    assert evidence is not None and evidence.rows == 1


def test_no_exec_directory_is_a_clean_no_op(tmp_path: Path) -> None:
    result = migrate(tmp_path)

    assert result.counts["folded"] == 0
    assert "nothing to fold" in result.summary


def test_registered_after_the_0_1_58_fold() -> None:
    from vaultspec_core.migrations import REGISTRY

    names = [m.name for m in REGISTRY]
    assert names.index("exec_ledger_only") > names.index("exec_ledger_fold")
    entry = next(m for m in REGISTRY if m.name == "exec_ledger_only")
    assert entry.target_version == "0.1.74"
