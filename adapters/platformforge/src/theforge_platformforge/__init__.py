"""Forge Protocol v1 provider adapter for Platform Forge (``platformforge``).

The adapter is a separate distribution installed in the specialist's interpreter: it imports
``platformforge`` (only public seams: the ``capability_manifest`` surface and the offline
``analyze_*`` tree analyzers), speaks the protocol on stdin/stdout and never imports
``theforge``. Platform Forge declares its own capability manifest
(``platformforge/capability-manifest/v3``); the adapter records that surface in
``native_surface.json`` and exposes only seams the snapshot proves present — mutating
executors the manifest marks ``runtime_available: false`` are never claimed.
"""

PROVIDER_ID = "platform-forge"
VERSION = "0.1.0"
# Platform Forge releases this adapter supports (one major line at a time).
SUPPORTED_SPECIALIST = ">=0.1.0,<0.2.0"
# Interpreter the specialist needs (``requires-python >= 3.10``); the adapter itself runs on
# Python >= 3.10 for ``--replay`` and environment refusals.
REQUIRED_PYTHON = (3, 10)
