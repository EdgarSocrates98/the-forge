import pytest
from hypothesis import given
from hypothesis import strategies as st

from theforge.security import env as env_module
from theforge.security.env import ALLOWED_ENV, CREDENTIAL_PATTERNS, safe_env
from theforge.security.paths import is_secret_name, resolve_inside
from theforge.security.redact import REDACTED, redact, redact_text


@pytest.mark.parametrize(
    ("raw", "leaked"),
    [
        ("key AKIAABCDEFGHIJKLMNOP here", "AKIAABCDEFGHIJKLMNOP"),
        ("token=abc123secretvalue", "abc123secretvalue"),
        ("password: hunter2xyz", "hunter2xyz"),
        ("AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY",
         "wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY"),
        ("Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
         "abcdefghijklmnopqrstuvwxyz012345"),
        ("ghp_" + "a" * 36, "a" * 36),
        ("-----BEGIN RSA PRIVATE KEY-----\nMIIE\n-----END RSA PRIVATE KEY-----", "MIIE"),
    ],
)
def test_redact_text_removes_secrets(raw: str, leaked: str) -> None:
    out = redact_text(raw)
    assert leaked not in out
    assert REDACTED in out


def test_redact_keeps_plain_text() -> None:
    assert redact_text("tokens: 5 files") == "tokens: 5 files"
    assert redact_text("max_tokens: 100") == "max_tokens: 100"


def test_redact_text_preserves_structure() -> None:
    assert redact_text('{"password": "hunter2xyz"}') == f'{{"password": "{REDACTED}"}}'
    assert redact_text("password = 'my pass word'") == f"password = '{REDACTED}'"
    assert redact_text("postgres://user:s3cretpw@host/db") == f"postgres://user:{REDACTED}@host/db"
    assert redact_text("GITHUB_TOKEN=x1y2z3") == f"GITHUB_TOKEN={REDACTED}"


@given(st.text())
def test_redact_text_is_idempotent(text: str) -> None:
    once = redact_text(text)
    assert redact_text(once) == once


def test_redact_structure_and_sensitive_keys() -> None:
    data = {"intent": "password=hunter2xyz", "nested": [{"api_key": "plain"}], "count": 3}
    assert redact(data) == {
        "intent": f"password={REDACTED}", "nested": [{"api_key": REDACTED}], "count": 3,
    }


@pytest.mark.parametrize("value", [["a", "b"], {"k": "v"}, 12345, True])
def test_redact_sensitive_key_non_str_values(value) -> None:
    assert redact({"password": value}) == {"password": REDACTED}


def test_redact_sensitive_key_keeps_none_and_empty() -> None:
    assert redact({"token": None, "secret": ""}) == {"token": None, "secret": ""}


def test_safe_env_drops_credentials() -> None:
    env = safe_env({
        "PATH": "/bin", "AWS_SECRET_ACCESS_KEY": "x", "GITHUB_TOKEN": "y",
        "SystemRoot": "C:\\Windows",
    })
    assert env["PATH"] == "/bin"
    assert env["SystemRoot"] == "C:\\Windows"
    assert "AWS_SECRET_ACCESS_KEY" not in env and "GITHUB_TOKEN" not in env
    assert env["PYTHONIOENCODING"] == "utf-8"


_SYSTEM_ENV = {
    "PATH": "/usr/bin:/bin", "SystemRoot": "C:\\Windows", "WINDIR": "C:\\Windows",
    "HOME": "/home/u", "USERPROFILE": "C:\\Users\\u", "TEMP": "C:\\Temp", "LANG": "C.UTF-8",
}

_CREDENTIAL_ENV = {
    "AWS_ACCESS_KEY_ID": "dummy-access-key-id",
    "AWS_SECRET_ACCESS_KEY": "-".join(("dummy", "secret", "access", "key")),
    "AWS_SESSION_TOKEN": "sess",
    "AWS_PROFILE": "prod",
    "AWS_SHARED_CREDENTIALS_FILE": "/home/u/.aws/credentials",
    "GH_TOKEN": "ghp_x",
    "GITHUB_TOKEN": "ghp_y",
    "SSH_AUTH_SOCK": "/tmp/ssh-agent.sock",
    "GOOGLE_APPLICATION_CREDENTIALS": "/home/u/gcp.json",
    "AZURE_CLIENT_SECRET": "az",
    "ARM_CLIENT_SECRET": "arm",
    "HTTPS_PROXY": "http://u:p@h:3128",
    "NPM_TOKEN": "npm",
    "PIP_INDEX_URL": "https://user:pw@pypi.example/simple",
    "KUBECONFIG": "/home/u/.kube/config",
    "DOCKER_CONFIG": "/home/u/.docker",
    "OPENAI_API_KEY": "sk-x",
    "VAULT_TOKEN": "hvs.x",
    "FOO_PASSWORD": "hunter2",
}


def test_safe_env_drops_every_credential_category_and_keeps_system_vars() -> None:
    env = safe_env({**_SYSTEM_ENV, **_CREDENTIAL_ENV})
    for name in _CREDENTIAL_ENV:
        assert name not in env
    for value in _CREDENTIAL_ENV.values():
        assert value not in env.values()
    for name, value in _SYSTEM_ENV.items():
        assert env[name] == value
    assert env["PYTHONIOENCODING"] == "utf-8" and env["PYTHONUTF8"] == "1"


