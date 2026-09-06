"""Tests for the per-Step-record fold planner.

The planner is pure, so these assert the decisions themselves: what folds,
what is refused and why, that recovered rows never invent an operation, and
that a Step recorded without a scope keeps its mapping.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from vaultspec_core.vaultcore.exec_fold import FoldSource, plan_fold, scope_paths

BODY = """# do a thing

## Scope

- `src/a.py`
- `src/b.py`

## Description

Prose that no consumer reads.

## Outcome

More prose.
"""


def _source(name: str, step_id: str | None, body: str = BODY) -> FoldSource:
    return FoldSource(Path(f".vault/exec/2026-01-01-feat/{name}.md"), step_id, body)


class TestScopePaths:
    def test_reads_backticked_cells_in_order(self) -> None:
        assert scope_paths(BODY) == ("src/a.py", "src/b.py")

    def test_absent_scope_yields_nothing(self) -> None:
        assert scope_paths("# x\n\n## Description\n\nProse.\n") == ()

    def test_empty_scope_yields_nothing(self) -> None:
        assert scope_paths("## Scope\n\n## Description\n\nProse.\n") == ()

    def test_duplicates_collapse(self) -> None:
        body = "## Scope\n\n- `a.py`\n- `a.py`\n- `b.py`\n"

        assert scope_paths(body) == ("a.py", "b.py")

    def test_prose_after_scope_is_not_harvested(self) -> None:
        """Only the Scope section contributes paths."""
        body = "## Scope\n\n- `a.py`\n\n## Notes\n\nAlso touched `b.py`.\n"

        assert scope_paths(body) == ("a.py",)


class TestPlanFold:
    def test_recovers_scope_paths_as_touched_rows(self) -> None:
        plan = plan_fold([_source("2026-01-01-feat-S01", "S01")])

        assert plan.rows == [
            "- `S01` `T` `src/a.py`",
            "- `S01` `T` `src/b.py`",
        ]
        assert plan.recovered_paths == 2
        assert len(plan.folded) == 1

    def test_never_invents_an_operation(self) -> None:
        """body-v1 recorded no operation, so no row may claim A, M, D, or R."""
        plan = plan_fold([_source("2026-01-01-feat-S01", "S01")])

        for row in plan.rows:
            assert "`T`" in row
            for invented in ("`A`", "`M`", "`D`", "`R`"):
                assert invented not in row

    def test_step_without_scope_keeps_its_mapping(self) -> None:
        """A recorded Step must not read as never executed after folding."""
        plan = plan_fold(
            [_source("2026-01-01-feat-S01", "S01", "# x\n\n## Description\n\nP.\n")]
        )

        assert plan.rows == ["- `S01` `T`"]
        assert plan.recovered_paths == 0
        assert len(plan.folded) == 1

    def test_rows_are_ordered_numerically_by_step(self) -> None:
        plan = plan_fold(
            [
                _source("2026-01-01-feat-S10", "S10"),
                _source("2026-01-01-feat-S02", "S02"),
                _source("2026-01-01-feat-S01", "S01"),
            ]
        )

        assert [r.split("`")[1] for r in plan.rows][:3] == ["S01", "S01", "S02"]
        assert plan.rows[-1].startswith("- `S10`")

    def test_record_without_step_id_is_skipped_not_dropped(self) -> None:
        plan = plan_fold([_source("2026-01-01-feat-legacy", None)])

        assert plan.rows == []
        assert plan.folded == []
        assert [s.reason for s in plan.skipped] == ["no step_id"]

    def test_summary_is_skipped(self) -> None:
        plan = plan_fold([_source("2026-01-01-feat-P01-summary", "S01")])

        assert plan.folded == []
        assert [s.reason for s in plan.skipped] == ["phase summary"]

    def test_existing_ledger_is_never_folded_into_itself(self) -> None:
        plan = plan_fold([_source("2026-01-01-feat-ledger", None)])

        assert plan.folded == []
        assert [s.reason for s in plan.skipped] == ["is the ledger"]

    def test_empty_input_plans_nothing(self) -> None:
        plan = plan_fold([])

        assert plan.is_empty
        assert plan.rows == []

    def test_mixed_folder_folds_only_what_it_should(self) -> None:
        plan = plan_fold(
            [
                _source("2026-01-01-feat-S01", "S01"),
                _source("2026-01-01-feat-S02", "S02"),
                _source("2026-01-01-feat-P01-summary", None),
                _source("2026-01-01-feat-legacy", None),
                _source("2026-01-01-feat-ledger", None),
            ]
        )

        assert len(plan.folded) == 2
        assert len(plan.skipped) == 3
        assert plan.recovered_paths == 4


BODY_V2 = """# do a thing

