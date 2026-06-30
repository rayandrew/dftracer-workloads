from __future__ import annotations

import os
import subprocess
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Optional

import typer

from . import bench, config, runner
from . import benchpark as bpmod
from . import data as datamod
from . import patch as patchmod
from . import prepare as preparemod
from . import workspace as wsmod

app = typer.Typer(
    help="Scaffold, run and trace benchpark experiments with DFTracer.", no_args_is_help=True
)
patch_app = typer.Typer(
    help="Edit and regenerate source instrumentation patches.", no_args_is_help=True
)
app.add_typer(patch_app, name="patch")
data_app = typer.Typer(help="Prepare and stage workload datasets.", no_args_is_help=True)
app.add_typer(data_app, name="data")
workspace_app = typer.Typer(
    help="List, inspect and edit scaffolded workspaces.", no_args_is_help=True
)
app.add_typer(workspace_app, name="workspace")


class Mode(str, Enum):
    off = "off"
    normal = "normal"
    agg_full = "agg-full"
    agg_selective = "agg-selective"


EXPERIMENT = typer.Argument(
    None, help='benchpark experiment spec, e.g. "unet3d +rocm package_manager=spack-pip"'
)
SYSTEM = typer.Option(
    None, "--system", help='benchpark system spec, e.g. "llnl-elcapitan cluster=tuolumne"'
)
MODE = typer.Option(None, "--mode", help="DFTracer tracing mode")
INTERVAL = typer.Option(None, "--interval-ms", help="aggregation interval, ms (agg-* modes)")
AGG_RULES = typer.Option(
    None, "--agg-rules", help="selective aggregation rules yaml (agg-selective)"
)
NODES = typer.Option(None, "--nodes", help="node count (-> n_nodes ramble var)")
QUEUE = typer.Option(None, "--queue", help="scheduler queue/partition (e.g. pdebug)")
TIME_LIMIT = typer.Option(None, "--time-limit", help="job walltime in minutes (-> timeout)")
REPEATS = typer.Option(
    0,
    "--repeats",
    help="run the experiment N times (ramble n_repeats): each repeat gets its "
    "own dir + trace/ and a separate job, FOMs aggregated (mean/stdev). 0 = single run.",
)
NO_WAIT = typer.Option(
    False,
    "--no-wait",
    help="submit the flux job(s) and return immediately (don't block or "
    "harvest); collect results later with `dftw harvest`. Default blocks until jobs finish.",
)
DRY_RUN = typer.Option(
    False,
    "--dry-run",
    help="concretize + render (ramble setup --dry-run) and show the build/run plan without "
    "installing, submitting, or harvesting. Needs the target toolchain to concretize.",
)
DATA = typer.Option(
    None, "--data-dir", help="dataset dir (-> data_dir ramble var; or DFTW_DATA_DIR)"
)
WORK = typer.Option(None, "--work", help="experiments_root override (or DFTW_WORK)")
RESULTS = typer.Option(None, "--results", help="results store override (or DFTW_RESULTS)")
WORKSPACE = typer.Option(
    None, "--workspace", help="operate on an existing workspace (or DFTW_WORKSPACE)"
)
NOINPUT = typer.Option(
    False, "--no-input", help="never prompt; fail if a required value is missing"
)
VERBOSE = typer.Option(False, "--verbose", "-v", help="show benchpark scaffolding output")


def _set_verbose(verbose: bool) -> None:
    if verbose:
        os.environ["DFTW_VERBOSE"] = "1"


