"""Packaging gates (7.2-7.4), exercised through the same scripts the CI runs.

The gate logic lives only in ``scripts/ci/``; these tests call those scripts instead of
re-implementing the checks, so local runs and CI cannot drift apart.
"""

import importlib.util
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from email.parser import HeaderParser
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).parents[1]
CI_SCRIPTS = REPO / "scripts" / "ci"
ZERO_DEPS = CI_SCRIPTS / "check_zero_deps.py"
FRESH_INSTALL = CI_SCRIPTS / "fresh_install.py"

ARTIFICIAL_DEP = "requests>=2.0"


def _run_script(
    script: Path, *args: str | Path, timeout: float = 120
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *map(str, args)],
        capture_output=True, text=True, timeout=timeout,
    )


def _write_pyproject(path: Path, dependencies: str) -> Path:
    path.write_text(
        '[project]\nname = "theforge"\nversion = "0.1.0"\n'
        f"dependencies = {dependencies}\n",
        encoding="utf-8",
    )
    return path


def _fake_wheel(path: Path, requires: list[str]) -> Path:
    metadata = "Metadata-Version: 2.3\nName: theforge\nVersion: 0.1.0\n"
    metadata += "".join(f"Requires-Dist: {req}\n" for req in requires)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("theforge/__init__.py", "")
        zf.writestr("theforge-0.1.0.dist-info/METADATA", metadata)
    return path


def _inject_requirement(wheel: Path, dest: Path, requirement: str) -> Path:
    """Copy ``wheel`` to ``dest`` adding an unmarked ``Requires-Dist`` to its METADATA."""
    with zipfile.ZipFile(wheel) as src, zipfile.ZipFile(dest, "w") as out:
        for item in src.infolist():
            data = src.read(item)
            if item.filename.endswith(".dist-info/METADATA"):
                head, sep, body = data.decode("utf-8").partition("\n\n")
                data = f"{head}\nRequires-Dist: {requirement}{sep}{body}".encode()
            out.writestr(item, data)
    return dest


# --- zero runtime dependencies (7.3) -------------------------------------------------------


def test_zero_deps_gate_accepts_project() -> None:
    out = _run_script(ZERO_DEPS)
    assert out.returncode == 0, out.stdout + out.stderr


def test_zero_deps_gate_rejects_declared_runtime_dependency(tmp_path: Path) -> None:
    pyproject = _write_pyproject(tmp_path / "pyproject.toml", f'["{ARTIFICIAL_DEP}"]')
    out = _run_script(ZERO_DEPS, "--pyproject", pyproject)
    assert out.returncode != 0
    assert "requests" in out.stderr


def test_zero_deps_gate_rejects_unmarked_wheel_requirement(tmp_path: Path) -> None:
    pyproject = _write_pyproject(tmp_path / "pyproject.toml", "[]")
    wheel = _fake_wheel(tmp_path / "theforge-0.1.0-py3-none-any.whl",
                        ['pytest>=8.0; extra == "dev"', 'requests; python_version >= "3.11"'])
    out = _run_script(ZERO_DEPS, "--pyproject", pyproject, wheel)
    assert out.returncode != 0
    assert "requests" in out.stderr
    assert "pytest" not in out.stderr


def test_zero_deps_gate_accepts_extra_only_wheel_requirements(tmp_path: Path) -> None:
    pyproject = _write_pyproject(tmp_path / "pyproject.toml", "[]")
    wheel = _fake_wheel(tmp_path / "theforge-0.1.0-py3-none-any.whl",
                        ['pytest>=8.0; extra == "dev"', "mypy>=1.10 ; extra=='dev'"])
    out = _run_script(ZERO_DEPS, "--pyproject", pyproject, wheel)
    assert out.returncode == 0, out.stdout + out.stderr


def test_zero_deps_gate_fails_when_glob_matches_no_wheel(tmp_path: Path) -> None:
    out = _run_script(ZERO_DEPS, tmp_path / "dist" / "*.whl")
    assert out.returncode != 0
    assert "no wheel" in out.stderr.lower()


def _fresh_install_module() -> Any:
    spec = importlib.util.spec_from_file_location("fresh_install", FRESH_INSTALL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(("change", "needle"), [
    ({"requires": ["requests>=2.0"]}, "runtime requirements"),
    ({"requires": ["pytest; extra=='dev'", "requests; python_version>'3'"]}, "runtime"),
    ({"console_scripts": {"theforge": "x:y", "forge": "theforge.cli.main:main"}},
     "entry points"),
    ({"direct_url": '{"url": "file:///w", "dir_info": {"editable": true}}'}, "editable"),
    ({"module_file": "REPO"}, "not the fresh venv"),
])
def test_fresh_install_metadata_check_rejects_bad_installs(
    tmp_path: Path, change: dict[str, Any], needle: str
) -> None:
    gate = _fresh_install_module()
    # The real gate builds its venv outside the repository; tmp_path may live inside it
    # (addopts --basetemp=.pytest_tmp), which the gate rightly treats as "not fresh". The
    # path is only compared, never created.
    venv = Path(tempfile.gettempdir()) / f"theforge-probe-{tmp_path.name}" / "venv"
    probe: dict[str, Any] = {
        "name": "theforge", "version": "1.2.3", "requires_python": ">=3.11",
        "requires": ["pytest; extra == 'dev'", "ruff; extra=='dev'"],
        "console_scripts": {"theforge": "theforge.cli.main:main",
                            "forge": "theforge.cli.main:main"},
        "module_file": str(venv / "Lib" / "site-packages" / "theforge" / "__init__.py"),
        "direct_url": '{"url": "file:///w.whl", "archive_info": {}}',
    }
    wheel = tmp_path / "theforge-1.2.3-py3-none-any.whl"
    gate.check_metadata(probe, wheel, venv)  # the baseline probe is accepted
    probe.update(change)
    if probe["module_file"] == "REPO":
        probe["module_file"] = str(REPO / "src" / "theforge" / "__init__.py")
    with pytest.raises(gate.GateError, match=needle):
        gate.check_metadata(probe, wheel, venv)


# --- built wheel: zero deps + clean install (7.2, 7.3, 7.4) --------------------------------


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    dist = tmp_path_factory.mktemp("dist")
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--quiet",
         "--disable-pip-version-check", "--wheel-dir", str(dist), str(REPO)],
        check=True, timeout=600,
    )
    wheels = sorted(dist.glob("theforge-*.whl"))
    assert len(wheels) == 1, wheels
    return wheels[0]


