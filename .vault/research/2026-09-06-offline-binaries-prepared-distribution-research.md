---
tags:
  - '#research'
  - '#offline-binaries'
date: '2026-09-06'
modified: '2026-09-06'
body_schema: 'body-v2'
body_hash: 'sha256:1e0427b6ce7ce5022fb61cf277416aca9a4a57114fe7c52a72112c732975dd8c'
related:
  - "[[2026-08-29-offline-binaries-research]]"
---

# `offline-binaries` research: `measuring the prepared distribution and the isolation available to gate it`

`2026-08-29-offline-binaries-research` established the shape of a prepared
distribution and left three things unmeasured: how much bigger the download
gets, whether `PYAPP_SKIP_INSTALL` is by itself enough, and what a
`--network none` gate could actually be run under on this fleet. All three were
measured against a real artifact built for `x86_64-unknown-linux-gnu` inside the
pinned `manylinux_2_28_x86_64` image, and against cross-resolved closures for
the other three targets. The prepared route works, the gate is available on
Linux only, and the artifacts roughly double in size.

## Findings

### Skipping installation is not sufficient on its own; full isolation is what removes the fetch

`PYAPP_SKIP_INSTALL` suppresses the project installation and nothing else.
Without `PYAPP_FULL_ISOLATION`, `materialize()` in `pyapp-0.29.0/src/distribution.rs:247`
takes the virtual-environment branch, and that branch calls `ensure_uv_available()`
BEFORE it consults `skip_install()` at all. The `uv` download therefore still
happens, which is exactly the failure #340 observed - its error names
`astral-sh/uv`, not a package. With `PYAPP_FULL_ISOLATION=1` the unpacked
distribution is used in place (`pyapp-0.29.0/src/distribution.rs:232`) and no
network code path is reachable.

Reproduced end to end: the published `vaultspec-core-v0.1.73`
`x86_64-unknown-linux-gnu` asset, run under `docker run --network none`, exits 1
with `download failed: https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-unknown-linux-gnu.tar.gz`.
A binary built from the same tree with both options set runs `--version`,
`install` and `vault check all` to completion in the same container.

### A distribution supplied by path needs its internal layout declared

`PYAPP_DISTRIBUTION_PATH` implicitly enables embedding
(`pyapp-0.29.0/docs/changelog.md:223`) but disables every default PyApp has for
where the interpreter and `site-packages` sit: `set_python_path` panics if
`PYAPP_DISTRIBUTION_PYTHON_PATH` is unset whenever a path is supplied
(`pyapp-0.29.0/build.rs:809`), and `set_site_packages_path` silently falls back
to a rootless `lib/python3.13/site-packages` that does not exist in a
python-build-standalone archive (`pyapp-0.29.0/build.rs:915`). Both must be
declared, and they must describe the `python/`-rooted `install_only` layout.

`normalize_relative_path` (`pyapp-0.29.0/build.rs:470`) converts a forward-slash
path for a Windows target only when the converted string also has a leading or
trailing separator to strip; otherwise it returns the ORIGINAL argument, so a
Windows path written with `/` reaches the binary unconverted. Writing the
Windows separators directly removes the dependency on that behaviour.

### PyApp defaults Linux x86-64 to a micro-architecture level the repository has never declared

`get_distribution_source` sets `variant_cpu` to `v3` for Linux x86-64 with no
configuration (`pyapp-0.29.0/build.rs:552`), so every published binary for that
target has embedded an `x86_64_v3` CPython. v3 implies AVX2, which is Haswell
and later. That is a narrower platform contract than the declared `GLIBC_2.28`
floor in `dev/binaries/build_pyapp.py`, which reaches distributions that also
run on pre-2013 hardware. Not a regression and not introduced here - it is
restated so the prepared build produces the same artifact - but it is an
undeclared half of the platform contract.

### Artifact size roughly doubles, and one transitive dependency is most of the delta

Measured, in bytes. "stock" is the python-build-standalone `install_only_stripped`
archive PyApp would have embedded anyway; "prepared" is that archive with
`vaultspec-core` 0.1.73 and its full closure installed and re-archived at gzip
level 9.

| target                      | stock    | prepared | published v0.1.73 asset |
| --------------------------- | -------- | -------- | ----------------------- |
| `x86_64-unknown-linux-gnu`  | 33356817 | 65751054 | 37313856                |
| `aarch64-unknown-linux-gnu` | 28414163 | 59557457 | 31861592                |
| `x86_64-pc-windows-msvc`    | 21299543 | 54298058 | 24632320                |
| `aarch64-apple-darwin`      | 16456948 | 42500244 | 19603776                |

