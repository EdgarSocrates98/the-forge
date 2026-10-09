"""Host detection with evidence (FASE 4).

Never trusts an env var alone: a detection claims a host only when at
least two independent evidence classes agree, and every claim carries
the evidence list plus the limitations of offline detection.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from theforge.contracts.base import ContractError

HOST_DETECTION_SCHEMA = "forge/HostDetectionResult/v1"

KNOWN_HOSTS: tuple[str, ...] = ("claude", "devin", "codex", "copilot")

# env marker -> (host, weight). Session-scoped markers only; generic vars
# like CI/GITHUB_ACTIONS are context, not host identity.
_ENV_MARKERS: tuple[tuple[str, str], ...] = (
    ("DEVIN_CLI", "devin"),
    ("DEVIN_SESSION", "devin"),
    ("CLAUDECODE", "claude"),
    ("CLAUDE_CODE", "claude"),
    ("CODEX_CLI", "codex"),
    ("CODEX_SANDBOX", "codex"),
    ("COPILOT_CLI", "copilot"),
)

# Binary names probed on PATH (presence = host installed, not running).
_HOST_BINS: dict[str, tuple[str, ...]] = {
    "claude": ("claude", "claude.exe"),
    "devin": ("devin", "devin.exe"),
    "codex": ("codex", "codex.exe"),
    "copilot": ("copilot", "copilot.exe"),
}

# Config dirs created in a project by each host (project-scoped evidence).
_PROJECT_DIRS: dict[str, tuple[str, ...]] = {
    "claude": (".claude",),
    "devin": (".devin",),
    "codex": (".codex", ".agents"),
    "copilot": (".github/copilot", ".github/skills"),
}


@dataclass(frozen=True, kw_only=True)
class HostEvidence:
    kind: str  # env | binary | config_dir
    detail: str


@dataclass(frozen=True, kw_only=True)
class HostDetection:
    """Per-host detection outcome with its evidence."""

    host: str
    detected: bool
    running: bool  # session markers observed (env) — installed != running
    evidence: tuple[HostEvidence, ...] = field(default_factory=tuple)

    @property
    def confidence_basis(self) -> str:
        kinds = {e.kind for e in self.evidence}
        if self.running:
            return "session env markers"
        if len(kinds) >= 2:
            return f"installed: {'+'.join(sorted(kinds))}"
        if kinds:
            return f"weak: {'+'.join(sorted(kinds))} only"
        return "no evidence"


@dataclass(frozen=True, kw_only=True)
class HostDetectionResult:
    schema: str = HOST_DETECTION_SCHEMA
    current: str | None = None  # host running this session, if evidenced
    detections: tuple[HostDetection, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.schema != HOST_DETECTION_SCHEMA:
            raise ContractError(f"unsupported schema {self.schema!r}")
        if self.current is not None and self.current not in KNOWN_HOSTS:
            raise ContractError(f"unknown host {self.current!r}")

    def for_host(self, host: str) -> HostDetection | None:
        return next((d for d in self.detections if d.host == host), None)


def detect_hosts(
    *,
    project_root: Path | None = None,
    env: dict[str, str] | None = None,
) -> HostDetectionResult:
    """Evidence-based host detection; never raises on a missing host."""
    env = dict(os.environ if env is None else env)
    detections: list[HostDetection] = []
    for host in KNOWN_HOSTS:
        ev: list[HostEvidence] = []
        running = False
        for marker, marker_host in _ENV_MARKERS:
            if marker_host == host and env.get(marker):
                ev.append(HostEvidence(kind="env", detail=f"{marker} set"))
                running = True
        for binname in _HOST_BINS[host]:
            if shutil.which(binname):
                ev.append(HostEvidence(kind="binary", detail=f"{binname} on PATH"))
                break
        if project_root is not None:
            for rel in _PROJECT_DIRS[host]:
                if (project_root / rel).is_dir():
                    ev.append(HostEvidence(kind="config_dir", detail=f"{rel}/ present"))
        detected = running or len({e.kind for e in ev}) >= 2
        detections.append(
            HostDetection(host=host, detected=detected, running=running, evidence=tuple(ev))
        )
    current = next((d.host for d in detections if d.running), None)
    limitations = [
        "env markers are session hints, not proof of host identity",
        "binary/config presence proves installation, not a running session",
        "host-side loading of installed assets is not observable offline",
    ]
    return HostDetectionResult(
        current=current, detections=tuple(detections), limitations=tuple(limitations)
    )
