from ramble.appkit import *


class Unet3d(ExecutableApplication):
    """MLCommons UNet3D (3D medical image segmentation), DFTracer-instrumented."""

    name = "unet3d"

    tags = ["python", "machine-learning", "i-o", "mpi"]

    software_spec("unet3d", pkg_spec="unet3d")

    executable(
        "clear_cache",
        'cd {unet3d_root} && python3 -c "'
        "from mlperf_logging.mllog import constants; "
        "from runtime.logging import mllog_event; "
        'mllog_event(key=constants.CACHE_CLEAR, value=True)"',
        use_mpi=False,
    )
    executable(
        "train",
        "python3 {unet3d_root}/main.py"
        " --data_dir {data_dir}"
        " --epochs {epochs}"
        " --evaluate_every {evaluate_every}"
        " --start_eval_at {start_eval_at}"
        " --quality_threshold {quality_threshold}"
        " --batch_size {batch_size}"
        " --optimizer sgd"
        " --ga_steps {ga_steps}"
        " --learning_rate {learning_rate}"
        " --seed {seed}"
        " --lr_warmup_epochs {lr_warmup_epochs}"
        " --num_workers {num_workers}"
        " {extra_args}",
        use_mpi=True,
    )

    workload("train", executables=["clear_cache", "train"])

    # NOTE: workload_variable must come AFTER workload("train")
    # ramble attaches these by workload name, so the workload has to exist first or
    # the defaults are silently dropped (and {unet3d_root} etc. never expand).
    workload_variable(
        "unet3d_root",
        default="{unet3d}/retired_benchmarks/unet3d/pytorch",
        description="instrumented source directory",
        workloads=["train"],
    )
    workload_variable(
        "data_dir", default="REQUIRED", description="staged dataset", workloads=["train"]
    )
    workload_variable("epochs", default="10", description="training epochs", workloads=["train"])
    workload_variable(
        "batch_size", default="4", description="per-GPU batch size", workloads=["train"]
    )
    workload_variable(
        "ga_steps", default="1", description="grad accumulation steps", workloads=["train"]
    )
    workload_variable(
        "num_workers", default="8", description="dataloader workers", workloads=["train"]
    )
    workload_variable(
        "learning_rate", default="0.8", description="learning rate", workloads=["train"]
    )
    workload_variable(
        "lr_warmup_epochs", default="200", description="lr warmup epochs", workloads=["train"]
    )
    workload_variable(
        "evaluate_every", default="20", description="eval interval", workloads=["train"]
    )
    workload_variable(
        "start_eval_at", default="1000", description="first eval epoch", workloads=["train"]
    )
    workload_variable(
        "quality_threshold", default="0.908", description="target mean dice", workloads=["train"]
    )
    workload_variable("seed", default="-1", description="random seed", workloads=["train"])
    workload_variable(
        "extra_args",
        default="",
        description="escape hatch: extra main.py flags for the long-tail argparse args",
        workloads=["train"],
    )

    archive_pattern("{experiment_run_dir}/unet3d.log")

    # ramble uses re.match (anchored), so mid-line mllog targets need a leading .* to match.
    figure_of_merit(
        "samples_per_epoch",
        log_file="{experiment_run_dir}/{experiment_name}.out",
        fom_regex=r'.*"key": "samples_per_epoch", "value": (?P<fom>[0-9]+)',
        group_name="fom",
        units="samples",
    )

    success_criteria(
        "completed",
        mode="string",
        match=r'.*"key": "run_stop"',
        file="{experiment_run_dir}/{experiment_name}.out",
    )
