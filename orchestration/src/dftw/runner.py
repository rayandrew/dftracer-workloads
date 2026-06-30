from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

import yaml

from . import benchpark
from . import patch as patchmod

if TYPE_CHECKING:
    from .config import Config


def workload_name(experiment: str) -> str:
    """The workload/benchmark name is the leading token of a benchpark spec."""
    return experiment.split()[0]


def _slug(spec: str) -> str:
    """Filesystem-safe id for a benchpark spec (e.g. 'llnl-elcapitan cluster=tuolumne')."""
    return re.sub(r"[^A-Za-z0-9._=-]+", "-", spec.strip()).strip("-")


def _deploy_path(env_var: str, default: Path, override: Optional[str] = None) -> Path:
    """Resolve a deployment location: explicit override > DFTW_* env > repo default."""
    val = override or os.environ.get(env_var)
    return Path(val) if val else default


def work_root(cfg: Config, override: Optional[str] = None) -> Path:
    return _deploy_path("DFTW_WORK", cfg.root / ".dftw" / "work", override)


def results_root(cfg: Config, override: Optional[str] = None) -> Path:
    return _deploy_path("DFTW_RESULTS", cfg.root / ".dftw" / "results", override)


def resolve_data_dir(data_dir: Optional[str] = None) -> Optional[Path]:
    val = data_dir or os.environ.get("DFTW_DATA_DIR")
    return Path(val) if val else None


def _git_sha(root: Path) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True
        )
        return out.stdout.strip() or None
    except OSError:
        return None


def _inject_ramble_vars(ramble_yaml: Path, **vars: object) -> None:
    rd = yaml.safe_load(ramble_yaml.read_text()) or {}
    section = rd.setdefault("ramble", {}).setdefault("variables", {})
    section.update({k: str(v) for k, v in vars.items() if v is not None})
    ramble_yaml.write_text(yaml.safe_dump(rd, sort_keys=False))


def _inject_experiment_vars(ramble_yaml: Path, **vars: object) -> None:
    """Set vars at *experiment* scope (the per-experiment variables block)"""
    vals = {k: str(v) for k, v in vars.items() if v is not None}
    if not vals:
        return
    rd = yaml.safe_load(ramble_yaml.read_text()) or {}

    def walk(node: object) -> None:
        if isinstance(node, dict):
            block = node.get("variables")
            if isinstance(block, dict) and "n_gpus" in block:  # an experiment's var block
                block.update(vals)
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(rd.get("ramble", {}).get("applications", {}))
    ramble_yaml.write_text(yaml.safe_dump(rd, sort_keys=False))


def _paths(
    cfg: Config, experiment: str, system: str, work: Optional[str]
) -> tuple[Path, Path, Path, Path]:
    """Workspace layout keyed by (system, workload) only"""
    wl = workload_name(experiment)
    sysslug = _slug(system)
    wr = work_root(cfg, work)
    sysdir = wr / "systems" / sysslug
    exprdir = sysdir / wl
    exproot = wr / "runs"  # shared experiments_root: one spack/ramble clone
    workspace = exproot / sysslug / wl / "workspace"
    return sysdir, exprdir, exproot, workspace


def _render_inputs_hash(cfg: Config, wl: str, ramble_yaml: Path) -> str:
    """Freshness key for the rendered workspace"""
    h = hashlib.sha256(ramble_yaml.read_bytes())
    sources = [
        cfg.root / "repo" / "applications" / wl / "application.py",
        cfg.root / "repo" / "experiments" / wl / "experiment.py",
        cfg.root / "repo" / "modifiers" / "dftracer" / "modifier.py",
    ]
    for src in sources:
        if src.exists():
            h.update(src.read_bytes())
    return h.hexdigest()


def _inject_modifier_mode(ramble_yaml: Path, modifier: str, mode: str) -> None:
    """Set a ramble modifier's mode IN PLACE."""
    rd = yaml.safe_load(ramble_yaml.read_text()) or {}
    for m in rd.get("ramble", {}).get("modifiers", []):
        if isinstance(m, dict) and m.get("name") == modifier:
            m["mode"] = mode
            break
    ramble_yaml.write_text(yaml.safe_dump(rd, sort_keys=False))


