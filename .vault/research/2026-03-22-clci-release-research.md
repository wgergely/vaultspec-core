---
tags:
  - '#research'
  - '#clci-release'
date: '2026-03-22'
related: []
---

# clci-release research: python cli release and distribution pipeline

Research into industry-standard release mechanisms for a Python CLI project
(hatchling build backend, uv toolchain) covering versioning, packaging, PyPI
publishing, standalone binary distribution, platform package managers, and
GitHub Actions CI/CD automation.

## Findings

### 1. versioning strategy

**SemVer is the correct choice** for vaultspec-core. The project has a CLI
surface and MCP API that constitute a public contract. The current static
`version = "0.1.0"` in pyproject.toml should be replaced with dynamic
versioning via `hatch-vcs`.

**hatch-vcs** (recommended for hatchling projects) wraps `setuptools-scm` to
derive versions from git tags:

- Tagged commit `v0.2.0` produces version `0.2.0`
- 3 commits after tag produces `0.2.1.dev3+g1234567`
- Eliminates version drift between pyproject.toml and tags
- Generates `_version.py` at build time for runtime access
- Requires `fetch-depth: 0` in `actions/checkout` for CI

Configuration:

```toml
[build-system]
requires = ["hatchling", "hatch-vcs"]
build-backend = "hatchling.build"

[project]
dynamic = ["version"]  # replaces static version = "0.1.0"

[tool.hatch.version]
source = "vcs"

[tool.hatch.build.hooks.vcs]
version-file = "src/vaultspec_core/_version.py"
```

**Alternatives considered:**

- **`release-please`** (Google) - see section 10 for deep analysis. Automates
  release PRs from conventional commits. Killer feature: PR-based review gate
  before any release ships. Conflicts with `hatch-vcs` (see section 10.2).
- `python-semantic-release` - similar to release-please but Python-native;
  direct push model (no PR review gate)
- `bump2version` / `bump-my-version` - file-based version bumping; declining
  adoption

### 2. pypi distribution

**PyPI + `uv tool install` is the primary distribution path.** The existing
`[project.scripts]` entries (`vaultspec-core`, `vaultspec-mcp`) already enable
console script creation. Users install with:

```
uv tool install vaultspec-core
pipx install vaultspec-core
```

Both create isolated virtualenvs with the binary on PATH. No special packaging
changes needed from the publisher side.

**Pros:** largest ecosystem, users know `pip install`, trusted publishing
eliminates credentials, version resolution built in.

**Cons:** requires Python runtime (unless standalone binaries also shipped),
startup latency with heavy deps (pydantic, starlette, uvicorn pulled in even
for CLI-only use - flagged in release readiness audit as CLI-06).

**Build artifacts:** `uv build` produces both wheel (`.whl`) and sdist
(`.tar.gz`). For a pure-Python project, a single `py3-none-any.whl` serves
all platforms. Both should always be published. Verification via
`uvx twine check dist/*` before upload.

### 3. trusted publishing and ci/cd pipeline

**Current state:** existing `publish.yml` uses `pypa/gh-action-pypi-publish`
with OIDC setup. Should be replaced with `uv publish` for a fully uv-native
pipeline.

**`uv publish` (recommended replacement for `pypa/gh-action-pypi-publish`):**

`uv publish` is the native uv command for uploading packages to PyPI. It
supports OIDC trusted publishing out of the box, making it a drop-in
replacement for the pypa action with a simpler workflow.

Key flags (verified against docs.astral.sh/uv):

- `--trusted-publishing always` - forces OIDC; fails if not in supported CI
- `--publish-url <URL>` - target index URL (or use `--index` with pyproject.toml
  config). Default: `https://upload.pypi.org/legacy/`
- `--check-url <URL>` - verifies existing files in registry before upload;
  skips identical files, handles raced parallel uploads
- `--token` / `UV_PUBLISH_TOKEN` - API token auth (not needed with trusted
  publishing)
- `--no-attestations` / `UV_PUBLISH_NO_ATTESTATIONS` - disables attestation
  uploads. Note: `uv publish` does NOT generate attestations itself;
  attestations must be created separately and placed as
  `.publish.attestation` files alongside distributions (PEP 740)
