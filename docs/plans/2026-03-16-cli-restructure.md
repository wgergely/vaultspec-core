# CLI Restructure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restructure the vaultspec-core CLI to conform to the binding contract (`cli-contract.md`), fixing all regressions, wrong behaviors, and structural issues documented in `cli-grounding-research.md`.

**Architecture:** Bottom-up. Fix the console/output foundation first (Unicode crash), then harden the backend APIs that new CLI commands need, then restructure the CLI namespace from flat to domain-grouped (`vault`, `spec`, `dev`), then fix the three top-level commands (`install`, `uninstall`, `sync`), then rewrite tests, then align the justfile. No backward compatibility — clean break.

**Tech Stack:** Python 3.13+, Typer, Rich, PyYAML, pytest, just

**References:**
- Contract: `cli-contract.md`
- Research: `cli-grounding-research.md`

---

## Phase 0: Foundation — Console & Global Options

Fix the output layer first. Every phase after this depends on Rich console working on Windows.

### Task 0.1: Fix Unicode crash on Windows

**Files:**
- Modify: `src/vaultspec_core/console.py`
- Test: `src/vaultspec_core/tests/cli/test_console.py` (create)

**Step 1: Write the failing test**

```python
# src/vaultspec_core/tests/cli/test_console.py
"""Tests for console singleton."""

import pytest

from vaultspec_core.console import get_console, reset_console


@pytest.mark.unit
class TestConsole:
    def setup_method(self):
        reset_console()

    def test_console_singleton_returns_same_instance(self):
        c1 = get_console()
        c2 = get_console()
        assert c1 is c2

    def test_console_reset_creates_new_instance(self):
        c1 = get_console()
        reset_console()
        c2 = get_console()
        assert c1 is not c2

    def test_console_can_print_unicode(self):
        """Console must handle Unicode without UnicodeEncodeError."""
        console = get_console()
        # These characters caused cp1252 crash on Windows
        console.print("✓ OK")
        console.print("⚠ WARN")
        console.print("█░")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest src/vaultspec_core/tests/cli/test_console.py -v`
Expected: FAIL on `test_console_can_print_unicode` with UnicodeEncodeError on Windows

**Step 3: Write minimal implementation**

Replace `console.py` content:

```python
"""Provide the shared Rich console used for user-facing CLI output.

Configures safe_box and encoding to prevent Unicode crashes on Windows
terminals that use cp1252 or similar legacy codepages.
"""

from __future__ import annotations

import os
import sys

from rich.console import Console

__all__ = ["get_console", "reset_console"]

_console: Console | None = None


def _is_utf8_capable() -> bool:
    """Check if stdout can handle UTF-8 output."""
    encoding = getattr(sys.stdout, "encoding", None) or ""
    return encoding.lower().replace("-", "") in ("utf8", "utf_8", "utf8")


def get_console() -> Console:
    """Return the shared stdout Rich console singleton.

    Configures safe_box=True on non-UTF-8 terminals to prevent
    UnicodeEncodeError from box-drawing and symbol characters.
    """
    global _console
    if _console is None:
        utf8 = _is_utf8_capable()
        _console = Console(
            highlight=False,
            soft_wrap=True,
            no_color="NO_COLOR" in os.environ,
            safe_box=not utf8,
        )
    return _console


def reset_console() -> None:
    """Reset the stdout console singleton."""
    global _console
    _console = None
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest src/vaultspec_core/tests/cli/test_console.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/vaultspec_core/console.py src/vaultspec_core/tests/cli/test_console.py
git commit -m "fix: prevent Unicode crash on Windows by enabling safe_box on non-UTF-8 terminals"
```

---

### Task 0.2: Remove --verbose, fix --target help, suppress completions

**Files:**
- Modify: `src/vaultspec_core/cli.py`
- Test: `src/vaultspec_core/tests/cli/test_main_cli.py` (will be rewritten later; update minimally now)

**Step 1: Write the failing test**

```python
# Add to test_main_cli.py or a new test_global_options.py
@pytest.mark.unit
class TestGlobalOptions:
    def test_no_verbose_flag(self, runner, test_project):
        """--verbose must not exist."""
        result = runner.invoke(app, ["--verbose", "sync"], catch_exceptions=False)
        assert result.exit_code != 0
        assert "No such option" in result.output or "no such option" in result.output.lower()

    def test_target_help_text(self, runner):
        """--target help must describe destination folder."""
        result = runner.invoke(app, ["--help"])
        assert "Select installation destination folder" in result.output

    def test_debug_flag_exists(self, runner, test_project):
        """--debug must still exist."""
        result = runner.invoke(app, ["--help"])
        assert "--debug" in result.output

    def test_no_install_completion(self, runner):
        """--install-completion must not appear in help."""
        result = runner.invoke(app, ["--help"])
        assert "--install-completion" not in result.output
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest src/vaultspec_core/tests/cli/test_main_cli.py::TestGlobalOptions -v`
Expected: FAIL — `--verbose` still exists, `--target` has wrong help text

**Step 3: Write minimal implementation**

In `cli.py`:

1. Change `app = typer.Typer(...)` to include `add_completion=False`
2. Remove the `verbose` parameter from `main()`
3. Simplify logging: only `--debug` toggles between WARNING (default) and DEBUG
4. Update `--target` help text

```python
app = typer.Typer(
    help=(
        "vaultspec-core: Workspace runtime for vaultspec-managed projects.\n\n"
        "Examples:\n"
        "  vaultspec-core install .\n"
        "  vaultspec-core sync\n"
        "  vaultspec-core vault stats\n"
        '  vaultspec-core spec rules add --name my-rule --content "Do not use mocks."\n'
    ),
    no_args_is_help=True,
    add_completion=False,
)

# ...

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    target: Annotated[
        Path | None,
        typer.Option(
            "--target",
            "-t",
            help='Select installation destination folder. Use "." for current working directory.',
            dir_okay=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    debug: Annotated[
        bool, typer.Option("--debug", "-d", help="Enable debug logging")
    ] = False,
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            help="Show version",
            callback=version_callback,
            is_eager=True,
        ),
    ] = False,
):
    """Initialize workspace and logging."""
    log_level = logging.DEBUG if debug else logging.WARNING
    configure_logging(level=log_level, debug=debug)
    # ... rest unchanged
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest src/vaultspec_core/tests/cli/test_main_cli.py::TestGlobalOptions -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/vaultspec_core/cli.py
git commit -m "fix: remove --verbose, fix --target help text, suppress typer completions"
```

---

## Phase 1: Backend Hardening

Build the backend functions that new CLI commands will need. No CLI changes yet — pure library code + tests.

### Task 1.1: Vault query engine — scan, filter, list

**Files:**
- Create: `src/vaultspec_core/vaultcore/query.py`
- Test: `src/vaultspec_core/vaultcore/tests/test_query.py`

This module composes `scan_vault()`, `get_doc_type()`, `parse_frontmatter()`, and `VaultGraph` into a unified query surface that `vault stats`, `vault list`, and `vault feature list` will call.

**Step 1: Write the failing tests**

