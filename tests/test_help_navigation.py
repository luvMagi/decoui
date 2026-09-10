"""Tests for cross-references, tabs and history in the Help window.

Three mechanisms that only make sense together. A page is addressed by a key,
the same key a tab, a history entry and a written link all use; opening a page
gives it a tab, as the main window does for a tool; and back and forward walk
the pages actually visited, **across** tabs rather than inside one -- with a
tab per page there is nothing for a per-tab history to hold.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

import decoui.guide
from decoui import tool, toolset
from decoui.guide import guide_pages
from decoui.registry import build_tree
from decoui.theme import builtin_themes, set_active_theme
from decoui.markup import LINK_SCHEME, inline
from decoui.ui.help_window import _HELP_ROLE, HelpWindow
from decoui.ui.retheme import retheme_application


@toolset(label="Text Tools", tags=["text"])
class _TextTools:
    """Utilities for strings.

    Read [Themes](guide.themes) for how this panel is coloured, and
    [Encode](_TextTools.encode) for the one everybody uses. [Gone](No.Such.Key)
    names nothing and must stay prose.
    """

    @tool(label="Encode Text")
    def encode(self, text: str) -> str:
        """Encode a string.

        Args:
            text: What to encode.
        """

    @tool(label="Decode Text")
    def decode(self, text: str) -> str:
        """Decode a string.

        Args:
            text: What to decode.
        """


@pytest.fixture()
def window(qt_app: QApplication) -> Iterator[HelpWindow]:
    """Show a themed help window over one toolset.

    Yields:
        The window, opened on decoui's own contents page.
    """
    stylesheet, font = qt_app.styleSheet(), qt_app.font()
    retheme_application(builtin_themes()["light"])
    win = HelpWindow(build_tree(_TextTools))
    win.resize(940, 660)
    win.show()
    yield win
    win.close()
    set_active_theme(builtin_themes()["light"])
    qt_app.setStyleSheet(stylesheet)
    qt_app.setFont(font)


def _titles(window: HelpWindow) -> list[str]:
    """Return the open tabs' labels, left to right.

    Args:
        window: The window to read.

    Returns:
        One title per tab.
    """
    return [window._tabs.tabText(i) for i in range(window._tabs.count())]


# ── Writing a reference ───────────────────────────────────────────────────────

def test_a_reference_to_a_known_page_becomes_a_link() -> None:
    """Verify ``[[key]]`` renders as an anchor under decoui's own scheme."""
    rendered = inline("see [[guide.themes]]", frozenset({"guide.themes"}))

    assert f'href="{LINK_SCHEME}:guide.themes"' in rendered
    assert ">guide.themes</a>" in rendered


def test_a_reference_may_be_given_its_own_text() -> None:
    """Verify ``[[key|label]]`` shows the label and links the key."""
    rendered = inline("see [[guide.themes|Themes]]", frozenset({"guide.themes"}))

    assert f'href="{LINK_SCHEME}:guide.themes"' in rendered
    assert ">Themes</a>" in rendered


def test_a_reference_to_an_unknown_page_stays_prose() -> None:
    """Verify an unresolvable target degrades to its own text.

    Which tools exist is up to the application that loaded them, so a guide
    cannot be written against a fixed set. A link that goes nowhere is worse
    than the sentence without it.
    """
    rendered = inline("see [[no.such.key|Gone]]", frozenset({"guide.themes"}))

    assert rendered == "see Gone"
    assert "<a" not in rendered


def test_a_reference_may_carry_markup_of_its_own() -> None:
    """Verify the link text goes through the same inline pass."""
    rendered = inline("[[guide.themes|**loud**]]", frozenset({"guide.themes"}))

    assert "<b>loud</b></a>" in rendered


def test_decouis_own_guide_pages_reference_nothing_that_is_missing() -> None:
    """Verify every link shipped in the guide resolves, in every language.

    The pages are prose in twelve directories and nothing else checks them. A
    typo would not raise -- it would quietly render as plain text, which is
    exactly the failure that is hard to notice.
    """
    known = {page.page_id for page in guide_pages()} | {"guide"}
    pattern = re.compile(r"\[[^\]\n]+\]\((?P<target>[A-Za-z_][\w.]*)\)")
    package = Path(decoui.guide.__file__).parent

    dangling = [
        f"{path.parent.name}/{path.name}: {match.group('target')}"
        for path in sorted(package.rglob("*.md"))
        for match in pattern.finditer(path.read_text(encoding="utf-8"))
        # Only guide keys are checkable here: a tool key depends on which
        # application loaded which toolsets, and decoui's own pages have no
        # business naming one anyway.
        if match.group("target").startswith("guide")
        and match.group("target") not in known
    ]
    assert not dangling


# ── Tabs ──────────────────────────────────────────────────────────────────────

