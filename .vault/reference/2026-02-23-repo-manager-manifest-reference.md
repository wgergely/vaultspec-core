---
tags:
  - '#reference'
  - '#repo-manager-extension'
date: '2026-02-23'
---

# repo-manager manifest and configuration format reference

## crate(s)

- `crates/repo-core` — repository config manifest and resolver
- `crates/repo-extensions` — extension manifest, config, MCP integration, registry
- `crates/repo-presets` — preset providers (Python venv via `uv` and `venv`)
- `crates/repo-meta` — tool definition schema, preset definition schema
- `crates/repo-fs` — workspace layout detection

## file(s)

- `/y/code/repository-manager-worktrees/main/crates/repo-core/src/config/manifest.rs`
- `/y/code/repository-manager-worktrees/main/crates/repo-core/src/config/resolver.rs`
- `/y/code/repository-manager-worktrees/main/crates/repo-core/src/config/runtime.rs`
- `/y/code/repository-manager-worktrees/main/crates/repo-core/src/hooks.rs`
- `/y/code/repository-manager-worktrees/main/crates/repo-extensions/src/manifest.rs`
- `/y/code/repository-manager-worktrees/main/crates/repo-extensions/src/config.rs`
- `/y/code/repository-manager-worktrees/main/crates/repo-extensions/src/registry.rs`
- `/y/code/repository-manager-worktrees/main/crates/repo-extensions/src/mcp.rs`
- `/y/code/repository-manager-worktrees/main/crates/repo-presets/src/context.rs`
- `/y/code/repository-manager-worktrees/main/crates/repo-presets/src/provider.rs`
- `/y/code/repository-manager-worktrees/main/crates/repo-presets/src/python/uv.rs`
- `/y/code/repository-manager-worktrees/main/crates/repo-presets/src/python/venv.rs`
- `/y/code/repository-manager-worktrees/main/crates/repo-meta/src/schema/preset.rs`
- `/y/code/repository-manager-worktrees/main/crates/repo-meta/src/schema/tool.rs`
- `/y/code/repository-manager-worktrees/main/test-fixtures/repos/config-test/.repository/config.toml`

______________________________________________________________________

## 1. repository config format (`config.toml`)

### location and hierarchy

The repo-manager loads and merges four config layers in order (later wins):

1. `~/.config/repo-manager/config.toml` — global defaults
1. `~/.config/repo-manager/org/config.toml` — org-shared defaults
1. `.repository/config.toml` — per-repository config
1. `.repository/config.local.toml` — local overrides (git-ignored)

The struct for a single layer is `Manifest` (`repo-core/src/config/manifest.rs`).
After merging all layers the result is a `ResolvedConfig` (`resolver.rs`).

### `Manifest` struct — top-level fields

```rust
pub struct Manifest {
    pub core:       CoreSection,             // mode = "standard" | "worktrees"
    pub presets:    HashMap<String, Value>,  // key = "type:name"
    pub tools:      Vec<String>,             // tool slugs
    pub rules:      Vec<String>,             // rule ids
    pub extensions: HashMap<String, Value>,  // key = extension name
    pub hooks:      Vec<HookConfig>,         // lifecycle hooks
}
```

### `[core]` section

```toml
[core]
mode = "standard"   # or "worktrees" (default)
```

`mode` is the only field on `CoreSection`. It selects which workspace layout
backend is used.

### `[presets."type:name"]` section

Presets use a namespaced key: `env:python`, `env:node`, `tool:linter`,
`config:editor`, etc. The value is an arbitrary JSON/TOML object — there is no
fixed schema enforced at parse time. The object is passed verbatim to the
matching `PresetProvider`.

```toml
[presets."env:python"]
version = "3.12"
provider = "uv"       # "uv" (default) or "venv"
```

The `RuntimeContext` transformer (`runtime.rs`) routes preset keys:

- `env:*` → `RuntimeContext.runtime` (keyed by name after the colon)
- `tool:*` / `config:*` → `RuntimeContext.capabilities`

