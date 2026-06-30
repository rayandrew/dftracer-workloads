from ramble.modkit import *


class Dftracer(BasicModifier):
    """DFTracer I/O tracing, selectable per run via modes."""

    name = "dftracer"

    tags("profiler", "io-tracing")

    maintainers("rayandrew")

    _default_mode = "normal"

    mode(name="off", description="Tracing disabled")
    mode(name="normal", description="Full per-event tracing, no aggregation")
    mode(name="agg-full", description="Tracing with full aggregation")
    mode(name="agg-selective", description="Tracing with selective aggregation rules")

    _on = ["normal", "agg-full", "agg-selective"]  # any tracing enabled
    _agg = ["agg-full", "agg-selective"]  # aggregation enabled

    env_var_modification("DFTRACER_ENABLE", "0", method="set", modes=["off"])

    # base tracing (all on-modes, including normal)
    env_var_modification("DFTRACER_ENABLE", "1", method="set", modes=_on)
    env_var_modification("DFTRACER_INC_METADATA", "1", method="set", modes=_on)
    env_var_modification("DFTRACER_TRACE_COMPRESSION", "1", method="set", modes=_on)
    env_var_modification(
        "DFTRACER_LOG_FILE",
        "{experiment_run_dir}/trace/{experiment_name}",
        method="set",
        modes=_on,
    )

    # Declare the trace dir as this modifier's output so harvest captures it
    # uniformly (parallel to the builtin darshan modifier's archive_pattern).
    # Glob only matches when tracing is on, so this is safe in the "off" mode.
    archive_pattern("{experiment_run_dir}/trace/*")

    # aggregation (agg-* only); interval is a ramble variable (dftw injects it)
    env_var_modification("DFTRACER_ENABLE_AGGREGATION", "1", method="set", modes=_agg)
    env_var_modification(
        "DFTRACER_TRACE_INTERVAL_MS", "{dftracer_interval_ms}", method="set", modes=_agg
    )
    env_var_modification("DFTRACER_AGGREGATION_TYPE", "FULL", method="set", modes=["agg-full"])
    env_var_modification(
        "DFTRACER_AGGREGATION_TYPE", "SELECTIVE", method="set", modes=["agg-selective"]
    )
    env_var_modification(
        "DFTRACER_AGGREGATION_FILE", "{dftracer_agg_rules}", method="set", modes=["agg-selective"]
    )

    # Default trace-derived I/O FOMs for any dftracer-traced workload (apps add their own on top):
    # a post-run step writes a flat per-cat/op/rank table, extracted below as context FOMs.
    _summary = "{experiment_run_dir}/dftracer_summary.txt"

    archive_pattern("{experiment_run_dir}/dftracer_summary.txt")

    executable_modifier("dftracer_summarize")

    def dftracer_summarize(self, executable_name, executable, app_inst=None):
        from ramble.util.executable import CommandExecutable

        pre_exec, post_exec = [], []
        # Attach once, after the main (mpi) executable, and only when tracing is on.
        if executable.mpi and self._usage_mode in self._on:
            post_exec.append(
                CommandExecutable(
                    "dftracer-summary",
                    template=[
                        # dftracer_stats from PATH or the spack install; tolerate absence.
                        "export DFTRACER_STATS_BIN=$(command -v dftracer_stats ||"
                        " echo $(spack location -i dftracer-utils 2>/dev/null)/bin/dftracer_stats)",
                        "python3 {dftracer_summary_script} {experiment_run_dir}/trace"
                        " -o "
                        + self._summary
                        + " --index-dir {experiment_run_dir}/.dftindex || true",
                    ],
                    mpi=False,
                )
            )
        return pre_exec, post_exec

    # Dimension and metrics share one line, so the context and metric regexes match the same line.
    figure_of_merit_context(
        "dftracer category", regex=r"dftracer_cat (?P<cat>\S+)", output_format="cat {cat}"
    )
    figure_of_merit_context(
        "dftracer operation", regex=r"dftracer_op (?P<op>\S+)", output_format="op {op}"
    )
    figure_of_merit_context(
        "dftracer rank", regex=r"dftracer_rank (?P<rank>\S+)", output_format="rank {rank}"
    )

    _cat_metrics = [
        ("events", "count", r"count=(?P<v>[0-9]+)", ""),
        ("duration", "dur", r"dur_s=(?P<v>[0-9.]+)", "s"),
        ("io_ops", "iops", r"iops=(?P<v>[0-9]+)", ""),
        ("io_time", "io", r"io_s=(?P<v>[0-9.]+)", "s"),
        ("bytes", "bytes", r"bytes=(?P<v>[0-9]+)", "bytes"),
        ("bandwidth", "mibps", r"mibps=(?P<v>[0-9.]+)", "MiB/s"),
    ]
    for _kind, _ctx, _prefix in (
        ("cat", "dftracer category", "dftracer_cat"),
        ("op", "dftracer operation", "dftracer_op"),
    ):
        for _label, _g, _frag, _unit in _cat_metrics:
            figure_of_merit(
                f"{_kind}_{_label}",
                fom_regex=rf"{_prefix} \S+ .*{_frag}",
                group_name="v",
                units=_unit,
                log_file=_summary,
                contexts=[_ctx],
            )

    for _label, _g, _frag, _unit in (
        ("io_time", "io", r"io_s=(?P<v>[0-9.]+)", "s"),
        ("bytes", "bytes", r"bytes=(?P<v>[0-9]+)", "bytes"),
    ):
        figure_of_merit(
            f"rank_{_label}",
            fom_regex=rf"dftracer_rank \S+ .*{_frag}",
            group_name="v",
            units=_unit,
            log_file=_summary,
            contexts=["dftracer rank"],
        )

    for _name, _frag, _unit in (
        ("dftracer_events_total", r"dftracer_events_total (?P<v>[0-9]+)", ""),
        ("dftracer_trace_files", r"dftracer_trace_files (?P<v>[0-9]+)", ""),
    ):
        figure_of_merit(_name, fom_regex=_frag, group_name="v", units=_unit, log_file=_summary)
