"""The Forge adapter for the Spark Forge (``sparkforge-aws``): a Forge Protocol v1 provider.

Stdlib-only and Python >= 3.10 (the Spark Forge floor). It speaks the protocol through JSON
on stdin/stdout and never imports ``theforge``.
"""

PROVIDER_ID = "spark-forge"
VERSION = "0.1.0"
# Spark Forge releases this adapter supports (pre-1.0: one specialist minor at a time).
SUPPORTED_SPECIALIST = ">=0.5.0,<0.6.0"
