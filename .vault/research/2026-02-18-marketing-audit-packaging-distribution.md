---
title: "Marketing Audit: Packaging & Distribution"
date: 2026-02-18
type: research
tags: [marketing-audit, packaging]
author: MarketingAgent1
---

## Marketing Audit: Packaging & Distribution Readiness

## Summary

vaultspec 0.1.0 is in active early development. The packaging baseline is functional but far from release-ready. There is no PyPI publishing pipeline, no Docker strategy, no changelog, and the LICENSE file is effectively empty. The GPU-only requirement is a significant distribution constraint that is acknowledged in documentation but not enforced gracefully. The repo name/package name mismatch adds minor friction for first-time contributors.

---

## 1. Installation Experience

**Current State:** Install requires cloning the repository and running `pip install -e ".[rag,dev]"` from source. There is no `pip install vaultspec` path available today — the package is not published on PyPI.

**Gaps:**

- No PyPI release exists.
- `<repository-url>` placeholder in README Quick Start is not filled in (should be the actual GitHub URL).
- The `docs/` directory referenced in README (getting-started.md, concepts.md, etc.) does not appear to exist, resulting in broken documentation links.
- The `.vaultspec/README.md` referenced in README likely does not exist either as a separate file.

**Recommendations:**

- Fill in the actual GitHub clone URL in the README.
- Either create or remove the `docs/` documentation links — broken links damage credibility.
- Add a PyPI badge and installation section once the package is published.

---

## 2. PyPI Readiness

**Current State:** `pyproject.toml` has the minimum required fields: `name`, `version`, `description`, `readme`, `requires-python`, `license`, `authors`, and `dependencies`.

**Gaps:**

- `license = {file = "LICENSE"}` references an effectively empty LICENSE file. PyPI will reject or warn on this.
- No `classifiers` array — PyPI search and filtering rely on trove classifiers (e.g., `Programming Language :: Python :: 3.13`, `License :: ...`, `Development Status :: 3 - Alpha`).
- No `keywords` field for discoverability.
- No `project.urls` table (Homepage, Documentation, Repository, Bug Tracker).

- No `[tool.setuptools.packages.find]` or explicit `packages` config — setuptools may not correctly discover the nested `.vaultspec/lib/src` package layout, which is non-standard.
- The package source layout (`src` under `.vaultspec/lib/`) is highly non-standard. setuptools will likely fail to package it correctly without explicit configuration.
- No `MANIFEST.in` (less critical with setuptools + pyproject.toml, but notable).

- Version `0.1.0` signals pre-release; should be accompanied by a `Development Status :: 3 - Alpha` classifier.

**Recommendations:**

- Add trove classifiers, keywords, and project URLs.
- Explicitly configure `[tool.setuptools.packages.find]` with `where = [".vaultspec/lib/src"]` or restructure the package layout.
- Populate the LICENSE file before any publishing attempt.
- Run `python -m build && twine check dist/*` locally to validate the package before publishing.

---

## 3. CI/CD Pipeline

**Current State:** GitHub Actions CI runs `ruff` lint and unit tests on `ubuntu-latest` for pushes and PRs to `main`. GPU integration tests are commented out.

**Gaps:**

- No publishing workflow (no `release.yml`, no `publish.yml`).
- No version bumping automation (no use of `bump2version`, `commitizen`, or similar).
- No GitHub Releases creation.
- No changelog generation.

- Lint step installs only `ruff` — `ty` (type checker) is in dev dependencies but not run in CI.
- Unit tests install `.[dev]` but not `.[rag]`, so any unit test that imports RAG modules will fail in CI.
- GPU tests are commented out entirely — no self-hosted runner is configured.

**Recommendations:**

- Add a `release.yml` workflow triggered on `v*` tags that: builds the package, creates a GitHub Release, and publishes to PyPI using a trusted publisher (OIDC, not API key secrets).
- Add `ty` type-checking as a CI step.
- Add `pytest --co -q` (collection-only) as a fast smoke test that catches import errors without requiring GPU.
- Document or implement a strategy for GPU CI (self-hosted runner, or skip with a clear gap acknowledgment).

---