@pytest.mark.parametrize("name", sorted(_CREDENTIAL_ENV.keys() - {"PIP_INDEX_URL"}))
def test_credential_patterns_match_each_category(name: str) -> None:
    assert any(p.search(name) for p in CREDENTIAL_PATTERNS)
    assert any(p.search(name.lower()) for p in CREDENTIAL_PATTERNS)


@pytest.mark.parametrize("name", ["PATH", "HOME", "TEMP", "LANG", "PYTHONPATH", "TOKENS_DIR"])
def test_credential_patterns_spare_plain_names(name: str) -> None:
    assert not any(p.search(name) for p in CREDENTIAL_PATTERNS)


def test_allowed_env_entries_have_justification() -> None:
    expected = {
        "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "HOME",
        "USERPROFILE", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL",
        "PYTHONIOENCODING", "PYTHONUTF8",
    }
    assert set(ALLOWED_ENV) == expected
    for name, why in ALLOWED_ENV.items():
        assert name == name.upper()
        assert isinstance(why, str) and why.strip(), name
        assert not any(p.search(name) for p in CREDENTIAL_PATTERNS), name


def test_safe_env_is_case_insensitive_and_preserves_source_case() -> None:
    env = safe_env({"Path": "/bin", "systemroot": "C:\\Windows", "Aws_Profile": "p"})
    assert env["Path"] == "/bin" and env["systemroot"] == "C:\\Windows"
    assert "Aws_Profile" not in env


def test_safe_env_drops_allowlisted_value_with_url_userinfo() -> None:
    env = safe_env({"PATH": "/bin", "LANG": "https://user:pw@host/x", "TMP": "ftp://tok@h"})
    assert env["PATH"] == "/bin"
    assert "LANG" not in env and "TMP" not in env


def test_safe_env_second_pass_drops_credentials_even_if_allowlisted(monkeypatch) -> None:
    widened = {**ALLOWED_ENV, "GITHUB_TOKEN": "mistake", "HTTPS_PROXY": "mistake"}
    monkeypatch.setattr(env_module, "ALLOWED_ENV", widened)
    env = safe_env({"PATH": "/bin", "GITHUB_TOKEN": "t", "https_proxy": "http://h:1"})
    assert env == {"PATH": "/bin", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


_ID = st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_",
              min_size=0, max_size=12)
_CREDENTIAL_NAMES = st.one_of(
    st.builds(lambda s: "AWS_" + s, _ID),
    st.builds(lambda s: s + "_TOKEN", _ID),
    st.builds(lambda a, b: a + "_SECRET" + b, _ID, _ID),
    st.builds(lambda s: s + "_PASSWORD", _ID),
    st.builds(lambda s: s + "_API_KEY", _ID),
    st.builds(lambda a, b: a + "_ACCESS_KEY" + b, _ID, _ID),
    st.builds(lambda a, b: a + "CREDENTIAL" + b, _ID, _ID),
    st.builds(lambda s: "AZURE_" + s, _ID),
    st.builds(lambda s: "ARM_" + s, _ID),
    st.builds(lambda s: "GH_" + s, _ID),
    st.builds(lambda s: s + "_PROXY", _ID),
    st.sampled_from([
        "SSH_AUTH_SOCK", "GOOGLE_APPLICATION_CREDENTIALS", "GITHUB_TOKEN", "NPM_TOKEN",
        "KUBECONFIG", "DOCKER_CONFIG", "NETRC",
    ]),
)


@given(_CREDENTIAL_NAMES, st.booleans(), st.text(max_size=20))
def test_credential_names_never_survive(name: str, lower: bool, value: str) -> None:
    key = name.lower() if lower else name
    assert any(p.search(key) for p in CREDENTIAL_PATTERNS)
    widened = {**ALLOWED_ENV, key.upper(): "test"}
    original = env_module.ALLOWED_ENV
    env_module.ALLOWED_ENV = widened  # type: ignore[misc]
    try:
        env = safe_env({"PATH": "/bin", key: value})
    finally:
        env_module.ALLOWED_ENV = original  # type: ignore[misc]
    assert key not in env


@pytest.mark.parametrize(
    ("name", "secret"),
    [(".env", True), (".env.local", True), ("id_rsa", True), ("server.pem", True),
     ("creds.key", True), ("credentials.json", True), ("notes.txt", False),
     ("environment.py", False), (".npmrc", True), (".netrc", True), (".pgpass", True),
     ("api.token", True), ("secrets.yaml", True), ("secrets.json", True)],
)
def test_secret_names(name: str, secret: bool) -> None:
    assert is_secret_name(name) is secret


def test_resolve_inside(tmp_path) -> None:
    (tmp_path / "a.txt").write_text("x")
    assert resolve_inside(tmp_path, tmp_path / "a.txt") == (tmp_path / "a.txt").resolve()
    assert resolve_inside(tmp_path, tmp_path / ".." / "x") is None
    assert resolve_inside(tmp_path, tmp_path / "missing") is None


def test_resolve_inside_rejects_symlink_escape(tmp_path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "s.txt").write_text("s")
    root = tmp_path / "root"
    root.mkdir()
    try:
        (root / "link.txt").symlink_to(outside / "s.txt")
    except OSError:
        pytest.skip("symlinks not permitted on this host")
    assert resolve_inside(root, root / "link.txt") is None


def test_resolve_inside_rejects_nul_byte(tmp_path) -> None:
    assert resolve_inside(tmp_path, tmp_path / "a\x00b") is None
