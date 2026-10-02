"""Secret redaction applied before anything is persisted or echoed from providers."""

import re
from typing import Any

REDACTED = "[REDACTED]"

# Identifier that CONTAINS a sensitive word (GITHUB_TOKEN, MY_API_KEY, secret_key,
# DB_PASSWORD, "password"). "token" is not matched when followed by a bare plural "s"
# (`tokens: 5 files`, `max_tokens: 100` are usage stats, not secrets); `tokens_used`
# style identifiers still match, an accepted false positive.
_KEY = (
    r"(?i)\b([A-Za-z0-9_.-]*(?:api[_-]?key|secret|token(?!s\b)|password|passwd|credential)"
    r"[A-Za-z0-9_.-]*)"
)

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
     REDACTED),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), REDACTED),
    (re.compile(r"\bghp_[A-Za-z0-9]{36}\b"), REDACTED),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"), REDACTED),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), REDACTED),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), REDACTED),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{20,}=*"), REDACTED),
    # URL credentials: scheme://user:password@host
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^\s:/@]+:)(?!\[REDACTED\]@)[^\s/@]+(@)"),
     r"\1" + REDACTED + r"\2"),
    # Quoted values (may contain spaces): "password": "x y", token = 'x'.
    (re.compile(_KEY + r"""(["']?\s*[:=]\s*)(["'])(?!\[REDACTED\]\3)(?:(?!\3)[^\n])*\3"""),
     r"\1\2\3" + REDACTED + r"\3"),
    # Unquoted values.
    (re.compile(_KEY + r"""(["']?\s*[:=]\s*)(["']?)(?!\[REDACTED\])[^\s'",;]+"""),
     r"\1\2\3" + REDACTED),
)

SENSITIVE_KEYS = frozenset({
    "password", "passwd", "secret", "token", "api_key", "apikey", "authorization",
    "access_key", "secret_key", "client_secret", "aws_secret_access_key",
})


def redact_text(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            sensitive = str(key).lower() in SENSITIVE_KEYS and item is not None and item != ""
            out[key] = REDACTED if sensitive else redact(item)
        return out
    return value
