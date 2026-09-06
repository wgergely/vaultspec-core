"""Integration tests for the top-level ``status`` CLI verb.

Implements the verification surface for the vault-orientation ADR's
decisions D1, D2, D4, D5, and D7: the rollup mode lists in-flight plans
with open/closed counts and renders documents as stems only; ``--limit``
and ``--since`` change the recent set; the trace mode maps a checked step
to its execution-record stem and reports an open step as having no
record; an unknown target exits 1 naming near-matches; ``--json`` matches
the versioned envelope and carries hints; and hint lines appear in human
output unless suppressed.

Every test drives the real Typer application through ``CliRunner``
against genuine ``.vault/`` documents on the filesystem. There are no
mocks, patches, stubs, or skips: the verb reads real files and the
assertions read the verb's real output. Documents carry deliberately
distinct, stale ``modified:`` stamps so recency ordering and windowing
are observable, non-tautological facts.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from vaultspec_core.cli import app

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration]


def _run(root: Path, *args: str):
    """Invoke the top-level ``status`` verb against *root* via root ``-t``."""
    runner = CliRunner(env={"NO_COLOR": "1"})
    return runner.invoke(app, ["-t", str(root), "status", *args])


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _plan(
    feature: str,
    *,
    date: str,
    modified: str,
    steps: list[tuple[str, bool]],
    related: list[str] | None = None,
    tier: str = "L2",
) -> str:
    """Render a plan with one phase of explicit step rows.

    The declared *tier* defaults to ``L2``; pass a value outside the tier
    enum to write a genuinely malformed plan the parser rejects.
    """
    lines = [
        "---",
        "tags:",
        "  - '#plan'",
        f"  - '#{feature}'",
        f"date: '{date}'",
        f"modified: '{modified}'",
        f"tier: {tier}",
    ]
    if related:
        lines.append("related:")
        lines += [f"  - '[[{r}]]'" for r in related]
    else:
        lines.append("related: []")
    lines += [
        "---",
        "",
        f"# `{feature}` plan",
        "",
        f"{feature} plan body.",
        "",
        "## Phase `P01` - Build",
        "",
        "Phase intent.",
        "",
    ]
    for step_id, checked in steps:
        box = "x" if checked else " "
        lines.append(f"- [{box}] `P01.{step_id}` - do the work; `src/{step_id}.py`.")
    lines.append("")
    return "\n".join(lines)


def _exec(
    feature: str,
    *,
    date: str,
    modified: str,
    step_id: str | None,
    plan_stem: str,
) -> str:
    """Render an execution record, optionally carrying a ``step_id:``."""
    lines = [
        "---",
        "tags:",
        "  - '#exec'",
        f"  - '#{feature}'",
        f"date: '{date}'",
        f"modified: '{modified}'",
    ]
    if step_id is not None:
        lines.append(f"step_id: '{step_id}'")
    lines += [
        "related:",
        f"  - '[[{plan_stem}]]'",
        "---",
        "",
        "Execution details.",
        "",
    ]
    return "\n".join(lines)


def _grounding(
    doc_type: str,
    feature: str,
    *,
    date: str,
    modified: str,
    related: list[str] | None = None,
) -> str:
    """Render a non-plan grounding document (adr, research, reference)."""
    lines = [
        "---",
        "tags:",
        f"  - '#{doc_type}'",
        f"  - '#{feature}'",
        f"date: '{date}'",
        f"modified: '{modified}'",
    ]
    if related:
        lines.append("related:")
        lines += [f"  - '[[{r}]]'" for r in related]
    else:
        lines.append("related: []")
    lines += ["---", "", f"# {feature} {doc_type}", "", "Body.", ""]
    return "\n".join(lines)


def _build_vault(root: Path) -> dict[str, str]:
    """Build one feature vault: research, adr, a plan, and three execs.

    The plan ``S01`` and ``S02`` are closed with matching records, ``S03``
    is open with no record, and one extra exec references the plan without
    a ``step_id:`` (the unlinked bucket). The plan's recency stamp is the
    most recent date so the rollup lists it.
    """
    vault = root / ".vault"
    (root / ".vaultspec").mkdir(parents=True, exist_ok=True)

    feature = "widget"
    plan_stem = f"2026-03-01-{feature}-plan"
    adr_stem = f"2026-02-20-{feature}-adr"
    research_stem = f"2026-02-10-{feature}-research"

    _write(
        vault / "research" / f"{research_stem}.md",
        _grounding("research", feature, date="2026-02-10", modified="2026-02-10"),
    )
    _write(
        vault / "adr" / f"{adr_stem}.md",
        _grounding(
            "adr",
            feature,
            date="2026-02-20",
            modified="2026-02-20",
            related=[research_stem],
        ),
    )
    _write(
        vault / "plan" / f"{plan_stem}.md",
        _plan(
            feature,
            date="2026-03-01",
            modified="2026-03-15",
            steps=[("S01", True), ("S02", True), ("S03", False)],
            related=[adr_stem, research_stem],
        ),
    )
    _write(
        vault / "exec" / f"2026-03-01-{feature}" / f"2026-03-01-{feature}-P01-S01.md",
        _exec(
            feature,
            date="2026-03-02",
            modified="2026-03-02",
            step_id="S01",
            plan_stem=plan_stem,
        ),
    )
    _write(
        vault / "exec" / f"2026-03-01-{feature}" / f"2026-03-01-{feature}-P01-S02.md",
        _exec(
            feature,
            date="2026-03-10",
            modified="2026-03-10",
            step_id="S02",
            plan_stem=plan_stem,
        ),
    )
    _write(
        vault / "exec" / f"2026-03-01-{feature}" / f"2026-03-01-{feature}-orphan.md",
        _exec(
            feature,
            date="2026-03-12",
            modified="2026-03-12",
            step_id=None,
            plan_stem=plan_stem,
        ),
    )

    return {
        "feature": feature,
        "plan": plan_stem,
        "adr": adr_stem,
        "research": research_stem,
        "exec_s01": f"2026-03-01-{feature}-P01-S01",
        "exec_orphan": f"2026-03-01-{feature}-orphan",
    }


# ---------------------------------------------------------------------------
# Rollup mode (decisions D2 / D4 / D7)
# ---------------------------------------------------------------------------


class TestRollup:
    """The no-argument rollup lists in-flight plans as stems plus hints."""

    def test_lists_in_flight_plan_with_counts(self, tmp_path: Path) -> None:
        ids = _build_vault(tmp_path)

        result = _run(tmp_path)

        assert result.exit_code == 0, result.output
        assert "Plans in flight" in result.output
        assert ids["plan"] in result.output
        # The clean plan line renders tier, the step fraction, and the cursor.
        assert "2/3 steps" in result.output
        assert "next P01.S03" in result.output

    def test_renders_stems_only_no_absolute_paths(self, tmp_path: Path) -> None:
        ids = _build_vault(tmp_path)

        result = _run(tmp_path)

        assert result.exit_code == 0, result.output
        # Stems appear; no absolute filesystem path leaks into the output.
        assert ids["plan"] in result.output
        assert ids["research"] in result.output
        assert str(tmp_path) not in result.output
        assert ".vault" not in result.output
        # No path-shaped tokens: a stem like "exec/2026-..." or a backslash
        # path would betray a leaked file path. The completion fraction
        # "2/3" is the only legitimate slash, so assert on the path
        # segments that would accompany a real path instead.
        assert ".md" not in result.output
        assert "exec/" not in result.output
        assert "\\" not in result.output

    def test_limit_narrows_each_type_group(self, tmp_path: Path) -> None:
        ids = _build_vault(tmp_path)
        # A second, older research document. The limit applies per type, so
        # at --limit 1 the research group keeps only its newest member.
        old_research = "2026-01-01-widget-old-research"
        _write(
            tmp_path / ".vault" / "research" / f"{old_research}.md",
            _grounding("research", "widget", date="2026-01-01", modified="2026-01-01"),
        )

        result = _run(tmp_path, "--limit", "1")

        assert result.exit_code == 0, result.output
        recent_block = result.output.split("Active features")[0].split(
            "Recent changes"
        )[1]
        # The newest research survives; the older one is dropped by the cap.
        assert ids["research"] in recent_block
        assert old_research not in recent_block

    def test_since_window_filters_by_day_distance(self, tmp_path: Path) -> None:
        ids = _build_vault(tmp_path)
        # The newest document is the plan at 2026-03-15. A 5-day window
        # anchored on the plan date keeps the plan and excludes the
        # 2026-02-10 research document. The verb anchors --since on today,
        # so seed today far in the future relative to the fixtures by using
        # a window wide enough to include all, then a narrow one to exclude.
        wide = _run(tmp_path, "--since", "100000")
        narrow = _run(tmp_path, "--since", "1")

        assert wide.exit_code == 0, wide.output
        assert narrow.exit_code == 0, narrow.output
        wide_recent = wide.output.split("Active features")[0]
        narrow_recent = narrow.output.split("Active features")[0]
        # The wide window includes the old research document; the 1-day
        # window (all fixtures predate today) excludes everything recent.
        assert ids["research"] in wide_recent
        assert ids["research"] not in narrow_recent

    def test_hints_present_in_human_output(self, tmp_path: Path) -> None:
        _build_vault(tmp_path)

        result = _run(tmp_path)

        assert result.exit_code == 0, result.output
        assert "Next action" in result.output
        assert "vaultspec-core status" in result.output
        assert "vaultspec-core spec doctor" in result.output

    def test_no_hints_suppresses_hint_block(self, tmp_path: Path) -> None:
        _build_vault(tmp_path)

        result = _run(tmp_path, "--no-hints")

        assert result.exit_code == 0, result.output
        assert "Next action" not in result.output

    def test_json_envelope_shape(self, tmp_path: Path) -> None:
        ids = _build_vault(tmp_path)

        result = _run(tmp_path, "--json")

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["schema"] == "vaultspec.vault.status.v1"
        assert payload["status"] == "unchanged"
        data = payload["data"]
        plan_stems = [p["stem"] for p in data["plans_in_flight"]]
        assert ids["plan"] in plan_stems
        in_flight = next(p for p in data["plans_in_flight"] if p["stem"] == ids["plan"])
        assert in_flight["open_steps"] == 1
        assert in_flight["closed_steps"] == 2
        assert in_flight["total_steps"] == 3
        assert "hints" in payload
        commands = [h["command"] for h in payload["hints"]["next_steps"]]
        assert any("vaultspec-core status" in c for c in commands)
        assert any("spec doctor" in c for c in commands)


# ---------------------------------------------------------------------------
# Trace mode (decisions D1 / D5 / D7)
# ---------------------------------------------------------------------------


class TestTrace:
    """A target argument renders the grounding trace for that target."""

    def test_checked_step_maps_to_record_stem(self, tmp_path: Path) -> None:
        ids = _build_vault(tmp_path)

        result = _run(tmp_path, ids["plan"])

        assert result.exit_code == 0, result.output
        assert "Grounding Trace" in result.output
        # The closed S01 step is mapped to its execution-record stem.
        assert ids["exec_s01"] in result.output

    def test_open_step_renders_no_rows(self, tmp_path: Path) -> None:
        ids = _build_vault(tmp_path)

        result = _run(tmp_path, ids["plan"])

        assert result.exit_code == 0, result.output
        # S03 is open and has no ledger rows. The plan-line header also
        # names the cursor ("next P01.S03"), so select the step row by its
        # checkbox glyph rather than the first line mentioning the id.
        s03_line = next(
            line
            for line in result.output.splitlines()
            if "P01.S03" in line and "[ ]" in line
        )
        assert "no rows" in s03_line
        assert "no record" not in result.output

    def test_ledger_mapped_step_renders_rows_and_verify(self, tmp_path: Path) -> None:
        ids = _build_vault(tmp_path)
        feature = ids["feature"]
        _write(
            tmp_path
            / ".vault"
            / "exec"
            / f"2026-03-01-{feature}"
            / f"2026-03-01-{feature}-ledger.md",
            _exec(
                feature,
                date="2026-03-16",
                modified="2026-03-16",
                step_id=None,
                plan_stem=ids["plan"],
            ).replace(
                "Execution details.",
                "## Changes\n\n- `S02` `M` `src/a.py`\n- `S02` `A` `src/b.py`\n"
                "- `S02` `verify:` `pytest` -> `pass`\n",
            ),
        )

        result = _run(tmp_path, ids["plan"])

        assert result.exit_code == 0, result.output
        s02_line = next(
            line
            for line in result.output.splitlines()
            if "P01.S02" in line and "[x]" in line
        )
        assert "ledger 2 rows" in s02_line
        assert "verify:pass" in s02_line

    def test_unlinked_record_is_reported(self, tmp_path: Path) -> None:
        ids = _build_vault(tmp_path)

        result = _run(tmp_path, ids["plan"])

        assert result.exit_code == 0, result.output
        assert "unlinked records" in result.output
        assert ids["exec_orphan"] in result.output

    def test_grounding_documents_grouped_by_type(self, tmp_path: Path) -> None:
        ids = _build_vault(tmp_path)

        result = _run(tmp_path, ids["plan"])

        assert result.exit_code == 0, result.output
        assert "grounding" in result.output
        assert ids["adr"] in result.output
        assert ids["research"] in result.output

    def test_renders_stems_only_no_absolute_paths(self, tmp_path: Path) -> None:
        ids = _build_vault(tmp_path)

        result = _run(tmp_path, ids["plan"])

        assert result.exit_code == 0, result.output
        assert str(tmp_path) not in result.output
        assert ".vault" not in result.output

    def test_unknown_target_exits_1_with_near_matches(self, tmp_path: Path) -> None:
        _build_vault(tmp_path)

        # 'widg' is a substring of the 'widget' feature and plan stem, so
        # the error must name the near-matches.
        result = _run(tmp_path, "widg")

        assert result.exit_code == 1, result.output
        assert "Could not resolve" in result.output
        assert "Did you mean" in result.output
        assert "widget" in result.output

    def test_hints_present_in_human_output(self, tmp_path: Path) -> None:
        ids = _build_vault(tmp_path)

        result = _run(tmp_path, ids["plan"])

        assert result.exit_code == 0, result.output
        assert "Next action" in result.output
        assert f"vaultspec-core vault graph --feature {ids['feature']}" in result.output
        assert "vaultspec-core vault plan status" in result.output

    def test_json_envelope_shape(self, tmp_path: Path) -> None:
        ids = _build_vault(tmp_path)

        result = _run(tmp_path, ids["plan"], "--json")

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["schema"] == "vaultspec.vault.status.v1"
        assert payload["status"] == "unchanged"
        data = payload["data"]
        assert data["target"] == ids["plan"]
        assert data["kind"] == "plan"
        plan = data["plans"][0]
        assert plan["stem"] == ids["plan"]
        s01 = next(s for s in plan["steps"] if s["canonical_id"] == "S01")
        assert s01["record_stem"] == ids["exec_s01"]
        assert s01["checked"] is True
        s03 = next(s for s in plan["steps"] if s["canonical_id"] == "S03")
        assert s03["record_stem"] is None
        assert s03["checked"] is False
        assert ids["exec_orphan"] in plan["unlinked_records"]
        assert "hints" in payload
        commands = [h["command"] for h in payload["hints"]["next_steps"]]
        assert any("vault graph" in c for c in commands)
        assert any("vault plan status" in c for c in commands)


# ---------------------------------------------------------------------------
# Human-review refinements (post-verify sign-off pass)
# ---------------------------------------------------------------------------


class TestReviewRefinements:
    """Refinements applied after the human interface review.

    A leftover Phase summary is an unlinked exec document like any other
    (the ledger is the only execution artifact), the active-features listing
    is capped in human output, and an unresolvable target with no
    near-matches points at the feature list.
    """

    def test_leftover_phase_summary_is_unlinked(self, tmp_path: Path) -> None:
        ids = _build_vault(tmp_path)
        feature = ids["feature"]
        summary_stem = f"2026-03-01-{feature}-P01-summary"
        _write(
            tmp_path
            / ".vault"
            / "exec"
            / f"2026-03-01-{feature}"
            / f"{summary_stem}.md",
            _exec(
                feature,
                date="2026-03-14",
                modified="2026-03-14",
                step_id=None,
                plan_stem=ids["plan"],
            ),
        )

        result = _run(tmp_path, ids["plan"], "--json")

        assert result.exit_code == 0, result.output
        plan = json.loads(result.output)["data"]["plans"][0]
        assert "summaries" not in plan
        assert summary_stem in plan["unlinked_records"]
        assert ids["exec_orphan"] in plan["unlinked_records"]

        human = _run(tmp_path, ids["plan"])
        assert "summaries" not in human.output
        assert summary_stem in human.output

    def test_unknown_target_without_near_matches_points_to_feature_list(
        self, tmp_path: Path
    ) -> None:
        _build_vault(tmp_path)

        result = _run(tmp_path, "zzz-no-such-target-qqq")

        assert result.exit_code == 1, result.output
        assert "Could not resolve" in result.output
        assert "Did you mean" not in result.output
        assert "vaultspec-core vault feature list" in result.output

    def test_active_features_capped_on_both_surfaces(self, tmp_path: Path) -> None:
        """Both surfaces cap the feature list, and both report the total.

        The machine payload used to stay uncapped while the human render cut at
        ten - the asymmetry this campaign exists to remove. `status` opens every
        session, so its largest field cannot be a full dump: measured at 10,476
        documents the uncapped list was 52% of a 259 KB payload, and no flag
        narrowed it.

        The list is ordered by latest activity, so the cap keeps the end an
        orienting caller wants; `active_features_total` says what it did not see.
        """
        ids = _build_vault(tmp_path)
        # Twelve extra single-document features push the total past the cap.
        for n in range(12):
            feature = f"filler-{n:02d}"
            _write(
                tmp_path / ".vault" / "research" / f"2026-01-01-{feature}-research.md",
                _grounding(
                    "research", feature, date="2026-01-01", modified="2026-01-01"
                ),
            )

        result = _run(tmp_path)

        assert result.exit_code == 0, result.output
        assert "more" in result.output
        assert "vaultspec-core vault feature list" in result.output

        payload = json.loads(_run(tmp_path, "--json").output)
        data = payload["data"]
        features = data["active_features"]

        assert len(features) == 10, "the machine payload must cap too"
        assert data["active_features_total"] == 13
        assert data["active_features_truncated"] is True
        # The most recently active feature survives the cut.
        assert ids["feature"] in {f["name"] for f in features}

    def test_a_feature_list_within_the_cap_is_not_marked_truncated(
        self, tmp_path: Path
    ) -> None:
        """A small vault reports its true total and no truncation."""
        _build_vault(tmp_path)

        data = json.loads(_run(tmp_path, "--json").output)["data"]

        assert data["active_features_truncated"] is False
        assert data["active_features_total"] == len(data["active_features"])


# ---------------------------------------------------------------------------
# Clean plan line, recently-completed bucket, file paths, index exclusion
# ---------------------------------------------------------------------------


def _build_completed_vault(root: Path) -> dict[str, str]:
    """Build a vault whose single plan is 100% complete and grounded."""
    vault = root / ".vault"
    (root / ".vaultspec").mkdir(parents=True, exist_ok=True)
    feature = "gizmo"
    plan_stem = f"2026-04-01-{feature}-plan"
    _write(
        vault / "plan" / f"{plan_stem}.md",
        _plan(
            feature,
            date="2026-04-01",
            modified="2026-04-20",
            steps=[("S01", True), ("S02", True)],
        ),
    )
    for step in ("S01", "S02"):
        _write(
            vault
            / "exec"
            / f"2026-04-01-{feature}"
            / f"2026-04-01-{feature}-P01-{step}.md",
            _exec(
                feature,
                date="2026-04-02",
                modified="2026-04-02",
                step_id=step,
                plan_stem=plan_stem,
            ),
        )
    return {"feature": feature, "plan": plan_stem}


class TestPlanLineAndDiscovery:
    """The clean plan line, recently-completed bucket, paths, and index drop."""

    def test_recently_completed_bucket_lists_finished_plan(
        self, tmp_path: Path
    ) -> None:
        ids = _build_completed_vault(tmp_path)

        result = _run(tmp_path)

        assert result.exit_code == 0, result.output
        assert "Recently completed" in result.output
        completed = result.output.split("Recently completed")[1]
        assert ids["plan"] in completed
        # A finished plan shows the 'complete' cursor and 100%.
        assert "complete" in completed
        assert "2/2 steps" in completed
        # A complete plan is not also listed as in flight.
        in_flight = result.output.split("Recently completed")[0]
        assert ids["plan"] not in in_flight.split("Plans in flight")[1]

    def test_recently_completed_in_json(self, tmp_path: Path) -> None:
        ids = _build_completed_vault(tmp_path)

        payload = json.loads(_run(tmp_path, "--json").output)

        completed = payload["data"]["recently_completed"]
        assert ids["plan"] in {p["stem"] for p in completed}
        entry = next(p for p in completed if p["stem"] == ids["plan"])
        assert entry["open_steps"] == 0
        assert entry["completion_percent"] == 100.0
        assert entry["next_open_step"] is None

    def test_active_feature_row_shows_plan_tail(self, tmp_path: Path) -> None:
        _build_vault(tmp_path)

        result = _run(tmp_path)

        assert result.exit_code == 0, result.output
        active = result.output.split("Active features")[1]
        # Condensed tail: tier and step fraction on the feature row.
        assert "L2 2/3" in active

    def test_trace_header_is_clean_plan_line(self, tmp_path: Path) -> None:
        ids = _build_vault(tmp_path)

        result = _run(tmp_path, ids["plan"])

        assert result.exit_code == 0, result.output
        header = next(
            line
            for line in result.output.splitlines()
            if ids["plan"] in line and "2/3 steps" in line
        )
        assert "L2" in header
        assert "next P01.S03" in header

    def test_trace_cursor_marks_next_open_step(self, tmp_path: Path) -> None:
        ids = _build_vault(tmp_path)

        result = _run(tmp_path, ids["plan"])

        assert result.exit_code == 0, result.output
        s03_row = next(
            line
            for line in result.output.splitlines()
            if "P01.S03" in line and "[ ]" in line
        )
        assert s03_row.lstrip().startswith(">")

    def test_paths_flag_surfaces_record_path(self, tmp_path: Path) -> None:
        ids = _build_vault(tmp_path)

        without = _run(tmp_path, ids["plan"])
        withp = _run(tmp_path, ids["plan"], "--paths")

        assert without.exit_code == 0 and withp.exit_code == 0
        # Default mode stays stems-only; --paths reveals the repo-relative file.
        assert ".vault/exec" not in without.output
        assert ".vault/exec" in withp.output
        assert f"{ids['exec_s01']}.md" in withp.output

    def test_paths_in_trace_json(self, tmp_path: Path) -> None:
        ids = _build_vault(tmp_path)

        payload = json.loads(_run(tmp_path, ids["plan"], "--paths", "--json").output)

        paths = payload["data"]["paths"]
        assert ids["exec_s01"] in paths
        assert paths[ids["exec_s01"]].endswith(f"{ids['exec_s01']}.md")
        assert paths[ids["exec_s01"]].startswith(".vault/")

    def test_index_documents_excluded_from_rollup(self, tmp_path: Path) -> None:
        _build_vault(tmp_path)
        # A derived index aggregate must not relist the feature's docs.
        _write(
            tmp_path / ".vault" / "index" / "widget.index.md",
            "---\ntags:\n  - '#index'\n  - '#widget'\n"
            "date: '2026-03-20'\nmodified: '2026-03-20'\n---\n\n# widget index\n",
        )

        payload = json.loads(_run(tmp_path, "--json").output)

        assert "index" not in payload["data"]["recent_documents"]
        human = _run(tmp_path)
        assert "widget.index" not in human.output


class TestJSONErrors:
    """Failures under ``--json`` emit ``vaultspec.error.v1``, not plain text.

    Covers the two failure modes named in the issue: a workspace that fails
    to resolve at all (no ``.vaultspec/`` under the target), and a target
    argument that fails to resolve within an otherwise valid workspace. Both
    must produce a parseable envelope on stdout and a non-zero exit, per
    the documented contract in ``docs/CLI.md``.
    """

    def test_invalid_workspace_emits_json_error_envelope(self, tmp_path: Path) -> None:
        # A bare directory with no .vaultspec/ fails workspace resolution
        # before graph construction is ever reached.
        result = _run(tmp_path, "--json")

        assert result.exit_code == 1, result.output
        payload = json.loads(result.output)
        assert payload["schema"] == "vaultspec.error.v1"
        assert payload["status"] == "failed"
        assert "vaultspec_dir" in payload["data"]["message"]

    def test_invalid_target_emits_json_error_envelope(self, tmp_path: Path) -> None:
        _build_vault(tmp_path)

        result = _run(tmp_path, "zzz-no-such-target-qqq", "--json")

        assert result.exit_code == 1, result.output
        payload = json.loads(result.output)
        assert payload["schema"] == "vaultspec.error.v1"
        assert payload["status"] == "failed"
        assert "Could not resolve" in payload["data"]["message"]

    def test_success_path_json_is_unaffected(self, tmp_path: Path) -> None:
        """A valid workspace still emits its normal envelope and exits 0."""
        _build_vault(tmp_path)

        result = _run(tmp_path, "--json")

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["schema"] == "vaultspec.vault.status.v1"
        assert payload["status"] == "unchanged"


class TestExecMissingFlag:
    """A checked step lacking an execution record flags the plan line."""

    def test_plan_line_flags_checked_step_without_record(self, tmp_path: Path) -> None:
        (tmp_path / ".vaultspec").mkdir(parents=True, exist_ok=True)
        feature = "gadget"
        stem = f"2026-05-01-{feature}-plan"
        _write(
            tmp_path / ".vault" / "plan" / f"{stem}.md",
            _plan(
                feature,
                date="2026-05-01",
                modified="2026-05-20",
                # S01 is closed but has no execution record; S02 stays open.
                steps=[("S01", True), ("S02", False)],
            ),
        )

        result = _run(tmp_path)

        assert result.exit_code == 0, result.output
        in_flight = result.output.split("Recent changes")[0]
        assert stem in in_flight
        # One checked-but-ungrounded step surfaces as a !1 flag on the line.
        assert "!1" in in_flight


class TestRecencyHygiene:
    """Execution records collapse per feature unless verbosely requested."""

    def test_exec_collapsed_per_feature_by_default(self, tmp_path: Path) -> None:
        ids = _build_vault(tmp_path)

        result = _run(tmp_path)

        assert result.exit_code == 0, result.output
        assert "Execution activity" in result.output
        # The widget feature has three exec records, summarised on one line.
        assert "3 records" in result.output
        # Individual exec stems do not flood the recent view.
        assert ids["exec_s01"] not in result.output

    def test_exec_collapse_in_json(self, tmp_path: Path) -> None:
        _build_vault(tmp_path)

        payload = json.loads(_run(tmp_path, "--json").output)["data"]

        assert "exec" not in payload["recent_documents"]
        activity = payload["exec_activity"]
        widget = next(a for a in activity if a["feature"] == "widget")
        assert widget["count"] == 3

    def test_verbose_exec_lists_records(self, tmp_path: Path) -> None:
        ids = _build_vault(tmp_path)

        result = _run(tmp_path, "--verbose-exec")

        assert result.exit_code == 0, result.output
        # Verbose mode lists exec records individually and drops the collapse.
        assert ids["exec_s01"] in result.output
        assert "Execution activity" not in result.output

    def test_verbose_exec_json_includes_exec_group(self, tmp_path: Path) -> None:
        _build_vault(tmp_path)

        payload = json.loads(_run(tmp_path, "--verbose-exec", "--json").output)["data"]

        assert "exec" in payload["recent_documents"]
        assert payload["exec_activity"] == []


# ---------------------------------------------------------------------------
# Feature rollup across several plans carrying one feature tag
# ---------------------------------------------------------------------------


def _build_multi_plan_vault(root: Path) -> dict[str, str]:
    """Build a feature planned across two documents, one of them legacy.

    The older plan declares no step rows at all (the legacy shape that
    used to win the rollup outright); the newer one is fully closed.
    """
    vault = root / ".vault"
    (root / ".vaultspec").mkdir(parents=True, exist_ok=True)
    feature = "split"
    legacy_stem = f"2026-01-05-{feature}-plan"
    current_stem = f"2026-06-05-{feature}-plan"
    _write(
        vault / "plan" / f"{legacy_stem}.md",
        _plan(feature, date="2026-01-05", modified="2026-01-05", steps=[]),
    )
    _write(
        vault / "plan" / f"{current_stem}.md",
        _plan(
            feature,
            date="2026-06-05",
            modified="2026-06-05",
            steps=[("S01", True), ("S02", True), ("S03", False)],
        ),
    )
    return {"feature": feature, "legacy": legacy_stem, "current": current_stem}


class TestFeaturePlanAggregation:
    """The active-feature row sums every plan carrying the feature tag."""

    def test_step_less_plan_does_not_mask_its_sibling(self, tmp_path: Path) -> None:
        _build_multi_plan_vault(tmp_path)

        result = _run(tmp_path)

        assert result.exit_code == 0, result.output
        row = next(
            line
            for line in result.output.split("Active features")[1].splitlines()
            if "split" in line
        )
        # The sibling plan's steps reach the row instead of a bare 0/0.
        assert "L2 2/3 66.7%" in row
        assert "across 2 plans" in row

    def test_aggregate_counts_in_json(self, tmp_path: Path) -> None:
        _build_multi_plan_vault(tmp_path)

        payload = json.loads(_run(tmp_path, "--json").output)["data"]

        feature = next(f for f in payload["active_features"] if f["name"] == "split")
        assert feature["plan_step_count"] == 3
        assert feature["plan_steps_completed"] == 2
        assert feature["plan_completion_percent"] == 66.7
        assert feature["plan_count"] == 2
        assert feature["plans_unreadable"] == 0

    def test_unreadable_plan_is_reported_not_rendered_as_no_progress(
        self, tmp_path: Path
    ) -> None:
        vault = tmp_path / ".vault"
        (tmp_path / ".vaultspec").mkdir(parents=True, exist_ok=True)
        # A real malformed plan: 'L9' is not a member of the tier enum.
        _write(
            vault / "plan" / "2026-05-01-cracked-plan.md",
            _plan(
                "cracked",
                date="2026-05-01",
                modified="2026-05-01",
                steps=[("S01", True)],
                tier="L9",
            ),
        )

        result = _run(tmp_path)

        assert result.exit_code == 0, result.output
        row = next(
            line
            for line in result.output.split("Active features")[1].splitlines()
            if "cracked" in line
        )
        assert "1 unreadable plan" in row
