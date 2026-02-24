---
tags:
  - "#reference"
  - "#repo-manager-extensions"
date: 2026-02-23
related: []
---

# repo-manager extensions system reference

```
Crate(s): repo-extensions, repo-core, repo-meta, repo-cli
File(s):
  crates/repo-extensions/src/lib.rs
  crates/repo-extensions/src/manifest.rs
  crates/repo-extensions/src/registry.rs
  crates/repo-extensions/src/config.rs
  crates/repo-extensions/src/mcp.rs
  crates/repo-extensions/src/error.rs
  crates/repo-core/src/config/manifest.rs
  crates/repo-core/src/config/resolver.rs
  crates/repo-core/src/config/runtime.rs
  crates/repo-core/src/sync/engine.rs
  crates/repo-core/src/sync/tool_syncer.rs
  crates/repo-core/src/hooks.rs
  crates/repo-meta/src/registry.rs
  crates/repo-meta/src/schema/mcp.rs
  crates/repo-meta/src/schema/tool.rs
  crates/repo-cli/src/commands/extension.rs
  crates/repo-cli/src/commands/tool.rs
  test-fixtures/repos/config-test/.repository/config.toml
Related: []
```

---

## overview

The repository-manager extension system is **partially designed and partially implemented**. The data-model layer (manifest parsing, registry, MCP config resolution) is fully implemented and tested. The lifecycle layer (install, add, remove, activate) is explicitly stubbed out — every CLI handler returns `"not yet implemented"`. Understanding both what exists and what is missing is the purpose of this audit.

---

## 1. extension lifecycle

### 1.1 discovery

Extensions are not auto-discovered from the filesystem. The only discovery mechanism is the built-in `ExtensionRegistry` (`crates/repo-extensions/src/registry.rs:21-81`), which is a static in-memory catalog of known extension names and their source URLs:

```rust
// registry.rs:34-48
pub fn with_known() -> Self {
    let mut registry = Self::new();
    registry.register(ExtensionEntry {
        name: "vaultspec".to_string(),
        source: "https://github.com/vaultspec/vaultspec.git".to_string(),
        ...
    });
    registry.register(ExtensionEntry {
        name: "registry-manager".to_string(),
        source: "https://github.com/registry-manager/registry-manager.git".to_string(),
        ...
    });
    registry
}
```

There is no filesystem scan for installed extensions. Extensions configured in `config.toml` are referenced by name under `[extensions."<name>"]`. During sync, the engine iterates `manifest.extensions.keys()` and looks for the extension source at `.repository/extensions/<name>/` (`engine.rs:538-539`).

### 1.2 registration in config.toml

Extensions are declared in the repository's `config.toml` under the `[extensions]` table:

```toml
[extensions."vaultspec"]
source = "https://github.com/vaultspec/vaultspec.git"
ref_pin = "v0.1.0"
```

The `Manifest` struct in `repo-core` stores extensions as `HashMap<String, Value>` (`manifest.rs:72`), meaning the per-extension config is freeform JSON/TOML. The `ExtensionConfig` struct in `repo-extensions` (`config.rs:11-20`) provides the typed view:

```rust
pub struct ExtensionConfig {
    pub source: String,
    #[serde(default)]
    pub ref_pin: Option<String>,
    #[serde(default, flatten)]
    pub config: HashMap<String, toml::Value>,
}
```

The `ref_pin` field accepts a branch name, tag, or commit hash. Arbitrary extra keys pass through via `flatten`.

### 1.3 installation (NOT IMPLEMENTED)

`handle_extension_install` in `crates/repo-cli/src/commands/extension.rs:14-18` returns an immediate error:

```rust
pub fn handle_extension_install(source: &str, _no_activate: bool) -> Result<()> {
    Err(CliError::user(format!(
        "Extension install is not yet implemented. Source: {source}"
    )))
}
```

Similarly, `handle_extension_add`, `handle_extension_init`, and `handle_extension_remove` are all stubs (`extension.rs:21-39`). No git clone, no file system operations, no subprocess invocation is performed.

### 1.4 activation (NOT IMPLEMENTED)

There is no activation mechanism. The sync engine reads extensions from `manifest.extensions` and attempts to resolve their MCP config from `.repository/extensions/<name>/` — but if the directory does not exist, it logs a debug message and silently skips (`engine.rs:559-567`):

