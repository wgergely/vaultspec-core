set positional-arguments := false
set shell := ["pwsh", "-NoProfile", "-c"]
set windows-shell := ["pwsh.exe", "-NoProfile", "-c"]

image := "ghcr.io/wgergely/vaultspec-core"
local_image := "vaultspec-core:local"

default:
  @echo "Available commands:"
  @echo "  prod [args...]    Run the vaultspec-core Python CLI (pure 1:1 mirror)"
  @echo "  dev <target>      Development toolchain (deps, lint, fix, audit, test, build, etc.)"
  @echo "  ci                Full CI pipeline: lint → audit → vault check → test"
  @echo ""
  @echo "Run 'just <command> --help' for more details."

# ===========================================================================
#  prod  - pure 1:1 mirror of the vaultspec-core Python CLI
#
#  just prod [args...]  →  uv run vaultspec-core [args...]
#
#  Examples:
#    just prod install . claude --force
#    just prod sync claude --dry-run
#    just prod vault check all --fix
#    just prod vault check all -v
#    just prod vault graph --metrics
#    just prod vault add adr -f my-feature
#    just prod spec rules list
# ===========================================================================

prod *args='':
  if ("{{args}}" -match "^(--help|-h|help)$") { \
    echo "Usage: just prod [args...]" ; \
    echo "" ; \
    echo "Runs the vaultspec-core Python CLI (pure 1:1 mirror)." ; \
    echo "Examples:" ; \
    echo "  just prod install . claude --force" ; \
    echo "  just prod sync claude --dry-run" ; \
    echo "  just prod vault check all --fix" ; \
    echo "  just prod vault check all -v" ; \
    echo "  just prod vault graph --metrics" ; \
    echo "  just prod vault add adr -f my-feature" ; \
    echo "  just prod spec rules list" \
  } else { \
    uv run vaultspec-core {{args}} \
  }

# ===========================================================================
#  dev  - development toolchain (linters, formatters, tests, builds)
#
#  Nothing here exists in the shipped CLI.
#
#  Verbs:
#    deps      dependency management (sync, upgrade, lock)
#    lint      read-only static analysis (ruff, ty, taplo, markdownlint, ...)
#    fix       auto-fix everything fixable (python, toml, markdown, vault)
#    audit     supply-chain / security checks (pip-audit)
#    test      pytest, docker smoke
#    build     uv build, docker build
#    publish   docker push
#    precommit pre-commit hook management (install, upgrade, run)
#
#  Examples:
#    just dev deps sync
#    just dev lint
#    just dev lint type
#    just dev fix
#    just dev fix python
#    just dev fix vault
#    just dev audit deps
#    just dev test python
#    just dev build docker
# ===========================================================================

dev target='--help' *args='':
  switch ("{{target}}") { \
    "deps" { just _dev-deps {{args}} } \
    "lint" { just _dev-lint {{args}} } \
    "fix" { just _dev-fix {{args}} } \
    "audit" { just _dev-audit {{args}} } \
    "test" { just _dev-test {{args}} } \
    "build" { just _dev-build {{args}} } \
    "publish" { just _dev-publish {{args}} } \
    "precommit" { just _dev-precommit {{args}} } \
    { $_ -match "^(--help|-h|help)$" } { \
      echo "Usage: just dev <target> [args...]" ; \
      echo "" ; \
      echo "Targets:" ; \
      echo "  deps      dependency management (sync, upgrade, lock)" ; \
      echo "  lint      read-only static analysis (ruff, ty, taplo, markdownlint, ...)" ; \
      echo "  fix       auto-fix everything fixable (python, toml, markdown, vault)" ; \
      echo "  audit     supply-chain / security checks (pip-audit)" ; \
      echo "  test      pytest, docker smoke" ; \
      echo "  build     uv build, docker build" ; \
      echo "  publish   docker push" ; \
      echo "  precommit pre-commit hook management (install, upgrade, run)" \
    } \
    default { \
      Write-Error "unknown dev target: {{target}}" ; \
      Write-Error "  targets: deps lint fix audit test build publish precommit" ; \
      exit 1 \
    } \
  }

# ===========================================================================
#  ci  - full pipeline: lint → audit → vault check → test
# ===========================================================================

ci *args='':
  if ("{{args}}" -match "^(--help|-h|help)$") { \
    echo "Usage: just ci" ; \
    echo "" ; \
    echo "Runs the full CI pipeline: lint → audit → vault check → test" \
  } else { \
    just dev lint all; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } \
    just dev audit deps; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } \
    just prod vault check all; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } \
    just dev test all \
  }