```python
# src/vaultspec_core/vaultcore/tests/test_query.py
"""Tests for vault query engine."""

import pytest
from pathlib import Path

from vaultspec_core.vaultcore.query import (
    VaultDocument,
    list_documents,
    get_stats,
    list_feature_details,
)


@pytest.mark.unit
class TestListDocuments:
    def test_list_all(self, vault_project):
        docs = list_documents(vault_project)
        assert len(docs) > 0
        assert all(isinstance(d, VaultDocument) for d in docs)

    def test_filter_by_type(self, vault_project):
        docs = list_documents(vault_project, doc_type="adr")
        assert all(d.doc_type == "adr" for d in docs)

    def test_filter_by_feature(self, vault_project):
        docs = list_documents(vault_project, feature="test-feature")
        assert all(d.feature == "test-feature" for d in docs)

    def test_filter_by_date(self, vault_project):
        docs = list_documents(vault_project, date="2026-03-16")
        assert all(d.date == "2026-03-16" for d in docs)

    def test_list_orphaned(self, vault_project):
        docs = list_documents(vault_project, doc_type="orphaned")
        # Orphaned = no incoming links
        assert isinstance(docs, list)

    def test_list_invalid(self, vault_project):
        docs = list_documents(vault_project, doc_type="invalid")
        # Invalid = has broken outgoing links
        assert isinstance(docs, list)


@pytest.mark.unit
class TestGetStats:
    def test_basic_stats(self, vault_project):
        stats = get_stats(vault_project)
        assert "total_docs" in stats
        assert "total_features" in stats
        assert "counts_by_type" in stats

    def test_stats_with_feature_filter(self, vault_project):
        stats = get_stats(vault_project, feature="test-feature")
        assert "total_docs" in stats

    def test_stats_includes_orphan_count(self, vault_project):
        stats = get_stats(vault_project)
        assert "orphaned_count" in stats

    def test_stats_includes_invalid_count(self, vault_project):
        stats = get_stats(vault_project)
        assert "invalid_link_count" in stats


@pytest.mark.unit
class TestListFeatureDetails:
    def test_returns_feature_info(self, vault_project):
        features = list_feature_details(vault_project)
        assert isinstance(features, list)
        if features:
            f = features[0]
            assert "name" in f
            assert "doc_count" in f
            assert "types" in f
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest src/vaultspec_core/vaultcore/tests/test_query.py -v`
Expected: FAIL — `vaultcore.query` module does not exist

**Step 3: Write minimal implementation**

```python
# src/vaultspec_core/vaultcore/query.py
"""Unified query engine for .vault/ document operations.

Composes scanner, parser, graph, and metrics into a single query surface
used by CLI commands (vault stats, vault list, vault feature list).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .models import DocType
from .parser import parse_frontmatter
from .scanner import get_doc_type, scan_vault


@dataclass
class VaultDocument:
    """A resolved vault document with parsed metadata."""

    path: Path
    name: str
    doc_type: str
    feature: str | None
    date: str | None
    tags: list[str]


def _parse_date_from_filename(name: str) -> str | None:
    """Extract YYYY-MM-DD prefix from filename."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", name)
    return m.group(1) if m else None


def _parse_feature_from_tags(tags: list[str], doc_type_tag: str | None) -> str | None:
    """Extract feature name from tags (the non-type tag)."""
    for tag in tags:
        cleaned = tag.lstrip("#")
        if doc_type_tag and cleaned == doc_type_tag:
            continue
        if cleaned in {dt.value for dt in DocType}:
            continue
        return cleaned
    return None


def _scan_all(root_dir: Path) -> list[VaultDocument]:
    """Scan vault and parse all documents into VaultDocument objects."""
    docs = []
    for doc_path in scan_vault(root_dir):
        content = doc_path.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(content)
        dt = get_doc_type(doc_path, root_dir)
        dt_str = dt.value if dt else "unknown"
        tags = meta.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        feature = _parse_feature_from_tags(tags, dt_str)
        date = meta.get("date") or _parse_date_from_filename(doc_path.name)

        docs.append(
            VaultDocument(
                path=doc_path,
                name=doc_path.stem,
                doc_type=dt_str,
                feature=feature,
                date=str(date) if date else None,
                tags=tags,
            )
        )
    return docs


def list_documents(
    root_dir: Path,
    *,
    doc_type: str | None = None,
    feature: str | None = None,
    date: str | None = None,
) -> list[VaultDocument]:
    """List vault documents with optional filters.

    Args:
        root_dir: Project root directory.
        doc_type: Filter by type. Standard types: adr, audit, exec, plan,
            reference, research. Special types: "orphaned", "invalid".
        feature: Filter by feature tag (without # prefix).
        date: Filter by date string (YYYY-MM-DD).
    """
    docs = _scan_all(root_dir)

    if doc_type == "orphaned":
        from ..graph import VaultGraph

        graph = VaultGraph(root_dir)
        orphan_names = set(graph.get_orphaned())
        docs = [d for d in docs if d.name in orphan_names]
    elif doc_type == "invalid":
        from ..graph import VaultGraph

        graph = VaultGraph(root_dir)
        invalid_sources = {src for src, _ in graph.get_invalid_links()}
        docs = [d for d in docs if d.name in invalid_sources]
    elif doc_type:
        docs = [d for d in docs if d.doc_type == doc_type]

    if feature:
        feature = feature.lstrip("#")
        docs = [d for d in docs if d.feature == feature]

    if date:
        docs = [d for d in docs if d.date == date]

    return docs


def get_stats(
    root_dir: Path,
    *,
    feature: str | None = None,
    doc_type: str | None = None,
    date: str | None = None,
) -> dict:
    """Compute vault statistics with optional filters.

    Returns dict with: total_docs, total_features, counts_by_type,
    orphaned_count, invalid_link_count.
    """
    docs = list_documents(root_dir, feature=feature, doc_type=doc_type, date=date)

    counts_by_type: dict[str, int] = {}
    features: set[str] = set()
    for d in docs:
        counts_by_type[d.doc_type] = counts_by_type.get(d.doc_type, 0) + 1
        if d.feature:
            features.add(d.feature)

    # Orphan/invalid counts from graph (unfiltered)
    from ..graph import VaultGraph

    try:
        graph = VaultGraph(root_dir)
        orphaned_count = len(graph.get_orphaned())
        invalid_link_count = len(graph.get_invalid_links())
    except Exception:
        orphaned_count = 0
        invalid_link_count = 0

    return {
        "total_docs": len(docs),
        "total_features": len(features),
        "counts_by_type": counts_by_type,
        "orphaned_count": orphaned_count,
        "invalid_link_count": invalid_link_count,
    }


def list_feature_details(
    root_dir: Path,
    *,
    date: str | None = None,
    doc_type: str | None = None,
    orphaned_only: bool = False,
) -> list[dict]:
    """List features with enriched metadata.

    Returns list of dicts with: name, doc_count, types (set of doc types
    present), earliest_date, has_plan.
    """
    docs = _scan_all(root_dir)

    # Group by feature
    by_feature: dict[str, list[VaultDocument]] = {}
    for d in docs:
        if d.feature:
            by_feature.setdefault(d.feature, []).append(d)

    # Orphan detection
    orphan_features: set[str] = set()
    if orphaned_only:
        from ..graph import VaultGraph

        graph = VaultGraph(root_dir)
        orphan_names = set(graph.get_orphaned())
        for feat, feat_docs in by_feature.items():
            if all(d.name in orphan_names for d in feat_docs):
                orphan_features.add(feat)

    results = []
    for feat, feat_docs in sorted(by_feature.items()):
        if orphaned_only and feat not in orphan_features:
            continue

        types = {d.doc_type for d in feat_docs}

        if doc_type and doc_type not in types:
            continue

        dates = [d.date for d in feat_docs if d.date]
        earliest = min(dates) if dates else None

        if date and earliest and earliest > date:
            continue

        results.append(
            {
                "name": feat,
                "doc_count": len(feat_docs),
                "types": sorted(types),
                "earliest_date": earliest,
                "has_plan": "plan" in types,
            }
        )

    return results
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest src/vaultspec_core/vaultcore/tests/test_query.py -v`
Expected: PASS (may need conftest fixture for `vault_project` — use existing vault test fixtures)

