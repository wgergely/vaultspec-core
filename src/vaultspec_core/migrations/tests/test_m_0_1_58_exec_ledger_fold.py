"""Tests for the ``exec_ledger_fold`` migration (0.1.58).

This is the first registered migration that removes documents, and it runs
automatically - through ``install --upgrade`` and lazily through any vault
command - so the safety properties matter more than the happy path:

- only pre-``body-v2`` records fold, because the manifest bumps to the
  running package version rather than a migration's target, so a pre-release
  workspace re-runs the registry on every vault command and folding
  current-schema records would silently eat freshly authored ones;
- records that cannot be attributed to one Step are left intact;
- a second run is a true no-op, as the registry contract requires;
- every folded Step still resolves through the shared execution-record index.

All fixtures are real files; no mocks, patches, or skips.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from vaultspec_core.config import reset_config
from vaultspec_core.migrations.m_0_1_58_exec_ledger_fold import migrate

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


def _skeleton(root: Path) -> Path:
    folder = root / ".vault" / "exec" / _FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    (root / ".vaultspec" / "templates").mkdir(parents=True, exist_ok=True)
    # The fold scaffolds its ledger from the deployed template mirror.
    src = (
        Path(__file__).resolve().parents[2]
        / "builtins"
        / "templates"
        / "exec-ledger.md"
    )
    (root / ".vaultspec" / "templates" / "exec-ledger.md").write_text(
        src.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return folder


def _record(
    root: Path,
    name: str,
    *,
    step_id: str | None,
    schema: str | None = "body-v1",
    scope: tuple[str, ...] = ("src/foo.py",),
) -> Path:
    folder = root / ".vault" / "exec" / _FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.md"
    lines = ["---", "tags:", "  - '#exec'", "  - '#demo'", "date: '2026-05-17'"]
    if schema:
        lines.append(f"body_schema: '{schema}'")
    if step_id:
        lines.append(f"step_id: '{step_id}'")
    lines += ["related:", f"  - '[[{_PLAN_STEM}]]'", "---", "", "# did a thing", ""]
    if scope:
        lines += ["## Scope", ""]
        lines += [f"- `{s}`" for s in scope]
        lines.append("")
    lines += ["## Description", "", "Prose no consumer reads.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _ledger(root: Path) -> Path:
    return root / ".vault" / "exec" / _FOLDER / f"{_FOLDER}-ledger.md"


def test_folds_body_v1_records(tmp_path: Path) -> None:
    _skeleton(tmp_path)
    first = _record(tmp_path, f"{_FOLDER}-S01", step_id="S01")
    second = _record(tmp_path, f"{_FOLDER}-S02", step_id="S02", scope=("src/bar.py",))

    result = migrate(tmp_path)

    assert result.counts["folded"] == 2
    assert result.counts["paths"] == 2
    assert not first.exists()
    assert not second.exists()
    text = _ledger(tmp_path).read_text(encoding="utf-8")
    assert "- `S01` `T` `src/foo.py`" in text
    assert "- `S02` `T` `src/bar.py`" in text


def _pre_ledger_record(root: Path, name: str, *, step_id: str, note: str) -> Path:
    """Write a pre-ledger record: ``body-v1`` schema, ``## Changes`` body shape.

    Such a record predates the Step column but carried the same ``## Changes``
    contract, so the planner recovers real operations and its ``## Notes``
    from it. This migration gates on the schema declaration, so the record is
    in scope: the two do not coincide.
    """
    folder = root / ".vault" / "exec" / _FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.md"
    lines = [
        "---",
        "tags:",
        "  - '#exec'",
        "  - '#demo'",
        "date: '2026-05-17'",
        "body_schema: 'body-v1'",
        f"step_id: '{step_id}'",
        "related:",
        f"  - '[[{_PLAN_STEM}]]'",
        "---",
        "",
        "# did a thing",
        "",
        "## Changes",
        "",
        "- `M` `src/a.py`",
        "",
        "## Notes",
        "",
        f"- {note}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_notes_are_carried_before_the_record_is_removed(tmp_path: Path) -> None:
    """A recovered note must reach the ledger, not die with its record."""
    _skeleton(tmp_path)
    note = "Rolled back the index rebuild; it corrupts on empty features."
    record = _pre_ledger_record(tmp_path, f"{_FOLDER}-S01", step_id="S01", note=note)

    result = migrate(tmp_path)

    text = _ledger(tmp_path).read_text(encoding="utf-8")
    assert "- `S01` `M` `src/a.py`" in text
    assert f"- `S01` {note}" in text, "a recovered note was dropped"
    assert not record.exists()
    assert result.counts["notes"] == 1


def test_current_schema_records_are_never_folded(tmp_path: Path) -> None:
    """The property that makes an auto-run fold safe before release."""
    _skeleton(tmp_path)
    fresh = _record(tmp_path, f"{_FOLDER}-S01", step_id="S01", schema="body-v2")

    result = migrate(tmp_path)

    assert fresh.exists()
    assert result.counts["folded"] == 0
    assert result.counts["current"] == 1
    assert not _ledger(tmp_path).exists()


def test_mixed_corpus_folds_only_legacy(tmp_path: Path) -> None:
    _skeleton(tmp_path)
    legacy = _record(tmp_path, f"{_FOLDER}-S01", step_id="S01")
    fresh = _record(tmp_path, f"{_FOLDER}-S02", step_id="S02", schema="body-v2")

    result = migrate(tmp_path)

    assert not legacy.exists()
    assert fresh.exists()
    assert result.counts["folded"] == 1
    assert result.counts["current"] == 1


def test_record_without_step_id_is_left_intact(tmp_path: Path) -> None:
    _skeleton(tmp_path)
    orphan = _record(tmp_path, f"{_FOLDER}-legacy", step_id=None)

    result = migrate(tmp_path)

    assert orphan.exists()
    assert result.counts["folded"] == 0


def test_phase_summary_is_left_intact(tmp_path: Path) -> None:
    _skeleton(tmp_path)
    summary = _record(tmp_path, f"{_FOLDER}-P01-summary", step_id="S01")

    result = migrate(tmp_path)

    assert summary.exists()
    assert result.counts["folded"] == 0


def test_second_run_is_a_true_no_op(tmp_path: Path) -> None:
    """The registry contract: an already-migrated workspace is untouched."""
    _skeleton(tmp_path)
    _record(tmp_path, f"{_FOLDER}-S01", step_id="S01")

    migrate(tmp_path)
    before = _ledger(tmp_path).read_text(encoding="utf-8")
    listing = sorted(p.name for p in (tmp_path / ".vault" / "exec" / _FOLDER).iterdir())

    second = migrate(tmp_path)

    assert second.counts["folded"] == 0
    assert _ledger(tmp_path).read_text(encoding="utf-8") == before
    assert (
        sorted(p.name for p in (tmp_path / ".vault" / "exec" / _FOLDER).iterdir())
        == listing
    )


def test_folded_steps_resolve_through_the_index(tmp_path: Path) -> None:
    from vaultspec_core.plan.status import ExecRecordIndex

    _skeleton(tmp_path)
    _record(tmp_path, f"{_FOLDER}-S01", step_id="S01")
    _record(tmp_path, f"{_FOLDER}-S02", step_id="S02", scope=("src/bar.py",))

    migrate(tmp_path)
    index = ExecRecordIndex.build(tmp_path)

    stem = f"{_FOLDER}-ledger"
    assert index.record_for("demo", "S01") == stem
    assert index.record_for("demo", "S02") == stem


def test_no_exec_directory_is_a_clean_no_op(tmp_path: Path) -> None:
    (tmp_path / ".vault").mkdir(parents=True, exist_ok=True)

    result = migrate(tmp_path)

    assert result.counts["folded"] == 0
    assert "nothing to fold" in result.summary


def test_prose_is_discarded(tmp_path: Path) -> None:
    _skeleton(tmp_path)
    _record(tmp_path, f"{_FOLDER}-S01", step_id="S01")

    migrate(tmp_path)

    assert "Prose no consumer reads" not in _ledger(tmp_path).read_text(
        encoding="utf-8"
    )


def test_registered_in_the_registry() -> None:
    from vaultspec_core.migrations import REGISTRY

    entry = next(m for m in REGISTRY if m.name == "exec_ledger_fold")
    assert entry.target_version == "0.1.58"
