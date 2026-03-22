---
tags:
  - '#research'
  - '#clci-release'
date: '2026-03-22'
related:
  - '[[2026-03-21-cli-release-readiness-audit]]'
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

- `release-please` (Google) - automates release PRs from conventional commits;
  strong but requires strict commit discipline
- `python-semantic-release` - similar to release-please; analyzes commits,
  bumps, tags, publishes
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

**Current state:** existing `publish.yml` has correct OIDC setup
(`id-token: write`, `pypi` environment, `pypa/gh-action-pypi-publish`) but
lacks CI gating, TestPyPI staging, and version validation.

**Recommended multi-stage pipeline:**

```
CI (lint + test) -> build -> verify -> publish-testpypi -> publish-pypi -> github-release
```

Key patterns:

- **Reusable workflows:** extract CI into `ci-reusable.yml` with
  `on: workflow_call`, called from both `ci.yml` and `publish.yml` via `needs:`
- **Build once, publish everywhere:** use `actions/upload-artifact@v4` /
  `actions/download-artifact@v4` to pass dist artifacts between jobs
- **GitHub Environments:** `testpypi` and `pypi` environments provide
  deployment protection rules (required reviewers, wait timers)
- **Attestations:** enable `attestations: true` in `pypa/gh-action-pypi-publish`
  for Sigstore-based supply chain signing (zero-cost, zero-friction)

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

### 9. gaps in current setup

Based on the existing `publish.yml` and \[[2026-03-21-cli-release-readiness-audit]\]:

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

**Phase 1 - Foundation (immediate priority):**

- Switch to `hatch-vcs` for dynamic versioning from git tags
- Extract CI into reusable workflow (`ci-reusable.yml` with `on: workflow_call`)
- Full multi-stage publish pipeline:
  - CI gate (lint + test via reusable workflow, `needs:` dependency)
  - Build step (`uv build`) with artifact upload
  - Build verification (`uvx twine check dist/*`)
  - TestPyPI publish (separate `testpypi` environment + trusted publisher)
  - PyPI publish (existing `pypi` environment, trusted publishing via OIDC)
  - GitHub Release creation (`softprops/action-gh-release@v2`) with
    auto-generated notes and dist artifacts attached
- Enable Sigstore attestations (`attestations: true` in publish action)
- Create `.github/release.yml` for categorized changelog labels
- Register trusted publishers on both pypi.org and test.pypi.org
- Document install methods: `uv tool install vaultspec-core` /
  `pipx install vaultspec-core`

**Phase 2 - Standalone binaries:**

- Add PyInstaller/Nuitka matrix build to publish workflow
- Attach platform binaries to GitHub Releases
- Create install script (`curl | sh` pattern)
- Validate pydantic-core Rust extension bundling

**Phase 3 - Package managers:**

- Create Scoop bucket with manifest pointing to GH Release binaries
- Create Homebrew tap (Python formula initially, binary formula after Phase 2)
- Evaluate Chocolatey/winget based on user demand
