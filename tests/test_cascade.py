"""Tests for cascading fill and lazily evaluated defaults."""

from __future__ import annotations

from typing import Any

import pytest
from PySide6.QtWidgets import QApplication

from decoui import tool, toolset
from decoui.assist import MAX_CASCADE_DEPTH, InlineRunner
from decoui.registry import build_tree
from decoui.ui.tool_page import ToolPage


def _page(cls: type, qt_app: QApplication) -> ToolPage:
    """Build a ToolPage for a toolset class holding exactly one tool.

    Args:
        cls: A class decorated with @toolset.
        qt_app: The shared QApplication.

    Returns:
        A ToolPage whose assist callbacks run synchronously.
    """
    info = build_tree(cls)[0].tools[0]
    return ToolPage(info, cls(), assist_runner=InlineRunner())


def _warnings(page: ToolPage) -> list[str]:
    """Return the WARNING lines the page has logged.

    Args:
        page: The page under test.

    Returns:
        Messages logged at WARNING level.
    """
    return [entry.message for entry in page._log_records if entry.level == "WARNING"]


# ── Fixtures: toolsets under test ────────────────────────────────────────────

@toolset(label="Deploy Tools")
class DeployTools:
    """Toolset exercising a single source with two derived targets."""

    calls: list[str] = []

    @tool(
        label="Deploy",
        cascade={"service": "on_service_changed"},
    )
    def deploy(self, service: str = "", version: str = "", owner: str = "") -> None:
        """Placeholder tool body; the test only drives the form."""

    def on_service_changed(self, value: str, form: dict[str, Any]) -> dict[str, str]:
        """Return derived fields for the chosen service.

        Args:
            value: The committed service name.
            form: Snapshot of the whole form.

        Returns:
            Values for the version and owner fields.
        """
        DeployTools.calls.append(value)
        return {"version": f"{value}-1.0", "owner": f"{value}-team"}


@toolset(label="Chain Tools")
class ChainTools:
    """Toolset whose fields cascade in a straight line a -> b -> ... -> f."""

    calls: list[str] = []

    @tool(
        label="Chain",
        cascade={
            "a": lambda value: {"b": value + "b"},
            "b": lambda value: {"c": value + "c"},
            "c": lambda value: {"d": value + "d"},
            "d": lambda value: {"e": value + "e"},
            "e": lambda value: {"f": value + "f"},
            "f": lambda value: {"g": value + "g"},
        },
    )
    def chain(
        self,
        a: str = "",
        b: str = "",
        c: str = "",
        d: str = "",
        e: str = "",
        f: str = "",
        g: str = "",
    ) -> None:
        """Placeholder tool body; the test only drives the form."""


@toolset(label="Cycle Tools")
class CycleTools:
    """Toolset where two fields cascade into each other."""

    calls: list[str] = []

    @tool(
        label="Cycle",
        cascade={"a": "from_a", "b": "from_b"},
    )
    def cycle(self, a: str = "", b: str = "") -> None:
        """Placeholder tool body; the test only drives the form."""

    def from_a(self, value: str) -> dict[str, str]:
        """Write into b when a changes.

        Args:
            value: The committed value of a.

        Returns:
            A new value for b.
        """
        CycleTools.calls.append(f"a={value}")
        return {"b": value + "-b"}

    def from_b(self, value: str) -> dict[str, str]:
        """Write back into a when b changes.

        Args:
            value: The committed value of b.

        Returns:
            A new value for a.
        """
        CycleTools.calls.append(f"b={value}")
        return {"a": value + "-a"}


@pytest.fixture(autouse=True)
def _reset_call_logs() -> None:
    """Clear the per-class call logs before each test."""
    DeployTools.calls = []
    ChainTools.calls = []
    CycleTools.calls = []


# ── Cascade behaviour ─────────────────────────────────────────────────────────

def test_commit_fills_derived_fields(qt_app: QApplication) -> None:
    """Verify committing a source writes every returned target."""
    page = _page(DeployTools, qt_app)

    page._widgets["service"].setText("web")
    page._widgets["service"].editingFinished.emit()

    assert page._widgets["version"].text() == "web-1.0"
    assert page._widgets["owner"].text() == "web-team"
    assert DeployTools.calls == ["web"]


def test_unchanged_commit_does_not_fire(qt_app: QApplication) -> None:
    """Verify tabbing through an untouched field triggers no lookup."""
    page = _page(DeployTools, qt_app)

    page._widgets["service"].editingFinished.emit()
    page._widgets["service"].setText("web")
    page._widgets["service"].editingFinished.emit()
    page._widgets["service"].editingFinished.emit()

    assert DeployTools.calls == ["web"]