```rust
Err(_) => {
    // Extension source not installed yet - skip silently
    tracing::debug!(
        "Extension '{}' source not found at {:?}, skipping MCP resolution",
        ext_name, ext_source_dir.as_ref()
    );
    continue;
}
```

So the system is designed to tolerate uninstalled extensions gracefully, but does not take any action to install them.

### 1.5 the only working operation: list

`handle_extension_list` (`extension.rs:45-85`) is the sole functional CLI handler. It queries `ExtensionRegistry::with_known()` and prints the static catalog. The `--json` flag outputs structured JSON. All entries are reported as `"installed": false` since no install tracking exists.

---

## 2. extension CLI commands

All commands are defined in `crates/repo-cli/src/commands/extension.rs`. The surface is:

| Command | Handler | Status |
|---|---|---|
| `repo extension list [--json]` | `handle_extension_list` | Functional (read-only, static catalog) |
| `repo extension install <source> [--no-activate]` | `handle_extension_install` | Stub — returns error |
| `repo extension add <name>` | `handle_extension_add` | Stub — returns error |
| `repo extension init <name>` | `handle_extension_init` | Stub — returns error |
| `repo extension remove <name>` | `handle_extension_remove` | Stub — returns error |

The distinction between `install` (by URL/path) and `add` (by known name) is present in the interface design but not yet implemented in either handler.

---

## 3. extension manifest format (`repo_extension.toml`)

The canonical filename is `"repo_extension.toml"` (`lib.rs:16`). Extensions place this file at the root of their source repository.

### full schema

```toml
[extension]
name = "vaultspec"           # required; alphanumeric + hyphens + underscores
version = "0.1.0"            # required; must be valid semver
description = "..."          # optional

[requires.python]
version = ">=3.13"           # python version constraint string

[runtime]
type = "python"              # runtime type string ("python", "node", etc.)
install = "pip install -e '.[dev]'"  # install command (freeform string)

[entry_points]
cli = ".vaultspec/lib/scripts/cli.py"           # relative path to CLI script
mcp = ".vaultspec/lib/scripts/subagent.py serve" # command + args, space-separated

[provides]
mcp = ["vs-subagent-mcp"]              # list of MCP server names provided
mcp_config = "mcp.json"               # optional: relative path to mcp.json
content_types = ["rules", "agents"]   # content types managed

[outputs]
claude_dir = ".claude"
gemini_dir = ".gemini"
agent_dir = ".agent"
agents_md = "AGENTS.md"
```

### struct hierarchy

```
ExtensionManifest           manifest.rs:47
  extension: ExtensionMeta  (name, version, description)
  requires: Requirements    (python: PythonRequirement)
  runtime: RuntimeConfig    (runtime_type, install)
  entry_points: EntryPoints (cli, mcp)
  provides: Provides        (mcp[], mcp_config, content_types[])
  outputs: Outputs          (claude_dir, gemini_dir, agent_dir, agents_md)
```

### validation rules

- `extension.name` must be non-empty and match `[a-zA-Z0-9-_]+` (`manifest.rs:248-263`).
- `extension.version` must be valid semver via the `semver` crate (`manifest.rs:266-269`).
- Unknown fields in `[extension]` are rejected (`deny_unknown_fields` on `ExtensionMeta`, `manifest.rs:69`).
- Unknown top-level sections are accepted (the outer struct does not have `deny_unknown_fields`).
- Entry point paths that are absolute are force-resolved relative to the source directory with a warning (`manifest.rs:167-174`).

---

## 4. dependency installation

**No dependency installation is performed by the system.** The `RuntimeConfig.install` field (`manifest.rs:103`) records an install command string, but there is no code path that reads this field and executes it. It is parsed and round-tripped in tests, but never invoked.

The `repo-meta` registry (`registry.rs:47-53`) associates preset IDs to provider names (`"env:python"` -> `"uv"`, `"env:node"` -> `"node"`, `"env:rust"` -> `"rust"`), but this is a metadata mapping only — no subprocess is spawned from this code.

The hooks system (`crates/repo-core/src/hooks.rs`) does support arbitrary subprocess execution via `Command::new` (`hooks.rs:210`), but hooks are general-purpose lifecycle callbacks (pre/post branch-create, pre/post branch-delete, pre/post sync) configured by the user — they are not extension-installation hooks.

---

## 5. virtual environment management

### what exists: venv path probing

