"""Provider implementations and shared execution-provider exports.

This package re-exports the common provider abstractions, model registries, and
concrete integrations used by the execution protocol. ``base`` defines the
shared provider contract and prompt-loading helpers, while ``claude`` and
``gemini`` implement provider-specific workspace file conventions within that
common interface.
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
