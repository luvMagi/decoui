"""Tests for Copy Result and Send Result on the tool page.

The return value is still not drawn anywhere. What these cover is the two
things that were added instead: putting it on the clipboard, and handing it to
another tool's field. Both have to agree with what history recorded for the
same run -- a value that reads one way on the page and another way in the
history is the failure this feature is most able to cause.
"""

from __future__ import annotations

from typing import Annotated

import pytest
from PySide6.QtWidgets import QApplication

from decoui import F, tool, toolset
from decoui.assist import InlineRunner
from decoui.engine.executor import render_result
from decoui.registry import build_tree
from decoui.ui.main_window import MainWindow
from decoui.ui.tool_page import ToolPage

#: Shared declaration: one tool returns it, two accept it.
ArtifactId = Annotated[str, F(id="artifact", label="Artifact id")]


@toolset(label="Build")
class _Build:
    """Produces an artifact id."""

    @tool(label="Build")
    def build(self) -> ArtifactId:
        """Placeholder tool body."""
        return "build-4711"


@toolset(label="Deploy")
class _Deploy:
    """Two consumers of the artifact id."""

    @tool(label="Deploy")
    def deploy(self, artifact: ArtifactId, env: str = "staging") -> None:
        """Placeholder tool body."""

    @tool(label="Verify")
    def verify(self, artifact: ArtifactId) -> None:
        """Placeholder tool body."""


@toolset(label="Quiet")
class _Quiet:
    """A tool whose return value goes nowhere."""

    @tool(label="Count")
    def count(self) -> int:
        """Placeholder tool body."""
        return 7


def _window(*classes: type) -> MainWindow:
    """Build a main window over the given toolsets.

    Args:
        *classes: @toolset classes to load.

    Returns:
        A window whose pages can be opened and inspected.
    """
    return MainWindow(build_tree(*classes), title="test")


def _page(window: MainWindow, tool_id: str):
    """Open a tool page and return it.

    Args:
        window: The window to open it in.
        tool_id: Which tool.

    Returns:
        The live ToolPage.
    """
    info = next(
        t for ts in window._tree for t in ts.tools if t.tool_id == tool_id
    )
    window._show_tool(info)
    return window._tool_pages[tool_id]


# ── render_result: the one rendering ──────────────────────────────────────────

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("build-4711", '"build-4711"'),
        (7, "7"),
        ({"artifact": "b-1", "size": 20481}, '{"artifact": "b-1", "size": 20481}'),
        (["a", "b"], '["a", "b"]'),
    ],
)
def test_render_result_covers_the_ordinary_values(value, expected) -> None:
    """Verify the shared renderer, including None meaning "nothing to show"."""
    assert render_result(value) == expected


def test_render_result_falls_back_rather_than_failing() -> None:
    """Verify an unserialisable value still renders.

    A finished run must not lose its result to a repr problem, so the renderer
    is lossy on purpose and never raises.
    """
    class _Awkward:
        """Object json.dumps cannot handle directly."""

        def __repr__(self) -> str:
            """Return a recognisable marker."""
            return "<awkward>"

    assert render_result(_Awkward()) == '"<awkward>"'


def test_render_result_keeps_non_ascii_readable() -> None:
    """Verify text is not escaped into \\uXXXX, which nobody can read."""
    assert render_result("構築済み") == '"構築済み"'


# ── Button state ──────────────────────────────────────────────────────────────

def test_the_buttons_start_disabled(qt_app) -> None:
    """Verify a page that has not run yet offers nothing to copy or send."""
    page = _page(_window(_Build, _Deploy), "_Build.build")

    assert page._copy_result_btn.isEnabled() is False
    assert page._send_result_btn.isEnabled() is False


def test_a_successful_run_enables_them(qt_app) -> None:
    """Verify finishing with a value is what turns the buttons on."""
    page = _page(_window(_Build, _Deploy), "_Build.build")

    page._on_finished("build-4711", "success")

    assert page._copy_result_btn.isEnabled() is True
    assert page._send_result_btn.isEnabled() is True


@pytest.mark.parametrize("status", ["error", "cancelled"])
def test_a_run_that_did_not_succeed_leaves_them_off(qt_app, status) -> None:
    """Verify a failed or cancelled run is never treated as having a result."""
    page = _page(_window(_Build, _Deploy), "_Build.build")

    page._on_finished(None, status)

    assert page._copy_result_btn.isEnabled() is False
    assert page._result is None