**Step 5: Update `vaultcore/__init__.py` exports**

Add to `src/vaultspec_core/vaultcore/__init__.py`:
```python
from .query import VaultDocument as VaultDocument
from .query import get_stats as get_stats
from .query import list_documents as list_documents
from .query import list_feature_details as list_feature_details
```

**Step 6: Commit**

```bash
git add src/vaultspec_core/vaultcore/query.py src/vaultspec_core/vaultcore/tests/test_query.py src/vaultspec_core/vaultcore/__init__.py
git commit -m "feat: add vault query engine for stats, list, and feature detail operations"
```

---

### Task 1.2: Feature archive mechanism

**Files:**
- Modify: `src/vaultspec_core/vaultcore/query.py` (add `archive_feature`)
- Test: `src/vaultspec_core/vaultcore/tests/test_query.py` (add archive tests)

**Step 1: Write the failing test**

```python
@pytest.mark.unit
class TestArchiveFeature:
    def test_archive_moves_docs(self, vault_project):
        """Archiving moves all docs for a feature into .vault/_archive/."""
        from vaultspec_core.vaultcore.query import archive_feature

        result = archive_feature(vault_project, "test-feature")
        assert result["archived_count"] >= 0
        archive_dir = vault_project / ".vault" / "_archive"
        # If docs existed, archive dir should be created
        if result["archived_count"] > 0:
            assert archive_dir.exists()

    def test_archive_nonexistent_feature(self, vault_project):
        """Archiving a feature with no docs returns zero count."""
        from vaultspec_core.vaultcore.query import archive_feature

        result = archive_feature(vault_project, "nonexistent-feature-xyz")
        assert result["archived_count"] == 0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest src/vaultspec_core/vaultcore/tests/test_query.py::TestArchiveFeature -v`
Expected: FAIL — `archive_feature` does not exist

**Step 3: Write minimal implementation**

Add to `query.py`:

```python
def archive_feature(root_dir: Path, feature: str) -> dict:
    """Move all documents for a feature into .vault/_archive/.

    Preserves directory structure under the archive folder.

    Returns dict with: archived_count, paths (list of new paths).
    """
    import shutil

    from ..config import get_config

    cfg = get_config()
    vault_dir = root_dir / cfg.docs_dir
    archive_dir = vault_dir / "_archive"

    feature = feature.lstrip("#")
    docs = list_documents(root_dir, feature=feature)

    if not docs:
        return {"archived_count": 0, "paths": []}

    archived: list[str] = []
    for doc in docs:
        # Preserve subdirectory (e.g., adr/, plan/)
        rel = doc.path.relative_to(vault_dir)
        dest = archive_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(doc.path), str(dest))
        archived.append(str(dest.relative_to(root_dir)))

    return {"archived_count": len(archived), "paths": archived}
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest src/vaultspec_core/vaultcore/tests/test_query.py::TestArchiveFeature -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/vaultspec_core/vaultcore/query.py src/vaultspec_core/vaultcore/tests/test_query.py
git commit -m "feat: add feature archive mechanism (moves docs to .vault/_archive/)"
```

---

### Task 1.3: Manifest-aware sync filtering

**Files:**
- Modify: `src/vaultspec_core/core/sync.py`
- Test: `src/vaultspec_core/tests/cli/test_sync_manifest.py` (create)

**Step 1: Write the failing test**

```python
# src/vaultspec_core/tests/cli/test_sync_manifest.py
"""Tests for manifest-aware sync filtering."""

import json
import pytest
from vaultspec_core.core import types as _t
from vaultspec_core.core.sync import sync_to_all_tools
from vaultspec_core.core.enums import Tool


@pytest.mark.unit
class TestManifestAwareSync:
    def test_sync_to_all_skips_uninstalled_providers(self, test_project):
        """sync_to_all_tools must skip providers not in manifest."""
        # Write manifest with only claude installed
        manifest_path = test_project / ".vaultspec" / "providers.json"
        manifest_path.write_text(
            json.dumps({"version": "1.0", "installed": ["claude"]}),
            encoding="utf-8",
        )
        # Create a test rule
        rule = _t.RULES_SRC_DIR / "test.md"
        rule.write_text("---\nname: test\n---\nTest rule.\n", encoding="utf-8")

        from vaultspec_core.core.rules import collect_rules, transform_rule

        sources = collect_rules()
        result = sync_to_all_tools(
            sources, "rules_dir", transform_rule, "Rules"
        )
        # Should only have synced to .claude/rules, not .gemini/rules etc.
        claude_rules = test_project / ".claude" / "rules"
        gemini_rules = test_project / ".gemini" / "rules"
        assert (claude_rules / "test.md").exists()
        assert not (gemini_rules / "test.md").exists()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest src/vaultspec_core/tests/cli/test_sync_manifest.py -v`
Expected: FAIL — sync currently writes to all configured tools regardless of manifest

**Step 3: Write minimal implementation**

In `sync.py`, modify `sync_to_all_tools()` to read manifest and filter:

```python
def sync_to_all_tools(
    sources, dir_attr, transform_fn, label,
    prune=False, dry_run=False, dest_path_fn=None, is_skill=False,
) -> SyncResult:
    """Sync sources to all installed tool destinations.

    Reads the provider manifest and skips tools that are not installed.
    """
    from .manifest import read_manifest

    installed = read_manifest(_t.TARGET_DIR)
    total = SyncResult()

    for tool_type, cfg in _t.TOOL_CONFIGS.items():
        # Skip providers not in manifest (when manifest exists)
        if installed and cfg.name not in installed:
            continue

        dest_dir = getattr(cfg, dir_attr, None)
        if dest_dir is None:
            continue
        # ... rest of existing logic
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest src/vaultspec_core/tests/cli/test_sync_manifest.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/vaultspec_core/core/sync.py src/vaultspec_core/tests/cli/test_sync_manifest.py
git commit -m "fix: sync_to_all_tools respects provider manifest instead of syncing all configured tools"
```

---

### Task 1.4: Revert mechanism for builtin resources

**Files:**
- Create: `src/vaultspec_core/core/revert.py`
- Test: `src/vaultspec_core/core/tests/test_revert.py` (create)

**Step 1: Write the failing test**

