---
tags:
  - "#reference"
  - "#commands"
date: 2026-02-05
related: []
---

# Command System vs Action System Analysis

**Date:** 2026-02-05
**Auditor:** Lead Implementation Engineer
**Status:** Analysis Complete - Recommendation: KEEP SEPARATE

## Executive Summary

The `@command` system in `pp-editor-core` and the action system in `pp-editor-events` serve **distinct, complementary purposes** and should remain separate. The command system is for **asynchronous LLM/plugin-triggered text operations**, while the action system is for **synchronous keyboard-driven UI commands**.

## System Comparison

### @command System (`pp-editor-core/api/commands.rs`)

**Purpose:** Async handler for text-based LLM/plugin commands triggered within markdown content

**Characteristics:**

- **Async by design** (`async fn execute`)
- **Text-in, text-out** (returns `Result<String, CommandError>`)
- **Context-aware** (receives `ProviderContext` with cursor position, block type, scope)
- **Cancelable** (accepts `CancellationToken` for long-running operations)
- **Name-based dispatch** (e.g., `@prompt`, `@p`, `@file`, `@web`)
- **Case-insensitive lookup** (via `CommandRegistry`)
- **Dynamic registration** (handlers can be added at runtime)

**Example Commands:**

```rust
@p list all files              -> "ls -la"
@prompt find modified today    -> "find . -mtime 0"
@file src/main.rs              -> <file contents>
@web search rust async         -> <web results>
```

**Architecture:**

```text
User types "@p list files" in markdown
    ↓
Parser detects @command syntax
    ↓
CommandRegistry::execute("p", "list files", context)
    ↓
LlmClient::generate_command()  [ASYNC, CANCELABLE]
    ↓
Returns "ls -la" to be inserted
```

### Action System (`pp-editor-events/actions.rs` + `dispatch.rs`)

**Purpose:** Synchronous keyboard-driven UI commands through GPUI event loop

**Characteristics:**

- **Sync by design** (registered via `.on_action()` in render)
- **Intent-based** (type-safe action structs, not strings)
- **Keystroke-triggered** (via `Keymap` and `KeyBinding`)
- **Context-filtered** (via `KeyContext` stack like "editor", "pane")
- **Focus-aware** (dispatch through focus tree)
- **Compile-time checked** (actions are Rust types)
- **Two-phase dispatch** (Capture and Bubble phases)

**Example Actions:**

```rust
actions!(editor, [MoveCursorUp, DeleteLine, Copy, Paste]);

// Keybinding:
ctrl-k ctrl-d  →  editor::DeleteLine
ctrl-s         →  workspace::Save
```

**Architecture:**

```text
User presses "ctrl-s"
    ↓
Platform Event → KeyDown
    ↓
Keystroke Matching (Keymap)
    ↓
Context Filtering (KeyContext stack)
    ↓
Action Dispatch (via DispatchTree)
    ↓
Handler executes synchronously
```

## Integration Points

### Where They Meet: Markdown Editor

The systems integrate in the markdown editor context:

1. **Actions handle UI interactions:**
   - Cursor movement (`MoveCursorUp`, `MoveCursorLeft`)
   - Text editing (`InsertNewline`, `DeleteCharBackward`)
   - Clipboard operations (`Copy`, `Paste`)

2. **Commands handle content generation:**
   - LLM prompts (`@prompt <description>`)
   - File insertion (`@file <path>`)
   - Web lookup (`@web <query>`)

### Terminal Block Example

The markdown parser detects terminal blocks with directives:

```markdown
<| @bash ls -la |>
<| @ps Get-Process |>
```

These `@` directives are **NOT** the same as `@command` handlers. They are:

- Markdown syntax markers (parsed by `MarkdownSpanKind::TerminalBlockDelimiter`)
- Shell type indicators (bash, powershell, etc.)
- NOT async command handlers

## Conflict Analysis

### No Overlap Found

| Aspect | @command System | Action System |
|--------|----------------|---------------|
| **Trigger** | Text parsing (`@name args`) | Keystrokes (`ctrl-k`) |
| **Execution** | Async (may take seconds) | Sync (instant) |
| **Return Value** | `Result<String>` | `DispatchResult` |
| **Input** | Natural language string | None (or action params) |
| **Cancelable** | Yes (via token) | No |
| **Registration** | Runtime (dynamic) | Compile-time (static) |
| **Dispatch** | String lookup | Type-based |

### Complementary Design

The systems work together:

```rust
// User types in editor
User: "@p list files"

// 1. Actions handle typing (via EditorInputEvent)
editor::InsertCharacter('p')  // Action system

// 2. Parser detects @command when complete
Parser: Found "@p list files"

// 3. Commands handle execution
CommandRegistry::execute() -> "ls -la"  // Command system

// 4. Actions handle insertion of result
editor::InsertText("ls -la")  // Action system
```

## Recommendation: KEEP SEPARATE

### Rationale

