"""The release-binary build.

A release workflow runs this against a bare interpreter with no project
environment, which is why it is an instrument rather than a harness module:
nothing in :mod:`vaultspec_core` imports it, and the published wheel does not
ship it.

The package marker exists so the builder is importable under its real dotted
name (``dev.binaries.build_pyapp``), which is what lets the cohabiting
:mod:`dev.binaries.tests` package exercise it the way every other tree in this
repository tests its own code.

Modules:
    :mod:`dev.binaries.build_pyapp`: Release binary builder driven by PyApp.
"""

from __future__ import annotations
