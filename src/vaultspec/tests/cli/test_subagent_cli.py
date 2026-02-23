"""Tests for the subagent_cli.py CLI entry point.

Covers: argument parsing for all subcommands (run, a2a-serve, serve, list),
        all 14 `run` flags, all 5 `a2a-serve` flags, defaults verification,
        and validation error paths via subprocess.
"""

import subprocess
import sys

import pytest

pytestmark = [pytest.mark.unit]

# ---------------------------------------------------------------------------
# Helper: run subagent_cli as subprocess
# ---------------------------------------------------------------------------


def run_subagent(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    """Run vaultspec.subagent_cli as subprocess and return the result."""
    return subprocess.run(
        [sys.executable, "-m", "vaultspec.subagent_cli", *args],
        capture_output=True,
        text=True,
        check=check,
        timeout=30,
    )


# ===================================================================
# TestSubagentArgParsing — direct parser tests for `run` subcommand
# ===================================================================


class TestSubagentArgParsing:
    """Test argparse configuration for the `run` subcommand by parsing args directly."""

    @pytest.fixture()
    def parser(self):
        """Return the real subagent_cli argument parser."""
        from ... import subagent_cli

        return subagent_cli._make_parser()

    def test_run_agent_flag(self, parser):
        args = parser.parse_args(["run", "--agent", "my-agent", "--goal", "do X"])
        assert args.command == "run"
        assert args.agent == "my-agent"
        assert args.goal == "do X"

    def test_run_agent_short_flag(self, parser):
        args = parser.parse_args(["run", "-a", "my-agent", "--goal", "do X"])
        assert args.agent == "my-agent"

    def test_run_model_override(self, parser):
        args = parser.parse_args(
            ["run", "--agent", "x", "--goal", "y", "--model", "opus-4"]
        )
        assert args.model == "opus-4"

    def test_run_model_short_flag(self, parser):
        args = parser.parse_args(["run", "-a", "x", "--goal", "y", "-m", "opus-4"])
        assert args.model == "opus-4"

    def test_run_provider_claude(self, parser):
        args = parser.parse_args(
            ["run", "--agent", "x", "--goal", "y", "--provider", "claude"]
        )
        assert args.provider == "claude"

    def test_run_provider_gemini(self, parser):
        args = parser.parse_args(
            ["run", "--agent", "x", "--goal", "y", "--provider", "gemini"]
        )
        assert args.provider == "gemini"

    def test_run_provider_invalid_raises(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(
                ["run", "--agent", "x", "--goal", "y", "--provider", "invalid"]
            )

    def test_run_provider_short_flag(self, parser):
        args = parser.parse_args(["run", "-a", "x", "--goal", "y", "-p", "gemini"])
        assert args.provider == "gemini"

    def test_run_mode_default(self, parser):
        args = parser.parse_args(["run", "--agent", "x", "--goal", "y"])
        assert args.mode == "read-write"

    def test_run_mode_readonly(self, parser):
        args = parser.parse_args(
            ["run", "--agent", "x", "--goal", "y", "--mode", "read-only"]
        )
        assert args.mode == "read-only"

    def test_run_mode_invalid_raises(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(
                ["run", "--agent", "x", "--goal", "y", "--mode", "invalid"]
            )

    def test_run_interactive_flag(self, parser):
        args = parser.parse_args(["run", "--agent", "x", "--goal", "y", "-i"])
        assert args.interactive is True

    def test_run_interactive_long_flag(self, parser):
        args = parser.parse_args(
            ["run", "--agent", "x", "--goal", "y", "--interactive"]
        )
        assert args.interactive is True

    def test_run_interactive_default_false(self, parser):
        args = parser.parse_args(["run", "--agent", "x", "--goal", "y"])
        assert args.interactive is False

    def test_run_resume_session(self, parser):
        args = parser.parse_args(
            ["run", "--agent", "x", "--goal", "y", "--resume-session", "abc-123"]
        )
        assert args.resume_session == "abc-123"

    def test_run_resume_session_default_none(self, parser):
        args = parser.parse_args(["run", "--agent", "x", "--goal", "y"])
        assert args.resume_session is None

    def test_run_max_turns(self, parser):
        args = parser.parse_args(
            ["run", "--agent", "x", "--goal", "y", "--max-turns", "5"]
        )
        assert args.max_turns == 5

    def test_run_max_turns_default_none(self, parser):
        args = parser.parse_args(["run", "--agent", "x", "--goal", "y"])
        assert args.max_turns is None

    def test_run_budget(self, parser):
        args = parser.parse_args(
            ["run", "--agent", "x", "--goal", "y", "--budget", "100.0"]
        )
        assert args.budget == 100.0

    def test_run_budget_default_none(self, parser):
        args = parser.parse_args(["run", "--agent", "x", "--goal", "y"])
        assert args.budget is None

    def test_run_effort_low(self, parser):
        args = parser.parse_args(
            ["run", "--agent", "x", "--goal", "y", "--effort", "low"]
        )
        assert args.effort == "low"

    def test_run_effort_medium(self, parser):
        args = parser.parse_args(
            ["run", "--agent", "x", "--goal", "y", "--effort", "medium"]
        )
        assert args.effort == "medium"

    def test_run_effort_high(self, parser):
        args = parser.parse_args(
            ["run", "--agent", "x", "--goal", "y", "--effort", "high"]
        )
        assert args.effort == "high"

    def test_run_effort_invalid_raises(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(
                ["run", "--agent", "x", "--goal", "y", "--effort", "invalid"]
            )

    def test_run_effort_default_none(self, parser):
        args = parser.parse_args(["run", "--agent", "x", "--goal", "y"])
        assert args.effort is None

    def test_run_output_format_text(self, parser):
        args = parser.parse_args(
            ["run", "--agent", "x", "--goal", "y", "--output-format", "text"]
        )
        assert args.output_format == "text"

    def test_run_output_format_json(self, parser):
        args = parser.parse_args(
            ["run", "--agent", "x", "--goal", "y", "--output-format", "json"]
        )
        assert args.output_format == "json"

    def test_run_output_format_stream_json(self, parser):
        args = parser.parse_args(
            ["run", "--agent", "x", "--goal", "y", "--output-format", "stream-json"]
        )
        assert args.output_format == "stream-json"

    def test_run_output_format_invalid_raises(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(
                ["run", "--agent", "x", "--goal", "y", "--output-format", "invalid"]
            )

    def test_run_output_format_default_none(self, parser):
        args = parser.parse_args(["run", "--agent", "x", "--goal", "y"])
        assert args.output_format is None

    def test_run_context_single(self, parser):
        args = parser.parse_args(
            ["run", "--agent", "x", "--goal", "y", "--context", "a.md"]
        )
        assert args.context == ["a.md"]

    def test_run_context_multiple(self, parser):
        args = parser.parse_args(
            [
                "run",
                "--agent",
                "x",
                "--goal",
                "y",
                "--context",
                "a.md",
                "--context",
                "b.md",
            ]
        )
        assert args.context == ["a.md", "b.md"]

    def test_run_context_default_none(self, parser):
        args = parser.parse_args(["run", "--agent", "x", "--goal", "y"])
        assert args.context is None

    def test_run_plan_flag(self, parser):
        args = parser.parse_args(["run", "--agent", "x", "--plan", "plan.md"])
        assert args.plan == "plan.md"

    def test_run_plan_default_none(self, parser):
        args = parser.parse_args(["run", "--agent", "x", "--goal", "y"])
        assert args.plan is None

    def test_run_mcp_servers(self, parser):
        json_str = '{"s":{"cmd":"x"}}'
        args = parser.parse_args(
            ["run", "--agent", "x", "--goal", "y", "--mcp-servers", json_str]
        )
        assert args.mcp_servers == json_str

    def test_run_mcp_servers_default_none(self, parser):
        args = parser.parse_args(["run", "--agent", "x", "--goal", "y"])
        assert args.mcp_servers is None

    def test_run_task_legacy_flag(self, parser):
        args = parser.parse_args(["run", "--agent", "x", "--task", "do something"])
        assert args.task == "do something"

    def test_run_task_short_flag(self, parser):
        args = parser.parse_args(["run", "-a", "x", "-t", "do something"])
        assert args.task == "do something"

    def test_run_task_file_flag(self, parser):
        args = parser.parse_args(
            ["run", "--agent", "x", "--goal", "y", "--task-file", "task.md"]
        )
        assert args.task_file == "task.md"

    def test_run_task_file_short_flag(self, parser):
        args = parser.parse_args(["run", "-a", "x", "--goal", "y", "-f", "task.md"])
        assert args.task_file == "task.md"


# ===================================================================
# TestSubagentA2aServeArgs — direct parser tests for `a2a-serve`
# ===================================================================


class TestSubagentA2aServeArgs:
    """Test argparse configuration for the `a2a-serve` subcommand."""

    @pytest.fixture()
    def parser(self):
        """Return the real subagent_cli argument parser."""
        from ... import subagent_cli

        return subagent_cli._make_parser()

    def test_a2a_serve_defaults(self, parser):
        args = parser.parse_args(["a2a-serve"])
        assert args.command == "a2a-serve"
        assert args.executor == "claude"
        assert args.port == 10010
        assert args.agent == "vaultspec-researcher"
        assert args.mode == "read-only"

    def test_a2a_serve_custom_executor(self, parser):
        args = parser.parse_args(["a2a-serve", "--executor", "gemini"])
        assert args.executor == "gemini"

    def test_a2a_serve_custom_port(self, parser):
        args = parser.parse_args(["a2a-serve", "--port", "9999"])
        assert args.port == 9999

    def test_a2a_serve_custom_agent(self, parser):
        args = parser.parse_args(["a2a-serve", "--agent", "my-agent"])
        assert args.agent == "my-agent"

    def test_a2a_serve_custom_model(self, parser):
        args = parser.parse_args(["a2a-serve", "--model", "custom-model"])
        assert args.model == "custom-model"

    def test_a2a_serve_model_default_none(self, parser):
        args = parser.parse_args(["a2a-serve"])
        assert args.model is None

    def test_a2a_serve_custom_mode(self, parser):
        args = parser.parse_args(["a2a-serve", "--mode", "read-write"])
        assert args.mode == "read-write"

    def test_a2a_serve_all_custom(self, parser):
        args = parser.parse_args(
            [
                "a2a-serve",
                "--executor",
                "gemini",
                "--port",
                "9999",
                "--agent",
                "my-agent",
                "--model",
                "custom",
                "--mode",
                "read-write",
            ]
        )
        assert args.executor == "gemini"
        assert args.port == 9999
        assert args.agent == "my-agent"
        assert args.model == "custom"
        assert args.mode == "read-write"

    def test_a2a_serve_invalid_executor_raises(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["a2a-serve", "--executor", "invalid"])

    def test_a2a_serve_invalid_mode_raises(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["a2a-serve", "--mode", "invalid"])

    def test_a2a_serve_short_flags(self, parser):
        args = parser.parse_args(
            ["a2a-serve", "-e", "gemini", "-a", "my-agent", "-m", "fast"]
        )
        assert args.executor == "gemini"
        assert args.agent == "my-agent"
        assert args.model == "fast"


# ===================================================================
# TestSubagentOtherSubcommands — serve and list
# ===================================================================


class TestSubagentOtherSubcommands:
    """Test argparse configuration for `serve` and `list` subcommands."""

    @pytest.fixture()
    def parser(self):
        from ... import subagent_cli

        return subagent_cli._make_parser()

    def test_serve_command(self, parser):
        args = parser.parse_args(["serve"])
        assert args.command == "serve"

    def test_list_command(self, parser):
        args = parser.parse_args(["list"])
        assert args.command == "list"

    def test_no_subcommand_raises(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args([])


# ===================================================================
# TestSubagentValidation — subprocess-based validation error paths
# ===================================================================


class TestSubagentValidation:
    """Test validation error paths via subprocess invocation."""

    def test_run_without_agent_errors(self):
        result = run_subagent("run", "--goal", "x")
        assert result.returncode != 0

    def test_run_without_goal_or_plan_errors(self):
        result = run_subagent("run", "--agent", "x")
        assert result.returncode != 0

    def test_command_required(self):
        result = run_subagent()
        assert result.returncode != 0

    def test_run_invalid_provider_errors(self):
        result = run_subagent(
            "run", "--agent", "x", "--goal", "y", "--provider", "invalid"
        )
        assert result.returncode != 0

    def test_run_invalid_effort_errors(self):
        result = run_subagent(
            "run", "--agent", "x", "--goal", "y", "--effort", "invalid"
        )
        assert result.returncode != 0

    def test_run_invalid_output_format_errors(self):
        result = run_subagent(
            "run", "--agent", "x", "--goal", "y", "--output-format", "invalid"
        )
        assert result.returncode != 0

    def test_a2a_serve_invalid_executor_errors(self):
        result = run_subagent("a2a-serve", "--executor", "invalid")
        assert result.returncode != 0


# ===================================================================
# TestSubagentHelpText — subprocess-based help verification
# ===================================================================


class TestSubagentHelpText:
    """Test --help output across subcommands."""

    def test_main_help(self):
        result = run_subagent("--help")
        assert result.returncode == 0
        assert "Sub-agent CLI" in result.stdout

    def test_run_help(self):
        result = run_subagent("run", "--help")
        assert result.returncode == 0
        assert "--agent" in result.stdout
        assert "--goal" in result.stdout
        assert "--model" in result.stdout
        assert "--provider" in result.stdout
        assert "--mode" in result.stdout
        assert "--interactive" in result.stdout
        assert "--resume-session" in result.stdout
        assert "--max-turns" in result.stdout
        assert "--budget" in result.stdout
        assert "--effort" in result.stdout
        assert "--output-format" in result.stdout
        assert "--context" in result.stdout
        assert "--plan" in result.stdout
        assert "--mcp-servers" in result.stdout

    def test_a2a_serve_help(self):
        result = run_subagent("a2a-serve", "--help")
        assert result.returncode == 0
        assert "--executor" in result.stdout
        assert "--port" in result.stdout
        assert "--agent" in result.stdout
        assert "--model" in result.stdout
        assert "--mode" in result.stdout

    def test_serve_help(self):
        result = run_subagent("serve", "--help")
        assert result.returncode == 0

    def test_list_help(self):
        result = run_subagent("list", "--help")
        assert result.returncode == 0
