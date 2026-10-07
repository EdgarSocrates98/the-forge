"""The Forge adapter for the Spark Forge AWS (``sparkforge-aws``): a Forge Protocol v1 provider.

Stdlib-only and Python >= 3.10 (the Spark Forge AWS floor). It speaks the protocol through JSON
on stdin/stdout and never imports ``theforge``.
"""

PROVIDER_ID = "spark-forge-aws"
VERSION = "0.3.0"
# Spark Forge AWS releases this adapter supports (pre-1.0: one specialist minor at a time).
SUPPORTED_SPECIALIST = ">=0.5.0,<0.6.0"
