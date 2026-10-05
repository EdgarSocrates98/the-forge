"""Retry policy of plan nodes (Cycle 3 Wave F, F3).

Retry is configuration, never the default: ``retry.toml`` sits next to
``policy.toml``/``complexity.toml`` (user file under the config dir, project file
under ``.forge/config/``; per key the project file wins). Defaults retry nothing:
``max_attempts`` is 1. When enabled, only the listed error codes retry — transient
protocol failures (timeout / nonzero exit, ``Codes.PROTO_*``), never refusals,
policy blocks or skips. Attempts are capped hard at ``MAX_ATTEMPTS`` and backoff is
deterministic exponential (``backoff_seconds * 2**n``, capped by
``backoff_cap_seconds``) — no jitter, no unbounded retry.

Every attempt is a real child run with its own receipt; the recorded
``NodeOutcome.attempts`` says how many the plan run drove.
"""

import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

from theforge.contracts.codes import Codes

__all__ = ["MAX_ATTEMPTS", "RetryPolicy", "load_retry_config", "retry_backoff",
           "retryable"]

CONFIG_FILE: Final = "retry.toml"
# Never retry forever: the hard ceiling on attempts a config may ask for.
MAX_ATTEMPTS: Final = 5
MAX_BACKOFF_SECONDS: Final = 60.0
DEFAULT_RETRYABLE: Final = frozenset({Codes.PROTO_TIMEOUT, Codes.PROTO_EXIT})


@dataclass(frozen=True, kw_only=True)
class RetryPolicy:
    """How a plan node may retry: ``max_attempts`` counts the first try."""

    max_attempts: int = 1  # 1 = never retry
    retryable_codes: frozenset[str] = DEFAULT_RETRYABLE
    backoff_seconds: float = 0.5  # base of the exponential backoff
    backoff_cap_seconds: float = 5.0
    source: str = "defaults"  # "defaults" | "project" (the last file that applied)


def retryable(policy: RetryPolicy, code: str | None) -> bool:
    """Whether another attempt may follow a failure carrying ``code``."""
    return code is not None and code in policy.retryable_codes


def retry_backoff(policy: RetryPolicy, attempt: int) -> float:
    """Seconds to sleep before attempt ``attempt`` + 1 (1 = after the first try)."""
    delay: float = policy.backoff_seconds * float(2 ** max(0, attempt - 1))
    return float(min(delay, policy.backoff_cap_seconds))


def _number(raw: object) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return float(raw)


def load_retry_config(*, user_dir: Path, forge_dir: Path,
                      warnings: list[str]) -> RetryPolicy:
    """Merge defaults, the user file and the project file (project wins per key).

    Missing files keep the defaults; malformed values append to ``warnings`` and
    never raise — a broken retry policy must not stop a run, it just disables
    the offending keys.
    """
    policy = RetryPolicy()
    for path, label in ((user_dir / CONFIG_FILE, "user"),
                        (forge_dir / "config" / CONFIG_FILE, "project")):
        try:
            raw = tomllib.loads(path.read_bytes().decode("utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, tomllib.TOMLDecodeError) as exc:
            warnings.append(f"{label} {CONFIG_FILE}: unreadable ({exc})")
            continue
        table = raw.get("retry") if isinstance(raw, dict) else None
        if not isinstance(table, dict):
            warnings.append(f"{label} {CONFIG_FILE}: missing [retry] table")
            continue
        changed = False
        if "max_attempts" in table:
            value = table["max_attempts"]
            if isinstance(value, int) and not isinstance(value, bool) \
                    and 1 <= value <= MAX_ATTEMPTS:
                policy = replace(policy, max_attempts=value)
                changed = True
            else:
                warnings.append(
                    f"{label} {CONFIG_FILE}: retry.max_attempts must be an integer "
                    f"1..{MAX_ATTEMPTS}")
        if "retryable_codes" in table:
            value = table["retryable_codes"]
            if isinstance(value, list) and all(isinstance(c, str) for c in value):
                policy = replace(policy, retryable_codes=frozenset(value))
                changed = True
            else:
                warnings.append(
                    f"{label} {CONFIG_FILE}: retry.retryable_codes must be a "
                    "list of strings")
        for key in ("backoff_seconds", "backoff_cap_seconds"):
            if key not in table:
                continue
            seconds = _number(table[key])
            if seconds is None or not 0.0 <= seconds <= MAX_BACKOFF_SECONDS:
                warnings.append(
                    f"{label} {CONFIG_FILE}: retry.{key} must be a number "
                    f"0..{MAX_BACKOFF_SECONDS:g}")
                continue
            if key == "backoff_seconds":
                policy = replace(policy, backoff_seconds=seconds)
            else:
                policy = replace(policy, backoff_cap_seconds=seconds)
            changed = True
        if changed:
            policy = replace(policy, source=label)
    return policy