def _wizard(
    cfg: config.Config,
    experiment: Optional[str],
    system: Optional[str],
    mode: Optional[str],
    nodes: Optional[int],
    data_dir: Optional[str],
    interval_ms: Optional[int],
    agg_rules: Optional[str],
    no_input: bool,
) -> tuple[str, str, str, int, Optional[str], dict[str, str]]:
    """Fill missing run inputs. Every value has a flag; only missing ones are prompted."""
    system = system or os.environ.get("DFTW_SYSTEM")

    if not system:
        if no_input:
            raise typer.BadParameter("missing --system (and no DFTW_SYSTEM)")
        detected = bench.detect_system(cfg)
        choices = ([f"{detected}    (auto-detected)"] if detected else []) + bench.systems(cfg)
        choices.append("custom spec…")
        pick = _ask(_select("System", choices, default=choices[0]))
        if detected and pick.startswith(detected):
            system = detected
        elif pick == "custom spec…":
            system = _ask(_text("Benchpark system spec"))
        else:
            system = _ask(_text("Benchpark system spec", default=pick))

    if not experiment:
        if no_input:
            raise typer.BadParameter("missing experiment spec")
        exps = bench.experiments(cfg)
        wl = _ask(_select("Experiment", exps) if exps else _text("Experiment name"))
        rt = bench.gpu_runtime(cfg, system) if system else None
        suffix = f" +{rt}" if rt else ""
        experiment = _ask(
            _text("Experiment spec", default=f"{wl}{suffix} package_manager=spack-pip")
        )

    if not mode:
        mode = (
            "normal"
            if no_input
            else _ask(_select("DFTracer mode", [m.value for m in Mode], default=Mode.normal.value))
        )

    if nodes is None:
        nodes = 1 if no_input else int(_ask(_text("Nodes", default="1")) or "1")

    if data_dir is None and not no_input:
        seed = os.environ.get("DFTW_DATA_DIR", "")
        data_dir = _ask(_text("Data dir (blank to skip)", default=seed)) or None

    # DFTracer modifier knobs that only the aggregation modes need.
    mode = mode or "normal"
    overrides: dict[str, str] = {}
    if mode in ("agg-full", "agg-selective"):
        if interval_ms is None and not no_input:
            interval_ms = int(_ask(_text("Aggregation interval (ms)", default="1000")) or "1000")
        overrides["dftracer_interval_ms"] = str(1000 if interval_ms is None else interval_ms)
    if mode == "agg-selective":
        if not agg_rules and not no_input:
            agg_rules = _ask(_text("Selective aggregation rules (yaml path)")) or None
        if agg_rules:
            overrides["dftracer_agg_rules"] = agg_rules

    return experiment, system, mode, nodes, data_dir, overrides


def _q() -> Any:  # lazy import so fully-flagged / CI use needs no TUI dep
    try:
        import questionary

        return questionary
    except ImportError:
        raise typer.BadParameter(
            "interactive prompts need 'questionary' (pip install questionary), or pass all flags / --no-input"
        )


def _ask(question: Any) -> Any:
    """Run a prompt; abort the whole command on Ctrl-C/Esc (questionary returns None)."""
    ans = question.ask()
    if ans is None:
        raise typer.Abort()
    return ans


def _select(message: str, choices: Iterable[str], default: Optional[str] = None) -> Any:
    # type-to-filter over the list; don't bind j/k so they can be typed into the filter
    return _q().select(
        message, choices=list(choices), default=default, use_search_filter=True, use_jk_keys=False
    )


def _text(message: str, default: str = "") -> Any:
    return _q().text(message, default=default)


@app.command()
def new(
    experiment: Optional[str] = EXPERIMENT,
    system: Optional[str] = SYSTEM,
    mode: Optional[Mode] = MODE,
    interval_ms: Optional[int] = INTERVAL,
    agg_rules: Optional[str] = AGG_RULES,
    nodes: Optional[int] = NODES,
    data_dir: Optional[str] = DATA,
    work: Optional[str] = WORK,
    no_input: bool = NOINPUT,
    verbose: bool = VERBOSE,
) -> None:
    """Scaffold a benchpark workspace (system init + experiment init + setup)."""
    cfg = config.load()
    _set_verbose(verbose)
    e, s, m, n, d, ov = _wizard(
        cfg,
        experiment,
        system,
        mode.value if mode else None,
        nodes,
        data_dir,
        interval_ms,
        agg_rules,
        no_input,
    )
    _, ws, _ = runner.prepare(cfg, e, s, m, n, d, work, ov)
    typer.echo(f"workspace: {ws}")
    typer.echo(f'activate:  eval "$(dftw activate {ws})"')


@app.command()
def activate(workspace: str = typer.Argument(..., help="a scaffolded workspace dir")) -> None:
    """Print shell to enter a workspace: eval \"$(dftw activate <ws>)\"."""
    ws = Path(workspace).resolve()
    exproot = runner._find_exproot(ws)
    typer.echo(f"export DFTW_WORKSPACE={ws}")
    typer.echo(f". {exproot}/setup.sh")


def _workspace(workspace: Optional[str]) -> Optional[Path]:
    ws = workspace or os.environ.get("DFTW_WORKSPACE")
    return Path(ws) if ws else None