def test_the_window_opens_on_the_guide(window: HelpWindow) -> None:
    """Verify a reader meets decoui's own pages before anybody's tools."""
    assert window._current_key() == "guide"
    assert window._tabs.count() == 1


def test_each_page_opens_in_its_own_tab(window: HelpWindow) -> None:
    """Verify pages accumulate as tabs, the way the main window opens tools."""
    window._tree.setCurrentItem(window._tree.topLevelItem(1))      # the toolset
    window._navigate("_TextTools.encode")

    assert window._tabs.count() == 3
    assert _titles(window) == ["Using decoui", "Text Tools", "Encode Text"]


def test_reopening_a_page_raises_its_tab_instead_of_duplicating_it(
    window: HelpWindow,
) -> None:
    """Verify one page never occupies two tabs."""
    window._navigate("_TextTools.encode")
    window._navigate("guide")
    window._navigate("_TextTools.encode")

    assert _titles(window).count("Encode Text") == 1
    assert window._current_key() == "_TextTools.encode"


def test_filtering_the_tree_opens_nothing(window: HelpWindow) -> None:
    """Verify typing in the search box does not spawn tabs.

    Filtering is how a reader looks for something. A tab per keystroke is not
    what they asked for, and it would bury what they were already reading.
    """
    before = window._tabs.count()

    window._search.setText("decode")

    assert window._tabs.count() == before


# ── Following a link ──────────────────────────────────────────────────────────

def test_a_link_opens_its_target_and_moves_the_tree(window: HelpWindow) -> None:
    """Verify the three views stay in step when a link is followed."""
    window._follow(QUrl(f"{LINK_SCHEME}:guide.themes"))

    assert window._current_key() == "guide.themes"
    assert window._tree.currentItem().data(0, _HELP_ROLE) == "guide.themes"


def test_a_link_to_anything_but_decouis_own_scheme_is_ignored(
    window: HelpWindow,
) -> None:
    """Verify an http link written into a docstring cannot navigate anywhere.

    Prose reaches the renderer from tools decoui did not write. Following an
    arbitrary URL from there would make a docstring a way to reach the network.
    """
    before = window._current_key()

    window._follow(QUrl("https://example.com"))

    assert window._current_key() == before


# ── History ───────────────────────────────────────────────────────────────────

def test_back_returns_across_tabs(window: HelpWindow) -> None:
    """Verify back walks the pages visited, not the current tab's own history."""
    window._navigate("_TextTools")
    window._navigate("guide.themes")

    window._go_back()

    assert window._current_key() == "_TextTools"


def test_forward_undoes_a_back_step(window: HelpWindow) -> None:
    """Verify the pair is symmetric."""
    window._navigate("_TextTools")
    window._go_back()

    window._go_forward()

    assert window._current_key() == "_TextTools"


def test_back_reopens_a_tab_that_was_closed(window: HelpWindow) -> None:
    """Verify closing a tab does not erase where the reader has been."""
    window._navigate("_TextTools")
    window._navigate("guide.themes")
    window._close_tab(window._tabs.indexOf(window._open_tabs["_TextTools"]))
    assert "_TextTools" not in window._open_tabs

    window._go_back()

    assert window._current_key() == "_TextTools"
    assert "_TextTools" in window._open_tabs


def test_a_new_visit_drops_the_forward_trail(window: HelpWindow) -> None:
    """Verify forward means "the way I came back from", not "somewhere I saw"."""
    window._navigate("_TextTools")
    window._navigate("guide.themes")
    window._go_back()

    window._navigate("_TextTools.encode")

    assert not window._forward_btn.isEnabled()


def test_the_arrows_are_disabled_where_there_is_nowhere_to_go(
    window: HelpWindow,
) -> None:
    """Verify the buttons say whether they will do anything."""
    assert not window._back_btn.isEnabled()
    assert not window._forward_btn.isEnabled()

    window._navigate("_TextTools")

    assert window._back_btn.isEnabled()
    assert not window._forward_btn.isEnabled()


# ── Colour ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("theme_id", sorted(builtin_themes()))
def test_links_are_inked_with_the_theme_token(
    window: HelpWindow, theme_id: str
) -> None:
    """Verify a link takes ``text.link`` rather than Qt's default anchor blue.

    Checked on the laid-out document, not on the stylesheet: QTextBrowser can
    ink an anchor from its palette instead, and a CSS rule that loses that
    argument is invisible in the HTML.

    Args:
        window: The help window.
        theme_id: The built-in theme under test.
    """
    theme = builtin_themes()[theme_id]
    retheme_application(theme)
    page = window._tabs.currentWidget()
    page.setHtml(window._wrap(f'<p><a href="{LINK_SCHEME}:guide">a link</a></p>'))

    cursor = QTextCursor(page.document())
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    cursor.movePosition(
        QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor
    )

    assert cursor.charFormat().isAnchor()
    assert cursor.charFormat().foreground().color().name().lower() == (
        theme.colors["text.link"].lower()
    )
