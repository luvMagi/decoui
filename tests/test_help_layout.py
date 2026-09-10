"""Regression tests for the Help window's vertical rhythm.

The help pages are HTML rendered by QTextBrowser, and the one thing that has
to hold is an ordering, not a number: **a paragraph must be further from the
next paragraph than its own lines are from each other.** Get that backwards and
the blank line between two paragraphs stops reading as a break -- the page
becomes one undifferentiated block of text, which is what ``p { margin: 6px }``
did against a 145% line height.

The numbers themselves are left to the stylesheet. What is asserted here is the
hierarchy: line < list item < paragraph < section heading.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication

from decoui.theme import builtin_themes, set_active_theme
from decoui.ui.help_window import HelpWindow
from decoui.ui.retheme import retheme_application

#: Long enough to wrap at the window's width, so the block has an inside.
_LONG = (
    "This paragraph has to be long enough that it wraps onto a second line, "
    "because the whole question is whether the space between two paragraphs is "
    "larger than the space between the lines within one of them."
)


@pytest.fixture()
def window(qt_app: QApplication) -> Iterator[HelpWindow]:
    """Show a themed, empty help window ready to be handed HTML.

    Yields:
        The window; its stylesheet is restored to the caller's afterwards.
    """
    stylesheet, font = qt_app.styleSheet(), qt_app.font()
    retheme_application(builtin_themes()["light"])
    # An empty toolset tree still opens on decoui's own guide, so the window
    # always has a tab to lay HTML out in.
    win = HelpWindow([])
    win.resize(940, 660)
    win.show()
    yield win
    win.close()
    set_active_theme(builtin_themes()["light"])
    qt_app.setStyleSheet(stylesheet)
    qt_app.setFont(font)


def _blocks(window: HelpWindow, body: str) -> list[tuple[float, float, float, int]]:
    """Lay out one page and report each block's geometry.

    Args:
        window: The window whose renderer and theme to use.
        body: Inner HTML for the page.

    Returns:
        One ``(top, bottom, height, lines)`` per block, in document order. The
        line count is what turns a block's height into a line height -- a
        sample paragraph does not wrap onto a predictable number of lines.
    """
    page = window._tabs.currentWidget()
    page.setHtml(window._wrap(body))
    doc = page.document()
    doc.setTextWidth(page.viewport().width())
    layout = doc.documentLayout()
    out = []
    block = doc.begin()
    while block.isValid():
        rect = layout.blockBoundingRect(block)
        out.append((rect.top(), rect.bottom(), rect.height(), block.layout().lineCount()))
        block = block.next()
    return out


def test_paragraphs_stand_further_apart_than_their_own_lines(
    window: HelpWindow,
) -> None:
    """Verify the gap between paragraphs clears the line spacing inside one.

    Below that threshold the break is invisible: readers see evenly spaced
    lines and no paragraphs at all.
    """
    first, second = _blocks(window, f"<p>{_LONG}</p><p>{_LONG}</p>")

    assert first[3] > 1, "the sample paragraph did not wrap; widen the window"
    line_height = first[2] / first[3]
    gap = second[0] - first[1]

    assert gap >= line_height


def test_list_items_stay_tighter_than_paragraphs(window: HelpWindow) -> None:
    """Verify a list reads as one thing rather than as more paragraphs.

    Items packed as loosely as paragraphs make the list dissolve into the prose
    around it, which is the same failure seen from the other side.
    """
    blocks = _blocks(
        window, f"<p>{_LONG}</p><ul><li>first item</li><li>second item</li></ul>"
    )
    paragraph, item_one, item_two = blocks[0], blocks[1], blocks[2]

    between_items = item_two[0] - item_one[1]
    before_list = item_one[0] - paragraph[1]

    assert between_items < before_list


def test_a_section_heading_opens_more_space_than_a_paragraph_break(
    window: HelpWindow,
) -> None:
    """Verify sections separate more strongly than the paragraphs inside them."""
    blocks = _blocks(window, f"<p>{_LONG}</p><p>{_LONG}</p><h2>Section</h2><p>{_LONG}</p>")
    para_one, para_two, heading = blocks[0], blocks[1], blocks[2]

    paragraph_gap = para_two[0] - para_one[1]
    heading_gap = heading[0] - para_two[1]

    assert heading_gap > paragraph_gap
