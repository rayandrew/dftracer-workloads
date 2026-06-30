from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from .config import Config


def benchpark_bin(root: Path) -> Path:
    return root / "vendor" / "benchpark" / "bin" / "benchpark"


def config_dir(root: Path) -> Path:
    return root / "benchpark-config"


def bootstrap_home(root: Path) -> Path:
    """The ramble/spack bootstrap location, read from benchpark-config/bootstrap.yaml."""
    data = yaml.safe_load((config_dir(root) / "bootstrap.yaml").read_text())
    return Path(os.path.expanduser(data["bootstrap"]["location"]))


def tool_bin(root: Path, tool: str) -> Path:
    """Path to a bootstrapped tool binary (ramble | spack)."""
    return bootstrap_home(root) / tool / "bin" / tool


def lib_dir(root: Path) -> Path:
    """Shared python for our benchpark objects (e.g. the DFTracer/PyTorch experiment mixins)."""
    return root / "repo" / "lib"


def env(root: Path) -> dict[str, str]:
    """Process env with dftw's shared lib on PYTHONPATH so experiment.py can import it."""
    e = dict(os.environ)
    prev = e.get("PYTHONPATH", "")
    e["PYTHONPATH"] = f"{lib_dir(root)}{os.pathsep}{prev}" if prev else str(lib_dir(root))
    return e


def run(
    cfg: Config, *args: str, check: bool = True, quiet: bool = False
) -> "subprocess.CompletedProcess[Any]":
    """Invoke the vendored benchpark CLI."""
    bin = benchpark_bin(cfg.root)
    if not bin.exists():
        raise SystemExit("benchpark missing: run `git submodule update --init --recursive`")
    cmd = [sys.executable, str(bin), "--config", str(config_dir(cfg.root)), *args]
    if not (quiet and not os.environ.get("DFTW_VERBOSE")):
        return subprocess.run(cmd, check=check, env=env(cfg.root))
    r = subprocess.run(cmd, env=env(cfg.root), capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stdout or "")
        sys.stderr.write(r.stderr or "")
        if check:
            raise SystemExit(
                f"benchpark {args[0]} failed (exit {r.returncode}); re-run with --verbose"
            )
    return r