### `tools` array

```toml
tools = ["cursor", "claude", "vscode"]
```

Matches tool slugs defined in `.repository/tools/*.toml` (or built-in tool
definitions in `repo-meta`). Merging across layers accumulates unique values.

### `rules` array

```toml
rules = ["no-unsafe", "no-unwrap"]
```

Rule identifiers. Merging is additive (unique values).

### `[extensions."name"]` section

```toml
[extensions."vaultspec"]
source = "https://github.com/vaultspec/vaultspec.git"
ref = "v0.1.0"
```

These are freeform TOML objects stored as `HashMap<String, Value>`. They are
passed to `ExtensionConfig` when the extension system resolves them. Deep
merge is applied across config layers.

The typed `ExtensionConfig` struct (`repo-extensions/src/config.rs`) provides:

```rust
pub struct ExtensionConfig {
    pub source:  String,           // git URL or local path
    pub ref_pin: Option<String>,   // branch/tag/commit
    pub config:  HashMap<String, toml::Value>,  // arbitrary extension fields (flattened)
}
```

`ref_pin` is the TOML key `ref_pin`. Note: the manifest example in
`manifest.rs` tests uses `ref` (bare word), but `ExtensionConfig` uses
`ref_pin` to avoid the Rust keyword. There is a mismatch to watch here —
the tests in `manifest.rs` read `ext["ref"]` from the raw `Value` map because
the `Manifest.extensions` field stores raw `Value`, not `ExtensionConfig`.

### `[[hooks]]` array

```toml
[[hooks]]
event   = "post-branch-create"
command = "npm"
args    = ["install"]

[[hooks]]
event       = "pre-sync"
command     = "sh"
args        = ["-c", "echo syncing"]
working_dir = "/optional/override"
```

`HookEvent` enum (`hooks.rs`) has exactly 6 variants:
`pre-branch-create`, `post-branch-create`, `pre-branch-delete`,
`post-branch-delete`, `pre-sync`, `post-sync`.

Hook args support `${VAR_NAME}` substitution. Available vars differ by event:

- branch events: `BRANCH_NAME`, `WORKTREE_PATH`
- sync events: `HOOK_EVENT_TYPE`

Hooks are fail-fast: a non-zero exit stops the chain.

______________________________________________________________________

## 2. extension manifest format (`repo_extension.toml`)

The canonical file that an extension ships is named `repo_extension.toml`
(constant `MANIFEST_FILENAME`). It is parsed by `ExtensionManifest`
(`repo-extensions/src/manifest.rs`).

### complete schema

```toml
[extension]
name        = "vaultspec"          # required; alphanumeric, hyphens, underscores only
version     = "0.1.0"             # required; must be valid semver
description = "..."               # optional

[requires.python]
version = ">=3.13"                # PEP 440 / semver constraint string

[runtime]
type    = "python"                # runtime type: "python", "node", ...
install = "pip install -e '.[dev]'"  # arbitrary shell command

[entry_points]
cli = ".vaultspec/lib/scripts/cli.py"
mcp = ".vaultspec/lib/scripts/subagent.py serve"

[provides]
mcp          = ["vs-subagent-mcp"]
mcp_config   = "mcp.json"
content_types = ["rules", "agents", "skills", "system", "templates"]

[outputs]
claude_dir = ".claude"
gemini_dir = ".gemini"
agent_dir  = ".agent"
agents_md  = "AGENTS.md"
```

### struct breakdown

