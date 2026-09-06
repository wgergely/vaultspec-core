#!/usr/bin/env python
"""Build the ``vaultspec-core`` and ``vaultspec-mcp`` release binaries with PyApp.

PyApp (https://ofek.dev/pyapp) is a Rust bootstrapper from the Hatch
ecosystem. It is configured entirely through ``PYAPP_*`` environment
variables read at ``cargo`` build time; there is no project-side config
file. This script encodes the decided build model once so the release
workflow (and a maintainer reproducing a release locally) can invoke it
identically on every target.

Two binaries are produced from the same prepared distribution, differing only
in their execution entry point:

- ``vaultspec-core`` runs ``python -m vaultspec_core`` (PYAPP_EXEC_MODULE).
- ``vaultspec-mcp`` runs the object reference ``vaultspec_core.mcp_server.app:run``
  (PYAPP_EXEC_SPEC), matching the ``vaultspec-mcp`` console script.

The binaries install nothing at launch. Each target's build first assembles a
*prepared distribution*: the stock python-build-standalone archive for that
triple with the project and its entire dependency closure installed into that
distribution's own ``site-packages``. PyApp then embeds that archive
(PYAPP_DISTRIBUTION_PATH), unpacks it whole rather than deriving a virtual
environment from it (PYAPP_FULL_ISOLATION), and runs the entry point without
an installation step (PYAPP_SKIP_INSTALL). A binary therefore reaches its
first launch with an interpreter, the application and every dependency already
inside it, and needs no network on any launch.

That is a property, not a hope, and it is only a property because nothing in
the artifact can fetch: with installation skipped and full isolation on, the
bootstrapper's own network paths - the ``uv`` download and the dependency
resolution it drives - are not reachable. `.github/workflows/binaries.yml`
runs each Linux artifact under ``docker run --network none`` before it may
become a release asset, which is the check that speaks to the claim; a
networked ``--version`` asserts nothing about it.

The prepared distribution is per-target because three runtime dependencies
(``pydantic``, ``rustworkx``, ``PyYAML``) ship native code, so a closure
resolved for one triple is not valid on another. Every leg of the release
matrix builds on the architecture it targets, so each resolves its own closure
with its own interpreter rather than by cross-resolution.

Usage::

    uv run --no-project --python 3.13 python dev/binaries/build_pyapp.py \
        --tag vaultspec-core-v0.1.48 --outdir dist-bin \
        [--target <triple>] [--wheel dist/vaultspec_core-0.1.48-py3-none-any.whl]

``--wheel`` is what the project is installed from. The release passes the
wheel it just built, which is why the wheel must exist before the binaries and
why publication to PyPI is no longer a precondition of them. Without it the
pinned ``vaultspec-core==<version>`` is resolved from PyPI instead, so a
maintainer can still reproduce a shipped binary from a published version
alone.

``--target`` selects the Rust target triple; it defaults to the host and every
release leg passes its own. Cross-compiling is no longer supported by this
script: preparing a distribution needs an interpreter of the target platform
to resolve and install into, and the release matrix has had no cross-built leg
since the Intel macOS target was dropped.

Beyond the standard library this needs ``cargo`` (as it always has) and ``uv``,
which installs the closure into the distribution being prepared.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# Pinned PyApp crate version. Bumping this changes the bootstrapper and the
# embedded python-build-standalone distributions it selects, so it is an
# explicit, reviewable dependency rather than "whatever is latest".
PYAPP_VERSION = "0.29.0"

# The PyPI distribution both binaries install from.
PROJECT_NAME = "vaultspec-core"

# Embedded CPython series. Must satisfy the package's requires-python.
PYTHON_VERSION = "3.13"

# The python-build-standalone release the prepared distribution starts from.
#
# PyApp picks a distribution per target from a table compiled into its build
# script, and setting PYAPP_DISTRIBUTION_PATH replaces that choice with this
# one. The two are pinned to the same release deliberately: the interpreter a
# user gets is then the interpreter PYAPP_VERSION would have shipped anyway,
# and this change is about what is installed *beside* the interpreter rather
# than about which interpreter it is. Bumping PYAPP_VERSION means re-reading
# `DEFAULT_CPYTHON_DISTRIBUTIONS` in that crate's `build.rs` and moving these
# two constants with it.
CPYTHON_RELEASE = "20251014"
CPYTHON_VERSION = "3.13.9"

# The python-build-standalone platform slug per Rust target triple, again
# mirroring what PyApp itself would have selected.
#
# `x86_64_v3` on Linux x86-64 is NOT a typo and not a choice made here: PyApp
# defaults that target to the v3 micro-architecture level, so it is what every
# release since binaries existed has shipped. Restating it preserves the
# artifact rather than changing it. It is worth knowing that this is a platform
# requirement the repository has never declared - v3 implies AVX2, so a
# pre-Haswell x86-64 host is outside the artifact's real contract while sitting
# comfortably inside the GLIBC_2.28 floor declared below. Narrowing it is a
# separate decision about what the download promises, not a build detail.
DISTRIBUTION_SLUG: dict[str, str] = {
    "x86_64-unknown-linux-gnu": "x86_64_v3-unknown-linux-gnu",
    "aarch64-unknown-linux-gnu": "aarch64-unknown-linux-gnu",
    "x86_64-pc-windows-msvc": "x86_64-pc-windows-msvc",
    "aarch64-apple-darwin": "aarch64-apple-darwin",
}

# The import name that must exist in the prepared distribution's site-packages
# for the archive to be worth building a binary against.
IMPORT_NAME = "vaultspec_core"


# The platform contract, per target triple: the highest ``GLIBC_x.y`` symbol
# version an artifact for that target is permitted to require. This is the
# promise a download makes about which systems it loads on, and it is declared
# here rather than inherited from whichever machine ran the build - an
# inherited floor moves silently the next time a runner is upgraded.
#
# 2.28 is the manylinux_2_28 baseline and sits below every distribution the
# install documentation names; RHEL 9 and its rebuilds are the binding
# constraint at 2.34.
#
# A target absent from this table declares no libc floor: macOS and Windows
# pin theirs through the SDK and the CRT, neither of which is expressed as an
# ELF symbol version.
GLIBC_FLOOR: dict[str, tuple[int, ...]] = {
    "x86_64-unknown-linux-gnu": (2, 28),
    "aarch64-unknown-linux-gnu": (2, 28),
}

# Section type of the GNU version-requirements table (``.gnu.version_r``).
SHT_GNU_VERNEED = 0x6FFFFFFE


class PlatformFloorError(RuntimeError):
    """An artifact requires a platform newer than its target triple declares."""


class DistributionError(RuntimeError):
    """A prepared distribution could not be assembled, or is not usable."""


@dataclass(frozen=True)
class Layout:
    """Where the interpreter and its ``site-packages`` sit inside an archive.

    PyApp knows these paths for the distributions it selects itself and knows
    none of them for one handed to it by path - it refuses to guess and fails
    the build outright when ``PYAPP_DISTRIBUTION_PYTHON_PATH`` is unset. They
    are the stock python-build-standalone ``install_only`` layout, restated
    here because the archive is now this builder's own artifact rather than an
    upstream download it passes through untouched.

    Separators are the target's, not the builder's. PyApp converts a
    forward-slash path for a Windows target only when that path also has a
    leading or trailing separator to strip, so a Windows path written with
    ``/`` reaches the binary unconverted. Writing the Windows form directly
    removes the dependency on that detail.
    """

    python: str
    site_packages: str

    @classmethod
    def for_target(cls, target: str) -> Layout:
        """Return the archive layout the *target*'s distribution uses."""
        if target.endswith("windows-msvc"):
            return cls(
                python=r"python\python.exe",
                site_packages=r"python\Lib\site-packages",
            )
        return cls(
            python="python/bin/python3",
            site_packages=f"python/lib/python{PYTHON_VERSION}/site-packages",
        )

    def interpreter(self, root: Path) -> Path:
        """Return the interpreter inside an unpacked distribution at *root*."""
        return root.joinpath(*self.python.replace("\\", "/").split("/"))

    def site(self, root: Path) -> Path:
        """Return the ``site-packages`` inside an unpacked distribution."""
        return root.joinpath(*self.site_packages.replace("\\", "/").split("/"))


