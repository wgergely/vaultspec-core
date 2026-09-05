"""Unit tests for the vault command group.

Covers vault add, vault stats, vault check, etc.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from vaultspec_core.cli import app

from ...vaultcore import DocType, vault_today

if TYPE_CHECKING:
    from pathlib import Path

    from typer.testing import CliRunner

    from vaultspec_core.tests.cli.workspace_factory import WorkspaceFactory

pytestmark = [pytest.mark.unit]


class TestGetVersion:
    """Verify version information is correctly retrieved."""

    def test_reads_version_from_pyproject(self, synthetic_project: Path):
        from importlib.metadata import version

        from vaultspec_core.cli_common import get_version

        v = get_version()
        expected = version("vaultspec-core")
        assert v == expected

    def test_get_version_returns_string(self, synthetic_project: Path):
        from vaultspec_core.cli_common import get_version

        assert isinstance(get_version(), str)


class TestHelpText:
    """Verify that --help output contains expected strings."""

    def test_main_help(self, runner: CliRunner, synthetic_project: Path):
        result = runner.invoke(
            app, ["--target", str(synthetic_project), "vault", "--help"]
        )
        assert result.exit_code == 0
        assert "add" in result.output
        assert "check" in result.output
        assert "stats" in result.output

    def test_add_help(self, runner: CliRunner, synthetic_project: Path):
        result = runner.invoke(
            app, ["--target", str(synthetic_project), "vault", "add", "--help"]
        )
        assert result.exit_code == 0
        assert "--feature" in result.output


class TestAddSubcommand:
    """Verify 'vault add' behavior."""

    @pytest.mark.parametrize("force", [False, True])
    @pytest.mark.parametrize("dry_run", [False, True])
    @pytest.mark.parametrize("json_output", [False, True])
    def test_add_rejects_extra_tags_before_writing(
        self,
        runner: CliRunner,
        synthetic_project: Path,
        force: bool,
        dry_run: bool,
        json_output: bool,
    ) -> None:
        args = [
            "--target",
            str(synthetic_project),
            "vault",
            "add",
            "research",
            "--feature",
            "tag-rejection",
            "--title",
            "Tag rejection",
        ]
        if force:
            assert runner.invoke(app, args).exit_code == 0
        vault = synthetic_project / ".vault"
        before = {p.relative_to(vault): p.read_bytes() for p in vault.rglob("*.md")}
        result = runner.invoke(
            app,
            args
            + ["--tags", "review"]
            + (["--json"] if json_output else [])
            + (["--force"] if force else [])
            + (["--dry-run"] if dry_run else []),
        )
        assert result.exit_code == 1
        assert "Unsupported tags" in result.output
        if json_output:
            payload = json.loads(result.stdout)
            assert payload["status"] == "failed"
        after = {p.relative_to(vault): p.read_bytes() for p in vault.rglob("*.md")}
        assert after == before

    def test_add_generates_correct_filename(
        self, runner: CliRunner, synthetic_project: Path
    ):
        date_str = vault_today().isoformat()

        # Cleanup potential leftover from previous failed tests
        expected_path = (
            synthetic_project / ".vault" / "adr" / f"{date_str}-test-feat-adr.md"
        )
        if expected_path.exists():
            expected_path.unlink()

        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "vault",
                "add",
                "adr",
                "--feature",
                "test-feat",
                "--title",
                "My Title",
            ],
        )
        assert result.exit_code == 0, f"Failed: {result.output}"
        assert expected_path.exists()

    def test_add_topic_infix_generates_disambiguated_filename(
        self, runner: CliRunner, synthetic_project: Path
    ):
        date_str = vault_today().isoformat()
        expected_path = (
            synthetic_project
            / ".vault"
            / "reference"
            / f"{date_str}-topic-feat-engine-wire-reference.md"
        )
        if expected_path.exists():
            expected_path.unlink()

        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "vault",
                "add",
                "reference",
                "--feature",
                "topic-feat",
                "--topic",
                "engine-wire",
            ],
        )
        assert result.exit_code == 0, f"Failed: {result.output}"
        assert expected_path.exists()
        body = expected_path.read_text(encoding="utf-8")
        assert "{topic}" not in body
        assert "{title}" not in body

    def test_add_topic_rejected_for_non_admitting_type(
        self, runner: CliRunner, synthetic_project: Path
    ):
        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "vault",
                "add",
                "plan",
                "--feature",
                "topic-feat",
                "--topic",
                "second",
            ],
        )
        assert result.exit_code == 1
        assert "--topic is only valid" in result.output

    def test_add_topic_rejects_non_kebab_value(
        self, runner: CliRunner, synthetic_project: Path
    ):
        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "vault",
                "add",
                "reference",
                "--feature",
                "topic-feat",
                "--topic",
                "Not Kebab!",
            ],
        )
        assert result.exit_code == 1

    def test_add_strips_hash_from_feature(
        self, runner: CliRunner, synthetic_project: Path
    ):
        """Creating with #feature should strip the hash."""
        date_str = vault_today().isoformat()

        expected_path = (
            synthetic_project / ".vault" / "adr" / f"{date_str}-my-feat-adr.md"
        )
        if expected_path.exists():
            expected_path.unlink()

        runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "vault",
                "add",
                "adr",
                "--feature",
                "#my-feat",
            ],
        )
        assert expected_path.exists()

    def test_add_valid_doc_types_accepted(
        self, runner: CliRunner, tmp_path: Path, synthetic_project: Path
    ):
        """Test all user-creatable DocType choices are accepted.

        ``DocType.INDEX`` is auto-generated and not user-creatable; the
        ``vault add`` surface rejects it with an explicit error so this
        test exercises only the authored types.

        Uses real templates via seed_builtins - never shadow template files.
        """
        from vaultspec_core.builtins import seed_builtins
        from vaultspec_core.core.types import init_paths

        # Seed real templates from the repo into the tmp workspace
        rules_dir = tmp_path / ".vaultspec"
        rules_dir.mkdir(parents=True)
        seed_builtins(rules_dir, force=True)

        # Create vault type directories
        for dt in DocType:
            (tmp_path / ".vault" / dt.value).mkdir(parents=True, exist_ok=True)

        # Create prerequisite docs for feature 'f' so exec validation passes.
        # Exec requires research + ADR + plan to exist for the feature.
        for prereq in ("research", "adr", "plan"):
            d = tmp_path / ".vault" / prereq
            (d / f"2026-01-01-f-{prereq}.md").write_text(
                f"---\ntags:\n  - '#{prereq}'\n  - '#f'\n"
                f"date: '2026-01-01'\nrelated: []\n---\n# Prerequisite\n",
                encoding="utf-8",
            )

        init_paths(tmp_path)

        for dt in DocType:
            if dt is DocType.INDEX:
                continue
            result = runner.invoke(
                app,
                [
                    "--target",
                    str(tmp_path),
                    "vault",
                    "add",
                    dt.value,
                    "--feature",
                    "f",
                ],
            )
            if dt is DocType.EXEC:
                # Execution is logged with `vault exec log`, never scaffolded.
                assert result.exit_code == 1, result.output
                assert "vault exec log" in result.output
                continue
            assert result.exit_code == 0, (
                f"DocType {dt.value} rejected (output: {result.output})"
            )

    def test_add_index_type_is_rejected(
        self, runner: CliRunner, tmp_path: Path, synthetic_project: Path
    ):
        """``vault add index`` must redirect users to ``vault feature index``.

        Index files are auto-generated; allowing ``vault add`` to write
        one would put the file at the wrong filename
        (``<date>-<feature>-index.md`` instead of
        ``<feature>.index.md``) and bypass the generator's bookkeeping.
        """
        from vaultspec_core.builtins import seed_builtins
        from vaultspec_core.core.types import init_paths

        rules_dir = tmp_path / ".vaultspec"
        rules_dir.mkdir(parents=True)
        seed_builtins(rules_dir, force=True)
        for dt in DocType:
            (tmp_path / ".vault" / dt.value).mkdir(parents=True, exist_ok=True)
        init_paths(tmp_path)

        result = runner.invoke(
            app,
            [
                "--target",
                str(tmp_path),
                "vault",
                "add",
                "index",
                "--feature",
                "rejected-feature",
            ],
        )
        assert result.exit_code != 0
        assert "auto-generated" in result.output
        assert "vault feature index" in result.output
        # No .vault/index/<...>.md file should have been written.
        index_dir = tmp_path / ".vault" / "index"
        if index_dir.is_dir():
            assert not any(index_dir.iterdir())

    def test_add_created_doc_passes_validation(
        self, runner: CliRunner, synthetic_project: Path
    ):
        """Created documents must pass the project's own frontmatter validation."""
        from vaultspec_core.vaultcore.parser import parse_vault_metadata

        date_str = vault_today().isoformat()
        expected_path = (
            synthetic_project
            / ".vault"
            / "research"
            / f"{date_str}-valid-doc-research.md"
        )
        if expected_path.exists():
            expected_path.unlink()

        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "vault",
                "add",
                "research",
                "--feature",
                "valid-doc",
                "--title",
                "Validation Test",
            ],
        )
        assert result.exit_code == 0, f"Failed: {result.output}"
        assert expected_path.exists()

        # The created document must pass our own validation
        content = expected_path.read_text(encoding="utf-8")
        metadata, _ = parse_vault_metadata(content)
        errors = metadata.validate()
        assert not errors, f"Created document fails validation: {errors}"

    def test_add_retains_template_annotations_until_explicit_fix(
        self, runner: CliRunner, synthetic_project: Path
    ):
        """Hydration must not strip agent-facing template instructions."""
        date_str = vault_today().isoformat()
        expected_path = (
            synthetic_project
            / ".vault"
            / "research"
            / f"{date_str}-annotation-lifecycle-research.md"
        )
        if expected_path.exists():
            expected_path.unlink()

        add_result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "vault",
                "add",
                "research",
                "--feature",
                "annotation-lifecycle",
                "--title",
                "Annotation Lifecycle",
            ],
        )
        assert add_result.exit_code == 0, add_result.output

        created = expected_path.read_text(encoding="utf-8")
        assert "<!-- FRONTMATTER RULES:" in created
        assert "<!-- LINK RULES:" in created

        fix_result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "vault",
                "check",
                "annotations",
                "--feature",
                "annotation-lifecycle",
                "--fix",
            ],
        )
        assert fix_result.exit_code == 0, fix_result.output

        sanitized = expected_path.read_text(encoding="utf-8")
        assert "<!-- FRONTMATTER RULES:" not in sanitized
        assert "<!-- LINK RULES:" not in sanitized


