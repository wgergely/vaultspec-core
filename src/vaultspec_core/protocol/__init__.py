"""Public surface for the vaultspec-core execution protocol.

Exports the shared provider contract
(:class:`~vaultspec_core.protocol.providers.base.ExecutionProvider`),
model registries
(:class:`~vaultspec_core.protocol.providers.ClaudeModels`,
:class:`~vaultspec_core.protocol.providers.GeminiModels`), and
:class:`~vaultspec_core.protocol.providers.CapabilityLevel`
from :mod:`.providers`.  Sits above :mod:`vaultspec_core.core.enums`;
consumed by :mod:`vaultspec_core.cli`.
"""

from .providers import CapabilityLevel as CapabilityLevel
from .providers import ClaudeModels as ClaudeModels
from .providers import ExecutionProvider as ExecutionProvider
from .providers import GeminiModels as GeminiModels

__all__ = [
    "CapabilityLevel",
    "ClaudeModels",
    "ExecutionProvider",
    "GeminiModels",
]
