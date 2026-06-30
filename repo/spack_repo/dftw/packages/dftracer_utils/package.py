from spack.package import *
from spack_repo.builtin.build_systems.python import PythonPackage


class DftracerUtils(PythonPackage):
    """DFTracer-utils: python bindings + utilities to read/analyze DFTracer traces"""

    homepage = "https://github.com/LLNL/dftracer-utils"
    git = "https://github.com/LLNL/dftracer-utils.git"

    maintainers("hariharan-devarajan", "rayandrew")
    license("MIT")

    version("0.0.10", tag="v0.0.10", commit="424f5ad8c48acd401af9d9a94c59475dddf37dc8")

    variant("mpi", default=True, description="MPI-aware utilities")
    variant("analysis", default=False, description="dask/pyarrow trace-analysis extras")

    depends_on("python@3.8:", type=("build", "run"))
    depends_on("py-scikit-build-core@0.10:", type="build")
    depends_on("py-setuptools-scm@8:", type="build")  # scikit-build-core dynamic version provider
    depends_on("cmake@3.15:", type="build")
    depends_on("ninja", type="build")
    depends_on("c", type="build")
    depends_on("cxx", type="build")

    depends_on("rocksdb@10.10.1")
    depends_on("zstd@1.5.7:")
    depends_on("zlib-ng")
    depends_on("simdjson@3.2:")
    depends_on("span-lite@0.11.0")

    depends_on("mpi", when="+mpi")

    depends_on("py-pyarrow@14:", when="+analysis", type="run")
    depends_on("py-dask@2024.1:", when="+analysis", type="run")
    depends_on("py-dask-jobqueue@0.8:", when="+analysis", type="run")

    def setup_build_environment(self, env):
        if self.spec.satisfies("%cce") or self.spec.satisfies("%clang"):
            env.append_flags("CXXFLAGS", "-Wno-error=non-pod-varargs")
        env.set("DFTRACER_UTILS_LOCAL_PACKAGES", "ON")
        env.set("CPM_USE_LOCAL_PACKAGES", "ON")
        env.set("DFTRACER_UTILS_ENABLE_MPI", "ON" if self.spec.satisfies("+mpi") else "OFF")