# ---------------------------------------------------------------------------
#  Internal recipes (prefixed with _ to hide from --list)
# ---------------------------------------------------------------------------

_dev-deps target='--help':
  switch ("{{target}}") { \
    "sync" { uv sync --locked --group dev } \
    "upgrade" { uv sync --upgrade --all-groups } \
    "lock" { uv lock } \
    "lock-upgrade" { uv lock --upgrade } \
    { $_ -match "^(--help|-h|help)$" } { \
      echo "Usage: just dev deps <target>" ; \
      echo "" ; \
      echo "Targets:" ; \
      echo "  sync          Sync dependencies" ; \
      echo "  upgrade       Upgrade all dependencies" ; \
      echo "  lock          Lock dependencies" ; \
      echo "  lock-upgrade  Upgrade and lock dependencies" \
    } \
    default { \
      Write-Error "unknown dev deps target: {{target}}" ; \
      Write-Error "  targets: sync upgrade lock lock-upgrade" ; \
      exit 1 \
    } \
  }

_dev-lint target='--help':
  switch ("{{target}}") { \
    "python" { uv run ruff check src tests } \
    "type" { uv run python -m ty check src/vaultspec_core } \
    "links" { \
      if (Get-Command lychee -ErrorAction SilentlyContinue) { \
        lychee --config lychee.toml README.md .vault .vaultspec \
      } elseif (Get-Command docker -ErrorAction SilentlyContinue) { \
        docker run --rm -v "${PWD}:/repo" -w /repo lycheeverse/lychee:latest --config /repo/lychee.toml README.md .vault .vaultspec \
      } else { \
        Write-Error "lychee not found and docker is unavailable" ; \
        exit 127 \
      } \
    } \
    "toml" { \
      if (Get-Command taplo -ErrorAction SilentlyContinue) { \
        taplo lint *.toml \
      } elseif (Get-Command docker -ErrorAction SilentlyContinue) { \
        docker run --rm -v "${PWD}:/repo" -w /repo tamasfe/taplo:0.9 lint *.toml \
      } else { \
        Write-Error "taplo not found and docker is unavailable" ; \
        exit 127 \
      } \
    } \
    "markdown" { \
      uv run mdformat --check README.md .vaultspec/ .vault/ ; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } \
      uv run pymarkdown --config .pymarkdown.json scan -r README.md .vaultspec/ .vault/ \
    } \
    "workflow" { \
      if (Get-Command actionlint -ErrorAction SilentlyContinue) { \
        actionlint \
      } elseif (Get-Command docker -ErrorAction SilentlyContinue) { \
        docker run --rm -v "${PWD}:/repo" -w /repo rhysd/actionlint:latest \
      } else { \
        Write-Error "actionlint not found and docker is unavailable" ; \
        exit 127 \
      } \
    } \
    "all" { \
      just _dev-lint python; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } \
      just _dev-lint type; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } \
      just _dev-lint links; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } \
      just _dev-lint toml; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } \
      just _dev-lint markdown; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } \
      just _dev-lint workflow \
    } \
    { $_ -match "^(--help|-h|help)$" } { \
      echo "Usage: just dev lint <target>" ; \
      echo "" ; \
      echo "Targets:" ; \
      echo "  python    Run Ruff on Python source" ; \
      echo "  type      Run Ty (type checker) on Python source" ; \
      echo "  links     Run Lychee link checker" ; \
      echo "  toml      Run Taplo TOML linter" ; \
      echo "  markdown  Run Markdown linting and formatting checks" ; \
      echo "  workflow  Run Actionlint on GitHub workflows" ; \
      echo "  all       Run all linters" \
    } \
    default { \
      Write-Error "unknown dev lint target: {{target}}" ; \
      Write-Error "  targets: python type links toml markdown workflow all" ; \
      exit 1 \
    } \
  }

_dev-fix target='--help':
  switch ("{{target}}") { \
    "python" { \
      uv run ruff format src tests; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } \
      uv run ruff check --fix src tests \
    } \
    "toml" { \
      if (Get-Command taplo -ErrorAction SilentlyContinue) { \
        taplo fmt *.toml \
      } elseif (Get-Command docker -ErrorAction SilentlyContinue) { \
        docker run --rm -v "${PWD}:/repo" -w /repo tamasfe/taplo:0.9 fmt *.toml \
      } else { \
        Write-Error "taplo not found and docker is unavailable" ; \
        exit 127 \
      } \
    } \
    "markdown" { \
      uv run mdformat README.md .vaultspec/ .vault/ ; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } \
      uv run pymarkdown --config .pymarkdown.json fix -r README.md .vaultspec/ .vault/ \
    } \
    "vault" { uv run vaultspec-core vault check all --fix } \
    "all" { \
      just _dev-fix python; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } \
      just _dev-fix toml; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } \
      just _dev-fix markdown; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } \
      just _dev-fix vault \
    } \
    { $_ -match "^(--help|-h|help)$" } { \
      echo "Usage: just dev fix <target>" ; \
      echo "" ; \
      echo "Targets:" ; \
      echo "  python    Auto-fix and format Python source" ; \
      echo "  toml      Auto-format TOML files" ; \
      echo "  markdown  Auto-format Markdown files" ; \
      echo "  vault     Auto-fix vault issues" ; \
      echo "  all       Run all fixers" \
    } \
    default { \
      Write-Error "unknown dev fix target: {{target}}" ; \
      Write-Error "  targets: python toml markdown vault all" ; \
      exit 1 \
    } \
  }

