# dftracer-workloads

[![ci](https://github.com/LLNL/dftracer-workloads/actions/workflows/ci.yml/badge.svg)](https://github.com/LLNL/dftracer-workloads/actions/workflows/ci.yml)
[![docs](https://readthedocs.org/projects/dftracer-workloads/badge/?version=latest)](https://dftracer-workloads.readthedocs.io/en/latest/)

`dftw` runs real AI/HPC workloads instrumented with
[DFTracer](https://github.com/LLNL/dftracer). It builds out-of-tree on LLNL
[benchpark](https://github.com/LLNL/benchpark) and
[ramble](https://github.com/GoogleCloudPlatform/ramble), adding a thin CLI that scaffolds,
builds, runs, traces, and harvests experiments with pinned dependencies, pinned source, and
archived per-run results.

- One command to run a traced workload end to end (`dftw run`).
- Tracing as a sweep axis: `off`, `normal`, `agg-full`, `agg-selective`.
- Automatic I/O figures of merit from the traces (I/O time, bytes, bandwidth; by category,
  operation, and rank), on top of each app's own FOMs.
- Lean, reproducible per-run results filed by timestamp.

## Quickstart

```bash
git clone https://github.com/LLNL/dftracer-workloads.git
cd dftracer-workloads
./bootstrap.sh
export PATH="$PWD/bin:$PATH"

export DFTW_DATA_DIR=/p/lustre5/$USER/dataset/dftw/unet3d
dftw data prepare unet3d --dest "$DFTW_DATA_DIR"
dftw run "unet3d +rocm package_manager=spack-pip" \
  --system "llnl-elcapitan cluster=tuolumne" --nodes 1 --mode normal
```

Full documentation: <https://dftracer-workloads.readthedocs.io>.

## Documentation

Docs are Sphinx + MyST (Markdown) under `docs/`, published on Read the Docs.

```bash
pip install -e "orchestration[docs]"
python -m sphinx -b html -W docs/source docs/_build/html
open docs/_build/html/index.html
```

## Contributing

- Add a workload: see
  [Adding an experiment](https://dftracer-workloads.readthedocs.io/en/latest/adding-experiments.html).
- Style: `ruff` (config in `ruff.toml`). Docs pages avoid em-dashes and over-explaining.
- Commit small, reviewable changes; instrumentation patches are generated, never hand-edited
  (`dftw patch`).

### Running CI locally

CI (`.github/workflows/ci.yml`) runs four jobs. The first three need no HPC and mirror what
you can run locally:

```bash
pip install -e "orchestration[dev,docs]"

# lint
ruff check orchestration/src repo/modifiers repo/applications repo/experiments tests

# unit tests (trace summarizer + FOM-regex coupling)
pytest tests -q

# docs (warnings are errors)
python -m sphinx -b html -W docs/source docs/_build/html
```

The fourth job, `render`, bootstraps benchpark and checks that `unet3d` scaffolds and renders
its `ramble.yaml` with the dftracer modifier wired in (no build, no GPU):

```bash
./bootstrap.sh
export PATH="$PWD/bin:$PATH"
dftw info "unet3d +rocm package_manager=spack-pip"
```

A full build/run of `unet3d` needs a ROCm + flux system (LLNL); on the target machine,
`dftw run --dry-run` concretizes and renders without submitting.

## License

See [LICENSE](LICENSE).