## 4. Docker Strategy

**Current State:** No Dockerfile or docker-compose.yml exists.

**Assessment:** Docker is feasible but non-trivial given the CUDA 13.0 requirement. A viable strategy:

- Base image: `nvidia/cuda:13.0.0-runtime-ubuntu24.04` (or equivalent).

- Install Python 3.13 (not in standard NVIDIA images — would require a custom layer or use of `nvidia/cuda` + `deadsnakes` PPA).

- Install PyTorch with cu130 index URL.
- GPU passthrough requires `--gpus all` at runtime (`docker run --gpus all ...`).

**Gaps:** CUDA 13.0 is very recent (2025). Pre-built NVIDIA base images may not yet exist for this version. This needs verification against `nvcr.io` registry.

**Recommendations:**

- A Docker image is a low-priority nice-to-have given the GPU complexity.

- A higher-value investment: provide a `docker-compose.yml` with NVIDIA runtime configured as an example for users who want containerized deployments.
- Ensure the `--extra-index-url` for PyTorch cu130 is prominently documented as a known friction point.

---

## 5. Dependency Analysis

**Core dependencies (always installed):**

- `a2a-sdk`, `agent-client-protocol`, `claude-agent-sdk` — niche/young packages; supply chain risk is elevated for early-stage SDKs. Version pinning floors (>=) with no upper bounds may cause future breakage.
- `pydantic>=2.0.0`, `httpx`, `uvicorn`, `starlette`, `sse-starlette`, `mcp`, `PyYAML` — well-established, reasonable.
- The core install will be moderate in size (~50-100MB depending on pydantic/httpx resolution).

**RAG extras (`.[rag]`):**

- `torch>=2.5.0` — enormous (2-3GB+ with CUDA). The `pip install` path via PyPI will pull CPU-only torch unless the user specifies `--extra-index-url`. This is a critical gap: `pip install vaultspec[rag]` will install CPU torch, which then fails at runtime with `GPUNotAvailableError`.
- `sentence-transformers`, `lancedb`, `einops` — reasonable for RAG use case.

**Security concerns:**

- `claude-agent-sdk>=0.1.30` and `a2a-sdk>=0.3.22` are very new packages with minimal community audit history.
- No `cargo-deny`-equivalent (pip-audit, safety) configured in CI.

**Recommendations:**

- Add `pip-audit` or `safety` scan to CI.
- Document the `--extra-index-url https://download.pytorch.org/whl/cu130` requirement prominently and consider adding a `postinstall` note or a `check_gpu.py` script.
- Consider pinning upper bounds on critical SDK dependencies (`claude-agent-sdk<0.2`, etc.) to avoid silent breaking changes.
- Add a warning at import time if torch is installed but CUDA is unavailable.

---

## 6. GPU Requirement Communication

**Current State:** README Prerequisites section mentions "NVIDIA GPU with CUDA 13.0+ (required for RAG/search features)." The CI comments include the `--extra-index-url` for cu130.

**Gaps:**

- The requirement is mentioned once in Prerequisites but not reinforced in the Quick Start or install command itself.
- `pip install -e ".[rag,dev]"` in Quick Start will silently install CPU torch.
- No graceful degradation: the system raises `GPUNotAvailableError` immediately — there is no CPU fallback path, which is a valid design decision but needs stronger upfront communication.
- CUDA 13.0 is unusually specific and very recent. Most users with NVIDIA cards will have CUDA 11.x or 12.x. CUDA 13.0 requires RTX 40-series or newer. This significantly narrows the compatible user base.

**Recommendations:**

- Add the `--extra-index-url` flag directly to the Quick Start install command.
- Add a system requirements section with explicit GPU model guidance (RTX 40xx or newer recommended).
- Consider providing a `vaultspec check-gpu` CLI command that validates the environment before users attempt to build an index.
- Consider making RAG an optional feature that degrades to keyword search on CPU — this would dramatically expand the addressable user base.

---

## 7. Release Process

**Current State:** No release process exists. No CHANGELOG.md, no tagging convention documented, no publishing workflow.

**Recommended Release Workflow:**

