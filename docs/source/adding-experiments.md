# Adding an experiment

A workload is three pieces under `repo/`, plus declaring its outputs so harvest and I/O FOMs
come for free. Use `unet3d` as the reference.

## 1. Spack package

`repo/spack_repo/dftw/packages/<name>/package.py`, pinned source + build:

```python
class MyWorkload(Package):
    version("mlperf", git="https://github.com/org/repo", commit="<sha>")
    patch("dftracer.patch", level=1)          # instrumentation, via `dftw patch`
    depends_on("python", type=("build", "run"))
    depends_on("mpi")
    depends_on("dftracer@2.0.3 +mpi", type=("build", "run"))

    def install(self, spec, prefix):
        install_tree(".", prefix)
```

Pin or bump the source with `dftw pin <name> <ref>`; regenerate the patch with `dftw patch
{edit,save}`.

## 2. Ramble application

`repo/applications/<name>/application.py`, executables + FOMs:

```python
class MyWorkload(ExecutableApplication):
    executable("train", "python3 {app_root}/main.py --data_dir {data_dir} ...", use_mpi=True)
    workload("train", executables=["train"])

    # Declare workload variables AFTER workload("train") or ramble drops them.
    workload_variable("data_dir", default="REQUIRED", workloads=["train"])

    # Declare app outputs so harvest captures them.
    archive_pattern("{experiment_run_dir}/myworkload.log")

    figure_of_merit(
        "samples_per_sec",
        log_file="{experiment_run_dir}/{experiment_name}.out",
        fom_regex=r'.*"key": "throughput", "value": (?P<fom>[0-9.]+)',  # note the leading .*
        group_name="fom", units="samples/s",
    )
```

```{warning}
ramble matches FOM/success regexes with `re.match` (anchored at line start). If the value is
mid-line, prefix the regex with `.*`. A missing application FOM also flips the experiment to
`FAILED`. See {doc}`tracing`.
```

## 3. Benchpark experiment

`repo/experiments/<name>/experiment.py` declares variants, scaling, and the package spec.
Reuse the shared mixins in `repo/lib/dftw_bench/` (`PyTorch`, `DFTracer`).

## 4. Tracing and I/O FOMs are automatic

Applying the `dftracer` modifier (the default for `dftw run`) adds tracing, declares `trace/*`
and `dftracer_summary.txt` as archived outputs, and emits per-category, per-operation, and
per-rank I/O FOMs. Your app only adds its own FOMs on top.

## 5. Verify

```bash
dftw list experiments
dftw info "<name> ..."
dftw build "<name> ..." --system "..." --mode normal
dftw run   "<name> ..." --system "..." --mode normal --nodes 1
```

Confirm the harvested `results.json` has your app FOM plus the trace-derived I/O FOMs, and
that the run directory stayed lean (see {doc}`harvesting`).