```rust
pub struct ExtensionManifest {
    pub extension:    ExtensionMeta,
    pub requires:     Option<Requirements>,
    pub runtime:      Option<RuntimeConfig>,
    pub entry_points: Option<EntryPoints>,
    pub provides:     Option<Provides>,
    pub outputs:      Option<Outputs>,
}

pub struct Requirements {
    pub python: Option<PythonRequirement>,
}
pub struct PythonRequirement {
    pub version: String,   // e.g. ">=3.13" — stored as opaque string, not parsed
}

pub struct RuntimeConfig {
    pub runtime_type: String,         // TOML key "type"
    pub install: Option<String>,      // arbitrary shell command string
}

pub struct EntryPoints {
    pub cli: Option<String>,          // relative path (+ optional args)
    pub mcp: Option<String>,          // relative path (+ optional args)
}

pub struct Provides {
    pub mcp:          Vec<String>,    // MCP server names
    pub mcp_config:   Option<String>, // relative path to mcp.json
    pub content_types: Vec<String>,
}

pub struct Outputs {
    pub claude_dir: Option<String>,
    pub gemini_dir: Option<String>,
    pub agent_dir:  Option<String>,
    pub agents_md:  Option<String>,
}
```

### entry point resolution

`EntryPoints::resolve(python_path, source_dir)` produces `ResolvedEntryPoints`.
Entry point strings are split on whitespace: `"subagent.py serve"` becomes
`program=python_path`, `args=[source_dir/subagent.py, serve]`.
Absolute paths in entry points are forced to resolve relative to `source_dir`
(security boundary; a warning is emitted).

### `ExtensionMeta` is `deny_unknown_fields`

The `[extension]` table will reject unknown keys (e.g., adding `author` will
cause a parse error). All other top-level sections (`[runtime]`, `[provides]`,
etc.) are open: unknown TOML sections are silently ignored at deserialization.

______________________________________________________________________

## 3. presets system (`repo-presets`)

Presets are declared in `.repository/presets/*.toml` using `PresetDefinition`
(`repo-meta/src/schema/preset.rs`):

```toml
[meta]
id          = "python-agentic"
description = "Python with AI tools"

[requires]
tools   = ["cursor", "claude"]
presets = ["env:python"]

[rules]
include = ["no-api-keys"]

[config]
python_version = "3.11"
```

The `[config]` table is fully freeform (`HashMap<String, toml::Value>`).

### `PresetProvider` trait

All preset providers implement:

```rust
pub trait PresetProvider: Send + Sync {
    fn id(&self) -> &str;                                        // e.g. "env:python"
    async fn check(&self, context: &Context) -> Result<PresetCheckReport>;
    async fn apply(&self, context: &Context) -> Result<ApplyReport>;
}
```

### Python providers

Two concrete providers ship for Python:

| Provider       | `id()`              | mechanism                    |
| -------------- | ------------------- | ---------------------------- |
| `UvProvider`   | `"env:python"`      | `uv venv --python <version>` |
| `VenvProvider` | `"env:python-venv"` | `python -m venv`             |

`UvProvider.apply()` runs: `uv venv --python <python_version> <venv_path>`
from the repository root.

`VenvProvider` also exposes `create_tagged_sync(root, tag)` and
`create_tagged(root, tag)` for worktree-tagged venv creation
(naming pattern: `.venv-{worktree}-{platform}-py{version}`).

### `Context` struct

```rust
pub struct Context {
    pub layout:   WorkspaceLayout,
    pub root:     NormalizedPath,
    pub config:   HashMap<String, toml::Value>,  // from preset config table
    pub venv_tag: Option<String>,
}
```

Key derived values from `config`:

- `context.python_version()` → `config["version"]` or `"3.12"` (default)
- `context.provider()` → `config["provider"]` or `"uv"` (default)
- `context.venv_path()` → `.venv` (no tag) or `.venv-{tag}` (with tag)

______________________________________________________________________

## 4. tool definitions (`repo-meta/src/schema/tool.rs`)

Tool files live at `.repository/tools/*.toml`:

```toml
[meta]
name        = "VSCode"
slug        = "vscode"
description = "..."

[integration]
config_path      = ".vscode/settings.json"
type             = "json"          # text | json | toml | yaml | markdown
additional_paths = [".vscode/"]

[capabilities]
supports_custom_instructions = true
supports_mcp                 = true
supports_rules_directory     = false

[schema]
instruction_key  = "..."
mcp_key          = "mcpServers"
python_path_key  = "python.defaultInterpreterPath"  # used by VSCode tool syncer
```

