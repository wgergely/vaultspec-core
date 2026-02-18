# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- MIT LICENSE file with copyright 2026 Gergely Wootsch
- PyPI classifiers, keywords, and project URLs in `pyproject.toml`
- Setuptools package discovery for non-standard `.vaultspec/lib/src/` layout
- CI jobs: `security-audit` (pip-audit) and `type-check` (ty)
- Windows CI matrix for `unit-tests` job
- PyPI OIDC trusted publisher release workflow
- Marketing audit research documents in `.vault/research/`
- Wave 6 strategic features: A2A integration, ACP protocol
  support, subagent MCP server
- System prompt restructure with XML-structured bootstrap

### Changed

- README: replaced placeholder URLs, added PyTorch CUDA install instructions
- `FRAMEWORK.md` and `PROJECT.md` integrated into `system/` directory
- Framework structure reorganized with centralized path management

### Fixed

- Removed 30 type-suppression bandaids across 9 files
- Removed stale type-ignore comments and redundant ty root path
- Pre-existing ruff lint errors in test files

### Removed

- Stale model assertions in provider tests

[Unreleased]: https://github.com/wgergely/task/compare/HEAD...HEAD
