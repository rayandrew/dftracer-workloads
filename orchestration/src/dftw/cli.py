from __future__ import annotations

import subprocess
from enum import Enum
from typing import Optional

import typer

from . import config
from . import patch as patchmod

app = typer.Typer(help="Orchestration CLI for dftracer-workloads.", no_args_is_help=True)
patch_app = typer.Typer(
    help="Edit and regenerate workload instrumentation patches.", no_args_is_help=True
)
app.add_typer(patch_app, name="patch")


class Mode(str, Enum):
    off = "off"
    agg_full = "agg-full"
    agg_selective = "agg-selective"


@app.command()
def build(workload: str, system: Optional[str] = None) -> None:
    """Build a workload for the current system."""
    cfg = config.load()
    cfg.workload(workload)
    raise SystemExit("pending: requires the unet3d experiment + system (roadmap steps 3-4)")


@app.command()
def run(workload: str, mode: Mode = Mode.off, nodes: int = 1, system: Optional[str] = None) -> None:
    """Run a workload, with tracing selected by --mode."""
    cfg = config.load()
    cfg.workload(workload)
    raise SystemExit("pending: requires the unet3d experiment + system (roadmap steps 3-4)")


@app.command()
def gen(workload: str) -> None:
    """Generate a DLIO config from the workload trace (dftracer-utils)."""
    raise SystemExit("pending: requires dftracer-utils wiring (roadmap step 6)")


@app.command()
def compare(workload: str) -> None:
    """Run the DLIO counterpart and score fidelity vs the real run."""
    raise SystemExit("pending: requires DLIO + comparator wiring (roadmap step 6)")


@app.command()
def loop(workload: str) -> None:
    """Run real, generate DLIO, run DLIO, compare, iterate."""
    raise SystemExit("pending: requires DLIO + comparator wiring (roadmap step 6)")


@app.command()
def pin(target: str, value: str) -> None:
    """Update a workload's pinned commit, or `pin stack <version>`."""
    cfg = config.load()
    if target == "stack":
        for k in config.STACK_PACKAGES:
            cfg.stack[k] = value
        cfg.save()
        typer.echo(f"stack pinned to {value}")
        return
    wl = cfg.workload(target)
    sha = _resolve(wl["repo"], value)
    wl["ref"] = sha
    cfg.save()
    typer.echo(f"{target} pinned to {sha}")
    typer.echo(f"run `dftw patch edit {target}` to re-apply the patch on the new base")


@patch_app.command("edit")
def patch_edit(workload: str, editor: Optional[str] = None) -> None:
    """Clone at the pinned commit, apply the patch, open the editor."""
    patchmod.edit(config.load(), workload, editor)


@patch_app.command("save")
def patch_save(workload: str) -> None:
    """Regenerate the patch from the dev checkout (git diff)."""
    p = patchmod.save(config.load(), workload)
    typer.echo(f"wrote {p}")


@patch_app.command("status")
def patch_status(workload: str) -> None:
    """Show drift between the dev checkout and the saved patch."""
    patchmod.status(config.load(), workload)


@patch_app.command("reset")
def patch_reset(workload: str) -> None:
    """Discard the dev checkout."""
    patchmod.reset(config.load(), workload)
    typer.echo(f"reset dev checkout for {workload}")


def _resolve(repo: str, ref: str) -> str:
    out = subprocess.run(["git", "ls-remote", repo, ref], capture_output=True, text=True)
    line = out.stdout.strip().split("\n")[0].strip() if out.stdout.strip() else ""
    return line.split()[0] if line else ref


def main() -> None:
    app()


if __name__ == "__main__":
    main()
