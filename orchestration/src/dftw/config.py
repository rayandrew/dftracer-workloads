from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional, Union

import yaml

CONFIG_NAME = "dftw.yaml"
STACK_PACKAGES = ["dftracer", "dftracer-utils", "pydftracer"]


def repo_root(start: Optional[Union[Path, str]] = None) -> Path:
    env = os.environ.get("DFTW_ROOT")
    if env and (Path(env) / CONFIG_NAME).exists():
        return Path(env).resolve()
    p = Path(start or Path.cwd()).resolve()
    for d in [p, *p.parents]:
        if (d / CONFIG_NAME).exists():
            return d
    raise SystemExit(f"{CONFIG_NAME} not found from {p}")


class Config:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / CONFIG_NAME
        self.data: dict[str, Any] = yaml.safe_load(self.path.read_text()) or {}

    @property
    def stack(self) -> dict[str, Any]:
        return self.data.setdefault("stack", {})

    @property
    def workloads(self) -> dict[str, Any]:
        return self.data.setdefault("workloads", {})

    def workload(self, name: str) -> dict[str, Any]:
        if name not in self.workloads:
            raise SystemExit(f"unknown workload: {name}")
        return self.workloads[name]

    def save(self) -> None:
        self.path.write_text(yaml.safe_dump(self.data, sort_keys=False))


def load(start: Optional[Union[Path, str]] = None) -> Config:
    return Config(repo_root(start))