@pytest.mark.slow
def test_ci_gates_pass_on_built_wheel(built_wheel: Path) -> None:
    zero = _run_script(ZERO_DEPS, built_wheel.parent / "*.whl")
    assert zero.returncode == 0, zero.stdout + zero.stderr
    fresh = _run_script(FRESH_INSTALL, built_wheel, timeout=900)
    assert fresh.returncode == 0, fresh.stdout + fresh.stderr
    for step in ("pip check", "entry points", "doctor", "init", "demo.echo"):
        assert step in fresh.stdout, step


@pytest.mark.slow
def test_ci_gates_fail_on_artificial_runtime_dependency(built_wheel: Path, tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    shutil.copyfile(REPO / "pyproject.toml", pyproject)
    text = pyproject.read_text(encoding="utf-8")
    assert "dependencies = []" in text
    tainted_text = text.replace("dependencies = []", f'dependencies = ["{ARTIFICIAL_DEP}"]', 1)
    pyproject.write_text(tainted_text, encoding="utf-8")
    declared = _run_script(ZERO_DEPS, "--pyproject", pyproject, built_wheel)
    assert declared.returncode != 0
    assert "requests" in declared.stderr

    tainted_dir = tmp_path / "tainted"
    tainted_dir.mkdir()
    tainted = _inject_requirement(built_wheel, tainted_dir / built_wheel.name, ARTIFICIAL_DEP)
    shipped = _run_script(ZERO_DEPS, tainted)
    assert shipped.returncode != 0
    assert "requests" in shipped.stderr


# --- adapters are separate distributions (real-provider-integration 1.4) -------------------


AGENTIC_SDIST_EXCLUDES = (
    "/.claude", "/.agents", "/.devin", "/.codex", "/.kiro", "/.tokensave",
    "/CLAUDE.md", "/AGENTS.md",
)


def test_theforge_build_config_keeps_adapters_out_of_wheel_and_sdist() -> None:
    with (REPO / "pyproject.toml").open("rb") as fh:
        data = tomllib.load(fh)
    assert data["project"]["dependencies"] == []
    targets = data["tool"]["hatch"]["build"]["targets"]
    assert targets["wheel"]["packages"] == ["src/theforge"]
    assert "/adapters" in targets["sdist"]["exclude"]
    # Agentic assets and local-only state never ship (agentic-maintainability, requirement 5.2).
    assert set(AGENTIC_SDIST_EXCLUDES) <= set(targets["sdist"]["exclude"])


def _runtime_requirements(metadata: str) -> list[str]:
    requires = HeaderParser().parsestr(metadata).get_all("Requires-Dist") or []
    return [req for req in requires if "extra" not in req.partition(";")[2]]


@pytest.fixture(scope="module")
def built_sdist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    dist = tmp_path_factory.mktemp("sdist")
    subprocess.run(
        [sys.executable, "-m", "build", "--sdist", "--outdir", str(dist), str(REPO)],
        check=True, timeout=600, capture_output=True,
    )
    sdists = sorted(dist.glob("theforge-*.tar.gz"))
    assert len(sdists) == 1, sdists
    return sdists[0]


@pytest.mark.slow
def test_built_wheel_excludes_adapters_and_has_no_runtime_dependency(built_wheel: Path) -> None:
    with zipfile.ZipFile(built_wheel) as zf:
        names = zf.namelist()
        metadata = next(n for n in names if n.endswith(".dist-info/METADATA"))
        assert _runtime_requirements(zf.read(metadata).decode("utf-8")) == []
    assert names
    assert not [n for n in names if n.startswith("adapters/") or "theforge_" in n.split("/")[0]]


@pytest.mark.slow
def test_built_sdist_excludes_adapters_and_has_no_runtime_dependency(built_sdist: Path) -> None:
    with tarfile.open(built_sdist) as tf:
        members = [m.name.partition("/")[2] for m in tf.getmembers()]
        root = tf.getmembers()[0].name.partition("/")[0]
        pkg_info = tf.extractfile(f"{root}/PKG-INFO")
        assert pkg_info is not None
        metadata = pkg_info.read().decode("utf-8")
    assert "src/theforge/__init__.py" in members
    assert not [m for m in members if m == "adapters" or m.startswith("adapters/")]
    agentic = tuple(d.lstrip("/") for d in AGENTIC_SDIST_EXCLUDES)
    assert not [m for m in members if m.split("/")[0] in agentic]
    assert _runtime_requirements(metadata) == []
