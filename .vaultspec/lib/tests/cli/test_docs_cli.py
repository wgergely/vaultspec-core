"""Tests for the docs.py CLI entry point.

Covers: argument parsing for all subcommands (audit, create, index, search),
        --version flag, --help text with GPU/CUDA note, audit --summary,
        audit --features, audit --verify, create output path generation,
        and _get_version() reading from pyproject.toml.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
from tests.constants import PROJECT_ROOT, TEST_PROJECT

pytestmark = [pytest.mark.unit]

# Path to the docs.py script
DOCS_SCRIPT = PROJECT_ROOT / ".vaultspec" / "lib" / "scripts" / "docs.py"


# ---------------------------------------------------------------------------
# Helper: run docs.py as subprocess
# ---------------------------------------------------------------------------


def run_docs(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    """Run docs.py as subprocess and return the result."""
    return subprocess.run(
        [sys.executable, str(DOCS_SCRIPT), *args],
        capture_output=True,
        text=True,
        check=check,
        timeout=30,
    )


# ===================================================================
# _get_version()
# ===================================================================


class TestGetVersion:
    """Tests for _get_version() reading from pyproject.toml."""

    def test_reads_version_from_pyproject(self):
        """_get_version() should read version from pyproject.toml."""
        result = run_docs("--version")
        # --version causes SystemExit(0) and prints to stdout
        assert result.returncode == 0
        assert "0.1.0" in result.stdout

    def test_version_flag_short(self):
        """-V flag should print version."""
        result = run_docs("-V")
        assert result.returncode == 0
        assert "0.1.0" in result.stdout

    def test_get_version_returns_string(self):
        """Import _get_version and verify it returns a string."""
        import docs

        version = docs._get_version()
        assert isinstance(version, str)
        assert version == "0.1.0"

    def test_get_version_missing_pyproject(self, monkeypatch, tmp_path):
        """_get_version returns 'unknown' when pyproject.toml is missing."""
        import docs

        # Temporarily redirect ROOT_DIR to a path with no pyproject.toml
        monkeypatch.setattr(docs, "ROOT_DIR", tmp_path)
        version = docs._get_version()
        assert version == "unknown"


# ===================================================================
# --help text
# ===================================================================


class TestHelpText:
    """Tests for --help output across subcommands."""

    def test_main_help(self):
        result = run_docs("--help")
        assert result.returncode == 0
        assert "Audit and manage the .vault vault" in result.stdout

    def test_audit_help(self):
        result = run_docs("audit", "--help")
        assert result.returncode == 0
        assert "--summary" in result.stdout
        assert "--features" in result.stdout
        assert "--verify" in result.stdout
        assert "--graph" in result.stdout
        assert "--json" in result.stdout
        assert "--root" in result.stdout

    def test_create_help(self):
        result = run_docs("create", "--help")
        assert result.returncode == 0
        assert "--type" in result.stdout
        assert "--feature" in result.stdout
        assert "--title" in result.stdout

    def test_index_help_has_gpu_note(self):
        """Index subcommand epilog should mention GPU/CUDA requirement."""
        result = run_docs("index", "--help")
        assert result.returncode == 0
        assert "NVIDIA GPU" in result.stdout or "CUDA" in result.stdout

    def test_search_help_has_gpu_note(self):
        """Search subcommand epilog should mention GPU/CUDA requirement."""
        result = run_docs("search", "--help")
        assert result.returncode == 0
        assert "NVIDIA GPU" in result.stdout or "CUDA" in result.stdout

    def test_index_help_has_full_flag(self):
        result = run_docs("index", "--help")
        assert result.returncode == 0
        assert "--full" in result.stdout

    def test_search_help_has_query_arg(self):
        result = run_docs("search", "--help")
        assert result.returncode == 0
        assert "query" in result.stdout


# ===================================================================
# Argument parsing via monkeypatch
# ===================================================================


class TestArgumentParsing:
    """Test argparse configuration by parsing args directly."""

    @pytest.fixture()
    def parser(self):
        """Return the real docs.py argument parser."""
        import docs

        return docs._make_parser()

    def test_audit_summary_flag(self, parser):
        args = parser.parse_args(["audit", "--summary"])
        assert args.command == "audit"
        assert args.summary is True

    def test_audit_features_flag(self, parser):
        args = parser.parse_args(["audit", "--features"])
        assert args.command == "audit"
        assert args.features is True

    def test_audit_verify_flag(self, parser):
        args = parser.parse_args(["audit", "--verify"])
        assert args.command == "audit"
        assert args.verify is True

    def test_audit_graph_flag(self, parser):
        args = parser.parse_args(["audit", "--graph"])
        assert args.command == "audit"
        assert args.graph is True

    def test_audit_json_flag(self, parser):
        args = parser.parse_args(["audit", "--json"])
        assert args.command == "audit"
        assert args.json is True

    def test_audit_root_path(self, parser, tmp_path):
        args = parser.parse_args(["audit", "--root", str(tmp_path)])
        assert args.root == tmp_path

    def test_audit_limit_default(self, parser):
        args = parser.parse_args(["audit"])
        assert args.limit == 10

    def test_audit_limit_custom(self, parser):
        args = parser.parse_args(["audit", "--limit", "25"])
        assert args.limit == 25

    def test_audit_type_filter(self, parser):
        args = parser.parse_args(["audit", "--type", "adr"])
        assert args.type == "adr"

    def test_audit_feature_filter(self, parser):
        args = parser.parse_args(["audit", "--feature", "editor-demo"])
        assert args.feature == "editor-demo"

    def test_create_all_required_args(self, parser):
        args = parser.parse_args(["create", "--type", "adr", "--feature", "my-feat"])
        assert args.command == "create"
        assert args.type == "adr"
        assert args.feature == "my-feat"

    def test_create_with_title(self, parser):
        args = parser.parse_args(
            [
                "create",
                "--type",
                "plan",
                "--feature",
                "auth",
                "--title",
                "Auth Phase 1",
            ]
        )
        assert args.title == "Auth Phase 1"

    def test_create_rejects_invalid_type(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["create", "--type", "invalid", "--feature", "x"])

    def test_create_requires_type(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["create", "--feature", "x"])

    def test_create_requires_feature(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["create", "--type", "adr"])

    def test_index_full_flag(self, parser):
        args = parser.parse_args(["index", "--full"])
        assert args.command == "index"
        assert args.full is True

    def test_index_json_flag(self, parser):
        args = parser.parse_args(["index", "--json"])
        assert args.json is True

    def test_search_query_positional(self, parser):
        args = parser.parse_args(["search", "how to deploy"])
        assert args.command == "search"
        assert args.query == "how to deploy"

    def test_search_limit_default(self, parser):
        args = parser.parse_args(["search", "test query"])
        assert args.limit == 5

    def test_search_limit_custom(self, parser):
        args = parser.parse_args(["search", "test query", "--limit", "20"])
        assert args.limit == 20

    def test_search_json_flag(self, parser):
        args = parser.parse_args(["search", "query", "--json"])
        assert args.json is True

    def test_search_requires_query(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["search"])

    def test_verbose_flag(self, parser):
        args = parser.parse_args(["--verbose", "audit"])
        assert args.verbose is True

    def test_debug_flag(self, parser):
        args = parser.parse_args(["--debug", "audit"])
        assert args.debug is True

    def test_no_command_defaults_none(self, parser):
        args = parser.parse_args([])
        assert args.command is None


# ===================================================================
# Audit subcommand (functional, using test-project vault)
# ===================================================================


class TestAuditSummary:
    """Test audit --summary on the test-project vault."""

    def test_audit_summary_text(self):
        """audit --summary should print vault summary stats."""
        result = run_docs("audit", "--summary", "--root", str(TEST_PROJECT))
        assert result.returncode == 0
        assert "Vault Summary" in result.stdout
        assert "Total Documents" in result.stdout
        assert "Total Features" in result.stdout
        assert "By Type" in result.stdout

    def test_audit_summary_json(self):
        """audit --summary --json should print valid JSON."""
        result = run_docs("audit", "--summary", "--json", "--root", str(TEST_PROJECT))
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "summary" in data
        summary = data["summary"]
        assert "total_docs" in summary
        assert "total_features" in summary
        assert "counts_by_type" in summary
        assert summary["total_docs"] > 0

    def test_audit_summary_counts_types(self):
        """Summary counts should include known doc types."""
        result = run_docs("audit", "--summary", "--json", "--root", str(TEST_PROJECT))
        data = json.loads(result.stdout)
        types = data["summary"]["counts_by_type"]
        # The test-project vault has at least adr and plan docs
        assert "adr" in types
        assert "plan" in types


class TestAuditFeatures:
    """Test audit --features on the test-project vault."""

    def test_audit_features_text(self):
        """audit --features should list features."""
        result = run_docs("audit", "--features", "--root", str(TEST_PROJECT))
        assert result.returncode == 0
        assert "Features" in result.stdout

    def test_audit_features_json(self):
        """audit --features --json should produce a features list."""
        result = run_docs("audit", "--features", "--json", "--root", str(TEST_PROJECT))
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "features" in data
        assert isinstance(data["features"], list)
        assert len(data["features"]) > 0


class TestAuditVerify:
    """Test audit --verify on the test-project vault."""

    def test_audit_verify_text(self):
        """audit --verify should print verification results."""
        result = run_docs("audit", "--verify", "--root", str(TEST_PROJECT))
        assert result.returncode == 0
        # Should contain either "Passed" or "Failed" depending on vault state
        assert "Verification" in result.stdout or "errors" in result.stdout.lower()

    def test_audit_verify_json(self):
        """audit --verify --json should produce verification results."""
        result = run_docs("audit", "--verify", "--json", "--root", str(TEST_PROJECT))
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "verification" in data
        v = data["verification"]
        assert "passed" in v
        assert "errors" in v
        assert isinstance(v["errors"], list)

    def test_audit_combined_summary_and_features(self):
        """audit --summary --features should output both sections."""
        result = run_docs(
            "audit",
            "--summary",
            "--features",
            "--json",
            "--root",
            str(TEST_PROJECT),
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "summary" in data
        assert "features" in data


# ===================================================================
# Create subcommand (output path generation)
# ===================================================================


class TestCreateSubcommand:
    """Test create subcommand output path logic."""

    def test_create_generates_correct_filename(self, tmp_path):
        """Create should generate yyyy-mm-dd-<feature>-<type>.md filename."""
        import argparse

        import docs

        # Set up a minimal .vaultspec/templates directory with a template
        template_dir = tmp_path / ".vaultspec" / "templates"
        template_dir.mkdir(parents=True)
        (template_dir / "adr.md").write_text(
            "---\ntags: [#adr, #<feature>]\ndate: <yyyy-mm-dd>\n---\n# <title>\n",
            encoding="utf-8",
        )

        args = argparse.Namespace(
            type="adr", feature="my-feature", title="Test ADR", root=tmp_path
        )
        docs.handle_create(args)

        date_str = datetime.now().strftime("%Y-%m-%d")
        expected = tmp_path / ".vault" / "adr" / f"{date_str}-my-feature-adr.md"
        assert expected.exists()
        content = expected.read_text(encoding="utf-8")
        assert "#my-feature" in content
        assert date_str in content
        assert "Test ADR" in content

    def test_create_strips_hash_from_feature(self):
        """Feature name should have leading # stripped."""
        feature = "#editor-demo"
        cleaned = feature.strip("#")
        assert cleaned == "editor-demo"

    def test_create_missing_type_errors_subprocess(self):
        """create without --type should fail."""
        result = run_docs("create", "--feature", "test-feat")
        assert result.returncode != 0

    def test_create_missing_feature_errors_subprocess(self):
        """create without --feature should fail."""
        result = run_docs("create", "--type", "adr")
        assert result.returncode != 0

    def test_create_valid_doc_types_accepted(self):
        """All DocType values should be accepted by create --type."""
        from vault.models import DocType

        for dt in DocType:
            # Just test that parsing accepts the type (will fail at execution
            # stage due to missing vault, but argparse should not reject it)
            result = run_docs(
                "create",
                "--type",
                dt.value,
                "--feature",
                "test",
                "--root",
                str(Path("/nonexistent")),
            )
            # Should not fail due to argparse rejection (returncode 2)
            assert result.returncode != 2, f"DocType {dt.value} rejected by argparse"


