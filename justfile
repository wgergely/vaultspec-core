set positional-arguments := false
set shell := ["bash", "-cu"]

image := "ghcr.io/wgergely/vaultspec-core"
local_image := "vaultspec-core:local"

default:
  @just --list

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
  case "{{args}}" in \
    "--help"|"-h"|"help") \
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
      echo "  just prod spec rules list" ;; \
    *) \
      uv run vaultspec-core {{args}} ;; \
  esac

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
  case "{{target}}" in \
    deps) \
      just _dev-deps {{args}} ;; \
    lint) \
      just _dev-lint {{args}} ;; \
    fix) \
      just _dev-fix {{args}} ;; \
    audit) \
      just _dev-audit {{args}} ;; \
    test) \
      just _dev-test {{args}} ;; \
    build) \
      just _dev-build {{args}} ;; \
    publish) \
      just _dev-publish {{args}} ;; \
    precommit) \
      just _dev-precommit {{args}} ;; \
    --help|-h|help) \
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
      echo "  precommit pre-commit hook management (install, upgrade, run)" ;; \
    *) \
      echo "unknown dev target: {{target}}" >&2; \
      echo "  targets: deps lint fix audit test build publish precommit" >&2; \
      exit 1 ;; \
  esac

# ===========================================================================
#  ci  - full pipeline: lint → audit → vault check → test
# ===========================================================================

ci *args='':
  case "{{args}}" in \
    "--help"|"-h"|"help") \
      echo "Usage: just ci" ; \
      echo "" ; \
      echo "Runs the full CI pipeline: lint → audit → vault check → test" ;; \
    *) \
      just dev lint all && \
      just dev audit deps && \
      just prod vault check all && \
      just dev test all ;; \
  esac

# ---------------------------------------------------------------------------
#  Internal recipes (prefixed with _ to hide from --list)
# ---------------------------------------------------------------------------

_dev-deps target='--help':
  case "{{target}}" in \
    sync) \
      uv sync --locked --group dev ;; \
    upgrade) \
      uv sync --upgrade --all-groups ;; \
    lock) \
      uv lock ;; \
    lock-upgrade) \
      uv lock --upgrade ;; \
    --help|-h|help) \
      echo "Usage: just dev deps <target>" ; \
      echo "" ; \
      echo "Targets:" ; \
      echo "  sync          Sync dependencies" ; \
      echo "  upgrade       Upgrade all dependencies" ; \
      echo "  lock          Lock dependencies" ; \
      echo "  lock-upgrade  Upgrade and lock dependencies" ;; \
    *) \
      echo "unknown dev deps target: {{target}}" >&2; \
      echo "  targets: sync upgrade lock lock-upgrade" >&2; \
      exit 1 ;; \
  esac

_dev-lint target='--help':
  case "{{target}}" in \
    python) \
      uv run ruff check src tests ;; \
    type) \
      uv run python -m ty check src/vaultspec_core ;; \
    links) \
      if command -v lychee >/dev/null 2>&1; then \
        lychee --config lychee.toml \
          README.md .vault .vaultspec; \
      elif command -v docker >/dev/null 2>&1; then \
        docker run --rm -v "$PWD:/repo" -w /repo \
          lycheeverse/lychee:latest \
          --config /repo/lychee.toml \
          README.md .vault .vaultspec; \
      else \
        echo "lychee not found and docker is unavailable" >&2; \
        exit 127; \
      fi ;; \
    toml) \
      if command -v taplo >/dev/null 2>&1; then \
        taplo lint *.toml; \
      elif command -v docker >/dev/null 2>&1; then \
        docker run --rm -v "$PWD:/repo" -w /repo \
          tamasfe/taplo:0.9 lint *.toml; \
      else \
        echo "taplo not found and docker is unavailable" >&2; \
        exit 127; \
      fi ;; \
    markdown) \
      uv run mdformat --check README.md .vaultspec/ .vault/ && \
      uv run pymarkdown --config .pymarkdown.json \
        scan -r README.md .vaultspec/ .vault/ ;; \
    workflow) \
      if command -v actionlint >/dev/null 2>&1; then \
        actionlint; \
      elif command -v docker >/dev/null 2>&1; then \
        docker run --rm -v "$PWD:/repo" -w /repo \
          rhysd/actionlint:latest; \
      else \
        echo "actionlint not found and docker is unavailable" >&2; \
        exit 127; \
      fi ;; \
    all) \
      just _dev-lint python && \
      just _dev-lint type && \
      just _dev-lint links && \
      just _dev-lint toml && \
      just _dev-lint markdown && \
      just _dev-lint workflow ;; \
    --help|-h|help) \
      echo "Usage: just dev lint <target>" ; \
      echo "" ; \
      echo "Targets:" ; \
      echo "  python    Run Ruff on Python source" ; \
      echo "  type      Run Ty (type checker) on Python source" ; \
      echo "  links     Run Lychee link checker" ; \
      echo "  toml      Run Taplo TOML linter" ; \
      echo "  markdown  Run Markdown linting and formatting checks" ; \
      echo "  workflow  Run Actionlint on GitHub workflows" ; \
      echo "  all       Run all linters" ;; \
    *) \
      echo "unknown dev lint target: {{target}}" >&2; \
      echo "  targets: python type links toml markdown workflow all" >&2; \
      exit 1 ;; \
  esac