- `--index <name>` - publish to a named index defined in `pyproject.toml`

**TestPyPI via pyproject.toml index config:**

```toml
[[tool.uv.index]]
name = "testpypi"
url = "https://test.pypi.org/simple/"
publish-url = "https://test.pypi.org/legacy/"
explicit = true
```

Then: `uv publish --index testpypi --trusted-publishing always`

Or directly: `uv publish --publish-url https://test.pypi.org/legacy/ --check-url https://test.pypi.org/simple/ --trusted-publishing always`

**Astral's canonical reference workflow** (from
`astral-sh/trusted-publishing-examples`):

```yaml
name: Release
on:
  push:
    tags:
      - v*
jobs:
  pypi:
    runs-on: ubuntu-latest
    environment:
      name: pypi
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v6
      - run: uv python install 3.13
      - run: uv build
      - run: uv run --isolated --no-project --with dist/*.whl tests/smoke_test.py
      - run: uv run --isolated --no-project --with dist/*.tar.gz tests/smoke_test.py
      - run: uv publish
```

Key observations from the reference workflow:

- No `--trusted-publishing` flag needed - uv auto-detects OIDC environment
- Smoke tests the built wheel AND sdist before publishing
- No `twine check` - replaced by the smoke test pattern
- `uv python install 3.13` ensures consistent Python version

**Advantages of `uv publish` over `pypa/gh-action-pypi-publish`:**

- Single tool for build + publish (no separate action)
- Simpler workflow YAML
- Faster (Rust-native)
- `--check-url` handles idempotent re-uploads gracefully

**Disadvantage:** `uv publish` does not generate Sigstore attestations. The
pypa action has `attestations: true` for this. If attestations are desired,
either use the pypa action or generate attestations separately.

**Recommended multi-stage pipeline:**

```
CI (lint + test) -> build + smoke test -> publish-testpypi -> publish-pypi -> github-release
```

Key patterns:

- **Reusable workflows:** extract CI into `ci-reusable.yml` with
  `on: workflow_call`, called from both `ci.yml` and `publish.yml` via `needs:`
- **Build once, publish everywhere:** use `actions/upload-artifact@v4` /
  `actions/download-artifact@v4` to pass dist artifacts between jobs
- **GitHub Environments:** `testpypi` and `pypi` environments provide
  deployment protection rules (required reviewers, wait timers)
- **Smoke tests replace twine check:** Astral's pattern of installing the
  built artifact and running a smoke test is more thorough than `twine check`

**TestPyPI setup:** separate trusted publisher on test.pypi.org with a
`testpypi` environment. Useful for pre-release validation.

### 4. changelog and release notes

**GitHub's auto-generated release notes** are the pragmatic choice for
early-stage projects. Configure via `.github/release.yml`:

```yaml
changelog:
  categories:
    - title: Breaking Changes
      labels: [breaking]
    - title: Features
      labels: [enhancement, feature]
    - title: Bug Fixes
      labels: [bug, fix]
    - title: Maintenance
      labels: [chore, dependencies, ci]
```

Use `softprops/action-gh-release@v2` with `generate_release_notes: true` or
`gh release create --generate-notes`.

**Alternatives:** `git-cliff` (gaining traction, highly configurable),
`towncrier` (used by pip/pytest but high friction), `python-semantic-release`
(full automation but strict conventional commit requirement).

### 5. pre-release workflow

PEP 440 pre-release versions: `0.2.0a1` (alpha), `0.2.0b1` (beta),
`0.2.0rc1` (release candidate). With `hatch-vcs`, tags like `v0.2.0rc1` are
automatically normalized.

pip does not install pre-releases by default (requires `--pre` flag), so
publishing alphas/betas/RCs directly to PyPI is safe. GitHub Releases marked
with `prerelease: true` via:

```yaml
prerelease: ${{ contains(github.ref, '-rc') || contains(github.ref, '-alpha') }}
```

### 6. standalone binary distribution

**For the audience (developers using AI-assisted tooling):** they almost
certainly have Python 3.13+ and are comfortable with pipx/uv. This
significantly reduces the urgency of standalone binaries.

**Tool comparison for building standalone executables:**

