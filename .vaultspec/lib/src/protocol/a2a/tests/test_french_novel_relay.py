"""3-turn collaborative French novel relay — real LLM integration test.

Exercises the full A2A relay pipeline with real Claude and Gemini executors:
Claude begins the story, Gemini continues, Claude writes the epilogue.
All turns go through TeamCoordinator using in-process A2A ASGI servers.

Markers:
- @pytest.mark.integration
- @pytest.mark.claude / @pytest.mark.gemini — require real CLIs on PATH
- @requires_anthropic / @requires_gemini — skip guards
"""

from __future__ import annotations

import re
import shutil
import time
from typing import TYPE_CHECKING

import httpx
import pytest
from tests.constants import PROJECT_ROOT as _TEST_ROOT

from orchestration.team import TeamCoordinator, extract_artifact_text
from protocol.a2a.server import create_app
from protocol.a2a.tests.conftest import _make_card
from protocol.providers.base import ClaudeModels, GeminiModels

if TYPE_CHECKING:
    from a2a.server.agent_execution import AgentExecutor

requires_anthropic = pytest.mark.skipif(
    not shutil.which("claude"),
    reason="Claude CLI not on PATH",
)

requires_gemini = pytest.mark.skipif(
    not shutil.which("gemini"),
    reason="Gemini CLI not on PATH",
)


# ===================================================================
# Module-level helpers
# ===================================================================


def _build_app_transport(executor, name: str, port: int) -> httpx.ASGITransport:
    """Build an httpx.ASGITransport backed by an in-process A2A app."""
    card = _make_card(name, port)
    app = create_app(executor, card)
    return httpx.ASGITransport(app=app)


async def _build_coordinator_with_apps(
    executors: list[tuple[AgentExecutor, str, int]],
    name: str = "relay-team",
) -> tuple[TeamCoordinator, list[str]]:
    """Bootstrap a TeamCoordinator with in-process ASGI agent apps."""
    mounts: dict[str, httpx.ASGITransport] = {}
    agent_urls: list[str] = []
    for executor, agent_name, port in executors:
        base_url = f"http://localhost:{port}"
        agent_urls.append(base_url + "/")
        transport = _build_app_transport(executor, agent_name, port)
        mounts[f"http://localhost:{port}/"] = transport
        mounts[f"http://localhost:{port}"] = transport

    coordinator = TeamCoordinator()
    coordinator._http_client = httpx.AsyncClient(mounts=mounts)
    await coordinator.form_team(name, agent_urls)
    return coordinator, agent_urls


# ===================================================================
# French prose validation
# ===================================================================

FRENCH_WORDS: frozenset[str] = frozenset(
    {
        "le",
        "la",
        "les",
        "un",
        "une",
        "de",
        "du",
        "des",
        "et",
        "est",
        "dans",
        "sur",
        "qui",
        "que",
        "pas",
        "avec",
        "pour",
        "mais",
    }
)


def _assert_french_prose(
    text: str,
    min_len: int = 100,
    max_len: int = 5000,
    check_character: bool = True,
) -> None:
    """Assert that *text* looks like a French prose paragraph.

    Checks:
    - Non-empty and within length bounds.
    - Contains at least 3 words from ``FRENCH_WORDS`` (case-insensitive).
    - Optionally contains "Croustillant" (character continuity check).

    Set *check_character* to ``False`` for turns where the LLM may use
    pronouns or synonyms instead of the character name verbatim.
    """
    assert text, "Response text is empty"
    assert len(text) >= min_len, (
        f"Response too short ({len(text)} chars, expected >={min_len}): {text!r}"
    )
    assert len(text) <= max_len, (
        f"Response too long ({len(text)} chars, expected <={max_len})"
    )

    words_found = sum(
        1
        for word in FRENCH_WORDS
        if re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE)
    )
    assert words_found >= 3, (
        f"Expected >=3 French indicator words, found {words_found}. "
        f"Text: {text[:200]!r}"
    )

    if check_character:
        assert "Croustillant" in text, (
            f"Character 'Croustillant' not found in response: {text[:200]!r}"
        )


# ===================================================================
# French story prompts
# ===================================================================

PROMPT_BEGIN = (
    "Tu es Jean-Claude, un critique pâtissier français avec un don pour "
    "l'écriture dramatique. Commence une histoire en français sur un croissant "
    "nommé Croustillant qui vit dans une boulangerie parisienne. Écris exactement "
    "un paragraphe (3-5 phrases). Termine par une situation de suspense. "
    "Réponds uniquement avec l'histoire, sans explication."
)

PROMPT_CONTINUE = (
    "Tu es Jean-Claude, un critique pâtissier français. Voici le début d'une "
    "histoire écrite par un collègue:\n\n"
    "{chapter_1}\n\n"
    "Continue cette histoire avec exactement un paragraphe (3-5 phrases). "
    "Croustillant doit rencontrer un nouveau personnage. Termine par un moment "
    "de tension. Réponds uniquement avec la suite de l'histoire."
)

