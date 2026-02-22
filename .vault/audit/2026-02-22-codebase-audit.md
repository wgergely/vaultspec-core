---
tags: ["#audit", "#codebase-audit"]
related: ["[[2026-02-22-codebase-audit-research.md]]"]
date: 2026-02-22
---

# Codebase Audit Report: Security & Robustness

**Date:** 2026-02-22
**Scope:** `src/vaultspec` (All modules)
**Auditor:** vaultspec-code-reviewer

## Executive Summary
The codebase demonstrates a high level of maturity, security, and robustness. The architecture employs a "defense in depth" strategy, combining strict sandboxing at the protocol level with path validation at the client level. Error handling is generally robust, with graceful degradation for missing optional dependencies (RAG, PyYAML).

## Key Strengths
1.  **Sandboxing:** Strict enforcement of read-only modes and path restrictions in `protocol/sandbox.py` and `protocol/providers`.
2.  **Input Validation:** Strong sanitization of SQL queries (`rag/store.py`), shell commands (`hooks/engine.py`), and file paths.
3.  **Concurrency:** Robust state machine in `orchestration/task_engine.py` and thread-safe operations in `rag/indexer.py`.
4.  **Dependency Handling:** Core CLI functionality remains available even if heavy dependencies (Torch, LanceDB) are missing.

## Findings by Module

### 1. Core & Infrastructure
- **Logging:** Centralized configuration, but `cli.py` relies heavily on `print`/`stderr` instead of the logger.
- **Security:** Tokens loaded from user home (secure). Atomic file writes prevent corruption.
- **Recommendation:** Invoke `configure_logging()` earlier in `cli.py`.

### 2. Vault Operations (`vaultcore`, `graph`, `verification`)
- **Security:** `parser.py` prefers `yaml.safe_load`. Fallback parser is primitive but safe for simple use cases.
- **Robustness:** Resilient against UTF-8 BOM issues and file I/O errors.
- **Gaps:** `hydration.py` is silent on failures.

### 3. Protocol & Orchestration
- **Security:** Process isolation is excellent. Orphaned processes are actively killed. Tokens passed via env vars.
- **Robustness:** Bridges survive stream errors. Dead child processes are detected and respawned.
- **Logging:** Comprehensive JSONL session logs (sensitive data handling required for `.vault/logs/`).

### 4. RAG & Metrics
- **Security:** SQL injection prevented via manual sanitization in `store.py`. `trust_remote_code=True` in embeddings is a necessary supply-chain risk.
- **Robustness:** Fallback to filesystem scan if vector store unavailable.
- **Defect:** `get_document` crashes if RAG is enabled but GPU is missing (uncaught `GPUNotAvailableError`).

### 5. Tools & Hooks (`mcp_tools`, `hooks`)
- **Security:** `subprocess.run(shell=False)` mitigates injection in hooks. `spawn_agent` is high-privilege but scoped.
- **Robustness:** Timeouts enforced for shell commands (60s) and tasks (300s).

## Recommendations
1.  **Fix:** Catch `GPUNotAvailableError` in `rag/api.py` to enable fallback on non-GPU systems.
2.  **Improve:** Standardize `cli.py` logging to use the `logging` module.
3.  **Harden:** Consider stricter validation for the fallback YAML parser in `vaultcore/parser.py`.