`ToolSchemaKeys.python_path_key` is currently the only field that hints at
Python awareness in the tool integration layer. It carries a JSON keypath for
writing the Python interpreter path into the tool's settings file.

______________________________________________________________________

## 5. MCP template variables in `mcp.json`

When an extension ships an `mcp.json` (declared via `provides.mcp_config`),
the `resolve_mcp_config()` function (`repo-extensions/src/mcp.rs`) performs
template substitution before injecting MCP server entries into tools.

Supported placeholders:

| Placeholder            | Resolved value                                       |
| ---------------------- | ---------------------------------------------------- |
| `{{root}}`             | Absolute path to repository root                     |
| `{{extension.source}}` | Absolute path to extension source directory          |
| `{{runtime.python}}`   | Absolute path to extension's Python venv interpreter |

`ResolveContext`:

```rust
pub struct ResolveContext {
    pub root:             String,
    pub extension_source: String,
    pub python_path:      Option<String>,   // None = extension has no Python runtime
}
```

Security: `mcp_config` path must be relative to `source_dir`; canonicalize
containment check is enforced. Absolute paths and `../` traversal are rejected.

______________________________________________________________________

## 6. extension lifecycle status

As of `crates/repo-cli/src/commands/extension.rs`, all mutating extension
operations (`install`, `add`, `init`, `remove`) return `CliError::user("... not yet implemented")`. Only `extension list` works (reads the built-in `ExtensionRegistry`).

The `ExtensionRegistry` hardcodes two known extensions:

- `vaultspec` → `https://github.com/vaultspec/vaultspec.git`
- `registry-manager` → `https://github.com/registry-manager/registry-manager.git`

The actual install/fetch/activate pipeline does not exist yet.

______________________________________________________________________

## 7. gap analysis — python package dependency support

The table below lists what would need to be **added** to the manifest schema to
express Python package installation requirements.

### gap 1 — python package dependencies in `repo_extension.toml`

**Current state:** `[requires.python]` has only a `version: String` field
(e.g., `">=3.13"`). There is no field for declaring Python packages to install,
no reference to `pyproject.toml`, `requirements.txt`, or git-based deps.

**Missing fields needed on `Requirements` or a new `[packages]` section:**

```toml

# proposed additions to repo_extension.toml

[requires.python]
version           = ">=3.13"
packages          = ["vaultspec @ git+https://github.com/vaultspec/vaultspec"]
pyproject         = "pyproject.toml"     # path to pyproject.toml in extension root
requirements_file = "requirements.txt"   # alternative: path to requirements.txt
```

Rust struct additions:

```rust
pub struct PythonRequirement {
    pub version:           String,
    // NEW:
    pub packages:          Vec<String>,       // PEP 508 specifiers
    pub pyproject:         Option<String>,    // relative path
    pub requirements_file: Option<String>,    // relative path
}
```

### gap 2 — package manager preference in `[runtime]`

**Current state:** `RuntimeConfig` has `runtime_type: String` and
`install: Option<String>` (free-form shell command). There is no structured
field for the package manager choice.

**Missing:** A `package_manager` field to allow structured orchestration rather
than relying solely on a raw shell command string.

```toml
[runtime]
type            = "python"
package_manager = "uv"    # or "pip", "poetry", "pdm"
install         = "uv sync --frozen"
```

Rust struct:

```rust
pub struct RuntimeConfig {
    pub runtime_type:    String,
    pub install:         Option<String>,
    // NEW:
    pub package_manager: Option<String>,   // "uv" | "pip" | "poetry" | "pdm"
}
```

### gap 3 — venv path declaration in `[runtime]` or `[requires.python]`