def _inject_repeats(ramble_yaml: Path, n: int) -> None:
    """Set ramble's n_repeats IN PLACE: ramble renders N independent instances (<exp>.1..N),
    each its own run dir + trace/, launched as separate non-colliding jobs, and aggregated by
    `ramble workspace analyze` (mean/stdev). The ramble-native way to run a benchmark N times."""
    rd = yaml.safe_load(ramble_yaml.read_text()) or {}
    rd.setdefault("ramble", {}).setdefault("config", {})["n_repeats"] = str(n)
    ramble_yaml.write_text(yaml.safe_dump(rd, sort_keys=False))


def prepare(
    cfg: Config,
    experiment: str,
    system: str,
    mode: str = "normal",
    nodes: int = 1,
    data_dir: Optional[str] = None,
    work: Optional[str] = None,
    overrides: Optional[dict[str, str]] = None,
    time_limit: Optional[int] = None,
    repeats: int = 0,
    dry_run: bool = False,
) -> tuple[Path, Path, dict[str, Any]]:
    """Scaffold a benchpark workspace: system init -> experiment init -> inject -> setup."""
    sysdir, exprdir, exproot, workspace = _paths(cfg, experiment, system, work)
    spec = experiment  # mode is NOT in the spec -- it's an in-place modifier (see below)

    print(f"dftw: scaffolding {workload_name(experiment)} [{mode}] on {system}", file=sys.stderr)
    if not (sysdir / "system_id.yaml").exists():
        benchpark.run(cfg, "system", "init", f"--dest={sysdir}", *system.split(), quiet=True)
    _inject_aux_packages(sysdir)  # must run before benchpark setup copies it into the workspace
    wl = workload_name(experiment)
    ramble_yaml = exprdir / "ramble.yaml"
    spec_marker = exprdir / ".dftw-spec"  # the benchpark spec last scaffolded (NOT incl mode)
    exp_py = cfg.root / "repo" / "experiments" / wl / "experiment.py"
    stale = (
        ramble_yaml.exists()
        and exp_py.exists()
        and exp_py.stat().st_mtime > ramble_yaml.stat().st_mtime
    )
    spec_changed = not spec_marker.exists() or spec_marker.read_text().strip() != spec
    needs_scaffold = not ramble_yaml.exists() or stale or spec_changed
    if needs_scaffold:
        if exprdir.exists():
            shutil.rmtree(exprdir, ignore_errors=True)
        benchpark.run(
            cfg, "experiment", "init", f"--dest={wl}", str(sysdir), *spec.split(), quiet=True
        )
        spec_marker.write_text(spec)

    inj: dict[str, object] = dict(overrides or {})  # generic ramble-var overrides (--set)
    inj["n_nodes"] = nodes
    # Abs path to the trace summarizer the modifier runs post-run (it lives outside the workspace).
    inj.setdefault(
        "dftracer_summary_script",
        str(cfg.root / "repo" / "modifiers" / "dftracer" / "dftracer_summary.py"),
    )
    ddir = resolve_data_dir(data_dir)
    if ddir is not None:
        inj.setdefault("data_dir", str(ddir))

    if mode in ("agg-full", "agg-selective"):
        inj.setdefault("dftracer_interval_ms", "1000")
    if mode == "agg-selective" and "dftracer_agg_rules" not in inj:
        raise SystemExit(
            "dftracer=agg-selective needs the rules yaml: pass --agg-rules <yaml> "
            "(or --set dftracer_agg_rules=<yaml>)"
        )
    _inject_ramble_vars(exprdir / "ramble.yaml", **inj)
    _inject_experiment_vars(exprdir / "ramble.yaml", timeout=time_limit, dftracer_mode=mode)
    _inject_modifier_mode(exprdir / "ramble.yaml", "dftracer", mode)
    _inject_repeats(exprdir / "ramble.yaml", repeats)
    (exprdir / ".dftw-meta").write_text(json.dumps({"system": system, "experiment": experiment}))

    cfg_hash = _render_inputs_hash(cfg, wl, exprdir / "ramble.yaml")
    marker = exprdir / ".dftw-setup-hash"
    workspace_cfg = workspace / "configs" / "ramble.yaml"
    fresh = workspace.exists() and marker.exists() and marker.read_text().strip() == cfg_hash
    if dry_run:
        # Preview path
        if not workspace_cfg.exists():
            benchpark.run(cfg, "setup", str(exprdir), str(exproot), quiet=True)
            _heal_spack_packages(cfg, exproot)
            _register_modifier_repo(cfg, exproot)
    elif fresh:
        print("dftw: workspace up to date (skipping benchpark setup)", file=sys.stderr)
    elif workspace_cfg.exists() and not needs_scaffold:
        # Re-render in place: run-params changed (mode/queue/nodes/repeats)
        print("dftw: re-rendering in place (reusing venv)", file=sys.stderr)
        _ramble(exproot, workspace, "workspace", "setup")
        marker.write_text(cfg_hash)
    else:
        benchpark.run(cfg, "setup", str(exprdir), str(exproot), quiet=True)
        _heal_spack_packages(cfg, exproot)
        _register_modifier_repo(cfg, exproot)
        marker.write_text(cfg_hash)

    if workspace.exists():
        _prune_stale_repeats(workspace, mode, repeats)

    try:
        source_commit = patchmod.pkg_info(cfg, workload_name(experiment))["commit"]
    except Exception:
        source_commit = None

    provenance = {
        "dftw_sha": _git_sha(cfg.root),  # the dftw release identity
        "experiment": experiment,
        "system": system,
        "mode": mode,
        "nodes": nodes,
        "data_dir": str(ddir) if ddir else None,
        "overrides": dict(overrides or {}),
        "source_commit": source_commit,
    }
    return exproot, workspace, provenance


