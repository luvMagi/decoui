"""Tests for the settings entry point and the theme picker."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QScrollArea

from decoui.storage.db import get_setting, init_db, set_db_path, set_setting
from decoui.theme import (
    active_theme,
    builtin_themes,
    set_active_theme,
    set_active_theme_dir,
)
from decoui.ui.settings_dialog import THEME_SETTING, SettingsDialog
from decoui.ui.tag_bar import TagBar


@pytest.fixture()
def themes_dir(tmp_path: Path) -> Iterator[Path]:
    """Isolate theme discovery and the settings database.

    Without this the dialog would scan the developer's real ``~/.decoui/themes``
    and the results would depend on whose machine the suite runs on.

    Yields:
        An empty directory the dialog will read themes from.
    """
    directory = tmp_path / "themes"
    directory.mkdir()
    set_db_path(tmp_path / "history.db")
    init_db()
    set_active_theme_dir(directory)
    set_active_theme(builtin_themes()["light"])
    yield directory
    set_active_theme_dir(None)
    set_active_theme(builtin_themes()["light"])


def _add_theme(
    directory: Path, theme_id: str, name: str, colors: dict[str, str] | None = None
) -> None:
    """Write a minimal user theme into the directory.

    Args:
        directory: The theme directory.
        theme_id: Id for the new theme.
        name: Display name for the new theme.
        colors: Tokens to override on top of light. Left empty the theme is a
            pure rename, which renders the same stylesheet as light -- fine for
            testing the picker, useless for testing that anything was restyled.
    """
    (directory / f"{theme_id}.json").write_text(json.dumps({
        "version": 1, "id": theme_id, "name": name,
        "extends": "light", "colors": colors or {},
    }), encoding="utf-8")


# ── The entry point ───────────────────────────────────────────────────────────

def test_settings_button_is_outside_the_scrolling_pills(qt_app: QApplication) -> None:
    """Verify the button cannot scroll out of reach.

    The tag pills live in a horizontally scrolling area. A button placed in
    there would slide off-screen as soon as an application declared enough tags.
    """
    bar = TagBar([f"tag{index}" for index in range(40)])

    button = bar._settings_btn

    assert bar.layout().indexOf(button) >= 0
    assert not isinstance(button.parent(), QScrollArea)
    assert button.parent() is bar

    bar.close()


def test_settings_button_is_reachable_without_any_tags(qt_app: QApplication) -> None:
    """Verify an application that declares no tags still has a way in."""
    bar = TagBar([])

    assert bar._settings_btn.toolTip() == "Settings"

    bar.close()


def test_settings_button_hard_codes_no_colour(qt_app: QApplication) -> None:
    """Verify the button takes its colours from the theme, not from itself.

    It does carry a stylesheet: the application's generic QPushButton rule
    spends 14px of padding either side, which is right for a word and leaves an
    18px icon nothing, so the button asks for none. What it must never do is
    name a colour -- that would be a second copy to keep in step with every
    theme, and the one that got forgotten.
    """
    bar = TagBar(["one"])

    sheet = bar._settings_btn.styleSheet()

    assert "#" not in sheet, f"a colour literal leaked into the button: {sheet!r}"
    assert "color" not in sheet, f"the button names a colour: {sheet!r}"

    bar.close()


def test_settings_button_emits_the_request(qt_app: QApplication) -> None:
    """Verify pressing the button asks the window to open settings."""
    bar = TagBar(["one"])
    seen: list[bool] = []
    bar.settings_requested.connect(lambda: seen.append(True))

    bar._settings_btn.click()

    assert seen == [True]

    bar.close()


# ── The dialog ────────────────────────────────────────────────────────────────

def test_dialog_is_modal_and_titled(qt_app: QApplication, themes_dir: Path) -> None:
    """Verify the dialog identifies itself and blocks the window behind it."""
    dialog = SettingsDialog()

    assert dialog.windowTitle() == "Settings"
    assert dialog.isModal()

    dialog.close()


def test_dialog_lists_user_themes(qt_app: QApplication, themes_dir: Path) -> None:
    """Verify a theme dropped into the directory can actually be selected."""
    _add_theme(themes_dir, "brand", "Brand")

    dialog = SettingsDialog()

    labels = [dialog._combo.itemText(i) for i in range(dialog._combo.count())]
    assert "Brand" in labels
    assert "Light" in labels

    dialog.close()


def test_dialog_opens_on_the_running_theme(
    qt_app: QApplication, themes_dir: Path
) -> None:
    """Verify the dialog reflects reality, not the stored intent.

    When the stored choice could not be loaded the user is looking at the
    fallback, and that is what the dialog must show.
    """
    set_setting(THEME_SETTING, "vanished")

    dialog = SettingsDialog()

    assert dialog.selected_theme_id() == active_theme().id == "light"

    dialog.close()


def test_picker_is_never_hidden_or_disabled(
    qt_app: QApplication, themes_dir: Path
) -> None:
    """Verify the picker is always usable, whatever is installed.

    Its presence is what tells a user the feature exists, so it stays enabled
    even in the degenerate case of a single available theme.
    """
    dialog = SettingsDialog()

    assert dialog._combo.count() >= 1
    assert dialog._combo.isEnabled()
    assert not dialog._combo.isHidden()

    dialog.close()


def test_restart_notice_is_always_visible(
    qt_app: QApplication, themes_dir: Path
) -> None:
    """Verify the restart requirement is stated before the user commits."""
    from PySide6.QtWidgets import QLabel

    dialog = SettingsDialog()

    notes = [
        label.text()
        for label in dialog.findChildren(QLabel)
        if "restart" in label.text().lower()
    ]
    assert notes

    dialog.close()


def test_duplicate_display_names_are_left_alone(
    qt_app: QApplication, themes_dir: Path
) -> None:
    """Verify decoui does not rename or hide themes the user named itself."""
    _add_theme(themes_dir, "one", "Same")
    _add_theme(themes_dir, "two", "Same")

    dialog = SettingsDialog()

    labels = [dialog._combo.itemText(i) for i in range(dialog._combo.count())]
    assert labels.count("Same") == 2

    dialog.close()


# ── Accepting and cancelling ──────────────────────────────────────────────────

def test_ok_persists_the_theme_id(qt_app: QApplication, themes_dir: Path) -> None:
    """Verify the id is stored, not the display name.

    Storing the name would break the moment a user renamed their own theme.
    """
    _add_theme(themes_dir, "brand", "Brand")
    dialog = SettingsDialog()
    dialog._combo.setCurrentIndex(dialog._combo.findData("brand"))

    dialog.accept()

    assert get_setting(THEME_SETTING) == "brand"


def test_ok_without_a_change_writes_nothing(
    qt_app: QApplication, themes_dir: Path
) -> None:
    """Verify simply opening and confirming leaves the settings untouched."""
    dialog = SettingsDialog()

    dialog.accept()

    assert get_setting(THEME_SETTING) is None


def test_cancel_discards_the_selection(qt_app: QApplication, themes_dir: Path) -> None:
    """Verify a picked-then-cancelled theme is not saved."""
    _add_theme(themes_dir, "brand", "Brand")
    dialog = SettingsDialog()
    dialog._combo.setCurrentIndex(dialog._combo.findData("brand"))

    dialog.reject()

    assert get_setting(THEME_SETTING) is None
    assert dialog.result() == QDialog.DialogCode.Rejected


def test_accepting_restyles_the_running_application(
    qt_app: QApplication, themes_dir: Path
) -> None:
    """Verify a new theme reaches the open windows, not only the database.

    This is the v0.5.0 change: up to v0.4.0 the dialog recorded a choice and
    said a restart was needed, because widgets that style themselves in code
    would have been left stale. They are now told -- see decoui.ui.retheme.
    """
    _add_theme(themes_dir, "brand", "Brand", colors={"bg.app": "#123456"})
    before = qt_app.styleSheet()
    dialog = SettingsDialog()
    dialog._combo.setCurrentIndex(dialog._combo.findData("brand"))

    dialog.accept()

    assert active_theme().id == "brand"
    assert qt_app.styleSheet() != before
    assert "#123456" in qt_app.styleSheet()


def test_accepting_the_running_theme_restyles_nothing(
    qt_app: QApplication, themes_dir: Path
) -> None:
    """Verify pressing OK without changing the theme leaves the windows alone.

    A re-theme rebuilds every console from its records, which costs the scroll
    position. Paying that for a dialog the user only opened to read would be
    a change they did not ask for.
    """
    _add_theme(themes_dir, "brand", "Brand", colors={"bg.app": "#123456"})
    dialog = SettingsDialog()
    before = qt_app.styleSheet()

    dialog.accept()

    assert active_theme().id == "light"
    assert qt_app.styleSheet() == before
