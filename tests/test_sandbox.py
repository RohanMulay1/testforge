"""Unit tests for task loading + sandbox isolation (no SDK / API needed)."""

import pytest

from testforge.sandbox import Sandbox, load_manifest, load_tasks


def test_manifest_has_train_and_test_splits():
    manifest = load_manifest()
    assert "train" in manifest["splits"]
    assert "test" in manifest["splits"]


def test_splits_are_disjoint_and_cover_all():
    manifest = load_manifest()
    train = set(manifest["splits"]["train"])
    test = set(manifest["splits"]["test"])
    assert train.isdisjoint(test)
    assert len(load_tasks("all")) == len(train) + len(test)


def test_load_tasks_returns_existing_sources():
    for spec in load_tasks("all"):
        assert spec.source_path.exists()
        assert spec.source_filename == "source.py"


def test_unknown_split_raises():
    with pytest.raises(ValueError):
        load_tasks("nope")


def test_sandbox_copies_source_and_cleans_up():
    spec = load_tasks("train")[0]
    with Sandbox(spec) as sb:
        sandbox_dir = sb.dir
        assert sb.source_path.exists()
        assert sb.source_path.read_text(encoding="utf-8") == spec.source_path.read_text(encoding="utf-8")
        assert sb.find_test_file() is None  # nothing written yet
    assert not sandbox_dir.exists()  # torn down on exit


def test_sandbox_keep_preserves_dir():
    spec = load_tasks("train")[0]
    with Sandbox(spec, keep=True) as sb:
        sandbox_dir = sb.dir
        (sandbox_dir / "test_source.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
        assert sb.find_test_file() is not None
        assert sb.read_test_file().startswith("def test_x")
    assert sandbox_dir.exists()  # kept
    # cleanup so we don't leave temp dirs around
    import shutil
    shutil.rmtree(sandbox_dir, ignore_errors=True)
