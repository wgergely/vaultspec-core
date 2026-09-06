"""Tests for the ``vaultspec-core vault repair`` operator pipeline."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

import pytest

from vaultspec_core.cli import app
from vaultspec_core.cli._repair_render import render_repair_run
from vaultspec_core.config import reset_config
from vaultspec_core.vaultcore.checks import run_all_checks
from vaultspec_core.vaultcore.repair import (
    RepairRun,
    _changed_files,
    _vault_file_fingerprints,
    run_repair_pipeline,
)

if TYPE_CHECKING:
    from pathlib import Path

    from typer.testing import CliRunner

    from vaultspec_core.tests.cli.workspace_factory import WorkspaceFactory

pytestmark = [pytest.mark.unit]


def _write_doc(
    root: Path,
    doc_type: str,
    stem: str,
    feature: str,
    *,
    docs_dir: str = ".vault",
) -> Path:
    path = root / docs_dir / doc_type / f"{stem}-{doc_type}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "tags:\n"
        f"  - '#{doc_type}'\n"
        f"  - '#{feature}'\n"
        "date: '2026-05-15'\n"
        "related: []\n"
        "---\n"
        f"\n# {stem}\n",
        encoding="utf-8",
    )
    return path


def _json_payload(output: str) -> dict[str, Any]:
    assert output.lstrip().startswith("{"), (
        "JSON-mode CLI output must not include human text before the payload:\n"
        f"{output}"
    )
    # Unwrap the cli-json-consistency envelope; repair tests assert on the
    # command's own payload nested under `data`.
    envelope = json.loads(output)
    assert set(envelope) >= {"schema", "status", "data"}, envelope
    return envelope["data"]


def _write_state_mutation_workspace(root: Path) -> None:
    """Create a tmp vault that requires multiple sequential file mutations."""
    research = root / ".vault" / "research" / "2026-05-15-State-Mutation-research.md"
    plan = root / ".vault" / "plan" / "2026-05-15-state-mutation-plan.md"
    adr = root / ".vault" / "adr" / "2026-05-15-state-mutation-adr.md"
    for path in (research, plan, adr):
        path.parent.mkdir(parents=True, exist_ok=True)

    research.write_text(
        "---\n"
        "tags:\n"
        "  - research\n"
        "  - state-mutation\n"
        "date: '2026-05-15'\n"
        "related: []\n"
        "---\n\n# Research\n",
        encoding="utf-8",
    )
    plan.write_text(
        "---\n"
        "tags:\n"
        "  - '#plan'\n"
        "  - '#state-mutation'\n"
        "date: '2026-05-15'\n"
        "related:\n"
        "  - '[[2026-05-15-State-Mutation-research.md]]'\n"
        "  - '[[missing-target]]'\n"
        "---\n\n# Plan\n",
        encoding="utf-8",
    )
    adr.write_text(
        "---\n"
        "tags:\n"
        "  - '#adr'\n"
        "  - '#state-mutation'\n"
        "date: '2026-05-15'\n"
        "related: []\n"
        "---\n\n# `state-mutation` adr: `State Mutation` | (**status:** `accepted`)\n",
        encoding="utf-8",
    )


class TestVaultRepair:
    def test_help_lists_repair_command(
        self,
        factory: WorkspaceFactory,
        runner: CliRunner,
    ) -> None:
        factory.install("core")

        result = runner.invoke(app, ["--target", str(factory.path), "vault", "--help"])

        assert result.exit_code == 0
        assert "repair" in result.output

    def test_growing_sections_carry_their_window(
        self,
        factory: WorkspaceFactory,
    ) -> None:
        """Every section that grows with the repair reports what it withheld.

        The payload previously returned these lists whole while the human
        rendering capped them, so the machine surface was largest exactly when
        the vault was most broken. Each is now a window: the rows, plus the
        total they were cut from and whether more follow.
        """
        factory.install("core")
        _write_doc(
            factory.path,
            "research",
            "2026-05-15-repair-window",
            "repair-window",
        )

        result = factory.run("vault", "repair", "--dry-run", "--json")
        envelope = json.loads(result.output)
        payload = _json_payload(result.output)

        assert envelope["schema"] == "vaultspec.vault.repair.v2"
        for section in (
            "journal",
            "changed_files",
            "generated_indexes",
            "planned_fixes",
            "unresolved",
            "root_causes",
        ):
            assert set(payload[section]) >= {
                "items",
                "returned",
                "total",
                "truncated",
            }, f"{section} is not a window: {payload[section]}"
            assert payload[section]["returned"] == len(payload[section]["items"])
            assert payload[section]["returned"] <= payload[section]["total"]

    def test_nested_diagnostics_are_bounded_too(
        self,
        factory: WorkspaceFactory,
    ) -> None:
        """A bounded row count does not bound a row that holds a collection.

        Root-cause buckets and per-check summaries each embed the diagnostics
        they group. Bounding only the outer list left 99% of a 2.5 MB payload
        in four rows that were never elided, so the nested collections carry
        their own windows.
        """
        factory.install("core")
        _write_doc(
            factory.path,
            "research",
            "2026-05-15-repair-nested",
            "repair-nested",
        )

        payload = _json_payload(
            factory.run("vault", "repair", "--dry-run", "--json").output
        )

        for bucket in payload["root_causes"]["items"]:
            assert set(bucket["diagnostics"]) >= {"items", "returned", "total"}
            assert bucket["diagnostics"]["returned"] <= bucket["diagnostics"]["total"]

        for phase in payload["phases"]:
            for check in phase.get("checks", []):
                # Findings are either carried and bounded, or absent and said
                # to be absent. A checker that silently omitted them would be
                # indistinguishable from one that found nothing.
                if "diagnostics" in check:
                    assert set(check["diagnostics"]) >= {
                        "items",
                        "returned",
                        "total",
                    }
                else:
                    assert check["diagnostics_omitted"], check
                    assert {"errors", "warnings", "info"} <= set(check), check

    def test_dry_run_reports_index_plan_without_writing(
        self,
        factory: WorkspaceFactory,
    ) -> None:
        factory.install("core")
        _write_doc(
            factory.path,
            "research",
            "2026-05-15-repair-dry-run",
            "repair-dry-run",
        )
        index_path = factory.path / ".vault" / "index" / "repair-dry-run.index.md"

        result = factory.run(
            "vault",
            "repair",
            "--feature",
            "repair-dry-run",
            "--dry-run",
            "--json",
        )
        payload = _json_payload(result.output)

        assert result.exit_code == 0
        assert payload["dry_run"] is True
        assert payload["changed_files"]["items"] == []
        assert (
            ".vault/index/repair-dry-run.index.md"
            in payload["generated_indexes"]["items"]
        )
        assert not index_path.exists()

    def test_repair_refreshes_feature_index(
        self,
        factory: WorkspaceFactory,
    ) -> None:
        factory.install("core")
        _write_doc(
            factory.path,
            "research",
            "2026-05-15-repair-index",
            "repair-index",
        )
        index_path = factory.path / ".vault" / "index" / "repair-index.index.md"

        result = factory.run(
            "vault",
            "repair",
            "--feature",
            "repair-index",
            "--json",
        )
        payload = _json_payload(result.output)

        assert result.exit_code == 0
        assert index_path.exists()
        assert (
            ".vault/index/repair-index.index.md"
            in payload["generated_indexes"]["items"]
        )
        assert ".vault/index/repair-index.index.md" in payload["changed_files"]["items"]

    def test_repair_does_not_report_unchanged_index_as_modified(
        self,
        factory: WorkspaceFactory,
    ) -> None:
        factory.install("core")
        _write_doc(
            factory.path,
            "research",
            "2026-05-15-repair-index-stable",
            "repair-index-stable",
        )

        first = run_repair_pipeline(factory.path, feature="repair-index-stable")
        second = run_repair_pipeline(factory.path, feature="repair-index-stable")

        index_rel = ".vault/index/repair-index-stable.index.md"
        assert index_rel in first.changed_files
        assert index_rel not in second.changed_files

    def test_repair_tracks_changed_indexes_in_configured_docs_dir(
        self,
        factory: WorkspaceFactory,
    ) -> None:
        old_docs_dir = os.environ.get("VAULTSPEC_DOCS_DIR")
        os.environ["VAULTSPEC_DOCS_DIR"] = "notes"
        reset_config()
        try:
            factory.install("core")
            _write_doc(
                factory.path,
                "research",
                "2026-05-15-repair-custom-docs",
                "repair-custom-docs",
                docs_dir="notes",
            )
            index_path = (
                factory.path / "notes" / "index" / "repair-custom-docs.index.md"
            )

            run = run_repair_pipeline(factory.path, feature="repair-custom-docs")

            assert index_path.exists()
            assert "notes/index/repair-custom-docs.index.md" in run.generated_indexes
            assert "notes/index/repair-custom-docs.index.md" in run.changed_files
        finally:
            if old_docs_dir is None:
                os.environ.pop("VAULTSPEC_DOCS_DIR", None)
            else:
                os.environ["VAULTSPEC_DOCS_DIR"] = old_docs_dir
            reset_config()

    def test_repair_rebuilds_snapshot_after_structure_rename(
        self,
        factory: WorkspaceFactory,
    ) -> None:
        factory.install("core")
        upper = (
            factory.path
            / ".vault"
            / "research"
            / "2026-05-15-Repair-Stale-Snapshot-research.md"
        )
        lower = (
            factory.path
            / ".vault"
            / "research"
            / "2026-05-15-repair-stale-snapshot-research.md"
        )
        upper.parent.mkdir(parents=True, exist_ok=True)
        upper.write_text(
            "---\n"
            "tags:\n"
            "  - research\n"
            "  - repair-stale-snapshot\n"
            "date: '2026-05-15'\n"
            "related: []\n"
            "---\n\n# Stale Snapshot\n",
            encoding="utf-8",
        )

        result = factory.run(
            "vault",
            "repair",
            "--feature",
            "repair-stale-snapshot",
            "--json",
        )
        payload = _json_payload(result.output)

        assert result.exit_code == 0, result.output
        assert lower.exists()
        repaired = lower.read_text(encoding="utf-8")
        assert "#research" in repaired
        assert "#repair-stale-snapshot" in repaired
        assert payload["fixed_count"] >= 2

    def test_repair_strips_template_annotations(
        self,
        factory: WorkspaceFactory,
    ) -> None:
        factory.install("core")
        doc = _write_doc(
            factory.path,
            "research",
            "2026-05-15-repair-annotations",
            "repair-annotations",
        )
        annotated = doc.read_text(encoding="utf-8").replace(
            "---\n\n# 2026-05-15-repair-annotations\n",
            "---\n\n<!-- Fill this generated scaffold. -->\n\n"
            "# 2026-05-15-repair-annotations\n",
        )
        doc.write_text(annotated, encoding="utf-8")

        result = factory.run(
            "vault",
            "repair",
            "--feature",
            "repair-annotations",
            "--no-index",
            "--json",
        )
        payload = _json_payload(result.output)

        assert result.exit_code == 0, result.output
        assert payload["fixed_count"] >= 1
        assert "<!-- Fill this generated scaffold. -->" not in doc.read_text(
            encoding="utf-8"
        )

    def test_sanitize_annotations_command_strips_without_index_refresh(
        self,
        factory: WorkspaceFactory,
    ) -> None:
        factory.install("core")
        doc = _write_doc(
            factory.path,
            "research",
            "2026-05-15-sanitize-command",
            "sanitize-command",
        )
        doc.write_text(
            doc.read_text(encoding="utf-8")
            + "\n<!-- Remove this generated annotation. -->\n",
            encoding="utf-8",
        )
        index_path = factory.path / ".vault" / "index" / "sanitize-command.index.md"

        result = factory.run(
            "vault",
            "sanitize",
            "annotations",
            "--feature",
            "sanitize-command",
            "--json",
        )
        payload = json.loads(result.output)["data"]

        assert result.exit_code == 0, result.output
        assert payload["fixed_count"] == 1
        assert not index_path.exists()
        assert "<!-- Remove this generated annotation. -->" not in doc.read_text(
            encoding="utf-8"
        )

    def test_sanitize_annotations_dry_run_does_not_strip(
        self,
        factory: WorkspaceFactory,
    ) -> None:
        factory.install("core")
        doc = _write_doc(
            factory.path,
            "research",
            "2026-05-15-sanitize-dry-run",
            "sanitize-dry-run",
        )
        doc.write_text(
            doc.read_text(encoding="utf-8")
            + "\n<!-- Preview this generated annotation. -->\n",
            encoding="utf-8",
        )

        result = factory.run(
            "vault",
            "sanitize",
            "annotations",
            "--feature",
            "sanitize-dry-run",
            "--dry-run",
            "--json",
        )
        payload = json.loads(result.output)["data"]

        assert result.exit_code == 0
        assert payload["fixed_count"] == 0
        diagnostics = payload["diagnostics"]["items"]
        assert sum(1 for diag in diagnostics if diag["severity"] == "warning") == 1
        assert "Would remove template annotations" in diagnostics[0]["message"]
        assert "<!-- Preview this generated annotation. -->" in doc.read_text(
            encoding="utf-8"
        )

    def test_check_all_fix_synchronizes_graph_after_cascaded_mutations(
        self,
        tmp_path: Path,
    ) -> None:
        root = tmp_path / "dummy-repo"
        root.mkdir()
        _write_state_mutation_workspace(root)

        results = run_all_checks(root, feature="state-mutation", fix=True)
        postcheck = run_all_checks(root, feature="state-mutation", fix=False)

        lower_research = (
            root / ".vault" / "research" / "2026-05-15-state-mutation-research.md"
        )
        upper_research = (
            root / ".vault" / "research" / "2026-05-15-State-Mutation-research.md"
        )
        plan = root / ".vault" / "plan" / "2026-05-15-state-mutation-plan.md"
        adr = root / ".vault" / "adr" / "2026-05-15-state-mutation-adr.md"

        assert sum(result.fixed_count for result in results) >= 6
        research_names = {path.name for path in lower_research.parent.iterdir()}
        assert lower_research.name in research_names
        assert upper_research.name not in research_names
        lower_text = lower_research.read_text(encoding="utf-8")
        assert "#research" in lower_text
        assert "#state-mutation" in lower_text

        plan_text = plan.read_text(encoding="utf-8")
        assert ".md]]" not in plan_text
        assert "[[missing-target]]" not in plan_text
        assert "[[2026-05-15-state-mutation-research]]" in plan_text
        assert "[[2026-05-15-state-mutation-adr]]" in plan_text
        assert "[[2026-05-15-state-mutation-research]]" in adr.read_text(
            encoding="utf-8"
        )
        assert all(result.error_count == 0 for result in postcheck)
        postcheck_warnings = [
            diag.message
            for result in postcheck
            for diag in result.diagnostics
            if diag.severity == "warning"
        ]
        # The fixture is deliberately legacy-shaped: its documents predate the
        # body_schema declaration and declare none. Undeclared provenance with
        # no ledger entry makes no claim, so it is silent rather than a
        # warning; only the missing feature index survives repair.
        assert postcheck_warnings == [
            "Feature 'state-mutation' has no feature index. Run "
            "vaultspec-core vault feature index to generate "
            "index/state-mutation.index.md",
        ]

    def test_repair_changed_files_tracks_cascaded_tmp_workspace_mutations(
        self,
        tmp_path: Path,
    ) -> None:
        root = tmp_path / "dummy-repo"
        root.mkdir()
        _write_state_mutation_workspace(root)

        run = run_repair_pipeline(
            root,
            feature="state-mutation",
            include_index=True,
        )

        assert run.error_count == 0
        # Repair generates the feature index, and the fixture's legacy-shaped
        # documents declare no body_schema and have no ledger entry - an
        # undeclared claim, so no warning remains once the index exists.
        residual_warnings = [
            diag.message
            for result in run.postcheck
            for diag in result.diagnostics
            if diag.severity == "warning"
        ]
        assert residual_warnings == []
        assert ".vault/plan/2026-05-15-state-mutation-plan.md" in run.changed_files
        assert ".vault/adr/2026-05-15-state-mutation-adr.md" in run.changed_files
        assert (
            ".vault/research/2026-05-15-State-Mutation-research.md" in run.changed_files
        )
        assert (
            ".vault/research/2026-05-15-state-mutation-research.md" in run.changed_files
        )
        assert ".vault/index/state-mutation.index.md" in run.changed_files

    def test_repair_fingerprints_skip_internal_vault_directories(
        self,
        tmp_path: Path,
    ) -> None:
        root = tmp_path / "dummy-repo"
        root.mkdir()
        _write_doc(root, "research", "2026-05-15-visible", "visible")
        for rel_path in (
            ".vault/.obsidian/state.md",
            ".vault/.trash/deleted.md",
            ".vault/data/cache.md",
            ".vault/logs/trace.md",
            ".vault/_archive/old.md",
        ):
            path = root / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# internal\n", encoding="utf-8")

        fingerprints = _vault_file_fingerprints(root)

        assert ".vault/research/2026-05-15-visible-research.md" in fingerprints
        assert all("obsidian" not in path for path in fingerprints)
        assert all(".trash" not in path for path in fingerprints)
        assert all("/data/" not in path for path in fingerprints)
        assert all("/logs/" not in path for path in fingerprints)
        assert all("_archive" not in path for path in fingerprints)

    def test_fingerprints_detect_same_size_same_tick_content_change(
        self,
        tmp_path: Path,
    ) -> None:
        """Size and mtime alone cannot see a fixed-width rewrite.

        Rewriting the ``modified: 'yyyy-mm-dd'`` frontmatter stamp - the
        single most common repair-pipeline mutation - never changes
        ``st_size``, since the canonical value is always a 12-byte quoted
        date. If that rewrite also lands within the same mtime tick as the
        prior stat (ordinary on this project's own NTFS volume under a
        fast successive-write loop, not just a theoretical FAT/exFAT
        concern), a ``(size, mtime_ns)``-only fingerprint cannot
        distinguish the rewritten file from the original. Force the
        collision deterministically with ``os.utime`` rather than racing
        the clock.
        """
        root = tmp_path / "dummy-repo"
        root.mkdir()
        doc = _write_doc(root, "research", "2026-05-15-collision", "collision")
        frozen_ns = 1_700_000_000_123_456_700
        os.utime(doc, ns=(frozen_ns, frozen_ns))

        before = _vault_file_fingerprints(root)

        content = doc.read_text(encoding="utf-8")
        rewritten = content.replace("date: '2026-05-15'", "date: '2026-05-16'")
        assert len(rewritten) == len(content), "the rewrite must stay same-size"
        doc.write_text(rewritten, encoding="utf-8")
        os.utime(doc, ns=(frozen_ns, frozen_ns))

        after = _vault_file_fingerprints(root)

        rel = ".vault/research/2026-05-15-collision-research.md"
        assert before[rel][0] == after[rel][0], "size must collide for this repro"
        assert before[rel][1] == after[rel][1], "mtime must collide for this repro"
        assert before[rel] != after[rel], "the content hash must still tell them apart"
        assert rel in _changed_files(before, after)

    def test_fingerprints_reuse_prior_hash_when_not_racy(
        self,
        tmp_path: Path,
    ) -> None:
        """A file older than the racy boundary trusts its prior hash.

        Full-hashing every document on every fingerprint capture is too
        expensive to pay several times per repair run (measured ~600ms
        for a single pass over this project's own ~1200-document vault),
        so captures after the first reuse a file's previously-computed
        hash whenever its ``(size, mtime_ns)`` still matches *and* its
        mtime is strictly older than the racy boundary. Feed a
        deliberately wrong prior hash for such a file and confirm it
        passes through unrecomputed - proving the reuse path actually
        fires rather than merely producing an output indistinguishable
        from a fresh hash.
        """
        root = tmp_path / "dummy-repo"
        root.mkdir()
        doc = _write_doc(root, "research", "2026-05-15-reuse", "reuse")
        rel = ".vault/research/2026-05-15-reuse-research.md"
        stat = doc.stat()
        boundary_ns = stat.st_mtime_ns + 1
        previous = {rel: (stat.st_size, stat.st_mtime_ns, "deliberately-wrong-hash")}

        fingerprints = _vault_file_fingerprints(
            root, previous=previous, boundary_ns=boundary_ns
        )

        assert fingerprints[rel][2] == "deliberately-wrong-hash"

    def test_fingerprints_rehash_when_racy(
        self,
        tmp_path: Path,
    ) -> None:
        """A file at or after the racy boundary is always freshly hashed.

        The counterpart to the reuse test: a file whose mtime is not
        strictly older than the boundary might have been rewritten since
        *previous* was captured, so its hash must never be trusted from
        *previous* even when ``(size, mtime_ns)`` still matches.
        """
        root = tmp_path / "dummy-repo"
        root.mkdir()
        doc = _write_doc(root, "research", "2026-05-15-racy", "racy")
        rel = ".vault/research/2026-05-15-racy-research.md"
        stat = doc.stat()
        boundary_ns = stat.st_mtime_ns
        previous = {rel: (stat.st_size, stat.st_mtime_ns, "deliberately-wrong-hash")}

        fingerprints = _vault_file_fingerprints(
            root, previous=previous, boundary_ns=boundary_ns
        )

        assert fingerprints[rel][2] != "deliberately-wrong-hash"

    def test_repair_dry_run_journal_matches_planned_mutation_classes(
        self,
        tmp_path: Path,
    ) -> None:
        root = tmp_path / "dummy-repo"
        root.mkdir()
        _write_state_mutation_workspace(root)

        run = run_repair_pipeline(
            root,
            feature="state-mutation",
            dry_run=True,
            include_index=True,
        )

        assert run.changed_files == []
        assert not (root / ".vault" / "index" / "state-mutation.index.md").exists()
        planned_actions = {
            (entry["phase"], entry["action"], entry["status"]) for entry in run.journal
        }
        assert ("fix", "planned-fix", "planned") in planned_actions
        assert ("index", "refresh-index", "planned") in planned_actions

    def test_repair_reports_partial_failure_when_index_refresh_fails(
        self,
        tmp_path: Path,
    ) -> None:
        root = tmp_path / "dummy-repo"
        root.mkdir()
        _write_state_mutation_workspace(root)
        index_dir_collision = root / ".vault" / "index"
        index_dir_collision.write_text("not a directory", encoding="utf-8")

        run = run_repair_pipeline(
            root,
            feature="state-mutation",
            include_index=True,
        )

        assert run.partial_failure is True
        assert run.error_count >= 1
        assert any(
            entry["phase"] == "index" and entry["status"] == "failed"
            for entry in run.journal
        )
        assert any(item["check"] == "index" for item in run.unresolved)
        assert any(
            phase.get("phase") == "index" and phase.get("failed") is True
            for phase in run.phases
        )
        assert run.generated_indexes == []
        assert index_dir_collision.is_file()

    def test_dry_run_does_not_plan_index_for_unknown_feature(
        self,
        factory: WorkspaceFactory,
    ) -> None:
        factory.install("core")

        result = factory.run(
            "vault",
            "repair",
            "--feature",
            "missing-feature",
            "--dry-run",
            "--json",
        )
        payload = _json_payload(result.output)
        index_phase = next(p for p in payload["phases"] if p["phase"] == "index")

        if result.exit_code != 0:
            print("REPAIR OUTPUT:")
            print(result.output)
        assert result.exit_code == 0
        assert payload["generated_indexes"]["items"] == []
        assert index_phase["planned"] == []

    def test_no_index_skips_generated_artifact_refresh(
        self,
        factory: WorkspaceFactory,
    ) -> None:
        factory.install("core")
        _write_doc(
            factory.path,
            "research",
            "2026-05-15-repair-skip-index",
            "repair-skip-index",
        )
        index_path = factory.path / ".vault" / "index" / "repair-skip-index.index.md"

        result = factory.run(
            "vault",
            "repair",
            "--feature",
            "repair-skip-index",
            "--no-index",
            "--json",
        )
        payload = _json_payload(result.output)
        index_phase = next(p for p in payload["phases"] if p["phase"] == "index")

        assert result.exit_code == 0
        assert index_phase["skipped"] is True
        assert payload["generated_indexes"]["items"] == []
        assert not index_path.exists()

    def test_check_order_and_info_visibility_are_stable(
        self,
        factory: WorkspaceFactory,
    ) -> None:
        factory.install("core")
        _write_doc(
            factory.path,
            "adr",
            "2026-05-15-info-visibility",
            "info-visibility",
        )

        json_result = factory.run("vault", "check", "all", "--json")
        checks = json.loads(json_result.output)["data"]["checks"]
        # ``modified-stamp`` is the last document-scoped checker in both the
        # read-only and the --fix branch: its staleness fingerprint is
        # compared against bodies as the run finally leaves them, so it must
        # follow every checker that rewrites a body (annotations, markdown
        # hygiene, wiki-link repair, the adr-status heading rewrite).
        assert [item["check_name"] for item in checks] == [
            "structure",
            "frontmatter",
            "annotations",
            "markdown",
            "links",
            "dangling",
            "body-links",
            "placeholders",
            "orphans",
            "features",
            "exec-mapping",
            "body-sections",
            "feature-rename-integrity",
            "references",
            "schema",
            "adr-status",
            "modified-stamp",
            "rename-integrity",
            "encoding",
            "foreign",
        ]

        factory.run("vault", "feature", "index", "--feature", "info-visibility")
        default_result = factory.run(
            "vault",
            "check",
            "features",
            "--feature",
            "info-visibility",
        )
        verbose_result = factory.run(
            "vault",
            "check",
            "features",
            "--feature",
            "info-visibility",
            "--verbose",
        )

        assert "research document" not in default_result.output
        assert "research document" in verbose_result.output

    def test_repair_human_output_prioritizes_severity_before_truncating(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run = RepairRun(dry_run=False)
        run.unresolved = [
            {
                "severity": "warning",
                "path": None,
                "message": f"warning {index}",
            }
            for index in range(25)
        ]
        run.unresolved.extend(
            {
                "severity": "info",
                "path": None,
                "message": f"informational {index}",
            }
            for index in range(3)
        )
        run.unresolved.append(
            {
                "severity": "error",
                "path": ".vault/plan/example.md",
                "message": "actionable failure",
            }
        )

        render_repair_run(run)
        captured = capsys.readouterr()
        output = captured.out

        assert captured.err == "", f"unexpected stderr output: {captured.err!r}"
        assert "actionable failure" in output
        assert output.index("actionable failure") < output.index("warning 0")
        assert "warning 20" not in output
        assert "informational 0" not in output
        assert "3 INFO diagnostics hidden" in output
        assert "6 more non-INFO diagnostics" in output

    def test_repair_human_output_counts_hidden_info_when_no_visible_items(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run = RepairRun(dry_run=False)
        run.unresolved = [
            {
                "severity": "info",
                "path": None,
                "message": f"informational {index}",
            }
            for index in range(3)
        ]

        render_repair_run(run)
        captured = capsys.readouterr()
        output = captured.out

        assert captured.err == "", f"unexpected stderr output: {captured.err!r}"
        assert "informational 0" not in output
        assert "3 INFO diagnostics hidden" in output
