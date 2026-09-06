"""Guards for the prepared distribution the release binaries are built from.

The binaries carry their application and its whole dependency closure, so a
launch installs nothing and needs no network. Two things decide whether that
holds, and neither of them is visible in a build log that ends in "Finished":
the ``PYAPP_*`` settings the binary is compiled from, and the archive those
settings point at.

`.github/workflows/binaries.yml` proves the property on the artifact by running
it with the network taken away. This file proves the inputs to that artifact,
which is the half a `cargo` toolchain is not needed for - and the half that
says *why* an offline run passed, so a future edit that removes the reason goes
red here rather than at the next release.
"""

from __future__ import annotations

import gzip
import re
import tarfile
from pathlib import Path

import pytest

from dev.binaries.build_pyapp import (
    BINARIES,
    CPYTHON_RELEASE,
    CPYTHON_VERSION,
    DISTRIBUTION_SLUG,
    PROJECT_NAME,
    PYTHON_VERSION,
    Binary,
    DistributionError,
    Layout,
    _reset_metadata,
    distribution_url,
    pyapp_env,
    repack,
    strip_install_provenance,
)

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
BINARIES_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "binaries.yml"

#: Every target the release matrix builds. Read from the workflow rather than
#: restated, because a target added there with no distribution row would fail
#: at release time on a machine nobody is watching.
MATRIX_TARGET = re.compile(r"^\s+target:\s+(\S+)\s*$", re.MULTILINE)


def workflow_targets() -> set[str]:
    """Return the target triples ``binaries.yml`` declares."""
    text = BINARIES_WORKFLOW.read_text(encoding="utf-8")
    return set(MATRIX_TARGET.findall(text))


def test_the_workflow_declares_targets_at_all() -> None:
    """Refuse to let the comparisons below pass by matching nothing."""
    assert workflow_targets(), f"no target: rows found in {BINARIES_WORKFLOW}"


def test_every_released_target_has_a_distribution_to_prepare() -> None:
    """A target with no stock archive cannot be built at all, only discovered."""
    assert workflow_targets() <= set(DISTRIBUTION_SLUG), (
        "binaries.yml builds targets DISTRIBUTION_SLUG does not describe: "
        f"{sorted(workflow_targets() - set(DISTRIBUTION_SLUG))}"
    )


def test_no_distribution_is_declared_for_a_target_nobody_builds() -> None:
    """A stale row is a claim about a platform the release does not serve."""
    assert set(DISTRIBUTION_SLUG) <= workflow_targets(), (
        "DISTRIBUTION_SLUG describes targets binaries.yml does not build: "
        f"{sorted(set(DISTRIBUTION_SLUG) - workflow_targets())}"
    )


@pytest.mark.parametrize("target", sorted(DISTRIBUTION_SLUG))
def test_distribution_url_names_the_pinned_release(target: str) -> None:
    """The archive is pinned by release and version, not tracked by tag."""
    url = distribution_url(target)
    assert url.startswith(
        "https://github.com/astral-sh/python-build-standalone/releases/download/"
        f"{CPYTHON_RELEASE}/"
    )
    assert f"cpython-{CPYTHON_VERSION}" in url
    # A literal '+' in a URL path is a space to some servers; the local version
    # separator has to travel percent-encoded.
    assert "+" not in url.rsplit("/", maxsplit=1)[-1]
    assert url.endswith("-install_only_stripped.tar.gz")


def test_the_embedded_series_matches_the_distribution_version() -> None:
    """`PYAPP_PYTHON_VERSION` and the archive must name one interpreter."""
    assert CPYTHON_VERSION.startswith(f"{PYTHON_VERSION}.")


def test_an_undeclared_target_is_refused_rather_than_guessed() -> None:
    """A wrong archive would build cleanly and fail on a user's machine."""
    with pytest.raises(DistributionError, match="no python-build-standalone"):
        distribution_url("s390x-unknown-linux-gnu")


@pytest.mark.parametrize("target", sorted(DISTRIBUTION_SLUG))
@pytest.mark.parametrize("binary", BINARIES, ids=lambda binary: binary.name)
def test_no_binary_installs_anything_at_launch(binary: Binary, target: str) -> None:
    """The two settings that make the artifact offline, on every target.

    ``PYAPP_SKIP_INSTALL`` alone is not enough and that is the whole point of
    asserting both: without full isolation PyApp still builds a virtual
    environment out of the unpacked distribution, and building it fetches
    ``uv`` before it resolves a single package - which is the download #340
    observed.
    """
    env = pyapp_env(binary, "9.9.9", target, Path("dist.tar.gz"))
    assert env["PYAPP_SKIP_INSTALL"] == "1"
    assert env["PYAPP_FULL_ISOLATION"] == "1"


