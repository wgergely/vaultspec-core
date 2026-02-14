---
tags:
  - "#plan"
  - "#editor-improvement"
date: 2026-02-06
related:
  - "[[2026-02-06-editor-audit-reference]]"
  - "[[2026-02-06-incremental-layout-engine-research]]"
  - "[[2026-02-06-incremental-layout-engine-design-adr]]"
  - "[[2026-02-04-adopt-zed-displaymap]]"
  - "[[2026-02-04-editor-event-handling]]"
---

# Editor Improvement Plan

This plan addresses critical safety, performance, and feature completeness issues identified in the recent editor audit (see [[2026-02-06-editor-audit-reference]]). The goal is to enhance the robustness, performance, and user experience of the `pp-editor-main` and `pp-editor-core` crates, bringing them closer to the standards set by the Zed reference codebase.

## Proposed Changes

Based on comprehensive research documented in [[2026-02-06-incremental-layout-engine-research]] and the architectural decisions in [[2026-02-06-incremental-layout-engine-design-adr]], we will:

1. **Systematically eliminate safety hazards** by replacing all problematic `unwrap()` calls with robust error handling or sensible defaults
2. **Implement an incremental layout engine** following Zed's DisplayMap and BlockMap patterns, using a `SumTree`-based approach with a "Patch" system for efficient synchronization
3. **Complete UI feature implementation** with robust IME support, custom block layout synchronization, gutter rendering, and code folding
4. **Conduct a comprehensive functional audit** to ensure parity with Zed's high standards for cursor movement, selection, scrolling, and rendering fidelity

The implementation strictly adheres to the "Hierarchy of Truth": `<ADR>` > `<Research>` > Implementation.

## Tasks

### Phase 1: Safety & Correctness Improvements

**Goal**: Systematically address critical correctness issues and replace all problematic `unwrap()` calls with robust error handling or sensible default values to prevent panics and improve application stability.

1. **Audit and fix `state.rs` unwrap calls**
   - Step summary: [[2026-02-06-editor-improvement-phase1-step1]]
   - Executing sub-agent: `safety-auditor`
   - References: [[2026-02-06-editor-audit-reference]]
   - Tasks:
     - Review all `unwrap()` calls related to selections
     - Implement `Option::map_or()`, `Result::unwrap_or_else()`, or the `?` operator
     - Document rationale for each change
     - Run `cargo clippy` to verify improvements

2. **Audit and fix Tree-sitter parser unwrap calls**
   - Step summary: [[2026-02-06-editor-improvement-phase1-step2]]
   - Executing sub-agent: `safety-auditor`
   - References: [[2026-02-06-editor-audit-reference]]
   - Tasks:
     - Identify all `unwrap()` calls in `syntax/tree_sitter/parser.rs`
     - Replace with error propagation (`Result` and `?`) or appropriate fallback mechanisms
     - Define clear error types for parsing failures
     - Ensure parsing failures do not lead to crashes

3. **Audit and fix theme_adapter unwrap calls**
   - Step summary: [[2026-02-06-editor-improvement-phase1-step3]]
   - Executing sub-agent: `safety-auditor`
   - References: [[2026-02-06-editor-audit-reference]]
   - Tasks:
     - Address the `unwrap()` call for theme's background color
     - Provide default background color if theme does not explicitly set one
     - Document the default color choice

4. **Fix buffer.rs CRLF handling**
   - Step summary: [[2026-02-06-editor-improvement-phase1-step4]]
   - Executing sub-agent: `standard-executor`
   - References: [[2026-02-06-editor-audit-reference]]
   - Tasks:
     - Update `Buffer::line_end_char` to handle both `\n` and `\r\n`
     - Prevent trailing `\r` issues in cross-platform scenarios
     - Add unit tests for CRLF handling

