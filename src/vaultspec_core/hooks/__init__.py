"""Declarative lifecycle hooks for vaultspec-core events.

Loads YAML definitions from ``.vaultspec/hooks/``, validates against
:data:`SUPPORTED_EVENTS`, and executes shell actions with re-entrancy protection
and a 60-second timeout. Key exports: :func:`load_hooks`, :func:`trigger`,
:func:`fire_hooks`; data classes :class:`Hook`, :class:`HookAction`,
:class:`HookResult`. Invoked by :mod:`vaultspec_core.cli.root` after install/sync.

Execution is gated on the operator consent ledger in :mod:`.trust`, whose
:func:`~.trust.grant`, :func:`~.trust.revoke`, :func:`~.trust.is_trusted` and
:func:`~.trust.partition_by_trust` are re-exported here for the CLI surfaces
that ask for consent and report it.
"""

from .engine import SUPPORTED_EVENTS as SUPPORTED_EVENTS
from .engine import Hook as Hook
from .engine import HookAction as HookAction
from .engine import HookResult as HookResult
from .engine import fire_hooks as fire_hooks
from .engine import load_hooks as load_hooks
from .engine import trigger as trigger
from .trust import grant as grant
from .trust import granted_digests as granted_digests
from .trust import hook_digest as hook_digest
from .trust import is_trusted as is_trusted
from .trust import partition_by_trust as partition_by_trust
from .trust import revoke as revoke
from .trust import trust_file_path as trust_file_path