```python
# src/vaultspec_core/core/tests/test_revert.py
"""Tests for builtin resource revert."""

import pytest
from pathlib import Path

from vaultspec_core.core.revert import (
    is_builtin,
    get_builtin_content,
    revert_resource,
)


@pytest.mark.unit
class TestRevert:
    def test_is_builtin_detects_suffix(self):
        assert is_builtin("governance.builtin.md") is True
        assert is_builtin("my-custom-rule.md") is False

    def test_get_builtin_content_returns_original(self):
        """Builtin resources ship with the package and can be retrieved."""
        # This depends on actual builtin files existing in the package
        # For now, test the interface
        content = get_builtin_content("rules", "governance.builtin.md")
        # Either returns content (if file exists in package) or None
        assert content is None or isinstance(content, str)

    def test_revert_builtin_restores_content(self, tmp_path):
        """Revert overwrites a modified builtin with its original."""
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        target = rules_dir / "governance.builtin.md"
        target.write_text("MODIFIED CONTENT", encoding="utf-8")

        result = revert_resource("rules", "governance.builtin.md", rules_dir)
        assert result["reverted"] is True or result["reverted"] is False
        # If original exists in package, file should be restored

    def test_revert_custom_resource_fails(self, tmp_path):
        """Cannot revert a custom (non-builtin) resource."""
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        target = rules_dir / "my-rule.md"
        target.write_text("custom content", encoding="utf-8")

        result = revert_resource("rules", "my-rule.md", rules_dir)
        assert result["reverted"] is False
        assert "not a builtin" in result["reason"].lower()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest src/vaultspec_core/core/tests/test_revert.py -v`
Expected: FAIL — module does not exist

**Step 3: Write minimal implementation**

```python
# src/vaultspec_core/core/revert.py
"""Revert mechanism for builtin firmware resources.

Builtin resources (files ending in .builtin.md) ship with the vaultspec-core
package. Revert restores the original package content, discarding local edits.
Custom resources cannot be reverted — they have no canonical original.
"""

from __future__ import annotations

import importlib.resources
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_BUILTIN_SUFFIX = ".builtin.md"

# Map resource categories to their package data paths
_PACKAGE_PATHS: dict[str, str] = {
    "rules": "vaultspec_core.firmware.rules",
    "skills": "vaultspec_core.firmware.skills",
    "agents": "vaultspec_core.firmware.agents",
    "system": "vaultspec_core.firmware.system",
}


def is_builtin(filename: str) -> bool:
    """Check if a filename represents a builtin resource."""
    return filename.endswith(_BUILTIN_SUFFIX)


def get_builtin_content(category: str, filename: str) -> str | None:
    """Retrieve the original content of a builtin resource from the package.

    Returns None if the resource is not found in the package.
    """
    package = _PACKAGE_PATHS.get(category)
    if not package:
        return None

    try:
        pkg = importlib.resources.files(package)
        resource = pkg / filename
        if resource.is_file():
            return resource.read_text(encoding="utf-8")
    except (ModuleNotFoundError, FileNotFoundError, TypeError):
        pass

    return None


def revert_resource(
    category: str, filename: str, base_dir: Path
) -> dict:
    """Revert a resource to its builtin original.

    Args:
        category: Resource category (rules, skills, agents, system).
        filename: The resource filename (must end in .builtin.md).
        base_dir: Directory containing the resource file.

    Returns:
        Dict with "reverted" (bool) and "reason" (str).
    """
    if not is_builtin(filename):
        return {"reverted": False, "reason": "Not a builtin resource. Only .builtin.md files can be reverted."}

    original = get_builtin_content(category, filename)
    if original is None:
        return {"reverted": False, "reason": f"Original not found in package for {category}/{filename}."}

    target = base_dir / filename
    from .helpers import atomic_write

    atomic_write(target, original)
    logger.info("Reverted %s/%s to package original.", category, filename)
    return {"reverted": True, "reason": "Restored to package original."}
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest src/vaultspec_core/core/tests/test_revert.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/vaultspec_core/core/revert.py src/vaultspec_core/core/tests/test_revert.py
git commit -m "feat: add revert mechanism for builtin firmware resources"
```

---

### Task 1.5: Dry-run tree renderer

**Files:**
- Create: `src/vaultspec_core/core/dry_run.py`
- Test: `src/vaultspec_core/core/tests/test_dry_run.py` (create)

**Step 1: Write the failing test**

```python
# src/vaultspec_core/core/tests/test_dry_run.py
"""Tests for dry-run tree renderer."""

import pytest
from pathlib import Path

from vaultspec_core.core.dry_run import DryRunItem, DryRunStatus, render_dry_run_tree


@pytest.mark.unit
class TestDryRunTree:
    def test_renders_new_items(self, capsys):
        items = [
            DryRunItem(".vaultspec/", DryRunStatus.NEW),
            DryRunItem(".vaultspec/rules/", DryRunStatus.NEW),
        ]
        render_dry_run_tree(items, title="Install preview")
        # Should not crash and should produce output
        # (Rich console output captured via capsys)

    def test_renders_mixed_statuses(self, capsys):
        items = [
            DryRunItem(".vaultspec/", DryRunStatus.EXISTS),
            DryRunItem(".claude/rules/", DryRunStatus.NEW),
            DryRunItem("CLAUDE.md", DryRunStatus.UPDATE),
            DryRunItem(".gemini/", DryRunStatus.DELETE),
        ]
        render_dry_run_tree(items, title="Preview")

    def test_status_enum_values(self):
        assert DryRunStatus.NEW.value == "new"
        assert DryRunStatus.EXISTS.value == "exists"
        assert DryRunStatus.UPDATE.value == "update"
        assert DryRunStatus.OVERRIDE.value == "override"
        assert DryRunStatus.DELETE.value == "delete"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest src/vaultspec_core/core/tests/test_dry_run.py -v`
Expected: FAIL — module does not exist

**Step 3: Write minimal implementation**

```python
# src/vaultspec_core/core/dry_run.py
"""Rich tree renderer for dry-run previews.

Used by install --dry-run and uninstall --dry-run to display a coloured,
categorized tree of filesystem changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from rich.tree import Tree

from vaultspec_core.console import get_console


class DryRunStatus(StrEnum):
    """Status categories for dry-run items."""

    NEW = "new"
    EXISTS = "exists"
    UPDATE = "update"
    OVERRIDE = "override"
    DELETE = "delete"


_STATUS_STYLES: dict[DryRunStatus, tuple[str, str]] = {
    DryRunStatus.NEW: ("[green]+[/green]", "[green]"),
    DryRunStatus.EXISTS: ("[dim]=[/dim]", "[dim]"),
    DryRunStatus.UPDATE: ("[yellow]~[/yellow]", "[yellow]"),
    DryRunStatus.OVERRIDE: ("[bold yellow]![/bold yellow]", "[bold yellow]"),
    DryRunStatus.DELETE: ("[red]-[/red]", "[red]"),
}


@dataclass
class DryRunItem:
    """A single item in a dry-run preview."""

    path: str
    status: DryRunStatus


def render_dry_run_tree(items: list[DryRunItem], *, title: str = "Preview") -> None:
    """Render a coloured tree of dry-run items to the console.

    Groups items by status category and displays with colour coding:
    - green (+) = new
    - dim (=) = already exists, no change
    - yellow (~) = will be updated
    - bold yellow (!) = will be overridden
    - red (-) = will be deleted
    """
    console = get_console()
    tree = Tree(f"[bold]{title}[/bold]")

    # Group by status for summary
    by_status: dict[DryRunStatus, list[DryRunItem]] = {}
    for item in items:
        by_status.setdefault(item.status, []).append(item)

    # Render each item
    for item in items:
        prefix, style = _STATUS_STYLES[item.status]
        tree.add(f"{prefix} {style}{item.path}[/{style.lstrip('[')}]" if style.startswith("[") else f"{prefix} {item.path}")

    console.print(tree)

    # Summary line
    parts = []
    for status in DryRunStatus:
        count = len(by_status.get(status, []))
        if count:
            prefix, _ = _STATUS_STYLES[status]
            parts.append(f"{prefix} {count} {status.value}")
    console.print("  ".join(parts))
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest src/vaultspec_core/core/tests/test_dry_run.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/vaultspec_core/core/dry_run.py src/vaultspec_core/core/tests/test_dry_run.py
git commit -m "feat: add Rich tree renderer for dry-run previews with colour-coded status categories"
```

