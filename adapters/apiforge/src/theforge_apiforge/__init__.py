"""The Forge adapter for the API Forge (``apiforge``): a Forge Protocol v1 provider.

Stdlib-only and Python >= 3.10. It speaks the protocol through JSON on stdin/stdout and never
imports ``theforge``. The API Forge itself needs Python 3.12 (``REQUIRED_PYTHON``).
"""

PROVIDER_ID = "api-forge"
VERSION = "0.3.0"
# API Forge releases this adapter supports (pre-1.0: one specialist minor at a time).
SUPPORTED_SPECIALIST = ">=0.1.0,<0.2.0"
# Interpreter the API Forge needs; the adapter itself runs on Python >= 3.10.
REQUIRED_PYTHON = (3, 12)
