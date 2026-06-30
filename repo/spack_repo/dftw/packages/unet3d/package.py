from spack.package import *
from spack_repo.builtin.build_systems.generic import Package


class Unet3d(Package):
    """MLCommons UNet3D training benchmark, instrumented with DFTracer.

    Sparse checkout of only the unet3d subdir, pinned to a commit (updated by `dftw pin`).
    """

    homepage = "https://github.com/mlcommons/training"
    git = "https://github.com/mlcommons/training.git"

    tags = ["benchmark", "machine-learning"]

    version(
        "mlperf",
        commit="e8c72a4f0e26abeab626cf32a5b30c5d9e448a60",
        get_full_repo=False,
        git_sparse_paths=["retired_benchmarks/unet3d/pytorch"],
    )

    patch("dftracer.patch", level=1)
    depends_on("python", type=("build", "run"))
    depends_on("mpi")
    depends_on("py-mpi4py", type=("build", "run"))
    depends_on("dftracer@2.0.3 +mpi", type=("build", "run"))

    def patch(self):
        pkg = join_path("retired_benchmarks", "unet3d", "pytorch", "data_loading")
        data_loader = join_path(pkg, "data_loader.py")
        pytorch_loader = join_path(pkg, "pytorch_loader.py")
        filter_file('"*_x.npy"', '"*_x.npz"', data_loader, string=True)
        filter_file('"*_y.npy"', '"*_y.npz"', data_loader, string=True)
        filter_file(
            'open("evaluation_cases.txt", "r")',
            'open(__import__("os").path.join('
            "__import__('os').path.dirname(__import__('os').path.dirname("
            '__import__("os").path.abspath(__file__))), "evaluation_cases.txt"), "r")',
            data_loader,
            string=True,
        )
        filter_file(
            "np.load(self.images[idx])",
            'np.load(self.images[idx])["data"]',
            pytorch_loader,
            string=True,
        )
        filter_file(
            "np.load(self.labels[idx])",
            'np.load(self.labels[idx])["data"]',
            pytorch_loader,
            string=True,
        )

    def install(self, spec, prefix):
        install_tree(".", prefix)