**Current state:** Venv path is computed by `Context.venv_path()` using a
hardcoded convention (`.venv` or `.venv-{tag}`). The extension manifest has no
way to declare a custom venv path.

**Missing:**

```toml
[runtime]
type     = "python"
venv     = ".venv"    # explicit venv directory name (default ".venv")
```

Rust:

```rust
pub struct RuntimeConfig {
    pub runtime_type: String,
    pub install:      Option<String>,
    // NEW:
    pub venv:         Option<String>,  // venv directory relative to extension source
}
```

This would be read by `Context.venv_path()` or a new `ExtensionContext` type
when the extension activation pipeline runs.

### gap 4 — post-install hook for `uv sync`

**Current state:** `Manifest.hooks` (`[[hooks]]`) supports 6 lifecycle events
(`pre/post-branch-create`, `pre/post-branch-delete`, `pre/post-sync`). There
is no `post-extension-install` or `post-extension-activate` event.

**Missing:** A new `HookEvent` variant would be needed for extension install/activate
triggers, or the `RuntimeConfig.install` field could be promoted to a structured
hook type rather than a bare shell string.

Proposed new hook events:

```rust
pub enum HookEvent {
    // existing ...
    PostExtensionInstall,   // NEW: after extension git clone/fetch
    PostExtensionActivate,  // NEW: after extension files are written to output dirs
}
```

Alternatively, the structured approach keeps it inside the manifest:

```toml
[runtime]
type    = "python"
install = "uv sync --frozen"   # executed post-install (already supported as a string)
```

The `install` field already exists in `RuntimeConfig` as a free-form string.
What is missing is the execution machinery — nothing currently invokes
`RuntimeConfig.install` anywhere in the codebase. It is declared but dead.

### gap 5 — python version pinning via `.python-version` file

**Current state:** `PythonRequirement.version` is an opaque string. The
`UvProvider` passes it directly to `uv venv --python <version>`. There is no
support for reading a `.python-version` file or `pyproject.toml`'s
`[tool.python]` table.

**Missing:** Either an `auto` sentinel value (delegate to uv's own discovery),
or a `version_file` field:

```toml
[requires.python]
version      = ">=3.13"
version_file = ".python-version"   # if set, override version from this file
```

______________________________________________________________________

## 8. summary of existing python-aware fields

| Location                                | Field                | Purpose                                              |
| --------------------------------------- | -------------------- | ---------------------------------------------------- |
| `repo_extension.toml [requires.python]` | `version`            | Python version constraint (string)                   |
| `repo_extension.toml [runtime]`         | `type = "python"`    | Declares runtime type                                |
| `repo_extension.toml [runtime]`         | `install`            | Shell command (not yet executed)                     |
| `repo_extension.toml [entry_points]`    | `cli`, `mcp`         | Scripts invoked via python interpreter               |
| `mcp.json` template                     | `{{runtime.python}}` | Resolved venv interpreter path                       |
| `config.toml [presets."env:python"]`    | `version`            | Python version for venv creation                     |
| `config.toml [presets."env:python"]`    | `provider`           | `"uv"` or `"venv"`                                   |
| `tool definition [schema]`              | `python_path_key`    | JSON key for writing interpreter path to tool config |

______________________________________________________________________

## 9. architectural notes

- The `extensions` field in `Manifest` stores raw `Value` (not `ExtensionConfig`).
  Typed parsing happens only when the extension activation pipeline reads it.
  This means arbitrary fields can be added to `[extensions."name"]` tables
  without changing the core manifest schema.

- `RuntimeConfig.install` is a valid declaration point for `uv sync` or
  `uv pip install` commands, but the execution layer that would invoke it does
  not exist yet (all extension lifecycle operations return "not implemented").

- The preset system (`env:python`) and the extension system are architecturally
  separate. Presets configure the developer's local environment; extensions
  ship content (rules, agents, MCP servers). An extension that needs Python
  dependencies today has no automated way to ensure `uv sync` runs — the
  `install` field is the intended hook but it is currently inert.
