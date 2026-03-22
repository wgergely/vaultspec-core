"""Declarative lifecycle hooks for vaultspec-core events.

Loads YAML definitions from ``.vaultspec/hooks/``, validates against
:data:`SUPPORTED_EVENTS`, and executes shell actions with re-entrancy protection
and a 60-second timeout. Key exports: :func:`load_hooks`, :func:`trigger`,
:func:`fire_hooks`; data classes :class:`Hook`, :class:`HookAction`,
:class:`HookResult`. Invoked by :mod:`vaultspec_core.cli.root` after install/sync.
"""

from .engine import SUPPORTED_EVENTS as SUPPORTED_EVENTS
from .engine import Hook as Hook
from .engine import HookAction as HookAction
from .engine import HookResult as HookResult
from .engine import fire_hooks as fire_hooks
from .engine import load_hooks as load_hooks
from .engine import trigger as trigger
