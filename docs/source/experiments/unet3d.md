# unet3d

MLCommons UNet3D (3D medical image segmentation), DFTracer-instrumented. A real PyTorch + MPI
training workload with substantial read I/O, and the reference workload for this harness.

## Spec

```bash
dftw run "unet3d +rocm package_manager=spack-pip" \
  --system "llnl-elcapitan cluster=tuolumne" \
  --nodes 1 --mode normal
```

Variants: `+rocm` / `+cuda` (programming model), `package_manager=spack-pip` (required),
`workload=train`. Strong and weak scaling are supported. Any tracing mode works. See the full
set with `dftw info "unet3d +rocm package_manager=spack-pip"`.

## Dataset

UNet3D reads `.npz` volumes from the prepare pipeline (download, preprocess, `.npz`, scale):

```bash
dftw data prepare unet3d --dest "$DFTW_DATA_DIR"
```

The path is passed in as the `data_dir` workload variable (defaults to `DFTW_DATA_DIR`).

## Key workload variables

Override with `--set key=value`. Defaults:

:::{list-table}
:header-rows: 1
:widths: 30 16 54

* - Variable
  - Default
  - Meaning
* - `epochs`
  - `10`
  - training epochs
* - `batch_size`
  - `4`
  - per-GPU batch size
* - `num_workers`
  - `8`
  - DataLoader workers (each forks a traced process)
* - `ga_steps`
  - `1`
  - gradient-accumulation steps
* - `learning_rate`
  - `0.8`
  - learning rate
* - `lr_warmup_epochs`
  - `200`
  - LR warmup epochs
* - `evaluate_every`
  - `20`
  - evaluation interval
* - `start_eval_at`
  - `1000`
  - first eval epoch
* - `quality_threshold`
  - `0.908`
  - target mean DICE
* - `seed`
  - `-1`
  - random seed
* - `extra_args`
  - empty
  - extra `main.py` flags
:::

A short smoke run will not reach `quality_threshold`, so MLPerf logs `run_stop` with `status:
aborted`. That is expected. The run still succeeds and produces complete traces and FOMs.

## Figures of merit

- App: `samples_per_epoch` (from `unet3d.log` / job output).
- Trace-derived I/O (when tracing is on): per-category, per-operation, and per-rank I/O time,
  bytes, bandwidth, and op counts. See {doc}`../tracing`.

## Instrumentation

The spack package pins the upstream commit and applies `dftracer.patch`, which initializes
DFTracer per rank with a `{rank}-of-{size}` trace path and lets forked DataLoader workers
reinitialize via `pthread_atfork`, so worker I/O is traced into `trace/` instead of leaking to
the CWD. Update it with `dftw patch {edit,save,status}` and bump the source with `dftw pin
unet3d <ref>`.
