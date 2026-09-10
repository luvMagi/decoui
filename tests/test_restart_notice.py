"""Tests for the notice that a language change waits for the next launch."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import QApplication, QLabel

from decoui.i18n import set_language, t_in
from decoui.storage.db import init_db, set_db_path
from decoui.ui import settings_dialog as settings_module
from decoui.ui.restart_notice import LOCK_SECONDS, RestartNoticeDialog
from decoui.ui.settings_dialog import SettingsDialog


@pytest.fixture()
def english(tmp_path: Path) -> Iterator[None]:
    """Run the interface in English, against a throwaway database.

    Yields:
        Nothing; the language is restored afterwards so the rest of the suite
        is not left in whatever a test chose.
    """
    set_db_path(tmp_path / "history.db")
    init_db()
    set_language("en")
    yield
    set_language("en")


def _escape(dialog: RestartNoticeDialog) -> QKeyEvent:
    """Build an Escape key press aimed at a dialog.

    Args:
        dialog: Unused beyond documenting the intent of the event.

    Returns:
        The key event.
    """
    return QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
    )


# ── The notice itself ─────────────────────────────────────────────────────────

def test_the_notice_is_written_in_the_language_just_chosen(
    qt_app: QApplication, english: None
) -> None:
    """Verify the text comes from the chosen catalogue, not the running one.

    This is the whole point: a reader who has just asked for Japanese is told in
    Japanese, which is also the clearest confirmation that the choice landed.
    """
    dialog = RestartNoticeDialog("ja-JP")

    assert dialog.windowTitle() == t_in("ja-JP", "settings.restart_title")
    assert dialog.windowTitle() != t_in("en", "settings.restart_title")

    dialog.close()


def test_the_notice_names_the_language_in_its_own_name(
    qt_app: QApplication, english: None
) -> None:
    """Verify the body says the endonym rather than the code or the English name."""
    dialog = RestartNoticeDialog("zh-CN")

    body = next(
        label.text() for label in dialog.findChildren(QLabel)
        if "decoui" in label.text()
    )

    assert "简体中文" in body
    assert "zh-CN" not in body

    dialog.close()


def test_the_button_is_locked_and_counts_down(
    qt_app: QApplication, english: None
) -> None:
    """Verify the button refuses the first seconds and shows how many are left.

    Driven by calling the tick directly rather than by sleeping: the behaviour
    under test is the state machine, and three real seconds per test is a price
    the suite should not pay to observe it.
    """
    dialog = RestartNoticeDialog("en")

    assert dialog.locked
    assert not dialog._button.isEnabled()
    assert dialog._button.text() == t_in("en", "settings.restart_wait",
                                         seconds=LOCK_SECONDS)

    for remaining in range(LOCK_SECONDS - 1, 0, -1):
        dialog._tick()
        assert dialog.locked
        assert not dialog._button.isEnabled()
        assert dialog._button.text() == t_in("en", "settings.restart_wait",
                                             seconds=remaining)

    dialog._tick()

    assert not dialog.locked
    assert dialog._button.isEnabled()
    assert dialog._button.text() == t_in("en", "common.ok")

    dialog.close()


def test_the_lock_cannot_be_walked_around(
    qt_app: QApplication, english: None
) -> None:
    """Verify Escape and the title bar's close button are refused while locked.

    Without this the lock is decoration: Escape closes a QDialog by default, so
    the keystroke most likely to be pressed reflexively would dismiss the notice
    faster than the button ever could.
    """
    dialog = RestartNoticeDialog("en")
    dialog.show()

    qt_app.sendEvent(dialog, _escape(dialog))
    assert dialog.isVisible(), "Escape dismissed a locked notice"

    closing = QCloseEvent()
    qt_app.sendEvent(dialog, closing)
    assert not closing.isAccepted(), "the close button dismissed a locked notice"

    for _ in range(LOCK_SECONDS):
        dialog._tick()

    reopened = QCloseEvent()
    qt_app.sendEvent(dialog, reopened)
    assert reopened.isAccepted(), "the notice refused to close after unlocking"


# ── When the settings dialog raises it ────────────────────────────────────────

@pytest.fixture()
def raised(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record the language of every notice the settings dialog raises.

    Args:
        monkeypatch: pytest's patcher.

    Returns:
        The list the recorder appends to.
    """
    seen: list[str] = []

    class Recorder(RestartNoticeDialog):
        def exec(self) -> int:
            seen.append(self.language)
            return 1

    monkeypatch.setattr(settings_module, "RestartNoticeDialog", Recorder)
    return seen


def _accept_with_language(code: str) -> None:
    """Open settings, pick a language and press OK.

    Args:
        code: The language to select.
    """
    dialog = SettingsDialog()
    dialog._language.setCurrentIndex(dialog._language.findData(code))
    dialog.accept()


def test_choosing_a_different_language_raises_the_notice(
    qt_app: QApplication, english: None, raised: list[str]
) -> None:
    """Verify the user is told, in the language they picked."""
    _accept_with_language("ja-JP")

    assert raised == ["ja-JP"]


def test_choosing_the_running_language_raises_nothing(
    qt_app: QApplication, english: None, raised: list[str]
) -> None:
    """Verify no notice when nothing about the interface is going to change."""
    _accept_with_language("en")

    assert raised == []


def test_going_back_to_the_running_language_raises_nothing(
    qt_app: QApplication, english: None, raised: list[str]
) -> None:
    """Verify the test is against what is running, not against what was stored.

    A user who picked a language last session and has not restarted since is
    offered that stored choice when the dialog reopens. Switching back to the
    one actually on screen needs no restart -- but comparing against the stored
    value, as the write to the database must, would announce one anyway.
    """
    _accept_with_language("ja-JP")
    raised.clear()

    # Still running English; the stored choice is now ja-JP.
    _accept_with_language("en")

    assert raised == []