@pytest.mark.parametrize("target", sorted(DISTRIBUTION_SLUG))
def test_the_binary_is_built_against_the_prepared_archive(target: str) -> None:
    """A distribution *path* is what carries the closure; a source would not."""
    prepared = Path("prepared") / f"{PROJECT_NAME}-{target}.tar.gz"
    env = pyapp_env(BINARIES[0], "9.9.9", target, prepared)
    assert env["PYAPP_DISTRIBUTION_PATH"] == str(prepared)
    # PyApp fails the build rather than guessing either of these for an archive
    # it did not choose itself, so their absence is not a survivable default.
    assert env["PYAPP_DISTRIBUTION_PYTHON_PATH"]
    assert env["PYAPP_DISTRIBUTION_SITE_PACKAGES_PATH"]


@pytest.mark.parametrize("target", sorted(DISTRIBUTION_SLUG))
def test_nothing_reintroduces_an_installer(target: str) -> None:
    """Every setting whose only purpose is to install at runtime stays unset.

    `PYAPP_UV_ENABLED` is the one that shipped: it is what fetched `uv` on
    first launch. The project options are installation *sources* - setting any
    of them re-enables the installation step this build exists to remove.

    `PYAPP_ALLOW_UPDATES` is here because its absence is a DECISION rather than
    an oversight. It would re-expose `self update`, which installs from an
    index into an artifact whose whole premise is that it does not, and would
    desynchronise the bytes from the digest the channel pointer and the
    attestation describe. Upgrades belong to Homebrew and Scoop.
    """
    env = pyapp_env(BINARIES[0], "9.9.9", target, Path("dist.tar.gz"))
    for banned in (
        "PYAPP_UV_ENABLED",
        "PYAPP_PROJECT_PATH",
        "PYAPP_PROJECT_DEPENDENCY_FILE",
        "PYAPP_DISTRIBUTION_SOURCE",
        "PYAPP_PIP_EXTERNAL",
        "PYAPP_ALLOW_UPDATES",
    ):
        assert banned not in env, f"{banned} would put an installer back"


def test_windows_layout_uses_the_separator_pyapp_will_not_convert() -> None:
    """PyApp only rewrites a forward-slash path that has a separator to strip.

    ``normalize_relative_path`` in the crate's ``build.rs`` replaces ``/`` with
    ``\\``, then falls back to the *original* argument when there is no leading
    or trailing separator to remove - so a Windows path written with ``/``
    reaches the binary unconverted. Writing the Windows form removes the
    dependency on that behaviour rather than relying on it.
    """
    layout = Layout.for_target("x86_64-pc-windows-msvc")
    assert layout.python == "python\\python.exe"
    assert layout.site_packages == "python\\Lib\\site-packages"


@pytest.mark.parametrize("target", ["x86_64-unknown-linux-gnu", "aarch64-apple-darwin"])
def test_unix_layout_matches_the_install_only_archive(target: str) -> None:
    """The stock archive roots everything under ``python/``."""
    layout = Layout.for_target(target)
    assert layout.python == "python/bin/python3"
    assert layout.site_packages == f"python/lib/python{PYTHON_VERSION}/site-packages"


@pytest.mark.parametrize("target", sorted(DISTRIBUTION_SLUG))
def test_the_layout_resolves_inside_an_unpacked_distribution(
    target: str, tmp_path: Path
) -> None:
    """The declared strings and the paths this builder walks are one thing."""
    layout = Layout.for_target(target)
    interpreter = layout.interpreter(tmp_path)
    site = layout.site(tmp_path)
    assert interpreter.is_relative_to(tmp_path)
    assert site.is_relative_to(tmp_path)
    # Whatever the separator in the declaration, the walk lands under python/.
    assert interpreter.relative_to(tmp_path).parts[0] == "python"
    assert site.relative_to(tmp_path).parts[0] == "python"


def _distribution(root: Path) -> Path:
    """Write a small tree standing in for an unpacked distribution."""
    (root / "python" / "bin").mkdir(parents=True)
    interpreter = root / "python" / "bin" / "python3.13"
    interpreter.write_text("#!/bin/sh\n", encoding="utf-8")
    interpreter.chmod(0o755)
    (root / "python" / "lib").mkdir(parents=True)
    (root / "python" / "lib" / "data.txt").write_text("payload\n", encoding="utf-8")
    return root


