"""Canonical JSON and hashing shared by every persisted contract."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any


def canonical_json(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_of(obj: Any) -> str:
    return sha256_hex(canonical_json(obj).encode("utf-8"))


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
