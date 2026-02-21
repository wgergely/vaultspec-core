"""Vault document verification and repair."""

from .api import (
    FixResult,
    VerificationError,
    fix_violations,
    get_malformed,
    list_features,
    verify_file,
    verify_vault_structure,
    verify_vertical_integrity,
)

__all__ = [
    "FixResult",
    "VerificationError",
    "fix_violations",
    "get_malformed",
    "list_features",
    "verify_file",
    "verify_vault_structure",
    "verify_vertical_integrity",
]