@dataclass(frozen=True)
class Binary:
    """One console entry point rendered as a self-contained release binary."""

    name: str
    # Exactly one of exec_module / exec_spec is set (PyApp execution modes
    # are mutually exclusive).
    exec_module: str | None = None
    exec_spec: str | None = None

    def pyapp_exec_env(self) -> dict[str, str]:
        if self.exec_module is not None:
            return {"PYAPP_EXEC_MODULE": self.exec_module}
        assert self.exec_spec is not None
        return {"PYAPP_EXEC_SPEC": self.exec_spec}


BINARIES = (
    Binary(name="vaultspec-core", exec_module="vaultspec_core"),
    Binary(name="vaultspec-mcp", exec_spec="vaultspec_core.mcp_server.app:run"),
)


def version_from_tag(tag: str) -> str:
    """Derive the PyPI version from a release tag.

    Release tags are ``vaultspec-core-v<version>`` (see publish.yml); a bare
    ``v<version>`` or ``<version>`` is also accepted for local invocation.
    """
    for prefix in (f"{PROJECT_NAME}-v", "v"):
        if tag.startswith(prefix):
            return tag[len(prefix) :]
    return tag


def host_target_triple() -> str:
    """Return the host Rust target triple as reported by ``rustc``."""
    out = subprocess.run(
        ["rustc", "-vV"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    for line in out.splitlines():
        if line.startswith("host:"):
            return line.split(":", 1)[1].strip()
    raise RuntimeError("could not determine host target triple from `rustc -vV`")


def distribution_url(target: str) -> str:
    """Return the stock python-build-standalone archive URL for *target*."""
    slug = DISTRIBUTION_SLUG.get(target)
    if slug is None:
        known = ", ".join(sorted(DISTRIBUTION_SLUG))
        raise DistributionError(
            f"no python-build-standalone distribution is declared for {target}; "
            f"this builder prepares distributions for: {known}. A new release "
            f"target needs a row in DISTRIBUTION_SLUG, not a fallback."
        )
    name = urllib.parse.quote(
        f"cpython-{CPYTHON_VERSION}+{CPYTHON_RELEASE}-{slug}"
        "-install_only_stripped.tar.gz"
    )
    return (
        "https://github.com/astral-sh/python-build-standalone/releases/download/"
        f"{CPYTHON_RELEASE}/{name}"
    )


def fetch(url: str, dest: Path) -> Path:
    """Download *url* to *dest*, returning it."""
    print(f"fetching {url}", flush=True)
    with urllib.request.urlopen(url) as response, dest.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    print(f"  -> {dest} ({dest.stat().st_size} bytes)", flush=True)
    return dest


def unpack(source: Path, root: Path) -> Path:
    """Extract *source* into *root*, returning it.

    ``filter="tar"`` rather than ``"data"``: the data filter normalises file
    modes, and the mode that matters here is the execute bit on the
    interpreter this script is about to run.
    """
    root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(source, "r:gz") as tar:
        tar.extractall(root, filter="tar")
    return root


def strip_install_provenance(site: Path) -> list[Path]:
    """Remove the recorded install source from every distribution in *site*.

    ``direct_url.json`` is PEP 610 metadata, written when something is
    installed from a path or a URL rather than resolved from an index. Its
    contents are an absolute ``file://`` path to the wheel, which on a runner
    means the workspace directory of the job that happened to build it - build
    -machine identity of exactly the kind :func:`_reset_metadata` strips from
    the tar headers, smuggled in as a file rather than as a mode.

    It is optional metadata describing where an install came from, and nothing
    here reads it: the binary is not pip-managed and cannot be reinstalled in
    place. Removing it means the same wheel prepared on two machines yields
    the same archive, rather than two archives differing by a path.
    """
    removed = [
        record
        for dist in sorted(site.glob("*.dist-info"))
        if (record := dist / "direct_url.json").is_file()
    ]
    for record in removed:
        record.unlink()
    return removed


def repack(root: Path, dest: Path) -> Path:
    """Re-archive an unpacked distribution reproducibly, returning *dest*.

    Entry order, timestamps and ownership are all fixed, and the gzip header
    carries no mtime of its own, so two runs over one tree produce one archive
    - which is what lets the binary embedding it have a digest that describes
    its inputs rather than its build.

    What this does NOT claim is that two machines produce the same release
    binary. This function controls the archive; the Rust compile around it is
    not controlled here, and no check in this repository compares two builds
    of one tag. The archive is made deterministic because a determinism that
    is cheap and unclaimed is worth more than one that is expensive and
    asserted, not because whole-artifact reproducibility has been established.
    """
    entries = sorted(
        (path.relative_to(root).as_posix(), path) for path in root.rglob("*")
    )
    with (
        dest.open("wb") as raw,
        gzip.GzipFile(
            filename="", mode="wb", compresslevel=9, fileobj=raw, mtime=0
        ) as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as tar,
    ):
        for name, path in entries:
            tar.add(path, arcname=name, recursive=False, filter=_reset_metadata)
    return dest


def _reset_metadata(info: tarfile.TarInfo) -> tarfile.TarInfo:
    """Strip build-machine identity from one archive member."""
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    return info


def install_closure(python: Path, requirement: str) -> None:
    """Install *requirement* and every dependency into *python*'s environment.

    ``--only-binary=:all:`` is the load-bearing flag. A source build here would
    succeed against whatever compiler the build machine happens to carry and
    yield an archive whose native modules match nobody's declared platform;
    refusing it turns "this dependency publishes no wheel for this target" into
    a build failure that names the dependency. That is the failure mode which
    shipped ``vaultspec-core-x86_64-apple-darwin`` for several releases exiting
    1 - ``cryptography`` publishes no x86_64 macOS wheel - and it was found by
    a user rather than by the build.
    """
    command = [
        "uv",
        "pip",
        "install",
        "--python",
        str(python),
        # The distribution is not a virtual environment, and uv declines to
        # install into an interpreter that is not one unless the target is
        # stated deliberately.
        "--system",
        "--only-binary=:all:",
        "--no-compile-bytecode",
        requirement,
    ]
    print(f"::group::uv pip install ({requirement})", flush=True)
    subprocess.run(command, check=True)
    print("::endgroup::", flush=True)


def prepare_distribution(
    target: str, requirement: str, workdir: Path, cache: Path
) -> Path:
    """Assemble the per-target distribution the binaries are built against.

    The result is the stock archive for *target* with *requirement* and its
    whole dependency closure installed into the distribution's own
    ``site-packages`` - which is what lets PyApp unpack it and run with
    nothing left to install, and so nothing left to fetch.
    """
    layout = Layout.for_target(target)
    url = distribution_url(target)
    cache.mkdir(parents=True, exist_ok=True)
    stock = cache / Path(urllib.parse.unquote(url)).name
    if not stock.is_file():
        fetch(url, stock)

    root = unpack(stock, workdir / "distribution")
    python = layout.interpreter(root)
    if not python.is_file():
        raise DistributionError(
            f"the stock distribution for {target} has no interpreter at "
            f"{layout.python}; the archive layout moved and Layout.for_target "
            f"no longer describes it"
        )

    install_closure(python, requirement)

    site = layout.site(root)
    if not (site / IMPORT_NAME).is_dir():
        raise DistributionError(
            f"{IMPORT_NAME} is not in {layout.site_packages} after installing "
            f"{requirement}. A binary built against this archive would start "
            f"and then fail to import itself, so it is refused here instead."
        )

    for record in strip_install_provenance(site):
        print(f"dropped {record.relative_to(root).as_posix()}", flush=True)

    prepared = workdir / f"{PROJECT_NAME}-{target}.tar.gz"
    repack(root, prepared)
    print(
        f"prepared {prepared} ({prepared.stat().st_size} bytes) from a stock "
        f"archive of {stock.stat().st_size} bytes",
        flush=True,
    )
    return prepared


def pyapp_env(
    binary: Binary, version: str, target: str, distribution: Path
) -> dict[str, str]:
    """Return the ``PYAPP_*`` settings one binary is compiled from.

    Separated from the build so the offline configuration is assertable
    without a Rust toolchain. It is the only thing that decides whether the
    artifact installs at launch, and "we set the flag" was true of nothing
    before it was true of this.
    """
    layout = Layout.for_target(target)
    return {
        # Metadata only, now that nothing is installed from an index: these
        # name what the binary carries rather than what it goes and fetches.
        "PYAPP_PROJECT_NAME": PROJECT_NAME,
        "PYAPP_PROJECT_VERSION": version,
        "PYAPP_PYTHON_VERSION": PYTHON_VERSION,
        # The prepared archive. Setting a path implicitly enables
        # PYAPP_DISTRIBUTION_EMBED, so the bytes travel inside the binary.
        "PYAPP_DISTRIBUTION_PATH": str(distribution),
        # PyApp knows the internal layout of the distributions it chooses
        # itself and refuses to guess at one handed to it, so these are not
        # optional restatements of a default.
        "PYAPP_DISTRIBUTION_PYTHON_PATH": layout.python,
        "PYAPP_DISTRIBUTION_SITE_PACKAGES_PATH": layout.site_packages,
        # BOTH of these are required for an offline binary, and the second is
        # the one that is easy to leave out. PYAPP_SKIP_INSTALL alone stops the
        # project being installed; without full isolation PyApp still derives a
        # virtual environment from the unpacked distribution, and building that
        # environment fetches `uv` before it resolves anything - which is the
        # download #340 actually observed, ahead of any package. Full isolation
        # runs the unpacked distribution in place, so the fetching code path is
        # never entered at all.
        "PYAPP_SKIP_INSTALL": "1",
        "PYAPP_FULL_ISOLATION": "1",
        **binary.pyapp_exec_env(),
    }


def build_one(
    binary: Binary, version: str, target: str, distribution: Path, workdir: Path
) -> Path:
    """Build a single PyApp binary and return the path to the raw executable."""
    root = workdir / binary.name
    env = os.environ.copy()
    env.update(pyapp_env(binary, version, target, distribution))
    # CLEARED, not merely unset. Every PYAPP_* option is read from the
    # environment by the crate's build script, so one left over in a shell or
    # exported by a workflow would silently reconfigure a release binary.
    #
    # There is no installation here, so there is no installer: the first two
    # would only decide which tool a management command reaches for, and every
    # one of those tools has to be downloaded before it can be reached for.
    # PYAPP_ALLOW_UPDATES is the third because its absence is a decision - it
    # re-exposes `self update`, which would install from an index into an
    # artifact whose premise is that it does not, and would put bytes on disk
    # that the published digest and the attestation no longer describe.
    for inherited in (
        "PYAPP_UV_ENABLED",
        "PYAPP_DISTRIBUTION_SOURCE",
        "PYAPP_ALLOW_UPDATES",
    ):
        env.pop(inherited, None)

    cmd = [
        "cargo",
        "install",
        "pyapp",
        "--version",
        PYAPP_VERSION,
        "--locked",
        "--force",
        "--root",
        str(root),
        "--target",
        target,
    ]
    print(f"::group::cargo install pyapp ({binary.name}, {target})", flush=True)
    subprocess.run(cmd, check=True, env=env)
    print("::endgroup::", flush=True)

    exe = "pyapp.exe" if target.endswith("windows-msvc") else "pyapp"
    produced = root / "bin" / exe
    if not produced.is_file():
        raise FileNotFoundError(f"pyapp did not produce {produced}")
    return produced


def asset_name(binary: Binary, target: str) -> str:
    suffix = ".exe" if target.endswith("windows-msvc") else ""
    return f"{binary.name}-{target}{suffix}"


def write_checksum(asset: Path) -> Path:
    """Write ``<asset>.sha256`` in ``sha256sum``-compatible format.

    ``newline=""`` is load-bearing, not cosmetic. Without it Python's text
    layer rewrites the trailing newline to the host line ending, so the
    Windows leg of the release matrix emits CRLF while every other leg emits
    LF. The aggregated ``SHA256SUMS`` then carries mixed endings and both
    downstream readers break on exactly the Windows rows: ``sha256sum -c``
    refuses to verify them, and a field-splitting reader sees the asset name
    with a trailing carriage return, so a lookup by name finds nothing. That
    is how vaultspec-core-v0.1.60 published a Scoop manifest with empty
    hashes out of a green run.
    """
    digest = hashlib.sha256(asset.read_bytes()).hexdigest()
    checksum = asset.with_name(asset.name + ".sha256")
    checksum.write_text(f"{digest}  {asset.name}\n", encoding="utf-8", newline="")
    return checksum


def _cstring(blob: bytes, offset: int) -> str:
    """Read the NUL-terminated string starting at *offset*."""
    end = blob.index(b"\x00", offset)
    return blob[offset:end].decode("utf-8")


def required_symbol_versions(asset: Path) -> set[str]:
    """Return every versioned symbol requirement recorded in an ELF binary.

    Read from the binary's own ``.gnu.version_r`` table, which is what the
    dynamic loader consults. A requirement recorded there is fatal at load time
    when the host's libc does not define that version, whether or not the
    symbols naming it are weak - so this, not the symbol bindings, is the thing
    that decides where an artifact can run.

    Parsed here rather than shelled out to ``readelf`` so the check needs
    nothing on the build machine but the standard library, and runs identically
    on a maintainer's laptop.
    """
    blob = asset.read_bytes()
    if blob[:4] != b"\x7fELF":
        raise PlatformFloorError(f"{asset.name} is not an ELF binary")
    if (blob[4], blob[5]) != (2, 1):
        raise PlatformFloorError(
            f"{asset.name} is not little-endian ELF64; "
            "every Linux target this builder produces is"
        )

    (section_table,) = struct.unpack_from("<Q", blob, 0x28)
    entry_size, count = struct.unpack_from("<HH", blob, 0x3A)

    versions: set[str] = set()
    for index in range(count):
        header = section_table + index * entry_size
        (kind,) = struct.unpack_from("<I", blob, header + 0x04)
        if kind != SHT_GNU_VERNEED:
            continue
        (offset,) = struct.unpack_from("<Q", blob, header + 0x18)
        strings, entries = struct.unpack_from("<II", blob, header + 0x28)
        # sh_link names the string table the version names live in; sh_info
        # counts the top-level entries, one per needed shared object.
        (string_table,) = struct.unpack_from(
            "<Q", blob, section_table + strings * entry_size + 0x18
        )
        versions |= _verneed_names(blob, offset, entries, string_table)
    return versions


def _verneed_names(
    blob: bytes, offset: int, entries: int, string_table: int
) -> set[str]:
    """Walk one ``.gnu.version_r`` table, returning the versions it requires."""
    names: set[str] = set()
    for _ in range(entries):
        auxiliary, next_entry = struct.unpack_from("<II", blob, offset + 0x08)
        cursor = offset + auxiliary
        (auxiliary_count,) = struct.unpack_from("<H", blob, offset + 0x02)
        for _ in range(auxiliary_count):
            name, next_auxiliary = struct.unpack_from("<II", blob, cursor + 0x08)
            names.add(_cstring(blob, string_table + name))
            if not next_auxiliary:
                break
            cursor += next_auxiliary
        if not next_entry:
            break
        offset += next_entry
    return names


def glibc_version(requirement: str) -> tuple[int, ...] | None:
    """Return the numeric version of a ``GLIBC_x.y`` requirement, else None."""
    prefix = "GLIBC_"
    if not requirement.startswith(prefix):
        return None
    parts = requirement[len(prefix) :].split(".")
    if not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def check_platform_floor(asset: Path, target: str) -> None:
    """Fail the build when *asset* requires a libc newer than *target* allows.

    The build machine's glibc is what an unpinned Linux build ends up
    advertising, so this runs on the produced artifact rather than on the
    toolchain: it is the artifact, not the builder, that a user downloads.
    """
    floor = GLIBC_FLOOR.get(target)
    if floor is None:
        return
    exceeded = sorted(
        requirement
        for requirement in required_symbol_versions(asset)
        if (version := glibc_version(requirement)) is not None and version > floor
    )
    if exceeded:
        declared = ".".join(str(part) for part in floor)
        raise PlatformFloorError(
            f"{asset.name} requires {', '.join(exceeded)} but {target} declares a "
            f"floor of GLIBC_{declared}. The binary will not load on any host "
            f"below the versions it requires. Build this target against a libc "
            f"at or below the declared floor rather than the build machine's."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--tag", help="release tag, e.g. vaultspec-core-v0.1.48")
    source.add_argument("--version", help="PyPI version directly, e.g. 0.1.48")
    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path("dist-bin"),
        help="directory to place the renamed binaries and checksums in",
    )
    parser.add_argument(
        "--target",
        help="Rust target triple to build for; defaults to the host",
    )
    parser.add_argument(
        "--wheel",
        type=Path,
        help=(
            "project wheel to bake into the distribution; defaults to "
            "resolving the pinned version from PyPI"
        ),
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path(".pyapp-distributions"),
        help="directory to keep downloaded stock distributions in",
    )
    args = parser.parse_args()

    version = args.version if args.version else version_from_tag(args.tag)
    target = args.target if args.target else host_target_triple()
    requirement = str(args.wheel) if args.wheel else f"{PROJECT_NAME}=={version}"
    if args.wheel and not args.wheel.is_file():
        raise DistributionError(f"--wheel {args.wheel} does not exist")

    outdir: Path = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    produced: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="pyapp-build-") as tmp:
        workdir = Path(tmp)
        # ONE distribution, both binaries. They differ only in an entry point,
        # so preparing it twice would double the slowest step of the build to
        # embed identical bytes.
        distribution = prepare_distribution(target, requirement, workdir, args.cache)
        for binary in BINARIES:
            raw = build_one(binary, version, target, distribution, workdir)
            asset = outdir / asset_name(binary, target)
            shutil.copy2(raw, asset)
            if not target.endswith("windows-msvc"):
                asset.chmod(0o755)
            check_platform_floor(asset, target)
            checksum = write_checksum(asset)
            produced.extend((asset, checksum))
            print(f"built {asset} ({asset.stat().st_size} bytes)", flush=True)

    print(f"\n{PROJECT_NAME} {version} binaries for {target}:")
    for path in produced:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