def _heal_spack_packages(cfg: Config, exproot: Path) -> None:
    """Repair a corrupted spack-packages clone in the experiments_root."""
    pkgs = exproot / "spack-packages"
    if not pkgs.exists():
        return
    repo_yaml = pkgs / "repos" / "spack_repo" / "builtin" / "repo.yaml"
    status = subprocess.run(
        ["git", "-C", str(pkgs), "status", "--porcelain"], capture_output=True, text=True
    ).stdout
    corrupt = not repo_yaml.exists() or any(line[:1] == "D" for line in status.splitlines())
    if not corrupt:
        return
    src = benchpark.bootstrap_home(cfg.root) / "spack-packages"
    if not src.exists() or not shutil.which("rsync"):
        return  # cannot heal; let benchpark's own error surface
    print(f"dftw: repairing corrupted spack-packages clone ({pkgs})", file=sys.stderr)
    subprocess.run(["rsync", "-a", "--delete", f"{src}/", f"{pkgs}/"], check=True)


def _inject_aux_packages(sysdir: Path) -> None:
    """Add dftw's package fixes to benchpark's auxiliary_software_files/packages.yaml."""
    aux = sysdir / "auxiliary_software_files" / "packages.yaml"
    if not aux.exists():
        return
    doc = yaml.safe_load(aux.read_text()) or {}
    key = "packages:" if "packages:" in doc else "packages"  # benchpark emits the odd key
    pkgs = doc.setdefault(key, {})
    if "iconv" in pkgs and "perl" in pkgs:
        return
    pkgs.setdefault("iconv", {"require": "libiconv"})
    pkgs.setdefault(
        "perl", {"externals": [{"spec": "perl@5.26.3", "prefix": "/usr"}], "buildable": False}
    )
    aux.write_text(yaml.safe_dump(doc, sort_keys=False))


def _register_modifier_repo(cfg: Config, exproot: Path) -> None:
    """Register dftw's modifier repo with this ramble instance."""
    sentinel = exproot / ".dftw-modifier-repo"
    if sentinel.exists():
        return
    repo = cfg.root / "repo" / "modifiers"
    cmd = f". {exproot}/setup.sh && ramble repo add -t modifiers --scope=site {repo}"
    quiet = not os.environ.get("DFTW_VERBOSE")
    if subprocess.run(["bash", "-c", cmd], check=False, capture_output=quiet).returncode == 0:
        sentinel.write_text("ok\n")


def _ramble(exproot: Path, workspace: Path, *args: str) -> None:
    cmd = f". {exproot}/setup.sh && ramble --workspace-dir {workspace} " + " ".join(args)
    subprocess.run(["bash", "-c", cmd], check=True)


def _scheduler_job_ids(stdout: str) -> list[str]:
    return re.findall(r"\bf[1-9A-HJ-NP-Za-km-z]{10,12}\b", stdout)  # flux F58 ids


