"""Task loading + per-task isolated sandboxes.

Each task runs in a fresh temp directory containing only a copy of the task's
``source.py``. The agent writes its test file there; the harness measures it there;
the directory is torn down afterwards (unless ``keep=True`` for debugging). This
isolation keeps runs deterministic and prevents tests from one task leaking into
another or polluting the repo.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .paths import MANIFEST, TASKS_DIR


@dataclass(frozen=True)
class TaskSpec:
    name: str
    source_path: Path          # tasks/<name>/source.py
    source_filename: str       # "source.py"


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def load_tasks(split: str) -> list[TaskSpec]:
    """Load the TaskSpecs for a named split ("train" | "test" | "all")."""
    manifest = load_manifest()
    source_filename = manifest.get("source_filename", "source.py")
    splits = manifest["splits"]
    if split == "all":
        names = [n for group in splits.values() for n in group]
    else:
        if split not in splits:
            raise ValueError(f"unknown split '{split}'; have {list(splits)} (or 'all')")
        names = splits[split]
    specs = []
    for name in names:
        src = TASKS_DIR / name / source_filename
        if not src.exists():
            raise FileNotFoundError(f"missing source for task '{name}': {src}")
        specs.append(TaskSpec(name=name, source_path=src, source_filename=source_filename))
    return specs


class Sandbox:
    """Context manager for a single task's isolated working directory."""

    def __init__(self, task: TaskSpec, keep: bool = False):
        self.task = task
        self.keep = keep
        self.dir: Path = Path()

    def __enter__(self) -> "Sandbox":
        self.dir = Path(tempfile.mkdtemp(prefix=f"testforge_{self.task.name}_"))
        shutil.copy2(self.task.source_path, self.dir / self.task.source_filename)
        return self

    def __exit__(self, *exc) -> None:
        if not self.keep and self.dir.exists():
            shutil.rmtree(self.dir, ignore_errors=True)

    @property
    def source_path(self) -> Path:
        return self.dir / self.task.source_filename

    def find_test_file(self) -> Path | None:
        candidates = sorted(self.dir.glob("test_*.py"))
        return candidates[0] if candidates else None

    def read_test_file(self) -> str | None:
        path = self.find_test_file()
        return path.read_text(encoding="utf-8") if path else None