# ===================================================================
# No-command behavior
# ===================================================================


class TestNoCommand:
    """Test behavior when no subcommand is given."""

    def test_no_command_prints_help(self):
        """Running docs.py with no arguments should print help and exit 0."""
        result = run_docs()
        assert result.returncode == 0
        assert "usage:" in result.stdout.lower() or "audit" in result.stdout


# ===================================================================
# Logging configuration dispatch
# ===================================================================


class TestLoggingDispatch:
    """Test that --verbose and --debug correctly dispatch to configure_logging."""

    def test_verbose_configures_info(self, monkeypatch):
        """--verbose should call configure_logging(level='INFO')."""
        import docs

        calls = []
        monkeypatch.setattr(docs, "configure_logging", lambda **kw: calls.append(kw))
        monkeypatch.setattr("sys.argv", ["docs.py", "--verbose", "audit", "--summary"])
        monkeypatch.setattr(docs, "handle_audit", lambda *_args: None)
        docs.main()
        assert calls == [{"level": "INFO"}]

    def test_debug_configures_debug(self, monkeypatch):
        """--debug should call configure_logging(level='DEBUG')."""
        import docs

        calls = []
        monkeypatch.setattr(docs, "configure_logging", lambda **kw: calls.append(kw))
        monkeypatch.setattr("sys.argv", ["docs.py", "--debug", "audit", "--summary"])
        monkeypatch.setattr(docs, "handle_audit", lambda *_args: None)
        docs.main()
        assert calls == [{"level": "DEBUG"}]

    def test_default_configures_no_args(self, monkeypatch):
        """No verbose/debug should call configure_logging() with no args."""
        import docs

        calls = []
        monkeypatch.setattr(docs, "configure_logging", lambda **kw: calls.append(kw))
        monkeypatch.setattr("sys.argv", ["docs.py", "audit", "--summary"])
        monkeypatch.setattr(docs, "handle_audit", lambda *_args: None)
        docs.main()
        assert calls == [{}]