@app.command()
def build(
    experiment: Optional[str] = EXPERIMENT,
    system: Optional[str] = SYSTEM,
    mode: Optional[Mode] = MODE,
    interval_ms: Optional[int] = INTERVAL,
    agg_rules: Optional[str] = AGG_RULES,
    nodes: Optional[int] = NODES,
    queue: Optional[str] = QUEUE,
    time_limit: Optional[int] = TIME_LIMIT,
    data_dir: Optional[str] = DATA,
    work: Optional[str] = WORK,
    workspace: Optional[str] = WORKSPACE,
    no_input: bool = NOINPUT,
    dry_run: bool = DRY_RUN,
    verbose: bool = VERBOSE,
) -> None:
    """Build the workload (spack + pip). Operates on --workspace/DFTW_WORKSPACE if active."""
    cfg = config.load()
    _set_verbose(verbose)
    ws = _workspace(workspace)
    if ws and not experiment:
        runner.run_in_workspace(ws, "workspace", "setup", *(["--dry-run"] if dry_run else []))
        typer.echo(f"{'dry-run rendered' if dry_run else 'built'}: {ws}")
        return
    e, s, m, n, d, ov = _wizard(
        cfg,
        experiment,
        system,
        mode.value if mode else None,
        nodes,
        data_dir,
        interval_ms,
        agg_rules,
        no_input,
    )
    if queue:
        ov["queue"] = queue
    out = runner.build(cfg, e, s, m, n, d, work, ov, time_limit, dry_run=dry_run)
    typer.echo(f"{'dry-run rendered' if dry_run else 'built'}: {out}")


def _pick_run_target(
    cfg: config.Config, work: Optional[str], no_input: bool
) -> Optional[wsmod.Workspace]:
    """An already-built workspace to run, or None to fall through to the scaffold wizard."""
    wss = wsmod.discover(cfg, work)
    if not wss:
        return None  # nothing built yet -> scaffold
    if no_input:
        if len(wss) == 1:
            return wss[0]
        raise typer.BadParameter(
            f"{len(wss)} workspaces; pass an experiment spec or --workspace to disambiguate"
        )
    new = "+ scaffold a new experiment…"
    pick = _ask(_select("Run which workspace?", [w.name for w in wss] + [new]))
    return None if pick == new else next(w for w in wss if w.name == pick)


@app.command()
def run(
    experiment: Optional[str] = EXPERIMENT,
    system: Optional[str] = SYSTEM,
    mode: Optional[Mode] = MODE,
    interval_ms: Optional[int] = INTERVAL,
    agg_rules: Optional[str] = AGG_RULES,
    nodes: Optional[int] = NODES,
    queue: Optional[str] = QUEUE,
    time_limit: Optional[int] = TIME_LIMIT,
    repeats: int = REPEATS,
    no_wait: bool = NO_WAIT,
    dry_run: bool = DRY_RUN,
    data_dir: Optional[str] = DATA,
    work: Optional[str] = WORK,
    results: Optional[str] = RESULTS,
    workspace: Optional[str] = WORKSPACE,
    no_input: bool = NOINPUT,
    verbose: bool = VERBOSE,
) -> None:
    """Run the workload (ramble on), block until the flux job(s) finish, then harvest FOMs +
    traces + provenance. Use --no-wait to submit and harvest later with `dftw harvest`.

    With no experiment/--workspace, pick an existing workspace to run (the common case);
    choose "new" to scaffold one.
    """
    cfg = config.load()
    _set_verbose(verbose)
    wait = not no_wait

    def _finish(res: object, e: str, s: str, m: str) -> None:
        if dry_run:
            return  # the plan was already printed by runner.run
        if wait:
            typer.echo(f"results: {res}")
        else:
            ids = " ".join(res) if isinstance(res, list) else str(res)
            typer.echo(
                f"submitted: {ids}\nharvest when done: "
                f"dftw harvest --experiment '{e}' --system '{s}' --mode {m}"
            )

    ws = _workspace(workspace)
    if ws and not experiment:
        runner.run_in_workspace(ws, "on")
        typer.echo(
            f"ran: {ws} (harvest from an experiment scaffolded by dftw to record provenance)"
        )
        return
    # Default: run an already-built workspace. Only fall to the scaffold wizard if there are
    # none, or the user explicitly gave/asked for a new experiment.
    if not experiment:
        w = _pick_run_target(cfg, work, no_input)
        if w is not None:
            n = int(w.nodes) if w.nodes.isdigit() else 1
            ov = {} if w.queue in ("default", "") else {"queue": w.queue}
            tl = int(w.timeout) if w.timeout.isdigit() else None
            dd = None if w.data_dir in ("-", "") else w.data_dir
            res = runner.run(
                cfg,
                w.experiment,
                w.system,
                w.mode,
                n,
                dd,
                work,
                results,
                ov,
                tl,
                repeats,
                wait,
                dry_run,
            )
            _finish(res, w.experiment, w.system, w.mode)
            return
    e, s, m, n, d, ov = _wizard(
        cfg,
        experiment,
        system,
        mode.value if mode else None,
        nodes,
        data_dir,
        interval_ms,
        agg_rules,
        no_input,
    )
    if queue:
        ov["queue"] = queue
    res = runner.run(cfg, e, s, m, n, d, work, results, ov, time_limit, repeats, wait, dry_run)
    _finish(res, e, s, m)