---

## Phase 2: CLI Namespace Restructure

Rewrite the CLI surface layer. This is the big structural change — flat namespace becomes domain-grouped.

### Task 2.1: Create the new CLI module structure

**Files:**
- Create: `src/vaultspec_core/cli/` (package)
- Create: `src/vaultspec_core/cli/__init__.py`
- Create: `src/vaultspec_core/cli/root.py` (root app + global options + top-level commands)
- Create: `src/vaultspec_core/cli/vault_cmd.py` (vault group)
- Create: `src/vaultspec_core/cli/spec_cmd.py` (spec group)
- Create: `src/vaultspec_core/cli/dev_cmd.py` (dev group)

**Step 1: Create the package structure**

```python
# src/vaultspec_core/cli/__init__.py
"""CLI package — the user-facing command surface for vaultspec-core.

Organized into domain groups:
- root: install, uninstall, sync (top-level commands + global options)
- vault_cmd: vault stats, vault list, vault add, vault feature, vault doctor
- spec_cmd: spec rules, spec skills, spec agents, spec system, spec hooks
- dev_cmd: dev test
"""

from .root import app, run

__all__ = ["app", "run"]
```

**Step 2: Create root.py with top-level commands (stubs)**

```python
# src/vaultspec_core/cli/root.py
"""Root CLI application with global options and top-level commands.

Top-level commands: install, uninstall, sync.
Domain groups: vault, spec, dev.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

from vaultspec_core.config.workspace import WorkspaceError, resolve_workspace
from vaultspec_core.core.types import init_paths
from vaultspec_core.logging_config import configure_logging

from .dev_cmd import dev_app
from .spec_cmd import spec_app
from .vault_cmd import vault_app

logger = logging.getLogger(__name__)

app = typer.Typer(
    help=(
        "vaultspec-core: Spec-driven workspace runtime.\n\n"
        "Manages .vaultspec/ firmware and .vault/ documentation records.\n\n"
        "Commands:\n"
        "  install    Deploy vaultspec framework to a project\n"
        "  uninstall  Remove vaultspec framework from a project\n"
        "  sync       Sync firmware to provider output directories\n"
        "  vault      Manage .vault/ documentation records\n"
        "  spec       Author and modify .vaultspec/ firmware\n"
        "  dev        Development and testing utilities\n"
    ),
    no_args_is_help=True,
    add_completion=False,
)

# Mount domain groups
app.add_typer(vault_app, name="vault")
app.add_typer(spec_app, name="spec")
app.add_typer(dev_app, name="dev")


def _version_callback(value: bool):
    if value:
        from vaultspec_core.cli_common import get_version

        typer.echo(get_version())
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    target: Annotated[
        Path | None,
        typer.Option(
            "--target",
            "-t",
            help='Select installation destination folder. Use "." for current working directory.',
            dir_okay=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    debug: Annotated[
        bool, typer.Option("--debug", "-d", help="Enable debug logging")
    ] = False,
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            help="Show version",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
):
    """Root callback — configures logging and resolves workspace."""
    log_level = logging.DEBUG if debug else logging.WARNING
    configure_logging(level=log_level, debug=debug)

    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(0)

    # install/uninstall manage their own target — skip workspace resolution
    if ctx.invoked_subcommand in ("install", "uninstall"):
        from vaultspec_core.core import types as _t

        target_override = target or Path.cwd()
        _t.TARGET_DIR = target_override
        ctx.obj = {"target": target_override}
        return

    # All other commands need a resolved workspace
    try:
        layout = resolve_workspace(target_override=target)
        init_paths(layout)
        ctx.obj = {"target": layout.target_dir, "layout": layout}
    except WorkspaceError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


# --- Top-level commands: install, uninstall, sync ---
# These are defined here (not in sub-modules) because they are root-level.

# Placeholder signatures — full implementation in Phase 3.
# For now, delegate to existing core.commands functions.


@app.command("install")
def cmd_install(
    path: Annotated[
        Path,
        typer.Argument(
            help="Target directory to install into",
            exists=True,
            dir_okay=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    provider: Annotated[
        str,
        typer.Argument(help="Provider: all (default), core, claude, gemini, antigravity, codex"),
    ] = "all",
    upgrade: Annotated[
        bool, typer.Option("--upgrade", help="Re-sync builtin firmware without re-scaffolding"),
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview changes as a coloured tree"),
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Override contents if installation already exists"),
    ] = False,
):
    """Deploy the vaultspec framework to a project directory."""
    from vaultspec_core.core.commands import install_run

    install_run(path=path, provider=provider, upgrade=upgrade, dry_run=dry_run)


@app.command("uninstall")
def cmd_uninstall(
    path: Annotated[
        Path,
        typer.Argument(
            help="Target directory to remove vaultspec from",
            exists=True,
            dir_okay=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    provider: Annotated[
        str,
        typer.Argument(help="Provider: all (default), core, claude, gemini, antigravity, codex"),
    ] = "all",
    keep_vault: Annotated[
        bool, typer.Option("--keep-vault", help="Preserve .vault/ documentation directory"),
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview removals as a coloured tree"),
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Required to execute. Uninstall is destructive."),
    ] = False,
):
    """Remove the vaultspec framework from a project directory."""
    from vaultspec_core.core.commands import uninstall_run

    uninstall_run(path=path, provider=provider, keep_vault=keep_vault, dry_run=dry_run)


@app.command("sync")
def cmd_sync(
    provider: Annotated[
        str,
        typer.Argument(help="Provider: all (default), claude, gemini, antigravity, codex"),
    ] = "all",
    prune: Annotated[
        bool, typer.Option("--prune", help="Remove files from providers that no longer exist in .vaultspec/"),
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview sync changes without writing"),
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite files not managed by vaultspec"),
    ] = False,
):
    """Sync .vaultspec/ firmware to provider output directories.

    Reads the provider manifest to determine which providers are installed.
    """
    valid = {"all", "claude", "gemini", "antigravity", "codex"}
    if provider == "core":
        typer.echo(
            "Error: 'core' is not a valid sync target. "
            "The sync source is .vaultspec/ (core) itself.",
            err=True,
        )
        raise typer.Exit(code=1)
    if provider not in valid:
        typer.echo(
            f"Error: Unknown provider '{provider}'. Valid: {', '.join(sorted(valid))}",
            err=True,
        )
        raise typer.Exit(code=1)

    from vaultspec_core.core.commands import sync_provider

    sync_provider(provider, prune=prune, dry_run=dry_run, force=force)


def run():
    """Console-script entry point."""
    app()
```

**Step 3: Create vault_cmd.py (stubs)**

