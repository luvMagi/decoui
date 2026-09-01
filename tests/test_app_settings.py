"""Tests for persisted application settings."""

from __future__ import annotations

from pathlib import Path

from decoui.storage.db import get_setting, init_db, set_db_path, set_setting


def test_setting_round_trip_and_update(tmp_path: Path) -> None:
    """Verify settings can be inserted, read, and updated."""
    set_db_path(tmp_path / "settings.db")
    init_db()

    assert get_setting("missing", "fallback") == "fallback"

    set_setting("ui.sidebar.width", "240")
    assert get_setting("ui.sidebar.width") == "240"

    set_setting("ui.sidebar.width", "320")
    assert get_setting("ui.sidebar.width") == "320"
