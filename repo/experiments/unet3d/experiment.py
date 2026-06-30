from benchpark.directives import maintainers, variant
from benchpark.experiment import Experiment
from benchpark.programming_model import ProgrammingModel, ProgrammingModelType
from benchpark.scaling import Scaling, ScalingMode
from dftw_bench import DFTracer, PyTorch

_ProgrammingModel = ProgrammingModel(ProgrammingModelType.Cuda, ProgrammingModelType.Rocm)


class _Unet3dPMHelper(_ProgrammingModel.Helper):
    def get_spack_variants(self):
        return ""


_ProgrammingModel.Helper = _Unet3dPMHelper


class Unet3d(
    Experiment,
    DFTracer,
    PyTorch,
    _ProgrammingModel,
    Scaling(ScalingMode.Strong, ScalingMode.Weak),
):
    """MLCommons UNet3D, traced with DFTracer, paired later with a DLIO counterpart."""

    maintainers("rayandrew")
    torchvision = True

    variant("workload", default="train", values=("train",), description="ramble workload")

    def compute_applications_section(self):
        epochs = 1 if self.spec.satisfies("exec_mode=test") else 20

        self.add_experiment_variable("n_nodes", 1, True)
        self.add_experiment_variable("n_gpus", "{n_nodes}*{sys_gpus_per_node}", True)
        self.add_experiment_variable("epochs", epochs, True)
        self.add_experiment_variable("batch_size", 4, True)
        self.add_experiment_variable("dftracer_mode", "normal", True)

        self.set_environment_variable("DFTW_RESULTS_DIR", "{experiment_run_dir}")

        if self.spec.satisfies("+rocm"):
            miopen = "{experiment_run_dir}/miopen-cache"
            self.set_environment_variable("MIOPEN_USER_DB_PATH", miopen)
            self.set_environment_variable("MIOPEN_CUSTOM_CACHE_DIR", miopen)
            self.set_environment_variable("MIOPEN_FIND_MODE", "FAST")
            self.set_environment_variable("MPICH_GPU_SUPPORT_ENABLED", "0")

        self.register_scaling_config(
            {
                ScalingMode.Strong: {
                    "n_nodes": lambda var, itr, dim, sf: var.val(dim) * sf,
                    "batch_size": lambda var, itr, dim, sf: var.val(dim) // sf,
                },
                ScalingMode.Weak: {
                    "n_nodes": lambda var, itr, dim, sf: var.val(dim) * sf,
                    "batch_size": lambda var, itr, dim, sf: var.val(dim),
                },
            }
        )

        self.set_required_variables(
            n_resources="{n_gpus}",
            process_problem_size="{batch_size}",
            total_problem_size="{batch_size}*{n_gpus}",
        )

    def compute_package_section(self):
        if self.spec.variants["package_manager"][0] != "spack-pip":
            raise ValueError("Use package_manager=spack-pip for this experiment")

        pip_lines = self.torch_pip_lines() + [
            "nibabel==3.2.1",
            "scipy",
            "git+https://github.com/NVIDIA/dllogger",
            "git+https://github.com/mlcommons/logging.git@1.1.0-rc4",
        ]
        self.add_package_spec(self.name, ["unet3d"], package_manager="spack")
        self.add_package_spec(self.name, ["\n".join(pip_lines)], package_manager="pip")
