# Harvesting & results

A run produces artifacts inside the ramble workspace, which is overwritten on the next run.
Harvesting files a self-contained snapshot of one run into the results store so it survives,
stays lean, and is reproducible.

## When it happens

- `dftw run` harvests automatically after the job finishes.
- `dftw run --no-wait` skips it; run `dftw harvest` once the job completes.
- `dftw harvest` can also re-harvest an existing finished workspace.

## Layout

Each harvest writes one timestamped directory:

```
$DFTW_RESULTS/<workload>/<mode>/<YYYYMMDD-HHMMSS>/
├── results.json          # this run's ramble FOMs (app + trace-derived I/O)
├── metadata.yaml         # provenance: dftw sha, system, mode, run id
├── configs/ramble.yaml   # the exact rendered config
├── experiments/<app>/<workload>/<instance>/
│   ├── <instance>.out            # scheduler / job stdout (the FOM log)
│   ├── exit_codes.out            # per-step exit codes
│   ├── execute_experiment        # the exact command that ran
│   ├── unet3d.log                # app output (declared by the application)
│   ├── dftracer_summary.txt      # trace summary (declared by the modifier)
│   └── trace/*.pfw.gz            # DFTracer traces
├── software/             # spack specs
└── ...
```

## How it works

Harvest delegates file selection to ramble. It does not hand-pick files. What gets collected
is declared at the source via ramble's `archive_pattern` directive: the application declares
its outputs (unet3d: `unet3d.log`), the dftracer modifier declares its outputs (`trace/*`,
`dftracer_summary.txt`).

`dftw harvest` then:

1. runs `ramble workspace analyze` for the FOMs,
2. runs `ramble workspace archive`, which materializes exactly the declared files plus
   `configs/`, `results/`, and `software/`, and files that snapshot into the per-run slot,
3. drops the two directories that accumulate across runs (`logs/`, the full FOM history under
   `results/`) so each slot stays lean; this run's FOMs are surfaced as `results.json`,
4. moves the live traces out of the workspace so the work directory does not grow unbounded.

Because selection is declarative, adding a workload needs no changes to harvest. Just declare
that workload's outputs with `archive_pattern` (see {doc}`adding-experiments`).

`ramble workspace archive` is selective per experiment: it captures FOM logs and declared
patterns, not the whole run directory, so transient caches (e.g. a MIOpen kernel cache) are
excluded automatically.

## Repeats

`dftw run --repeats N` uses ramble's `n_repeats`: N independent instances, each with its own
run directory, `trace/`, and job. `ramble workspace analyze` aggregates their FOMs
(mean/stdev), and all instances are captured in the harvest.
