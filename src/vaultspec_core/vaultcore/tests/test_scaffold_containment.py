"""Unit tests for the scaffolder's containment chokepoint and date admission.

The surface tests prove the known doors are shut. These prove the thing that
keeps the next one shut: ``create_vault_doc`` refuses any composed
destination that resolves outside the vault's document root, and it does so
by looking at the path rather than at the field that produced it. A guard
written as "reject a bad date" would leave the next value free to repeat the
escape; a guard written as "reject a destination that is not in the tree"
does not.

Two properties are separated deliberately, because they are not the same
claim. Only a field that *leads* a path component can traverse - which today
means the document's date and its parent plan's date, both admitted as
calendar dates before composition. Every other identity field is embedded
after a prefix and so cannot escape by traversal; what it must still never
do is leave the docs root by any route, and that is asserted directly rather
than assumed. The symlinked type directory covers the route no amount of
field validation reaches, and is what shows the guard is resolution-based.

:func:`normalize_vault_date` is tested for what it guarantees rather than
for a list of strings it happens to reject: whatever it returns is the
rendering of a parsed calendar date, so it cannot carry a separator.
"""

from __future__ import annotations

import datetime as _dt
from typing import TYPE_CHECKING

import pytest

from vaultspec_core.config import reset_config
from vaultspec_core.core.exceptions import VaultSpecError
from vaultspec_core.vaultcore.hydration import (
    DocumentIdentity,
    create_vault_doc,
)
from vaultspec_core.vaultcore.models import DocType, parse_lenient_date
from vaultspec_core.vaultcore.normalize import normalize_vault_date

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def reset_cfg() -> Generator[None]:
    """Reset the process-global config to defaults around every test."""
    reset_config()
    yield
    reset_config()


def _workspace(root: Path) -> Path:
    """Build the minimum on-disk tree ``create_vault_doc`` needs to write."""
    templates = root / ".vaultspec" / "templates"
    templates.mkdir(parents=True, exist_ok=True)
    (templates / "research.md").write_text(
        "---\ntags:\n  - '#research'\n  - '#{feature}'\n"
        "date: '{yyyy-mm-dd}'\nrelated: []\n---\n\n"
        "# `{feature}` research\n\n## Context\n\nProse.\n",
        encoding="utf-8",
    )
    (root / ".vault" / "research").mkdir(parents=True, exist_ok=True)
    return root / ".vaultspec"


class TestContainmentIsBoundToThePathNotTheField:
    """Any composed destination is judged by where it resolves."""

    @pytest.mark.parametrize(
        "feature",
        ["../escaped", "sub/nested", "/rooted"],
        ids=["parent-segment", "separator", "leading-slash"],
    )
    def test_a_separator_bearing_feature_never_lands_outside_the_docs_root(
        self, tmp_path: Path, feature: str
    ) -> None:
        """An un-normalized feature may fail, but it may not escape.

        ``feature`` is embedded after the date prefix, so it cannot lead a
        component and cannot traverse the way a leading field can. The
        property that has to hold regardless is the one asserted: whatever
        the scaffolder does with this - refuse it, or fail to write it - no
        file appears outside the vault's document root. Asserting the
        outcome rather than a specific exception keeps the test honest about
        which platform normalizes trailing dots out of a path component and
        which does not.
        """
        content_root = _workspace(tmp_path)
        docs_root = (tmp_path / ".vault").resolve()
        landing = tmp_path / "outside"
        landing.mkdir()

        created: Path | None
        try:
            created = create_vault_doc(
                tmp_path,
                DocumentIdentity(
                    doc_type=DocType.RESEARCH, feature=feature, date="2026-01-01"
                ),
                content_root=content_root,
            )
        except (VaultSpecError, OSError, ValueError):
            created = None

        assert list(landing.iterdir()) == []
        if created is not None:
            assert docs_root in created.resolve().parents

    def test_a_symlinked_type_directory_is_refused(self, tmp_path: Path) -> None:
        """Containment resolves before comparing, so a link cannot relay a write.

        Windows refuses symlink creation without developer mode or
        elevation; there the attack cannot be staged at all, so the refusal
        to create the link is itself the asserted outcome and the scenario
        ends.
        """
        content_root = _workspace(tmp_path)
        outside = tmp_path / "outside-type-dir"
        outside.mkdir()
        research = tmp_path / ".vault" / "research"
        research.rmdir()
        try:
            research.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            assert not research.exists(), "refused symlink left an artifact behind"
            return

        with pytest.raises(VaultSpecError, match="outside the managed"):
            create_vault_doc(
                tmp_path,
                DocumentIdentity(
                    doc_type=DocType.RESEARCH, feature="linked", date="2026-01-01"
                ),
                content_root=content_root,
            )

        assert list(outside.iterdir()) == []

    def test_the_ordinary_destination_is_still_written(self, tmp_path: Path) -> None:
        """The guard admits the path every real scaffold takes."""
        content_root = _workspace(tmp_path)

        created = create_vault_doc(
            tmp_path,
            DocumentIdentity(
                doc_type=DocType.RESEARCH, feature="ordinary", date="2026-01-01"
            ),
            content_root=content_root,
        )

        assert created == (
            tmp_path / ".vault" / "research" / "2026-01-01-ordinary-research.md"
        )
        assert created.is_file()


