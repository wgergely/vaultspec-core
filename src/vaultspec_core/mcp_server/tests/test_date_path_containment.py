"""Containment tests for the date the MCP write tools name documents from.

The MCP surface is the same sink as the CLI reached through a different
door, and it is the door a model drives. ``create`` takes a ``date`` field
declared in the tool schema as a free string; ``log`` takes none, and reads
one out of the parent plan instead - which means the value comes from a file
the model may have been handed rather than from anything it was asked for.

Both tools are exercised over the real in-memory MCP transport against a
real installed vault on the real filesystem, and the assertions read
filesystem state: after a refused call, nothing exists outside the vault
root. A tool that reported failure while still having written the file
would pass an output-only assertion, so the output is never the evidence.

The legitimate cases are asserted alongside, so the admission cannot be
satisfied by refusing every date.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from mcp import Client

from vaultspec_core.mcp_server.app import create_server

from .conftest import data_of

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

_PLAN_STEM = "2026-05-17-contain-feat-plan"


def _write_plan(vault_root: Path, *, date: str) -> Path:
    """Write a minimal one-Step plan stamped with *date*."""
    plan_dir = vault_root / ".vault" / "plan"
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_file = plan_dir / f"{_PLAN_STEM}.md"
    plan_file.write_text(
        "---\ntags:\n  - '#plan'\n  - '#contain-feat'\n"
        f"date: '{date}'\n"
        "modified: '2026-05-17'\ntier: L1\nrelated: []\n---\n\n"
        "# `contain-feat` plan\n\n## Description\n\nProse.\n\n## Steps\n\n"
        "- [ ] `S01` - first; `src/foo.py`.\n\n"
        "## Parallelization\n\nProse.\n\n## Verification\n\nProse.\n",
        encoding="utf-8",
    )
    return plan_file


@pytest.fixture
def landing(vault_root: Path) -> Iterator[Path]:
    """Yield an empty directory beside the vault that nothing may write into.

    It is a sibling of the vault root because that is where a relative
    escape from ``.vault/<type>/`` arrives, and it carries a per-test unique
    name and is removed afterwards so one test can never read another's
    leftovers as its own evidence.
    """
    directory = Path(tempfile.mkdtemp(prefix="vsc-landing-", dir=vault_root.parent))
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _files_under(directory: Path) -> list[Path]:
    """Return every file below *directory*, which the vault must never reach.

    The scan is bounded to a directory this test created for the purpose.
    The MCP vault fixture is rooted in the system temporary directory, so a
    walk of its parent would be a walk of the whole machine's scratch space;
    naming the landing site explicitly is both faster and a sharper
    assertion than "nothing anywhere changed".
    """
    return sorted(path for path in directory.rglob("*") if path.is_file())


class TestCreateToolDateContainment:
    """The ``create`` tool's ``date`` may not choose where the document lands."""

    @pytest.mark.parametrize(
        "shape",
        ["relative", "absolute"],
        ids=["parent-segments", "absolute-path"],
    )
    async def test_non_date_value_fails_the_item_and_writes_nothing(
        self, vault_root: Path, landing: Path, shape: str
    ) -> None:
        value = (
            f"../../../{landing.name}/2026-01-01"
            if shape == "relative"
            else str(landing / "2026-01-01")
        )

        mcp = create_server()
        async with Client(mcp) as client:
            payload: Any = data_of(
                await client.call_tool(
                    "create",
                    {
                        "documents": [
                            {
                                "feature": "contain-feat",
                                "type": "research",
                                "date": value,
                            }
                        ]
                    },
                )
            )

        assert payload["items"][0]["status"] == "failed"
        assert _files_under(landing) == []
        assert not any(
            (vault_root / ".vault" / "research").glob("*contain-feat-research.md")
        )

    async def test_a_bad_date_fails_only_its_own_item(self, vault_root: Path) -> None:
        """Per-item admission, not a batch abort: the next document still applies.

        The batch envelope's whole contract is that one bad item does not
        cost the others, and a validation added at the wrong level would
        quietly break that.
        """
        mcp = create_server()
        async with Client(mcp) as client:
            payload: Any = data_of(
                await client.call_tool(
                    "create",
                    {
                        "documents": [
                            {
                                "feature": "bad-date-feat",
                                "type": "research",
                                "date": "whenever",
                            },
                            {"feature": "good-date-feat", "type": "research"},
                        ]
                    },
                )
            )

        assert payload["status"] == "mixed"
        assert payload["items"][0]["status"] == "failed"
        assert payload["items"][1]["status"] == "created"
        assert any(
            (vault_root / ".vault" / "research").glob("*good-date-feat-research.md")
        )

    async def test_a_real_date_is_still_honoured(self, vault_root: Path) -> None:
        mcp = create_server()
        async with Client(mcp) as client:
            payload: Any = data_of(
                await client.call_tool(
                    "create",
                    {
                        "documents": [
                            {
                                "feature": "kept-date-feat",
                                "type": "research",
                                "date": "2026-03-04",
                            }
                        ]
                    },
                )
            )

        assert payload["items"][0]["status"] == "created"
        assert (
            vault_root / ".vault" / "research" / "2026-03-04-kept-date-feat-research.md"
        ).is_file()


class TestLogToolPlanDateContainment:
    """The ``log`` tool reads its date from the plan, so the plan is the input."""

    @pytest.mark.parametrize(
        "shape",
        ["relative", "absolute"],
        ids=["parent-segments", "absolute-path"],
    )
    async def test_a_poisoned_stamp_lands_the_ledger_in_the_vault_anyway(
        self, vault_root: Path, landing: Path, shape: str
    ) -> None:
        """The stamp is set aside for the plan's own filename date.

        Failing the call would block an agent's execution logging on one bad
        frontmatter line in a plan it did not write. The value actually used
        is a parsed calendar date either way, so the ledger lands where a
        well-stamped plan's would and nothing reaches the landing site.
        """
        value = (
            f"../../../{landing.name}/2026-01-01"
            if shape == "relative"
            else str(landing / "2026-01-01")
        )
        _write_plan(vault_root, date=value)

        mcp = create_server()
        async with Client(mcp) as client:
            payload: Any = data_of(
                await client.call_tool(
                    "log",
                    {
                        "feature": "contain-feat",
                        "plan": _PLAN_STEM,
                        "step": "S01",
                        "rows": ["M:src/foo.py"],
                    },
                )
            )

        assert payload["created"] is True
        assert _files_under(landing) == []
        assert (
            vault_root
            / ".vault"
            / "exec"
            / "2026-05-17-contain-feat"
            / "2026-05-17-contain-feat-ledger.md"
        ).is_file()

    async def test_a_well_stamped_plan_still_logs(self, vault_root: Path) -> None:
        _write_plan(vault_root, date="2026-05-17")

        mcp = create_server()
        async with Client(mcp) as client:
            payload: Any = data_of(
                await client.call_tool(
                    "log",
                    {
                        "feature": "contain-feat",
                        "plan": _PLAN_STEM,
                        "step": "S01",
                        "rows": ["M:src/foo.py"],
                    },
                )
            )

        assert payload["created"] is True
        ledger = (
            vault_root
            / ".vault"
            / "exec"
            / "2026-05-17-contain-feat"
            / "2026-05-17-contain-feat-ledger.md"
        )
        assert ledger.is_file()
        assert "- `S01` `M` `src/foo.py`" in ledger.read_text(encoding="utf-8")
