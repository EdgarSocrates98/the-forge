"""Forge Protocol v1 provider adapter for Forge Doctor Data (``forge_doctor_data``).

The adapter is a separate distribution installed in the specialist's interpreter: it imports
``forge_doctor_data`` (only the public boundary and documented contract functions), speaks the
protocol on stdin/stdout and never imports ``theforge``.
"""

PROVIDER_ID = "forge-doctor-data"
VERSION = "0.3.0"
# Forge Doctor Data releases this adapter supports (one major line at a time).
SUPPORTED_SPECIALIST = ">=1.0.0rc1,<2.0.0"
# Interpreter the specialist needs (``requires-python >= 3.11``); the adapter itself runs on
# Python >= 3.10 for ``--replay`` and environment refusals.
REQUIRED_PYTHON = (3, 11)
