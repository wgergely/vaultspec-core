"""The offline release-binary build.

A release workflow runs this against a bare interpreter with no project
environment, which is why it is an instrument rather than a harness module:
nothing in :mod:`vaultspec_core` imports it, and the published wheel does not
ship it.

What it produces carries its own interpreter, the application and the whole
dependency closure, so a release binary installs nothing and reaches no
network on any launch. That is asserted rather than assumed: the settings
which make it true are pinned in :mod:`dev.binaries.tests`, and every artifact
is run with the network taken away before it may become a release asset.

The package marker exists so the builder is importable under its real dotted
name (``dev.binaries.build_pyapp``), which is what lets the cohabiting
:mod:`dev.binaries.tests` package exercise it the way every other tree in this
repository tests its own code.

Modules:
    :mod:`dev.binaries.build_pyapp`: Release binary builder driven by PyApp.
"""

from __future__ import annotations