PROMPT_FINISH = (
    "Tu es Jean-Claude, un critique pâtissier français. Voici une histoire en "
    "deux parties écrite collaborativement:\n\n"
    "{chapter_1}\n\n"
    "{chapter_2}\n\n"
    "Écris l'épilogue de cette histoire en exactement un paragraphe (3-5 phrases). "
    "Croustillant doit trouver une résolution. Réponds uniquement avec l'épilogue."
)


# ===================================================================
# Live test class — 3-turn relay with real LLM executors
# ===================================================================


@pytest.mark.integration
@pytest.mark.claude
@pytest.mark.gemini
@pytest.mark.timeout(300)
@requires_anthropic
@requires_gemini
class TestFrenchNovelRelayLive:
    """3-turn French story relay with real Claude and Gemini via A2A.

    Claude begins the story, Gemini continues, Claude writes the epilogue.
    Validates real French prose output and narrative coherence across agents.
    """

    @pytest.mark.asyncio
    async def test_three_turn_french_story(self):
        """GOLD STANDARD: Claude → Gemini → Claude creative relay in French."""
        from protocol.a2a.executors.claude_executor import ClaudeA2AExecutor
        from protocol.a2a.executors.gemini_executor import GeminiA2AExecutor

        claude_executor = ClaudeA2AExecutor(
            model=ClaudeModels.MEDIUM,
            root_dir=str(_TEST_ROOT),
            mode="read-only",
        )
        gemini_executor = GeminiA2AExecutor(
            root_dir=_TEST_ROOT,
            model=GeminiModels.LOW,
            agent_name="vaultspec-researcher",
        )

        coordinator, _ = await _build_coordinator_with_apps(
            [
                (claude_executor, "claude-relay", 10105),
                (gemini_executor, "gemini-relay", 10106),
            ],
            name="novel-relay-live",
        )

        relay_start = time.monotonic()

        try:
            session = coordinator.session
            agent_names = list(session.members.keys())
            assert len(agent_names) == 2
            claude_name = agent_names[0]
            gemini_name = agent_names[1]

            # Turn 1: Claude begins the story
            t1_start = time.monotonic()
            tasks_1 = await coordinator.dispatch_parallel({claude_name: PROMPT_BEGIN})
            t1_elapsed = time.monotonic() - t1_start
            task_1 = tasks_1[claude_name]
            assert task_1.status.state.value == "completed", (
                f"Turn 1 state: {task_1.status.state.value}"
            )
            chapter_1 = extract_artifact_text(task_1)
            _assert_french_prose(chapter_1)
            print(f"Turn 1 (Claude begins): {t1_elapsed:.2f}s | {len(chapter_1)} chars")

            # Turn 2: relay chapter_1 to Gemini to continue
            t2_start = time.monotonic()
            task_2 = await coordinator.relay_output(
                task_1,
                gemini_name,
                PROMPT_CONTINUE.format(chapter_1=chapter_1),
            )
            t2_elapsed = time.monotonic() - t2_start
            assert task_2.status.state.value == "completed", (
                f"Turn 2 state: {task_2.status.state.value}"
            )
            chapter_2 = extract_artifact_text(task_2)
            _assert_french_prose(chapter_2, check_character=False)
            assert chapter_2 != chapter_1, "Turn 2 echoed Turn 1 verbatim (no progress)"
            print(
                f"Turn 2 (Gemini continues): {t2_elapsed:.2f}s | {len(chapter_2)} chars"
            )

            # Turn 3: relay chapter_2 back to Claude for the epilogue
            t3_start = time.monotonic()
            task_3 = await coordinator.relay_output(
                task_2,
                claude_name,
                PROMPT_FINISH.format(chapter_1=chapter_1, chapter_2=chapter_2),
            )
            t3_elapsed = time.monotonic() - t3_start
            assert task_3.status.state.value == "completed", (
                f"Turn 3 state: {task_3.status.state.value}"
            )
            epilogue = extract_artifact_text(task_3)
            _assert_french_prose(epilogue)
            assert epilogue != chapter_1, "Epilogue echoed chapter 1 verbatim"
            assert epilogue != chapter_2, "Epilogue echoed chapter 2 verbatim"

            total_elapsed = time.monotonic() - relay_start
            print(
                f"Turn 3 (Claude finishes): {t3_elapsed:.2f}s | {len(epilogue)} chars"
            )
            print(
                f"French novel relay total: "
                f"T1={t1_elapsed:.2f}s, T2={t2_elapsed:.2f}s, "
                f"T3={t3_elapsed:.2f}s, Total={total_elapsed:.2f}s"
            )

            # Task IDs must be distinct
            assert len({task_1.id, task_2.id, task_3.id}) == 3
            # All tasks share the team context
            assert task_1.context_id == session.team_id
            assert task_2.context_id == session.team_id
            assert task_3.context_id == session.team_id

        finally:
            await coordinator.dissolve_team()