def test_a_run_returning_none_leaves_them_off(qt_app) -> None:
    """Verify None is "nothing to show", not a value to copy."""
    page = _page(_window(_Build, _Deploy), "_Build.build")

    page._on_finished(None, "success")

    assert page._copy_result_btn.isEnabled() is False


def test_the_tooltip_previews_the_value(qt_app) -> None:
    """Verify the tooltip is where an otherwise invisible value becomes legible."""
    page = _page(_window(_Build, _Deploy), "_Build.build")

    page._on_finished("build-4711", "success")

    assert page._copy_result_btn.toolTip() == '"build-4711"'


def test_a_long_value_is_truncated_in_the_tooltip(qt_app) -> None:
    """Verify a huge return value does not produce a screen-filling tooltip."""
    page = _page(_window(_Build, _Deploy), "_Build.build")

    page._on_finished("x" * 5000, "success")

    tip = page._copy_result_btn.toolTip()
    assert len(tip) < 250
    assert tip.endswith("…")


def test_a_page_with_no_result_says_so(qt_app) -> None:
    """Verify the disabled state explains itself rather than sitting mute."""
    page = _page(_window(_Build, _Deploy), "_Build.build")

    assert page._copy_result_btn.toolTip()
    assert "build" not in page._copy_result_btn.toolTip()


# ── Copy ──────────────────────────────────────────────────────────────────────

def test_copy_result_matches_what_history_stored(qt_app) -> None:
    """Verify the page and the history record cannot disagree.

    They share one renderer precisely so that the text copied here is the text
    ``result_json`` holds for the same run.
    """
    page = _page(_window(_Build, _Deploy), "_Build.build")
    value = {"artifact": "build-4711", "size": 20481}

    page._on_finished(value, "success")
    page._copy_result()

    assert QApplication.clipboard().text() == render_result(value)


# ── Send: which destinations exist ────────────────────────────────────────────

def test_a_tool_with_no_destinations_has_no_send_button(qt_app) -> None:
    """Verify the button is absent, not disabled.

    A disabled Send would promise a destination that does not exist anywhere in
    the application.
    """
    page = _page(_window(_Quiet), "_Quiet.count")

    assert page._send_result_btn is None


def test_destinations_come_from_the_shared_id(qt_app) -> None:
    """Verify both consumers are offered, named the way history names tools."""
    window = _window(_Build, _Deploy)
    page = _page(window, "_Build.build")

    assert page._send_targets == [
        ("_Deploy.deploy", "Deploy: Deploy", "artifact"),
        ("_Deploy.verify", "Deploy: Verify", "artifact"),
    ]


def test_a_tool_is_not_offered_its_own_field(qt_app) -> None:
    """Verify a producer that also consumes the field is not a destination.

    Sending a value back into the tool that produced it is not a transfer, and
    listing it would be noise in every menu.
    """
    @toolset(label="Loop")
    class _Loop:
        """A tool that both takes and returns the same field."""

        @tool(label="Bump")
        def bump(self, artifact: ArtifactId) -> ArtifactId:
            """Placeholder tool body."""

    page = _page(_window(_Loop), "_Loop.bump")

    assert page._send_targets == []
    assert page._send_result_btn is None


def test_two_destinations_produce_a_menu(qt_app) -> None:
    """Verify the choice is offered as a menu, one entry per destination."""
    page = _page(_window(_Build, _Deploy), "_Build.build")

    menu = page._send_result_btn.menu()

    assert menu is not None
    assert [a.text() for a in menu.actions()] == [
        "Deploy: Deploy → artifact",
        "Deploy: Verify → artifact",
    ]


def test_one_destination_needs_no_menu(qt_app) -> None:
    """Verify a single destination is a direct action, not a one-item menu."""
    @toolset(label="Only")
    class _Only:
        """The sole consumer."""

        @tool(label="Take")
        def take(self, artifact: ArtifactId) -> None:
            """Placeholder tool body."""

    page = _page(_window(_Build, _Only), "_Build.build")

    assert page._send_result_btn.menu() is None
    assert len(page._send_targets) == 1


# ── Send: what it does ────────────────────────────────────────────────────────

def test_sending_opens_the_destination_and_fills_it(qt_app) -> None:
    """Verify the value lands and the user is taken to where it landed."""
    window = _window(_Build, _Deploy)
    page = _page(window, "_Build.build")
    page._on_finished("build-4711", "success")

    page.send_requested.emit("_Deploy.deploy", "artifact", page._result)

    target = window._tool_pages["_Deploy.deploy"]
    assert target._widgets["artifact"].text() == "build-4711"
    assert window._tabs.currentWidget() is target


