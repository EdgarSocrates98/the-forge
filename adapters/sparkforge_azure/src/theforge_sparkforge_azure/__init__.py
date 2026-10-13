"""Forge Protocol v1 provider adapter for Spark Forge Azure (``sparkforge_azure``).

The adapter is a separate distribution installed in the specialist's interpreter: it imports
``sparkforge_azure`` (only public seams: the ``adapters.tools`` table, ``sdd`` gates,
``doctor.run`` and the access-diagnosis pipelines), speaks the protocol on stdin/stdout and
never imports ``theforge``. Spark Forge Azure is an independent specialist: no AWS↔Azure
capability equivalence is assumed — capabilities come only from the recorded native surface.
"""

PROVIDER_ID = "spark-forge-azure"
VERSION = "0.1.0"
# Spark Forge Azure releases this adapter supports (one major line at a time).
SUPPORTED_SPECIALIST = ">=0.1.0,<0.2.0"
# Interpreter the specialist needs (``requires-python >= 3.10``); the adapter itself runs on
# Python >= 3.10 for ``--replay`` and environment refusals.
REQUIRED_PYTHON = (3, 10)
