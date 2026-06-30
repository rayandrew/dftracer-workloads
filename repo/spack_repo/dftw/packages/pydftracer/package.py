from spack.package import *
from spack_repo.builtin.build_systems.python import PythonPackage


class Pydftracer(PythonPackage):
    """Python libraries for DFTracer: the pure-Python API layer (`dftracer.python`)."""

    homepage = "https://github.com/LLNL/pydftracer"
    git = "https://github.com/LLNL/pydftracer.git"

    maintainers("hariharan-devarajan", "rayandrew")
    license("MIT")

    version("2.0.3", tag="v2.0.3", commit="1b27a55dede699ecb734bb00de8577045714c9e4")

    variant("dynamo", default=False, description="torch.compile / TorchDynamo tracing")

    depends_on("python@3.7:", type=("build", "run"))
    depends_on("py-setuptools@64:", type="build")
    depends_on("py-setuptools-scm@8:", type="build")

    depends_on("py-torch@2.5.1:", when="+dynamo", type="run")
