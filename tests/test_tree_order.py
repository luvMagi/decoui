"""Tests for the order build_tree() puts toolsets and tools in.

Up to v1.0.0 the sidebar was always sorted by label. It is now declaration
order by default, with the old behaviour available as ``order="label"``. Every
label below is chosen so that the two orders disagree: a test whose expectation
both orders satisfy would pass against either implementation and prove nothing.
"""

from __future__ import annotations

import pytest

from decoui import tool, toolset
from decoui.registry import build_tree


@toolset(label="Deploy")
class _Deploy:
    """Tools whose labels sort the opposite way to how they are written."""

    @tool(label="Zip")
    def zip_up(self) -> None:
        """Placeholder tool body; only the position is under test."""

    @tool(label="Build")
    def build(self) -> None:
        """Placeholder tool body; only the position is under test."""

    def helper(self) -> None:
        """Ordinary method, not a tool -- must not appear in the tree."""

    @tool(label="Analyse")
    def analyse(self) -> None:
        """Placeholder tool body; only the position is under test."""


@toolset(label="Audit")
class _Audit:
    """Second toolset, to test ordering between groups."""

    @tool(label="Check")
    def check(self) -> None:
        """Placeholder tool body."""


class _Base:
    """Undecorated base, to test where inherited tools land."""

    @tool(label="Inherited")
    def inherited(self) -> None:
        """Placeholder tool body."""


@toolset(label="Derived")
class _Derived(_Base):
    """Subclass adding one tool of its own."""

    @tool(label="Added")
    def added(self) -> None:
        """Placeholder tool body."""


@toolset(label="Override")
class _Override(_Base):
    """Subclass replacing the inherited tool with its own implementation."""

    @tool(label="Replaced")
    def inherited(self) -> None:
        """Placeholder tool body, under the name the base declared."""

    @tool(label="Extra")
    def extra(self) -> None:
        """Placeholder tool body."""


def test_tools_come_back_in_the_order_they_were_written() -> None:
    """Verify the class body's order is the default, not the alphabet.

    inspect.getmembers() -- what build_tree used before -- sorts by attribute
    name, so this list would come back Analyse, Build, Zip.
    """
    tools = build_tree(_Deploy)[0].tools

    assert [t.label for t in tools] == ["Zip", "Build", "Analyse"]


def test_methods_without_the_decorator_stay_out() -> None:
    """Verify walking the class namespace still collects only @tool methods."""
    names = [t.method_name for t in build_tree(_Deploy)[0].tools]

    assert "helper" not in names


def test_order_label_sorts_tools_alphabetically() -> None:
    """Verify order="label" is the pre-1.1.0 behaviour, unchanged."""
    tools = build_tree(_Deploy, order="label")[0].tools

    assert [t.label for t in tools] == ["Analyse", "Build", "Zip"]


def test_order_applies_to_toolsets_and_their_tools_together() -> None:
    """Verify one argument decides both levels, so they cannot disagree."""
    declared = build_tree(_Deploy, _Audit)
    assert [ts.label for ts in declared] == ["Deploy", "Audit"]
    assert [t.label for t in declared[0].tools] == ["Zip", "Build", "Analyse"]

    sorted_tree = build_tree(_Deploy, _Audit, order="label")
    assert [ts.label for ts in sorted_tree] == ["Audit", "Deploy"]
    assert [t.label for t in sorted_tree[0].tools] == ["Check"]


def test_inherited_tools_come_before_the_subclasss_own() -> None:
    """Verify the MRO is walked base-first, so a shared tool stays on top."""
    tools = build_tree(_Derived)[0].tools

    assert [t.label for t in tools] == ["Inherited", "Added"]


def test_an_overridden_tool_keeps_the_bases_position() -> None:
    """Verify overriding replaces the implementation, not the place.

    The subclass's function is what runs -- ``_Override.inherited`` carries the
    "Replaced" label -- but the entry stays where the base put it, ahead of
    anything the subclass added.
    """
    tools = build_tree(_Override)[0].tools

    assert [t.label for t in tools] == ["Replaced", "Extra"]
    assert tools[0].method is _Override.inherited


def test_a_subclass_can_drop_an_inherited_tool() -> None:
    """Verify a plain override removes the tool rather than keeping the base's.

    The marker is resolved on the class being scanned, not on the function the
    base declared, so shadowing a tool with an ordinary method un-tools it.
    """
    @toolset(label="Quiet")
    class _Quiet(_Base):
        """Subclass that shadows the inherited tool with a plain method."""

        def inherited(self) -> None:
            """Ordinary method now -- no @tool."""

    assert build_tree(_Quiet)[0].tools == []


@pytest.mark.parametrize("bad", ["Declaration", "alphabetical", "", None])
def test_unrecognised_orders_are_refused(bad) -> None:
    """Verify every near-miss raises rather than silently picking a default."""
    with pytest.raises(ValueError):
        build_tree(_Deploy, order=bad)