## Scope

- `src/a.py`

## Changes

- `M` `src/a.py`
- `A` `tests/test_a.py`
- `verify:` `pytest -q` -> `pass`

## Notes

left a scaffold in `src/a.py`.
"""


class TestBodyV2Fold:
    """A body-v2 record folds with its operations, verify line, and notes."""

    def test_rows_keep_their_operations(self) -> None:
        plan = plan_fold([_source("2026-01-01-feat-S03", "S03", BODY_V2)])

        assert plan.rows == [
            "- `S03` `M` `src/a.py`",
            "- `S03` `A` `tests/test_a.py`",
            "- `S03` `verify:` `pytest -q` -> `pass`",
        ]
        assert plan.recovered_paths == 2
        assert "`T`" not in "".join(plan.rows)

    def test_notes_are_carried_under_the_step_id(self) -> None:
        plan = plan_fold([_source("2026-01-01-feat-S03", "S03", BODY_V2)])

        assert plan.notes == ["- `S03` left a scaffold in `src/a.py`."]

    def test_body_v1_notes_are_discarded(self) -> None:
        body = BODY + "\n## Notes\n\nYet more prose.\n"
        plan = plan_fold([_source("2026-01-01-feat-S01", "S01", body)])

        assert plan.notes == []

    def test_empty_changes_keeps_a_coverage_row(self) -> None:
        body = "# x\n\n## Changes\n\n"
        plan = plan_fold([_source("2026-01-01-feat-S04", "S04", body)])

        assert plan.rows == ["- `S04` `T`"]


class TestSummaryRemoval:
    """A Phase Summary goes once every Step of its Phase has rows."""

    _PHASES: ClassVar[dict[str, list[str]]] = {
        "P01": ["S01", "S02"],
        "W01.P02": ["S03"],
    }

    def test_summary_removed_when_all_steps_fold(self) -> None:
        plan = plan_fold(
            [
                _source("2026-01-01-feat-S01", "S01"),
                _source("2026-01-01-feat-S02", "S02"),
                _source("2026-01-01-feat-P01-summary", None),
            ],
            phase_steps=self._PHASES,
        )

        assert [p.name for p in plan.summaries] == ["2026-01-01-feat-P01-summary.md"]
        assert plan.removed[-1].name.endswith("-summary.md")
        assert not plan.is_empty

    def test_summary_kept_when_a_step_has_no_rows(self) -> None:
        plan = plan_fold(
            [
                _source("2026-01-01-feat-S01", "S01"),
                _source("2026-01-01-feat-P01-summary", None),
            ],
            phase_steps=self._PHASES,
        )

        assert plan.summaries == []
        assert [s.reason for s in plan.skipped] == [
            "phase summary; Steps not all logged"
        ]

    def test_existing_ledger_coverage_counts(self) -> None:
        """A Step the ledger already covers counts toward its Phase."""
        plan = plan_fold(
            [
                _source("2026-01-01-feat-S02", "S02"),
                _source("2026-01-01-feat-P01-summary", None),
            ],
            phase_steps=self._PHASES,
            covered=("S01",),
        )

        assert len(plan.summaries) == 1
        assert [p.name for p in plan.folded] == ["2026-01-01-feat-S02.md"]
        assert not plan.is_empty

    def test_wave_qualified_summary_resolves_its_phase(self) -> None:
        plan = plan_fold(
            [
                _source("2026-01-01-feat-W01-P02-S03", "S03"),
                _source("2026-01-01-feat-W01-P02-summary", None),
            ],
            phase_steps=self._PHASES,
        )

        assert len(plan.summaries) == 1

    def test_summary_is_kept_when_the_fold_writes_nothing(self) -> None:
        """The #452 shape: every Step is already covered, so the fold recovers
        no row and no note, yet the summary's own narrative would be deleted
        with nothing written in its place."""
        plan = plan_fold(
            [_source("2026-01-01-feat-P01-summary", None)],
            phase_steps=self._PHASES,
            covered=("S01", "S02"),
        )

        assert plan.rows == []
        assert plan.notes == []
        assert plan.summaries == []
        assert plan.removed == []
        assert plan.is_empty
        assert [s.reason for s in plan.skipped] == [
            "phase summary; the fold writes nothing"
        ]

    def test_summary_kept_without_a_plan_mapping(self) -> None:
        plan = plan_fold([_source("2026-01-01-feat-P01-summary", None)])

        assert plan.summaries == []
        assert [s.reason for s in plan.skipped] == ["phase summary"]
