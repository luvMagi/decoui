"""Tests for assist metadata plumbing and startup validation."""

from __future__ import annotations

import pathlib

import pytest

from decoui import tool, toolset
from decoui.assist import (
    MAX_COMPLETION_ITEMS,
    _adapt_defaults,
    _adapt_lookup,
    normalize_candidates,
    resolve_callback,
)
from decoui.registry import build_tree


def _single_tool(cls: type):
    """Build the tree for one toolset class and return its only ToolInfo.

    Args:
        cls: A class decorated with @toolset holding exactly one @tool.

    Returns:
        The ToolInfo built for that tool.
    """
    return build_tree(cls)[0].tools[0]


def test_assist_metadata_reaches_tool_info() -> None:
    """Verify completions, cascade, defaults and debounce survive the decorator."""

    @toolset(label="Assist")
    class AssistTools:

        @tool(
            label="Deploy",
            completions={"env": ["prod", "staging"]},
            cascade={"env": lambda value: {"owner": value}},
            defaults={"owner": "nobody"},
            completion_debounce_ms=50,
        )
        def deploy(self, env: str = "", owner: str = "") -> None:
            pass

    info = _single_tool(AssistTools)

    assert info.completions == {"env": ["prod", "staging"]}
    assert set(info.cascade) == {"env"}
    assert info.defaults == {"owner": "nobody"}
    assert info.completion_debounce_ms == 50


def test_tool_without_assist_keeps_empty_defaults() -> None:
    """Verify a plain tool declares no assist behaviour."""

    @toolset(label="Plain")
    class PlainTools:

        @tool(label="Echo")
        def echo(self, text: str = "") -> None:
            pass

    info = _single_tool(PlainTools)

    assert info.completions == {}
    assert info.cascade == {}
    assert info.defaults is None


def test_completions_unknown_parameter_is_rejected() -> None:
    """Verify a misspelled completions key fails at startup."""

    @toolset(label="Assist")
    class AssistTools:

        @tool(label="Deploy", completions={"servcie": ["a"]})
        def deploy(self, service: str = "") -> None:
            pass

    with pytest.raises(ValueError) as excinfo:
        build_tree(AssistTools)

    assert "servcie" in str(excinfo.value)
    assert "service" in str(excinfo.value)


@pytest.mark.parametrize("where", ["placeholders", "labels"])
def test_text_map_unknown_parameter_is_rejected(where: str) -> None:
    """Verify a misspelled placeholders/labels key fails at startup.

    These two maps used to be skipped by validation entirely, so a typo left
    the text silently unused with no error anywhere.
    """

    @toolset(label="Assist")
    class AssistTools:

        @tool(label="Deploy", **{where: {"servcie": "hint"}})
        def deploy(self, service: str = "") -> None:
            pass

    with pytest.raises(ValueError) as excinfo:
        build_tree(AssistTools)

    message = str(excinfo.value)
    assert where in message
    assert "servcie" in message
    assert "service" in message


@pytest.mark.parametrize("where", ["placeholders", "labels"])
def test_text_map_rejects_non_str_value(where: str) -> None:
    """Verify a non-str placeholder/label is rejected while the tool is known.

    Without this the value reaches the form builder and fails there instead,
    where the traceback no longer names the tool that declared it.
    """

    @toolset(label="Assist")
    class AssistTools:

        @tool(label="Deploy", **{where: {"service": 123}})
        def deploy(self, service: str = "") -> None:
            pass

    with pytest.raises(TypeError) as excinfo:
        build_tree(AssistTools)

    message = str(excinfo.value)
    assert f"{where}['service']" in message
    assert "int" in message


@pytest.mark.parametrize("where", ["placeholders", "labels"])
def test_text_map_accepts_real_parameter_names(where: str) -> None:
    """Verify correct keys still build, so validation only rejects mistakes."""

    @toolset(label="Assist")
    class AssistTools:

        @tool(label="Deploy", **{where: {"service": "web"}})
        def deploy(self, service: str = "") -> None:
            pass

    info = _single_tool(AssistTools)

    assert info.params[0].name == "service"


def test_cascade_unknown_parameter_is_rejected() -> None:
    """Verify a misspelled cascade key fails at startup."""

    @toolset(label="Assist")
    class AssistTools:

        @tool(label="Deploy", cascade={"missing": lambda value: {}})
        def deploy(self, service: str = "") -> None:
            pass

    with pytest.raises(ValueError, match="missing"):
        build_tree(AssistTools)


