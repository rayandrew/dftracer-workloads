from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import yaml

from . import data as datamod

if TYPE_CHECKING:
    from .config import Config


def manifest_path(cfg: Config, workload: str) -> Path:
    # The staging pipeline lives with the workload's benchpark package (in-repo).
    return (
        cfg.root / "repo" / "spack_repo" / "dftw" / "packages" / workload / "data" / "prepare.yaml"
    )


def _done(marker: Path) -> bool:
    if not marker.exists():
        return False
    return marker.is_file() or any(marker.iterdir())


def _format(s: str, ctx: dict[str, Any]) -> str:
    return s.format(**ctx)


def _log(msg: str) -> None:
    """Engine progress goes to stderr; stdout is reserved for the result (the CLI
    echoes the prepared path via typer). Keeps this module free of the CLI framework."""
    print(msg, file=sys.stderr)


def _prep_venv(cfg: Config, workload: str, reqs: Path) -> Path:
    """A dedicated per-workload venv for data prep under .dftw/venvs."""
    venv = cfg.root / ".dftw" / "venvs" / f"prep-{workload}"
    py = venv / "bin" / "python"
    if not py.exists():
        _log(f"[venv]  creating prep venv ({venv})")
        venv.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, "-m", "venv", "--upgrade-deps", str(venv)], check=True)
    if reqs.exists():
        _log(f"[deps]  installing {reqs.name} into the prep venv")
        subprocess.run(
            [
                str(py),
                "-m",
                "pip",
                "install",
                "--quiet",
                "--disable-pip-version-check",
                "-r",
                str(reqs),
            ],
            check=True,
        )
    return venv


def _stage_env(venv_bin: Path) -> dict[str, str]:
    """Stage subprocess env: the prep venv's bin on PATH so `python3`/`pip` resolve to it."""
    env = os.environ.copy()
    env["PATH"] = f"{venv_bin}{os.pathsep}{env.get('PATH', '')}"
    return env


def prepare(
    cfg: Config,
    workload: str,
    dest: Optional[str] = None,
    work: Optional[str] = None,
    params: Optional[dict[str, str]] = None,
    keep_work: bool = False,
) -> Path:
    manifest = manifest_path(cfg, workload)
    if not manifest.exists():
        raise SystemExit(f"no data prepare manifest: {manifest}")
    spec = yaml.safe_load(manifest.read_text()) or {}

    root = Path(dest) if dest else datamod.canonical(cfg, workload)
    workdir = Path(work) if work else root.with_name(root.name + ".prepare")
    merged = {**(spec.get("params") or {}), **(params or {})}
    ctx: dict[str, Any] = {
        "DEST": str(root),
        "WORK": str(workdir),
        "DATADIR": str(manifest.parent),
        **merged,
    }
    stages = spec.get("stages", [])
    done = [_done(Path(_format(st["produces"], ctx))) for st in stages]
    last_done = max((i for i, d in enumerate(done) if d), default=-1)

    env = os.environ.copy()
    if last_done < len(stages) - 1:
        venv = _prep_venv(cfg, workload, manifest.parent / "requirements.txt")
        env = _stage_env(venv / "bin")

    for i, st in enumerate(stages):
        name = st["name"]
        if i <= last_done:
            _log(f"[skip] {name}")
            continue
        if st.get("manual"):
            _log(_instructions(st, ctx, f"manual step required: {name}"))
            raise SystemExit(2)
        _log(f"[run]  {name}")
        rc = subprocess.run(["bash", "-c", _format(st["run"], ctx)], env=env)
        if rc.returncode != 0:
            _log(_instructions(st, ctx, f"stage failed: {name}"))
            raise SystemExit(rc.returncode)

    if work is None and not keep_work and workdir.exists():
        _log(f"[clean] removing intermediates ({workdir})")
        shutil.rmtree(workdir, ignore_errors=True)

    _log(f"[done]  prepared {root}")
    return root


def _instructions(st: dict[str, Any], ctx: dict[str, Any], header: str) -> str:
    body = st.get("instructions")
    text = f"\n{header}\n"
    if body:
        text += "\n" + _format(str(body), ctx)
    return text
