# dftracer-workloads

`dftw` runs real AI/HPC workloads instrumented with
[DFTracer](https://github.com/LLNL/dftracer). It builds out-of-tree on LLNL
[benchpark](https://github.com/LLNL/benchpark) and
[ramble](https://github.com/GoogleCloudPlatform/ramble), adding a thin CLI that scaffolds,
builds, runs, traces, and harvests experiments with pinned dependencies, pinned source, and
archived per-run results.

Highlights:

- One command to run a traced workload end to end (`dftw run`).
- Tracing as a sweep axis: `off`, `normal`, `agg-full`, `agg-selective`.
- Automatic I/O figures of merit from the traces (I/O time, bytes, bandwidth; by category,
  operation, and rank), on top of each app's own FOMs.
- Lean, reproducible per-run results filed by timestamp.

## Layers

| Concern | Layer |
|---|---|
| Dependency builds (MPI, ROCm/CUDA PyTorch, DFTracer) | Spack packages |
| Run orchestration (execute scripts, FOMs, repeats) | Ramble applications + experiments |
| Per-machine config (arch, scheduler, MPI) | benchpark systems |
| Tracing + I/O FOMs | the `dftracer` modifier |
| Scaffold, run, harvest, compare | the `dftw` CLI |

`dftw` delegates to benchpark/ramble/spack wherever they already do the job (setup, `ramble
on`, `analyze`, `archive`). It only fills gaps benchpark cannot express: blocking on scheduler
jobs, per-run result filing, and cross-experiment comparison.

```{toctree}
:maxdepth: 2
:caption: Getting started

installation
quickstart
```

```{toctree}
:maxdepth: 2
:caption: Guides

cli
tracing
harvesting
```

```{toctree}
:maxdepth: 2
:caption: Experiments

experiments/index
experiments/unet3d
```

```{toctree}
:maxdepth: 2
:caption: Reference

architecture
adding-experiments
```
