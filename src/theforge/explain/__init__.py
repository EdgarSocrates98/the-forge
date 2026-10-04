"""Explain: integrity of persisted runs and the versioned explain report."""

from theforge.explain.hashcheck import verify_run_hashes
from theforge.explain.report import build_explain_report

__all__ = ["build_explain_report", "verify_run_hashes"]
