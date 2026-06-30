"""Discover and describe scaffolded workspaces for the `dftw workspace` commands."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import yaml

from . import runner

if TYPE_CHECKING:
    from .config import Config


_MODES = ("off", "normal", "agg-full", "agg-selective")


@dataclass
class Workspace:
    system: str  # benchpark system spec, e.g. "llnl-elcapitan cluster=tuolumne"
    experiment: str  # benchpark experiment spec, e.g. "unet3d +rocm package_manager=spack-pip"
    workload: str
    exprdir: Path  # where the ramble.yaml dftw injects into lives
    path: Path  # the ramble workspace dir
    built: bool  # has the spack-pip venv been created?
    mode: str  # the ACTIVE (latest-edited) mode -- what list/edit/run act on
    modes: list[str]  # every mode that has a rendered output dir (mode is in the experiment name)
    nodes: str
    queue: str
    timeout: str
    data_dir: str

    @property
    def name(self) -> str:
        """Stable id used for fuzzy matching + display, e.g. 'tuolumne…/unet3d'."""
        return f"{runner._slug(self.system)}/{self.workload}"


def _rendered_modes(workspace_path: Path) -> list[str]:
    """Modes that have an execute dir (mode is the trailing token of the experiment name)."""
    found = set()
    for ex in workspace_path.glob("experiments/*/*/*/execute_experiment"):
        tail = ex.parent.name.rsplit("_", 1)[-1]
        if tail in _MODES:
            found.add(tail)
    return sorted(found)


def _run_params(ramble_yaml: Path) -> dict[str, str]:
    """Pull the live run-params out of a workspace's ramble.yaml."""
    rd = yaml.safe_load(ramble_yaml.read_text()) or {}
    rb = rd.get("ramble", {})
    top = rb.get("variables", {}) or {}

    mode = "?"
    for m in rb.get("modifiers", []) or []:
        if isinstance(m, dict) and m.get("name") == "dftracer":
            mode = str(m.get("mode", "?"))

    exp: dict = {}

    def walk(node: object) -> None:
        if isinstance(node, dict):
            block = node.get("variables")
            if isinstance(block, dict) and "n_gpus" in block:
                exp.update(block)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(rb.get("applications", {}))
    return {
        "mode": mode,
        "nodes": str(top.get("n_nodes", exp.get("n_nodes", "?"))),
        "queue": str(top.get("queue", "default")),
        "timeout": str(exp.get("timeout", top.get("timeout", "?"))),
        "data_dir": str(top.get("data_dir", "-")),
    }


def discover(cfg: Config, work: Optional[str] = None) -> list[Workspace]:
    """All scaffolded workspaces under the (overridable) work root."""
    wr = runner.work_root(cfg, work)
    exproot = wr / "runs"
    out: list[Workspace] = []
    for meta_file in sorted((wr / "systems").glob("*/*/.dftw-meta")):
        exprdir = meta_file.parent
        ramble_yaml = exprdir / "ramble.yaml"
        if not ramble_yaml.exists():
            continue
        try:
            meta = json.loads(meta_file.read_text())
        except (OSError, ValueError):
            continue
        experiment = meta["experiment"]
        wl = runner.workload_name(experiment)
        sysslug = exprdir.parent.name
        path = exproot / sysslug / wl / "workspace"
        venv = path / "software" / "spack-pip" / wl / ".venv"
        out.append(
            Workspace(
                system=meta["system"],
                experiment=experiment,
                workload=wl,
                exprdir=exprdir,
                path=path,
                built=venv.is_dir(),
                modes=_rendered_modes(path),
                **_run_params(ramble_yaml),
            )
        )
    return out


def _editor_cmd() -> list[str]:
    """Best available editor: an explicit $EDITOR/$VISUAL wins; otherwise prefer the IDE if
    its CLI is on PATH (VSCode/Cursor remote inject `code`/`cursor`) with --wait so we block
    until the tab closes; then fall back to a terminal editor."""
    explicit = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if explicit:
        return shlex.split(explicit)
    for cli in ("code", "code-insiders", "cursor", "codium"):
        if shutil.which(cli):
            return [cli, "--wait"]
    for term in ("nano", "vim", "vi"):
        if shutil.which(term):
            return [term]
    return ["vi"]


def edit_in_editor(w: Workspace) -> dict:
    """Open the workspace's run-params in the user's editor; return the edited key/values."""
    body = (
        f"# dftw workspace edit -- {w.name}\n"
        f"# Save & close to apply (re-render in place, no rebuild). Lines are key: value.\n"
        f"mode: {w.mode}          # off | normal | agg-full | agg-selective\n"
        f"nodes: {w.nodes if w.nodes.isdigit() else 1}\n"
        f"queue: {w.queue}        # 'default' = cluster default, or e.g. pdebug\n"
        f"time_limit: {w.timeout if w.timeout.isdigit() else ''}   # minutes (blank = unset)\n"
        f"data_dir: {w.data_dir}\n"
    )
    with tempfile.NamedTemporaryFile("w+", suffix=".dftw.yaml", delete=False) as f:
        f.write(body)
        path = f.name
    try:
        subprocess.run([*_editor_cmd(), path], check=True)
        return yaml.safe_load(Path(path).read_text()) or {}
    finally:
        os.unlink(path)


def match(cfg: Config, query: Optional[str], work: Optional[str] = None) -> list[Workspace]:
    """Fuzzy-match workspaces. `*` is an ordered wildcard: 'tuo*unet3d' -> both, in order."""
    wss = discover(cfg, work)
    if not query:
        return wss
    parts = [p for p in query.lower().split("*") if p]

    def ok(w: Workspace) -> bool:
        hay, idx = w.name.lower(), 0
        for p in parts:
            j = hay.find(p, idx)
            if j < 0:
                return False
            idx = j + len(p)
        return True

    return [w for w in wss if ok(w)]
