---
tags:
  - "#step-record"
  - "#phase2"
  - "#incremental-layout"
date: 2026-02-06
phase: 2
step: 2
status: in_progress
related:
  - "[[2026-02-06-editor-improvement-plan]]"
  - "[[2026-02-06-incremental-layout-engine-design-adr]]"
  - "[[2026-02-06-editor-improvement-phase2-step1]]"
---

# Step 2: Implement SumTree Operations for Incremental Updates

## Objective

Complete the `SumTree` implementation with operations required for efficient range-based updates.

## Required Operations

Based on Step 1 design, we need:

1. **`append()`** - Join two trees (for split-modify-rejoin pattern)
2. **`insert_at<D>()`** - Insert items at a specific dimension
3. **`remove_range<D>()`** - Remove items in a range
4. **`replace_range<D>()`** - Replace items in a range (delete + insert)
5. **Complete `split_off<D>()`** - Currently marked `unimplemented!()`

## Implementation Strategy

### 1. Complete `split_off()`

The existing implementation has the right structure but stops at `unimplemented!()`.

**Key insight**: We can use a simpler approach - rebuild the tree by filtering items via cursor traversal instead of in-place Arc manipulation.

```rust
pub fn split_off<D: Dimension<T::Summary>>(
    &mut self,
    dim: &D,
    bias: Bias,
    cx: &<T::Summary as Summary>::Context,
) -> Self {
    // Use cursor to collect left and right items
    let mut cursor = self.cursor::<D>();
    cursor.seek(dim, bias, cx);

    // Collect right items
    let mut right_items = Vec::new();
    while cursor.item().is_some() {
        right_items.push(cursor.item().unwrap().clone());
        cursor.next(cx);
    }

    // Rebuild self as left tree (items before split point)
    // Rebuild right tree from collected items
    // Return right tree
}
```

### 2. Implement `append()`

```rust
pub fn append(&mut self, other: SumTree<T>, cx: &<T::Summary as Summary>::Context) {
    // Simple approach: extract all items from other, push to self
    let mut cursor = other.cursor::<D::default()>();
    while let Some(item) = cursor.item() {
        self.push(item.clone(), cx);
        cursor.next(cx);
    }
}
```

### 3. Implement High-Level Edit Operations

```rust
pub fn replace_range<D: Dimension<T::Summary>>(
    &mut self,
    start: &D,
    end: &D,
    items: Vec<T>,
    cx: &<T::Summary as Summary>::Context,
) {
    // 1. Split at end dimension
    let mut right = self.split_off(end, Bias::Right, cx);

    // 2. Split self at start dimension
    let _middle = self.split_off(start, Bias::Left, cx);

    // 3. Insert new items
    for item in items {
        self.push(item, cx);
    }

    // 4. Append right portion
    self.append(right, cx);
}
```

## Correctness Considerations

1. **Dimension Ordering**: All operations must respect the Ord constraint on Dimension
2. **Summary Recomputation**: Every structural change must trigger summary updates
3. **Arc Sharing**: Must use `Arc::make_mut()` correctly for copy-on-write
4. **Empty Trees**: Handle edge cases where trees become empty

## Testing Strategy

Add unit tests to `sum_tree/mod.rs`:

```rust
#[test]
fn test_split_off_basic() {
    let mut tree = SumTree::new();
    // Push items...
    let right = tree.split_off(&dimension, Bias::Right, &());
    // Verify left and right contain correct items
}

#[test]
fn test_replace_range() {
    let mut tree = SumTree::new();
    // Push items...
    tree.replace_range(&start, &end, new_items, &());
    // Verify range was replaced correctly
}

#[test]
fn test_append() {
    let mut left = SumTree::new();
    let mut right = SumTree::new();
    // Push items to both...
    left.append(right, &());
    // Verify all items present in left
}
```

## Implementation Notes

- Prioritize correctness over optimization initially
- Use cursor-based traversal (simple, safe) over complex Arc manipulation
- Performance optimization can come later once correctness is proven
- Document all public methods with examples

## Next Steps

After completing these operations:

- Step 3: Implement patch application in each DisplayMap layer
- Step 4: Integrate with `sync_layout()`
