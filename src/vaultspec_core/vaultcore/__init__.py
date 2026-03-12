"""Expose the vault document kernel used throughout vaultspec.

The `vaultcore` package provides the reusable primitives for working with
`.vault/` documents: `models` defines the domain objects, `parser` extracts
frontmatter and metadata, `links` reads wiki-link relationships, `scanner`
discovers and classifies files, and `hydration` scaffolds new records from
templates.
"""

from .hydration import create_vault_doc as create_vault_doc
from .hydration import get_template_path as get_template_path
from .hydration import hydrate_template as hydrate_template
from .links import extract_related_links as extract_related_links
from .links import extract_wiki_links as extract_wiki_links
from .models import DocType as DocType
from .models import DocumentMetadata as DocumentMetadata
from .models import VaultConstants as VaultConstants
from .parser import parse_frontmatter as parse_frontmatter
from .parser import parse_vault_metadata as parse_vault_metadata
from .scanner import get_doc_type as get_doc_type
from .scanner import scan_vault as scan_vault
