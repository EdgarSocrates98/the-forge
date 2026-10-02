import pytest
from hypothesis import given
from hypothesis import strategies as st

from theforge.security.env import safe_env
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