def test_sending_overwrites_whatever_was_there(qt_app) -> None:
    """Verify an existing value is replaced without a confirmation dialog."""
    window = _window(_Build, _Deploy)
    target = _page(window, "_Deploy.deploy")
    target._widgets["artifact"].setText("old-value")

    window._send_result("_Deploy.deploy", "artifact", "build-4711")

    assert target._widgets["artifact"].text() == "build-4711"


def test_sending_leaves_the_other_fields_alone(qt_app) -> None:
    """Verify one field is written, not the whole form."""
    window = _window(_Build, _Deploy)
    target = _page(window, "_Deploy.deploy")
    target._widgets["env"].setText("production")

    window._send_result("_Deploy.deploy", "artifact", "build-4711")

    assert target._widgets["env"].text() == "production"


def test_sending_to_an_unknown_tool_is_ignored(qt_app) -> None:
    """Verify a stale destination cannot crash the sender."""
    window = _window(_Build, _Deploy)

    window._send_result("_Gone.missing", "artifact", "build-4711")

    assert "_Gone.missing" not in window._tool_pages


def test_sending_into_a_field_the_tool_no_longer_has_is_ignored(qt_app) -> None:
    """Verify a renamed parameter is skipped rather than raising."""
    window = _window(_Build, _Deploy)
    target = _page(window, "_Deploy.deploy")

    target.set_param("no_such_field", "build-4711")

    assert target._widgets["artifact"].text() == ""


def test_sending_fires_the_targets_cascade(qt_app) -> None:
    """Verify a sent value behaves like a typed one, unlike a replayed one.

    Replay suspends cascades because it restores a whole form and the cascade
    would overwrite what it is restoring. Send writes one field, so the cascade
    is exactly what should happen next -- and since set_value() emits no commit
    signal, set_param has to say so itself.
    """
    @toolset(label="Chained")
    class _Chained:
        """A tool whose artifact field fills the version field."""

        @tool(label="Take", cascade={"artifact": "derive"})
        def take(self, artifact: ArtifactId, version: str = "") -> None:
            """Placeholder tool body."""

        def derive(self, value: str, form: dict) -> dict:
            """Return the version implied by an artifact id.

            Args:
                value: The committed artifact id.
                form: The rest of the form, unused here.

            Returns:
                The fields to fill.
            """
            return {"version": value.rsplit("-", 1)[-1]}

    # Built directly with an inline runner: a cascade normally dispatches
    # through the thread pool, and there is no event loop here to deliver it.
    info = build_tree(_Chained)[0].tools[0]
    target = ToolPage(info, _Chained(), assist_runner=InlineRunner())

    target.set_param("artifact", "build-4711")

    assert target._widgets["version"].text() == "4711"


def test_replay_still_does_not_fire_cascades(qt_app) -> None:
    """Verify the difference above is a difference, not a change to replay."""
    @toolset(label="Chained")
    class _Chained:
        """Same shape as the previous test, restored instead of sent."""

        @tool(label="Take", cascade={"artifact": "derive"})
        def take(self, artifact: ArtifactId, version: str = "") -> None:
            """Placeholder tool body."""

        def derive(self, value: str, form: dict) -> dict:
            """Return a value that a replay must not be allowed to write.

            Args:
                value: The committed artifact id.
                form: The rest of the form, unused here.

            Returns:
                The fields to fill.
            """
            return {"version": "derived"}

    info = build_tree(_Chained)[0].tools[0]
    target = ToolPage(info, _Chained(), assist_runner=InlineRunner())

    target.restore_params({"artifact": "build-4711", "version": "recorded"})

    assert target._widgets["version"].text() == "recorded"


# ── Holding the value ─────────────────────────────────────────────────────────

def test_the_next_run_releases_the_previous_value(qt_app) -> None:
    """Verify the held object is dropped when a new run starts.

    Send needs the live object, which means the page keeps whatever the tool
    returned alive. Dropping it at the start of the next run is what bounds
    that cost to one run's worth.
    """
    page = _page(_window(_Build, _Deploy), "_Build.build")
    page._on_finished("build-4711", "success")

    page._on_run()

    assert page._result is None
    assert page._copy_result_btn.isEnabled() is False