5. **Implement bounded history stacks**
   - Step summary: [[2026-02-06-editor-improvement-phase1-step5]]
   - Executing sub-agent: `standard-executor`
   - References: [[2026-02-06-editor-audit-reference]]
   - Tasks:
     - Implement maximum history depth or memory limit for `undo_stack` and `redo_stack`
     - Prevent memory exhaustion in long-lived sessions
     - Configure reasonable defaults (e.g., 1000 undo levels or 100MB memory limit)

6. **Fix layout/builder.rs style sorting**
   - Step summary: [[2026-02-06-editor-improvement-phase1-step6]]
   - Executing sub-agent: `standard-executor`
   - References: [[2026-02-06-editor-audit-reference]]
   - Tasks:
     - Ensure `push_style` maintains sorted `self.styles` OR
     - Refactor `build` method to handle unsorted styles correctly
     - Add tests to verify style application order

7. **Comprehensive unwrap() scan and remediation**
   - Step summary: [[2026-02-06-editor-improvement-phase1-step7]]
   - Executing sub-agent: `safety-auditor`
   - References: [[2026-02-06-editor-audit-reference]]
   - Tasks:
     - Perform project-wide search (`rg unwrap\(\)`) in `pp-editor-main` and `pp-editor-core`
     - Prioritize findings by severity and likelihood of panic
     - Address critical instances with proper error handling

8. **Automate Clippy fixes**
   - Step summary: [[2026-02-06-editor-improvement-phase1-step8]]
   - Executing sub-agent: `simple-executor`
   - References: [[2026-02-06-editor-audit-reference]]
   - Tasks:
     - Run `cargo clippy --fix` on `pp-editor-core`
     - Run `cargo clippy --fix` on `pp-editor-main`
     - Review and commit automated fixes

**Expected Outcome**: A stable and robust editor core that gracefully handles unexpected states and errors without crashing, adhering to Rust's idiomatic practices.

### Phase 2: Incremental Layout Engine with DisplayMap Patching

**Goal**: Implement an incremental layout strategy for `EditorState::sync_layout`, leveraging Zed's `DisplayMap` and `BlockMap` concepts with a "Patch" system for efficient synchronization. This significantly improves performance for large files and dynamic content.

