from __future__ import annotations
from pathlib import Path


def project_root() -> Path:
    p = Path(__file__).resolve()
    for parent in [p] + list(p.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    # fallback: cwd
    return Path.cwd().resolve()


def state_dir() -> Path:
    d = project_root() / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d