| Tool        | Standalone            | Active   | Binary Size | Startup        | CI Complexity |
| ----------- | --------------------- | -------- | ----------- | -------------- | ------------- |
| PyInstaller | Yes                   | Yes      | 80-120 MB   | Slow (onefile) | Low           |
| Nuitka      | Yes                   | Yes      | 50-80 MB    | Fast           | Medium        |
| cx_Freeze   | Yes                   | Moderate | Large       | Medium         | Low           |
| PyOxidizer  | Yes                   | **Dead** | -           | -              | High          |
| shiv        | **No** (needs Python) | Yes      | Small       | Fast           | Minimal       |
| zipapp      | **No** (needs Python) | Stable   | Tiny        | Fast           | Minimal       |

**Recommendation:** start with **PyInstaller** for simplicity. Evaluate
**Nuitka** if binary size or startup time becomes a concern. The pydantic-core
Rust extension is the main risk factor for both - test early.

**Special consideration:** two entry points (`vaultspec-core`, `vaultspec-mcp`)

- decide whether to produce two binaries or unify under a single binary with
  subcommand routing.

**GitHub Releases naming convention:**

```
vaultspec-core-{version}-{os}-{arch}.{ext}
  e.g. vaultspec-core-0.2.0-linux-x86_64.tar.gz
       vaultspec-core-0.2.0-windows-x86_64.zip
       vaultspec-core-0.2.0-macos-aarch64.tar.gz
```

Plus a `checksums.sha256` file alongside the archives.

**CI matrix for binary builds:**

```yaml
strategy:
  matrix:
    include:
      - os: ubuntu-latest
        target: linux-x86_64
      - os: macos-13
        target: macos-x86_64
      - os: macos-latest
        target: macos-aarch64
      - os: windows-latest
        target: windows-x86_64
```

### 7. platform package managers

**Recommended distribution tiers:**

- **Tier 1 (launch):** PyPI via `uv tool install` / `pipx install`. Zero extra
  work beyond existing setup.

- **Tier 2 (post-launch):** GitHub Releases with standalone binaries
  (PyInstaller/Nuitka). Enables `curl | sh` install and feeds Scoop/Homebrew.

- **Tier 3 (when demand exists):** Homebrew tap, Scoop bucket. Both point to
  GitHub Release artifacts.

- **Tier 4 (only if needed):** Chocolatey, winget, Snap.

**Windows package managers:**

- **Scoop** (recommended first) - JSON manifest in a bucket repo pointing to
  GitHub Release binaries. Lowest friction, developer audience aligns
  perfectly. `poetry`, `ruff`, `uv` are all on Scoop.
- **Chocolatey** - `.nupkg` with PowerShell install script. Moderation queue.
  Moderate maintenance burden.
- **winget** - YAML manifest PR to `microsoft/winget-pkgs`. Needs MSI/EXE
  installer. Higher effort.

**macOS:**

- **Homebrew** - start with own tap (`homebrew-vaultspec`). Two approaches:
  Python formula (installs via pip into Homebrew Python - how httpie/black do
  it) or binary formula (downloads standalone binary from GitHub Releases).
  Migrate to `homebrew-core` when adoption justifies review overhead.

**Linux:**

- PyPI + pipx covers ~90% of the developer audience
- GitHub Releases binaries for users without Python
- Snap is moderate effort with broad Ubuntu reach
- apt/deb and rpm are high effort, not recommended for a small team
- AUR packages are typically community-maintained

### 8. real-world precedent from comparable projects

| Project      | Primary                                        | Binary                       | Homebrew         | Scoop     | Choco     | Notes                                            |
| ------------ | ---------------------------------------------- | ---------------------------- | ---------------- | --------- | --------- | ------------------------------------------------ |
| ruff         | PyPI (platform wheels with Rust binary inside) | GH Releases                  | Formula          | Yes       | -         | Gold standard: native binary inside PyPI wheel   |
| uv           | PyPI (platform wheels)                         | GH Releases + install script | Formula          | Yes       | -         | Same as ruff; install.sh pattern                 |
| httpie       | PyPI                                           | No                           | Formula (Python) | -         | Community | Pure Python, no standalone                       |
| poetry       | PyPI + own installer                           | No                           | Formula          | Community | -         | Custom install script is middle ground           |
| black        | PyPI                                           | No                           | Formula          | -         | -         | PyPI alone is sufficient for Python dev audience |
| cookiecutter | PyPI                                           | No                           | Formula          | -         | -         | Same as black                                    |