def _scheduler_wait(exproot: Path, job_ids: list[str]) -> None:
    # `flux job status` blocks until the jobs reach a terminal state (it is not a status poll).
    if job_ids:
        print(f"dftw: waiting for {len(job_ids)} job(s) to finish...", file=sys.stderr)
        subprocess.run(
            ["bash", "-c", f". {exproot}/setup.sh && flux job status {' '.join(job_ids)}"],
            check=False,  # a failed experiment shouldn't abort the harvest of its traces
        )


def _ramble_on(exproot: Path, workspace: Path, wait: bool = True) -> list[str]:
    """Delegate submission to ramble (`on` -> `{batch_submit}`, scheduler-agnostic). It submits
    async and returns; when wait=True, block on the jobs so a following harvest sees them done.
    Returns the job ids (for the non-blocking path to report)."""
    cmd = f". {exproot}/setup.sh && ramble --workspace-dir {workspace} on"
    proc = subprocess.run(["bash", "-c", cmd], check=True, capture_output=True, text=True)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    job_ids = _scheduler_job_ids(proc.stdout + proc.stderr)
    if wait:
        _scheduler_wait(exproot, job_ids)
    return job_ids


def _prune_stale_repeats(workspace: Path, mode: str, repeats: int) -> None:
    """ramble renders <exp>_<mode>.1..N for n_repeats=N but never removes higher-numbered dirs
    when N drops (or back to a single run). Drop the now-stale repeat instances so they don't
    pollute harvest, which scopes by the <exp>_<mode>* glob."""
    keep = set(range(1, repeats + 1))  # .1..N valid; the base (no suffix) is always kept
    for inst in workspace.glob(f"experiments/*/*/*_{mode}.*"):
        m = re.search(rf"_{re.escape(mode)}\.(\d+)$", inst.name)
        if m and int(m.group(1)) not in keep:
            shutil.rmtree(inst, ignore_errors=True)


def _ramble_archive(exproot: Path, workspace: Path) -> Path:
    """Run `ramble workspace archive` and return the freshly produced archive dir."""
    adir = workspace / "archive"
    before = set(adir.glob("workspace-archive-*")) if adir.exists() else set()
    _ramble(exproot, workspace, "workspace", "archive")
    new = sorted(set(adir.glob("workspace-archive-*")) - before, key=lambda p: p.stat().st_mtime)
    if not new:
        raise RuntimeError("ramble workspace archive produced no archive directory")
    return new[-1]


def harvest(
    cfg: Config,
    experiment: str,
    system: str,
    mode: str,
    exproot: Path,
    workspace: Path,
    provenance: Optional[dict[str, Any]] = None,
    results: Optional[str] = None,
) -> Path:
    """File one run into dftw's per-run results store, delegating WHAT-to-collect to ramble.

    Every output is declared at its source via ramble's `archive_pattern` directive (app outputs in
    the application, DFTracer traces in the modifier), so harvest just:
      - runs `analyze` (delegated FOMs), then
      - runs `workspace archive` -- which materializes exactly the declared files + configs/results/
        software into a self-contained snapshot -- and files that snapshot into a per-run slot,
        dropping only ramble's internal run `logs/` (pure bloat, accumulates across runs), and
      - moves the live traces out so the work dir stays lean.
    No dftw-side per-app include/skip lists: adding a new workload just means declaring its outputs."""
    from datetime import datetime

    wl = workload_name(experiment)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = results_root(cfg, results) / wl / mode / run_id

    try:
        _ramble(exproot, workspace, "workspace", "analyze", "--formats", "json")
    except subprocess.CalledProcessError:
        pass  # still archive the traces even if FOM parsing fails

    archive_dir = _ramble_archive(exproot, workspace)
    dest.mkdir(parents=True, exist_ok=True)

    skip = {"logs", "results"}
    for item in sorted(archive_dir.iterdir()):
        if item.name in skip:
            continue
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)
    shutil.rmtree(archive_dir, ignore_errors=True)  # temp; the deliverable now lives in results/
    latest = workspace / "archive" / "archive.latest"
    if latest.is_symlink():
        latest.unlink()  # would otherwise dangle at the just-removed snapshot

    fom = workspace / "results" / "results.latest.json"
    if fom.exists():
        shutil.copy2(fom, dest / "results.json")

    for src in workspace.glob(f"experiments/*/*/*_{mode}*/trace/*.pfw*"):
        src.unlink()

    meta: dict[str, Any] = {"workload": wl, "system": system, "mode": mode, "run_id": run_id}
    meta.update(provenance or {})
    (dest / "metadata.yaml").write_text(yaml.safe_dump(meta, sort_keys=False))
    return dest


