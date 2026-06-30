# Quickstart

Running **unet3d** on Tuolumne (LLNL El Capitan, flux) with tracing, end to end. Adjust the
system and experiment specs for your machine.

## 1. Set deployment locations

```bash
export DFTW_DATA_DIR=/p/lustre5/$USER/dataset/dftw/unet3d
export DFTW_WORK=/p/lustre5/$USER/dftw/work
export DFTW_RESULTS=/p/lustre5/$USER/dftw/results
```

## 2. Prepare the dataset

```bash
dftw data prepare unet3d --dest "$DFTW_DATA_DIR"
```

Runs the resumable prepare pipeline (download, preprocess, `.npz`, scale) and stages the
result. Check state with `dftw data status unet3d`.

## 3. Build

```bash
dftw build "unet3d +rocm package_manager=spack-pip" \
  --system "llnl-elcapitan cluster=tuolumne" \
  --mode normal --no-input
```

Scaffolds the workspace, concretizes with spack for the target arch, and builds. Cached, so
re-running is cheap.

## 4. Run and harvest

```bash
dftw run "unet3d +rocm package_manager=spack-pip" \
  --system "llnl-elcapitan cluster=tuolumne" \
  --nodes 1 --mode normal --no-input
```

`dftw run` submits the flux job, blocks until it finishes, then harvests FOMs, traces, and
provenance into `$DFTW_RESULTS/unet3d/normal/<timestamp>/` and prints the path. Add
`--no-wait` to submit and harvest later with `dftw harvest`.

## 5. Results

```
$DFTW_RESULTS/unet3d/normal/<timestamp>/
├── results.json                     # ramble FOMs (app + trace-derived I/O)
├── metadata.yaml                    # provenance (dftw sha, system, mode, run id)
├── configs/ramble.yaml              # the exact rendered config
├── experiments/.../unet3d.log       # app mllog output
├── experiments/.../trace/*.pfw.gz   # DFTracer traces (per rank + per worker)
├── experiments/.../dftracer_summary.txt
└── software/                        # spack specs
```

`results.json` holds the app FOM (`samples_per_epoch`) plus trace-derived I/O FOMs by
category, operation, and rank. See {doc}`tracing`.

## Variations

```bash
# Aggregated tracing
dftw run "unet3d +rocm package_manager=spack-pip" --system "..." --mode agg-selective --agg-rules rules.yaml

# Repeat N times (ramble n_repeats; FOMs aggregated mean/stdev)
dftw run "unet3d +rocm package_manager=spack-pip" --system "..." --repeats 3

# Multi-node
dftw run "unet3d +rocm package_manager=spack-pip" --system "..." --nodes 2
```