class TestDateAdmissionAtTheSink:
    """The scaffolder admits its own date rather than trusting its callers."""

    @pytest.mark.parametrize(
        "value",
        ["", "not-a-date", "2026-13-45"],
        ids=["empty", "prose", "out-of-range"],
    )
    def test_a_value_that_is_not_a_date_never_reaches_a_path(
        self, tmp_path: Path, value: str
    ) -> None:
        content_root = _workspace(tmp_path)

        with pytest.raises(VaultSpecError):
            create_vault_doc(
                tmp_path,
                DocumentIdentity(
                    doc_type=DocType.RESEARCH, feature="datefeat", date=value
                ),
                content_root=content_root,
            )

        assert list((tmp_path / ".vault" / "research").iterdir()) == []

    def test_a_dry_run_is_refused_too(self, tmp_path: Path) -> None:
        """Preview resolves the same path, so it is admitted on the same terms.

        A dry run that happily reported an out-of-bounds destination would
        be a reconnaissance oracle, and callers that resolve-then-write in
        two calls (the ledger writer does exactly that) would carry the bad
        value through to the write regardless.
        """
        from vaultspec_core.vaultcore.hydration import WritePolicy

        content_root = _workspace(tmp_path)

        with pytest.raises(VaultSpecError):
            create_vault_doc(
                tmp_path,
                DocumentIdentity(
                    doc_type=DocType.RESEARCH, feature="dryfeat", date="../../elsewhere"
                ),
                write=WritePolicy(dry_run=True),
                content_root=content_root,
            )


class TestNormalizeVaultDate:
    """What the normalizer returns is a rendered date, not a filtered string."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("2026-03-04", "2026-03-04"),
            ("2026/03/04", "2026-03-04"),
            # Year-last is admitted only when one of the two leading
            # components exceeds 12, so this case cannot also be the 4th of
            # March: 04-03-2026 is ambiguous and the parser rejects it by
            # design rather than guessing a convention.
            ("25-03-2026", "2026-03-25"),
            ("2026-03-04T23:00:00+00:00", "2026-03-04"),
            (_dt.date(2026, 3, 4), "2026-03-04"),
            (_dt.datetime(2026, 3, 4, 12, 0, tzinfo=_dt.UTC), "2026-03-04"),
        ],
        ids=[
            "canonical",
            "year-first-slash",
            "unambiguous-year-last",
            "iso-timestamp",
            "date-object",
            "datetime-object",
        ],
    )
    def test_every_form_the_vault_parser_accepts_is_admitted(
        self, raw: object, expected: str
    ) -> None:
        """The admission narrows nothing: it is the lenient parser's own set.

        Tightening this to canonical-only would reject frontmatter the
        project has always tolerated and that ``vault check all --fix``
        exists to normalize, so the accepted set is pinned here against a
        well-meant future narrowing.
        """
        result = normalize_vault_date(raw)

        assert result.ok
        assert result.value == expected

    @pytest.mark.parametrize(
        "raw",
        ["", "   ", "not-a-date", "2026-13-45", "03-04-2026", None, 20260304],
        ids=[
            "empty",
            "blank",
            "prose",
            "out-of-range",
            "ambiguous-year-last",
            "none",
            "integer",
        ],
    )
    def test_anything_that_is_not_a_date_is_refused_with_a_message(
        self, raw: object
    ) -> None:
        result = normalize_vault_date(raw)

        assert not result.ok
        assert result.value is None
        assert result.error

    def test_the_returned_token_is_a_rendering_of_a_parsed_date(self) -> None:
        """The structural guarantee, asserted as a property rather than a list.

        Whatever survives is re-rendered from a :class:`datetime.date`, so a
        successful result is always exactly ten characters of digits and
        hyphens - which is why it cannot carry a separator, a relative
        segment, or a drive letter no matter what the caller supplied.
        """
        for raw in ("2026-03-04", "2026/03/04", "25-03-2026", "2026-03-04T01:02:03"):
            result = normalize_vault_date(raw)
            assert result.value is not None
            assert _dt.date.fromisoformat(result.value) == parse_lenient_date(raw)
            assert "/" not in result.value
            assert "\\" not in result.value
            assert ".." not in result.value
