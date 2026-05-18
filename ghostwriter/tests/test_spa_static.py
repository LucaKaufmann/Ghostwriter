"""Tests for SPA static file path handling."""

from app import main


def test_frontend_file_path_rejects_traversal(tmp_path, monkeypatch):
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    asset_path = frontend_dir / "asset.txt"
    asset_path.write_text("asset")
    (tmp_path / "pyproject.toml").write_text("secret")

    monkeypatch.setattr(main, "FRONTEND_DIR", frontend_dir)

    assert main._frontend_file_path("asset.txt") == asset_path.resolve()
    assert main._frontend_file_path("../pyproject.toml") is None