def test_clearing_a_field_still_cascades(qt_app: QApplication) -> None:
    """Verify emptying a source is a real change that updates derived fields."""
    page = _page(DeployTools, qt_app)

    page._widgets["service"].setText("web")
    page._widgets["service"].editingFinished.emit()
    page._widgets["service"].setText("")
    page._widgets["service"].editingFinished.emit()

    assert DeployTools.calls == ["web", ""]
    assert page._widgets["version"].text() == "-1.0"


def test_chained_cascade_stops_at_the_depth_limit(qt_app: QApplication) -> None:
    """Verify a long chain propagates but is cut off with a warning."""
    page = _page(ChainTools, qt_app)

    page._widgets["a"].setText("x")
    page._widgets["a"].editingFinished.emit()

    # 'a' runs at depth 0, so five callbacks run (a..e) and 'f' is written as a
    # target but never dispatched as a source.
    assert page._widgets["f"].text() == "xbcdef"
    assert page._widgets["g"].text() == ""
    warnings = _warnings(page)
    assert len(warnings) == 1
    assert f"exceeded {MAX_CASCADE_DEPTH} levels" in warnings[0]


def test_cycle_terminates_after_one_round(qt_app: QApplication) -> None:
    """Verify a -> b -> a settles instead of looping forever."""
    page = _page(CycleTools, qt_app)

    page._widgets["a"].setText("x")
    page._widgets["a"].editingFinished.emit()

    assert CycleTools.calls == ["a=x", "b=x-b"]
    assert page._widgets["a"].text() == "x-b-a"
    assert page._widgets["b"].text() == "x-b"


def test_unknown_target_is_dropped_with_a_warning(qt_app: QApplication) -> None:
    """Verify known targets still apply when the callback names a missing one."""

    @toolset(label="Partial Tools")
    class PartialTools:

        @tool(label="Partial", cascade={"a": lambda value: {"b": "ok", "ghost": "x"}})
        def partial(self, a: str = "", b: str = "") -> None:
            """Placeholder tool body; the test only drives the form."""

    page = _page(PartialTools, qt_app)
    page._widgets["a"].setText("go")
    page._widgets["a"].editingFinished.emit()

    assert page._widgets["b"].text() == "ok"
    assert any("ghost" in message for message in _warnings(page))


def test_non_dict_result_is_reported(qt_app: QApplication) -> None:
    """Verify a callback returning the wrong shape warns and writes nothing."""

    @toolset(label="Bad Tools")
    class BadTools:

        @tool(label="Bad", cascade={"a": lambda value: ["not", "a", "dict"]})
        def bad(self, a: str = "", b: str = "") -> None:
            """Placeholder tool body; the test only drives the form."""

    page = _page(BadTools, qt_app)
    page._widgets["a"].setText("go")
    page._widgets["a"].editingFinished.emit()

    assert page._widgets["b"].text() == ""
    assert any("expected a dict" in message for message in _warnings(page))


def test_raising_callback_is_reported(qt_app: QApplication) -> None:
    """Verify an exception inside a cascade leaves the form untouched."""

    def explode(value: str) -> dict[str, str]:
        raise RuntimeError("lookup failed")

    @toolset(label="Boom Tools")
    class BoomTools:

        @tool(label="Boom", cascade={"a": explode})
        def boom(self, a: str = "", b: str = "") -> None:
            """Placeholder tool body; the test only drives the form."""

    page = _page(BoomTools, qt_app)
    page._widgets["a"].setText("go")
    page._widgets["a"].editingFinished.emit()

    assert page._widgets["b"].text() == ""
    assert any("lookup failed" in message for message in _warnings(page))


def test_replay_does_not_trigger_cascades(qt_app: QApplication) -> None:
    """Verify restored parameters survive instead of being recomputed."""
    page = _page(DeployTools, qt_app)

    page.restore_params({"service": "web", "version": "pinned", "owner": "alice"})

    assert DeployTools.calls == []
    assert page._widgets["version"].text() == "pinned"
    assert page._widgets["owner"].text() == "alice"


def test_replay_resets_the_commit_baseline(qt_app: QApplication) -> None:
    """Verify a later commit of a restored value is treated as unchanged."""
    page = _page(DeployTools, qt_app)

    page.restore_params({"service": "web"})
    page._widgets["service"].editingFinished.emit()

    assert DeployTools.calls == []


