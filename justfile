set positional-arguments := false

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
  uv run vaultspec-core {{args}}

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

dev target *args='':
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
    *) \
      echo "unknown dev target: {{target}}" >&2; \
      echo "  targets: deps lint fix audit test build publish precommit" >&2; \
      exit 1 ;; \
  esac

# ===========================================================================
#  ci  - full pipeline: lint → audit → vault check → test
# ===========================================================================

ci:
  just dev lint all && \
  just dev audit deps && \
  just prod vault check all && \
  just dev test all

# ---------------------------------------------------------------------------
#  Internal recipes (prefixed with _ to hide from --list)
# ---------------------------------------------------------------------------

_dev-deps target='sync':
  case "{{target}}" in \
    sync) \
      uv sync --locked --group dev ;; \
    upgrade) \
      uv sync --upgrade --all-groups ;; \
    lock) \
      uv lock ;; \
    lock-upgrade) \
      uv lock --upgrade ;; \
    *) \
      echo "unknown dev deps target: {{target}}" >&2; \
      echo "  targets: sync upgrade lock lock-upgrade" >&2; \
      exit 1 ;; \
  esac

_dev-lint target='all':
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
      npx --yes @taplo/cli lint "$(pwd)"/*.toml ;; \
    markdown) \
      npx --yes markdownlint-cli \
        --config .markdownlint.json \
        .vaultspec/ .vault/ README.md ;; \
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
    *) \
      echo "unknown dev lint target: {{target}}" >&2; \
      echo "  targets: python type links toml markdown workflow all" >&2; \
      exit 1 ;; \
  esac

_dev-fix target='all':
  case "{{target}}" in \
    python) \
      uv run ruff format src tests && \
      uv run ruff check --fix src tests ;; \
    toml) \
      npx --yes @taplo/cli fmt "$(pwd)"/*.toml ;; \
    markdown) \
      npx --yes markdownlint-cli \
        --config .markdownlint.json --fix \
        .vaultspec/ .vault/ README.md ;; \
    vault) \
      uv run vaultspec-core vault check all --fix ;; \
    all) \
      just _dev-fix python && \
      just _dev-fix toml && \
      just _dev-fix markdown && \
      just _dev-fix vault ;; \
    *) \
      echo "unknown dev fix target: {{target}}" >&2; \
      echo "  targets: python toml markdown vault all" >&2; \
      exit 1 ;; \
  esac

_dev-audit target:
  case "{{target}}" in \
    deps) \
      tmp="${TMPDIR:-${TEMP:-/tmp}}/vaultspec-pip-audit-$$.txt"; \
      trap 'rm -f "$tmp"' EXIT; \
      uv export --frozen --group dev \
        --no-emit-project --output-file "$tmp"; \
      uv run pip-audit --strict -r "$tmp" ;; \
    *) \
      echo "unknown dev audit target: {{target}}" >&2; \
      echo "  targets: deps" >&2; \
      exit 1 ;; \
  esac

_dev-test target='all':
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
    *) \
      echo "unknown dev test target: {{target}}" >&2; \
      echo "  targets: python docker all" >&2; \
      exit 1 ;; \
  esac

_dev-build target:
  case "{{target}}" in \
    python) \
      uv build ;; \
    docker) \
      docker buildx build --load \
        -t {{ local_image }} . ;; \
    all) \
      just _dev-build python && \
      just _dev-build docker ;; \
    *) \
      echo "unknown dev build target: {{target}}" >&2; \
      echo "  targets: python docker all" >&2; \
      exit 1 ;; \
  esac

_dev-publish target tag:
  case "{{target}}" in \
    docker-ghcr) \
      docker buildx build --platform linux/amd64 \
        --push -t {{ image }}:{{tag}} . ;; \
    *) \
      echo "unknown dev publish target: {{target}}" >&2; \
      echo "  targets: docker-ghcr" >&2; \
      exit 1 ;; \
  esac

_dev-precommit target='run':
  case "{{target}}" in \
    install) \
      uv run prek install ;; \
    upgrade) \
      uv run prek auto-update ;; \
    run) \
      uv run prek run --all-files ;; \
    *) \
      echo "unknown dev precommit target: {{target}}" >&2; \
      echo "  targets: install upgrade run" >&2; \
      exit 1 ;; \
  esac
