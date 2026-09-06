#!/usr/bin/env python
"""Build the ``vaultspec-core`` and ``vaultspec-mcp`` release binaries with PyApp.

PyApp (https://ofek.dev/pyapp) is a Rust bootstrapper from the Hatch
ecosystem. It is configured entirely through ``PYAPP_*`` environment
variables read at ``cargo`` build time; there is no project-side config
file. This script encodes the decided build model once so the release
workflow (and a maintainer reproducing a release locally) can invoke it
identically on every target.

Two binaries are produced from the same PyPI distribution, differing only
in their execution entry point:

- ``vaultspec-core`` runs ``python -m vaultspec_core`` (PYAPP_EXEC_MODULE).
- ``vaultspec-mcp`` runs the object reference ``vaultspec_core.mcp_server.app:run``
  (PYAPP_EXEC_SPEC), matching the ``vaultspec-mcp`` console script.

The distribution source is the published PyPI package pinned to the release
version: PyApp installs it into a per-user data directory on first launch
(PYAPP_PROJECT_NAME + PYAPP_PROJECT_VERSION) using ``uv`` as the installer
(PYAPP_UV_ENABLED), while the CPython runtime is embedded into the binary
itself (PYAPP_DISTRIBUTION_EMBED). The binary therefore needs no Python on
the user's machine, but first launch does need network access: it fetches
``uv`` itself and resolves ``vaultspec-core==<version>`` and its dependency
closure from PyPI - so the release must be published to PyPI for the binary
to bootstrap. Later launches reuse what was installed and need no network.

Usage::

    uv run --no-project --python 3.13 python dev/binaries/build_pyapp.py \
        --tag vaultspec-core-v0.1.48 --outdir dist-bin [--target <triple>]

``--target`` cross-compiles for a Rust target triple other than the host
(the CI matrix uses it to build the macOS x86_64 binary on an Apple Silicon
runner); the matching ``rustup target`` must already be installed. Only the
Python standard library is used, so any Python 3.13 interpreter can run it.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile
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


@dataclass(frozen=True)
class Binary:
    """One console entry point rendered as a standalone binary."""

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


def build_one(binary: Binary, version: str, target: str, workdir: Path) -> Path:
    """Build a single PyApp binary and return the path to the raw executable."""
    root = workdir / binary.name
    env = os.environ.copy()
    env.update(
        {
            "PYAPP_PROJECT_NAME": PROJECT_NAME,
            "PYAPP_PROJECT_VERSION": version,
            "PYAPP_PYTHON_VERSION": PYTHON_VERSION,
            # Install the project with uv rather than pip on first launch.
            "PYAPP_UV_ENABLED": "1",
            # Bake the CPython distribution into the binary so the target
            # machine needs no interpreter.
            "PYAPP_DISTRIBUTION_EMBED": "1",
        }
    )
    env.update(binary.pyapp_exec_env())

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
        help="Rust target triple to (cross-)build for; defaults to the host",
    )
    args = parser.parse_args()

    version = args.version if args.version else version_from_tag(args.tag)
    target = args.target if args.target else host_target_triple()

    outdir: Path = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    produced: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="pyapp-build-") as tmp:
        workdir = Path(tmp)
        for binary in BINARIES:
            raw = build_one(binary, version, target, workdir)
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