class TestVaultJsonOutput:
    """JSON-mode commands must produce machine-readable stdout only."""

    def test_add_dry_run_json_has_no_human_prefix(
        self, runner: CliRunner, synthetic_project: Path
    ):
        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "vault",
                "add",
                "research",
                "--feature",
                "json-dry-run",
                "--dry-run",
                "--json",
            ],
        )

        payload = json.loads(result.output)["data"]
        assert result.exit_code == 0, result.output
        assert result.output.lstrip().startswith("{")
        assert payload["dry_run"] is True
        assert payload["type"] == "research"

    def test_graph_empty_json_has_no_human_prefix(self, factory: WorkspaceFactory):
        factory.install("core")

        result = factory.run("vault", "graph", "--json")

        payload = json.loads(result.output)["data"]
        assert result.exit_code == 0, result.output
        assert result.output.lstrip().startswith("{")
        assert payload["nodes"] == []
        assert payload.get("links", payload.get("edges", [])) == []

    def test_feature_index_empty_json_has_no_human_prefix(
        self, factory: WorkspaceFactory
    ):
        factory.install("core")

        result = factory.run("vault", "feature", "index", "--json")

        payload = json.loads(result.output)["data"]
        assert result.exit_code == 0, result.output
        assert result.output.lstrip().startswith("{")
        assert payload == {"generated": []}

    def test_feature_index_json_reports_existing_current_index_unchanged(
        self, factory: WorkspaceFactory
    ) -> None:
        """A semantic no-op reports no generated paths and no update."""
        factory.install("core")
        created = factory.run(
            "vault", "add", "research", "--feature", "stable-index", "--no-hints"
        )
        assert created.exit_code == 0, created.output
        first = factory.run(
            "vault", "feature", "index", "--feature", "stable-index", "--json"
        )
        assert first.exit_code == 0, first.output

        second = factory.run(
            "vault", "feature", "index", "--feature", "stable-index", "--json"
        )

        envelope = json.loads(second.output)
        assert envelope["status"] == "unchanged"
        assert envelope["data"] == {"generated": []}


