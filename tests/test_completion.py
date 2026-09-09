"""Tests for the autocomplete controller."""

from __future__ import annotations

from typing import Any

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFocusEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCompleter, QLineEdit

from decoui.assist import CompletionController, InlineRunner


@pytest.fixture()
def line_edit(qt_app: QApplication) -> QLineEdit:
    """Provide a focused line edit for completer tests.

    Args:
        qt_app: The shared QApplication.

    Returns:
        A visible QLineEdit ready to receive a completer.
    """
    widget = QLineEdit()
    widget.show()
    return widget


def _controller(
    line_edit: QLineEdit,
    spec: Any,
    debounce_ms: int = 0,
    form: dict[str, Any] | None = None,
) -> CompletionController:
    """Build a controller wired to the inline (synchronous) runner.

    Args:
        line_edit: The widget under test.
        spec: A static list or a lookup callback.
        debounce_ms: Debounce interval; 0 dispatches on every keystroke.
        form: Form snapshot handed to the callback.

    Returns:
        The configured controller.
    """
    return CompletionController(
        param_name="service",
        line_edit=line_edit,
        spec=spec,
        instance=None,
        form_reader=lambda: dict(form or {}),
        debounce_ms=debounce_ms,
        runner=InlineRunner(),
    )


def test_static_list_populates_the_completer(line_edit: QLineEdit) -> None:
    """Verify a static list is installed as a Qt-filtered completer."""
    controller = _controller(line_edit, ["prod", "staging", "dev"])

    assert controller.is_dynamic is False
    assert controller.candidates() == ["prod", "staging", "dev"]
    assert line_edit.completer() is not None
    assert (
        line_edit.completer().completionMode()
        is QCompleter.CompletionMode.PopupCompletion
    )


def test_dynamic_callback_receives_text_and_form(line_edit: QLineEdit) -> None:
    """Verify a lookup callback is called with the typed text and form snapshot."""
    seen: list[tuple[str, dict[str, Any]]] = []

    def lookup(text: str, form: dict[str, Any]) -> list[str]:
        seen.append((text, form))
        return [text + "-1", text + "-2"]

    controller = _controller(line_edit, lookup, form={"env": "prod"})
    line_edit.setText("web")
    line_edit.textEdited.emit("web")

    assert seen == [("web", {"env": "prod"})]
    assert controller.candidates() == ["web-1", "web-2"]
    assert (
        line_edit.completer().completionMode()
        is QCompleter.CompletionMode.UnfilteredPopupCompletion
    )


def test_dynamic_lookup_is_debounced(line_edit: QLineEdit) -> None:
    """Verify fast consecutive keystrokes produce a single lookup."""
    calls: list[str] = []
    controller = _controller(line_edit, lambda text: calls.append(text) or [], debounce_ms=80)

    for text in ("a", "ab", "abc"):
        line_edit.setText(text)
        line_edit.textEdited.emit(text)

    assert calls == []

    QTest.qWait(200)

    assert calls == ["abc"]
    assert controller.is_dynamic is True


def test_repeated_text_is_served_from_cache(line_edit: QLineEdit) -> None:
    """Verify the same query text does not hit the callback twice."""
    calls: list[str] = []

    def lookup(text: str) -> list[str]:
        calls.append(text)
        return ["hit"]

    controller = _controller(line_edit, lookup)
    for _ in range(3):
        line_edit.setText("web")
        line_edit.textEdited.emit("web")

    assert calls == ["web"]
    assert controller.candidates() == ["hit"]


def test_cache_is_dropped_when_another_field_changes(line_edit: QLineEdit) -> None:
    """Verify invalidate_cache forces a fresh lookup for the same text."""
    calls: list[str] = []
    controller = _controller(line_edit, lambda text: calls.append(text) or ["hit"])

    line_edit.setText("web")
    line_edit.textEdited.emit("web")
    controller.invalidate_cache()
    line_edit.textEdited.emit("web")

    assert calls == ["web", "web"]


def test_stale_results_are_discarded(line_edit: QLineEdit) -> None:
    """Verify a result that a newer keystroke superseded never reaches the model."""
    controller = _controller(line_edit, lambda text: ["fresh"])
    line_edit.setText("new")
    line_edit.textEdited.emit("new")

    # Replay an older in-flight request that finished late.
    controller._pending[0] = "old"
    controller._on_finished(0, ["stale"], 0.0)

    assert controller.candidates() == ["fresh"]