def test_defaults_unknown_parameter_is_rejected() -> None:
    """Verify a defaults dict may only name real parameters."""

    @toolset(label="Assist")
    class AssistTools:

        @tool(label="Deploy", defaults={"nope": 1})
        def deploy(self, service: str = "") -> None:
            pass

    with pytest.raises(ValueError, match="nope"):
        build_tree(AssistTools)


@pytest.mark.parametrize(
    ("annotation", "supported"),
    [
        (str, True),
        (pathlib.Path, True),
        (int, False),
        (float, False),
        (bool, False),
        (list, False),
        (dict, False),
    ],
)
def test_completions_only_allowed_on_text_widgets(annotation: type, supported: bool) -> None:
    """Verify completions are rejected for widgets that cannot host a completer.

    Args:
        annotation: The parameter annotation under test.
        supported: Whether completions should be accepted for it.
    """

    def deploy(self, value=None) -> None:
        pass

    # Set annotations explicitly: this module uses postponed evaluation, so a
    # parametrized annotation would otherwise stay an unresolvable string.
    deploy.__annotations__ = {"value": annotation, "return": None}
    decorated = tool(label="Deploy", completions={"value": ["a"]})(deploy)
    cls = toolset(label="Assist")(type("AssistTools", (), {"deploy": decorated}))

    if supported:
        assert _single_tool(cls).completions == {"value": ["a"]}
    else:
        with pytest.raises(TypeError, match="value"):
            build_tree(cls)


def test_completions_rejects_unsupported_spec_type() -> None:
    """Verify a non-list, non-callable, non-name spec fails at startup."""

    @toolset(label="Assist")
    class AssistTools:

        @tool(label="Deploy", completions={"service": 42})
        def deploy(self, service: str = "") -> None:
            pass

    with pytest.raises(TypeError, match="service"):
        build_tree(AssistTools)


def test_method_name_spec_must_exist_on_the_class() -> None:
    """Verify a string spec naming a missing method fails at startup."""

    @toolset(label="Assist")
    class AssistTools:

        @tool(label="Deploy", completions={"service": "lookup_services"})
        def deploy(self, service: str = "") -> None:
            pass

    with pytest.raises(AttributeError) as excinfo:
        build_tree(AssistTools)

    assert "lookup_services" in str(excinfo.value)
    assert "AssistTools" in str(excinfo.value)


def test_method_name_spec_binds_to_the_instance() -> None:
    """Verify a string spec resolves to a bound method that can use self."""

    @toolset(label="Assist")
    class AssistTools:
        prefix = "svc-"

        @tool(label="Deploy", completions={"service": "lookup"})
        def deploy(self, service: str = "") -> None:
            pass

        def lookup(self, text: str) -> list[str]:
            return [self.prefix + text]

    info = _single_tool(AssistTools)
    callback = resolve_callback(info.completions["service"], AssistTools())

    assert callback("web", {}) == ["svc-web"]


def test_adapt_lookup_supports_every_arity() -> None:
    """Verify 0-, 1-, and 2-argument callbacks are all callable uniformly."""
    assert _adapt_lookup(lambda: "none")("v", {"a": 1}) == "none"
    assert _adapt_lookup(lambda text: text)("v", {"a": 1}) == "v"
    assert _adapt_lookup(lambda text, form: (text, form))("v", {"a": 1}) == ("v", {"a": 1})


def test_adapt_defaults_supports_every_arity() -> None:
    """Verify defaults callbacks may take the form snapshot or nothing."""
    assert _adapt_defaults(lambda: {"a": 1})({}) == {"a": 1}
    assert _adapt_defaults(lambda form: form)({"a": 1}) == {"a": 1}


def test_normalize_candidates_cleans_the_result() -> None:
    """Verify candidates are stringified, de-duplicated, and order-preserving."""
    assert normalize_candidates(["b", "a", "b", 3]) == ["b", "a", "3"]
    assert normalize_candidates(None) == []
    assert normalize_candidates("single") == ["single"]


def test_normalize_candidates_truncates_long_results() -> None:
    """Verify oversized candidate lists are capped."""
    items = normalize_candidates(str(i) for i in range(MAX_COMPLETION_ITEMS + 500))

    assert len(items) == MAX_COMPLETION_ITEMS


def test_normalize_candidates_rejects_non_iterables() -> None:
    """Verify a scalar callback result is reported instead of silently ignored."""
    with pytest.raises(TypeError, match="int"):
        normalize_candidates(42)