class TestVaultGraphScopingFlags:
    """vault graph --node/--depth ego scoping and --derived/--no-derived."""

    def _graph_json(
        self, runner: CliRunner, project: Path, *extra: str
    ) -> dict[str, Any]:
        result = runner.invoke(
            app,
            ["--target", str(project), "vault", "graph", "--json", *extra],
        )
        assert result.exit_code == 0, result.output
        payload: dict[str, Any] = json.loads(result.output)
        return payload

    def _busiest_node(self, payload: dict[str, Any]) -> str:
        """Return the node id with the most incoming plus outgoing links."""
        nodes = payload["data"]["nodes"]
        ranked = sorted(
            nodes,
            key=lambda n: (len(n["out_links"]) + len(n["in_links"]), n["id"]),
            reverse=True,
        )
        return ranked[0]["id"]

    def test_derived_edges_are_opt_in(self, runner: CliRunner, synthetic_project: Path):
        """The default export omits the derived set.

        Derived edges are a computed similarity ranking rather than vault
        state, and they were 94% of a full export - 261 MB of a 416 MB payload
        at 10,476 documents. A caller that wants the ranking asks for it.
        """
        payload = self._graph_json(runner, synthetic_project)
        assert payload["schema"] == "vaultspec.vault.graph.v2"
        data = payload["data"]
        assert "derived_edges" in data
        assert "edges" in data
        assert data["derived_edges"] == []

    def test_derived_flag_includes_the_ranking_and_states_its_total(
        self, runner: CliRunner, synthetic_project: Path
    ):
        """Asking for the ranking returns it, capped, with its full total."""
        payload = self._graph_json(runner, synthetic_project, "--derived")
        data = payload["data"]

        assert isinstance(data["derived_edges"], list)
        assert len(data["derived_edges"]) > 0
        assert data["derived_edges_total"] >= len(data["derived_edges"])
        assert data["derived_edges_truncated"] == (
            len(data["derived_edges"]) < data["derived_edges_total"]
        )

    def test_the_derived_toggle_does_not_disturb_canonical_edges(
        self, runner: CliRunner, synthetic_project: Path
    ):
        """The real edge set is the same either way."""
        default = self._graph_json(runner, synthetic_project)
        with_derived = self._graph_json(runner, synthetic_project, "--derived")

        assert default["data"]["edges"] == with_derived["data"]["edges"]

    def test_node_scopes_to_ego_neighbourhood(
        self, runner: CliRunner, synthetic_project: Path
    ):
        full = self._graph_json(runner, synthetic_project)
        centre = self._busiest_node(full)
        ego = self._graph_json(runner, synthetic_project, "--node", centre)
        ego_ids = {n["id"] for n in ego["data"]["nodes"]}
        assert centre in ego_ids
        # An ego scope is a subset of the full node set.
        full_ids = {n["id"] for n in full["data"]["nodes"]}
        assert ego_ids <= full_ids
        assert len(ego_ids) < len(full_ids)

    def test_depth_zero_returns_only_the_centre(
        self, runner: CliRunner, synthetic_project: Path
    ):
        full = self._graph_json(runner, synthetic_project)
        centre = self._busiest_node(full)
        ego0 = self._graph_json(
            runner, synthetic_project, "--node", centre, "--depth", "0"
        )
        ids = {n["id"] for n in ego0["data"]["nodes"]}
        assert ids == {centre}

    def test_depth_grows_neighbourhood_monotonically(
        self, runner: CliRunner, synthetic_project: Path
    ):
        full = self._graph_json(runner, synthetic_project)
        centre = self._busiest_node(full)
        n0 = len(
            self._graph_json(
                runner, synthetic_project, "--node", centre, "--depth", "0"
            )["data"]["nodes"]
        )
        n1 = len(
            self._graph_json(
                runner, synthetic_project, "--node", centre, "--depth", "1"
            )["data"]["nodes"]
        )
        assert n0 == 1
        assert n1 >= n0

    def test_missing_node_fails_with_exit_one(
        self, runner: CliRunner, synthetic_project: Path
    ):
        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "vault",
                "graph",
                "--json",
                "--node",
                "this-node-does-not-exist",
            ],
        )
        assert result.exit_code == 1, result.output
        payload = json.loads(result.output)
        assert payload["status"] == "failed"
        assert "this-node-does-not-exist" in payload["data"]["message"]

    def test_ego_derived_edges_stay_within_scope(
        self, runner: CliRunner, synthetic_project: Path
    ):
        full = self._graph_json(runner, synthetic_project)
        centre = self._busiest_node(full)
        ego = self._graph_json(
            runner, synthetic_project, "--node", centre, "--depth", "2"
        )
        ids = {n["id"] for n in ego["data"]["nodes"]}
        for edge in ego["data"]["derived_edges"]:
            assert edge["source"] in ids
            assert edge["target"] in ids