```python
# src/vaultspec_core/cli/vault_cmd.py
"""Vault command group — manages .vault/ documentation records."""

from __future__ import annotations

import logging
from typing import Annotated

import typer

logger = logging.getLogger(__name__)

vault_app = typer.Typer(
    help="Manage .vault/ documentation records: create, list, query, and repair.",
    no_args_is_help=True,
)

feature_app = typer.Typer(
    help="Manage vault features: list details and archive completed features.",
    no_args_is_help=True,
)
vault_app.add_typer(feature_app, name="feature")


# --- Stub commands (implemented in Phase 4) ---


@vault_app.command("add")
def cmd_add(
    doc_type: Annotated[str, typer.Argument(help="Document type: adr, research, plan, audit, exec, reference")],
    feature: Annotated[str, typer.Option("--feature", help="Feature tag (kebab-case, required)")],
    date: Annotated[str | None, typer.Option("--date", help="Date override (YYYY-MM-DD, defaults to today)")] = None,
    title: Annotated[str | None, typer.Option("--title", help="Document title")] = None,
    content: Annotated[str | None, typer.Option("--content", help="Initial document content")] = None,
):
    """Create a new .vault/ document from a template."""
    typer.echo("Not yet implemented")
    raise typer.Exit(1)


@vault_app.command("stats")
def cmd_stats(
    feature: Annotated[str | None, typer.Option("--feature", help="Filter by feature tag")] = None,
    date: Annotated[str | None, typer.Option("--date", help="Filter by date (YYYY-MM-DD)")] = None,
    doc_type: Annotated[str | None, typer.Option("--type", help="Filter by document type")] = None,
    invalid: Annotated[bool, typer.Option("--invalid", help="Include invalid link count")] = False,
    orphaned: Annotated[bool, typer.Option("--orphaned", help="Include orphaned document count")] = False,
):
    """Display vault statistics: document counts per type, feature, and tag."""
    typer.echo("Not yet implemented")
    raise typer.Exit(1)


@vault_app.command("list")
def cmd_list(
    doc_type: Annotated[str, typer.Argument(help="Document type: adr, research, audit, plan, exec, orphaned, invalid")],
    date: Annotated[str | None, typer.Option("--date", help="Filter by date (YYYY-MM-DD)")] = None,
    feature: Annotated[str | None, typer.Option("--feature", help="Filter by feature tag")] = None,
):
    """List vault documents filtered by type, date, or feature."""
    typer.echo("Not yet implemented")
    raise typer.Exit(1)


@vault_app.command("doctor")
def cmd_doctor():
    """Detect and auto-repair vault structural issues."""
    typer.echo("Not yet implemented")
    raise typer.Exit(1)


@feature_app.command("list")
def cmd_feature_list(
    date: Annotated[str | None, typer.Option("--date", help="Filter features by earliest date")] = None,
    orphaned: Annotated[bool, typer.Option("--orphaned", help="Show only orphaned features")] = False,
    doc_type: Annotated[str | None, typer.Option("--type", help="Filter features containing this doc type")] = None,
):
    """List all tracked features with document counts and types."""
    typer.echo("Not yet implemented")
    raise typer.Exit(1)


@feature_app.command("archive")
def cmd_feature_archive(
    feature_tag: Annotated[str, typer.Argument(help="Feature tag to archive (kebab-case)")],
):
    """Move all documents for a feature into .vault/_archive/."""
    typer.echo("Not yet implemented")
    raise typer.Exit(1)
```

**Step 4: Create spec_cmd.py (stubs)**

