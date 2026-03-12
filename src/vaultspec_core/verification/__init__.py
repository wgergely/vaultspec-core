"""Expose the structural verification and repair package facade.

This package re-exports the `api` surface responsible for `.vault/` conformance
checks, integrity reporting, and limited repair helpers.
"""

from .api import FixResult as FixResult
from .api import VerificationError as VerificationError
from .api import fix_violations as fix_violations
from .api import get_malformed as get_malformed
from .api import list_features as list_features
from .api import verify_file as verify_file
from .api import verify_vault_structure as verify_vault_structure
from .api import verify_vertical_integrity as verify_vertical_integrity
