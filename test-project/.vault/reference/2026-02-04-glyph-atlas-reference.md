---
tags:
  - "#reference"
  - "#glyph-atlas-audit"
date: 2026-02-04
related: []
---

# Reference Codebase Audit: Glyph Atlas and Texture Management

Feature: Glyph Atlas and Texture Management
Description: Efficient glyph rasterization, atlas packing, and GPU synchronization system.
Crate(s): gpui
File(s):

- `ref/zed/crates/gpui/src/platform/blade/blade_atlas.rs`
- `ref/zed/crates/gpui/src/platform/blade/blade_renderer.rs`
- `ref/zed/crates/gpui/src/platform/blade/shaders.wgsl`
- `ref/zed/crates/gpui/src/text_system.rs`
- `ref/zed/crates/gpui/src/window.rs`
- `ref/zed/crates/gpui/src/scene.rs`
- `ref/zed/crates/gpui/src/platform/mac/text_system.rs` (and other platform variants)

## References

### 1. Atlas Architecture (`blade_atlas.rs`)

The reference implementation employs a triple-atlas strategy to handle different rendering requirements:

- **Monochrome**: 1-byte per pixel (`R8Unorm`), used for standard text and SVG masks.
- **Subpixel**: 4-bytes per pixel (`Bgra8Unorm`), used for subpixel antialiased text.
- **Polychrome**: 4-bytes per pixel (`Bgra8Unorm`), used for emojis and images.

Each kind can have multiple textures (1024x1024 by default) managed by a `BladeAtlasStorage`. Growth is handled dynamically using `etagere::BucketedAtlasAllocator`.

### 2. Glyph Rasterization (`text_system.rs`, `platform/mac/text_system.rs`)

Rasterization is lazily triggered during the paint phase:

1. `Window::paint_glyph` calculates the `RenderGlyphParams` (including subpixel variants).
2. It requests a tile from `sprite_atlas.get_or_insert_with`.
3. If not cached, `TextSystem::rasterize_glyph` is called.
4. The platform-specific implementation (e.g., `MacTextSystemState::rasterize_glyph`) uses OS APIs (`CGContext` on macOS, `DirectWrite` on Windows) to draw the glyph into a CPU-side buffer.
5. The resulting bitmap is uploaded to the GPU via a `BufferBelt` staging system.

### 3. GPU Synchronization and Staging (`blade_atlas.rs`)

- **BufferBelt**: A pool of staging buffers used to copy data from CPU to GPU.
- **PendingUpload**: Stores metadata about uploads that need to happen before the frame is rendered.
- **`before_frame`**: Flushes all `PendingUpload`s using `gpu_encoder.transfer("atlas")`. This ensures all glyphs needed for the current frame are present in GPU textures before drawing commands start.
- **`after_frame`**: Resets the `BufferBelt` using a GPU sync point to ensure the GPU has finished reading before the CPU reclaims memory.

### 4. Specialized Rendering (`blade_renderer.rs`, `shaders.wgsl`)

The renderer uses specialized pipelines and shaders for each sprite type:

- **`fs_mono_sprite`**: Applies contrast enhancement and gamma correction to the single-channel alpha mask.
- **`fs_subpixel_sprite`**: Uses **Dual-Source Blending** (`@blend_src(1)`) to achieve high-quality subpixel antialiasing. It applies separate gamma correction per color channel.
- **`fs_poly_sprite`**: Standard color texture sampling, with optional grayscale conversion.

### 5. Batching and Sorting (`scene.rs`)

To maximize performance:

- Primitives are inserted into a `Scene`.
- `Scene::finish` sorts sprites by `order` (z-index) and then by `tile.tile_id` (which effectively groups by texture if they don't collide, though `BatchIterator` explicitly checks `texture_id`).
- `BatchIterator` breaks batches whenever the `texture_id` or `PrimitiveKind` changes, allowing the renderer to bind the correct texture and pipeline once per batch.

### 6. Subpixel Variants

The reference implementation generates 4 subpixel variants along the X axis (and Y on macOS) to improve text clarity. These are cached separately in the atlas, identified by `RenderGlyphParams.subpixel_variant`.
