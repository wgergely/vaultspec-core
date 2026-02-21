"""RAG unit test fixtures."""

import shutil

import pytest

from tests.conftest import _build_rag_components
from tests.constants import (
    LANCE_SUFFIX_UNIT,
    TEST_PROJECT,
)


@pytest.fixture(scope="session")
def rag_components():
    """Set up real RAG components once for the entire test session (GPU only).

    Indexes a 13-doc subset covering all 5 doc_types and key features.
    Uses .lance-fast-unit/ to avoid colliding with integration fixtures.
    """
    components = _build_rag_components(
        TEST_PROJECT, fast=True, lance_suffix=LANCE_SUFFIX_UNIT
    )

    yield components

    lance_dir = components["lance_dir"]
    if lance_dir.exists():
        shutil.rmtree(lance_dir)
