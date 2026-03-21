"""Execution-provider implementations and shared exports.

Re-exports :class:`~vaultspec_core.protocol.providers.base.ExecutionProvider`,
:func:`~vaultspec_core.protocol.providers.base.resolve_includes`,
:func:`~vaultspec_core.protocol.providers.base.resolve_executable`,
:class:`~vaultspec_core.protocol.providers.claude.ClaudeProvider`,
:class:`~vaultspec_core.protocol.providers.gemini.GeminiProvider`, and the
model registries (:class:`~vaultspec_core.core.enums.ClaudeModels`,
:class:`~vaultspec_core.core.enums.GeminiModels`,
:class:`~vaultspec_core.core.enums.CapabilityLevel`) from
:mod:`vaultspec_core.core.enums`. Consumed by :mod:`vaultspec_core.protocol`.
"""

from ...core.enums import CapabilityLevel as CapabilityLevel
from ...core.enums import ClaudeModels as ClaudeModels
from ...core.enums import GeminiModels as GeminiModels
from ...core.enums import ModelRegistry as ModelRegistry
from .base import ExecutionProvider as ExecutionProvider
from .base import resolve_executable as resolve_executable
from .base import resolve_includes as resolve_includes
from .claude import ClaudeProvider as ClaudeProvider
from .gemini import GeminiProvider as GeminiProvider
