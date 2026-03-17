"""Declarative lifecycle hooks for vault/spec-core events.

Loads YAML hook definitions from ``.vaultspec/hooks/``, validates them against
:data:`SUPPORTED_EVENTS`, and executes their shell actions with re-entrancy
protection and a 60-second timeout per action.

Exports:
    :func:`load_hooks`: Parse hook YAML files into :class:`Hook` instances.
    :func:`trigger`: Execute all enabled hooks matching a given event.
    :func:`fire_hooks`: Convenience wrapper; silently swallows errors.
    :class:`Hook`: Hook definition loaded from YAML.
    :class:`HookAction`: A single action within a hook.
    :class:`HookResult`: Result of executing a single hook action.
    :data:`SUPPORTED_EVENTS`: Frozenset of valid event names.
"""

from .engine import SUPPORTED_EVENTS as SUPPORTED_EVENTS
from .engine import Hook as Hook
from .engine import HookAction as HookAction
from .engine import HookResult as HookResult
from .engine import fire_hooks as fire_hooks
from .engine import load_hooks as load_hooks
from .engine import trigger as trigger
