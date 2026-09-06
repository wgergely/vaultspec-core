"""``create_manifest_exclusive`` writes atomically without becoming a clobber.

It was the one manifest write that bypassed the atomic writer - a buffered
``os.fdopen`` on the ``O_EXCL``-created file, no temp, no fsync - so a partial
``providers.json`` could survive an interrupted install and be interpreted
downstream as a legacy workspace (issue #455). The payload now goes through
:func:`~vaultspec_core.core.helpers.atomic_write_bytes`.

That refactor introduces a hazard the original could not have: the atomic
writer ends in ``os.replace``, which clobbers. Every test here pins the
compare-and-swap contract that must survive it - the exclusivity is the entire
point of the function - along with payload completeness and temp-file cleanup.

The durability half of the change (fsync ordering under power loss) is not
observable from userspace and is deliberately not asserted here; the guard that
makes an unreadable manifest safe regardless is the ``strict=True`` read on the
migration trigger, covered in
``vaultspec_core.tests.cli.test_manifest_corruption_failsafe``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from vaultspec_core.core.manifest import (
    ManifestData,
    create_manifest_exclusive,
    read_manifest_data,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.unit]


def _manifest_path(workspace: Path) -> Path:
    return workspace / ".vaultspec" / "providers.json"


class TestExclusivityIsPreserved:
    def test_first_call_creates_a_complete_manifest(self, tmp_path: Path) -> None:
        data = ManifestData(vaultspec_version="1.2.3", installed={"claude"})

        assert create_manifest_exclusive(tmp_path, data) is True

        stored = read_manifest_data(tmp_path)
        assert stored.vaultspec_version == "1.2.3"
        assert stored.installed == {"claude"}
        assert stored.serial == data.serial + 1

    def test_payload_lands_whole_and_parses(self, tmp_path: Path) -> None:
        # A bulky payload, so a writer that flushed in chunks and stopped
        # short would leave a prefix rather than a document.
        data = ManifestData(
            vaultspec_version="1.2.3",
            installed={f"p{i}" for i in range(500)},
            provider_state={f"p{i}": {"blob": "z" * 500} for i in range(500)},
        )

        create_manifest_exclusive(tmp_path, data)

        payload = json.loads(_manifest_path(tmp_path).read_text(encoding="utf-8"))
        assert len(payload["installed"]) == 500
        assert len(payload["provider_state"]) == 500

    def test_second_call_declines_and_preserves_the_incumbent(
        self, tmp_path: Path
    ) -> None:
        create_manifest_exclusive(
            tmp_path, ManifestData(vaultspec_version="1.2.3", installed={"claude"})
        )
        incumbent = _manifest_path(tmp_path).read_bytes()

        created = create_manifest_exclusive(
            tmp_path, ManifestData(vaultspec_version="9.9.9", installed={"gemini"})
        )

        assert created is False
        assert _manifest_path(tmp_path).read_bytes() == incumbent, (
            "routing the payload through an atomic replace must not turn a "
            "create-if-absent into a clobber"
        )

    def test_declining_does_not_disturb_an_unreadable_incumbent(
        self, tmp_path: Path
    ) -> None:
        # The loser must not 'repair' what it found. A corrupt manifest is
        # evidence, and the migration guard now refuses on it rather than
        # replaying the registry; overwriting it here would destroy the very
        # state that refusal exists to preserve.
        _manifest_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        _manifest_path(tmp_path).write_bytes(b'{"version": "2.0", "inst')

        created = create_manifest_exclusive(
            tmp_path, ManifestData(installed={"claude"})
        )

        assert created is False
        assert _manifest_path(tmp_path).read_bytes() == b'{"version": "2.0", "inst'

    def test_no_temporary_files_survive_the_create(self, tmp_path: Path) -> None:
        create_manifest_exclusive(tmp_path, ManifestData(installed={"claude"}))

        residue = [
            item.name
            for item in (tmp_path / ".vaultspec").iterdir()
            if item.name.startswith(".vs-write-")
        ]
        assert residue == []
