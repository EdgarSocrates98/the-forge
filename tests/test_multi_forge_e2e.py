"""install-2.0 lf-0040 §9.1 — five-wheel end-to-end matrix.

Builds a wheel per Forge repo, installs all five into one venv and runs
each Forge's install CLI into fresh target directories in every relevant
order. Asserts:

- final-state equivalence modulo Forge-unique payloads (registry entries,
  ROUTING.md, AGENT_PROTOCOL.md are deterministic — AGENTS.md carries the
  same per-forge managed block set regardless of append order);
- no cross-Forge file deletion (every capability manifest + registry
  entry survives every order);
- consolidated AGENTS.md / CLAUDE.md / AGENT_PROTOCOL.md stay valid;
- user-authored content outside managed markers is byte-preserved;
- reinstall is idempotent (no duplication);
- uninstalling one Forge leaves every other Forge's state intact;
- a kill-mid-install leftover lock is reclaimed by the next op;
- the registry composes without the-forge installed.

Marks: slow + e2e. Knobs (env):

- ``FORGE_E2E_REPOS``  — dir holding the five checkouts
  (default: ``<repo>/..``, i.e. the forjas/ workspace);
- ``FORGE_E2E_WHEELHOUSE`` — reuse prebuilt wheels instead of building;
- ``FORGE_E2E_MATRIX`` — ``full`` (default, all 5! = 120 orders),
  ``reduced`` (12 strategic orders: every forge first and last at least
  once) or an explicit csv like ``aws,azure,api,platform,theforge``.
- ``FORGE_E2E_VENV`` — reuse an existing venv with the wheels installed.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import subprocess
import venv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPOS_ROOT = Path(os.environ.get("FORGE_E2E_REPOS", ROOT.parent))

# forge key → (repo dir, console script, install argv, root flag, uninstall argv)
FORGES: dict[str, dict[str, object]] = {
    "the-forge": {
        "repo": "the-forge",
        "cli": "theforge",
        "install": ["install", "apply"],
        "uninstall": ["install", "uninstall"],
        "repair": ["install", "repair"],
        "root_flag": "--root",
        "dist": "theforge_core",
    },
    "spark-forge-aws": {
        "repo": "spark-forge-aws",
        "cli": "sparkforge-aws",
        "install": ["install"],
        "uninstall": ["uninstall"],
        "repair": ["repair"],
        "root_flag": "--root",
        "dist": "sparkforge_aws",
    },
    "spark-forge-azure": {
        "repo": "spark-forge-azure",
        "cli": "sparkforge-azure",
        "install": ["install", "apply"],
        "uninstall": ["install", "uninstall"],
        "repair": ["install", "repair"],
        "root_flag": "--root",
        "dist": "sparkforge_azure",
    },
    "api-forge": {
        "repo": "api-forge",
        "cli": "apiforge",
        "install": ["install"],
        "uninstall": ["install", "uninstall"],
        "repair": ["install", "repair"],
        "root_flag": "--root",
        "dist": "apiforge_af",
    },
    "platform-forge": {
        "repo": "platform-forge",
        "cli": "platformforge",
        "install": ["install", "apply"],
        "uninstall": ["install", "uninstall"],
        "repair": ["install", "repair"],
        "root_flag": "--repo",
        "dist": "platformforge",
    },
}
FORGE_IDS = tuple(FORGES)
# canonical registry forge ids (manifest forge_id) keyed by repo key
FID = {
    "the-forge": "the-forge",
    "spark-forge-aws": "spark-forge-aws",
    "spark-forge-azure": "spark-forge-azure",
    "api-forge": "api-forge",
    "platform-forge": "platform-forge",
}

USER_MARK_AGENTS = "# workspace notes\nmy authored section — never overwritten\n"
USER_MARK_CLAUDE = "# claude scratch\nhand-written — keep me\n"


def _matrix() -> list[tuple[str, ...]]:
    spec = os.environ.get("FORGE_E2E_MATRIX", "full").strip().lower()
    if spec == "full":
        return list(itertools.permutations(FORGE_IDS))
    if spec == "reduced":
        out: list[tuple[str, ...]] = []
        seen: set[tuple[str, ...]] = set()
        perms = list(itertools.permutations(FORGE_IDS))
        for fid in FORGE_IDS:
            # each forge first once and last once, deterministic picks
            first = next(p for p in perms if p[0] == fid)
            last = next(p for p in perms if p[-1] == fid)
            for p in (first, last):
                if p not in seen:
                    seen.add(p)
                    out.append(p)
        out.append(tuple(reversed(FORGE_IDS)))
        return list(dict.fromkeys(out))
    order = tuple(x.strip() for x in spec.split(",") if x.strip())
    if set(order) != set(FORGE_IDS):
        raise SystemExit(f"FORGE_E2E_MATRIX explicit order must name all 5 forges: {order}")
    return [order]


MATRIX = _matrix()


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _run(cmd: list[str], *, env: dict[str, str], cwd: Path | None = None) -> dict:
    proc = subprocess.run(
        cmd,
        env=env,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=300,
    )
    try:
        doc = json.loads(proc.stdout)
    except json.JSONDecodeError:
        doc = {"_raw": proc.stdout[-4000:]}
    doc["_rc"] = proc.returncode
    return doc


@pytest.fixture(scope="session")
def wheelhouse(tmp_path_factory) -> Path:
    prebuilt = os.environ.get("FORGE_E2E_WHEELHOUSE")
    if prebuilt:
        wh = Path(prebuilt)
        missing = [k for k, f in FORGES.items() if not list(wh.glob(f"{f['dist']}-*.whl"))]
        if missing:
            pytest.fail(f"FORGE_E2E_WHEELHOUSE missing wheels for {missing}")
        return wh
    wh = tmp_path_factory.mktemp("wheelhouse")
    for key, f in FORGES.items():
        repo = REPOS_ROOT / str(f["repo"])
        if not repo.is_dir():
            pytest.fail(f"forge repo missing: {repo} (set FORGE_E2E_REPOS)")
        proc = subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", str(wh), str(repo)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=600,
        )
        if proc.returncode != 0:
            pytest.fail(f"uv build failed for {key}:\n{proc.stdout[-3000:]}")
    return wh


@pytest.fixture(scope="session")
def forge_venv(tmp_path_factory, wheelhouse) -> dict:
    reused = os.environ.get("FORGE_E2E_VENV")
    venv_dir = Path(reused) if reused else tmp_path_factory.mktemp("venv") / "v"
    env = os.environ.copy()
    home = tmp_path_factory.mktemp("home")
    env["HOME"] = str(home)
    env["XDG_CONFIG_HOME"] = str(home / ".config")
    env["TERM"] = "dumb"
    env["NO_COLOR"] = "1"
    env.pop("VIRTUAL_ENV", None)
    if not reused:
        venv.create(venv_dir, with_pip=True)
        py = venv_dir / "bin" / "python"
        wheels = [str(w) for w in sorted(wheelhouse.glob("*.whl"))]
        proc = subprocess.run(
            ["uv", "pip", "install", "--python", str(py), *wheels],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=900,
            env=env,
        )
        if proc.returncode != 0:
            pytest.fail(f"venv install failed:\n{proc.stdout[-3000:]}")
    bin_dir = venv_dir / "bin"
    clis = {k: str(bin_dir / str(f["cli"])) for k, f in FORGES.items()}
    missing = [c for c in clis.values() if not Path(c).exists()]
    if missing:
        pytest.fail(f"console scripts missing in venv: {missing}")
    return {"bin": bin_dir, "env": env, "clis": clis, "venv": venv_dir}


def _seed_user_docs(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    # platform-forge refuses non-repo targets (needs .git or forge.json) —
    # a real `git init` is the safest marker for every forge.
    if not (root / ".git").exists():
        subprocess.run(
            ["git", "init", "-q", str(root)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    (root / "AGENTS.md").write_text(USER_MARK_AGENTS, encoding="utf-8")
    (root / "CLAUDE.md").write_text(USER_MARK_CLAUDE, encoding="utf-8")


def _only_safe_refusals(out: dict, root: Path) -> bool:
    """§9.3 — a refused write to a path another Forge owns is the spec'd
    safe outcome for an ambiguous conflict, not a failure to compose.

    spark-forge-aws and spark-forge-azure both ship ``knowledge/spark/*``;
    whichever installs second reports ``refusals`` while its
    context-registry + consumer-docs still commit. We accept that receipt
    iff every refused path is a surviving foreign knowledge file —
    "install never deletes another forge's file" is then verified by
    construction. Any other failure shape still fails the test.
    """
    if out.get("status") != "failed":
        return False
    fails = [c for c in out.get("checks", []) if c.get("status") == "FAIL"]
    if {c.get("id") for c in fails} != {"refusals"}:
        return False
    checks = out.get("checks", [])
    for cid in ("context-registry", "consumer-docs"):
        if not any(c.get("id") == cid and c.get("status") == "PASS" for c in checks):
            return False
    refused = out.get("refused") or []
    if not refused:
        return False
    for rec in refused:
        rel = rec.get("path", "")
        if not rel.startswith("knowledge/"):
            return False
        if rec.get("reason") != "arquivo_do_usuario":
            return False
        if not (root / rel).is_file():
            return False  # foreign copy must survive — never clobbered
    return True


def _install(forge_venv: dict, key: str, root: Path) -> dict:
    f = FORGES[key]
    cmd = [forge_venv["clis"][key], *f["install"], str(f["root_flag"]), str(root), "--yes"]
    out = _run(cmd, env=forge_venv["env"])
    assert out["_rc"] == 0 or _only_safe_refusals(out, root), (
        f"{key} install rc={out['_rc']}: {out.get('_raw', out)}"
    )
    return out


def _uninstall(forge_venv: dict, key: str, root: Path) -> dict:
    f = FORGES[key]
    cmd = [forge_venv["clis"][key], *f["uninstall"], str(f["root_flag"]), str(root)]
    out = _run(cmd, env=forge_venv["env"])
    assert out["_rc"] == 0, f"{key} uninstall rc={out['_rc']}: {out.get('_raw', out)}"
    return out


def _repair(forge_venv: dict, key: str, root: Path) -> dict:
    f = FORGES[key]
    cmd = [forge_venv["clis"][key], *f["repair"], str(f["root_flag"]), str(root)]
    out = _run(cmd, env=forge_venv["env"])
    assert out["_rc"] == 0, f"{key} repair rc={out['_rc']}: {out.get('_raw', out)}"
    return out


def _registry(root: Path) -> dict | None:
    p = root / ".forge" / "context" / "registry.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _normalize_reg(reg: dict) -> dict:
    """Strip order/identity-volatile fields for cross-order equivalence."""
    reg = json.loads(json.dumps(reg))
    reg.pop("updated_at", None)
    reg.pop("workspace_root", None)
    for e in reg.get("forges", []):
        e.pop("installed_at", None)
        e.pop("updated_at", None)
        e.pop("installed_by", None)
        m = e.get("manifest") or {}
        m.pop("sha256", None)  # manifest bytes embed recorded_at
    reg["forges"] = sorted(reg.get("forges", []), key=lambda e: e.get("forge_id", ""))
    return reg


def _forge_blocks(root: Path, name: str) -> set[str]:
    text = (root / name).read_text(encoding="utf-8") if (root / name).exists() else ""
    out = set()
    for fid in FID.values():
        if f"forge:{fid}:begin" in text and f"forge:{fid}:end" in text:
            out.add(fid)
    return out


def _assert_composed_state(root: Path, installed: tuple[str, ...]) -> dict:
    """Shared post-state invariants for a root where `installed` ran."""
    reg = _registry(root)
    assert reg is not None, f"no registry in {root}"
    fids = {e.get("forge_id") for e in reg.get("forges", [])}
    assert fids == {FID[k] for k in installed}, fids
    ctx = root / ".forge" / "context"
    for k in installed:
        assert (ctx / "capabilities" / f"{FID[k]}.json").is_file(), FID[k]
    assert (ctx / "ROUTING.md").is_file()
    # consolidated docs valid: every managed block balanced, no orphan
    for name in ("AGENTS.md", "AGENT_PROTOCOL.md"):
        text = (root / name).read_text(encoding="utf-8")
        assert text.count(":begin -->") == text.count(":end -->"), name
        assert text.count(":begin -->") >= 1, name
    # user content byte-preserved at the top of the docs
    assert (root / "AGENTS.md").read_text(encoding="utf-8").startswith(USER_MARK_AGENTS)
    assert (root / "CLAUDE.md").read_text(encoding="utf-8").startswith(USER_MARK_CLAUDE)
    return reg


@pytest.mark.slow
@pytest.mark.e2e
@pytest.mark.parametrize("order", MATRIX, ids=["-".join(o) for o in MATRIX])
def test_install_order_equivalence(forge_venv, tmp_path, order):
    """§9.1/§9.5 — every install order converges to the same final state."""
    root = tmp_path / "target"
    _seed_user_docs(root)
    for key in order:
        _install(forge_venv, key, root)
    reg = _assert_composed_state(root, order)

    # equivalence artifact consumed by the cross-order check below;
    # capability manifests normalized (recorded_at is the only volatile
    # field per install)
    caps = {}
    for k in order:
        doc = json.loads(
            (root / ".forge" / "context" / "capabilities" / f"{FID[k]}.json").read_text(
                encoding="utf-8"
            )
        )
        doc.pop("recorded_at", None)
        caps[FID[k]] = doc
    marker = tmp_path / "_state.json"
    marker.write_text(
        json.dumps(
            {
                "order": list(order),
                "registry": _normalize_reg(reg),
                "capabilities": caps,
                "routing_sha": _sha(
                    (root / ".forge" / "context" / "ROUTING.md").read_bytes()
                ),
                "protocol_sha": _sha((root / "AGENT_PROTOCOL.md").read_bytes()),
                "agents_blocks": sorted(_forge_blocks(root, "AGENTS.md")),
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    # stash state for the cross-order equivalence check
    stash_dir = Path(os.environ.get("FORGE_E2E_STATES", forge_venv["venv"] / "e2e-states"))
    stash_dir.mkdir(parents=True, exist_ok=True)
    (stash_dir / ("-".join(order) + ".json")).write_bytes(marker.read_bytes())


@pytest.mark.slow
@pytest.mark.e2e
def test_cross_order_final_state_equivalence(forge_venv):
    """Final-state equivalence across every order that ran — registry
    (normalized), ROUTING.md and AGENT_PROTOCOL.md are byte-identical;
    AGENTS.md carries the same managed block set (append order may vary)."""
    stash_dir = Path(os.environ.get("FORGE_E2E_STATES", forge_venv["venv"] / "e2e-states"))
    states = sorted(stash_dir.glob("*.json"))
    if len(states) < 2:
        pytest.skip("needs ≥2 order runs (full matrix or repeated runs)")
    docs = [json.loads(p.read_text()) for p in states]
    base = docs[0]
    for d in docs[1:]:
        assert d["registry"] == base["registry"], (base["order"], d["order"])
        assert d["capabilities"] == base["capabilities"], (base["order"], d["order"])
        assert d["routing_sha"] == base["routing_sha"]
        assert d["protocol_sha"] == base["protocol_sha"]
        assert d["agents_blocks"] == base["agents_blocks"]


@pytest.mark.slow
@pytest.mark.e2e
def test_reinstall_idempotent(forge_venv, tmp_path):
    """Reinstall writes nothing new: consumer docs + context registry are
    byte-identical and no managed block is duplicated. Forge-owned state
    dirs (receipts/ledger) may embed timestamps — excluded on purpose."""
    root = tmp_path / "re"
    _seed_user_docs(root)
    for key in ("spark-forge-aws", "api-forge"):
        _install(forge_venv, key, root)
    docs_before = {
        name: (root / name).read_bytes()
        for name in ("AGENTS.md", "CLAUDE.md", "AGENT_PROTOCOL.md")
    }
    ctx_before = {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted((root / ".forge" / "context").rglob("*"))
        if p.is_file()
    }
    for key in ("spark-forge-aws", "api-forge"):
        out = _install(forge_venv, key, root)
        assert out.get("status") in ("completed", "unchanged", "ok"), out.get("status")
    docs_after = {
        name: (root / name).read_bytes()
        for name in ("AGENTS.md", "CLAUDE.md", "AGENT_PROTOCOL.md")
    }
    ctx_after = {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted((root / ".forge" / "context").rglob("*"))
        if p.is_file()
    }
    assert docs_after == docs_before
    assert ctx_after == ctx_before
    # no duplicated managed blocks
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    for fid in ("spark-forge-aws", "api-forge"):
        assert agents.count(f"forge:{fid}:begin") == 1


@pytest.mark.slow
@pytest.mark.e2e
def test_uninstall_one_forge_others_survive(forge_venv, tmp_path):
    root = tmp_path / "sel"
    _seed_user_docs(root)
    order = ("spark-forge-aws", "api-forge", "platform-forge")
    for key in order:
        _install(forge_venv, key, root)
    _uninstall(forge_venv, "api-forge", root)
    reg = _registry(root)
    fids = {e.get("forge_id") for e in reg.get("forges", [])}
    assert fids == {"spark-forge-aws", "platform-forge"}, fids
    ctx = root / ".forge" / "context"
    assert not (ctx / "capabilities" / "api-forge.json").exists()
    for fid in ("spark-forge-aws", "platform-forge"):
        assert (ctx / "capabilities" / f"{fid}.json").is_file()
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "forge:api-forge:" not in agents
    for fid in ("spark-forge-aws", "platform-forge"):
        assert f"forge:{fid}:begin" in agents
    proto = (root / "AGENT_PROTOCOL.md").read_text(encoding="utf-8")
    assert "api-forge" not in proto
    assert agents.startswith(USER_MARK_AGENTS)


@pytest.mark.slow
@pytest.mark.e2e
def test_stale_lock_recovers_on_next_op(forge_venv, tmp_path):
    root = tmp_path / "kill"
    _seed_user_docs(root)
    _install(forge_venv, "spark-forge-azure", root)
    ctx = root / ".forge" / "context"
    # simulate a kill-mid-install: lock file with dead pid + stale mtime
    lock = ctx / ".context.lock"
    lock.write_text(
        json.dumps({"pid": 2**22, "created_at": "2020-01-01T00:00:00Z"}),
        encoding="utf-8",
    )
    os.utime(lock, (946684800, 946684800))  # 2000-01-01 — undeniably stale
    # the next op — here an install of a second forge — must reclaim it
    _install(forge_venv, "platform-forge", root)
    reg = _registry(root)
    fids = {e.get("forge_id") for e in reg.get("forges", [])}
    assert fids == {"spark-forge-azure", "platform-forge"}, fids
    assert not lock.exists() or json.loads(lock.read_text())["pid"] != 2**22


@pytest.mark.slow
@pytest.mark.e2e
def test_registry_works_without_the_forge(forge_venv, tmp_path):
    root = tmp_path / "noctl"
    _seed_user_docs(root)
    for key in ("spark-forge-aws", "spark-forge-azure", "api-forge", "platform-forge"):
        _install(forge_venv, key, root)
    reg = _assert_composed_state(root, FORGE_IDS[1:])
    assert "the-forge" not in {e.get("forge_id") for e in reg.get("forges", [])}
    # routing document exists and lists the specialists
    routing = (root / ".forge" / "context" / "ROUTING.md").read_text(encoding="utf-8")
    for fid in ("spark-forge-aws", "spark-forge-azure", "api-forge", "platform-forge"):
        assert fid in routing


@pytest.mark.slow
@pytest.mark.e2e
def test_vendored_forgecontext_parity(forge_venv):
    """All five wheels carry the same _forgecontext.py body — only the
    ``_SOURCE_SHA256`` stamp may differ."""
    venv_dir = forge_venv["venv"]
    site = next(venv_dir.glob("lib/python*/site-packages"))
    bodies: dict[str, str] = {}
    for key in FORGES:
        pkg = {
            "the-forge": "theforge",
            "spark-forge-aws": "sparkforge_aws",
            "spark-forge-azure": "sparkforge_azure",
            "api-forge": "apiforge",
            "platform-forge": "platformforge",
        }[key]
        path = site / pkg / "_forgecontext.py"
        assert path.is_file(), f"{key}: {path} missing from wheel"
        # normalize the stamp line entirely — only _SOURCE_SHA256 may differ
        lines = path.read_bytes().split(b"\n")
        body = b"\n".join(
            b'_SOURCE_SHA256 = "stamp"' if line.startswith(b'_SOURCE_SHA256 = "') else line
            for line in lines
        )
        bodies[key] = _sha(body)
    assert len(set(bodies.values())) == 1, bodies
