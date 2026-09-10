"""Tests for the application startup sequence."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from decoui import tool, toolset
from decoui.registry import build_tree
from decoui.runner import (
    _check_explicit_toolsets,
    _create_instances,
    _run_startup_hook,
    _run_toolset_hooks,
)
from decoui.ui.main_window import MainWindow


@toolset(label="Loaded Tools", tags=["startup"])
class LoadedTools:
    """Toolset that loads its data in __init__, as a real tool would."""

    created: list[str] = []

    def __init__(self) -> None:
        """Record construction and pretend to load persisted configuration."""
        LoadedTools.created.append("init")
        self.config = {"env": "staging"}

    @tool(label="Deploy", defaults="load_defaults")
    def deploy(self, env: str = "") -> None:
        """Placeholder tool body; the test only inspects the form."""

    def load_defaults(self) -> dict[str, str]:
        """Seed the form from data loaded at startup.

        Returns:
            Initial values for the form.
        """
        return {"env": self.config["env"]}


@pytest.fixture(autouse=True)
def _reset_creation_log() -> None:
    """Clear the construction log before each test."""
    LoadedTools.created = []


@toolset(label="Other Tools")
class OtherTools:
    """Second toolset, used to prove an explicit list excludes the rest."""

    @tool(label="Ping")
    def ping(self) -> None:
        """Placeholder tool body."""


def test_explicit_toolsets_keep_the_callers_order() -> None:
    """Verify an explicit list is passed through unchanged."""
    assert _check_explicit_toolsets([OtherTools, LoadedTools]) == [
        OtherTools,
        LoadedTools,
    ]


def test_explicit_toolsets_reject_an_empty_list() -> None:
    """Verify an empty list is refused with its own message.

    Auto-discovery finding nothing and the caller passing nothing are different
    mistakes, so they must not share an error message.
    """
    with pytest.raises(RuntimeError) as excinfo:
        _check_explicit_toolsets([])

    assert "toolsets=[]" in str(excinfo.value)


def test_explicit_toolsets_reject_an_undecorated_class() -> None:
    """Verify a class without @toolset is named in the error."""

    class NotAToolSet:
        """Plain class that was never decorated."""

    with pytest.raises(TypeError) as excinfo:
        _check_explicit_toolsets([LoadedTools, NotAToolSet])

    assert "NotAToolSet" in str(excinfo.value)


def test_explicit_order_does_not_reach_the_tree() -> None:
    """Verify build_tree still sorts by label, whatever order was passed.

    Documented in gui_main(): an explicit list controls what loads, not the
    order the navigation tree shows.
    """
    ordered = _check_explicit_toolsets([OtherTools, LoadedTools])
    tree = build_tree(*ordered)

    assert [ts.label for ts in tree] == ["Loaded Tools", "Other Tools"]


def test_startup_hook_runs_once() -> None:
    """Verify the hook is invoked exactly once when provided."""
    calls: list[int] = []

    assert _run_startup_hook(lambda: calls.append(1)) == []
    assert calls == [1]


def test_missing_startup_hook_is_allowed() -> None:
    """Verify omitting the hook is not an error."""
    assert _run_startup_hook(None) == []


def test_failing_startup_hook_is_reported_not_fatal() -> None:
    """Verify a raising hook yields a problem instead of aborting startup."""

    def load_config() -> None:
        raise FileNotFoundError("config.json")

    problems = _run_startup_hook(load_config)

    assert len(problems) == 1
    assert "load_config" in problems[0].source
    assert "FileNotFoundError" in problems[0].summary
    assert "config.json" in problems[0].detail


def test_toolsets_are_instantiated_before_the_window() -> None:
    """Verify every toolset is constructed eagerly, once."""
    tree = build_tree(LoadedTools)

    instances, problems = _create_instances(tree)

    assert problems == []
    assert LoadedTools.created == ["init"]
    assert isinstance(instances[LoadedTools], LoadedTools)


def test_failing_toolset_init_is_skipped_not_fatal() -> None:
    """Verify a broken __init__ is reported while other toolsets still load."""

    @toolset(label="Broken Tools")
    class BrokenTools:

        def __init__(self) -> None:
            """Fail the way a missing config file would."""
            raise FileNotFoundError("settings.toml")

        @tool(label="Noop")
        def noop(self) -> None:
            """Placeholder tool body."""

    tree = build_tree(BrokenTools, LoadedTools)
    instances, problems = _create_instances(tree)

    assert LoadedTools in instances
    assert BrokenTools not in instances
    assert len(problems) == 1
    assert "Broken Tools" in problems[0].source
    assert "BrokenTools.__init__" in problems[0].summary
    assert "settings.toml" in problems[0].detail


def test_toolset_hook_fills_attributes_declared_in_init() -> None:
    """Verify on_startup() runs after construction and can write to self."""

    @toolset(label="Hooked Tools")
    class HookedTools:

        def __init__(self) -> None:
            """Declare state without loading it yet."""
            self.config: dict[str, str] = {}

        def on_startup(self) -> None:
            """Load the state declared above, before the event loop starts."""
            self.config = {"env": "production"}

        @tool(label="Noop")
        def noop(self) -> None:
            """Placeholder tool body."""

    instances, _ = _create_instances(build_tree(HookedTools))
    problems = _run_toolset_hooks(instances)

    assert problems == []
    assert instances[HookedTools].config == {"env": "production"}


def test_failing_toolset_hook_keeps_the_instance() -> None:
    """Verify a raising on_startup() leaves the toolset usable."""

    @toolset(label="Half Tools")
    class HalfTools:

        def __init__(self) -> None:
            """Declare state that the hook will fail to fill."""
            self.config: dict[str, str] = {}

        def on_startup(self) -> None:
            """Fail the way an unreachable backend would."""
            raise ConnectionError("backend unreachable")

        @tool(label="Noop")
        def noop(self) -> None:
            """Placeholder tool body."""

    instances, _ = _create_instances(build_tree(HalfTools))
    problems = _run_toolset_hooks(instances)

    assert len(problems) == 1
    assert "HalfTools.on_startup()" in problems[0].source
    assert "backend unreachable" in problems[0].summary
    assert instances[HalfTools].config == {}


def test_toolsets_without_a_hook_are_left_alone() -> None:
    """Verify the hook is optional."""
    instances, _ = _create_instances(build_tree(LoadedTools))

    assert _run_toolset_hooks(instances) == []


def test_a_tool_named_on_startup_is_not_called_as_a_hook() -> None:
    """Verify a @tool method never doubles as the startup hook."""

    @toolset(label="Named Tools")
    class NamedTools:

        calls: list[str] = []

        @tool(label="On Startup")
        def on_startup(self) -> None:
            """A regular tool that happens to share the hook's name."""
            NamedTools.calls.append("ran")

    instances, _ = _create_instances(build_tree(NamedTools))

    assert _run_toolset_hooks(instances) == []
    assert NamedTools.calls == []


