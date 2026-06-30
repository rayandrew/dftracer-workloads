import os

from spack.package import *
from spack_repo.builtin.build_systems.python import PythonPackage


class Dftracer(PythonPackage):
    """DFTracer: a low-overhead, multi-level I/O profiler for deep-learning Python apps."""

    homepage = "https://github.com/LLNL/dftracer"
    git = "https://github.com/LLNL/dftracer.git"

    maintainers("hariharan-devarajan", "rayandrew")
    license("MIT")

    version("2.0.3", tag="v2.0.3", commit="1e1d153d06a207cbb24cd32e04d0888dd1e88211")

    variant("mpi", default=True, description="MPI-aware I/O tracing")
    variant("hdf5", default=False, description="HDF5 I/O tracing")
    variant("gpu", default=False, description="GPU (HIP) tracing")
    variant("ftrace", default=False, description="Linux ftrace function tracing")
    variant("hwloc", default=False, description="hwloc hardware-locality metadata")

    depends_on("python@3.7:", type=("build", "run"))
    depends_on("py-setuptools@64:", type="build")
    depends_on("py-setuptools-scm@8:", type="build")
    depends_on("py-pybind11", type="build")
    depends_on("py-wheel", type="build")
    depends_on("ninja", type="build")
    depends_on("cmake@3.12:", type="build")
    depends_on("c", type="build")
    depends_on("cxx", type="build")

    depends_on("mpi", when="+mpi")
    depends_on("hdf5", when="+hdf5")
    depends_on("hwloc", when="+hwloc")

    depends_on("pydftracer@2.0.3", type="run")
    depends_on("dftracer-utils@0.0.10", type="run")

    # Forked DataLoader workers re-init via the explicit-logfile path, which stripped the
    # "extension" with find_last_of(".") over the WHOLE path -- truncating at a dot in a
    # parent dir (e.g. a hidden ".dftw" dir) and collapsing the log path to that ancestor,
    # so worker traces became empty-base "-<hash>-.pfw.gz" files in that dir. Only strip a
    # '.' in the basename; plus defensive empty-value hardening. (Upstream PR pending.)
    patch("fork-empty-logfile.patch")

    def patch(self):
        filter_file(
            'if(NOT DFTRACER_PYTHON_EXEC STREQUAL "OFF")',
            'if(NOT DFTRACER_PYTHON_EXE STREQUAL "OFF")',
            "CMakeLists.txt",
            string=True,
        )
        filter_file(
            "set(PYTHON_EXECUTABLE ${DFTRACER_PYTHON_EXEC})",
            "set(PYTHON_EXECUTABLE ${DFTRACER_PYTHON_EXE})\n"
            "        set(Python_EXECUTABLE ${DFTRACER_PYTHON_EXE})\n"
            "        set(Python3_EXECUTABLE ${DFTRACER_PYTHON_EXE})",
            "CMakeLists.txt",
            string=True,
        )

    @run_after("install")
    def _make_namespace_package(self):
        init = join_path(python_purelib, "dftracer", "__init__.py")
        if os.path.exists(init):
            os.remove(init)

    def setup_build_environment(self, env):
        spec = self.spec

        def onoff(v):
            return "ON" if spec.satisfies(f"+{v}") else "OFF"

        if spec.satisfies("%cce") or spec.satisfies("%clang"):
            env.append_flags("CXXFLAGS", "-Wno-error=non-pod-varargs")

        env.set("DFTRACER_ENABLE_MPI", onoff("mpi"))
        env.set("DFTRACER_ENABLE_HDF5", onoff("hdf5"))
        env.set("DFTRACER_ENABLE_HIP_TRACING", onoff("gpu"))
        env.set("DFTRACER_ENABLE_FTRACING", onoff("ftrace"))
        env.set("DFTRACER_DISABLE_HWLOC", "OFF" if spec.satisfies("+hwloc") else "ON")
        env.set("DFTRACER_BUILD_TYPE", "Release")
        env.set("DFTRACER_INSTALL_DIR", self.prefix)
        env.set("DFTRACER_PYTHON_SITE", python_purelib)
