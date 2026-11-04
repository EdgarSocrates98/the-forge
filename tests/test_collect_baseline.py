from __future__ import annotations

from audit.tooling.collect_baseline import github_summary


def test_offline_github_summary_preserves_baseline_shape() -> None:
    summary = github_summary("EdgarSocrates98/the-forge", enabled=False)

    assert summary["status"] == "NOT_RUN"
    assert summary["latest_ci"]["status"] == "NOT_RUN"
    assert summary["open_prs"]["status"] == "NOT_RUN"
    assert summary["latest_release"]["status"] == "NOT_RUN"
    assert summary["provenance"]["source"] == "not collected"
