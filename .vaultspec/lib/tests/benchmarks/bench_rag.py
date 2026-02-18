#!/usr/bin/env python3
"""RAG stack benchmarks: embedding, indexing, search, and resource usage.

Run with:
    python tests/benchmarks/bench_rag.py

Outputs a clean table of benchmark results.
"""

from __future__ import annotations

import shutil
import statistics
import sys
import time

import pytest

# Standalone bootstrap (only needed when running outside pytest)
if __name__ == "__main__":
    from pathlib import Path as _Path

    _lib = _Path(__file__).resolve().parent.parent.parent
    for _p in [str(_lib / "src"), str(_lib)]:
        if _p not in sys.path:
            sys.path.insert(0, _p)

from tests.constants import TEST_PROJECT


def _hr(char: str = "-", width: int = 72) -> str:
    return char * width


@pytest.mark.benchmark
@pytest.mark.quality
def test_bench_embedding_throughput(model, n_docs: int = 50) -> dict:
    """Time embedding N synthetic documents."""
    texts = [
        f"Document {i}: Architecture decision about component {i} "
        f"with detailed analysis of trade-offs and implementation strategy."
        for i in range(n_docs)
    ]

    start = time.perf_counter()
    model.encode_documents(texts)
    elapsed = time.perf_counter() - start

    return {
        "n_docs": n_docs,
        "elapsed_s": elapsed,
        "docs_per_sec": n_docs / elapsed,
    }


@pytest.mark.benchmark
@pytest.mark.quality
def test_bench_full_index(root, model, store_class, indexer_class) -> dict:
    """Time full_index() on the entire vault corpus."""
    lance_dir = root / ".lance"
    if lance_dir.exists():
        shutil.rmtree(lance_dir)

    store = store_class(root)
    indexer = indexer_class(root, model, store)

    start = time.perf_counter()
    result = indexer.full_index()
    elapsed = time.perf_counter() - start

    return {
        "total_docs": result.total,
        "elapsed_s": elapsed,
        "docs_per_sec": result.total / elapsed if elapsed > 0 else 0,
        "device": result.device,
    }


@pytest.mark.benchmark
@pytest.mark.quality
def test_bench_incremental_noop(indexer) -> dict:
    """Time incremental_index() when nothing has changed."""
    start = time.perf_counter()
    result = indexer.incremental_index()
    elapsed = time.perf_counter() - start

    return {
        "elapsed_s": elapsed,
        "added": result.added,
        "removed": result.removed,
    }