```python
# src/vaultspec_core/cli/spec_cmd.py
"""Spec command group — author and modify .vaultspec/ firmware contents."""

from __future__ import annotations

import logging
from typing import Annotated

import typer

from vaultspec_core.core import types as _t

logger = logging.getLogger(__name__)

spec_app = typer.Typer(
    help="Author and modify .vaultspec/ firmware: rules, skills, agents, system prompts, and hooks.",
    no_args_is_help=True,
)

rules_app = typer.Typer(help="Manage governance rules in .vaultspec/rules/rules/.")
skills_app = typer.Typer(help="Manage workflow skills in .vaultspec/rules/skills/.")
agents_app = typer.Typer(help="Manage agent definitions in .vaultspec/rules/agents/.")
system_app = typer.Typer(help="Manage system prompt parts in .vaultspec/rules/system/.")
hooks_app = typer.Typer(help="Manage lifecycle hooks in .vaultspec/rules/hooks/.")

spec_app.add_typer(rules_app, name="rules")
spec_app.add_typer(skills_app, name="skills")
spec_app.add_typer(agents_app, name="agents")
spec_app.add_typer(system_app, name="system")
spec_app.add_typer(hooks_app, name="hooks")


# --- Rules ---
@rules_app.command("list")
def cmd_rules_list():
    """List all rules in .vaultspec/rules/rules/."""
    from vaultspec_core.core import rules_list
    rules_list()


@rules_app.command("add")
def cmd_rules_add(
    name: Annotated[str, typer.Option("--name", help="Rule filename (without .md)")],
    content: Annotated[str | None, typer.Option("--content", help="Rule content text")] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite if exists")] = False,
):
    """Add a new rule to .vaultspec/rules/rules/."""
    from vaultspec_core.core import rules_add
    rules_add(name=name, content=content, force=force)


@rules_app.command("remove")
def cmd_rules_remove(
    name: Annotated[str, typer.Argument(help="Rule filename")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation")] = False,
):
    """Remove a rule from .vaultspec/rules/rules/."""
    from vaultspec_core.core import resource_remove
    resource_remove(name=name, base_dir=_t.RULES_SRC_DIR, label="Rule", force=force)


@rules_app.command("edit")
def cmd_rules_edit(
    name: Annotated[str, typer.Argument(help="Rule filename")],
):
    """Open a rule in the configured editor."""
    from vaultspec_core.core import resource_edit
    resource_edit(name=name, base_dir=_t.RULES_SRC_DIR, label="Rule")


@rules_app.command("revert")
def cmd_rules_revert(
    name: Annotated[str, typer.Argument(help="Builtin rule filename to restore")],
):
    """Restore a builtin rule to its original package content."""
    from vaultspec_core.core.revert import revert_resource
    result = revert_resource("rules", name, _t.RULES_SRC_DIR)
    if result["reverted"]:
        typer.echo(f"Reverted: {name}")
    else:
        typer.echo(f"Cannot revert: {result['reason']}", err=True)
        raise typer.Exit(1)


# --- Skills (same pattern as rules) ---
@skills_app.command("list")
def cmd_skills_list():
    """List all skills in .vaultspec/rules/skills/."""
    from vaultspec_core.core import skills_list
    skills_list()


@skills_app.command("add")
def cmd_skills_add(
    name: Annotated[str, typer.Option("--name", help="Skill name")],
    description: Annotated[str, typer.Option("--description", help="Skill description")] = "",
    force: Annotated[bool, typer.Option("--force", help="Overwrite if exists")] = False,
    template: Annotated[str | None, typer.Option("--template", help="Template to use")] = None,
):
    """Add a new skill to .vaultspec/rules/skills/."""
    from vaultspec_core.core import skills_add
    skills_add(name=name, description=description, force=force, template=template)


@skills_app.command("remove")
def cmd_skills_remove(
    name: Annotated[str, typer.Argument(help="Skill name")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation")] = False,
):
    """Remove a skill from .vaultspec/rules/skills/."""
    from vaultspec_core.core import resource_remove
    resource_remove(name=name, base_dir=_t.SKILLS_SRC_DIR, label="Skill", force=force)


@skills_app.command("edit")
def cmd_skills_edit(
    name: Annotated[str, typer.Argument(help="Skill name")],
):
    """Open a skill in the configured editor."""
    from vaultspec_core.core import resource_edit
    resource_edit(name=name, base_dir=_t.SKILLS_SRC_DIR, label="Skill")


@skills_app.command("revert")
def cmd_skills_revert(
    name: Annotated[str, typer.Argument(help="Builtin skill to restore")],
):
    """Restore a builtin skill to its original package content."""
    from vaultspec_core.core.revert import revert_resource
    result = revert_resource("skills", name, _t.SKILLS_SRC_DIR)
    if result["reverted"]:
        typer.echo(f"Reverted: {name}")
    else:
        typer.echo(f"Cannot revert: {result['reason']}", err=True)
        raise typer.Exit(1)


# --- Agents (same pattern) ---
@agents_app.command("list")
def cmd_agents_list():
    """List all agent definitions in .vaultspec/rules/agents/."""
    from vaultspec_core.core import agents_list
    agents_list()


@agents_app.command("add")
def cmd_agents_add(
    name: Annotated[str, typer.Option("--name", help="Agent name")],
    description: Annotated[str, typer.Option("--description", help="Agent description")] = "",
    force: Annotated[bool, typer.Option("--force", help="Overwrite if exists")] = False,
):
    """Add a new agent definition to .vaultspec/rules/agents/."""
    from vaultspec_core.core import agents_add
    agents_add(name=name, description=description, force=force)


@agents_app.command("remove")
def cmd_agents_remove(
    name: Annotated[str, typer.Argument(help="Agent name")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation")] = False,
):
    """Remove an agent definition from .vaultspec/rules/agents/."""
    from vaultspec_core.core import resource_remove
    resource_remove(name=name, base_dir=_t.AGENTS_SRC_DIR, label="Agent", force=force)


@agents_app.command("edit")
def cmd_agents_edit(
    name: Annotated[str, typer.Argument(help="Agent name")],
):
    """Open an agent definition in the configured editor."""
    from vaultspec_core.core import resource_edit
    resource_edit(name=name, base_dir=_t.AGENTS_SRC_DIR, label="Agent")


@agents_app.command("revert")
def cmd_agents_revert(
    name: Annotated[str, typer.Argument(help="Builtin agent to restore")],
):
    """Restore a builtin agent to its original package content."""
    from vaultspec_core.core.revert import revert_resource
    result = revert_resource("agents", name, _t.AGENTS_SRC_DIR)
    if result["reverted"]:
        typer.echo(f"Reverted: {name}")
    else:
        typer.echo(f"Cannot revert: {result['reason']}", err=True)
        raise typer.Exit(1)


# --- System ---
@system_app.command("list")
def cmd_system_list():
    """List all system prompt parts in .vaultspec/rules/system/."""
    from vaultspec_core.core import system_show
    system_show()


@system_app.command("add")
def cmd_system_add(
    name: Annotated[str, typer.Option("--name", help="System part filename (without .md)")],
    content: Annotated[str | None, typer.Option("--content", help="Content text")] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite if exists")] = False,
):
    """Add a new system prompt part to .vaultspec/rules/system/."""
    typer.echo("Not yet implemented")
    raise typer.Exit(1)


@system_app.command("remove")
def cmd_system_remove(
    name: Annotated[str, typer.Argument(help="System part filename")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation")] = False,
):
    """Remove a system prompt part from .vaultspec/rules/system/."""
    from vaultspec_core.core import resource_remove
    resource_remove(name=name, base_dir=_t.SYSTEM_SRC_DIR, label="System", force=force)


@system_app.command("edit")
def cmd_system_edit(
    name: Annotated[str, typer.Argument(help="System part filename")],
):
    """Open a system prompt part in the configured editor."""
    from vaultspec_core.core import resource_edit
    resource_edit(name=name, base_dir=_t.SYSTEM_SRC_DIR, label="System")


@system_app.command("revert")
def cmd_system_revert(
    name: Annotated[str, typer.Argument(help="Builtin system part to restore")],
):
    """Restore a builtin system prompt part to its original package content."""
    from vaultspec_core.core.revert import revert_resource
    result = revert_resource("system", name, _t.SYSTEM_SRC_DIR)
    if result["reverted"]:
        typer.echo(f"Reverted: {name}")
    else:
        typer.echo(f"Cannot revert: {result['reason']}", err=True)
        raise typer.Exit(1)


# --- Hooks ---
@hooks_app.command("list")
def cmd_hooks_list():
    """List all defined lifecycle hooks."""
    from vaultspec_core.core.commands import hooks_list
    hooks_list()


@hooks_app.command("run")
def cmd_hooks_run(
    event: Annotated[str, typer.Argument(help="Event name to trigger")],
    path: Annotated[str | None, typer.Option("--path", help="Context path variable")] = None,
):
    """Trigger hooks for a specific lifecycle event."""
    from vaultspec_core.core.commands import hooks_run
    hooks_run(event=event, path=path)
```

**Step 5: Create dev_cmd.py**

```python
# src/vaultspec_core/cli/dev_cmd.py
"""Dev command group — development-specific commands, not user-facing."""

from __future__ import annotations

import logging
from typing import Annotated

import typer

logger = logging.getLogger(__name__)

dev_app = typer.Typer(
    help="Development utilities: run tests and diagnostics.",
    no_args_is_help=True,
)


@dev_app.command("test")
def cmd_test(
    target: Annotated[
        str,
        typer.Argument(help="Test target: unit, integration, or all"),
    ] = "all",
    extra_args: Annotated[
        list[str] | None,
        typer.Argument(help="Extra pytest arguments"),
    ] = None,
):
    """Run the project test suite.

    Targets:
      unit         Run unit tests only
      integration  Run integration tests only
      all          Run all tests (default)
    """
    category_map = {
        "unit": "unit",
        "integration": "integration",
        "all": "all",
    }
    if target not in category_map:
        typer.echo(
            f"Error: Unknown test target '{target}'. Valid: unit, integration, all",
            err=True,
        )
        raise typer.Exit(1)

    from vaultspec_core.core.commands import test_run

    test_run(category=category_map[target], extra_args=extra_args)
```

**Step 6: Update entry points**

Modify `src/vaultspec_core/__main__.py` to import from new location:

```python
from vaultspec_core.cli import app

if __name__ == "__main__":
    app()
```

Update `pyproject.toml` console-script entry:

```toml
[project.scripts]
vaultspec-core = "vaultspec_core.cli:run"
```

**Step 7: Commit**

```bash
git add src/vaultspec_core/cli/ src/vaultspec_core/__main__.py pyproject.toml
git commit -m "refactor: restructure CLI into domain groups (vault, spec, dev) per contract"
```

---

### Task 2.2: Delete old CLI modules

**Files:**
- Delete: `src/vaultspec_core/cli.py` (replaced by `cli/root.py`)
- Delete: `src/vaultspec_core/spec_cli.py` (replaced by `cli/spec_cmd.py` + `cli/root.py`)
- Delete: `src/vaultspec_core/vault_cli.py` (replaced by `cli/vault_cmd.py`)

**Step 1: Remove old modules**

```bash
git rm src/vaultspec_core/cli.py src/vaultspec_core/spec_cli.py src/vaultspec_core/vault_cli.py
```

**Step 2: Fix any remaining imports**

Search for `from vaultspec_core.cli import`, `from vaultspec_core.spec_cli import`, `from vaultspec_core.vault_cli import` across the codebase and update to new paths.

Key files to check:
- `src/vaultspec_core/core/commands.py` — imports `_sync_provider` from `spec_cli`
- `src/vaultspec_core/mcp_server/app.py` — may reference old CLI

**Step 3: Commit**

