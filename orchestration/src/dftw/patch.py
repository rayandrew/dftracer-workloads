from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .config import Config


def package_dir(cfg: Config, name: str) -> Path:
    return cfg.root / "repo" / "spack_repo" / "dftw" / "packages" / name


def pkg_info(cfg: Config, name: str) -> dict[str, str]:
    """The source-of-truth for a workload's source"""
    pkg = package_dir(cfg, name) / "package.py"
    if not pkg.exists():
        raise SystemExit(f"no spack package for {name}: {pkg}")
    text = pkg.read_text()

    def grab(pattern: str, default: Optional[str] = None) -> Optional[str]:
        m = re.search(pattern, text)
        return m.group(1) if m else default

    repo = grab(r"""git\s*=\s*['"]([^'"]+)['"]""")
    commit = grab(r"""commit\s*=\s*['"]([0-9a-fA-F]{7,40})['"]""")
    if not (repo and commit):
        raise SystemExit(f"cannot parse git/commit from {pkg}")
    subdir = grab(r"""git_sparse_paths\s*=\s*\[\s*['"]([^'"]+)['"]""", "") or ""
    patch = grab(r"""patch\(\s*['"]([^'"]+)['"]""", "dftracer.patch") or "dftracer.patch"
    return {"repo": repo, "commit": commit, "subdir": subdir, "patch": patch}


def dev_dir(cfg: Config, name: str) -> Path:
    return cfg.root / ".dftw" / "dev" / name


def _git(cwd: Path, *args: str, **kw: Any) -> "subprocess.CompletedProcess[Any]":
    return subprocess.run(["git", *args], cwd=str(cwd), check=True, **kw)


def edit(cfg: Config, name: str, editor: Optional[str] = None) -> None:
    info = pkg_info(cfg, name)
    dev = dev_dir(cfg, name)
    if not dev.exists():
        dev.parent.mkdir(parents=True, exist_ok=True)
        _git(cfg.root, "clone", info["repo"], str(dev))
    _git(dev, "fetch", "--all", "--tags")
    _git(dev, "checkout", "--force", info["commit"])
    patch = package_dir(cfg, name) / info["patch"]
    if patch.exists() and patch.stat().st_size:
        _git(dev, "apply", "--3way", str(patch))
    _open_editor(dev / info["subdir"], editor)


def save(cfg: Config, name: str) -> Path:
    info = pkg_info(cfg, name)
    dev = dev_dir(cfg, name)
    if not dev.exists():
        raise SystemExit(f"no dev checkout for {name}: run `dftw patch edit {name}`")
    diff = subprocess.run(
        ["git", "diff", info["commit"], "--", info["subdir"] or "."],
        cwd=str(dev),
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    patch = package_dir(cfg, name) / info["patch"]
    patch.write_text(diff)
    return patch


def status(cfg: Config, name: str) -> None:
    info = pkg_info(cfg, name)
    dev = dev_dir(cfg, name)
    if not dev.exists():
        raise SystemExit(f"no dev checkout for {name}")
    _git(dev, "status", "--short", "--", info["subdir"] or ".")


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