@app.command()
def harvest(
    experiment: Optional[str] = EXPERIMENT,
    system: Optional[str] = SYSTEM,
    mode: Optional[Mode] = MODE,
    work: Optional[str] = WORK,
    results: Optional[str] = RESULTS,
    no_input: bool = NOINPUT,
    verbose: bool = VERBOSE,
) -> None:
    """Collect FOMs + traces + provenance from a finished run into the results store. Use after
    `dftw run --no-wait` once the flux job(s) complete (or to re-harvest an existing workspace)."""
    cfg = config.load()
    _set_verbose(verbose)
    if not experiment:
        w = _pick_run_target(cfg, work, no_input)
        if w is None:
            raise typer.Exit(1)
        e, s, m = w.experiment, w.system, w.mode
    else:
        e, s, m = experiment, system or "", (mode.value if mode else "normal")
    typer.echo(f"results: {runner.harvest_workspace(cfg, e, s, m, work, results)}")


@app.command("list")
def list_(
    what: str = typer.Argument("experiments", help="experiments | systems | modifiers"),
) -> None:
    """List available benchpark experiments, systems, or modifiers."""
    bpmod.run(config.load(), "list", what, check=False)


@app.command()
def info(experiment: str = EXPERIMENT, system: Optional[str] = SYSTEM) -> None:
    """Show a benchpark experiment's variants (+ DFTracer tracing modes)."""
    cfg = config.load()
    typer.echo(f"DFTracer modes: {', '.join(m.value for m in Mode)}\n")
    bpmod.run(cfg, "info", "experiment", *experiment.split(), check=False)


@app.command()
def gen(experiment: str = EXPERIMENT) -> None:
    """Generate a DLIO config from the workload trace (dftracer-utils)."""
    raise SystemExit("pending: requires dftracer-utils wiring (roadmap step 6)")


@app.command()
def compare(experiment: str = EXPERIMENT) -> None:
    """Run the DLIO counterpart and score fidelity vs the real run."""
    raise SystemExit("pending: requires DLIO + comparator wiring (roadmap step 6)")


_PASS = {"allow_extra_args": True, "ignore_unknown_options": True}


@app.command(context_settings=_PASS)
def benchpark(ctx: typer.Context) -> None:
    """Passthrough to the vendored benchpark CLI (with dftw's config)."""
    raise typer.Exit(bpmod.run(config.load(), *ctx.args, check=False).returncode)


@app.command(context_settings=_PASS)
def ramble(ctx: typer.Context) -> None:
    """Passthrough to the bootstrapped ramble."""
    root = config.load().root
    raise typer.Exit(subprocess.run([str(bpmod.tool_bin(root, "ramble")), *ctx.args]).returncode)


@app.command(context_settings=_PASS)
def spack(ctx: typer.Context) -> None:
    """Passthrough to the bootstrapped spack."""
    root = config.load().root
    raise typer.Exit(subprocess.run([str(bpmod.tool_bin(root, "spack")), *ctx.args]).returncode)