def build(
    cfg: Config,
    experiment: str,
    system: str,
    mode: str = "normal",
    nodes: int = 1,
    data_dir: Optional[str] = None,
    work: Optional[str] = None,
    overrides: Optional[dict[str, str]] = None,
    time_limit: Optional[int] = None,
    repeats: int = 0,
    dry_run: bool = False,
) -> Path:
    exproot, workspace, _ = prepare(
        cfg,
        experiment,
        system,
        mode,
        nodes,
        data_dir,
        work,
        overrides,
        time_limit,
        repeats,
        dry_run,
    )
    # dry-run: concretize + render the build plan without installing; else the real build.
    _ramble(exproot, workspace, "workspace", "setup", *(["--dry-run"] if dry_run else []))
    return workspace


def run(
    cfg: Config,
    experiment: str,
    system: str,
    mode: str = "normal",
    nodes: int = 1,
    data_dir: Optional[str] = None,
    work: Optional[str] = None,
    results: Optional[str] = None,
    overrides: Optional[dict[str, str]] = None,
    time_limit: Optional[int] = None,
    repeats: int = 0,
    wait: bool = True,
    dry_run: bool = False,
) -> Union[Path, list[str], list[Path]]:
    """Run the workload. wait=True (default): block on the flux jobs, then harvest -> results dir.
    wait=False: submit and return the flux job ids; harvest later with `dftw harvest`.
    dry_run=True: concretize + render + print what would run (returns the execute scripts), but do
    not submit or harvest."""
    exproot, workspace, prov = prepare(
        cfg,
        experiment,
        system,
        mode,
        nodes,
        data_dir,
        work,
        overrides,
        time_limit,
        repeats,
        dry_run,
    )
    if dry_run:
        # concretize + render (no install), then show what `ramble on` would submit -- no submit.
        _ramble(exproot, workspace, "workspace", "setup", "--dry-run")
        scripts = sorted(workspace.glob(f"experiments/*/*/*_{mode}*/execute_experiment"))
        print(
            "dftw: dry-run -- `ramble on` would submit these execute scripts via the scheduler "
            "(not executed):",
            file=sys.stderr,
        )
        for s in scripts:
            print(f"  {s}", file=sys.stderr)
        return scripts
    if any(workspace.glob(f"experiments/*/*/*_{mode}*/trace/*.pfw*")):
        print("dftw: archiving un-harvested traces from a previous run first", file=sys.stderr)
        harvest(cfg, experiment, system, mode, exproot, workspace, prov, results)
    job_ids = _ramble_on(exproot, workspace, wait=wait)
    if not wait:
        return job_ids  # detached: caller harvests once the jobs finish
    return harvest(cfg, experiment, system, mode, exproot, workspace, prov, results)


def harvest_workspace(
    cfg: Config,
    experiment: str,
    system: str,
    mode: str = "normal",
    work: Optional[str] = None,
    results: Optional[str] = None,
) -> Path:
    """Harvest an already-finished run (the `dftw harvest` / detached path)."""
    _, _, exproot, workspace = _paths(cfg, experiment, system, work)
    prov = {
        "dftw_sha": _git_sha(cfg.root),
        "experiment": experiment,
        "system": system,
        "mode": mode,
    }
    return harvest(cfg, experiment, system, mode, exproot, workspace, prov, results)


def run_in_workspace(workspace: Path, *args: str, results: Optional[str] = None) -> None:
    """Drive ramble in an already-scaffolded/activated workspace (dftw activate flow)."""
    exproot = _find_exproot(workspace)
    _ramble(exproot, workspace, *args)


def _find_exproot(workspace: Path) -> Path:
    """Walk up from a workspace to the experiments_root that holds setup.sh."""
    for d in [workspace, *workspace.parents]:
        if (d / "setup.sh").exists():
            return d
    raise SystemExit(f"no setup.sh found above {workspace}; is it a benchpark workspace?")