def test_repack_is_byte_for_byte_reproducible(tmp_path: Path) -> None:
    """Two runs over one tree produce one archive.

    The archive is embedded in the binary, so its bytes are part of the
    published digest. Without this, the same commit built twice yields two
    different SHA256SUMS and the attestation over them describes a build rather
    than a source.
    """
    root = _distribution(tmp_path / "dist")
    first = repack(root, tmp_path / "first.tar.gz")
    second = repack(root, tmp_path / "second.tar.gz")
    assert first.read_bytes() == second.read_bytes()


def test_repack_carries_no_build_machine_identity(tmp_path: Path) -> None:
    """Ownership and timestamps are the build host leaking into a download."""
    root = _distribution(tmp_path / "dist")
    prepared = repack(root, tmp_path / "prepared.tar.gz")
    with tarfile.open(prepared, "r:gz") as tar:
        members = tar.getmembers()
    assert members, "the archive is empty"
    for member in members:
        assert member.uid == 0
        assert member.gid == 0
        assert member.uname == ""
        assert member.gname == ""
        assert member.mtime == 0
    # The gzip header carries its own clock, and tarfile does not zero it.
    with prepared.open("rb") as raw:
        header = raw.read(8)
    assert header[4:8] == b"\x00\x00\x00\x00", "gzip mtime leaked into the archive"


def test_the_metadata_reset_leaves_permissions_alone(tmp_path: Path) -> None:
    """PyApp runs the archived interpreter directly.

    Asserted on the filter rather than on an extracted file because a Windows
    build host cannot express an execute bit at all, and this invariant has to
    hold on the host that *builds* Linux and macOS archives - which, for a
    maintainer reproducing a release, can be either.
    """
    info = tarfile.TarInfo("python/bin/python3")
    info.mode = 0o755
    assert _reset_metadata(info).mode == 0o755


def test_repack_preserves_the_mode_of_what_it_archives(tmp_path: Path) -> None:
    """Whatever mode the prepared tree has is the mode the archive carries."""
    root = _distribution(tmp_path / "dist")
    source = root / "python" / "bin" / "python3.13"
    prepared = repack(root, tmp_path / "prepared.tar.gz")
    with tarfile.open(prepared, "r:gz") as tar:
        member = tar.getmember("python/bin/python3.13")
    assert member.mode == source.stat().st_mode & 0o777


def test_repack_writes_a_gzip_stream_pyapp_can_read(tmp_path: Path) -> None:
    """The format is inferred from the archive name, so the two must agree."""
    root = _distribution(tmp_path / "dist")
    prepared = repack(root, tmp_path / "prepared.tar.gz")
    assert prepared.name.endswith(".tar.gz")
    with gzip.open(prepared, "rb") as stream:
        assert stream.read(1)


def _site(root: Path) -> Path:
    """Write a ``site-packages`` holding one wheel-installed distribution."""
    dist = root / "vaultspec_core-0.1.73.dist-info"
    dist.mkdir(parents=True)
    (dist / "RECORD").write_text("", encoding="utf-8")
    (dist / "direct_url.json").write_text(
        '{"url": "file:///home/runner/work/x/dist/w.whl", "dir_info": {}}',
        encoding="utf-8",
    )
    return root


def test_the_install_source_is_not_archived(tmp_path: Path) -> None:
    """A `file://` path to the build workspace is build-machine identity.

    Installing from `--wheel` writes the wheel's absolute path into PEP 610
    metadata, so without this the archive - and the digest of every binary
    embedding it - would differ between two machines that built the same tag
    from the same wheel.
    """
    site = _site(tmp_path / "site-packages")
    removed = strip_install_provenance(site)
    assert [record.name for record in removed] == ["direct_url.json"]
    assert not list(site.rglob("direct_url.json"))


def test_stripping_provenance_leaves_the_installation_intact(tmp_path: Path) -> None:
    """Only the source record goes; the distribution stays installed."""
    site = _site(tmp_path / "site-packages")
    strip_install_provenance(site)
    assert (site / "vaultspec_core-0.1.73.dist-info" / "RECORD").is_file()


def test_stripping_provenance_is_silent_on_an_index_install(tmp_path: Path) -> None:
    """Resolving from PyPI writes no such record, and that is not an error."""
    site = tmp_path / "site-packages"
    (site / "vaultspec_core-0.1.73.dist-info").mkdir(parents=True)
    assert strip_install_provenance(site) == []