@app.command()
def pin(workload: str, ref: str) -> None:
    """Update a workload's pinned source commit in its package.py."""
    cfg = config.load()
    info = patchmod.pkg_info(cfg, workload)
    sha = _resolve(info["repo"], ref)
    pkg = patchmod.package_dir(cfg, workload) / "package.py"
    pkg.write_text(pkg.read_text().replace(info["commit"], sha))
    typer.echo(f"{workload} pinned to {sha} (package.py)")
    typer.echo(f"run `dftw patch edit {workload}` to re-apply the patch on the new base")


@patch_app.command("edit")
def patch_edit(workload: str, editor: Optional[str] = None) -> None:
    """Clone the source at its pinned commit, apply the patch, open the editor."""
    patchmod.edit(config.load(), workload, editor)


@patch_app.command("save")
def patch_save(workload: str) -> None:
    """Regenerate the workload's patch from the dev checkout (git diff, subdir-scoped)."""
    typer.echo(f"wrote {patchmod.save(config.load(), workload)}")


@patch_app.command("status")
def patch_status(workload: str) -> None:
    """Show drift between the dev checkout and the saved patch."""
    patchmod.status(config.load(), workload)


@patch_app.command("reset")
def patch_reset(workload: str) -> None:
    """Discard the source dev checkout."""
    patchmod.reset(config.load(), workload)
    typer.echo(f"reset dev checkout for {workload}")


@data_app.command("stage")
def data_stage(
    workload: str,
    to: str = typer.Option(..., "--to", help="run-filesystem target"),
    from_: Optional[str] = typer.Option(None, "--from", help="override source"),
    link: bool = typer.Option(False, help="symlink instead of copy"),
) -> None:
    """Place the dataset on the run filesystem (idempotent)."""
    target, action = datamod.stage(config.load(), workload, from_, to, link)
    typer.echo(f"{action}: {target}")


@data_app.command("status")
def data_status(workload: str, to: str = typer.Option(..., "--to")) -> None:
    """Report staging state of a target."""
    typer.echo(datamod.status(config.load(), workload, to))


@data_app.command("prepare")
def data_prepare(
    workload: str,
    dest: Optional[str] = typer.Option(None, "--dest", help="final dataset dir (or DFTW_DATA_DIR)"),
    work: Optional[str] = typer.Option(
        None, "--work", help="scratch dir (default: <dest>.prepare)"
    ),
    keep_work: bool = typer.Option(False, "--keep-work", help="keep intermediates after success"),
    param: Optional[list[str]] = typer.Option(
        None, "--param", "-p", help="override a manifest param, key=value"
    ),
) -> None:
    """Produce the dataset via the resumable prepare pipeline.

    Intermediates (raw KITS19, preprocessed) go to a sibling <dest>.prepare and are
    removed on success; pass --keep-work to retain, or --work to relocate them.
    """
    params = dict(p.split("=", 1) for p in param) if param else None
    out = preparemod.prepare(config.load(), workload, dest, work, params, keep_work)
    typer.echo(out)  # result (the dataset path) on stdout; progress went to stderr


def _resolve(repo: str, ref: str) -> str:
    out = subprocess.run(["git", "ls-remote", repo, ref], capture_output=True, text=True)
    line = out.stdout.strip().split("\n")[0].strip() if out.stdout.strip() else ""
    return line.split()[0] if line else ref


def _resolve_ws(
    cfg: config.Config, name: Optional[str], work: Optional[str], no_input: bool
) -> wsmod.Workspace:
    """Resolve a workspace. A *given* query that uniquely matches edits straight away; a
    blank query always shows the picker so you can see the list and choose. Many matches ->
    pick (or, under --no-input, error unless it's unambiguous)."""
    matches = wsmod.match(cfg, name, work)
    if not matches:
        raise typer.BadParameter(
            f"no workspace matches {name!r}" if name else "no workspaces yet (run `dftw build`)"
        )
    if name and len(matches) == 1:
        return matches[0]
    if no_input:
        if len(matches) == 1:
            return matches[0]
        raise typer.BadParameter(
            (f"{name!r} matches " if name else "")
            + f"{len(matches)} workspaces: "
            + ", ".join(w.name for w in matches)
        )
    pick = _ask(_select("Workspace", [w.name for w in matches]))
    return next(w for w in matches if w.name == pick)


