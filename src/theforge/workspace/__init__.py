"""Workspace: multi-repo descriptor and explicit relations (where a plan runs)."""

from theforge.workspace.describe import describe_workspace, discover_repositories, repository_of
from theforge.workspace.relations import load_relations

__all__ = ["describe_workspace", "discover_repositories", "load_relations", "repository_of"]
