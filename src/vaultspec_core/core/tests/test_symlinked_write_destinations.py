"""Symlinked-destination refusal for the two managed writes that bypassed it.

:func:`~vaultspec_core.core.helpers.atomic_write_bytes` refuses to replace a
symlinked destination: following the link would sever it, leave the real file
stale, and land a managed write on a path the project never chose. Two write
paths reached the filesystem without going through it - the nested rules
``.gitignore`` convergence, which ran on every ``sync``, and the builtin
seeding, which used ``shutil.copy2``. Both open the destination for writing,
so both followed a link planted at that path and overwrote whatever it named.

These tests plant a real link at each destination and assert the file it
points at is unchanged afterwards. The assertion is on the *target's* bytes
rather than on a return value, because a call that reported failure while
still having clobbered the target would satisfy any weaker check.

Symlink creation needs developer mode or elevation on Windows. On a host that
refuses it the attack cannot be staged, so the refusal itself is the asserted
outcome and the scenario ends.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from vaultspec_core.builtins import builtins_root, seed_builtins
from vaultspec_core.config import reset_config
from vaultspec_core.core.rules import converge_spec_layer_gitignore

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

pytestmark = [pytest.mark.unit]

#: The pre-0.1.20 nested policy the rules convergence exists to replace. A
#: link whose target holds this is the only shape that reaches the write at
#: all; anything else is spared by the conservative subset check above it.
_STALE_POLICY = "*.md\n!*.builtin.md\n"

_PRECIOUS = "the operator's own file, which no managed write may replace\n"


@pytest.fixture(autouse=True)
def reset_cfg() -> Generator[None]:
    reset_config()
    yield
    reset_config()


class TestNestedRulesGitignoreConvergence:
    """``.vaultspec/rules/.gitignore`` is written, so a link there is a hazard."""

    def test_a_symlinked_gitignore_does_not_clobber_its_target(
        self, tmp_path: Path
    ) -> None:
        """Fixed content and destroy-only, but on the ``sync`` path.

        The shipped policy is short and known, so nothing is *disclosed* by
        this write - it simply overwrites. That still ends someone's file,
        and it happens on the verb people run most.

        The link's target deliberately carries the stale policy the
        convergence is looking for. A target holding anything else is
        already spared by the conservative subset check further up, which
        reads through the link and declines to touch an operator-customised
        file; the write is only reached when the target looks like exactly
        the file this function exists to replace. That narrow case is the
        one worth pinning, because it is the only one the guard above does
        not already cover.
        """
        rules_dir = tmp_path / ".vaultspec" / "rules"
        rules_dir.mkdir(parents=True)
        precious = tmp_path / "some-other.gitignore"
        precious.write_text(_STALE_POLICY, encoding="utf-8")

        link = rules_dir / ".gitignore"
        try:
            link.symlink_to(precious)
        except (OSError, NotImplementedError):
            assert not link.exists(), "refused symlink left an artifact behind"
            return

        converge_spec_layer_gitignore(rules_dir)

        assert precious.read_text(encoding="utf-8") == _STALE_POLICY
        assert link.is_symlink()

    def test_an_ordinary_stale_gitignore_is_still_converged(
        self, tmp_path: Path
    ) -> None:
        """The refusal must not cost the convergence its actual job."""
        rules_dir = tmp_path / ".vaultspec" / "rules"
        rules_dir.mkdir(parents=True)
        dest = rules_dir / ".gitignore"
        dest.write_text("*.md\n!*.builtin.md\n", encoding="utf-8")
        shipped = (builtins_root() / "rules" / ".gitignore").read_bytes()

        changed = converge_spec_layer_gitignore(rules_dir)

        assert changed is True
        assert dest.read_bytes() == shipped


class TestBuiltinSeeding:
    """Seeding copies bundled files in, so a link at a seed path is a hazard."""

    def test_a_symlinked_seed_destination_does_not_clobber_its_target(
        self, tmp_path: Path
    ) -> None:
        """``--force`` is the mode that overwrites, so it is the mode tested.

        Without ``force`` an existing destination is skipped and the link is
        never opened; the hazard is the upgrade path that deliberately
        replaces what it finds.
        """
        framework = tmp_path / ".vaultspec"
        framework.mkdir()
        seeded = seed_builtins(framework, force=True)
        assert seeded, "no builtins were seeded; the fixture proves nothing"

        relative = seeded[0][0]
        target = framework / relative
        precious = tmp_path / "precious.txt"
        precious.write_text(_PRECIOUS, encoding="utf-8")
        target.unlink()
        try:
            target.symlink_to(precious)
        except (OSError, NotImplementedError):
            assert not target.exists(), "refused symlink left an artifact behind"
            return

        seed_builtins(framework, force=True)

        assert precious.read_text(encoding="utf-8") == _PRECIOUS
        assert target.is_symlink()

    def test_ordinary_seeding_still_writes_the_bundled_bytes(
        self, tmp_path: Path
    ) -> None:
        """The unchanged path: a clean framework directory receives the builtins."""
        framework = tmp_path / ".vaultspec"
        framework.mkdir()

        results = seed_builtins(framework)

        assert results
        assert all(action == "[ADD]" for _, action in results)
        for relative, _ in results:
            assert (framework / relative).read_bytes() == (
                builtins_root() / relative
            ).read_bytes()