1. Maintain a `CHANGELOG.md` following Keep a Changelog format (or use `git-cliff` for automated generation from conventional commits).
2. Use `commitizen` or `bump2version` for version management.

3. Tag releases as `v0.1.0`, `v0.2.0`, etc.

4. GitHub Actions `release.yml` triggered on tag push:
   - Run full test suite (excluding GPU tests unless self-hosted runner available).
   - Build: `python -m build`.
   - Publish to PyPI via OIDC trusted publisher (no API key needed).
   - Create GitHub Release with auto-generated release notes from CHANGELOG.

5. Consider a separate pre-release channel (TestPyPI) for validation.

---

## 8. Naming and Branding

**Current State:** GitHub repository is named `task` (`https://github.com/wgergely/task`), while the package name is `vaultspec`. The README project name, pyproject.toml name, and CLI scripts all use `vaultspec`.

**Impact:**

- GitHub clone URL will be `git clone https://github.com/wgergely/task` — confusing to users who expect `vaultspec`.

- GitHub search for "vaultspec" will not surface the repository by name.
- PyPI package page will link to the `task` repository, which is dissonant.
- Issue tracker URL mismatch causes confusion in bug reports and documentation.

**Recommendations:**

- Rename the GitHub repository from `task` to `vaultspec` (or `vaultspec-framework`). GitHub redirects old URLs automatically.
- Update `project.urls` in `pyproject.toml` to point to the renamed repository.
- Fill in the `<repository-url>` placeholder in README with the canonical URL.

---

## 9. License

**Current State:** `pyproject.toml` declares `license = {file = "LICENSE"}` but the LICENSE file is empty (1 line, no content).

**Impact:**

- PyPI will show "License :: OSI Approved" as unknown or warn about missing license text.
- Without a license, the project is legally "All Rights Reserved" by default — users cannot legally use, modify, or distribute it.
- This is a critical blocker for any open-source distribution.

**License Recommendation:**

- **MIT License** — best fit for a developer framework/tooling project that wants broad adoption. Simple, permissive, well-understood.
- **Apache 2.0** — if patent protection is desired. Slightly more enterprise-friendly.
- Avoid GPL for a developer tool — it would restrict use in proprietary projects, limiting adoption.

**Action Required:** Populate `LICENSE` with chosen license text before any release.

---

## 10. Platform Support

**Current State:** Development environment is Windows 11 (based on project metadata). CI runs on `ubuntu-latest`. The GPU requirement (CUDA 13.0) implies NVIDIA hardware.

**Gaps:**

- No explicit platform support matrix documented.
- Windows development with Linux CI can mask platform-specific issues (path separators, subprocess behavior, asyncio ProactorEventLoop vs. SelectorEventLoop).
- macOS is effectively unsupported — Apple Silicon uses Metal, not CUDA, so RAG features cannot run.
- PyTorch cu130 wheels may not be available for Windows — needs verification.

**Recommendations:**

- Document supported platforms explicitly: "Linux (primary), Windows (development/testing), macOS (core features only — RAG not supported)."
- Add Windows to CI matrix for unit tests (no GPU needed) to catch path-handling regressions.
- Consider adding macOS to CI for core (non-RAG) unit tests.
- Verify PyTorch cu130 Windows wheel availability and document accordingly.

---

## Priority Matrix

| Priority | Action |
|---|---|
| **CRITICAL** | Populate LICENSE file |
| **CRITICAL** | Document `--extra-index-url` in install instructions |
| **HIGH** | Fix broken `docs/` links in README |
| **HIGH** | Fill in `<repository-url>` placeholder |
| **HIGH** | Add PyPI classifiers, keywords, project URLs |
| **HIGH** | Fix setuptools package discovery for non-standard layout |
| **HIGH** | Rename GitHub repo from `task` to `vaultspec` |
| **MEDIUM** | Add `pip-audit` to CI |
| **MEDIUM** | Add `ty` type-checking to CI |
| **MEDIUM** | Create CHANGELOG.md |
| **MEDIUM** | Add PyPI publishing workflow |
| **LOW** | Docker strategy (GPU complexity makes this low-value near-term) |
| **LOW** | CPU degradation path for RAG |