**Key insight from Astral (ruff/uv):** PyPI wheels can contain native
platform-specific binaries. This gives `pip install ruff` native performance
without separate binary downloads. However, this requires rewriting the tool
in Rust/C - not applicable for a pure Python project.

### 9. pyapp - standalone binary via hatch ecosystem

**PyApp** (by Ofek Lev, author of Hatch/Hatchling) is a Rust bootstrapper
that wraps Python applications as standalone executables. It is part of the
Hatch ecosystem and the modern alternative to PyInstaller/Nuitka for
hatchling-based projects.

**How it works:**

- PyApp is a Rust crate compiled with `cargo build`
- At build time, configure via environment variables (`PYAPP_PROJECT_NAME`,
  `PYAPP_PROJECT_VERSION`, etc.)
- The resulting binary is a thin Rust launcher that either embeds or
  downloads a Python distribution (`python-build-standalone` - same ones uv
  uses) at first run
- At runtime, it creates an isolated Python environment, installs the package
  via pip or uv, then invokes the entry point
- Subsequent runs reuse the cached environment

**Key configuration (environment variables at build time):**

| Variable                   | Purpose                     | Example                                      |
| -------------------------- | --------------------------- | -------------------------------------------- |
| `PYAPP_PROJECT_NAME`       | PyPI package name           | `vaultspec-core`                             |
| `PYAPP_PROJECT_VERSION`    | Version to install          | `0.2.0`                                      |
| `PYAPP_PROJECT_PATH`       | Embed a local wheel/sdist   | `dist/vaultspec_core-0.2.0-py3-none-any.whl` |
| `PYAPP_PYTHON_VERSION`     | Python version to bundle    | `3.13`                                       |
| `PYAPP_EXEC_MODULE`        | Module to run (`python -m`) | `vaultspec_core`                             |
| `PYAPP_EXEC_SPEC`          | Object reference            | `vaultspec_core.__main__:main`               |
| `PYAPP_DISTRIBUTION_EMBED` | Embed Python in binary      | `true`                                       |
| `PYAPP_UV_ENABLED`         | Use uv instead of pip       | `true`                                       |
| `PYAPP_SELF_COMMAND`       | Enable self-update commands | `self`                                       |
| `PYAPP_PROJECT_FEATURES`   | Optional extras             | `mcp,server`                                 |

**Comparison to PyInstaller/Nuitka:**

| Aspect            | PyApp                          | PyInstaller           | Nuitka     |
| ----------------- | ------------------------------ | --------------------- | ---------- |
| Build tool        | Rust (cargo)                   | Python                | C compiler |
| Binary size       | Small launcher (~5 MB)         | 80-120 MB             | 50-80 MB   |
| First-run latency | Downloads Python + installs    | None                  | None       |
| Fully offline     | Only with `DISTRIBUTION_EMBED` | Yes                   | Yes        |
| Self-update       | Built-in                       | No                    | No         |
| All packages work | Yes (uses real pip/uv)         | Most (hook-dependent) | Most       |
| CI complexity     | Needs Rust toolchain           | Low                   | Medium     |

**For vaultspec-core:** PyApp with `PYAPP_UV_ENABLED=true` and
`PYAPP_DISTRIBUTION_EMBED=true` produces a self-contained binary that uses uv
for fast package installation. The self-update feature (`PYAPP_SELF_COMMAND`)
is a significant advantage over PyInstaller. Main trade-off: requires Rust
toolchain in CI.

**CI matrix for PyApp builds:**

