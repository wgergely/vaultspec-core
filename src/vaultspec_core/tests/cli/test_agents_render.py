"""Per-provider agent render tests for #76.

Covers the renderer factory in :mod:`vaultspec_core.core.agents`:
``transform_agent`` dispatch, ``_render_claude_agent``,
``_render_gemini_agent``, the Claude->Gemini tool mapping, and a
parametrized regression guard over every source agent under
``.vaultspec/rules/agents/``.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from vaultspec_core.core.agents import (
    _CLAUDE_TO_GEMINI_TOOLS,
    _render_claude_agent,
    _render_gemini_agent,
    _render_passthrough_agent,
    transform_agent,
)
from vaultspec_core.core.enums import GeminiBuiltinTool, Tool
from vaultspec_core.vaultcore import parse_frontmatter

pytestmark = [pytest.mark.unit]


_REPO_ROOT = Path(__file__).resolve().parents[4]
_AGENTS_SRC = _REPO_ROOT / ".vaultspec" / "rules" / "agents"
_GEMINI_TOOL_SET = frozenset(t.value for t in GeminiBuiltinTool)

# URL of the upstream gemini-cli source file that defines the canonical
# tool name string constants. The live drift test below fetches this
# file and asserts every `GeminiBuiltinTool` enum value still matches
# the corresponding `*_TOOL_NAME` constant.
_UPSTREAM_BASE_DECLARATIONS_URL = (
    "https://raw.githubusercontent.com/google-gemini/gemini-cli/main/"
    "packages/core/src/tools/definitions/base-declarations.ts"
)

# Mapping from `GeminiBuiltinTool` member name -> upstream constant
# name in `base-declarations.ts`. The live test fetches the file,
# parses each constant's string value with the regex below, and
# asserts equality.
_ENUM_TO_UPSTREAM_CONSTANT: dict[GeminiBuiltinTool, str] = {
    GeminiBuiltinTool.GLOB: "GLOB_TOOL_NAME",
    GeminiBuiltinTool.GREP_SEARCH: "GREP_TOOL_NAME",
    GeminiBuiltinTool.READ_FILE: "READ_FILE_TOOL_NAME",
    GeminiBuiltinTool.RUN_SHELL_COMMAND: "SHELL_TOOL_NAME",
    GeminiBuiltinTool.WRITE_FILE: "WRITE_FILE_TOOL_NAME",
    GeminiBuiltinTool.REPLACE: "EDIT_TOOL_NAME",
    GeminiBuiltinTool.GOOGLE_WEB_SEARCH: "WEB_SEARCH_TOOL_NAME",
    GeminiBuiltinTool.WEB_FETCH: "WEB_FETCH_TOOL_NAME",
}

_TOOL_NAME_DECL_RE = re.compile(
    r"export\s+const\s+(?P<name>[A-Z_]+_TOOL_NAME)\s*[:=]\s*"
    r"(?:[A-Za-z]+\s*=\s*)?['\"](?P<value>[^'\"]+)['\"]",
)


def _fm(rendered: str) -> dict[str, object]:
    meta, _body = parse_frontmatter(rendered)
    return meta


class TestRenderClaudeAgent:
    def test_injects_name_from_filename_stem(self):
        out = _render_claude_agent("vaultspec-researcher.md", {}, "body")
        assert _fm(out)["name"] == "vaultspec-researcher"

    def test_preserves_description(self):
        out = _render_claude_agent("x.md", {"description": "Hello world"}, "body")
        assert _fm(out)["description"] == "Hello world"

    def test_preserves_tools_verbatim(self):
        meta = {"tools": ["Glob", "Grep", "Read", "Bash"]}
        out = _render_claude_agent("x.md", meta, "body")
        assert _fm(out)["tools"] == ["Glob", "Grep", "Read", "Bash"]

    def test_drops_authoring_keys(self):
        meta = {"tier": "HIGH", "mode": "read-write"}
        rendered_meta = _fm(_render_claude_agent("x.md", meta, "body"))
        assert "tier" not in rendered_meta
        assert "mode" not in rendered_meta

    def test_preserves_model_when_set(self):
        out = _render_claude_agent("x.md", {"model": "claude-opus-4-6"}, "body")
        assert _fm(out)["model"] == "claude-opus-4-6"

    def test_omits_optional_keys_when_absent(self):
        rendered_meta = _fm(_render_claude_agent("x.md", {}, "body"))
        assert rendered_meta == {"name": "x"}

    def test_body_is_preserved(self):
        out = _render_claude_agent("x.md", {}, "# Heading\n\ncontent")
        assert "# Heading\n\ncontent" in out


class TestRenderGeminiAgent:
    def test_injects_name(self):
        out = _render_gemini_agent("vaultspec-writer.md", {}, "body")
        assert _fm(out)["name"] == "vaultspec-writer"

    def test_preserves_description(self):
        out = _render_gemini_agent("x.md", {"description": "An agent"}, "body")
        assert _fm(out)["description"] == "An agent"

    def test_maps_every_known_tool(self):
        meta = {"tools": list(_CLAUDE_TO_GEMINI_TOOLS.keys())}
        out = _render_gemini_agent("x.md", meta, "body")
        assert _fm(out)["tools"] == list(_CLAUDE_TO_GEMINI_TOOLS.values())

    def test_drops_authoring_keys(self):
        meta = {"tier": "MEDIUM", "mode": "read-only", "tools": ["Read"]}
        rendered_meta = _fm(_render_gemini_agent("x.md", meta, "body"))
        assert "tier" not in rendered_meta
        assert "mode" not in rendered_meta

    def test_drops_unknown_tool_and_warns(self):
        warnings: list[str] = []
        meta = {"tools": ["Read", "BogusTool", "Bash"]}
        out = _render_gemini_agent("vaultspec-x.md", meta, "body", warnings=warnings)
        assert _fm(out)["tools"] == ["read_file", "run_shell_command"]
        assert any("BogusTool" in w for w in warnings)
        assert any("vaultspec-x" in w for w in warnings)

    def test_unknown_tool_without_warnings_accumulator(self):
        meta = {"tools": ["BogusTool"]}
        rendered_meta = _fm(_render_gemini_agent("x.md", meta, "body"))
        assert "tools" not in rendered_meta

    def test_empty_tools_list(self):
        rendered_meta = _fm(_render_gemini_agent("x.md", {"tools": []}, "body"))
        assert "tools" not in rendered_meta

    def test_no_tools_key(self):
        rendered_meta = _fm(_render_gemini_agent("x.md", {}, "body"))
        assert "tools" not in rendered_meta

    def test_non_string_tool_entries_ignored(self):
        meta = {"tools": ["Read", 42, None, "Grep"]}
        out = _render_gemini_agent("x.md", meta, "body")
        assert _fm(out)["tools"] == ["read_file", "grep_search"]


class TestTransformAgentDispatch:
    def test_claude_routes_to_claude_renderer(self):
        meta = {"tier": "HIGH", "tools": ["Glob"]}
        rendered_meta = _fm(transform_agent(Tool.CLAUDE, "a.md", meta, "body"))
        assert rendered_meta["name"] == "a"
        assert rendered_meta["tools"] == ["Glob"]
        assert "tier" not in rendered_meta

    def test_gemini_routes_to_gemini_renderer(self):
        meta = {"tier": "HIGH", "tools": ["Glob"]}
        rendered_meta = _fm(transform_agent(Tool.GEMINI, "a.md", meta, "body"))
        assert rendered_meta["name"] == "a"
        assert rendered_meta["tools"] == ["glob"]
        assert "tier" not in rendered_meta

    def test_unregistered_tool_falls_through_to_passthrough(self):
        meta = {"tier": "X", "tools": ["whatever"]}
        rendered_meta = _fm(transform_agent(Tool.ANTIGRAVITY, "a.md", meta, "body"))
        # Passthrough preserves source frontmatter, including authoring keys.
        assert rendered_meta["tier"] == "X"
        assert rendered_meta["tools"] == ["whatever"]

    def test_string_tool_name_is_coerced(self):
        rendered_meta = _fm(
            transform_agent("gemini", "a.md", {"tools": ["Read"]}, "body")
        )
        assert rendered_meta["tools"] == ["read_file"]

    def test_warnings_threaded_through(self):
        warnings: list[str] = []
        transform_agent(
            Tool.GEMINI,
            "a.md",
            {"tools": ["Bogus"]},
            "body",
            warnings=warnings,
        )
        assert warnings  # gemini renderer wrote into the accumulator

    def test_passthrough_renderer_ignores_warnings_kwarg(self):
        # Regression: every renderer in the registry must accept the
        # keyword-only `warnings` arg even when it does not use it.
        warnings: list[str] = []
        out = _render_passthrough_agent(
            "a.md", {"tools": ["Read"]}, "body", warnings=warnings
        )
        assert "Read" in out
        assert warnings == []


def _source_agent_files() -> list[Path]:
    if not _AGENTS_SRC.exists():
        return []
    return sorted(_AGENTS_SRC.glob("*.md"))


# Fail loudly at collection time rather than silently producing zero
# parametrized tests if the source-agent directory is ever moved or empty.
_SOURCE_AGENTS = _source_agent_files()
assert _SOURCE_AGENTS, (
    f"No source agents found under {_AGENTS_SRC}; the parametrized "
    "regression guard would silently produce zero tests."
)


@pytest.mark.parametrize("agent_path", _SOURCE_AGENTS, ids=lambda p: p.name)
class TestSourceAgentCoverage:
    """Regression guard: every shipped source agent renders cleanly."""

    def test_gemini_render_satisfies_schema(self, agent_path: Path):
        meta, body = parse_frontmatter(agent_path.read_text(encoding="utf-8"))
        warnings: list[str] = []
        rendered = transform_agent(
            Tool.GEMINI, agent_path.name, meta, body, warnings=warnings
        )
        rendered_meta = _fm(rendered)

        assert rendered_meta.get("name") == agent_path.stem
        assert "tier" not in rendered_meta
        assert "mode" not in rendered_meta

        rendered_tools = rendered_meta.get("tools", [])
        assert isinstance(rendered_tools, list)
        for tool_name in rendered_tools:
            assert tool_name in _GEMINI_TOOL_SET, (
                f"{agent_path.name}: rendered tool {tool_name!r} is not "
                f"in the Gemini tool vocabulary"
            )

        # No source agent should currently produce a warning. If this
        # ever fails, the source file uses a Claude tool name that
        # has no Gemini mapping; either map it or remove it from the
        # source.
        assert warnings == [], f"{agent_path.name}: {warnings}"

    def test_claude_render_strips_authoring_keys(self, agent_path: Path):
        meta, body = parse_frontmatter(agent_path.read_text(encoding="utf-8"))
        rendered = transform_agent(Tool.CLAUDE, agent_path.name, meta, body)
        rendered_meta = _fm(rendered)
        assert rendered_meta.get("name") == agent_path.stem
        assert "tier" not in rendered_meta
        assert "mode" not in rendered_meta


def _fetch_upstream_base_declarations() -> str:
    """Fetch `base-declarations.ts` from gemini-cli main.

    Hard-fails on any network or HTTP error. The integration marker on
    the calling test class is the opt-in gate; once selected, the test
    must reach upstream and verify the constants.
    """
    req = urllib.request.Request(
        _UPSTREAM_BASE_DECLARATIONS_URL,
        headers={"User-Agent": "vaultspec-core-tests"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


@pytest.mark.integration
class TestUpstreamGeminiToolPin:
    """Live drift guard against `google-gemini/gemini-cli` main.

    Fetches `packages/core/src/tools/definitions/base-declarations.ts`
    from the upstream main branch, parses every `*_TOOL_NAME` constant,
    and asserts that every `GeminiBuiltinTool` enum value still equals
    the corresponding upstream constant. Any drift fails immediately.
    """

    @pytest.fixture(scope="class")
    def upstream_constants(self) -> dict[str, str]:
        source = _fetch_upstream_base_declarations()
        constants: dict[str, str] = {}
        for match in _TOOL_NAME_DECL_RE.finditer(source):
            constants[match.group("name")] = match.group("value")
        assert constants, (
            "regex failed to extract any *_TOOL_NAME constants from upstream "
            "base-declarations.ts; the upstream file format may have changed"
        )
        return constants

    @pytest.mark.parametrize(
        "enum_member",
        list(_ENUM_TO_UPSTREAM_CONSTANT.keys()),
        ids=lambda m: m.name,
    )
    def test_enum_value_matches_upstream(
        self,
        enum_member: GeminiBuiltinTool,
        upstream_constants: dict[str, str],
    ):
        upstream_name = _ENUM_TO_UPSTREAM_CONSTANT[enum_member]
        assert upstream_name in upstream_constants, (
            f"upstream constant {upstream_name!r} not found in "
            f"base-declarations.ts; the upstream file may have removed or "
            f"renamed it"
        )
        upstream_value = upstream_constants[upstream_name]
        assert enum_member.value == upstream_value, (
            f"GeminiBuiltinTool.{enum_member.name} drift: "
            f"local={enum_member.value!r} upstream={upstream_value!r} "
            f"({upstream_name})"
        )

    def test_no_local_enum_member_is_orphaned(self, upstream_constants: dict[str, str]):
        for member in GeminiBuiltinTool:
            assert member in _ENUM_TO_UPSTREAM_CONSTANT, (
                f"GeminiBuiltinTool.{member.name} has no entry in "
                f"_ENUM_TO_UPSTREAM_CONSTANT; add the upstream constant "
                f"name so the live drift test can verify it"
            )


@pytest.mark.gemini
@pytest.mark.integration
class TestGeminiCliLoadsRenderedAgents:
    """Live load test: invoke real `gemini` CLI against rendered agents.

    For each source agent under `.vaultspec/rules/agents/`:
      1. render via `transform_agent(Tool.GEMINI, ...)`
      2. write the result into a tmp `.gemini/agents/` directory
      3. invoke `gemini -p "<probe>"` with the tmp dir as CWD - this
         triggers full session startup, which is the only path that
         actually validates local agent definitions; ``--version``,
         ``mcp list``, ``extensions list`` etc. exit before the
         agentLoader runs.
      4. assert no `Agent loading error` / `Invalid tool name` lines
         appear in the combined stdout/stderr.

    The `@pytest.mark.gemini` marker is the opt-in gate; the test
    asserts the binary is present once the marker selects it.

    The probe also verifies the bogus agent path actually fails: a
    deliberately broken agent file is written alongside the rendered
    ones, gemini is invoked once with both, and the test asserts that
    the broken agent shows up in the error list AND that none of the
    rendered ones do. This prevents false greens from a probe command
    that does not actually load agents.
    """

    _PROBE_PROMPT = "respond with only the word READY"

    def _invoke_gemini(self, gemini_bin: str, cwd: Path) -> tuple[str, list[str]]:
        env = os.environ.copy()
        env["NO_COLOR"] = "1"
        env["CI"] = "1"
        result = subprocess.run(
            [gemini_bin, "-p", self._PROBE_PROMPT],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        errors = [
            line
            for line in combined.splitlines()
            if "Agent loading error" in line or "Invalid tool name" in line
        ]
        return combined, errors

    def test_all_source_agents_load(self, tmp_path: Path):
        gemini_bin = shutil.which("gemini")
        assert gemini_bin is not None, (
            "gemini CLI not on PATH; the @pytest.mark.gemini marker is the "
            "opt-in gate - install gemini-cli before running this marker"
        )

        agents_dir = tmp_path / ".gemini" / "agents"
        agents_dir.mkdir(parents=True)

        # Render every shipped source agent.
        rendered_names: set[str] = set()
        for agent_path in _SOURCE_AGENTS:
            meta, body = parse_frontmatter(agent_path.read_text(encoding="utf-8"))
            rendered = transform_agent(Tool.GEMINI, agent_path.name, meta, body)
            (agents_dir / agent_path.name).write_text(rendered, encoding="utf-8")
            rendered_names.add(agent_path.stem)

        # Plant a deliberately invalid agent so we can prove the probe
        # actually triggers agent validation in this gemini build. Without
        # this canary a future gemini change that defers loading would
        # silently turn the test into a no-op.
        canary_name = "vaultspec-render-canary-invalid"
        (agents_dir / f"{canary_name}.md").write_text(
            "---\n"
            f"name: {canary_name}\n"
            "description: deliberately invalid; proves the probe loads agents\n"
            "tools: [zzz_definitely_not_a_real_gemini_tool]\n"
            "---\n\nx\n",
            encoding="utf-8",
        )

        _combined, errors = self._invoke_gemini(gemini_bin, tmp_path)

        # The canary MUST show up in errors; if it doesn't, the probe is
        # not actually loading agents and the test is a false green.
        canary_hit = [e for e in errors if canary_name in e]
        assert canary_hit, (
            "Canary check failed: gemini did not emit an Agent loading error "
            f"for the deliberately broken {canary_name}.md. The probe command "
            "no longer triggers agent validation; update the test."
        )

        # Every rendered shipped agent must be absent from the error list.
        offenders = [
            line for line in errors if any(name in line for name in rendered_names)
        ]
        assert not offenders, (
            "gemini CLI rejected at least one rendered shipped agent:\n"
            + "\n".join(offenders)
        )