_dev-audit target='--help':
  switch ("{{target}}") { \
    "deps" { \
      $tmp = [System.IO.Path]::GetTempFileName() ; \
      try { \
        uv export --frozen --group dev --no-emit-project --output-file $tmp ; \
        uv run pip-audit --strict -r $tmp \
      } finally { \
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue \
      } \
    } \
    { $_ -match "^(--help|-h|help)$" } { \
      echo "Usage: just dev audit <target>" ; \
      echo "" ; \
      echo "Targets:" ; \
      echo "  deps      Run pip-audit on dependencies" \
    } \
    default { \
      Write-Error "unknown dev audit target: {{target}}" ; \
      Write-Error "  targets: deps" ; \
      exit 1 \
    } \
  }

_dev-test target='--help':
  switch ("{{target}}") { \
    "python" { uv run pytest src/vaultspec_core -x -q --tb=short -m unit } \
    "docker" { \
      just _dev-build docker; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } \
      docker run --rm {{ local_image }} vaultspec-core --help \
    } \
    "all" { \
      just _dev-test python; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } \
      just _dev-test docker \
    } \
    { $_ -match "^(--help|-h|help)$" } { \
      echo "Usage: just dev test <target>" ; \
      echo "" ; \
      echo "Targets:" ; \
      echo "  python    Run pytest on Python source" ; \
      echo "  docker    Run smoke test in Docker" ; \
      echo "  all       Run all tests" \
    } \
    default { \
      Write-Error "unknown dev test target: {{target}}" ; \
      Write-Error "  targets: python docker all" ; \
      exit 1 \
    } \
  }

_dev-build target='--help':
  switch ("{{target}}") { \
    "python" { uv build } \
    "docker" { docker buildx build --load -t {{ local_image }} . } \
    "all" { \
      just _dev-build python; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } \
      just _dev-build docker \
    } \
    { $_ -match "^(--help|-h|help)$" } { \
      echo "Usage: just dev build <target>" ; \
      echo "" ; \
      echo "Targets:" ; \
      echo "  python    Build Python package" ; \
      echo "  docker    Build Docker image locally" ; \
      echo "  all       Run all builds" \
    } \
    default { \
      Write-Error "unknown dev build target: {{target}}" ; \
      Write-Error "  targets: python docker all" ; \
      exit 1 \
    } \
  }

_dev-publish target='--help' tag='':
  switch ("{{target}}") { \
    "docker-ghcr" { \
      if (-not "{{tag}}") { Write-Error "error: missing argument 'tag' for docker-ghcr" ; exit 1 } \
      docker buildx build --platform linux/amd64 --push -t {{ image }}:{{tag}} . \
    } \
    { $_ -match "^(--help|-h|help)$" } { \
      echo "Usage: just dev publish <target> <tag>" ; \
      echo "" ; \
      echo "Targets:" ; \
      echo "  docker-ghcr   Publish docker image to GHCR" \
    } \
    default { \
      Write-Error "unknown dev publish target: {{target}}" ; \
      Write-Error "  targets: docker-ghcr" ; \
      exit 1 \
    } \
  }

_dev-precommit target='--help':
  switch ("{{target}}") { \
    "install" { uv run prek install } \
    "upgrade" { uv run prek auto-update } \
    "run" { uv run prek run --all-files } \
    { $_ -match "^(--help|-h|help)$" } { \
      echo "Usage: just dev precommit <target>" ; \
      echo "" ; \
      echo "Targets:" ; \
      echo "  install   Install pre-commit hooks" ; \
      echo "  upgrade   Upgrade pre-commit hooks" ; \
      echo "  run       Run pre-commit hooks on all files" \
    } \
    default { \
      Write-Error "unknown dev precommit target: {{target}}" ; \
      Write-Error "  targets: install upgrade run" ; \
      exit 1 \
    } \
  }