_dev-fix target='--help':
  case "{{target}}" in \
    python) \
      uv run ruff format src tests && \
      uv run ruff check --fix src tests ;; \
    toml) \
      if command -v taplo >/dev/null 2>&1; then \
        taplo fmt *.toml; \
      elif command -v docker >/dev/null 2>&1; then \
        docker run --rm -v "$PWD:/repo" -w /repo \
          tamasfe/taplo:0.9 fmt *.toml; \
      else \
        echo "taplo not found and docker is unavailable" >&2; \
        exit 127; \
      fi ;; \
    markdown) \
      uv run mdformat README.md .vaultspec/ .vault/ && \
      uv run pymarkdown --config .pymarkdown.json \
        fix -r README.md .vaultspec/ .vault/ ;; \
    vault) \
      uv run vaultspec-core vault check all --fix ;; \
    all) \
      just _dev-fix python && \
      just _dev-fix toml && \
      just _dev-fix markdown && \
      just _dev-fix vault ;; \
    --help|-h|help) \
      echo "Usage: just dev fix <target>" ; \
      echo "" ; \
      echo "Targets:" ; \
      echo "  python    Auto-fix and format Python source" ; \
      echo "  toml      Auto-format TOML files" ; \
      echo "  markdown  Auto-format Markdown files" ; \
      echo "  vault     Auto-fix vault issues" ; \
      echo "  all       Run all fixers" ;; \
    *) \
      echo "unknown dev fix target: {{target}}" >&2; \
      echo "  targets: python toml markdown vault all" >&2; \
      exit 1 ;; \
  esac

_dev-audit target='--help':
  case "{{target}}" in \
    deps) \
      tmp="${TMPDIR:-${TEMP:-/tmp}}/vaultspec-pip-audit-$$.txt"; \
      trap 'rm -f "$tmp"' EXIT; \
      uv export --frozen --group dev \
        --no-emit-project --output-file "$tmp"; \
      uv run pip-audit --strict -r "$tmp" ;; \
    --help|-h|help) \
      echo "Usage: just dev audit <target>" ; \
      echo "" ; \
      echo "Targets:" ; \
      echo "  deps      Run pip-audit on dependencies" ;; \
    *) \
      echo "unknown dev audit target: {{target}}" >&2; \
      echo "  targets: deps" >&2; \
      exit 1 ;; \
  esac

_dev-test target='--help':
  case "{{target}}" in \
    python) \
      uv run pytest src/vaultspec_core \
        -x -q --tb=short -m unit ;; \
    docker) \
      just _dev-build docker && \
      docker run --rm {{ local_image }} \
        vaultspec-core --help ;; \
    all) \
      just _dev-test python && \
      just _dev-test docker ;; \
    --help|-h|help) \
      echo "Usage: just dev test <target>" ; \
      echo "" ; \
      echo "Targets:" ; \
      echo "  python    Run pytest on Python source" ; \
      echo "  docker    Run smoke test in Docker" ; \
      echo "  all       Run all tests" ;; \
    *) \
      echo "unknown dev test target: {{target}}" >&2; \
      echo "  targets: python docker all" >&2; \
      exit 1 ;; \
  esac

_dev-build target='--help':
  case "{{target}}" in \
    python) \
      uv build ;; \
    docker) \
      docker buildx build --load \
        -t {{ local_image }} . ;; \
    all) \
      just _dev-build python && \
      just _dev-build docker ;; \
    --help|-h|help) \
      echo "Usage: just dev build <target>" ; \
      echo "" ; \
      echo "Targets:" ; \
      echo "  python    Build Python package" ; \
      echo "  docker    Build Docker image locally" ; \
      echo "  all       Run all builds" ;; \
    *) \
      echo "unknown dev build target: {{target}}" >&2; \
      echo "  targets: python docker all" >&2; \
      exit 1 ;; \
  esac

_dev-publish target='--help' tag='':
  case "{{target}}" in \
    docker-ghcr) \
      if [ -z "{{tag}}" ]; then echo "error: missing argument 'tag' for docker-ghcr" >&2; exit 1; fi; \
      docker buildx build --platform linux/amd64 \
        --push -t {{ image }}:{{tag}} . ;; \
    --help|-h|help) \
      echo "Usage: just dev publish <target> <tag>" ; \
      echo "" ; \
      echo "Targets:" ; \
      echo "  docker-ghcr   Publish docker image to GHCR" ;; \
    *) \
      echo "unknown dev publish target: {{target}}" >&2; \
      echo "  targets: docker-ghcr" >&2; \
      exit 1 ;; \
  esac

_dev-precommit target='--help':
  case "{{target}}" in \
    install) \
      uv run prek install ;; \
    upgrade) \
      uv run prek auto-update ;; \
    run) \
      uv run prek run --all-files ;; \
    --help|-h|help) \
      echo "Usage: just dev precommit <target>" ; \
      echo "" ; \
      echo "Targets:" ; \
      echo "  install   Install pre-commit hooks" ; \
      echo "  upgrade   Upgrade pre-commit hooks" ; \
      echo "  run       Run pre-commit hooks on all files" ;; \
    *) \
      echo "unknown dev precommit target: {{target}}" >&2; \
      echo "  targets: install upgrade run" >&2; \
      exit 1 ;; \
  esac
