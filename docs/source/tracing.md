# DFTracer tracing & I/O FOMs

DFTracer integration lives in one benchpark modifier (`repo/modifiers/dftracer/`), reused
across every workload. It attaches in two layers:

- Runtime/env: the modifier sets `DFTRACER_*` and points trace output at the run directory.
  Selectable per run via modes.
- Source annotations (`initialize_log`, `@ai`) live in the workload's patch. They no-op when
  `DFTRACER_ENABLE=0`, so one build serves every mode.

## Modes

Set with `dftw run --mode <mode>`:

:::{list-table}
:header-rows: 1
:widths: 20 80

* - Mode
  - Behavior
* - `off`
  - Disabled. No traces, no I/O FOMs.
* - `normal`
  - Full per-event tracing, no aggregation. Richest traces (per rank + per worker).
* - `agg-full`
  - Aggregation at `--interval-ms` intervals.
* - `agg-selective`
  - Aggregation driven by `--agg-rules <yaml>` (required).
:::

## Where traces land

`DFTRACER_LOG_FILE` is set to `{experiment_run_dir}/trace/{experiment_name}`, so every rank
and every forked DataLoader worker writes into the run's `trace/`. Files are named
`...-<rank>-of-<n>-<hash>[-app].pfw.gz`: `-app` is the rank process, plain `-.pfw.gz` is a
forked worker (workers carry most of the read I/O). The modifier declares `trace/*` as its
archived output, so harvest keeps it (see {doc}`harvesting`).

## Trace-derived figures of merit

After the run, the modifier runs `repo/modifiers/dftracer/dftracer_summary.py`, which
summarizes the traces with [`dftracer_stats`](https://github.com/LLNL/dftracer-utils) and
writes a flat `dftracer_summary.txt`. ramble extracts every row as a figure of merit. This is
the default I/O FOM set for any traced workload; apps add their own on top.

The FOM set is data-driven: one row per category, operation, and rank the workload actually
produced. ramble's `figure_of_merit_context` turns each row into its own context, so nothing
needs enumerating.

:::{list-table}
:header-rows: 1
:widths: 28 28 44

* - Dimension
  - Context
  - Metrics
* - Category (`POSIX`, `compute`, `comm`, ...)
  - `cat <name>`
  - events, duration (s), io_ops, io_time (s), bytes, bandwidth (MiB/s)
* - Operation (`read`, `open64`, `lseek64`, ...)
  - `op <name>`
  - events, duration (s), io_ops, io_time (s), bytes, bandwidth (MiB/s)
* - Rank
  - `rank <r>`
  - io_time (s), bytes
* - Global
  - none
  - `dftracer_events_total`, `dftracer_trace_files`
:::

Transfer metrics (`io_ops`, `io_time`, `bytes`, `bandwidth`) come from the `grouped_io` block
(real read/write operations with sizes); `duration` covers all events in that group. Non-I/O
groups report `0` for the transfer metrics.

Example (unet3d, `normal`, 1 node, 4 ranks x 8 workers):

```text
dftracer_events_total 101254
dftracer_trace_files 36
dftracer_cat POSIX count=100538 dur_s=158.09 iops=6938 io_s=147.63 bytes=24400549360 mibps=157.617
dftracer_cat compute count=120 dur_s=439.53 iops=0 io_s=0.0 bytes=0 mibps=0.0
dftracer_op  read count=7258 dur_s=147.64 iops=6938 io_s=147.63 bytes=24400549360 mibps=157.617
dftracer_op  lseek64 count=91960 dur_s=0.93 iops=0 io_s=0.0 bytes=0 mibps=0.0
dftracer_rank 0 io_s=37.11 bytes=6246757740
```

The analyzer is resolved at run time from PATH or the spack install. If it is missing, the
summary step is skipped without failing the run, and only app-level FOMs are recorded.

## re.match gotcha

ramble matches FOM and success-criteria regexes with `re.match`, anchored at the start of the
line. A mid-line target (e.g. mllog `:::MLLOG {... "key": ...}`) needs a leading `.*`, or
nothing matches. A missing application FOM also cascades the experiment to `FAILED`. The trace
summary avoids this by putting stable keys at the start of each line.
