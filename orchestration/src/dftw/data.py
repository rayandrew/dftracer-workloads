from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .config import Config

MARKER_SUFFIX = ".dftw-staged"


def canonical(cfg: Config, name: str) -> Path:
    """Resolve the dataset location from deployment env (dftw is zero-config).

    DFTW_DATA_DIR is the full path; DFTW_DATA_ROOT/<name> is the convenience form.
    """
    full = os.environ.get("DFTW_DATA_DIR")
    if full:
        return Path(full)
    root = os.environ.get("DFTW_DATA_ROOT")
    if not root:
        raise SystemExit("set DFTW_DATA_DIR (full path) or DFTW_DATA_ROOT, or pass --from/--dest")
    return Path(root) / name


def _fingerprint(path: Path) -> str:
    n = 0
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            n += 1
            total += p.stat().st_size
    return f"{n} {total}"


def _marker(target: Path) -> Path:
    return target.with_name(target.name + MARKER_SUFFIX)


def _rsync(source: Path, target: Path) -> None:
    if shutil.which("rsync"):
        subprocess.run(["rsync", "-a", "--delete", f"{source}/", f"{target}/"], check=True)
    else:
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)


def stage(
    cfg: Config, name: str, src: Optional[str], dst: str, link: bool = False
) -> tuple[Path, str]:
    source = Path(src) if src else canonical(cfg, name)
    target = Path(dst)
    if not source.exists():
        raise SystemExit(f"source does not exist: {source}")

    want = _fingerprint(source)
    marker = _marker(target)
    if target.exists() and marker.exists() and marker.read_text().strip() == want:
        return target, "up-to-date"

    target.parent.mkdir(parents=True, exist_ok=True)
    if link:
        if target.is_symlink() or target.exists():
            target.unlink() if target.is_symlink() else shutil.rmtree(target)
        target.symlink_to(source)
        action = "linked"
    else:
        _rsync(source, target)
        action = "copied"
    marker.write_text(want)
    return target, action


def status(cfg: Config, name: str, dst: str) -> str:
    target = Path(dst)
    marker = _marker(target)
    if not target.exists():
        return "absent"
    if not marker.exists():
        return "present (unmanaged)"
    if marker.read_text().strip() == _fingerprint(canonical(cfg, name)):
        return "staged (up-to-date)"
    return "staged (stale)"
