---
tags:
  - "#reference"
  - "#legacy-code"
date: 2026-02-05
related: []
---

# Legacy Code Audit Report

**Date:** 2026-02-05
**Audited By:** Sonnet agents (3 parallel audits)
**Scope:** pp-editor-* crates
**Goal:** Identify deprecated code conflicting with reference-style architecture migration

---

## Executive Summary

The audit identified **2 deprecated modules** in `pp-editor-core` and significant integration gaps in `pp-editor-main`. The `pp-editor-events` crate is **production ready** with no legacy code.

### Quick Overview

| Crate | Status | Action Required |
|-------|--------|-----------------|
| pp-editor-core | ⚠️ Has legacy | Remove 2 modules |
| pp-editor-events | ✅ Clean | None |
| pp-editor-main | 🔴 Needs migration | Add pp-editor-events integration |

---

## pp-editor-core

### DEPRECATED (Remove)

#### `input.rs`

- **Path:** `src/input.rs`
- **Purpose:** Framework-agnostic input event types (KeyEvent, MouseEvent, etc.)
- **Conflict:** Duplicates `pp-editor-events::keyboard`, `pp-editor-events::mouse`
- **Action:** Delete - use GPUI native events via pp-editor-events

#### `input_handler.rs`

- **Path:** `src/input_handler.rs`
- **Purpose:** Custom InputHandler trait with built-in keybindings
- **Conflict:** Bypasses GPUI action system and pp-editor-events dispatch
- **Action:** Delete - implement action handlers instead

### NEEDS REVIEW

#### `api/commands.rs`

- **Path:** `src/api/commands.rs`
- **Purpose:** Custom @command handler trait
- **Concern:** May conflict with action system
- **Action:** Evaluate if distinct from actions or should be refactored

### KEEP (17+ modules)

| Module | Reason |
|--------|--------|
| `buffer.rs` | Core text storage (Ropey-backed) |
| `cursor.rs` | Cursor/selection state |
| `history.rs` | Undo/redo system |
| `operations.rs` | Editor operations (reusable from actions) |
| `state.rs` | Headless editor state |
| `display_map/` | Coordinate transformation (reference-compatible) |
| `decoration/` | Visual decorations |
| `folding/` | Code folding |
| `markdown/` | Markdown parsing |
| `syntax/` | Syntax highlighting |
| `layout/` | Text layout |
| `theme.rs` | Theme definitions |
| `sum_tree/` | Data structure |

---

## pp-editor-events

### Status: PRODUCTION READY

- **Modules:** 27 source modules
- **Lines:** ~7,400
- **Tests:** 220+ unit tests, 14 integration tests
- **Architecture:** Fully follows reference implementation patterns

### No Issues Found

The crate was built following reference implementation patterns throughout:

- ✅ GPUI hybrid model (direct handlers + actions)
- ✅ Two-phase dispatch (Capture/Bubble)
- ✅ FocusHandle-based focus management
- ✅ Hitbox-based mouse targeting
- ✅ Multi-stroke keystroke sequences
- ✅ IME support via InputHandler

### Minor Notes

- TODO comments in IME handler are **intentional** (awaiting buffer integration)
- StubPositionMap is a **testing utility**, not legacy code

---

## pp-editor-main

### Status: 40% INTEGRATED

**Critical Issue:** Does not depend on `pp-editor-events`

### Missing Integration

| Component | Current State | Required |
|-----------|---------------|----------|
| Event handlers | None | `.on_mouse_down()`, `.on_key_down()` |
| Focus management | Boolean field | FocusHandle from pp-editor-events |
| Action dispatch | Custom internal | pp-editor-events action system |
| Mouse targeting | None | Hitbox registration |
| Keyboard handling | Custom `handle_input()` | KeyboardHandler trait |

### Files Requiring Migration

**HIGH PRIORITY:**

1. `src/editor_model.rs` - Remove custom event handling, add FocusHandle
2. `src/editor_view.rs` - Add event handlers and focus tracking
3. `Cargo.toml` - Add pp-editor-events dependency

**MEDIUM PRIORITY:**
4. `src/default_keybindings.rs` - Integrate with pp-editor-events Keymap

### Rendering Infrastructure: GOOD

These files are well-integrated and need no changes:

- `src/editor_element.rs` - Element trait implementation
- `src/text_renderer.rs` - Glyph atlas system
- `src/gutter.rs` - Line numbers
- `src/decoration_views.rs` - Decoration rendering

---

## Migration Plan

### Phase 1: Remove Deprecated Code (pp-editor-core)

```bash
# Files to delete
crates/pp-editor-core/src/input.rs
crates/pp-editor-core/src/input_handler.rs

# Update lib.rs to remove module declarations
```

### Phase 2: Integrate pp-editor-main

1. **Add dependency:**

```toml
# In crates/pp-editor-main/Cargo.toml
pp-editor-events = { path = "../pp-editor-events" }
```

2. **Update EditorModel:**

- Replace `focused: bool` with `focus_handle: FocusHandle`
- Remove `handle_input()` and `dispatch_action()` methods
- Implement action handlers using pp-editor-events

3. **Update EditorView:**

```rust
div()
    .track_focus(&self.focus_handle)
    .on_mouse_down(MouseButton::Left, cx.listener(Self::handle_mouse_down))
    .on_key_down(cx.listener(Self::handle_key_down))
```

4. **Migrate keybindings:**

- Use pp-editor-events Keymap instead of pp-keymapping
- Add KeyContext for focus-aware bindings

### Phase 3: Verify Integration

- Run all tests
- Verify focus behavior
- Test mouse interactions
- Confirm action dispatch

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Removing input.rs breaks dependent code | Medium | Search for usages first |
| EditorModel refactor introduces bugs | High | Comprehensive testing |
| Keybinding migration breaks shortcuts | Medium | Test all default bindings |

---

## Recommendations

1. **Immediate:** Delete `input.rs` and `input_handler.rs` from pp-editor-core
2. **This Sprint:** Add pp-editor-events dependency to pp-editor-main
3. **Next Sprint:** Complete EditorModel and EditorView migration
4. **Follow-up:** Review `api/commands.rs` for action system integration

---

## Appendix: Compatibility Matrix

| pp-editor-core Module | pp-editor-events Equivalent | Action |
|----------------------|----------------------------|--------|
| `input.rs` | `keyboard`, `mouse`, `keystroke` | Replace |
| `input_handler.rs` | `actions`, `keymap`, `dispatch` | Replace |
| `buffer.rs` | *(none)* | Keep |
| `cursor.rs` | `selection` (partial) | Keep, minor updates |
| `operations.rs` | *(call from actions)* | Keep |
| `display_map/` | *(none)* | Keep |

---

**Audit Complete**
**Files Analyzed:** 45+
**Deprecated Modules:** 2
**Integration Gaps:** 4 critical
**Estimated Migration Effort:** Medium (2-3 days)
