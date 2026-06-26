from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .config import Config


def dev_dir(cfg: Config, name: str) -> Path:
    return cfg.root / ".dftw" / "dev" / name


def patch_path(cfg: Config, name: str, wl: dict[str, Any]) -> Path:
    rel = wl.get("patch", f"repo/spack_repo/dftw/packages/{name}/dftracer.patch")
    return cfg.root / rel


def _git(cwd: Path, *args: str, **kw: Any) -> "subprocess.CompletedProcess[Any]":
    return subprocess.run(["git", *args], cwd=str(cwd), check=True, **kw)


def edit(cfg: Config, name: str, editor: Optional[str] = None) -> None:
    wl = cfg.workload(name)
    dev = dev_dir(cfg, name)
    if not dev.exists():
        dev.parent.mkdir(parents=True, exist_ok=True)
        _git(cfg.root, "clone", wl["repo"], str(dev))
    _git(dev, "fetch", "--all", "--tags")
    _git(dev, "checkout", "--force", wl["ref"])
    patch = patch_path(cfg, name, wl)
    if patch.exists() and patch.stat().st_size:
        _git(dev, "apply", "--3way", str(patch))
    _open_editor(dev, editor)


def save(cfg: Config, name: str) -> Path:
    wl = cfg.workload(name)
    dev = dev_dir(cfg, name)
    if not dev.exists():
        raise SystemExit(f"no dev checkout for {name}: run `dftw patch edit {name}`")
    diff = subprocess.run(
        ["git", "diff", wl["ref"]], cwd=str(dev), check=True, capture_output=True, text=True
    ).stdout
    patch = patch_path(cfg, name, wl)
    patch.parent.mkdir(parents=True, exist_ok=True)
    patch.write_text(diff)
    return patch


def status(cfg: Config, name: str) -> None:
    dev = dev_dir(cfg, name)
    if not dev.exists():
        raise SystemExit(f"no dev checkout for {name}")
    _git(dev, "status", "--short")


def reset(cfg: Config, name: str) -> None:
    dev = dev_dir(cfg, name)
    if dev.exists():
        shutil.rmtree(dev)


def _open_editor(path: Path, editor: Optional[str]) -> None:
    editor = editor or os.environ.get("DFTW_EDITOR")
    if editor:
        subprocess.run([*editor.split(), str(path)])
    elif shutil.which("code"):
        subprocess.run(["code", "--wait", str(path)])
    elif os.environ.get("EDITOR"):
        subprocess.run([os.environ["EDITOR"], str(path)])
    else:
        subprocess.run([os.environ.get("SHELL", "bash")], cwd=str(path))
