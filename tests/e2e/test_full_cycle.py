"""Full-cycle SDD pipeline tests.

Tests the complete Research -> ADR -> Plan workflow using both Claude and
Gemini providers against test-project/.vault/.

Each test independently runs a multi-step pipeline dispatching real agents
to research French fairy tales, create an ADR, write an implementation
plan, and produce a short story.

Requires:
- Provider CLI installed and authenticated
- Network access to LLM API
"""

from __future__ import annotations

import shutil
from datetime import date
from typing import TYPE_CHECKING

import pytest

from tests.constants import TEST_PROJECT
from vaultspec.orchestration.subagent import run_subagent
from vaultspec.protocol.acp import SubagentResult
from vaultspec.protocol.providers import ClaudeProvider, GeminiProvider
from vaultspec.vaultcore import parse_frontmatter

if TYPE_CHECKING:
    from pathlib import Path

_has_claude_cli = shutil.which("claude") is not None
_has_gemini_cli = shutil.which("gemini") is not None

TODAY = date.today().isoformat()  # yyyy-mm-dd


def _cleanup_test_project(root: Path) -> None:
    """Remove all transient artifacts, preserving .vault/ and README.md."""
    for item in root.iterdir():
        if item.name in (".vault", "README.md", ".gitignore"):
            continue
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)


@pytest.fixture
def pipeline_root():
    """Set up test-project for full pipeline execution."""
    root = TEST_PROJECT
    # Create workspace structure
    (root / ".vaultspec" / "rules" / "agents").mkdir(parents=True, exist_ok=True)
    (root / ".vaultspec" / "rules").mkdir(parents=True, exist_ok=True)
    (root / ".vaultspec" / "rules" / "templates").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "rules").mkdir(parents=True, exist_ok=True)
    (root / ".gemini" / "rules").mkdir(parents=True, exist_ok=True)
    (root / ".gemini" / "settings.json").write_text("{}", encoding="utf-8")

    # Ensure vault output dirs exist
    for doc_type in ("research", "adr", "plan"):
        (root / ".vault" / doc_type).mkdir(parents=True, exist_ok=True)

    yield root
    _cleanup_test_project(root)


def _find_new_docs(vault_dir: Path, doc_type: str, feature: str) -> list[Path]:
    """Find documents matching a feature tag in a vault subdirectory."""
    target = vault_dir / doc_type
    if not target.exists():
        return []
    return [f for f in target.glob("*.md") if feature in f.name]


def _validate_frontmatter(doc_path: Path):
    """Validate a vault document has proper frontmatter."""
    content = doc_path.read_text(encoding="utf-8")
    meta, _body = parse_frontmatter(content)

    # Check tags exist
    tags = meta.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]
    assert len(tags) > 0, f"{doc_path.name} has no tags"

    # Check date exists and is valid format
    assert "date" in meta, f"Document {doc_path.name} missing 'date' in frontmatter"


def _write_researcher_agent(root: Path) -> None:
    """Write the researcher agent definition to the workspace."""
    agent_file = root / ".vaultspec" / "rules" / "agents" / "vaultspec-researcher.md"
    agent_file.write_text(
        "---\n"
        "tier: MEDIUM\n"
        "mode: read-write\n"
        "---\n\n"
        "# Persona\n"
        "You are Jean-Claude, a literary researcher "
        "specializing in French fairy tales.\n"
        "Your name is Jean-Claude. "
        "Always introduce yourself by name.\n"
        "You write concise research documents.\n"
        "When asked to persist findings, create a "
        "markdown file with YAML frontmatter.\n",
        encoding="utf-8",
    )


async def _run_research_step(
    root: Path, provider, feature: str = "fairy-tales"
) -> SubagentResult:
    """Step 1: Research French fairy tales."""
    _write_researcher_agent(root)

    return await run_subagent(
        agent_name="vaultspec-researcher",
        root_dir=root,
        initial_task=(
            f"Research French fairy tales by Charles Perrault. "
            f"Write a brief research summary (100 words max) and save it to "
            f".vault/research/{TODAY}-{feature}-research.md "
            f"The file MUST have this exact YAML frontmatter:\n"
            f"---\n"
            f'tags: ["#research", "#{feature}"]\n'
            f"date: {TODAY}\n"
            f"related: []\n"
            f"---\n"
            f"Then write the research content below the frontmatter."
        ),
        provider_instance=provider,
        interactive=False,
        debug=True,
    )


