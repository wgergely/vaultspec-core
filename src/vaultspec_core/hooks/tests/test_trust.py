"""Regression tests for the workspace-hook consent gate (GHSA-w5xf-54cr-fxcq).

Hook definitions live under ``.vaultspec/hooks/`` and are shared through git, so
a hook file is content a checkout carries rather than content the operator
authored. These tests pin the resulting rule: the engine spawns a hook's command
only when a consent record held outside the workspace vouches for that exact
file, and every ambiguity resolves to a refusal.

Everything here is real. Real YAML files on disk, the real
:func:`~vaultspec_core.hooks.engine.trigger`, and real subprocesses whose only
effect is to create an inert marker file inside the test's own ``tmp_path``. A
test that stubbed the spawn would prove nothing, because the spawn is the thing
being prevented.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

import pytest

from ...hooks import (
    Hook,
    HookAction,
    grant,
    is_trusted,
    load_hooks,
    revoke,
    trigger,
    trust_file_path,
)
from ..trust import TRUST_SCHEMA_VERSION, granted_digests

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.unit]

EVENT = "config.synced"


def carry_hook(workspace: Path, marker: Path, name: str = "carried") -> Path:
    """Write the hook a hostile checkout would carry, with an inert payload.

    The command creates one file and exits. It is deliberately the smallest
    observable side effect that still proves a process ran: if ``marker``
    exists afterwards, the workspace's command executed.
    """
    hooks_dir = workspace / ".vaultspec" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    script = workspace / "payload.py"
    script.write_text(
        f"import pathlib; pathlib.Path({str(marker)!r}).write_text('ran')",
        encoding="utf-8",
    )
    path = hooks_dir / f"{name}.yaml"
    path.write_text(
        f"event: {EVENT}\n"
        "enabled: true\n"
        "actions:\n"
        "  - type: shell\n"
        f"    command: {sys.executable.replace(chr(92), '/')} "
        f"{str(script).replace(chr(92), '/')}\n",
        encoding="utf-8",
    )
    return path


class TestUnconsentedHooksNeverRun:
    """The clone-and-run half of the advisory."""

    def test_carried_hook_does_not_execute_without_consent(
        self, tmp_path: Path
    ) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        marker = tmp_path / "marker.txt"
        carry_hook(workspace, marker)

        hooks = load_hooks(workspace / ".vaultspec" / "hooks")
        assert len(hooks) == 1, "the hook must still load, so listings can show it"

        results = trigger(hooks, EVENT, home=tmp_path / "home")

        assert results == []
        assert not marker.exists(), (
            "a workspace-carried hook ran without an operator consent record"
        )

    def test_consent_lets_the_same_hook_run(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        home = tmp_path / "home"
        marker = tmp_path / "marker.txt"
        path = carry_hook(workspace, marker)

        grant([path], home)
        hooks = load_hooks(workspace / ".vaultspec" / "hooks")
        results = trigger(hooks, EVENT, home=home)

        assert len(results) == 1
        assert results[0].success is True
        assert marker.read_text(encoding="utf-8") == "ran"

    def test_editing_a_trusted_hook_withdraws_consent(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        home = tmp_path / "home"
        marker = tmp_path / "marker.txt"
        path = carry_hook(workspace, marker)
        grant([path], home)

        # The swap an attacker needs: same filename, same approval, new command.
        path.write_text(
            path.read_text(encoding="utf-8") + "# appended\n", encoding="utf-8"
        )

        hooks = load_hooks(workspace / ".vaultspec" / "hooks")
        assert trigger(hooks, EVENT, home=home) == []
        assert not marker.exists()

    def test_revoking_consent_stops_execution(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        home = tmp_path / "home"
        marker = tmp_path / "marker.txt"
        path = carry_hook(workspace, marker)
        grant([path], home)

        assert revoke(path.parent, home) == 1

        hooks = load_hooks(workspace / ".vaultspec" / "hooks")
        assert trigger(hooks, EVENT, home=home) == []
        assert not marker.exists()


class TestConsentRecordLivesOutsideTheWorkspace:
    """A clone must not be able to carry its own approval."""

    def test_ledger_is_not_written_into_the_workspace(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        home = tmp_path / "home"
        path = carry_hook(workspace, tmp_path / "marker.txt")

        grant([path], home)

        ledger = trust_file_path(home)
        assert ledger.is_file()
        assert home in ledger.parents
        assert workspace not in ledger.parents
        # Nothing new appeared under the workspace: the approval is not a file
        # a commit could capture.
        assert sorted(p.name for p in (workspace / ".vaultspec").iterdir()) == ["hooks"]

    def test_ledger_is_keyed_by_absolute_workspace_path(self, tmp_path: Path) -> None:
        """A ledger copied beside a clone at another path grants nothing there."""
        original = tmp_path / "original"
        original.mkdir()
        home = tmp_path / "home"
        path = carry_hook(original, tmp_path / "marker-a.txt")
        grant([path], home)

        clone = tmp_path / "clone"
        clone.mkdir()
        clone_marker = tmp_path / "marker-b.txt"
        clone_hook = carry_hook(clone, clone_marker)

        assert is_trusted(path, home) is True
        assert is_trusted(clone_hook, home) is False
        assert trigger(load_hooks(clone_hook.parent), EVENT, home=home) == []
        assert not clone_marker.exists()


class TestLedgerFailuresDenyExecution:
    """Every doubt about the ledger has to answer "no"."""

    @pytest.mark.parametrize(
        "payload",
        [
            "not json at all",
            json.dumps({"version": TRUST_SCHEMA_VERSION + 1, "scopes": {}}),
            json.dumps(["a", "list", "not", "an", "object"]),
            json.dumps({"scopes": {}}),
        ],
        ids=["unparseable", "future-version", "wrong-shape", "no-version"],
    )
    def test_unusable_ledger_trusts_nothing(self, tmp_path: Path, payload: str) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        home = tmp_path / "home"
        marker = tmp_path / "marker.txt"
        path = carry_hook(workspace, marker)
        grant([path], home)

        trust_file_path(home).write_text(payload, encoding="utf-8")

        assert granted_digests(path.parent, home) == {}
        assert trigger(load_hooks(path.parent), EVENT, home=home) == []
        assert not marker.exists()

    def test_hook_without_a_source_file_is_never_trusted(self, tmp_path: Path) -> None:
        """A hook object with nothing on disk has no bytes to vouch for."""
        marker = tmp_path / "marker.txt"
        script = tmp_path / "payload.py"
        script.write_text(
            f"import pathlib; pathlib.Path({str(marker)!r}).write_text('ran')",
            encoding="utf-8",
        )
        synthesised = Hook(
            name="synthesised",
            event=EVENT,
            actions=[
                HookAction(
                    action_type="shell",
                    command=(
                        f"{sys.executable.replace(chr(92), '/')} "
                        f"{str(script).replace(chr(92), '/')}"
                    ),
                )
            ],
        )

        assert is_trusted(None, tmp_path / "home") is False
        assert trigger([synthesised], EVENT, home=tmp_path / "home") == []
        assert not marker.exists()