def test_window_reuses_startup_instances(qt_app: QApplication) -> None:
    """Verify opening a tool does not construct a second instance.

    Args:
        qt_app: The shared QApplication.
    """
    tree = build_tree(LoadedTools)
    instances, _ = _create_instances(tree)
    window = MainWindow(tree, instances=instances)

    window._show_tool(tree[0].tools[0])

    assert LoadedTools.created == ["init"]
    assert window._instances[LoadedTools] is instances[LoadedTools]


def test_startup_data_reaches_the_form(qt_app: QApplication) -> None:
    """Verify data loaded in __init__ is available to defaults= on first open.

    Args:
        qt_app: The shared QApplication.
    """
    tree = build_tree(LoadedTools)
    window = MainWindow(tree, instances=_create_instances(tree)[0])

    window._show_tool(tree[0].tools[0])
    page = window._tool_pages["LoadedTools.deploy"]

    assert page._widgets["env"].text() == "staging"


def test_window_without_instances_still_creates_them(qt_app: QApplication) -> None:
    """Verify MainWindow keeps working when constructed without a startup map.

    Args:
        qt_app: The shared QApplication.
    """
    tree = build_tree(LoadedTools)
    window = MainWindow(tree)

    window._show_tool(tree[0].tools[0])

    assert LoadedTools.created == ["init"]
