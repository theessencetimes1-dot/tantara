from types import SimpleNamespace

import pytest

import app.storage_paths as paths


def test_storage_paths_resolve_relative_and_legacy_paths_under_current_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "get_settings", lambda: SimpleNamespace(data_dir=tmp_path))
    (tmp_path / "uploads").mkdir()
    (tmp_path / "bundles").mkdir()
    assert paths.stored_path("uploads", "uploads/evidence.pdf") == tmp_path / "uploads/evidence.pdf"
    assert paths.stored_path("bundles", "/old/workspace/bundles/paperbook.pdf") == tmp_path / "bundles/paperbook.pdf"
    assert paths.stored_path("uploads", "legacy.pdf") == tmp_path / "uploads/legacy.pdf"
    with pytest.raises(ValueError, match="Unsupported"):
        paths.stored_path("unknown", "file.pdf")
    with pytest.raises(ValueError, match="Unsafe"):
        paths.stored_path("uploads", "../outside.pdf")
