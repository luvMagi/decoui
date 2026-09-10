"""Tests for the themes decoui ships.

These check that each shipped theme is complete, distinct, and readable. They
deliberately do not check that a theme resembles its reference screenshot: the
mockups were rendered, not built, and readability wins over resemblance
wherever the two disagree.
"""

from __future__ import annotations

import pytest

from decoui.theme import COLOR_TOKENS, SHAPE_TOKENS, Theme, builtin_themes, render_stylesheet

#: Themes decoui is expected to ship.
EXPECTED_IDS = {"light", "cockpit", "nasa", "jp-industrial"}

#: Foreground/background pairs a user has to be able to read.
CONTRAST_PAIRS = [
    ("text.primary", "bg.app"),
    ("text.primary", "bg.surface"),
    ("text.primary", "bg.field"),
    ("text.primary", "bg.table"),
    ("text.button", "bg.button"),
    ("text.button", "bg.button_hover"),
    ("text.secondary", "bg.surface"),
    ("text.muted", "bg.surface"),
    ("text.muted", "bg.header"),
    ("text.disabled", "bg.button_disabled"),
    # The tool list is the one place a theme may go dark while the rest stays
    # light, so its own pair matters more than the inherited one.
    ("text.on_sidebar", "bg.tree"),
    ("text.on_sidebar", "bg.tree_hover"),
    ("text.on_sidebar_selected", "bg.tree_selected"),
    ("text.tab_selected", "bg.tab_selected"),
    ("text.required", "bg.surface"),
    ("text.on_accent", "accent"),
    ("text.on_success", "success"),
    ("text.on_success", "success.hover"),
    ("text.on_danger", "danger"),
    ("text.on_danger", "danger.hover"),
    ("text.on_neutral", "neutral"),
    # Console output has to stay legible on whatever ground the theme gives it.
    ("console.stdout", "bg.console"),
    ("console.info", "bg.console"),
    ("console.warning", "bg.console"),
    ("console.error", "bg.console"),
    ("console.debug", "bg.console"),
]

#: WCAG AA for body text. Where the default theme already falls short of it,
#: that shortfall becomes the bar instead -- see test_contrast_is_no_worse.
AA_NORMAL = 4.5


def _relative_luminance(colour: str) -> float:
    """Return the WCAG relative luminance of a #rrggbb colour.

    Args:
        colour: A six-digit hex colour.

    Returns:
        Luminance in the range 0..1.
    """
    def channel(value: int) -> float:
        fraction = value / 255
        if fraction <= 0.03928:
            return fraction / 12.92
        return ((fraction + 0.055) / 1.055) ** 2.4

    red, green, blue = (int(colour[index:index + 2], 16) for index in (1, 3, 5))
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


def _contrast(foreground: str, background: str) -> float:
    """Return the WCAG contrast ratio between two colours.

    Args:
        foreground: Text colour.
        background: Surface behind it.

    Returns:
        A ratio from 1 (identical) to 21 (black on white).
    """
    first, second = _relative_luminance(foreground), _relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def _themes() -> dict[str, Theme]:
    """Return the shipped themes.

    Returns:
        Theme id to Theme.
    """
    return builtin_themes()


def test_expected_themes_are_shipped() -> None:
    """Verify the set of built-in themes is what the release promises."""
    assert set(_themes()) == EXPECTED_IDS


@pytest.mark.parametrize("theme_id", sorted(EXPECTED_IDS))
def test_theme_is_complete(theme_id: str) -> None:
    """Verify each theme defines every token, with no inheritance to hide gaps.

    The designer themes deliberately do not use ``extends``: written out in full
    they are easier to check, and a missing token fails here rather than
    silently taking a default theme's value.

    Args:
        theme_id: The theme under test.
    """
    theme = _themes()[theme_id]

    assert set(theme.colors) == COLOR_TOKENS
    assert set(theme.shape) == SHAPE_TOKENS
    assert theme.font.family
    assert theme.font.size_pt > 0


