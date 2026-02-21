"""Vault document parsing, scanning, and metadata models."""

from .hydration import get_template_path, hydrate_template
from .links import extract_related_links, extract_wiki_links
from .models import DocType, DocumentMetadata, VaultConstants
from .parser import parse_frontmatter, parse_vault_metadata
from .scanner import get_doc_type, scan_vault

__all__ = [
    "DocType",
    "DocumentMetadata",
    "VaultConstants",
    "extract_related_links",
    "extract_wiki_links",
    "get_doc_type",
    "get_template_path",
    "hydrate_template",
    "parse_frontmatter",
    "parse_vault_metadata",
    "scan_vault",
]