def test_cascades_are_suspended_while_running(qt_app: QApplication) -> None:
    """Verify a disabled parameter panel performs no lookups."""
    page = _page(DeployTools, qt_app)

    page._set_params_readonly(True)
    page._widgets["service"].setText("web")
    page._widgets["service"].editingFinished.emit()
    assert DeployTools.calls == []

    page._set_params_readonly(False)
    page._widgets["service"].editingFinished.emit()
    assert DeployTools.calls == ["web"]


def test_non_text_widgets_commit_too(qt_app: QApplication) -> None:
    """Verify checkboxes and combo boxes act as cascade sources."""

    @toolset(label="Flag Tools")
    class FlagTools:

        @tool(label="Flag", cascade={"verbose": lambda value: {"level": "DEBUG" if value else "INFO"}})
        def flag(self, verbose: bool = False, level: str = "") -> None:
            """Placeholder tool body; the test only drives the form."""

    page = _page(FlagTools, qt_app)
    page._widgets["verbose"].setChecked(True)

    assert page._widgets["level"].text() == "DEBUG"


# ── Defaults ──────────────────────────────────────────────────────────────────

def test_defaults_dict_fills_the_form(qt_app: QApplication) -> None:
    """Verify a defaults dict is written into the widgets."""

    @toolset(label="Default Tools")
    class DefaultTools:

        @tool(label="Defaults", defaults={"name": "alice", "count": 7})
        def run(self, name: str = "", count: int = 0) -> None:
            """Placeholder tool body; the test only drives the form."""

    page = _page(DefaultTools, qt_app)

    assert page._widgets["name"].text() == "alice"
    assert page._widgets["count"].value() == 7


def test_defaults_callable_is_evaluated_per_page(qt_app: QApplication) -> None:
    """Verify a defaults callback runs when the page is built, not at import."""
    calls: list[int] = []

    def load_defaults() -> dict[str, str]:
        calls.append(1)
        return {"name": f"run-{len(calls)}"}

    @toolset(label="Lazy Tools")
    class LazyTools:

        @tool(label="Lazy", defaults=load_defaults)
        def run(self, name: str = "") -> None:
            """Placeholder tool body; the test only drives the form."""

    assert calls == []

    first = _page(LazyTools, qt_app)
    second = _page(LazyTools, qt_app)

    assert first._widgets["name"].text() == "run-1"
    assert second._widgets["name"].text() == "run-2"


def test_defaults_callable_receives_the_signature_defaults(qt_app: QApplication) -> None:
    """Verify a one-argument defaults callback sees the pre-filled form."""

    @toolset(label="Form Tools")
    class FormTools:

        @tool(label="Form", defaults=lambda form: {"name": form["name"].upper()})
        def run(self, name: str = "alice") -> None:
            """Placeholder tool body; the test only drives the form."""

    page = _page(FormTools, qt_app)

    assert page._widgets["name"].text() == "ALICE"


def test_failing_defaults_leave_the_form_usable(qt_app: QApplication) -> None:
    """Verify a raising defaults callback warns and keeps signature defaults."""

    def explode() -> dict[str, str]:
        raise RuntimeError("no config")

    @toolset(label="Broken Tools")
    class BrokenTools:

        @tool(label="Broken", defaults=explode)
        def run(self, name: str = "fallback") -> None:
            """Placeholder tool body; the test only drives the form."""

    page = _page(BrokenTools, qt_app)

    assert page._widgets["name"].text() == "fallback"
    assert any("no config" in message for message in _warnings(page))


def test_defaults_do_not_trigger_cascades(qt_app: QApplication) -> None:
    """Verify pre-filled values are not treated as user commits."""

    @toolset(label="Seeded Tools")
    class SeededTools:

        calls: list[str] = []

        @tool(
            label="Seeded",
            defaults={"service": "web"},
            cascade={"service": "on_change"},
        )
        def run(self, service: str = "", owner: str = "") -> None:
            """Placeholder tool body; the test only drives the form."""

        def on_change(self, value: str) -> dict[str, str]:
            """Record the commit and return an owner.

            Args:
                value: The committed service name.

            Returns:
                A value for the owner field.
            """
            SeededTools.calls.append(value)
            return {"owner": "team"}

    page = _page(SeededTools, qt_app)

    assert page._widgets["service"].text() == "web"
    assert SeededTools.calls == []
    assert page._widgets["owner"].text() == ""
