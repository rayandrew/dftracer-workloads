# Installation

`dftw` bootstraps its own toolchain. It vendors benchpark as a submodule and, on first run,
bootstraps ramble + spack into the work directory. You need Python 3.10+ and git.

## Bootstrap

```bash
git clone https://github.com/LLNL/dftracer-workloads.git
cd dftracer-workloads
./bootstrap.sh
```

`bootstrap.sh` syncs the benchpark submodule, creates `.venv/`, installs benchpark's
requirements plus the `dftw` package, and bootstraps benchpark (ramble + spack). Pass `--dev`
for a development install; set `FORCE=1` to reinstall Python deps.

## Putting `dftw` on PATH

The repo ships a `bin/dftw` shim, so activate the venv or add `bin/` to your PATH:

```bash
export PATH="$PWD/bin:$PATH"
dftw --help
```

## Deployment (`DFTW_*` env)

`dftw` is zero-config. Locations resolve from environment variables (or flags), falling back
to repo-local defaults under `.dftw/`.

:::{list-table}
:header-rows: 1

* - Variable
  - Purpose
  - Default
* - `DFTW_WORK`
  - Build + workspace root
  - `./.dftw/work`
* - `DFTW_RESULTS`
  - Harvested results store
  - `./.dftw/results`
* - `DFTW_DATA_DIR`
  - Staged dataset location
  - required per workload
* - `DFTW_BENCHPARK_HOME`
  - benchpark bootstrap home
  - `$DFTW_WORK/.benchpark`
:::

On a cluster, point these at a fast parallel filesystem (e.g. Lustre), not the checkout.
Builds and traces are large.

## Requirements

- Python 3.10+, git.
- A supported scheduler (currently flux; the scheduler layer is pluggable via benchpark's
  allocation modifier).
- A C/C++ toolchain, MPI, and ROCm/CUDA available to spack, provided by the benchpark system
  you target.
