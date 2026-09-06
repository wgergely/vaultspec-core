"""The zero-enrolment sync exit must reflect errors the passes accumulated.

``cmd_sync`` short-circuits with "No enabled providers to sync." when the
manifest names no provider this run would touch. That message is true, and the
exit code beside it used to be an unconditional ``0`` computed before
``emit_outcomes`` ever saw the results - so any pass that had already failed was
discarded silently.

Whether that was reachable was open for a long time, because every *resource*
pass filters by the enrolled set before it does work: with nothing enrolled they
do nothing, so they fail at nothing. The provider-hooks pass does not. It loads
the workspace's canonical hook sources first and only then asks which providers
want them, so a hook source that cannot be decoded raises before enrolment is
ever consulted, and ``_run_all_syncs`` records it as an error-carrying result.

Everything here is real: a real installed workspace, a real hook file written in
a real non-UTF-8 encoding, and the real CLI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from vaultspec_core.tests.cli.workspace_factory import WorkspaceFactory

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.unit]

# A hook source saved as cp1252 rather than UTF-8 - the single most ordinary way
# a YAML file on a developer's machine becomes undecodable. `read_text` raises
# UnicodeDecodeError, which is not a `yaml.YAMLError`, so the loader's parse
# guard does not cover it.
UNDECODABLE_HOOK = b"event: pre_tool_use\ncommand: echo caf\xe9\nmatcher: Bash\n"


def workspace_with_failing_hook_pass(tmp_path: Path) -> WorkspaceFactory:
    """Install a workspace, un-enrol every provider, and break the hooks pass."""
    root = tmp_path / "project"
    root.mkdir()
    factory = WorkspaceFactory(root)
    factory.install("claude")
    factory.remove_provider_from_manifest("claude")

    hooks_dir = root / ".vaultspec" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    (hooks_dir / "undecodable.yaml").write_bytes(UNDECODABLE_HOOK)
    return factory


def test_hooks_pass_fails_before_enrolment_is_consulted(tmp_path: Path) -> None:
    """The accumulator really does carry an error on the zero-enrolment path.

    This is the fact the issue could not establish: with nothing enrolled, at
    least one pass still fails, so the discarded exit code is a live defect and
    not dead code.
    """
    factory = workspace_with_failing_hook_pass(tmp_path)

    from vaultspec_core.core.commands import sync_provider
    from vaultspec_core.core.manifest import installed_tool_configs
    from vaultspec_core.core.types import init_paths

    init_paths(factory.root)
    results = sync_provider("all", dry_run=False, force=False, skip=set())

    assert list(installed_tool_configs()) == []
    errors = [e for r in results for e in r.errors]
    assert errors, "expected the hooks pass to record an error"
    assert any("hooks sync failed" in e for e in errors), errors


def test_sync_exits_nonzero_when_a_pass_failed_with_nothing_enrolled(
    tmp_path: Path,
) -> None:
    """A failed pass must set the exit code even when no provider is enrolled."""
    factory = workspace_with_failing_hook_pass(tmp_path)

    result = factory.run("sync")

    assert result.exit_code != 0, (
        f"sync reported success despite a failed pass:\n{result.output}"
    )


def test_sync_still_exits_zero_when_nothing_enrolled_and_nothing_failed(
    tmp_path: Path,
) -> None:
    """The short-circuit stays a success when there is genuinely nothing wrong."""
    root = tmp_path / "clean"
    root.mkdir()
    factory = WorkspaceFactory(root)
    factory.install("claude")
    factory.remove_provider_from_manifest("claude")

    result = factory.run("sync")

    assert result.exit_code == 0, result.output
    assert "No enabled providers to sync" in result.output
