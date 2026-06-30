# Supported experiments

An experiment is a benchpark spec that `dftw` can scaffold, build, run, and harvest. Each is
three pieces in `repo/`:

- a ramble application (`repo/applications/<name>/`): executables, workload variables, FOMs;
- a benchpark experiment (`repo/experiments/<name>/`): variants, scaling, per-system package
  spec;
- a spack package (`repo/spack_repo/dftw/packages/<name>/`): pinned source, build,
  instrumentation patch.

The `dftracer` modifier applies to any of them, adding tracing and I/O FOMs uniformly.

## Currently supported

:::{list-table}
:header-rows: 1
:widths: 18 24 24 34

* - Workload
  - Domain
  - Systems (tested)
  - Notes
* - {doc}`unet3d`
  - MLCommons UNet3D (3D segmentation)
  - LLNL El Capitan / Tuolumne (ROCm/flux)
  - PyTorch, MPI, real read I/O; `.npz` dataset.
:::

List what your bootstrap exposes:

```bash
dftw list experiments
dftw list systems
dftw list modifiers
dftw info "unet3d +rocm package_manager=spack-pip"
```

Spack packages provided (`repo/spack_repo/dftw/packages/`): `dftracer`, `dftracer_utils`,
`pydftracer`, `unet3d`.

## Roadmap

A DLIO counterpart and the `dftw gen` / `dftw compare` fidelity loop (real workload, generate
DLIO config from the trace, run DLIO, score fidelity). See {doc}`../architecture`.
