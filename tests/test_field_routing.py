"""Tests for field identity: ``F(id=...)``, the routing index and its checks.

An id is a claim that two declarations -- one tool's return value and another
tool's parameter -- are the same field. Everything here exists to make that
claim either true or loudly wrong, because the failure it prevents is a value
arriving in a field that was built for something else, which looks like it
worked.

Nothing in this module touches Qt. That is the property being relied on when an
application asserts its own routing in its own test suite.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import pytest

from decoui import F, tool, toolset
from decoui.registry import build_tree, field_index, unconsumed_field_ids

#: The shared declaration, written once and used from both ends.
ArtifactId = Annotated[str, F(id="artifact", label="Artifact id")]


@toolset(label="Build")
class _Build:
    """Produces an artifact id."""

    @tool(label="Build")
    def build(self) -> ArtifactId:
        """Placeholder tool body; only the annotation is under test."""
        return "build-4711"


@toolset(label="Deploy")
class _Deploy:
    """Consumes an artifact id, from two different tools."""

    @tool(label="Deploy")
    def deploy(self, artifact: ArtifactId, env: str = "staging") -> None:
        """Placeholder tool body."""

    @tool(label="Verify")
    def verify(self, artifact: ArtifactId) -> None:
        """Placeholder tool body."""


def _tool_of(tree: list, label: str):
    """Return the one tool carrying a label.

    Args:
        tree: A tree from build_tree().
        label: The tool's display label.

    Returns:
        The matching ToolInfo.
    """
    return next(t for ts in tree for t in ts.tools if t.label == label)


# ── Declaring an id ───────────────────────────────────────────────────────────

def test_a_return_carries_the_id_it_declares() -> None:
    """Verify the id on a return annotation reaches ToolInfo."""
    assert _tool_of(build_tree(_Build), "Build").return_field_id == "artifact"


def test_an_optional_return_still_carries_its_id() -> None:
    """Verify Optional is unwrapped on the return side.

    A tool that may return None is the normal shape for "it worked, or there
    was nothing to do", and it must not lose its routing for saying so.
    """
    @toolset(label="Maybe")
    class _Maybe:
        """Toolset whose tool may return nothing."""

        @tool(label="Find")
        def find(self) -> Optional[ArtifactId]:
            """Placeholder tool body."""

    assert _tool_of(build_tree(_Maybe), "Find").return_field_id == "artifact"


def test_a_parameter_carries_the_id_it_declares() -> None:
    """Verify the id reaches ParamInfo as well as ToolInfo."""
    params = {p.name: p for p in _tool_of(build_tree(_Deploy), "Deploy").params}

    assert params["artifact"].field_id == "artifact"
    assert params["env"].field_id is None


def test_an_id_changes_nothing_else_about_a_parameter() -> None:
    """Verify F(id=) is inert beyond routing.

    The label chain, the stripped annotation and the required-field marker must
    all behave as they did before the id existed -- otherwise adding one to a
    shared alias would quietly restyle every form using it.
    """
    param = next(
        p for p in _tool_of(build_tree(_Deploy), "Deploy").params
        if p.name == "artifact"
    )

    assert param.annotation is str
    assert param.label == "Artifact id"
    assert param.has_default is False


def test_a_tree_without_ids_is_unchanged() -> None:
    """Verify the whole feature is dormant when nobody declares an id."""
    @toolset(label="Plain")
    class _Plain:
        """Toolset that never mentions F."""

        @tool(label="Go")
        def go(self, name: str) -> str:
            """Placeholder tool body."""
            return name

    info = _tool_of(build_tree(_Plain), "Go")

    assert info.return_field_id is None
    assert [p.field_id for p in info.params] == [None]
    assert field_index(build_tree(_Plain)) == {}


# ── The index ─────────────────────────────────────────────────────────────────

def test_the_index_lists_every_parameter_claiming_an_id() -> None:
    """Verify one produced field finds all of its destinations."""
    index = field_index(build_tree(_Build, _Deploy))

    assert index == {
        "artifact": [("_Deploy.deploy", "artifact"), ("_Deploy.verify", "artifact")]
    }


def test_the_index_covers_parameters_only() -> None:
    """Verify a return does not list itself as a destination.

    Sending a value to the field that produced it is not a route, and a tree
    holding only the producer therefore has nowhere to send anything.
    """
    assert field_index(build_tree(_Build)) == {}


# ── Unconsumed ids ────────────────────────────────────────────────────────────

def test_a_produced_id_nobody_accepts_is_reported_not_raised() -> None:
    """Verify a typo'd id is surfaced without stopping the application.

    Raising would forbid writing a producer before its consumer, which is a
    normal order to work in. Staying silent would leave a missing Send button
    as the only symptom.
    """
    tree = build_tree(_Build)

    assert unconsumed_field_ids(tree) == ["artifact"]


def test_a_consumed_id_is_not_reported() -> None:
    """Verify a fully wired route produces no startup noise."""
    assert unconsumed_field_ids(build_tree(_Build, _Deploy)) == []


def test_unconsumed_ids_are_deduplicated() -> None:
    """Verify two producers of the same orphan field report it once."""
    @toolset(label="Twin")
    class _Twin:
        """Two tools producing the same unconsumed field."""

        @tool(label="One")
        def one(self) -> ArtifactId:
            """Placeholder tool body."""

        @tool(label="Two")
        def two(self) -> ArtifactId:
            """Placeholder tool body."""

    assert unconsumed_field_ids(build_tree(_Twin)) == ["artifact"]


# ── Type agreement ────────────────────────────────────────────────────────────

def test_one_id_with_two_types_is_refused() -> None:
    """Verify a contradicted id raises and names both sites.

    This is the check that makes an id mean something: without it, sending a
    value across a mismatched pair would put a str where an int was expected
    and the form would show a plausible wrong value.
    """
    @toolset(label="Clash")
    class _Clash:
        """Two parameters claiming one id with different types."""

        @tool(label="A")
        def a(self, size: Annotated[str, F(id="size")]) -> None:
            """Placeholder tool body."""

        @tool(label="B")
        def b(self, size: Annotated[int, F(id="size")]) -> None:
            """Placeholder tool body."""

    with pytest.raises(ValueError) as excinfo:
        build_tree(_Clash)

    message = str(excinfo.value)
    assert "size" in message
    assert "_Clash.a" in message and "_Clash.b" in message


def test_a_return_contradicting_a_parameter_is_refused() -> None:
    """Verify the check spans both ends, not just parameter against parameter."""
    @toolset(label="Mismatch")
    class _Mismatch:
        """A producer and a consumer that disagree about the type."""

        @tool(label="Make")
        def make(self) -> Annotated[Path, F(id="artifact")]:
            """Placeholder tool body."""

        @tool(label="Take")
        def take(self, artifact: ArtifactId) -> None:
            """Placeholder tool body."""

    with pytest.raises(ValueError):
        build_tree(_Mismatch)


def test_optional_and_required_count_as_the_same_type() -> None:
    """Verify tolerating None does not make a field a different field."""
    @toolset(label="Loose")
    class _Loose:
        """One parameter optional, one not, both the same field."""

        @tool(label="A")
        def a(self, artifact: Optional[ArtifactId] = None) -> None:
            """Placeholder tool body."""

        @tool(label="B")
        def b(self, artifact: ArtifactId) -> None:
            """Placeholder tool body."""

    assert len(field_index(build_tree(_Loose))["artifact"]) == 2


# ── Field-level routing is refused, not half-honoured ─────────────────────────

@pytest.mark.parametrize(
    "annotation",
    [
        tuple[Annotated[str, F(id="artifact")], int],
        list[Annotated[str, F(id="artifact")]],
        dict[str, Annotated[int, F(id="artifact")]],
    ],
    ids=["tuple", "list", "dict"],
)
def test_an_id_buried_in_the_return_is_refused(annotation) -> None:
    """Verify a nested id raises instead of describing the container.

    The trap this closes: ``_find_field_meta()`` recurses, so reusing it here
    would report the nested F as if it described the whole return, and Send
    would hand an entire tuple to a field declared for one of its members --
    a plausible wrong value, not an error. The message has to point at the
    supported shape, because the author who wrote this wanted field-level
    routing and needs to know it does not exist.
    """
    def make(self) -> None:
        """Placeholder tool body; its return annotation is set below."""

    # Written here rather than in the signature because the annotation is what
    # varies per case, and a decorated class body cannot be parametrised.
    make.__annotations__["return"] = annotation

    cls = toolset(label="Nested")(
        type("_Nested", (), {"make": tool(label="Make")(make)})
    )

    with pytest.raises(ValueError) as excinfo:
        build_tree(cls)

    message = str(excinfo.value)
    assert "artifact" in message
    assert "Annotated" in message


def test_a_container_return_without_an_id_is_fine() -> None:
    """Verify the nested check only fires on an id, not on any F at all.

    An ``F`` carrying only a label inside a returned container describes
    nothing routable but breaks nothing either, so it must not be an error.
    """
    @toolset(label="Labelled")
    class _Labelled:
        """Returns a container whose member carries a label-only F."""

        @tool(label="Make")
        def make(self) -> tuple[Annotated[str, F(label="Name")], int]:
            """Placeholder tool body."""

    assert _tool_of(build_tree(_Labelled), "Make").return_field_id is None