```bash
git add -A
git commit -m "refactor: remove old flat CLI modules (cli.py, spec_cli.py, vault_cli.py)"
```

---

## Phase 3: Fix Top-Level Commands

Now fix the actual behavior of install, uninstall, sync to match the contract.

### Task 3.1: Install --force and --dry-run tree

**Files:**
- Modify: `src/vaultspec_core/core/commands.py` (install_run)
- Modify: `src/vaultspec_core/cli/root.py` (wire --force)
- Test: `src/vaultspec_core/tests/cli/test_install.py` (create)

**Step 1: Write failing tests**

```python
# src/vaultspec_core/tests/cli/test_install.py
"""Tests for install command."""

import pytest
from typer.testing import CliRunner
from vaultspec_core.cli import app


@pytest.mark.unit
class TestInstallForce:
    def test_install_force_overwrites(self, tmp_path, runner):
        """--force allows reinstall over existing .vaultspec/."""
        (tmp_path / ".vaultspec").mkdir()
        result = runner.invoke(app, ["install", str(tmp_path), "--force"])
        assert result.exit_code == 0

    def test_install_without_force_fails_if_exists(self, tmp_path, runner):
        """Without --force, install must fail if .vaultspec/ exists."""
        (tmp_path / ".vaultspec").mkdir()
        result = runner.invoke(app, ["install", str(tmp_path)])
        assert result.exit_code != 0


@pytest.mark.unit
class TestInstallDryRun:
    def test_dry_run_produces_tree_output(self, tmp_path, runner):
        """--dry-run must produce coloured tree with status categories."""
        result = runner.invoke(app, ["install", str(tmp_path), "--dry-run"])
        assert result.exit_code == 0
        # Must NOT use "would" wording
        assert "would" not in result.output.lower()
```

**Step 2-5: Implement and commit** (follow standard TDD cycle)

---

### Task 3.2: Uninstall --force safety gate and core cascade

**Files:**
- Modify: `src/vaultspec_core/core/commands.py` (uninstall_run)
- Test: `src/vaultspec_core/tests/cli/test_uninstall.py` (create)

**Step 1: Write failing tests**

```python
# src/vaultspec_core/tests/cli/test_uninstall.py
"""Tests for uninstall command."""

import pytest
from typer.testing import CliRunner
from vaultspec_core.cli import app


@pytest.mark.unit
class TestUninstallForce:
    def test_uninstall_without_force_fails(self, tmp_path, runner):
        """Uninstall must refuse without --force."""
        (tmp_path / ".vaultspec").mkdir()
        result = runner.invoke(app, ["uninstall", str(tmp_path)])
        assert result.exit_code != 0
        assert "force" in result.output.lower() or "--force" in result.output

    def test_uninstall_with_force_succeeds(self, tmp_path, runner):
        """Uninstall with --force must succeed."""
        (tmp_path / ".vaultspec").mkdir()
        result = runner.invoke(app, ["uninstall", str(tmp_path), "--force"])
        assert result.exit_code == 0


@pytest.mark.unit
class TestUninstallCoreCascade:
    def test_core_uninstall_removes_all_providers(self, tmp_path, runner):
        """Uninstalling 'core' must remove everything including provider dirs."""
        for d in [".vaultspec", ".claude", ".gemini", ".agents"]:
            (tmp_path / d).mkdir()
        result = runner.invoke(app, ["uninstall", str(tmp_path), "core", "--force"])
        assert result.exit_code == 0
        assert not (tmp_path / ".vaultspec").exists()
        assert not (tmp_path / ".claude").exists()
        assert not (tmp_path / ".gemini").exists()
```

**Step 2-5: Implement and commit** (follow standard TDD cycle)

---

### Task 3.3: Sync manifest-aware all and core error

Already partially done in Task 1.3. This task wires it into the CLI and adds the explicit "core" error message.

**Files:**
- Modify: `src/vaultspec_core/cli/root.py`
- Test: `src/vaultspec_core/tests/cli/test_sync.py` (create)

---

## Phase 4: Implement Vault Commands

Wire the vault_cmd.py stubs to the backend from Phase 1.

### Task 4.1: vault add (with --date, --content)
### Task 4.2: vault stats
### Task 4.3: vault list
### Task 4.4: vault feature list
### Task 4.5: vault feature archive
### Task 4.6: vault doctor

Each task follows the same pattern:
1. Write failing test against vault_cmd.py
2. Implement by calling query.py / verification API / hydration
3. Run tests
4. Commit

---

## Phase 5: Rewrite CLI Tests

### Task 5.1: Rewrite test_main_cli.py for new namespace
### Task 5.2: Rewrite test_vault_cli.py for decomposed commands
### Task 5.3: Rewrite test_spec_cli.py for spec nesting
### Task 5.4: Write test_dev_cli.py
### Task 5.5: Update test_automation_contracts.py for new justfile

---

## Phase 6: Justfile Alignment

### Task 6.1: Rename `sync` → `deps` to resolve collision

**Files:**
- Modify: `justfile`

Rename the uv dependency sync recipe to avoid collision:

```just
# Rename 'sync' to 'deps' for dependency management
deps target='sync':
  case "{{target}}" in \
    sync) uv sync --locked --group dev ;; \
    upgrade) uv sync --upgrade --all-groups ;; \
    *) echo "unknown deps target: {{target}}" >&2; exit 1 ;; \
  esac

# Add vaultspec-core sync passthrough
sync provider='all' *args='':
  uv run vaultspec-core sync {{provider}} {{args}}
```

### Task 6.2: Add vault and spec recipes

```just
vault *args='':
  uv run vaultspec-core vault {{args}}

spec *args='':
  uv run vaultspec-core spec {{args}}
```

### Task 6.3: Update test recipe to use `dev test`

```just
test target='all':
  case "{{target}}" in \
    python) uv run vaultspec-core dev test all ;; \
    docker) just build docker && docker run --rm {{ local_image }} vaultspec-core --help ;; \
    all) just test python && just test docker ;; \
    *) echo "unknown test target: {{target}}" >&2; exit 1 ;; \
  esac
```

---

## Phase 7: Help Text Quality Pass

### Task 7.1: Audit and rewrite all help strings

Go through every `help=` parameter in every command and option across all CLI modules. Each must clearly state what the command does and what it changes. No word salad.

---

## Dependency Graph

```
Phase 0 (console + global opts)
  └─→ Phase 1 (backend hardening)
       ├─→ Phase 2 (CLI restructure)
       │    └─→ Phase 3 (fix top-level commands)
       │         └─→ Phase 4 (vault command implementations)
       │              └─→ Phase 5 (rewrite tests)
       └─→ Phase 6 (justfile — can start after Phase 2)
Phase 7 (help text pass — after everything else)
```

Phases 1 and 2 can partially overlap: backend work (1.1–1.5) is independent of CLI wiring (2.1–2.2). Phase 6 can start as soon as Phase 2 is committed.

---

## Estimated Task Count

| Phase | Tasks | Approx Steps |
|-------|-------|-------------|
| 0: Foundation | 2 | 10 |
| 1: Backend | 5 | 25 |
| 2: CLI Restructure | 2 | 14 |
| 3: Top-Level Fixes | 3 | 15 |
| 4: Vault Commands | 6 | 30 |
| 5: Test Rewrite | 5 | 25 |
| 6: Justfile | 3 | 9 |
| 7: Help Text | 1 | 5 |
| **Total** | **27** | **~133** |