class TestNoCommand:
    def test_no_command_prints_help(self, runner: CliRunner, synthetic_project: Path):
        result = runner.invoke(app, ["--target", str(synthetic_project), "vault"])
        # vault_app uses no_args_is_help=True. The actual contract is that
        # help is rendered to output; the exit code is a Typer-version
        # implementation detail (0 in newer Typer, 2 in older), so we
        # assert on the rendered help block, not the exit code.
        assert "Usage" in result.output, (
            f"vault command without args did not render help: {result.output}"
        )
        assert "add" in result.output, (
            f"vault help did not list the 'add' subcommand: {result.output}"
        )


class TestCheckCodeBoundary:
    """The opt-in source-boundary scanner verb is advisory."""

    def test_findings_are_warnings_and_exit_zero(
        self, runner: CliRunner, tmp_path: Path, synthetic_project: Path
    ):
        from vaultspec_core.core.types import init_paths

        stem = "2026-07-16-my-feat-adr"
        doc = tmp_path / ".vault" / "adr" / f"{stem}.md"
        doc.parent.mkdir(parents=True)
        doc.write_text(
            "---\ntags:\n  - '#adr'\n  - '#my-feat'\n"
            "date: '2026-07-16'\nmodified: '2026-07-16'\nrelated: []\n---\n",
            encoding="utf-8",
        )
        (tmp_path / "module.py").write_text(f"# see {stem}\n", encoding="utf-8")
        (tmp_path / ".vaultspec").mkdir()
        init_paths(tmp_path)

        result = runner.invoke(
            app,
            ["--target", str(tmp_path), "vault", "check", "code-boundary"],
        )
        assert result.exit_code == 0, f"Failed: {result.output}"
        assert stem in result.output

    def test_clean_tree_reports_clean(
        self, runner: CliRunner, tmp_path: Path, synthetic_project: Path
    ):
        from vaultspec_core.core.types import init_paths

        (tmp_path / ".vault" / "adr").mkdir(parents=True)
        (tmp_path / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
        (tmp_path / ".vaultspec").mkdir()
        init_paths(tmp_path)

        result = runner.invoke(
            app,
            ["--target", str(tmp_path), "vault", "check", "code-boundary"],
        )
        assert result.exit_code == 0
        assert "clean" in result.output
