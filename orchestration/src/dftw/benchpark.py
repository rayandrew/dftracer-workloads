from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Config


def benchpark_bin(root: Path) -> Path:
    return root / "vendor" / "benchpark" / "bin" / "benchpark"


def config_dir(root: Path) -> Path:
    return root / "benchpark-config"


def run(cfg: Config, *args: str, check: bool = True) -> "subprocess.CompletedProcess[bytes]":
    bin = benchpark_bin(cfg.root)
    if not bin.exists():
        raise SystemExit("benchpark missing: run `git submodule update --init --recursive`")
    cmd = [sys.executable, str(bin), "--config", str(config_dir(cfg.root)), *args]
    return subprocess.run(cmd, check=check)
