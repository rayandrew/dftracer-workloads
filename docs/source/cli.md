# CLI reference

`dftw` is the single entry point. It delegates to benchpark/ramble/spack for everything they
already do, and adds the orchestration glue on top. Run `dftw <command> --help` for the
authoritative, up-to-date flags.

## Experiment lifecycle

:::{list-table}
:header-rows: 1
:widths: 22 78

* - Command
  - Description
* - `dftw new`
  - Scaffold a benchpark workspace (system init + experiment init + setup).
* - `dftw build <experiment>`
  - Build the workload (spack + pip). Operates on `--workspace`/`DFTW_WORKSPACE` if active.
* - `dftw run <experiment>`
  - Run the workload (`ramble on`), **block** until the flux job(s) finish, then harvest
    FOMs + traces + provenance. `--no-wait` submits and returns for later `dftw harvest`.
* - `dftw harvest <experiment>`
  - Collect FOMs + traces + provenance from a finished run into the results store (after
    `--no-wait`, or to re-harvest an existing workspace).
* - `dftw activate <workspace>`
  - Print shell to enter a workspace: `eval "$(dftw activate <ws>)"`.
:::

### `dftw run` key options

:::{list-table}
:header-rows: 1
:widths: 24 76

* - Flag
  - Meaning
* - `--system <spec>`
  - benchpark system spec, e.g. `"llnl-elcapitan cluster=tuolumne"`.
* - `--mode <mode>`
  - DFTracer tracing mode: `off | normal | agg-full | agg-selective`. See {doc}`tracing`.
* - `--nodes <n>`
  - Node count (sets the `n_nodes` ramble variable).
* - `--repeats <n>`
  - Run the experiment N times via ramble `n_repeats`: each repeat gets its own dir + trace
    and a separate job; FOMs are aggregated (mean/stdev). `0` = single run.
* - `--interval-ms <ms>`
  - Aggregation interval for `agg-*` modes.
* - `--agg-rules <yaml>`
  - Selective aggregation rules (required for `agg-selective`).
* - `--queue <name>`
  - Scheduler queue/partition (e.g. `pdebug`).
* - `--time-limit <min>`
  - Job walltime in minutes.
* - `--no-wait`
  - Submit the job(s) and return the job ids; harvest later with `dftw harvest`.
* - `--dry-run`
  - Concretize + render (`ramble setup --dry-run`) and show the plan without installing,
    submitting, or harvesting. Works from scratch on `dftw build` (scaffolds the workspace but
    does not install) and on `dftw run`. Needs the target toolchain to concretize, so it is not
    a CI/offline check.
:::

## Datasets

:::{list-table}
:header-rows: 1
:widths: 26 74

* - Command
  - Description
* - `dftw data prepare <workload>`
  - Produce the dataset via the resumable prepare pipeline (`--dest`, `--work`, `--keep-work`,
    `-p key=value`).
* - `dftw data stage <workload>`
  - Place an already-produced dataset on the run filesystem (idempotent).
* - `dftw data status <workload>`
  - Report the staging state of a target.
:::

## Inspection

:::{list-table}
:header-rows: 1
:widths: 26 74

* - Command
  - Description
* - `dftw list {experiments,systems,modifiers}`
  - List available benchpark experiments, systems, or modifiers.
* - `dftw info <experiment>`
  - Show an experiment's variants (+ DFTracer tracing modes).
* - `dftw workspace ...`
  - List, inspect, and edit scaffolded workspaces.
:::

## Source & patches

:::{list-table}
:header-rows: 1
:widths: 26 74

* - Command
  - Description
* - `dftw pin <workload> <ref>`
  - Update a workload's pinned upstream source commit in its `package.py`.
* - `dftw patch {edit,save,status,reset}`
  - Edit and regenerate the source-instrumentation patches. `edit` re-applies the patch with
    `git apply --3way` so upstream bumps surface as normal conflict markers.
:::

## Passthroughs

`dftw` exposes the bootstrapped tools directly, with dftw's config already wired in:

```bash
dftw benchpark ...   # vendored benchpark CLI
dftw ramble ...      # bootstrapped ramble
dftw spack ...       # bootstrapped spack
```

## Roadmap commands

These exist as commands but are **not yet wired** (they exit with a "pending" message):

- `dftw gen <experiment>`: generate a DLIO config from the workload trace (dftracer-utils).
- `dftw compare <experiment>`: run the DLIO counterpart and score fidelity vs the real run.

See {doc}`architecture` for the roadmap.
