set positional-arguments := false

image := "ghcr.io/wgergely/vaultspec-core"
local_image := "vaultspec-core:local"

default:
  @just --list

sync target='dependencies':
  case "{{target}}" in \
    dependencies) \
      uv sync --locked --group dev ;; \
    dependency-upgrades) \
      uv sync --upgrade --all-groups ;; \
    *) \
      echo "unknown sync target: {{target}}" >&2; \
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

fix target='lint':
  case "{{target}}" in \
    lint) \
      uv run ruff format src tests && \
      uv run ruff check --fix src tests && \
      npx --yes @taplo/cli fmt *.toml ;; \
    markdown) \
      npx --yes markdownlint-cli --config .markdownlint.json --fix .vaultspec/ .vault/ README.md ;; \
    vault) \
      uv run python -m vaultspec_core vault audit --verify --fix ;; \
    *) \
      echo "unknown fix target: {{target}}" >&2; \
      exit 1 ;; \
  esac

check target='all':
  case "{{target}}" in \
    lint) \
      uv run ruff check src tests ;; \
    type) \
      uv run python -m ty check src/vaultspec_core ;; \
    dependencies) \
      tmp="${TMPDIR:-${TEMP:-/tmp}}/vaultspec-pip-audit-$$.txt"; \
      trap 'rm -f "$tmp"' EXIT; \
      uv export --frozen --group dev --no-emit-project --output-file "$tmp"; \
      uv run pip-audit --strict -r "$tmp" ;; \
    links) \
      if command -v lychee >/dev/null 2>&1; then \
        lychee --config lychee.toml README.md .vault .vaultspec; \
      elif command -v docker >/dev/null 2>&1; then \
        docker run --rm -v "$PWD:/repo" -w /repo lycheeverse/lychee:latest --config /repo/lychee.toml README.md .vault .vaultspec; \
      else \
        echo "lychee not found and docker is unavailable" >&2; \
        exit 127; \
      fi ;; \
    toml) \
      npx --yes @taplo/cli lint *.toml ;; \
    markdown) \
      npx --yes markdownlint-cli --config .markdownlint.json .vaultspec/ .vault/ README.md ;; \
    workflow) \
      if command -v actionlint >/dev/null 2>&1; then \
        actionlint; \
      elif command -v docker >/dev/null 2>&1; then \
        docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest; \
      else \
        echo "actionlint not found and docker is unavailable" >&2; \
        exit 127; \
      fi ;; \
    vault) \
      uv run python -m vaultspec_core vault audit --verify ;; \
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

test target='all':
  case "{{target}}" in \
    python) \
      uv run pytest tests src --timeout=30 -m "not e2e and not integration and not benchmark and not gemini and not claude and not a2a and not team" -q ;; \
    docker) \
      just build docker && \
      docker run --rm {{ local_image }} vaultspec-core --help ;; \
    all) \
      just test python && \
      just test docker ;; \
    *) \
      echo "unknown test target: {{target}}" >&2; \
      exit 1 ;; \
  esac

build target:
  case "{{target}}" in \
    python) \
      uv build ;; \
    docker) \
      docker buildx build --load -t {{ local_image }} . ;; \
    all) \
      just build python && \
      just build docker ;; \
    *) \
      echo "unknown build target: {{target}}" >&2; \
      exit 1 ;; \
  esac

publish target tag:
  case "{{target}}" in \
    docker-ghcr) \
      docker buildx build --platform linux/amd64 --push -t {{ image }}:{{tag}} . ;; \
    *) \
      echo "unknown publish target: {{target}}" >&2; \
      exit 1 ;; \
  esac
