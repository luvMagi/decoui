"""Tests for theme discovery, selection priority, and failure handling."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtWidgets import QApplication

from decoui.runner import _apply_startup_theme
from decoui.storage.db import get_setting, init_db, set_db_path, set_setting
from decoui.theme import (
    builtin_themes,
    default_theme_dir,
    discover_themes,
    resolve_theme,
)


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    """Point the settings database at a throwaway file.

    Args:
        tmp_path: pytest's per-test directory.

    Returns:
        The database path, already initialised.
    """
    path = tmp_path / "history.db"
    set_db_path(path)
    init_db()
    return path


def _theme_file(directory: Path, theme_id: str, name: str, **extra: Any) -> Path:
    """Write a minimal valid theme extending the built-in light theme.

    Args:
        directory: Where to write it. Created if absent.
        theme_id: The theme's id.
        name: The theme's display name.
        **extra: Extra top-level keys, e.g. a colour override.

    Returns:
        The file written.
    """
    directory.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "version": 1,
        "id": theme_id,
        "name": name,
        "extends": "light",
        "colors": {"accent": "#123456"},
    }
    payload.update(extra)
    path = directory / f"{name.lower().replace(' ', '-')}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ── Discovery ─────────────────────────────────────────────────────────────────

def test_missing_theme_dir_is_not_an_error(tmp_path: Path) -> None:
    """Verify the common case -- no user themes -- is silent and creates nothing."""
    absent = tmp_path / "themes"

    themes, problems = discover_themes(absent)

    assert set(themes) == set(builtin_themes())
    assert problems == []
    assert not absent.exists()


def test_default_theme_dir_sits_beside_the_database() -> None:
    """Verify user themes live where users would look for them."""
    assert default_theme_dir() == Path.home() / ".decoui" / "themes"


def test_user_theme_is_discovered(tmp_path: Path) -> None:
    """Verify a dropped-in file becomes selectable without any code change."""
    _theme_file(tmp_path, "mine", "Mine")

    themes, problems = discover_themes(tmp_path)

    assert themes["mine"].name == "Mine"
    assert themes["mine"].colors["accent"] == "#123456"
    assert problems == []


def test_non_json_entries_are_ignored(tmp_path: Path) -> None:
    """Verify a notes file or a stray directory does not become a problem."""
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "notes.txt").write_text("not a theme", encoding="utf-8")
    (tmp_path / "backup").mkdir()

    themes, problems = discover_themes(tmp_path)

    assert set(themes) == set(builtin_themes())
    assert problems == []


def test_broken_file_does_not_hide_the_others(tmp_path: Path) -> None:
    """Verify one bad theme costs only itself.

    Hand-written JSON goes wrong routinely; a syntax error in one file must not
    take the user's other themes down with it.
    """
    _theme_file(tmp_path, "good", "Good")
    (tmp_path / "broken.json").write_text("{ nope", encoding="utf-8")

    themes, problems = discover_themes(tmp_path)

    assert "good" in themes
    assert len(problems) == 1
    assert "broken.json" in problems[0].source


def test_user_theme_may_replace_a_builtin(tmp_path: Path) -> None:
    """Verify shadowing works and is reported rather than silent."""
    _theme_file(tmp_path, "light", "My Light")

    themes, problems = discover_themes(tmp_path)

    assert themes["light"].name == "My Light"
    assert any("replaces" in problem.summary for problem in problems)


def test_extends_still_reaches_the_builtin_when_shadowed(tmp_path: Path) -> None:
    """Verify a shadowing theme cannot change what other themes inherit.

    Otherwise dropping one file into the directory would silently re-base every
    theme that extends it.
    """
    _theme_file(tmp_path, "light", "My Light", colors={"bg.app": "#000000"})
    _theme_file(tmp_path, "child", "Child")

    themes, _ = discover_themes(tmp_path)

    assert themes["light"].colors["bg.app"] == "#000000"
    assert themes["child"].colors["bg.app"] == builtin_themes()["light"].colors["bg.app"]


def test_duplicate_ids_resolve_by_filename(tmp_path: Path) -> None:
    """Verify two files claiming one id land the same way on every run."""
    tmp_path.mkdir(exist_ok=True)
    for filename, name in (("a-first.json", "First"), ("b-second.json", "Second")):
        (tmp_path / filename).write_text(json.dumps({
            "version": 1, "id": "dup", "name": name,
            "extends": "light", "colors": {},
        }), encoding="utf-8")

    themes, problems = discover_themes(tmp_path)

    assert themes["dup"].name == "Second"
    report = " ".join(problem.detail for problem in problems)
    assert "a-first.json" in report and "b-second.json" in report


def test_same_display_name_is_allowed(tmp_path: Path) -> None:
    """Verify decoui does not police names the user chose for their own files."""
    tmp_path.mkdir(exist_ok=True)
    for filename, theme_id in (("one.json", "one"), ("two.json", "two")):
        (tmp_path / filename).write_text(json.dumps({
            "version": 1, "id": theme_id, "name": "Same",
            "extends": "light", "colors": {},
        }), encoding="utf-8")

    themes, problems = discover_themes(tmp_path)

    assert themes["one"].name == themes["two"].name == "Same"
    assert problems == []


# ── Resolution ────────────────────────────────────────────────────────────────

def test_unknown_request_falls_back_to_light() -> None:
    """Verify an unavailable theme is reported and then survived."""
    themes = builtin_themes()

    theme, problems = resolve_theme(themes, "gone")

    assert theme.id == "light"
    assert len(problems) == 1
    assert "gone" in problems[0].summary


def test_no_request_yields_the_default() -> None:
    """Verify the no-preference case is not treated as a failure."""
    theme, problems = resolve_theme(builtin_themes(), None)

    assert theme.id == "light"
    assert problems == []


# ── Priority, through the real startup path ───────────────────────────────────

def test_default_startup_uses_light(qt_app: QApplication, db: Path) -> None:
    """Verify an application with no theme configured looks as it always did."""
    problems = _apply_startup_theme(qt_app, None, db.parent / "themes")

    assert problems == []
    assert qt_app.styleSheet()


def test_application_default_is_used_when_the_user_has_no_preference(
    qt_app: QApplication, db: Path, tmp_path: Path
) -> None:
    """Verify gui_main(theme=...) picks the theme when nothing is stored."""
    themes_dir = tmp_path / "themes"
    _theme_file(themes_dir, "brand", "Brand")

    problems = _apply_startup_theme(qt_app, "brand", themes_dir)

    from decoui.theme import active_theme
    assert active_theme().id == "brand"
    assert problems == []


def test_stored_choice_outranks_the_application_default(
    qt_app: QApplication, db: Path, tmp_path: Path
) -> None:
    """Verify the user's pick wins over the application's declared default.

    The argument names a default, the way db_path names a location -- what the
    user then chooses inside the application is theirs.
    """
    themes_dir = tmp_path / "themes"
    _theme_file(themes_dir, "brand", "Brand")
    _theme_file(themes_dir, "chosen", "Chosen")
    set_setting("ui.theme", "chosen")

    _apply_startup_theme(qt_app, "brand", themes_dir)

    from decoui.theme import active_theme
    assert active_theme().id == "chosen"


def test_missing_stored_choice_is_survived_and_kept(
    qt_app: QApplication, db: Path, tmp_path: Path
) -> None:
    """Verify a deleted theme costs the look, not the setting.

    The file may be missing only on this machine, so the preference stays put
    and comes back into effect once the theme returns.
    """
    set_setting("ui.theme", "vanished")

    problems = _apply_startup_theme(qt_app, None, tmp_path / "themes")

    from decoui.theme import active_theme
    assert active_theme().id == "light"
    assert len(problems) == 1
    assert get_setting("ui.theme") == "vanished"


def test_broken_selected_theme_still_starts(
    qt_app: QApplication, db: Path, tmp_path: Path
) -> None:
    """Verify a corrupt theme never stops the application from opening."""
    themes_dir = tmp_path / "themes"
    themes_dir.mkdir(parents=True)
    (themes_dir / "mine.json").write_text('{"version": 1, "id": "mine"', encoding="utf-8")
    set_setting("ui.theme", "mine")

    problems = _apply_startup_theme(qt_app, None, themes_dir)

    from decoui.theme import active_theme
    assert active_theme().id == "light"
    # One for the unreadable file, one for the selection that could not resolve.
    assert len(problems) == 2