@pytest.mark.benchmark
@pytest.mark.quality
def test_bench_search_latency(searcher, n_queries: int = 20) -> dict:
    """Measure search latency distribution over N queries."""
    queries = [
        "architecture decision",
        "editor demo layout",
        "displaymap coordinate mapping",
        "safety audit vulnerability",
        "implementation plan phase",
        "type:adr architecture",
        "feature:editor-demo rendering",
        "dispatch protocol selection",
        "incremental layout engine",
        "window positioning research",
        "text layout rendering",
        "event handling keyboard",
        "type:plan implementation",
        "tree-sitter parser",
        "vault graph re-ranking",
        "semantic search embedding",
        "LanceDB vector store",
        "date:2026-02 decisions",
        "caching audit performance",
        "code safety improvements",
    ]

    # Warmup
    searcher.search("warmup", top_k=1)

    latencies = []
    for i in range(n_queries):
        q = queries[i % len(queries)]
        start = time.perf_counter()
        searcher.search(q, top_k=5)
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies.append(elapsed_ms)

    latencies.sort()
    return {
        "n_queries": n_queries,
        "p50_ms": latencies[n_queries // 2],
        "p95_ms": latencies[int(n_queries * 0.95)],
        "p99_ms": latencies[int(n_queries * 0.99)],
        "mean_ms": statistics.mean(latencies),
        "stdev_ms": statistics.stdev(latencies) if len(latencies) > 1 else 0,
    }


@pytest.mark.benchmark
@pytest.mark.quality
def test_bench_memory(root) -> dict:
    """Measure GPU VRAM and LanceDB disk size. Requires CUDA GPU."""
    import torch

    result = {}
    result["gpu_name"] = torch.cuda.get_device_name(0)
    result["vram_allocated_mb"] = torch.cuda.memory_allocated(0) / (1024 * 1024)
    result["vram_reserved_mb"] = torch.cuda.memory_reserved(0) / (1024 * 1024)

    # LanceDB disk size
    lance_dir = root / ".lance"
    if lance_dir.exists():
        total_bytes = sum(f.stat().st_size for f in lance_dir.rglob("*") if f.is_file())
        result["lance_disk_mb"] = total_bytes / (1024 * 1024)
    else:
        result["lance_disk_mb"] = 0

    return result


def main():
    from rag.embeddings import EmbeddingModel
    from rag.indexer import VaultIndexer
    from rag.search import VaultSearcher
    from rag.store import VaultStore

    print(_hr("="))
    print("  RAG Stack Benchmarks")
    print(_hr("="))
    print()

    # Load model
    print("Loading embedding model...")
    t0 = time.perf_counter()
    model = EmbeddingModel()
    model_load_s = time.perf_counter() - t0
    print(f"  Model loaded in {model_load_s:.1f}s on {model.device}")
    print()

    # 1. Embedding throughput
    print(_hr())
    print("1. Embedding Throughput")
    print(_hr())
    for n in [10, 50, 100]:
        result = test_bench_embedding_throughput(model, n)
        print(
            f"  {result['n_docs']:>4d} docs: {result['elapsed_s']:.2f}s "
            f"({result['docs_per_sec']:.1f} docs/sec)"
        )
    print()

    # 2. Full index throughput
    print(_hr())
    print("2. Full Index Throughput (all vault docs)")
    print(_hr())
    idx_result = test_bench_full_index(TEST_PROJECT, model, VaultStore, VaultIndexer)
    print(
        f"  {idx_result['total_docs']} docs indexed in {idx_result['elapsed_s']:.2f}s "
        f"({idx_result['docs_per_sec']:.1f} docs/sec, device={idx_result['device']})"
    )
    print()

    # Set up components for remaining benchmarks
    store = VaultStore(TEST_PROJECT)
    indexer = VaultIndexer(TEST_PROJECT, model, store)
    searcher = VaultSearcher(TEST_PROJECT, model, store)

    # 3. Incremental no-op
    print(_hr())
    print("3. Incremental Index (no-op, nothing changed)")
    print(_hr())
    inc_result = test_bench_incremental_noop(indexer)
    print(
        f"  Elapsed: {inc_result['elapsed_s'] * 1000:.0f}ms "
        f"(added={inc_result['added']}, removed={inc_result['removed']})"
    )
    print()

    # 4. Search latency
    print(_hr())
    print("4. Search Latency (20 queries)")
    print(_hr())
    search_result = test_bench_search_latency(searcher, 20)
    print(f"  p50:  {search_result['p50_ms']:.1f}ms")
    print(f"  p95:  {search_result['p95_ms']:.1f}ms")
    print(f"  p99:  {search_result['p99_ms']:.1f}ms")
    mean = search_result["mean_ms"]
    stdev = search_result["stdev_ms"]
    print(f"  mean: {mean:.1f}ms (stdev={stdev:.1f}ms)")
    print()

    # 5. Memory / resources
    print(_hr())
    print("5. Resource Usage")
    print(_hr())
    mem = test_bench_memory(TEST_PROJECT)
    print(f"  GPU: {mem['gpu_name']}")
    print(f"  VRAM allocated: {mem['vram_allocated_mb']:.1f}MB")
    print(f"  VRAM reserved:  {mem['vram_reserved_mb']:.1f}MB")
    print(f"  LanceDB disk:   {mem['lance_disk_mb']:.1f}MB")
    print()

    # Cleanup
    lance_dir = TEST_PROJECT / ".lance"
    if lance_dir.exists():
        shutil.rmtree(lance_dir)

    print(_hr("="))
    print("  Benchmark complete")
    print(_hr("="))


if __name__ == "__main__":
    main()
