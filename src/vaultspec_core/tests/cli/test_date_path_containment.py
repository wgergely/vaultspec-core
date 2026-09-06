"""Containment tests for the date a scaffolded document is named from.

A vault document's ``date`` decides a directory and a filename, exactly as
its feature handle does, so it has to be admitted with the same discipline:
parsed into a calendar date before anything composes a path from it. These
tests drive the two CLI surfaces where a date arrives from outside - the
``vault add --date`` flag, and the ``date:`` frontmatter of the plan that
``vault exec log`` names its ledger after - and assert on FILESYSTEM STATE:
nothing may appear outside the workspace root, and the command must fail
rather than report success.

The document-content case is the one that matters most in practice. The
date it uses is not an operator argument at all; it is a field read back out
of a plan file, which in a cloned repository is content the workspace did
not author.

Every test uses a real workspace, the real CLI, and real files. Legitimate
dates - including the non-canonical forms the vault's lenient parser has
always accepted, and the natural default of today - are asserted to behave
exactly as before, so the guard cannot pass by refusing everything.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from vaultspec_core.cli import app
from vaultspec_core.vaultcore.models import vault_today

from .test_step_aware_exec import setup_test_plan

if TYPE_CHECKING:
    from pathlib import Path

    from typer.testing import CliRunner

pytestmark = [pytest.mark.integration]

_PLAN_STEM = "2026-05-17-test-feature-plan"


def _outside_files(root: Path) -> list[Path]:
    """Return every file that landed beside the workspace instead of inside it.

    The workspace is a child of ``tmp_path``, so a document that escapes the
    root by any number of parent segments has to materialise somewhere in
    that parent tree. Walking it is a direct read of the property under
    test: after a refused call, the answer is the empty list.
    """
    return sorted(
        path
        for path in root.parent.rglob("*")
        if path.is_file() and root not in path.parents and path.parent != root
    )


class TestAddDateFlagContainment:
    """``vault add --date`` may not name a path outside the vault."""

    @pytest.mark.parametrize(
        "shape",
        ["relative", "absolute"],
        ids=["parent-segments", "absolute-path"],
    )
    def test_non_date_flag_value_is_refused_before_any_write(
        self, runner: CliRunner, synthetic_project: Path, shape: str
    ) -> None:
        """A ``--date`` that is not a date fails, and writes nothing anywhere.

        Both shapes exercise the same sink. The relative one walks up out of
        the type directory; the absolute one relies on pathlib discarding
        the base entirely when the joined component is rooted, which is the
        more damaging of the two because the destination is chosen outright
        rather than merely offset.
        """
        landing = synthetic_project.parent / "outside-landing"
        landing.mkdir()
        value = (
            "../../../outside-landing/2026-01-01"
            if shape == "relative"
            else str(landing / "2026-01-01")
        )

        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "vault",
                "add",
                "research",
                "--feature",
                "containment-feat",
                "--date",
                value,
            ],
        )

        assert result.exit_code != 0, result.output
        assert list(landing.iterdir()) == []
        assert _outside_files(synthetic_project) == []
        assert not any(
            (synthetic_project / ".vault" / "research").glob("*containment-feat*")
        )

    def test_refusal_names_the_field_and_the_expected_form(
        self, runner: CliRunner, synthetic_project: Path
    ) -> None:
        """The diagnostic identifies the flag and states what a date looks like."""
        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "vault",
                "add",
                "research",
                "--feature",
                "containment-msg",
                "--date",
                "not-a-date",
            ],
        )

        assert result.exit_code != 0
        assert "--date" in result.output
        assert "YYYY-MM-DD" in result.output


class TestAddDateFlagStillAcceptsRealDates:
    """The admission narrows nothing an operator could legitimately type."""

    def test_canonical_date_scaffolds_at_that_date(
        self, runner: CliRunner, synthetic_project: Path
    ) -> None:
        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "vault",
                "add",
                "research",
                "--feature",
                "canonical-feat",
                "--date",
                "2026-03-04",
            ],
        )

        assert result.exit_code == 0, result.output
        created = (
            synthetic_project
            / ".vault"
            / "research"
            / "2026-03-04-canonical-feat-research.md"
        )
        assert created.is_file()
        assert "date: '2026-03-04'" in created.read_text(encoding="utf-8")

    def test_lenient_slash_form_is_accepted_and_canonicalized(
        self, runner: CliRunner, synthetic_project: Path
    ) -> None:
        """``yyyy/mm/dd`` is one of the forms the vault's parser has always taken.

        It parses to a real date, so it is admitted; the filename it produces
        is the canonical rendering of that date rather than the operator's
        punctuation, which is what keeps a separator out of the path.
        """
        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "vault",
                "add",
                "research",
                "--feature",
                "slash-feat",
                "--date",
                "2026/03/05",
            ],
        )

        assert result.exit_code == 0, result.output
        created = (
            synthetic_project
            / ".vault"
            / "research"
            / "2026-03-05-slash-feat-research.md"
        )
        assert created.is_file()

    def test_omitted_date_defaults_to_today(
        self, runner: CliRunner, synthetic_project: Path
    ) -> None:
        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "vault",
                "add",
                "research",
                "--feature",
                "default-feat",
            ],
        )

        assert result.exit_code == 0, result.output
        today = vault_today().isoformat()
        created = (
            synthetic_project
            / ".vault"
            / "research"
            / f"{today}-default-feat-research.md"
        )
        assert created.is_file()


class TestExecLogPlanDateContainment:
    """A plan's ``date:`` frontmatter may not steer where its ledger lands.

    ``vault exec log`` names both the exec folder and the ledger file from
    the parent plan's date. That value is document content, so a plan
    obtained with a repository - not written by the operator running the
    command - decides those two path segments.
    """

    @pytest.mark.parametrize(
        "shape",
        ["relative", "absolute"],
        ids=["parent-segments", "absolute-path"],
    )
    def test_a_poisoned_stamp_lands_the_ledger_in_the_vault_anyway(
        self, runner: CliRunner, synthetic_project: Path, shape: str
    ) -> None:
        """The stamp is ignored; the plan's own filename date names the ledger.

        Refusing outright would block execution logging on a workspace with
        one bad frontmatter line, so the unusable stamp is set aside in
        favour of the ``yyyy-mm-dd`` prefix the plan's filename carries. The
        security property is unchanged either way - the value used is a
        parsed calendar date - and the ledger lands exactly where a
        well-stamped plan's would.
        """
        landing = synthetic_project.parent / "outside-ledger"
        landing.mkdir()
        plan_file = setup_test_plan(synthetic_project)
        value = (
            "../../../../outside-ledger/2026-01-01"
            if shape == "relative"
            else str(landing / "2026-01-01")
        )
        text = plan_file.read_text(encoding="utf-8")
        plan_file.write_text(
            text.replace("date: '2026-05-17'", f"date: '{value}'", 1),
            encoding="utf-8",
        )

        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "vault",
                "exec",
                "log",
                "--feature",
                "test-feature",
                "--related",
                _PLAN_STEM,
                "--step",
                "P01.S01",
                "--row",
                "M:src/foo.py",
            ],
        )

        assert result.exit_code == 0, result.output
        assert list(landing.iterdir()) == []
        assert _outside_files(synthetic_project) == []
        ledger = (
            synthetic_project
            / ".vault"
            / "exec"
            / "2026-05-17-test-feature"
            / "2026-05-17-test-feature-ledger.md"
        )
        assert ledger.is_file()

    def test_a_plan_with_no_usable_date_at_all_is_refused_by_name(
        self, runner: CliRunner, synthetic_project: Path
    ) -> None:
        """With no filename prefix to fall back on there is nothing to name.

        This is the only shape that still fails, and it fails naming the
        document and the field - the value is content the operator may not
        have written, so identifying it is the difference between an
        actionable refusal and a dead end.
        """
        plan_file = setup_test_plan(synthetic_project)
        undated = plan_file.with_name("undated-test-feature-plan.md")
        undated.write_text(
            plan_file.read_text(encoding="utf-8").replace(
                "date: '2026-05-17'", "date: 'sometime'", 1
            ),
            encoding="utf-8",
        )
        plan_file.unlink()

        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "vault",
                "exec",
                "log",
                "--feature",
                "test-feature",
                "--related",
                "undated-test-feature-plan",
                "--step",
                "P01.S01",
                "--row",
                "M:src/foo.py",
            ],
        )

        assert result.exit_code != 0, result.output
        assert undated.name in result.output
        assert "date:" in result.output
        assert _outside_files(synthetic_project) == []

    def test_a_well_stamped_plan_still_logs_to_its_own_folder(
        self, runner: CliRunner, synthetic_project: Path
    ) -> None:
        """The unchanged path: a normal plan writes its ledger where it always did."""
        setup_test_plan(synthetic_project)

        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "vault",
                "exec",
                "log",
                "--feature",
                "test-feature",
                "--related",
                _PLAN_STEM,
                "--step",
                "P01.S01",
                "--row",
                "M:src/foo.py",
            ],
        )

        assert result.exit_code == 0, result.output
        ledger = (
            synthetic_project
            / ".vault"
            / "exec"
            / "2026-05-17-test-feature"
            / "2026-05-17-test-feature-ledger.md"
        )
        assert ledger.is_file()
        assert "- `S01` `M` `src/foo.py`" in ledger.read_text(encoding="utf-8")
