from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

# Unambiguous marker for "this is the dftw repo": its out-of-tree benchpark objects.
_MARKER = Path("repo") / "spack_repo"


def repo_root(start: Optional[Union[Path, str]] = None) -> Path:
    """Locate the repo root: DFTW_ROOT (set by bin/dftw) else walk up for the marker."""
    env = os.environ.get("DFTW_ROOT")
    if env and (Path(env) / _MARKER).exists():
        return Path(env).resolve()
    p = Path(start or Path.cwd()).resolve()
    for d in [p, *p.parents]:
        if (d / _MARKER).exists():
            return d
    raise SystemExit("not inside a dftw repo (set DFTW_ROOT or run from the repo tree)")


class Config:
    def __init__(self, root: Path) -> None:
        self.root = root


def load(start: Optional[Union[Path, str]] = None) -> Config:
    return Config(repo_root(start))