def test_failing_callback_keeps_previous_candidates(line_edit: QLineEdit) -> None:
    """Verify a raising lookup warns once and leaves the popup contents intact."""
    warnings: list[str] = []
    should_fail = False

    def lookup(text: str) -> list[str]:
        if should_fail:
            raise RuntimeError("backend down")
        return ["ok"]

    controller = _controller(line_edit, lookup)
    controller.failed.connect(warnings.append)

    line_edit.setText("a")
    line_edit.textEdited.emit("a")
    assert controller.candidates() == ["ok"]

    should_fail = True
    line_edit.setText("b")
    line_edit.textEdited.emit("b")

    assert controller.candidates() == ["ok"]
    assert len(warnings) == 1
    assert "backend down" in warnings[0]


def test_non_iterable_result_is_reported(line_edit: QLineEdit) -> None:
    """Verify a scalar callback result warns instead of corrupting the model."""
    warnings: list[str] = []
    controller = _controller(line_edit, lambda text: 42)
    controller.failed.connect(warnings.append)

    line_edit.textEdited.emit("a")

    assert controller.candidates() == []
    assert len(warnings) == 1
    assert "invalid result" in warnings[0]


def test_suspended_controller_performs_no_lookup(line_edit: QLineEdit) -> None:
    """Verify lookups stop while the tool is running."""
    calls: list[str] = []
    controller = _controller(line_edit, lambda text: calls.append(text) or [])

    line_edit.setText("a")
    controller.set_suspended(True)
    line_edit.textEdited.emit("a")
    assert calls == []

    controller.set_suspended(False)
    line_edit.textEdited.emit("a")
    assert calls == ["a"]


def _focus_in(line_edit: QLineEdit, reason: Qt.FocusReason) -> None:
    """Deliver a focus-in event with a specific reason.

    Args:
        line_edit: The widget receiving focus.
        reason: The focus reason to report.
    """
    QApplication.sendEvent(line_edit, QFocusEvent(QEvent.Type.FocusIn, reason))


def test_entering_an_empty_field_requests_candidates(line_edit: QLineEdit) -> None:
    """Verify clicking into a field offers candidates before anything is typed."""
    calls: list[str] = []
    controller = _controller(line_edit, lambda text: calls.append(text) or ["a", "b"])

    _focus_in(line_edit, Qt.FocusReason.MouseFocusReason)

    assert calls == [""]
    assert controller.candidates() == ["a", "b"]


def test_entering_a_filled_field_offers_the_full_list(line_edit: QLineEdit) -> None:
    """Verify re-entering a filled field is not narrowed by the existing value."""
    calls: list[str] = []
    _controller(line_edit, lambda text: calls.append(text) or [])

    line_edit.setText("web")
    _focus_in(line_edit, Qt.FocusReason.TabFocusReason)

    assert calls == [""]


def test_popup_focus_does_not_reopen_the_popup(line_edit: QLineEdit) -> None:
    """Verify the popup opening or closing never triggers another lookup.

    Without this guard the popup would reopen itself in a loop, since showing it
    hands focus back to the line edit.
    """
    calls: list[str] = []
    _controller(line_edit, lambda text: calls.append(text) or ["a"])

    _focus_in(line_edit, Qt.FocusReason.PopupFocusReason)
    _focus_in(line_edit, Qt.FocusReason.ActiveWindowFocusReason)

    assert calls == []


def test_static_list_opens_unfiltered_on_focus(line_edit: QLineEdit) -> None:
    """Verify a static list offers every option on entry, not just matches."""
    controller = _controller(line_edit, ["prod", "staging", "dev"])

    line_edit.setText("d")
    _focus_in(line_edit, Qt.FocusReason.MouseFocusReason)

    completer = line_edit.completer()
    assert completer.completionPrefix() == ""
    assert completer.completionCount() == 3
    assert controller.candidates() == ["prod", "staging", "dev"]


def test_suspended_controller_ignores_focus(line_edit: QLineEdit) -> None:
    """Verify entering a field while the tool runs performs no lookup."""
    calls: list[str] = []
    controller = _controller(line_edit, lambda text: calls.append(text) or [])

    controller.set_suspended(True)
    _focus_in(line_edit, Qt.FocusReason.MouseFocusReason)

    assert calls == []


def test_candidates_are_normalized(line_edit: QLineEdit) -> None:
    """Verify duplicates are dropped and non-strings coerced before display."""
    controller = _controller(line_edit, lambda text: ["b", "b", 7, "a"])

    line_edit.textEdited.emit("x")

    assert controller.candidates() == ["b", "7", "a"]
