import pytest

from .. import extract_related_links, extract_wiki_links

pytestmark = [pytest.mark.unit]


class TestExtractWikiLinks:
    def test_single_link(self):
        assert extract_wiki_links("See [[MyDoc]] for details") == {"MyDoc"}

    def test_multiple_links(self):
        text = "See [[DocA]] and [[DocB]] here"
        assert extract_wiki_links(text) == {"DocA", "DocB"}

    def test_aliased_link(self):
        assert extract_wiki_links("See [[DocA|Display Name]]") == {"DocA"}

    def test_no_links(self):
        assert extract_wiki_links("No links here") == set()

    def test_empty_string(self):
        assert extract_wiki_links("") == set()

    def test_link_with_spaces(self):
        assert extract_wiki_links("[[My Document]]") == {"My Document"}

    def test_duplicate_links(self):
        text = "[[DocA]] and [[DocA]] again"
        assert extract_wiki_links(text) == {"DocA"}


class TestExtractRelatedLinks:
    def test_valid_wikilinks(self):
        related = ["[[DocA]]", "[[DocB]]"]
        assert extract_related_links(related) == {"DocA", "DocB"}

    def test_aliased_wikilinks(self):
        related = ["[[DocA|Alias]]"]
        assert extract_related_links(related) == {"DocA"}

    def test_malformed_links(self):
        related = ["not-a-link", "DocB"]
        result = extract_related_links(related)
        assert result == set()

    def test_empty_list(self):
        assert extract_related_links([]) == set()

    def test_mixed_valid_and_malformed(self):
        related = ["[[Valid]]", "invalid", "[[Also Valid]]"]
        result = extract_related_links(related)
        assert result == {"Valid", "Also Valid"}
