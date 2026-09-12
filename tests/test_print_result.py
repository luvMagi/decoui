"""Tests for printing a successful run's return value to the console.

The switch has two layers and three states, so most of what is checked here is
which of them wins. The rest guards the two ways the feature could lie about a
run: printing something the run did not produce (a failed run, a ``None``), or
printing text that differs from what the same value reads as everywhere else.
"""

from __future__ import annotations

import pytest

from decoui import tool, toolset
from decoui.engine.executor import render_result
from decoui.i18n import set_language, t
from decoui.registry import build_tree
from decoui.ui.main_window import MainWindow


@toolset(label="Build")
class _Build:
    """A tool that says nothing about printing, and one that opts out."""

    @tool(label="Build")
    def build(self) -> str:
        """Placeholder tool body."""
        return "build-4711"

    @tool(label="Handle", print_result=False)
    def handle(self) -> str:
        """Placeholder tool body."""
        return "0x7ffe"

    @tool(label="Count", print_result=True)
    def count(self) -> int:
        """Placeholder tool body."""
        return 7


def _page(print_result: bool, tool_id: str = "_Build.build"):
    """Open one tool page under an application-wide setting.

    Args:
        print_result: What the application passed to gui_main().
        tool_id: Which tool to open.

    Returns:
        The live ToolPage.
    """
    window = MainWindow(
        build_tree(_Build), title="test", print_result=print_result
    )
    info = next(
        t for ts in window._tree for t in ts.tools if t.tool_id == tool_id
    )
    window._show_tool(info)
    return window._tool_pages[tool_id]


def _printed(page) -> list[str]:
    """Return the console lines the page holds, in order.

    Args:
        page: The ToolPage to read.

    Returns:
        The message of every log record, levels dropped.
    """
    return [entry.message for entry in page._log_records]


# ── Which switch wins ─────────────────────────────────────────────────────────

def test_nothing_is_printed_by_default(qt_app) -> None:
    """Verify an application that says nothing behaves as it did in v1.0.0."""
    page = _page(False)

    page._on_finished("build-4711", "success")

    assert _printed(page) == []


def test_the_application_switch_turns_it_on(qt_app) -> None:
    """Verify gui_main(print_result=True) reaches a tool that declares nothing."""
    page = _page(True)

    page._on_finished("build-4711", "success")

    assert '"build-4711"' in _printed(page)


def test_a_tool_may_opt_out_of_an_application_that_prints(qt_app) -> None:
    """Verify @tool(print_result=False) wins over the application default."""
    page = _page(True, "_Build.handle")

    page._on_finished("0x7ffe", "success")

    assert _printed(page) == []


def test_a_tool_may_opt_in_to_an_application_that_does_not(qt_app) -> None:
    """Verify @tool(print_result=True) wins the other way round."""
    page = _page(False, "_Build.count")

    page._on_finished(7, "success")

    assert "7" in _printed(page)


def test_the_registry_keeps_all_three_states(qt_app) -> None:
    """Verify None survives to the page rather than being read as False.

    The distinction is the whole design: a tool that declared nothing has to be
    told apart from one that declared "no".
    """
    tools = {t.tool_id: t for t in build_tree(_Build)[0].tools}

    assert tools["_Build.build"].print_result is None
    assert tools["_Build.handle"].print_result is False
    assert tools["_Build.count"].print_result is True


# ── What gets printed ─────────────────────────────────────────────────────────

def test_the_value_is_printed_under_a_banner_after_a_blank_line(qt_app) -> None:
    """Verify the shape: a gap, the rule, the value -- in that order."""
    page = _page(True)
    page._append_log("stdout", "working")

    page._on_finished("build-4711", "success")

    assert _printed(page) == [
        "working",
        "",
        "========== Result ==========",
        '"build-4711"',
    ]


def test_the_printed_lines_are_stdout(qt_app) -> None:
    """Verify they are ordinary output, not a level of their own.

    This is what makes them stored with the run, re-openable from history, and
    reachable by the log window's filter and search -- none of which would hold
    for a level no theme inks.
    """
    page = _page(True)

    page._on_finished("build-4711", "success")

    assert {entry.level for entry in page._log_records} == {"stdout"}


def test_the_printed_text_is_the_shared_rendering(qt_app) -> None:
    """Verify the console and the history record cannot read differently."""
    value = {"artifact": "b-1", "size": 20481}
    page = _page(True)

    page._on_finished(value, "success")

    assert _printed(page)[-1] == render_result(value)


def test_the_banner_follows_the_interface_language(qt_app) -> None:
    """Verify the word in the rule is translated, and the rule itself is not."""
    try:
        set_language("ja-JP")
        page = _page(True)

        page._on_finished("build-4711", "success")

        banner = f"========== {t('tool.result_banner')} =========="
        assert _printed(page)[1] == banner
        assert "結果" in _printed(page)[1]
    finally:
        set_language("en")


# ── What does not get printed ─────────────────────────────────────────────────

@pytest.mark.parametrize("status", ["error", "cancelled"])
def test_a_run_that_did_not_succeed_prints_nothing(qt_app, status) -> None:
    """Verify only a successful run has a return value worth announcing."""
    page = _page(True)

    page._on_finished(None, status)

    assert _printed(page) == []


def test_a_run_returning_none_prints_nothing(qt_app) -> None:
    """Verify decoui does not print the word None for a tool that returned none.

    Not even the banner: a rule over an empty space would say a value exists.
    """
    page = _page(True)
    page._append_log("stdout", "working")

    page._on_finished(None, "success")

    assert _printed(page) == ["working"]