1. **Design DisplayMap architecture and Patch system**
   - Step summary: [[2026-02-06-editor-improvement-phase2-step1]]
   - Executing sub-agent: `complex-executor`
   - References: [[2026-02-06-incremental-layout-engine-research]], [[2026-02-06-incremental-layout-engine-design-adr]], [[2026-02-04-adopt-zed-displaymap]]
   - Tasks:
     - Create detailed design document for incremental layout algorithm
     - Define `DisplayMap` internal structure with `SumTree` for layout metrics
     - Design "Patch" data structure for incremental updates (similar to Zed's approach)
     - Define how text edits, style changes, and block modifications generate patches
     - Document interface contracts and data flow

2. **Implement SumTree for layout metrics**
   - Step summary: [[2026-02-06-editor-improvement-phase2-step2]]
   - Executing sub-agent: `complex-executor`
   - References: [[2026-02-06-incremental-layout-engine-research]], [[2026-02-06-incremental-layout-engine-design-adr]]
   - Tasks:
     - Implement or integrate a `SumTree` data structure
     - Define summary types for line heights, cumulative heights, and block metrics
     - Implement efficient range queries for visible region determination
     - Add unit tests for `SumTree` operations

3. **Implement DisplayMap-like structure**
   - Step summary: [[2026-02-06-editor-improvement-phase2-step3]]
   - Executing sub-agent: `complex-executor`
   - References: [[2026-02-06-incremental-layout-engine-research]], [[2026-02-06-incremental-layout-engine-design-adr]]
   - Tasks:
     - Create `DisplayMap` structure in `EditorState`
     - Integrate `SumTree` for managing visual representation
     - Implement core methods: `to_display_point`, `to_buffer_point`, `row_count`
     - Ensure thread safety and proper synchronization

4. **Implement Patch system for incremental updates**
   - Step summary: [[2026-02-06-editor-improvement-phase2-step4]]
   - Executing sub-agent: `complex-executor`
   - References: [[2026-02-06-incremental-layout-engine-research]], [[2026-02-06-incremental-layout-engine-design-adr]]
   - Tasks:
     - Define `DisplayMapPatch` structure representing localized changes
     - Implement patch generation from buffer edits
     - Implement patch application to `DisplayMap` and `SumTree`
     - Ensure patches correctly handle line insertions, deletions, and modifications

5. **Refactor EditorState::sync_layout for incremental updates**
   - Step summary: [[2026-02-06-editor-improvement-phase2-step5]]
   - Executing sub-agent: `complex-executor`
   - References: [[2026-02-06-incremental-layout-engine-research]], [[2026-02-06-incremental-layout-engine-design-adr]]
   - Tasks:
     - Modify `sync_layout` to identify changes since last sync
     - Generate `DisplayMapPatch` for affected regions
     - Apply patches using `SumTree` to update layout data efficiently
     - Notify rendering pipeline about updated regions only
     - Preserve existing behavior during migration

6. **Implement BlockMap for custom content blocks**
   - Step summary: [[2026-02-06-editor-improvement-phase2-step6]]
   - Executing sub-agent: `complex-executor`
   - References: [[2026-02-06-incremental-layout-engine-research]], [[2026-02-06-incremental-layout-engine-design-adr]]
   - Tasks:
     - Develop `BlockMap` or integrate block management into `DisplayMap`
     - Define interface for custom blocks (markdown previews, diagnostics, etc.)
     - Implement block positioning and sizing within incremental layout
     - Ensure blocks respond correctly to scrolling, zooming, and text changes
     - Add support for dynamic block resizing

7. **Performance benchmarking and optimization**
   - Step summary: [[2026-02-06-editor-improvement-phase2-step7]]
   - Executing sub-agent: `standard-executor`
   - References: [[2026-02-06-incremental-layout-engine-design-adr]]
   - Tasks:
     - Establish benchmarks for layout calculation (small, medium, large files)
     - Measure old vs. new `sync_layout` implementation performance
     - Profile for bottlenecks and optimize hot paths
     - Document performance improvements (target: >5x faster for large files)

**Expected Outcome**: A highly performant and scalable layout engine leveraging incremental `DisplayMap` patching and `SumTree` for efficient layout calculations. Handles large files, rapid edits, and dynamic custom blocks without noticeable lag.

### Phase 3: UI Feature Completion & Synchronization

**Goal**: Address incomplete UI features, specifically robust IME composition tracking, comprehensive input handling, custom block synchronization, and implementation of missing core editor features like gutter and code folding.

1. **Implement robust IME composition tracking**
   - Step summary: [[2026-02-06-editor-improvement-phase3-step1]]
   - Executing sub-agent: `standard-executor`
   - References: [[2026-02-06-editor-audit-reference]], [[2026-02-04-editor-event-handling]]
   - Tasks:
     - Implement `marked_text_range` to track active IME composition
     - Implement `unmark_text` to clear composition state
     - Enhance `replace_and_mark_text_in_range` for full IME support
     - Render composition underline and pre-edit text
     - Support IME candidate window positioning
     - Test with Japanese, Chinese, and Korean IME systems

2. **Implement custom block layout synchronization with BlockMap**
   - Step summary: [[2026-02-06-editor-improvement-phase3-step2]]
   - Executing sub-agent: `standard-executor`
   - References: [[2026-02-06-editor-audit-reference]], [[2026-02-06-incremental-layout-engine-design-adr]]
   - Tasks:
     - Analyze current `TODO` comments in `pp-editor-main`
     - Integrate `BlockMap` functionality from Phase 2
     - Synchronize custom block layout with main text buffer
     - Ensure blocks respond to scrolling, zooming, and text changes
     - Follow Zed's architectural patterns for dynamic content
     - Resolve block height feedback loop issues

3. **Implement editor gutter rendering**
   - Step summary: [[2026-02-06-editor-improvement-phase3-step3]]
   - Executing sub-agent: `standard-executor`
   - References: [[2026-02-06-editor-audit-reference]]
   - Tasks:
     - Develop core gutter rendering logic in `pp-editor-main`
     - Display line numbers synchronized with text content
     - Integrate with existing `GutterTheme` from `theme.rs`
     - Support gutter click interactions for line selection
     - Render gutter decorations (breakpoints, diagnostics markers)

4. **Implement code folding**
   - Step summary: [[2026-02-06-editor-improvement-phase3-step4]]
   - Executing sub-agent: `standard-executor`
   - References: [[2026-02-06-editor-audit-reference]]
   - Tasks:
     - Develop logic to identify folding regions (syntax trees or indentation)
     - Maintain fold state in `EditorState`
     - Implement rendering for fold indicators (using `fold_indicator` theme)
     - Ensure folded regions impact line wrapping, cursor movement, and layout
     - Integrate `FoldRegion`, `UnfoldRegion`, `FoldAll`, `UnfoldAll` actions
     - Add keyboard shortcuts for folding operations

5. **Refine EditorView input handling**
   - Step summary: [[2026-02-06-editor-improvement-phase3-step5]]
   - Executing sub-agent: `standard-executor`
   - References: [[2026-02-06-editor-audit-reference]], [[2026-02-04-editor-event-handling]]
   - Tasks:
     - Review `EditorView` input handling for remaining inconsistencies
     - Ensure smooth interaction between keyboard, mouse, and touch input
     - Align with Zed's input architecture patterns
     - Add comprehensive input event tests

**Expected Outcome**: A complete and well-integrated UI supporting diverse input methods (including robust IME), seamlessly displaying custom content blocks via `BlockMap`, and including essential editor features like gutter and code folding.

### Phase 4: Comprehensive Functional Audit & Refinement

**Goal**: Conduct a deeper, granular functional audit of core editor features after foundational safety, performance, and UI issues are resolved. Compare against Zed's implementation for parity and identify areas for further refinement.

1. **Detailed cursor movement audit and implementation**
   - Step summary: [[2026-02-06-editor-improvement-phase4-step1]]
   - Executing sub-agent: `reference-auditor`
   - References: [[2026-02-06-editor-audit-reference]]
   - Tasks:
     - Compare cursor movement (character, word, line, paragraph, page, file start/end)
     - Audit smart navigation features (camelCase, snake_case awareness)
     - Implement missing or less robust movement commands
     - Test with multi-byte Unicode characters

2. **Advanced selection audit and implementation**
   - Step summary: [[2026-02-06-editor-improvement-phase4-step2]]
   - Executing sub-agent: `reference-auditor`
   - References: [[2026-02-06-editor-audit-reference]]
   - Tasks:
     - Evaluate text selection (single, multi-cursor, block selection)
     - Audit smart selection expansion (word, line, scope)
     - Implement advanced selection features as needed
     - Test rectangular block selection

3. **Comprehensive scrolling audit**
   - Step summary: [[2026-02-06-editor-improvement-phase4-step3]]
   - Executing sub-agent: `standard-executor`
   - References: [[2026-02-06-editor-audit-reference]]
   - Tasks:
     - Assess smooth scrolling implementation
     - Verify scroll-to-cursor behavior
     - Test scrollbar interaction (click, drag, scroll wheel)
     - Profile scrolling performance under various conditions
     - Ensure pixel-perfect and responsive scrolling

4. **Rendering fidelity audit**
   - Step summary: [[2026-02-06-editor-improvement-phase4-step4]]
   - Executing sub-agent: `reference-auditor`
   - References: [[2026-02-06-editor-audit-reference]]
   - Tasks:
     - Compare text rendering with Zed (font rendering, subpixel anti-aliasing)
     - Verify color accuracy and theme application
     - Test ligature support
     - Identify and correct visual artifacts or inconsistencies
     - Test on multiple platforms (Windows, macOS, Linux)

5. **Performance refinement and micro-optimizations**
   - Step summary: [[2026-02-06-editor-improvement-phase4-step5]]
   - Executing sub-agent: `standard-executor`
   - References: [[2026-02-06-incremental-layout-engine-design-adr]]
   - Tasks:
     - Conduct performance profiling to identify new bottlenecks
     - Implement micro-optimizations across the codebase
     - Optimize memory allocations and reduce clones
     - Profile and optimize rendering hot paths

**Expected Outcome**: An editor that matches or closely approximates Zed's high standards for functional completeness, responsiveness, and visual fidelity. All core editor operations are smooth, accurate, and performant.

## Parallelization

- **Phase 1 Steps 1-3** (Safety audits): Can be executed in parallel by `safety-auditor` as they target different modules
- **Phase 1 Steps 4-6** (Specific fixes): Can be executed in parallel by `standard-executor` as they are independent
- **Phase 2 Steps 1-4** (DisplayMap/Patch design and implementation): Must be executed sequentially due to dependencies
- **Phase 2 Step 6** (BlockMap): Can begin in parallel with Step 5 after Step 4 completes
- **Phase 3 Steps 1, 3, 4** (IME, Gutter, Folding): Can be executed in parallel as they are independent UI features
- **Phase 3 Step 2** (Custom block sync): Depends on Phase 2 Step 6 (BlockMap) completion
- **Phase 4 Steps 1-2** (Cursor/Selection audits): Can be executed in parallel by `reference-auditor`
- **Phase 4 Steps 3-5** (Scrolling, Rendering, Performance): Can be executed in parallel after incremental layout is stable

## Verification

### Phase 1 Success Criteria

- Zero `unwrap()` panics during normal operation across all tested scenarios
- All Clippy warnings resolved
- `cargo test` passes for all affected modules
- Manual testing confirms stable behavior under error conditions

### Phase 2 Success Criteria

- Layout calculation performance improvement >5x for files >10,000 lines
- Benchmark results documented showing old vs. new performance
- Incremental updates correctly handle all edit types (insert, delete, replace)
- Custom blocks render correctly and update incrementally
- `cargo test` passes for all new layout engine modules
- Integration tests confirm DisplayMap and BlockMap correctness

### Phase 3 Success Criteria

- IME composition works correctly for Japanese, Chinese, Korean input
- Custom blocks (markdown previews) synchronize perfectly with text edits
- Gutter displays correctly and stays synchronized with text
- Code folding works for all syntax-tree-supported languages
- All input events handled smoothly without dropped inputs
- Visual inspection confirms all UI features work as expected

### Phase 4 Success Criteria

- Cursor movement matches Zed's behavior across all movement types
- Selection features match Zed's advanced selection capabilities
- Scrolling is pixel-perfect and smooth (60 FPS minimum)
- Text rendering quality matches Zed on all platforms
- Performance profiling shows no remaining critical bottlenecks
- User acceptance testing confirms production-ready quality

### Overall Mission Success

The editor must demonstrate:

1. **Zero crashes** during extended use sessions (>1 hour continuous editing)
2. **Responsive performance** for large files (>50,000 lines) with <16ms frame times
3. **Complete IME support** verified by native speakers of CJK languages
4. **Production-ready quality** matching Zed's standards for core editing features

### Testing Strategy

Beyond unit and integration tests, verification requires:

- **Load testing**: Edit sessions with large files (100K+ lines)
- **Stress testing**: Rapid typing, rapid scrolling, rapid undo/redo
- **Platform testing**: Verification on Windows, macOS, Linux
- **Accessibility testing**: Screen reader compatibility, keyboard-only navigation
- **Visual regression testing**: Compare rendering output with baseline screenshots

**Honest Assessment**: While unit and integration tests provide confidence in correctness, the true measure of success requires extensive manual testing and user feedback. Visual features (gutter, folding, IME composition underlines) and performance characteristics (smooth scrolling, responsive editing) can only be fully validated through real-world usage. Each phase should include dedicated QA time for manual verification before proceeding to the next phase.
