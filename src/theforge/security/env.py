"""Environment for provider subprocesses: allowlist first, credential filter second.

Credentials never reach a provider. The allowlist (`ALLOWED_ENV`) is the primary control;
`CREDENTIAL_PATTERNS` is a defense-in-depth pass that drops any credential-shaped name even
if it is ever allowlisted by mistake. Names are compared case-insensitively (Windows env
names are case-insensitive) while the original case of the source key is preserved.
"""

import os
import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

ALLOWED_ENV: Final[Mapping[str, str]] = MappingProxyType({
    "PATH": "resolve executables the provider spawns (python, git, …)",
    "PATHEXT": "Windows: executable extensions needed to resolve commands on PATH",
    "SYSTEMROOT": "Windows: required by the CPython runtime and Winsock initialisation",
    "SYSTEMDRIVE": "Windows: system drive used by runtime and temp-path resolution",
    "WINDIR": "Windows: Windows directory expected by system libraries",
    "COMSPEC": "Windows: command interpreter used by subprocess/shell helpers",
    "HOME": "POSIX: Path.home() and tool config lookup in the child process",
    "USERPROFILE": "Windows: Path.home() and tool config lookup in the child process",
    "TEMP": "Windows: temporary directory for tempfile",
    "TMP": "Windows/POSIX: temporary directory for tempfile",
    "TMPDIR": "POSIX: temporary directory for tempfile",
    "LANG": "locale for consistent text decoding in the child",
    "LC_ALL": "locale override for consistent text decoding in the child",
    "PYTHONIOENCODING": "forced to utf-8 so protocol JSON on stdio is UTF-8",
    "PYTHONUTF8": "forced to 1 so Python providers use UTF-8 mode",
})

_FORCED: Final[Mapping[str, str]] = MappingProxyType({
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUTF8": "1",
})

CREDENTIAL_PATTERNS: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^AWS_",  # AWS keys, session token, profile, shared credentials file
        r"(^|_)TOKEN(_|$)",  # *_TOKEN, TF_TOKEN_*, GITHUB_TOKEN, NPM_TOKEN, VAULT_TOKEN
        r"SECRET",
        r"PASS(WORD|WD)",
        r"API_?KEY",
        r"ACCESS_?KEY",
        r"CREDENTIAL",  # GOOGLE_APPLICATION_CREDENTIALS, *_CREDENTIALS_FILE
        r"^SSH_AUTH_SOCK$",
        r"^(AZURE|ARM|GH|CLOUDSDK|ACTIONS)_",
        r"^(KUBECONFIG|DOCKER_CONFIG|NETRC)$",
        r"_PROXY$",  # HTTP(S)_PROXY / ALL_PROXY / *_proxy may carry userinfo
    )
)

_URL_USERINFO: Final = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^/?#\s@]+@")


def is_credential_name(name: str) -> bool:
    return any(pattern.search(name) for pattern in CREDENTIAL_PATTERNS)


def safe_env(source: Mapping[str, str] | None = None) -> dict[str, str]:
    src = os.environ if source is None else source
    env = {
        key: value
        for key, value in src.items()
        if key.upper() in ALLOWED_ENV
        and key.upper() not in _FORCED
        and not is_credential_name(key)
        and not _URL_USERINFO.search(value)
    }
    env.update(_FORCED)
    return env
