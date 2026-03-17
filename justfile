set positional-arguments := false

image := "ghcr.io/wgergely/vaultspec-core"
local_image := "vaultspec-core:local"

default:
  @just --list

# ---------------------------------------------------------------------------
# Dependencies & lockfile
# ---------------------------------------------------------------------------

deps target='sync':
  case "{{target}}" in \
    sync) \
      uv sync --locked --group dev ;; \
    upgrade) \
      uv sync --upgrade --all-groups ;; \
    *) \
      echo "unknown deps target: {{target}}" >&2; \
      exit 1 ;; \
  esac

lock target='dependencies':
  case "{{target}}" in \
    dependencies) \
      uv lock ;; \
    dependency-upgrades) \
      uv lock --upgrade ;; \
    *) \
      echo "unknown lock target: {{target}}" >&2; \
      exit 1 ;; \
  esac

# ---------------------------------------------------------------------------
# Top-level CLI pass-through  (vaultspec-core <group> ...)
# ---------------------------------------------------------------------------

sync provider='all' *args='':
  uv run vaultspec-core sync {{provider}} {{args}}

vault *args='':
  uv run vaultspec-core vault {{args}}

spec *args='':
  uv run vaultspec-core spec {{args}}

install path='.' provider='all' *args='':
  uv run vaultspec-core install "{{path}}" {{provider}} {{args}}

uninstall path='.' provider='all' *args='':
  uv run vaultspec-core uninstall "{{path}}" {{provider}} {{args}}

# ---------------------------------------------------------------------------
# Fix  (auto-correct lint, markdown, vault docs)
# ---------------------------------------------------------------------------

fix target='lint':
  case "{{target}}" in \
    lint) \
      uv run ruff format src tests && \
      uv run ruff check --fix src tests && \
      npx --yes @taplo/cli fmt *.toml ;; \
    markdown) \
      npx --yes markdownlint-cli \
        --config .markdownlint.json --fix \
        .vaultspec/ .vault/ README.md ;; \
    vault) \
      uv run vaultspec-core vault check all --fix ;; \
    all) \
      just fix lint && \
      just fix markdown && \
      just fix vault ;; \
    *) \
      echo "unknown fix target: {{target}}" >&2; \
      exit 1 ;; \
  esac

# ---------------------------------------------------------------------------
# Check  (read-only validation — lint, types, deps, vault, etc.)
# ---------------------------------------------------------------------------

check target='all':
  case "{{target}}" in \
    lint) \
      uv run ruff check src tests ;; \
    type) \
      uv run python -m ty check src/vaultspec_core ;; \
    dependencies) \
      tmp="${TMPDIR:-${TEMP:-/tmp}}/vaultspec-pip-audit-$$.txt"; \
      trap 'rm -f "$tmp"' EXIT; \
      uv export --frozen --group dev \
        --no-emit-project --output-file "$tmp"; \
      uv run pip-audit --strict -r "$tmp" ;; \
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
      npx --yes @taplo/cli lint *.toml ;; \
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
    vault) \
      uv run vaultspec-core vault check all ;; \
    all) \
      just check lint && \
      just check type && \
      just check dependencies && \
      just check links && \
      just check toml && \
      just check markdown && \
      just check workflow && \
      just check vault && \
      just test all ;; \
    *) \
      echo "unknown check target: {{target}}" >&2; \
      exit 1 ;; \
  esac

# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

test target='all':
  case "{{target}}" in \
    python) \
      uv run pytest src/vaultspec_core \
        -x -q --tb=short -m unit ;; \
    docker) \
      just build docker && \
      docker run --rm {{ local_image }} \
        vaultspec-core --help ;; \
    all) \
      just test python && \
      just test docker ;; \
    *) \
      echo "unknown test target: {{target}}" >&2; \
      exit 1 ;; \
  esac

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

build target:
  case "{{target}}" in \
    python) \
      uv build ;; \
    docker) \
      docker buildx build --load \
        -t {{ local_image }} . ;; \
    all) \
      just build python && \
      just build docker ;; \
    *) \
      echo "unknown build target: {{target}}" >&2; \
      exit 1 ;; \
  esac

# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------

publish target tag:
  case "{{target}}" in \
    docker-ghcr) \
      docker buildx build --platform linux/amd64 \
        --push -t {{ image }}:{{tag}} . ;; \
    *) \
      echo "unknown publish target: {{target}}" >&2; \
      exit 1 ;; \
  esac

# ---------------------------------------------------------------------------
# Vault shortcuts  (vault doctor, vault check <name>, vault graph)
# ---------------------------------------------------------------------------

doctor *args='':
  uv run vaultspec-core vault doctor {{args}}

graph *args='':
  uv run vaultspec-core vault graph {{args}}
