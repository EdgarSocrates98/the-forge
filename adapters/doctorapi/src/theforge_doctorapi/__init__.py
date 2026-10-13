"""Forge Protocol v1 provider adapter for Forge Doctor API (``forge_doctor_api``).

The adapter is a separate distribution installed in the specialist's interpreter: it drives
the spec-070 ``DoctorBoundary`` and the §26 public protocol models only (never arbitrary
internals), speaks the protocol on stdin/stdout and never imports ``theforge``.
"""

PROVIDER_ID = "forge-doctor-api"
VERSION = "0.3.0"
# Forge Doctor API is pre-1.0: its public surface may change per minor release, so the
# adapter pins a tight window and drifts to ``degraded`` outside it.
SUPPORTED_SPECIALIST = ">=0.2.0,<0.3.0"
# Interpreter the specialist needs (``requires-python >= 3.11``); the adapter itself runs on
# Python >= 3.10 for ``--replay`` and environment refusals.
REQUIRED_PYTHON = (3, 11)
