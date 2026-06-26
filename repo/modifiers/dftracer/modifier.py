from ramble.modkit import *


class Dftracer(BasicModifier):
    """DFTracer I/O tracing, selectable per run via modes."""

    name = "dftracer"

    tags("profiler", "io-tracing")

    maintainers("rayandrew")

    _default_mode = "off"

    mode(name="off", description="Tracing disabled")
    mode(name="agg-full", description="Tracing with full aggregation")
    mode(name="agg-selective", description="Tracing with selective aggregation rules")

    _on = ["agg-full", "agg-selective"]

    env_var_modification("DFTRACER_ENABLE", "0", method="set", modes=["off"])

    env_var_modification("DFTRACER_ENABLE", "1", method="set", modes=_on)
    env_var_modification("DFTRACER_INC_METADATA", "1", method="set", modes=_on)
    env_var_modification("DFTRACER_ENABLE_AGGREGATION", "1", method="set", modes=_on)
    env_var_modification("DFTRACER_TRACE_COMPRESSION", "1", method="set", modes=_on)
    env_var_modification(
        "DFTRACER_LOG_FILE",
        "{experiment_run_dir}/trace/{experiment_name}",
        method="set",
        modes=_on,
    )

    env_var_modification("DFTRACER_AGGREGATION_TYPE", "FULL", method="set", modes=["agg-full"])
    env_var_modification("DFTRACER_TRACE_INTERVAL_MS", "1000", method="set", modes=["agg-full"])

    env_var_modification(
        "DFTRACER_AGGREGATION_TYPE", "SELECTIVE", method="set", modes=["agg-selective"]
    )
    env_var_modification(
        "DFTRACER_AGGREGATION_FILE", "{dftracer_agg_rules}", method="set", modes=["agg-selective"]
    )
    env_var_modification(
        "DFTRACER_TRACE_INTERVAL_MS", "5000", method="set", modes=["agg-selective"]
    )
