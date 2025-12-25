# from __future__ import annotations

# from pathlib import Path


# def project_root() -> Path:
#     """
#     Resolve project root assuming this file lives in:
#     src/ai_book_translator/infrastructure/persistence/paths.py
#     """
#     return Path(__file__).resolve().parents[4]


# def state_dir() -> Path:
#     """
#     Project-local state directory:
#     <project_root>/state/
#     """
#     d = project_root() / "state"
#     d.mkdir(parents=True, exist_ok=True)
#     return d


# def state_path_for_hash(doc_hash: str) -> Path:
#     """
#     JSON file storing resumable translation state.
#     """
#     return state_dir() / f"{doc_hash}.json"


# def translation_txt_path(doc_hash: str) -> Path:
#     """
#     TXT file where translated chunks are appended incrementally.
#     """
#     return state_dir() / f"{doc_hash}.txt"

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