async def _run_adr_step(
    root: Path, provider, feature: str = "fairy-tales"
) -> SubagentResult:
    """Step 2: Create ADR from research."""
    return await run_subagent(
        agent_name="vaultspec-researcher",
        root_dir=root,
        initial_task=(
            f"Based on the research at .vault/research/{TODAY}-{feature}-research.md, "
            f"create an Architecture Decision Record. "
            f"Write a brief ADR (100 words max) and save it to "
            f".vault/adr/{TODAY}-{feature}-adr.md "
            f"The file MUST have this exact YAML frontmatter:\n"
            f"---\n"
            f'tags: ["#adr", "#{feature}"]\n'
            f"date: {TODAY}\n"
            f'related: ["[[{TODAY}-{feature}-research.md]]"]\n'
            f"---\n"
            f"Then write the ADR content below the frontmatter."
        ),
        provider_instance=provider,
        interactive=False,
        debug=True,
    )


async def _run_plan_step(
    root: Path, provider, feature: str = "fairy-tales"
) -> SubagentResult:
    """Step 3: Write implementation plan."""
    return await run_subagent(
        agent_name="vaultspec-researcher",
        root_dir=root,
        initial_task=(
            f"Based on the ADR at .vault/adr/{TODAY}-{feature}-adr.md, "
            f"create an implementation plan for writing a 150-word story "
            f"based on a French fairy tale by Charles Perrault. "
            f"Save the plan to .vault/plan/{TODAY}-{feature}-plan.md "
            f"The file MUST have this exact YAML frontmatter:\n"
            f"---\n"
            f'tags: ["#plan", "#{feature}"]\n'
            f"date: {TODAY}\n"
            f'related: ["[[{TODAY}-{feature}-adr.md]]"]\n'
            f"---\n"
            f"Then write the plan content below the frontmatter."
        ),
        provider_instance=provider,
        interactive=False,
        debug=True,
    )


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.skipif(not _has_gemini_cli, reason="Gemini CLI not installed")
@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_full_cycle_gemini(pipeline_root):
    """Full SDD cycle via Gemini: research -> ADR -> plan."""
    provider = GeminiProvider()
    feature = "fairy-tales"

    # Step 1: Research
    result = await _run_research_step(pipeline_root, provider, feature)
    assert isinstance(result, SubagentResult)
    assert result.session_id is not None

    research_docs = _find_new_docs(pipeline_root / ".vault", "research", feature)
    assert len(research_docs) >= 1, "Research document not created in .vault/research/"

    # Step 2: ADR
    result = await _run_adr_step(pipeline_root, provider, feature)
    assert isinstance(result, SubagentResult)

    adr_docs = _find_new_docs(pipeline_root / ".vault", "adr", feature)
    assert len(adr_docs) >= 1, "ADR document not created in .vault/adr/"

    # Step 3: Plan
    result = await _run_plan_step(pipeline_root, provider, feature)
    assert isinstance(result, SubagentResult)

    plan_docs = _find_new_docs(pipeline_root / ".vault", "plan", feature)
    assert len(plan_docs) >= 1, "Plan document not created in .vault/plan/"

    # Validate frontmatter on all created documents
    for doc in research_docs + adr_docs + plan_docs:
        _validate_frontmatter(doc)


@pytest.mark.integration
@pytest.mark.claude
@pytest.mark.skipif(not _has_claude_cli, reason="Claude CLI not installed")
@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_full_cycle_claude(pipeline_root):
    """Full SDD cycle via Claude: research -> ADR -> plan."""
    provider = ClaudeProvider()
    feature = "fairy-tales"

    # Step 1: Research
    result = await _run_research_step(pipeline_root, provider, feature)
    assert isinstance(result, SubagentResult)
    assert result.session_id is not None

    research_docs = _find_new_docs(pipeline_root / ".vault", "research", feature)
    assert len(research_docs) >= 1, "Research document not created in .vault/research/"

    # Step 2: ADR
    result = await _run_adr_step(pipeline_root, provider, feature)
    assert isinstance(result, SubagentResult)

    adr_docs = _find_new_docs(pipeline_root / ".vault", "adr", feature)
    assert len(adr_docs) >= 1, "ADR document not created in .vault/adr/"

    # Step 3: Plan
    result = await _run_plan_step(pipeline_root, provider, feature)
    assert isinstance(result, SubagentResult)

    plan_docs = _find_new_docs(pipeline_root / ".vault", "plan", feature)
    assert len(plan_docs) >= 1, "Plan document not created in .vault/plan/"

    # Validate frontmatter on all created documents
    for doc in research_docs + adr_docs + plan_docs:
        _validate_frontmatter(doc)


