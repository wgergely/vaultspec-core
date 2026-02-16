from pathlib import Path

import pytest
from vault.hydration import get_template_path, hydrate_template
from vault.models import DocType

pytestmark = [pytest.mark.unit]

_LIB_SRC = Path(__file__).resolve().parent.parent.parent
PROJECT_ROOT = _LIB_SRC.parent.parent.parent


class TestHydrateTemplate:
    def test_replaces_feature(self):
        result = hydrate_template("Feature: <feature>", "auth", "2026-02-08")
        assert result == "Feature: auth"

    def test_replaces_date(self):
        result = hydrate_template("Date: <yyyy-mm-dd>", "auth", "2026-02-08")
        assert result == "Date: 2026-02-08"

    def test_replaces_title(self):
        result = hydrate_template("# <title>", "auth", "2026-02-08", title="Auth Plan")
        assert result == "# Auth Plan"

    def test_no_title_placeholder_unchanged(self):
        result = hydrate_template("# <title>", "auth", "2026-02-08")
        assert result == "# <title>"

    def test_all_placeholders(self):
        template = "---\nfeature: <feature>\ndate: <yyyy-mm-dd>\n---\n# <title>"
        result = hydrate_template(template, "rag", "2026-03-01", title="RAG Plan")
        assert "<feature>" not in result
        assert "<yyyy-mm-dd>" not in result
        assert "<title>" not in result
        assert "rag" in result
        assert "2026-03-01" in result
        assert "RAG Plan" in result

    def test_no_placeholders(self):
        template = "Just plain text with no placeholders."
        result = hydrate_template(template, "auth", "2026-02-08")
        assert result == template


class TestGetTemplatePath:
    def test_adr_template_exists(self):
        result = get_template_path(PROJECT_ROOT, DocType.ADR)
        assert result is not None
        assert result.name == "ADR.md"

    def test_plan_template_exists(self):
        result = get_template_path(PROJECT_ROOT, DocType.PLAN)
        assert result is not None
        assert result.name == "PLAN.md"

    def test_exec_template_exists(self):
        result = get_template_path(PROJECT_ROOT, DocType.EXEC)
        assert result is not None

    def test_research_template_exists(self):
        result = get_template_path(PROJECT_ROOT, DocType.RESEARCH)
        assert result is not None
        assert result.name == "RESEARCH.md"