The one binary built rather than projected, `x86_64-unknown-linux-gnu`, is
67509088 bytes against a published 37313856 - an increase of 30195232 bytes, or
1.81x. PyApp's own overhead above the embedded archive measured 1758034 bytes.
Cross-resolution is a faithful proxy for this: the closure resolved with
`uv pip install --python-platform` produced an archive within 2478 bytes of the
one the native install produced for the same target.

The closure is 123 MB unpacked on Windows. `numpy` and `numpy.libs` are 43 MB of
that and are not optional - `rustworkx` requires `numpy`. `pip` accounts for a
further 12 MB and is dead weight once installation is skipped; removing it was
not attempted, because deleting files out of an upstream distribution is a new
way for the archive to be subtly wrong for a fraction of the delta.

### Source builds must be refused, not merely unlikely

`uv pip install --only-binary=:all:` is what turns "this dependency publishes no
wheel for this target" into a build failure naming the dependency. Without it a
missing wheel is compiled against whatever toolchain the build machine carries,
producing native modules for nobody's declared platform. This is the failure
that shipped `vaultspec-core-x86_64-apple-darwin` exiting 1 for several releases
(`.github/workflows/binaries.yml`, the dropped `macos-x86_64` row): `cryptography`
publishes macOS wheels for arm64 only.

### Every release leg now builds natively, so nothing is cross-resolved in the shipped path

`2026-08-29-offline-binaries-adr` named the cross-built Intel macOS leg as its
least comfortable part. That leg was dropped in #372 and the matrix has four
rows, each building on the architecture it targets. The preparation step can
therefore install with the target's own interpreter on every leg, and the
foreign-platform resolution that record worried about is not used to build
anything that ships.

### `--network none` is available on Linux only, and not from inside a container job

`unshare --map-root-user --net` fails with `Operation not permitted` inside the
pinned `manylinux_2_28_x86_64` image under a default Docker seccomp profile, so
the isolation cannot be created from inside the container job that builds the
Linux artifacts. It has to come from the docker daemon on the host instead,
which means an UNcontainerised job on the same runner calling
`docker run --network none`. Both Linux runner classes in the build matrix can
do that: the self-hosted x86-64 host serves container jobs, and
`ubuntu-24.04-arm` is a GitHub-hosted runner with a docker daemon.

macOS has a per-process equivalent that needs no privileges: `sandbox-exec` with
`(version 1)(allow default)(deny network*)`. It is documented as deprecated and
has been for years, which argues for a step that fails when it stops working
rather than one that stops isolating.

Windows has no unprivileged per-process network isolation. The two candidates
were a `New-NetFirewallRule` outbound block, which needs administrator rights on
a shared fleet host and can outlive a cancelled job, and a Windows container,
which nothing in this fleet is known to serve. Neither was taken. What remains
available is black-holing every proxy variable read by `reqwest`'s default
client (PyApp's HTTP client) and asserting a cold start still succeeds. That
detects a fetch; it does not prove no path exists.

PyApp resolves its data directory on Windows through the known-folder API rather
than through `LOCALAPPDATA`, so a redirected environment variable is not a
reliable way to force a cold start there. The directory is per-version, which
makes a first run of a newly built artifact cold regardless; an assertion about
what was fetched has to search both the redirected root and the real one.

### What was not investigated

Whether removing `pip` and `setuptools` from the prepared distribution is safe,
and what it would save compressed. Whether a `tar.zst` archive would recover a
useful part of the size delta - PyApp supports `tar|zstd` at runtime
(`pyapp-0.29.0/build.rs:14`) but Python 3.13's standard library cannot write it,
and the builder is stdlib-only by design. Whether `PYAPP_ALLOW_UPDATES` should
re-expose `self update`; it is off, which is the default once installation is
skipped (`pyapp-0.29.0/build.rs:1184`).

## Sources

- `pyapp-0.29.0/build.rs:470`
- `pyapp-0.29.0/build.rs:552`
- `pyapp-0.29.0/build.rs:809`
- `pyapp-0.29.0/build.rs:915`
- `pyapp-0.29.0/build.rs:1184`
- `pyapp-0.29.0/src/distribution.rs:232`
- `pyapp-0.29.0/src/distribution.rs:247`
- `pyapp-0.29.0/docs/changelog.md:223`
- `dev/binaries/build_pyapp.py`
- `.github/workflows/binaries.yml`
- https://ofek.dev/pyapp/latest/config/installation/
- https://ofek.dev/pyapp/latest/config/distribution/
- https://github.com/astral-sh/python-build-standalone/releases/tag/20251014