The `SyncEngine::find_extension_python` method (`engine.rs:612-626`) probes for an existing venv interpreter:

```rust
fn find_extension_python(&self, ext_source_dir: &NormalizedPath) -> Option<String> {
    let candidates = [
        ext_source_dir.join(".venv/bin/python"),
        ext_source_dir.join("venv/bin/python"),
        ext_source_dir.join(".venv/Scripts/python.exe"),
    ];
    for candidate in &candidates {
        if candidate.exists() {
            return Some(candidate.as_ref().to_string_lossy().to_string());
        }
    }
    None
}
```

This path is used to populate `ResolveContext.python_path` (`engine.rs:574`) when resolving MCP template variables.

### what does NOT exist: venv creation

There is no `uv venv`, `python -m venv`, `pip install`, or any subprocess call that creates or populates a virtual environment. The system probes for a pre-existing venv but cannot create one. If no venv is found at the candidate paths, `python_path` is `None` and any `{{runtime.python}}` template variable in `mcp.json` is left unexpanded (`mcp.rs:201-204`).

### venv path convention

The system assumes the convention `.venv/bin/python` (Linux/macOS) or `.venv/Scripts/python.exe` (Windows) relative to the extension's source directory at `.repository/extensions/<name>/`.

---

## 6. config.toml format

### reference config

The test fixture at `test-fixtures/repos/config-test/.repository/config.toml`:

```toml
# Repository Manager Configuration
# This fixture tests config generation across tools

tools = ["cursor", "claude"]

[core]
mode = "standard"
```

### full schema

```toml
# Top-level arrays (must appear before any [section] headers)
tools = ["cursor", "vscode", "claude", "windsurf", "antigravity", "gemini"]
rules = ["no-unsafe", "no-unwrap"]

[core]
mode = "standard"   # or "worktrees" (default)

[presets."env:python"]
version = "3.12"
provider = "uv"
venv_name = ".venv"

[presets."env:node"]
version = "20"

[presets."tool:linter"]
enabled = true

[extensions."vaultspec"]
source = "https://github.com/vaultspec/vaultspec.git"
ref_pin = "v0.1.0"
# Any additional keys pass through (flatten)

[extensions."other-ext"]
source = "https://github.com/org/other-ext.git"

[[hooks]]
event = "post-branch-create"
command = "npm"
args = ["install"]

[[hooks]]
event = "pre-sync"
command = "sh"
args = ["-c", "echo sync starting"]
working_dir = ".scripts"   # optional; must be inside repo root
```

### config hierarchy (4 layers, later overrides earlier)

1. `~/.config/repo-manager/config.toml` — global defaults
2. `~/.config/repo-manager/org/config.toml` — organization defaults
3. `.repository/config.toml` — repository config
4. `.repository/config.local.toml` — local overrides (git-ignored)

Merge semantics (`manifest.rs:156-197`):
- `core.mode`: last value wins.
- `presets`: deep merge per-key (object fields merged recursively, scalars replaced).
- `tools`: union (unique values from all layers).
- `rules`: union (unique values from all layers).
- `extensions`: deep merge per-key (same as presets).
- `hooks`: concatenate (all layers appended).

### preset key taxonomy

Preset keys follow the pattern `"type:name"` (e.g., `"env:python"`, `"tool:linter"`, `"config:editor"`). The `RuntimeContext` (`config/runtime.rs:54-108`) separates them:
- `env:*` presets go into `RuntimeContext.runtime` keyed by the name after the colon.
- `tool:*` and `config:*` presets go into `RuntimeContext.capabilities` (sorted list of keys).

### supported tool slugs

Built-in tool integrations (`tool_syncer.rs` test coverage confirms): `cursor`, `vscode`, `claude`, `windsurf`, `antigravity`, `gemini`. `cursor` -> `.cursorrules`, `vscode` -> `.vscode/settings.json`, `claude` -> `CLAUDE.md`.

---

## 7. MCP config resolution (the only active extension integration)

This is the only part of the extension system that is wired into the main sync pipeline.

### data flow

