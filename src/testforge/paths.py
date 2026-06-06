"""Canonical filesystem locations, derived from the package location."""

from __future__ import annotations

from pathlib import Path

# src/testforge/paths.py -> parents[2] == project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = PROJECT_ROOT / "tasks"
RUNS_DIR = PROJECT_ROOT / "runs"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
MANIFEST = TASKS_DIR / "manifest.json"
