---
feature: unwrap-fix-theme-registry
date: 2026-02-06
related: [[2026-02-06-editor-audit-reference]]
---

# `unwrap()` Fix in `ThemeRegistry`

## Summary

This document details the audit and fix of `expect()` calls within the `ThemeRegistry` in `crates/pp-ui-theme/src/registry.rs`. The primary goal is to eliminate potential panics by providing graceful fallback mechanisms when the active UI or syntax themes are not found in the registry.

## Problem

The `ThemeRegistry::active_ui()` and `ThemeRegistry::active_syntax()` methods currently use `expect()`, which will cause the application to panic if the requested active theme (UI or syntax) is not found in the registry. This can lead to application crashes and an undesirable user experience.

## Solution

The `expect()` calls will be replaced with `Option::map_or()` or a similar approach. This change ensures that if an active theme is not found, a predefined default theme is returned instead of panicking.

- For `ThemeRegistry::active_ui()`, the default `UiTheme` will be `pp_ui_theme::ui::nova::dark()`.
- For `ThemeRegistry::active_syntax()`, the default `SyntaxTheme` will be `pp_ui_theme::syntax::one_dark::theme()`.

## Changes Proposed

The following changes will be applied to `crates/pp-ui-theme/src/registry.rs`:

1. **Locate `expect()` calls**: Identify the lines containing `.expect("active ui theme not found")` and `.expect("active syntax theme not found")` in the `active_ui()` and `active_syntax()` methods, respectively.
2. **Replace with `Option::map_or()`**:
    - `ThemeRegistry::active_ui()`: Replace the `expect()` call with `map_or(pp_ui_theme::ui::nova::dark(), |theme| theme.clone())`.
    - `ThemeRegistry::active_syntax()`: Replace the `expect()` call with `map_or(pp_ui_theme::syntax::one_dark::theme(), |theme| theme.clone())`.

## Verification

After applying the changes, `cargo clippy --package pp-ui-theme` will be executed to ensure the code remains clean and free of new linting issues. This will also confirm that the `expect()` calls have been successfully removed.

## Impact

This change significantly improves the robustness and crash-resistance of the application's theming system by preventing panics in scenarios where active themes might not be correctly configured or loaded. It ensures a consistent user experience by always providing a fallback theme.