```yaml
strategy:
  matrix:
    include:
      - target: x86_64-unknown-linux-gnu
        os: ubuntu-latest
      - target: x86_64-apple-darwin
        os: macos-13
      - target: aarch64-apple-darwin
        os: macos-latest
      - target: x86_64-pc-windows-msvc
        os: windows-latest
steps:
  - uses: actions/checkout@v5
  - uses: dtolnay/rust-toolchain@stable
    with:
      targets: ${{ matrix.target }}
  - uses: astral-sh/setup-uv@v6
  - run: uv build
  - env:
      PYAPP_PROJECT_PATH: dist/vaultspec_core-*.whl
      PYAPP_PYTHON_VERSION: "3.13"
      PYAPP_EXEC_MODULE: vaultspec_core
      PYAPP_UV_ENABLED: "true"
      PYAPP_DISTRIBUTION_EMBED: "true"
    run: cargo install pyapp --force && cargo build --release --target ${{ matrix.target }}
```

**Status:** actively maintained by Ofek Lev. Used by Hatch itself for
standalone distribution. Dual-licensed Apache-2.0/MIT.

### 10. release-please - automated release management

**release-please** (Google) provides PR-based release automation. Its killer
feature is the human review gate: it opens a Release PR that you merge when
ready, rather than publishing automatically.

**How it works:**

- Runs on every push to main, analyzes Conventional Commit messages
- Opens/updates a single "Release PR" containing: version bump, CHANGELOG.md
  update, manifest update
- When you merge the Release PR, it creates a GitHub Release with a git tag
- Downstream publish jobs gate on `release_created` output

**10.1 Conventional Commits requirement:**

- `feat:` triggers minor bump, appears in changelog
- `fix:` triggers patch bump, appears in changelog
- `feat!:` or `BREAKING CHANGE:` footer triggers major bump
- Other prefixes (`chore:`, `docs:`, `ci:`, `refactor:`) are parsed but
  hidden from changelog by default
- Non-conventional commits are silently ignored (lenient, not strict)
- Minimum discipline: use `feat:` and `fix:` for user-facing changes
- Squash-merge PRs and edit the squash message to be conventional - this is
  the most common workflow

**10.2 Conflict with hatch-vcs:**

`hatch-vcs` and `release-please` are **mutually exclusive** for version
management:

- `hatch-vcs` derives version dynamically from git tags at build time
- `release-please` writes version into files (pyproject.toml) and commits
  the change in the Release PR

**If using release-please:** drop `hatch-vcs`, keep static `version` in
pyproject.toml, let release-please bump it via its `python` release type.
Use `importlib.metadata.version("vaultspec-core")` for runtime version access.

**10.3 Integration with `uv publish`:**

```yaml
name: Release
on:
  push:
    branches: [main]
permissions:
  contents: write
  pull-requests: write
jobs:
  release-please:
    runs-on: ubuntu-latest
    outputs:
      release_created: ${{ steps.release.outputs.release_created }}
      tag_name: ${{ steps.release.outputs.tag_name }}
    steps:
      - uses: google-github-actions/release-please-action@v4
        id: release
        with:
          release-type: python
  publish:
    needs: release-please
    if: ${{ needs.release-please.outputs.release_created }}
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v6
      - run: uv build
      - run: uv publish
```

**10.4 Configuration files:**

`release-please-config.json`:

```json
{
  "release-type": "python",
  "packages": {
    ".": {
      "package-name": "vaultspec-core",
      "changelog-path": "CHANGELOG.md",
      "bump-minor-pre-major": true,
      "bump-patch-for-minor-pre-major": true
    }
  }
}
```

`.release-please-manifest.json`:

```json
{
  ".": "0.1.0"
}
```

**10.5 Comparison matrix:**

| Aspect               | release-please            | hatch-vcs + manual tag | git-cliff + manual tag            |
| -------------------- | ------------------------- | ---------------------- | --------------------------------- |
| Automation           | Full (PR + tag + release) | None                   | Changelog only                    |
| Human gate           | Yes (merge PR to release) | No                     | No                                |
| Changelog            | Auto-generated            | Manual                 | Auto-generated (better templates) |
| Version source       | Files in repo             | Git tags               | Git tags                          |
| Setup complexity     | Medium (2 JSON + Action)  | Low                    | Low                               |
| Conventional commits | Required (but lenient)    | Not needed             | Recommended                       |

**10.6 Recommendation:**

