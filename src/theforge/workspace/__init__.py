"""Workspace: multi-repo descriptor, technology detection, config, relations."""

from theforge.workspace.config import WorkspaceConfig, load_workspace_config
from theforge.workspace.describe import (
    describe_workspace,
    discover_repositories,
    repository_of,
)
from theforge.workspace.detect import detect_workspace
from theforge.workspace.recommend import recommend_specialists
from theforge.workspace.relations import load_relations

__all__ = [
    "WorkspaceConfig",
    "describe_workspace",
    "detect_workspace",
    "discover_repositories",
    "load_relations",
    "load_workspace_config",
    "recommend_specialists",
    "repository_of",
]