```
SyncEngine::sync()
  -> resolve_extension_mcp_configs(&manifest)
     for each extension in manifest.extensions:
       1. Read .repository/extensions/<name>/repo_extension.toml
       2. Check provides.mcp_config field
       3. Read extension's mcp.json (relative to extension source dir)
       4. Resolve {{root}}, {{extension.source}}, {{runtime.python}} templates
       5. Collect per-extension resolved JSON objects
  -> merge_mcp_configs(configs)     # last-write-wins on key collision
  -> ToolSyncer::with_mcp_servers(merged)
     -> make_sync_context() injects servers into SyncContext
     -> tool integrations write MCP server entries to tool config files
```

### template variables in mcp.json

| Variable | Resolves to |
|---|---|
| `{{root}}` | Absolute path to repository root |
| `{{extension.source}}` | Absolute path to `.repository/extensions/<name>/` |
| `{{runtime.python}}` | Absolute path to `.venv/bin/python` (or `None` if not found) |

Example `mcp.json` (shipped by an extension):

```json
{
  "my-server": {
    "command": "{{runtime.python}}",
    "args": ["{{extension.source}}/scripts/serve.py", "--root", "{{root}}"]
  }
}
```

### security constraints

- `mcp_config` path must be relative (`mcp.rs:66-71`).
- After resolving, the canonical path must be contained within the extension source directory — path traversal via `../../` is rejected (`mcp.rs:88-112`).
- Entry point paths that are absolute are forced to relative via `trim_start_matches('/')` (`manifest.rs:173`).

### entry point resolution

`EntryPoints::resolve(python_path, source_dir)` (`manifest.rs:142-185`) converts a string like `".vaultspec/lib/scripts/subagent.py serve"` into:

```
ResolvedCommand {
    program: /path/to/.venv/bin/python,
    args: ["/abs/source_dir/.vaultspec/lib/scripts/subagent.py", "serve"]
}
```

The entry point string is split on whitespace: the first token is the script path (joined to `source_dir`), remaining tokens become additional args. The python interpreter is always `program`.

---

## 8. gaps and unimplemented surface

| Capability | Status | Where |
|---|---|---|
| `extension install` | Not implemented | `extension.rs:14-18` |
| `extension add` | Not implemented | `extension.rs:21-25` |
| `extension init` | Not implemented | `extension.rs:28-32` |
| `extension remove` | Not implemented | `extension.rs:35-39` |
| Git clone of extension source | Not implemented | No code path exists |
| Python venv creation | Not implemented | Only probing exists (`engine.rs:612-626`) |
| Running `runtime.install` command | Not implemented | Field is parsed, never executed |
| `requires.python.version` checking | Not implemented | Field is parsed, never checked |
| Extension activation state tracking | Not implemented | No install state persisted |
| Content type syncing (rules/agents) | Not implemented | `provides.content_types` parsed, not acted on |
| `outputs` directory mapping | Not implemented | Fields parsed, not used |

---

## 9. key type relationships

```
repo-core::config::Manifest
  .extensions: HashMap<String, Value>   ← freeform per-extension table

repo-extensions::ExtensionConfig         ← typed view of one extension entry
  .source: String
  .ref_pin: Option<String>
  .config: HashMap<String, toml::Value>

repo-extensions::ExtensionManifest      ← parsed repo_extension.toml
  .extension: ExtensionMeta
  .requires: Option<Requirements>
  .runtime: Option<RuntimeConfig>
  .entry_points: Option<EntryPoints>
  .provides: Option<Provides>
  .outputs: Option<Outputs>

repo-extensions::ResolveContext          ← inputs to mcp.json template resolution
  .root: String
  .extension_source: String
  .python_path: Option<String>

repo-extensions::ExtensionRegistry       ← static in-memory catalog
  .entries: HashMap<String, ExtensionEntry>

repo-meta::Registry                      ← preset-id -> provider mapping
  "env:python" -> "uv"
  "env:node" -> "node"
  "env:rust" -> "rust"
```

---

## 10. crate dependency graph (extension-relevant)

```
repo-cli
  -> repo-extensions (ExtensionRegistry for list command)
  -> repo-core (SyncEngine, Manifest)

repo-core
  -> repo-extensions (ExtensionManifest, resolve_mcp_config, merge_mcp_configs)

repo-mcp
  -> repo-extensions (dependency, exact role TBD)

repo-extensions
  -> toml, serde, serde_json, semver, thiserror, tracing
```

(`Cargo.toml` membership confirmed via: `repo-cli/Cargo.toml`, `repo-core/Cargo.toml`, `repo-mcp/Cargo.toml` all list `repo-extensions` as a dependency.)