@pytest.mark.unit
def test_pipeline_root_has_vault_dirs(pipeline_root):
    """Verify pipeline fixture creates required vault subdirectories."""
    for doc_type in ("research", "adr", "plan"):
        assert (pipeline_root / ".vault" / doc_type).is_dir(), (
            f".vault/{doc_type} missing"
        )


@pytest.mark.unit
def test_find_new_docs_returns_matching(tmp_path):
    """Verify _find_new_docs helper finds feature-tagged documents."""
    vault = tmp_path / ".vault"
    target = vault / "research"
    target.mkdir(parents=True)
    (target / f"{TODAY}-fairy-tales-research.md").write_text(
        '---\ntags: ["#research", "#fairy-tales"]\ndate: ' + TODAY + "\n---\nContent",
        encoding="utf-8",
    )
    docs = _find_new_docs(vault, "research", "fairy-tales")
    assert len(docs) == 1


@pytest.mark.unit
def test_find_new_docs_ignores_unrelated(tmp_path):
    """Verify _find_new_docs does not return documents without the feature name."""
    vault = tmp_path / ".vault"
    target = vault / "research"
    target.mkdir(parents=True)
    (target / f"{TODAY}-unrelated-research.md").write_text(
        "---\ndate: " + TODAY + "\n---\nOther content",
        encoding="utf-8",
    )
    docs = _find_new_docs(vault, "research", "fairy-tales")
    assert len(docs) == 0


@pytest.mark.unit
def test_find_new_docs_empty_dir(tmp_path):
    """Verify _find_new_docs returns empty list for nonexistent subdirectory."""
    vault = tmp_path / ".vault"
    vault.mkdir()
    docs = _find_new_docs(vault, "nonexistent", "fairy-tales")
    assert docs == []


@pytest.mark.unit
def test_validate_frontmatter_passes_valid(tmp_path):
    """Verify _validate_frontmatter accepts properly structured documents."""
    target = tmp_path / "research"
    target.mkdir()
    doc = target / f"{TODAY}-fairy-tales-research.md"
    doc.write_text(
        '---\ntags: ["#research", "#fairy-tales"]\ndate: '
        + TODAY
        + "\nrelated: []\n---\nContent here.",
        encoding="utf-8",
    )
    # Should not raise
    _validate_frontmatter(doc)


@pytest.mark.unit
def test_validate_frontmatter_fails_missing_date(tmp_path):
    """Verify _validate_frontmatter rejects documents without a date field."""
    target = tmp_path / "research"
    target.mkdir()
    doc = target / f"{TODAY}-fairy-tales-no-date.md"
    doc.write_text(
        '---\ntags: ["#research", "#fairy-tales"]\n---\nNo date here.',
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="missing 'date'"):
        _validate_frontmatter(doc)


@pytest.mark.unit
def test_cleanup_preserves_vault(tmp_path):
    """Verify _cleanup_test_project keeps .vault/ and README.md."""
    root = tmp_path / "project"
    root.mkdir()
    (root / ".vault").mkdir()
    (root / "README.md").write_text("readme", encoding="utf-8")
    (root / ".gitignore").write_text("*", encoding="utf-8")

    # Create transient file and directory
    (root / "transient.txt").write_text("temp", encoding="utf-8")
    transient_dir = root / "transient_dir"
    transient_dir.mkdir()
    (transient_dir / "inner.txt").write_text("inner", encoding="utf-8")

    _cleanup_test_project(root)

    assert (root / ".vault").is_dir(), ".vault/ should survive cleanup"
    assert (root / "README.md").is_file(), "README.md should survive cleanup"
    assert (root / ".gitignore").is_file(), ".gitignore should survive cleanup"
    assert not (root / "transient.txt").exists(), "transient file should be removed"
    assert not transient_dir.exists(), "transient dir should be removed"


@pytest.mark.unit
def test_researcher_agent_written(tmp_path):
    """Verify _write_researcher_agent creates the agent definition file."""
    root = tmp_path / "project"
    (root / ".vaultspec" / "rules" / "agents").mkdir(parents=True)
    _write_researcher_agent(root)
    agent_file = root / ".vaultspec" / "rules" / "agents" / "vaultspec-researcher.md"
    assert agent_file.exists()
    content = agent_file.read_text(encoding="utf-8")
    assert "Jean-Claude" in content
    assert "tier: MEDIUM" in content
