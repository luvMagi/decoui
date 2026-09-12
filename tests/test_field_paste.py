"""Tests that a form field takes text from the clipboard and nothing else.

The output console colours each line by level, and a selection copied out of it
reaches the clipboard as ``text/html`` alongside the plain text. A QTextEdit
accepts rich text by default, so pasting such a line back into a list or dict
field -- to re-run with an id the log just printed -- reproduced the console's
ink on the form's background. Under a light theme a white line landed on a white
field and was simply not there.

The value was never affected: fields are read back with ``toPlainText()``. Only
what the user could see was. These tests pin the paste behaviour rather than any
particular colour, because a theme cannot fix this and must not be asked to.
"""

from __future__ import annotations

import inspect

import pytest
from PySide6.QtCore import QMimeData
from PySide6.QtWidgets import QApplication, QTextEdit

from decoui.registry import ParamInfo
from decoui.widget_builder import build_widget, get_value

#: One coloured line, shaped the way the console puts it on the clipboard.
_CONSOLE_HTML = (
    '<pre style="white-space:pre-wrap">'
    '<span style="color:#ffffff">12:00:00 build-4711</span>'
    "</pre>"
)
_CONSOLE_TEXT = "12:00:00 build-4711"


def _field(annotation) -> QTextEdit:
    """Build the form widget for one annotation.

    Args:
        annotation: The parameter's type, as the registry would have stripped it.

    Returns:
        The widget build_widget() chose for it.
    """
    return build_widget(ParamInfo(
        name="items",
        annotation=annotation,
        default=inspect.Parameter.empty,
        has_default=False,
    ))


def _paste(widget: QTextEdit, html: str, text: str) -> None:
    """Put html-and-text on the clipboard and paste it into a widget.

    Both flavours are set because that is what a copy out of the console
    produces, and a field that reads the wrong one is the whole bug.

    Args:
        widget: The field to paste into.
        html: The ``text/html`` flavour.
        text: The ``text/plain`` flavour.
    """
    mime = QMimeData()
    mime.setHtml(html)
    mime.setText(text)
    QApplication.clipboard().setMimeData(mime)
    widget.paste()


@pytest.mark.parametrize("annotation", [list, list[str], dict])
def test_multiline_fields_refuse_rich_text(qt_app, annotation) -> None:
    """Verify every QTextEdit the builder produces has rich text switched off.

    This is the property, and it covers drops as well as pastes: both arrive
    through insertFromMimeData().
    """
    assert _field(annotation).acceptRichText() is False


def test_a_pasted_console_line_keeps_its_text(qt_app) -> None:
    """Verify the characters survive the paste even though the markup does not."""
    field = _field(list[str])

    _paste(field, _CONSOLE_HTML, _CONSOLE_TEXT)

    assert field.toPlainText() == _CONSOLE_TEXT


def test_a_pasted_console_line_loses_its_colour(qt_app) -> None:
    """Verify the console's ink does not follow the text into the field.

    The document's own HTML is where a surviving colour would show up, so that
    is what is inspected -- asserting on the rendered pixels would tie the test
    to whichever theme happened to be active.
    """
    field = _field(list[str])

    _paste(field, _CONSOLE_HTML, _CONSOLE_TEXT)

    assert "#ffffff" not in field.toHtml().lower()


def test_a_pasted_line_reads_back_as_an_ordinary_value(qt_app) -> None:
    """Verify the paste produces a value, not just visible text.

    A list field splits on newlines and commas; a line pasted from the console
    has to come back as one item like any typed one.
    """
    field = _field(list[str])

    _paste(field, _CONSOLE_HTML, _CONSOLE_TEXT)

    assert get_value(field) == [_CONSOLE_TEXT]
