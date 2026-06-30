# Architecture

`dftw` extends benchpark out-of-tree, no fork. benchpark is a submodule; the repo registers
its own repos via a one-line addition to benchpark's `config/repos.yaml`. The one thing
benchpark cannot express, comparing two experiments, lives in the `dftw` CLI.

## Layers

:::{list-table}
:header-rows: 1

* - Concern
  - Layer
* - Dependency builds
  - Spack packages (`repo/spack_repo/`)
* - Run orchestration
  - Ramble applications + experiments (`repo/applications/`, `repo/experiments/`)
* - Per-machine config
  - benchpark systems
* - Tracing + I/O FOMs
  - the `dftracer` modifier (`repo/modifiers/dftracer/`)
* - Scaffold, run, harvest, compare
  - the `dftw` CLI (`orchestration/`)
:::

Guiding principle: anything benchpark or ramble supports natively is delegated, not
reimplemented (setup, `ramble on`, `analyze`, `archive`, `n_repeats`, `archive_pattern`). The
CLI only fills genuine gaps: blocking on scheduler jobs (flux has no native wait in ramble),
filing lean per-run results, and the fidelity comparison loop.

## Repo layout

```text
dftracer-workloads/
├── vendor/benchpark/        # submodule (pinned), +1 line in repos.yaml
├── repo/
│   ├── modifiers/dftracer/  # tracing modes + I/O FOMs
│   ├── applications/        # ramble: unet3d (clone + patch), ...
│   ├── experiments/         # benchpark experiments
│   ├── systems/             # per-machine systems
│   ├── spack_repo/          # package.py: version(git=...) + patch(...)
│   └── lib/dftw_bench/      # shared benchpark mixins (PyTorch, DFTracer)
├── orchestration/           # the dftw CLI package
└── docs/
```

## DFTracer integration

Two layers, written once and reused. Runtime/env: a modifier sets `DFTRACER_*` and the trace
path, and emits default I/O FOMs from the traces. Source annotations live in each workload's
patch and no-op when `DFTRACER_ENABLE=0`, so a single build serves every mode.

## Dependency pinning

- `dftracer` / `dftracer-utils` / `pydftracer`: one shared, pinned version consumed by the
  modifier. Bump once, all workloads follow.
- Per-workload deps (PyTorch, DLIO): owned by each experiment, free to diverge.
- Perf-critical native deps (MPI, ROCm/CUDA PyTorch): spack source builds keyed to the system
  arch; pip wheels only for the lightweight Python stack.

## Per-machine builds

Each machine is a benchpark System declaring CPU/GPU arch, scheduler, and MPI, mixing in a
vendor base (ROCm / CUDA / OpenMP-CPU). Spack concretizes the same experiment spec into
vendor-optimized builds per target (e.g. Tuolumne/El Cap: zen4, gfx942/MI300A, flux).

## Workload source: clone + patch

The spack package pins the upstream commit and applies the instrumentation patch:

```python
version("mlperf", git="https://github.com/mlcommons/training", commit="<sha>")
patch("dftracer.patch")
```

Attribution stays correct, the patch is reviewable in isolation, and the build is exact.
Patches are generated, not hand-edited. `dftw patch` re-applies with `git apply --3way`, so
upstream bumps surface as normal conflict markers.

## Roadmap

1. Repo skeleton + benchpark bootstrap. Done.
2. DFTracer modifier with tracing modes. Done.
3. unet3d spack package (clone + patch) + ramble application. Done.
4. unet3d experiment + LLNL/flux system. Done.
5. `dftw build`/`run`, tracing as a sweep axis, harvest + trace-derived I/O FOMs. Done.
6. DLIO application/experiment + `dftw gen` / `dftw compare` fidelity loop. Planned.
7. MLflow/W&B tracking layer ingesting the fidelity FOM. Planned.

The original design note is at `docs/DESIGN.md`.