@pytest.mark.parametrize("theme_id", sorted(EXPECTED_IDS))
def test_font_stack_ends_in_a_generic_family(theme_id: str) -> None:
    """Verify a theme still renders on a machine without its preferred face.

    Without a generic last resort Qt falls back to its own default, which is
    exactly the look the theme was trying to replace.

    Args:
        theme_id: The theme under test.
    """
    assert _themes()[theme_id].font.family[-1] in {"monospace", "sans-serif", "serif"}


@pytest.mark.parametrize("theme_id", sorted(EXPECTED_IDS))
def test_theme_renders(theme_id: str) -> None:
    """Verify every theme produces a full stylesheet with no leftover tokens.

    Args:
        theme_id: The theme under test.
    """
    rendered = render_stylesheet(_themes()[theme_id])

    assert "$" not in rendered
    assert len(rendered.splitlines()) > 200


def _channel_distance(first: str, second: str) -> int:
    """Return the largest per-channel difference between two colours.

    Contrast ratio is the wrong tool for "can these be told apart": a mid green
    and a mid red have almost the same luminance and so almost no contrast,
    while being obviously different colours. This measures separation in RGB
    instead.

    Args:
        first: A six-digit hex colour.
        second: Another.

    Returns:
        The maximum absolute channel difference, 0..255.
    """
    return max(
        abs(int(first[index:index + 2], 16) - int(second[index:index + 2], 16))
        for index in (1, 3, 5)
    )


@pytest.mark.parametrize("theme_id", sorted(EXPECTED_IDS))
def test_run_and_stop_stay_distinguishable(theme_id: str) -> None:
    """Verify no theme collapses the Run and Stop buttons into one colour.

    Confusing them is not a cosmetic problem: these two buttons start and abort
    real work.

    Args:
        theme_id: The theme under test.
    """
    colours = _themes()[theme_id].colors

    assert _channel_distance(colours["success"], colours["danger"]) >= 40


@pytest.mark.parametrize("theme_id", sorted(EXPECTED_IDS))
def test_status_badges_stay_distinguishable(theme_id: str) -> None:
    """Verify the four run outcomes never render as the same fill.

    Args:
        theme_id: The theme under test.
    """
    colours = _themes()[theme_id].colors
    fills = {colours[token] for token in ("accent", "success", "danger", "neutral")}

    assert len(fills) == 4


@pytest.mark.parametrize("theme_id", sorted(EXPECTED_IDS - {"light"}))
def test_contrast_is_no_worse_than_the_default_theme(theme_id: str) -> None:
    """Verify a designer theme is never less readable than the default.

    An absolute WCAG AA floor cannot be used here: the default light theme
    predates any contrast requirement and misses AA on a few pairs of its own.
    Holding the new themes to AA where light already reaches it, and to light's
    own ratio where it does not, keeps this honest without quietly rewriting
    the default's colours.

    Args:
        theme_id: The theme under test.
    """
    light = _themes()["light"].colors
    colours = _themes()[theme_id].colors

    failures = []
    for foreground, background in CONTRAST_PAIRS:
        floor = min(AA_NORMAL, _contrast(light[foreground], light[background]))
        actual = _contrast(colours[foreground], colours[background])
        if actual < floor - 0.01:
            failures.append(f"{foreground} on {background}: {actual:.2f} < {floor:.2f}")

    assert not failures, "; ".join(failures)


def test_designer_themes_are_squarer_than_the_default() -> None:
    """Verify the geometry tokens were actually used.

    All three references are visibly harder-edged than decoui's default. If
    they had only recoloured, they would still carry its rounded corners.
    """
    light_radius = _themes()["light"].shape["shape.radius_control"]

    for theme_id in EXPECTED_IDS - {"light"}:
        assert _themes()[theme_id].shape["shape.radius_control"] < light_radius


def test_designer_themes_look_different_from_each_other() -> None:
    """Verify the three are three identities, not one palette in three tints."""
    accents = {
        _themes()[theme_id].colors["accent"] for theme_id in EXPECTED_IDS
    }

    assert len(accents) == len(EXPECTED_IDS)