1. **Different Responsibilities:**
   - Commands: **Content generation** (AI/LLM integration)
   - Actions: **User interaction** (keyboard/UI control)

2. **Different Execution Models:**
   - Commands: Async, cancelable, long-running
   - Actions: Sync, immediate, short-lived

3. **Different Extension Points:**
   - Commands: Plugin authors add LLM providers, file readers, web scrapers
   - Actions: Plugin authors add keyboard shortcuts, UI commands

4. **No Duplication:**
   - Commands do NOT duplicate action functionality
   - Actions do NOT duplicate command functionality

### Why Migration Would Be Wrong

Attempting to merge these would create:

- **Type confusion:** String-based vs type-based dispatch
- **Async/sync mismatch:** Actions can't be async in GPUI
- **Loss of cancelation:** Actions have no cancelation protocol
- **Weakened type safety:** String-based commands lose compile-time checks

## Integration with GPUI Event Loop

### Current State (Legacy)

The command system is in `pp-editor-core` but not yet integrated with the GPUI event loop.

### Required Integration Steps

1. **Parser Integration:**

   ```rust
   // In EditorModel or EditorView
   fn parse_commands(&self, text: &str) -> Vec<CommandInvocation> {
       // Detect @command patterns in text
       // Return list of (command_name, args, byte_range)
   }
   ```

2. **Registry Access:**

   ```rust
   // In application context (not editor)
   struct AppState {
       command_registry: Arc<RwLock<CommandRegistry>>,
   }
   ```

3. **Async Execution:**

   ```rust
   // Commands execute on background task, not in render
   let registry = app.command_registry.clone();
   cx.spawn(|mut cx| async move {
       let result = registry.execute("prompt", "list files", ctx, cancel).await?;
       cx.update_model(&editor_model, |editor, cx| {
           editor.insert_text(&result);
           cx.notify();
       })?;
       Ok(())
   }).detach();
   ```

4. **UI Feedback:**
   - Show spinner/progress during execution
   - Handle cancelation (Escape key)
   - Display errors inline

### Suggested Crate Structure

```text
pp-editor-events/       # Action system (keyboard)
  ├─ actions.rs         # Define editor actions
  ├─ dispatch.rs        # Dispatch logic
  └─ keymap.rs          # Keybindings

pp-editor-core/         # Core editor logic
  ├─ api/
  │   └─ commands.rs    # @command trait (stays here)
  ├─ markdown/
  │   └─ parser.rs      # Detect @commands in text

pp-editor-commands/     # NEW: Command implementations
  ├─ registry.rs        # CommandRegistry
  ├─ prompt.rs          # @prompt handler (LLM)
  ├─ file.rs            # @file handler
  └─ web.rs             # @web handler

pp-editor-main/         # GPUI integration
  ├─ editor_model.rs    # Register action handlers
  └─ command_runner.rs  # NEW: Async command execution
```

## Future Considerations

### Potential Command/Action Bridge

For cases where a command result needs to trigger an action:

```rust
// Command completes
let result = registry.execute("file", "src/main.rs", ctx).await?;

// Dispatch action to insert
cx.dispatch_action(editor::InsertText { text: result });
```

### Command Palette Integration

Commands could appear in a command palette alongside actions:

```rust
// Palette shows:
[Action] editor: Delete Line          (ctrl-k ctrl-d)
[Action] workspace: Save              (ctrl-s)
[Command] @prompt: Generate command   (async)
[Command] @file: Insert file          (async)
```

## Conclusion

The `@command` system and action system are **architecturally complementary**:

- **Actions** = Keyboard-driven UI control (sync)
- **Commands** = Text-driven content generation (async)

They should remain separate with clear integration boundaries. The command system needs GPUI event loop integration for async execution, but this should be done in `pp-editor-main` or a new `pp-editor-commands` crate, not by merging with `pp-editor-events`.

## Files Reviewed

1. `crates/pp-editor-core/src/api/commands.rs` - Command handler trait
2. `crates/pp-editor-core/src/api/context.rs` - Provider context
3. `crates/pp-editor-events/src/actions.rs` - Action definitions
4. `crates/pp-editor-events/src/dispatch.rs` - Dispatch system
5. `crates/pp-editor-events/src/keymap.rs` - Keybinding system
6. `legacy/editor/providers/src/command_registry.rs` - Legacy registry
7. `legacy/editor/providers/src/prompt_command.rs` - Example command

## Next Steps

1. **Migrate CommandRegistry** from legacy to new crate:
   - Create `crates/pp-editor-commands/`
   - Move registry implementation
   - Keep `CommandHandler` trait in `pp-editor-core/api/`

2. **Integrate with GPUI:**
   - Add command parser to `EditorModel`
   - Implement async command runner in `pp-editor-main`
   - Add UI feedback (spinner, cancelation)

3. **Document Integration:**
   - ADR: "Command System Architecture"
   - Guide: "Writing Command Handlers"
   - Example: Custom command plugin