For a project transitioning from no release process, release-please offers
the best value: automatic changelog, version bumping, and a human review gate
before anything ships. The main costs are adopting conventional commits
(lightweight - just `feat:` and `fix:`) and dropping `hatch-vcs` in favor of
static versioning managed by release-please.

### 11. gaps in current setup

Based on the existing `publish.yml` and `2026-03-21-cli-release-readiness-audit`:

- No CI gate before publishing (publish runs independently of lint/test)
- Static version in pyproject.toml (no dynamic versioning)
- No build artifact verification (`twine check`)
- No TestPyPI staging
- No GitHub Release creation (only PyPI publish)
- No changelog generation or release notes
- No standalone binary builds
- No tag format validation
- Version retrieval in `cli_common.py` uses fragile line-scanning of pyproject.toml
  (flagged as CLI-08 in audit)
- No `.github/release.yml` for categorized release notes

## Synthesis and Recommendation

### Key architectural decision: versioning strategy

Two viable paths exist. The ADR must choose one:

**Option A: release-please + static version + `uv publish`**

- release-please owns versioning (bumps `pyproject.toml` via Release PR)
- Conventional commits required (lightweight - `feat:` and `fix:`)
- Auto-generated CHANGELOG.md
- Human review gate before every release
- Publish triggers on `release_created` output, not tag push
- No `hatch-vcs` dependency

**Option B: hatch-vcs + manual tagging + `uv publish`**

- Version derived from git tags at build time
- No commit discipline required
- No automatic changelog (use GitHub's `generate_release_notes` or `git-cliff`)
- Developer manually creates tags: `git tag v0.2.0 && git push --tags`
- Publish triggers on tag push (`v*`)
- Simpler setup, more manual process

**Recommendation:** Option A (release-please) for a project intending to have
users and a public release cadence. The PR review gate and auto-changelog
justify the lightweight conventional commit overhead.

### Phased implementation

**Phase 1 - uv-native release pipeline:**

- Adopt release-please for version management and changelog
  - `release-please-config.json` + `.release-please-manifest.json`
  - Static `version` in pyproject.toml (drop `hatch-vcs` plan)
  - Conventional commits for `feat:` / `fix:` / `feat!:`
- Extract CI into reusable workflow (`ci-reusable.yml` with
  `on: workflow_call`)
- Replace `pypa/gh-action-pypi-publish` with `uv publish`:
  - CI gate (lint + test via reusable workflow, `needs:` dependency)
  - Build step (`uv build`) with artifact upload
  - Smoke test pattern (install built wheel + sdist, run smoke test)
  - PyPI publish via `uv publish` with OIDC trusted publishing
  - GitHub Release created by release-please on PR merge
- Register trusted publisher on pypi.org (environment: `pypi`)
- Create `.github/release.yml` for categorized release note labels
- Document install methods: `uv tool install vaultspec-core` /
  `pipx install vaultspec-core`
- Add smoke test script (`tests/smoke_test.py`) following Astral's pattern

**Phase 2 - Standalone binaries (PyApp):**

- Add PyApp matrix build to release workflow (requires Rust toolchain in CI)
- Configure: `PYAPP_UV_ENABLED=true`, `PYAPP_DISTRIBUTION_EMBED=true`,
  `PYAPP_EXEC_MODULE=vaultspec_core`, `PYAPP_SELF_COMMAND=self`
- Build targets: linux-x86_64, macos-x86_64, macos-aarch64, windows-x86_64
- Attach platform binaries to GitHub Releases with checksums
- Create install script (`curl | sh` pattern)

**Phase 3 - Package managers:**

- Create Scoop bucket with manifest pointing to GH Release binaries
- Create Homebrew tap (Python formula initially, binary formula after Phase 2)
- Evaluate Chocolatey/winget based on user demand

### Open questions for ADR

- TestPyPI stage: include in Phase 1 or defer? Adds pipeline complexity
  for a pure-Python package where smoke tests may be sufficient.
- Attestations: `uv publish` does not generate Sigstore attestations.
  Use `pypa/gh-action-pypi-publish` alongside `uv publish` for attestation,
  or skip attestations until uv adds support?
- Two entry points (`vaultspec-core`, `vaultspec-mcp`): should PyApp Phase 2
  produce two binaries or unify under a single binary?