@workspace_app.command("list")
def workspace_list(work: Optional[str] = WORK) -> None:
    """List scaffolded workspaces and their current run-params."""
    wss = wsmod.discover(config.load(), work)
    if not wss:
        typer.echo("no workspaces yet -- run `dftw build` first")
        return
    for w in wss:
        tag = "built" if w.built else "empty"
        typer.echo(
            f"{w.name:46} mode={w.mode:13} nodes={w.nodes:>3} "
            f"queue={w.queue:8} t={w.timeout:>4}m  [{tag}]"
        )


@workspace_app.command("info")
def workspace_info(
    name: Optional[str] = typer.Argument(None, help="workspace name / fuzzy (blank = pick)"),
    no_input: bool = NOINPUT,
    work: Optional[str] = WORK,
) -> None:
    """Show full detail for one workspace."""
    w = _resolve_ws(config.load(), name, work, no_input)
    modes = ", ".join(f"{m} (active)" if m == w.mode else m for m in (w.modes or [w.mode]))
    for k, v in (
        ("workspace", w.name),
        ("system", w.system),
        ("experiment", w.experiment),
        ("mode", modes),
        ("nodes", w.nodes),
        ("queue", w.queue),
        ("time-limit", f"{w.timeout} min"),
        ("data dir", w.data_dir),
        ("built", "yes" if w.built else "no"),
        ("path", str(w.path)),
    ):
        typer.echo(f"{k:11}: {v}")


@workspace_app.command("edit")
def workspace_edit(
    name: Optional[str] = typer.Argument(None, help="workspace name / fuzzy (blank = pick)"),
    mode: Optional[Mode] = MODE,
    nodes: Optional[int] = NODES,
    queue: Optional[str] = QUEUE,
    time_limit: Optional[int] = TIME_LIMIT,
    set_: Optional[list[str]] = typer.Option(None, "--set", help="extra ramble var key=value"),
    editor: bool = typer.Option(False, "--editor", help="edit run-params in $EDITOR"),
    no_input: bool = NOINPUT,
    work: Optional[str] = WORK,
    verbose: bool = VERBOSE,
) -> None:
    """Change a workspace's run-params (mode/queue/time/nodes) in place -- re-render, no rebuild."""
    cfg = config.load()
    _set_verbose(verbose)
    w = _resolve_ws(cfg, name, work, no_input)
    data_dir = None if w.data_dir in ("-", "") else w.data_dir

    def _num(v: Any) -> Optional[int]:
        v = str(v or "").strip()
        return int(v) if v.lstrip("-").isdigit() else None

    if editor:
        e = wsmod.edit_in_editor(w)
        mode = Mode(str(e.get("mode") or w.mode))
        nodes = _num(e.get("nodes")) if e.get("nodes") is not None else nodes
        qv = str(e.get("queue", "")).strip()
        queue = None if qv in ("", "default") else qv
        time_limit = _num(e.get("time_limit"))
        dv = str(e.get("data_dir", "")).strip()
        data_dir = None if dv in ("", "-") else dv
    elif (
        not (mode or nodes is not None or queue or time_limit is not None or set_) and not no_input
    ):
        mode = Mode(_ask(_select("Mode", [e.value for e in Mode], default=w.mode)))
        nodes = int(_ask(_text("Nodes", default=w.nodes if w.nodes.isdigit() else "1")) or "1")
        q = _ask(
            _text(
                "Queue (blank = cluster default)", default="" if w.queue == "default" else w.queue
            )
        )
        queue = q or None
        tl = _ask(_text("Time limit (minutes)", default=w.timeout if w.timeout.isdigit() else ""))
        time_limit = int(tl) if tl.strip().isdigit() else None

    eff_mode = mode.value if mode else w.mode
    eff_nodes = nodes if nodes is not None else (int(w.nodes) if w.nodes.isdigit() else 1)
    eff_time = (
        time_limit if time_limit is not None else (int(w.timeout) if w.timeout.isdigit() else None)
    )
    overrides = dict(p.split("=", 1) for p in (set_ or []))
    if queue:
        overrides["queue"] = queue

    typer.echo(
        f"editing {w.name}: mode={eff_mode} nodes={eff_nodes} "
        f"queue={overrides.get('queue', w.queue)} time-limit={eff_time}"
    )
    runner.build(
        cfg, w.experiment, w.system, eff_mode, eff_nodes, data_dir, work, overrides, eff_time
    )
    typer.echo(f"re-rendered {w.path} (spack stack reused; torch from cache)")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
