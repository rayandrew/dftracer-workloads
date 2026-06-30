from benchpark.directives import variant
from benchpark.experiment import ExperimentHelper


class DFTracer:
    """DFTracer I/O tracing as a benchpark modifier, mixed into an experiment."""

    class Helper(ExperimentHelper):
        def compute_modifiers_section(self):
            return [{"name": "dftracer", "mode": "normal"}]


class PyTorch:
    """Install torch (+ optional torchvision/torchaudio) from the pytorch.org wheel
    channel that matches the system's accelerator, mixed into an experiment.

    The channel is derived from the benchpark system's ``rocm_version``/``cuda_version``
    (the convention el-capitan/lumi/perlmutter/... all follow), never hardcoded, so an
    experiment carries over to any rocm/cuda system. Wheels are exact-pinned with the
    ``+<channel>`` local tag (e.g. ``torch==2.9.1+rocm6.4``) so pip can't rank a +xpu/+cu
    build above the right one.

    Children enable companion libraries with a boolean -- the version that *pairs* with
    ``torch_version`` is derived automatically (never hardcoded, never "latest"), e.g.::

        class MyExp(Experiment, PyTorch, ...):
            torchvision = True       # -> the torchvision coupled to this torch
            torchaudio = True

    Pass an explicit ``"x.y.z"`` instead of ``True`` only to override the pairing.
    """

    # Companion libs: False = off, True = use the version coupled to ``torch_version``,
    # or an explicit "x.y.z" to override. Children override these.
    torchvision = False
    torchaudio = False

    variant(
        "torch_version",
        default="2.9.1",
        description="torch wheel version (must exist for the system's accelerator channel)",
    )

    def _torch_parts(self):
        v = self.spec.variants["torch_version"][0]
        major, minor, patch = (v.split(".") + ["0", "0"])[:3]
        return int(major), int(minor), int(patch)

    def _torchvision_version(self):
        """The torchvision that ships with this torch. PyTorch couples them by a fixed
        minor offset -- torch 2.x <-> torchvision 0.(x+15) -- sharing the patch
        (torch 2.9.1 <-> torchvision 0.24.1)."""
        major, minor, patch = self._torch_parts()
        if major != 2:
            raise ValueError(f"unknown torchvision pairing for torch {major}.x")
        return f"0.{minor + 15}.{patch}"

    def _torchaudio_version(self):
        """torchaudio shares torch's version exactly (torch 2.9.1 <-> torchaudio 2.9.1)."""
        return self.spec.variants["torch_version"][0]

    def torch_channel(self):
        """pytorch.org wheel channel for this system's accelerator: rocm6.4 / cu124 / cpu."""
        system = self.system_spec.system
        if self.spec.satisfies("+rocm"):
            ver = getattr(system, "rocm_version", None)
            if ver is None:
                raise ValueError(
                    f"{type(system).__name__} exposes no rocm_version; cannot select a "
                    "torch rocm wheel channel"
                )
            return f"rocm{ver.major}.{ver.minor}"
        if self.spec.satisfies("+cuda"):
            ver = getattr(system, "cuda_version", None)
            if ver is None:
                raise ValueError(
                    f"{type(system).__name__} exposes no cuda_version; cannot select a "
                    "torch cuda wheel channel"
                )
            return f"cu{ver.major}{ver.minor}"
        return "cpu"

    def torch_pip_lines(self):
        """requirements.txt lines: the channel index plus exact-pinned torch-family wheels."""
        channel = self.torch_channel()
        version = self.spec.variants["torch_version"][0]
        lines = [
            f"--index-url https://download.pytorch.org/whl/{channel}",
            "--extra-index-url https://pypi.org/simple",
            f"torch=={version}+{channel}",
        ]
        for setting, derive in (
            (self.torchvision, self._torchvision_version),
            (self.torchaudio, self._torchaudio_version),
        ):
            if not setting:
                continue
            name = derive.__name__.lstrip("_").removesuffix("_version")
            ver = setting if isinstance(setting, str) else derive()
            lines.append(f"{name}=={ver}+{channel}")
        return lines
