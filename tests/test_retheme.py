"""Tests for swapping the theme of a running application.

The contract this file guards is not "the colours changed". It is that a window
re-themed in place ends up **indistinguishable from one built under that theme
in the first place**, and that nothing is destroyed on the way there. So most
of these tests build the same widget twice -- once natively under the target
theme, once under another and then re-themed -- and compare the two, rather
than asserting particular colour values that would have to be edited every time
a theme file is retouched.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication, QPushButton

from decoui import tool, toolset
from decoui.registry import ToolInfo, build_tree
from decoui.storage.db import init_db, set_db_path
from decoui.theme import (
    Theme,
    active_theme,
    builtin_themes,
    load_theme,
    set_active_theme,
)
from decoui.ui.help_window import HelpWindow
from decoui.ui.log_window import LogEntry, LogWindow
from decoui.ui.retheme import retheme_application
from decoui.ui.tag_bar import TagBar
from decoui.ui.tool_page import ToolPage

#: Two themes that disagree about as much as any two built-ins can: light is
#: mixed-case on a pale ground, nasa is uppercase on a dark one.
_FROM = "light"
_TO = "nasa"


@toolset(label="Retheme", tags=["demo"])
class _ThemeTools:
    """Tools used only as something to draw."""

    @tool(label="Echo", description="Prints what it is given.")
    def echo(self, text: str = "hi") -> None:
        """Print one line.

        Args:
            text: What to print.
        """
        print(text)

    @tool(label="Required")
    def required(self, needed: str) -> None:
        """Take a parameter with no default, so the form draws an asterisk.

        Args:
            needed: A value the form will mark as required.
        """

    @tool(label="Gated")
    def gated(self) -> None:
        """Block until the test lets it through, so a run can straddle a swap."""
        _GATE.wait(10)
        print("finished")


#: Held closed while a run is in flight, so the test can re-theme mid-run.
_GATE = threading.Event()


@pytest.fixture()
def app_theme(tmp_path: Path, qt_app: QApplication) -> Iterator[QApplication]:
    """Run one test under the light theme, with a throwaway database.

    The application stylesheet is restored afterwards: these tests set it for
    real, and leaving another theme's sheet installed would reach every test
    that runs after them.

    Yields:
        The Qt application, themed light.
    """
    set_db_path(tmp_path / "history.db")
    init_db()
    stylesheet = qt_app.styleSheet()
    font = qt_app.font()
    retheme_application(builtin_themes()[_FROM])
    yield qt_app
    set_active_theme(builtin_themes()[_FROM])
    qt_app.setStyleSheet(stylesheet)
    qt_app.setFont(font)


@pytest.fixture()
def recoloured(tmp_path: Path) -> Theme:
    """Return a theme that differs from light in the console's error colour.

    The four built-ins share all six console colours, so none of them can show
    that printed output was re-inked rather than left alone.

    Args:
        tmp_path: pytest's per-test directory, holding the theme file.

    Returns:
        A loaded theme, light in every respect but one.
    """
    path = tmp_path / "recoloured.json"
    path.write_text(json.dumps({
        "version": 1, "id": "recoloured", "name": "Recoloured",
        "extends": "light", "colors": {"console.error": "#00ccff"},
    }), encoding="utf-8")
    return load_theme(path)


def _info(label: str) -> ToolInfo:
    """Return one tool's metadata by label.

    Args:
        label: The tool's label.

    Returns:
        The matching ToolInfo.
    """
    return next(t for t in build_tree(_ThemeTools)[0].tools if t.label == label)


def _native(theme: Theme, build):
    """Build a widget under a theme, as a fresh launch would.

    Args:
        theme: The theme to build under.
        build: Zero-argument callable returning the widget.

    Returns:
        The widget, built while ``theme`` was the active one.
    """
    set_active_theme(theme)
    widget = build()
    set_active_theme(builtin_themes()[_FROM])
    return widget


# ── The page ──────────────────────────────────────────────────────────────────

def test_a_re_themed_page_matches_one_built_under_that_theme(
    app_theme: QApplication,
) -> None:
    """Verify re-theming leaves nothing of the old theme on a tool page."""
    info = _info("Echo")
    switched = ToolPage(info, _ThemeTools())
    native = _native(builtin_themes()[_TO], lambda: ToolPage(info, _ThemeTools()))

    retheme_application(builtin_themes()[_TO])

    assert switched._console.styleSheet() == native._console.styleSheet()
    assert switched._title.styleSheet() == native._title.styleSheet()
    assert switched._desc.styleSheet() == native._desc.styleSheet()
    assert switched._separator.styleSheet() == native._separator.styleSheet()
    assert switched._out_lbl.styleSheet() == native._out_lbl.styleSheet()
    assert switched._copy_btn.styleSheet() == native._copy_btn.styleSheet()


def test_the_required_asterisk_follows_the_theme(app_theme: QApplication) -> None:
    """Verify the marker inked inside rich text is re-inked too.

    It is drawn in a ``<span style>`` of its own, which no stylesheet reaches:
    left alone it would keep the previous theme's red on the new page.
    """
    info = _info("Required")
    switched = ToolPage(info, _ThemeTools())
    native = _native(builtin_themes()[_TO], lambda: ToolPage(info, _ThemeTools()))

    retheme_application(builtin_themes()[_TO])

    assert switched._required_labels[0][0].text() == native._required_labels[0][0].text()


def test_the_status_badge_keeps_its_state_and_takes_the_new_colours(
    app_theme: QApplication,
) -> None:
    """Verify a badge left over from a finished run is re-inked, not cleared.

    The badge is written when a run changes state and not touched again, so
    nothing else would ever repaint it -- the next run might be hours away.
    """
    page = ToolPage(_info("Echo"), _ThemeTools())
    page._set_status("success", "Done")

    native = _native(builtin_themes()[_TO], lambda: ToolPage(_info("Echo"), _ThemeTools()))
    native._set_status("success", "Done")

    retheme_application(builtin_themes()[_TO])

    assert page._status == "success"
    assert page._status_label.text() == "Done"
    assert page._status_label.styleSheet() == native._status_label.styleSheet()


def test_lines_already_printed_are_re_inked(
    app_theme: QApplication, recoloured: Theme
) -> None:
    """Verify console output written under the old theme takes the new colours.

    Half a console in the previous theme's palette is worse than either theme
    on its own, and the lines are the part a stylesheet cannot reach: their
    colour is a character format, written once as each line arrived.

    The theme here is written for the test rather than taken from the built-ins,
    which happen to agree on all six console colours -- against those, a page
    that re-inked nothing would pass.
    """
    page = ToolPage(_info("Echo"), _ThemeTools())
    page._append_log("ERROR", "it failed")
    assert _first_line_colour(page) == builtin_themes()[_FROM].colors["console.error"]

    retheme_application(recoloured)

    assert page._console.toPlainText() == "it failed\n"
    assert _first_line_colour(page) == recoloured.colors["console.error"]


def _first_line_colour(page: ToolPage) -> str:
    """Return the ink of the console's first character.

    Args:
        page: The page whose console to read.

    Returns:
        The colour as ``#rrggbb``.
    """
    cursor = page._console.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    cursor.movePosition(
        QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor
    )
    return cursor.charFormat().foreground().color().name()


def test_the_level_cache_is_refreshed_rather_than_abandoned(
    app_theme: QApplication,
) -> None:
    """Verify the per-line colour lookup stays a cache after a re-theme.

    The cache exists because rebuilding it per line put a file read and a full
    theme validation on the GUI thread for every line a tool printed. A
    re-theme has to refresh it, and must not be tempted to drop it.
    """
    page = ToolPage(_info("Echo"), _ThemeTools())

    retheme_application(builtin_themes()[_TO])

    assert page._level_colors == {
        level: builtin_themes()[_TO].colors[token]
        for level, token in {
            "stdout": "console.stdout",
            "DEBUG": "console.debug",
            "INFO": "console.info",
            "WARNING": "console.warning",
            "ERROR": "console.error",
            "CRITICAL": "console.critical",
        }.items()
    }


def test_nothing_is_rebuilt(app_theme: QApplication) -> None:
    """Verify a re-theme replaces no widget and discards no typed-in value.

    This is the whole reason the mechanism is a re-style pass: rebuilding the
    page would take the running tool and the half-filled form with it.
    """
    page = ToolPage(_info("Echo"), _ThemeTools())
    console, field = page._console, page._widgets["text"]
    field.setText("typed by hand")

    retheme_application(builtin_themes()[_TO])

    assert page._console is console
    assert page._widgets["text"] is field
    assert field.text() == "typed by hand"


def test_a_running_tool_is_not_interrupted(app_theme: QApplication) -> None:
    """Verify a run that straddles a theme change still finishes normally.

    This is the reason the mechanism re-styles rather than rebuilds. A rebuilt
    page would take the running tool's console, its status and its engine with
    it -- and the user pressing OK in Settings has no reason to expect that.
    """
    page = ToolPage(_info("Gated"), _ThemeTools())
    _GATE.clear()
    page._on_run()
    assert page._status == "running"

    retheme_application(builtin_themes()[_TO])
    assert page._status == "running"

    _GATE.set()
    assert QThreadPool.globalInstance().waitForDone(10_000)
    app_theme.processEvents()

    assert page._status == "success"
    assert "finished" in page._console.toPlainText()


# ── The top bar ───────────────────────────────────────────────────────────────

def test_a_re_themed_tag_bar_matches_one_built_under_that_theme(
    app_theme: QApplication,
) -> None:
    """Verify the band and the pills both follow.

    Neither survives a stylesheet swap on its own: the band is painted onto
    three widgets explicitly to beat the generic QWidget rule, and the pills
    carry their own rules because they are the one fully-rounded control.
    """
    switched = TagBar(["alpha", "beta"])
    native = _native(builtin_themes()[_TO], lambda: TagBar(["alpha", "beta"]))

    retheme_application(builtin_themes()[_TO])

    assert switched._label.styleSheet() == native._label.styleSheet()
    assert switched._scroll.styleSheet() == native._scroll.styleSheet()
    assert switched._scroll.viewport().styleSheet() == native._scroll.viewport().styleSheet()
    assert switched._container.styleSheet() == native._container.styleSheet()
    assert switched._all_btn.styleSheet() == native._all_btn.styleSheet()
    assert switched._buttons["alpha"].styleSheet() == native._buttons["alpha"].styleSheet()


# ── Capitals ──────────────────────────────────────────────────────────────────

def test_capitals_arrive_with_a_theme_that_asks_for_them(
    app_theme: QApplication,
) -> None:
    """Verify switching to an uppercase theme capitalises the controls."""
    bar = TagBar(["alpha"])
    bar.show()

    retheme_application(builtin_themes()[_TO])

    assert _capitalisation(bar) == QFont.Capitalization.AllUppercase


def test_capitals_are_undone_by_a_theme_that_does_not(
    app_theme: QApplication,
) -> None:
    """Verify going back to a mixed-case theme takes the capitals away again.

    Qt has no ``text-transform``, so capitals go through the widget font --
    which keeps whatever was last written to it. Setting only the uppercase
    case would make the change one-way: every theme after the first uppercase
    one would inherit its capitals.
    """
    bar = TagBar(["alpha"])
    bar.show()
    retheme_application(builtin_themes()[_TO])

    retheme_application(builtin_themes()[_FROM])

    assert _capitalisation(bar) == QFont.Capitalization.MixedCase


def _capitalisation(bar: TagBar) -> QFont.Capitalization:
    """Return the case a bar's pills are rendered in.

    Args:
        bar: The tag bar to inspect.

    Returns:
        The capitalization of its first pill's font.
    """
    return bar.findChildren(QPushButton)[0].font().capitalization()


# ── The other windows ─────────────────────────────────────────────────────────

def test_an_open_log_window_follows(app_theme: QApplication) -> None:
    """Verify a log window open at the time is re-themed with everything else.

    Two themes on screen at once is worse than either, and this window is
    top-level: it is not inside the main window's tree and would be missed by
    anything that only walked from there.
    """
    switched = LogWindow("Run", [LogEntry("INFO", "line")])
    native = _native(
        builtin_themes()[_TO], lambda: LogWindow("Run", [LogEntry("INFO", "line")])
    )
    switched.show()

    retheme_application(builtin_themes()[_TO])

    assert switched._console.styleSheet() == native._console.styleSheet()
    switched.close()
    native.close()


def test_an_open_help_window_follows(app_theme: QApplication) -> None:
    """Verify the help page is re-rendered under the new theme.

    QTextBrowser does not read the application stylesheet: the theme's colours
    are inlined into each document, so the page has to be built again. What is
    checked is the ink -- comparing Qt's own HTML serialisation against a
    natively built window fails on font-resolution detail that never reaches
    the screen.
    """
    old_ink = builtin_themes()[_FROM].colors["text.primary"].lower()
    new_ink = builtin_themes()[_TO].colors["text.primary"].lower()
    assert old_ink != new_ink

    switched = HelpWindow(build_tree(_ThemeTools))
    switched.show()
    assert old_ink in switched._tabs.currentWidget().toHtml().lower()

    retheme_application(builtin_themes()[_TO])

    rendered = switched._tabs.currentWidget().toHtml().lower()
    assert new_ink in rendered
    assert old_ink not in rendered
    switched.close()


# ── The application itself ────────────────────────────────────────────────────

def test_the_application_stylesheet_and_font_are_replaced(
    app_theme: QApplication,
) -> None:
    """Verify the global half of the swap happens, not only the per-widget half."""
    from decoui.theme import render_stylesheet

    target = builtin_themes()[_TO]

    retheme_application(target)

    assert app_theme.styleSheet() == render_stylesheet(target)
    assert app_theme.font().families() == list(target.font.family)
    assert active_theme().id == _TO
