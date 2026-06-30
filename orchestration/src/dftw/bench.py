"""Benchpark introspection: discovery + system facts, used to power the wizard."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
from typing import TYPE_CHECKING, Optional

from . import benchpark

if TYPE_CHECKING:
    from .config import Config

_MEMO: dict[str, str] = {}  # in-process cache, also memoizes the benchpark commit


def _bench_sha(cfg: Config) -> str:
    """Commit of the vendored benchpark; the discovery cache key (auto-invalidates)."""
    if "_sha" not in _MEMO:
        out = subprocess.run(
            ["git", "-C", str(cfg.root / "vendor" / "benchpark"), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        )
        _MEMO["_sha"] = out.stdout.strip() or "unknown"
    return _MEMO["_sha"]


def _capture(cfg: Config, *args: str, timeout: int = 240) -> str:
    """Run `benchpark <args>` and return stdout, cached by (benchpark commit, args)."""
    sha = _bench_sha(cfg)
    key = f"{sha}|{' '.join(args)}"
    if key in _MEMO:
        return _MEMO[key]
    cache = cfg.root / ".dftw" / "cache" / "benchpark.json"
    disk = {}
    if cache.exists():
        try:
            disk = json.loads(cache.read_text())
        except (json.JSONDecodeError, OSError):
            disk = {}
    if disk.get("_sha") == sha and key in disk:
        _MEMO[key] = disk[key]
        return disk[key]

    bin = benchpark.benchpark_bin(cfg.root)
    if not bin.exists():
        return ""
    cmd = [sys.executable, str(bin), "--config", str(benchpark.config_dir(cfg.root)), *args]
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=benchpark.env(cfg.root)
        )
    except (subprocess.TimeoutExpired, OSError):
        return ""
    text = out.stdout or ""
    if text.strip():  # cache only successful, non-empty results
        disk = disk if disk.get("_sha") == sha else {"_sha": sha}
        disk[key] = text
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(disk))
        except OSError:
            pass
        _MEMO[key] = text
    return text


def _list(cfg: Config, kind: str) -> list[str]:
    """`benchpark list <kind>` -> sorted names (kind: experiments|systems|modifiers)."""
    names = []
    for raw in _capture(cfg, "list", kind).splitlines():
        if not raw[:1].isspace() or not raw.strip():  # headers are flush-left
            continue
        names.append(raw.strip().split("+", 1)[0].split()[0])
    return sorted(set(names))


def experiments(cfg: Config) -> list[str]:
    """dftw's own DFTracer-instrumented experiments (repo/experiments/*)."""
    d = cfg.root / "repo" / "experiments"
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if (p / "experiment.py").exists())


def systems(cfg: Config) -> list[str]:
    return _list(cfg, "systems")


def clusters(cfg: Config, system: str) -> list[str]:
    """Cluster/instance_type values a system offers (from `benchpark info system`)."""
    text = _capture(cfg, "info", "system", system.split()[0])
    found = []
    for m in re.finditer(r"values:\s*\(([^)]*)\)", text):
        found += [v.strip().strip("'\"") for v in m.group(1).split(",") if v.strip()]
    # info also prints each cluster as a top-level key under "Hardware:"
    for line in text.splitlines():
        key = re.match(r"^\s{4}([A-Za-z0-9_.-]+):\s*$", line)
        if key:
            found.append(key.group(1))
    return sorted(set(found))


def gpu_runtime(cfg: Config, system_spec: str) -> Optional[str]:
    """GPU programming model benchpark associates with a system: 'rocm'|'cuda'|None.

    Read from `benchpark info system` (accelerator vendor / tested runtime), so the
    wizard's '+rocm' suggestion comes from benchpark, not a hardcoded assumption.
    """
    text = _capture(cfg, "info", "system", system_spec.split()[0]).lower()
    if not text:
        return None
    if "runtime: rocm" in text or "vendor: amd" in text:
        return "rocm"
    if "runtime: cuda" in text or "vendor: nvidia" in text:
        return "cuda"
    return None


def detect_cluster() -> Optional[str]:
    """Best-effort current cluster from the hostname (e.g. tuolumne1001 -> tuolumne)."""
    if os.environ.get("DFTW_SYSTEM"):
        return None  # explicit override wins; nothing to detect
    host = socket.gethostname()
    token = re.match(r"^([a-zA-Z][a-zA-Z-]*?)\d*$", host.split(".")[0])
    return token.group(1).lower() if token else None


def detect_system(cfg: Config) -> Optional[str]:
    """Map the current host to a full benchpark system spec, via benchpark's catalog.

    Returns e.g. 'llnl-elcapitan cluster=tuolumne' when the hostname token matches a
    cluster value of some system; otherwise None (wizard then has no preselection).
    """
    token = detect_cluster()
    if not token:
        return None
    for sysname in systems(cfg):
        cl = clusters(cfg, sysname)
        if token in (c.lower() for c in cl):
            return f"{sysname} cluster={token}"
    return None
