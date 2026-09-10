"""Tests for theme tokens, theme files, and stylesheet rendering."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from decoui.theme import (
    COLOR_TOKENS,
    FONT_KEYS,
    SHAPE_TOKENS,
    Theme,
    ThemeError,
    active_theme,
    builtin_themes,
    load_theme,
    render_stylesheet,
)
from decoui.ui.tag_bar import _pill_style
from decoui.ui.tool_page import _STATUS_INK, _status_style

RESOURCE_DIR = Path(__file__).parent / "resources"

#: The two declarations the pre-theme stylesheet had that the template
#: deliberately dropped. The splitter's hairline became a wider hoverable grab
#: area with the line drawn inside it, and the pane's `border-top` went with
#: the switch to document mode, where the page draws that separator itself.
DELIBERATE_REMOVALS = {
    ("QSplitter::handle:horizontal", "width"),
    ("QTabWidget::pane", "border-top"),
}


def _rules(stylesheet: str) -> dict[str, set[str]]:
    """Return each selector in a stylesheet and the properties it declares.

    Comments and values are both discarded: this is used to compare the shape
    of two sheets, and a value is exactly what a theme is free to change.

    Args:
        stylesheet: QSS text.

    Returns:
        Selector to the set of property names it sets. A selector list is split
        on commas, so ``"QSpinBox, QDoubleSpinBox"`` contributes two entries.
    """
    stylesheet = re.sub(r"/\*.*?\*/", "", stylesheet, flags=re.DOTALL)
    rules: dict[str, set[str]] = {}
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", stylesheet):
        properties = set(re.findall(r"([a-z-]+)\s*:", body))
        for selector in selectors.split(","):
            rules.setdefault(" ".join(selector.split()), set()).update(properties)
    return rules


def _light() -> Theme:
    """Return the built-in light theme.

    Returns:
        The theme every other one is compared against.
    """
    return builtin_themes()["light"]


def _payload(**overrides: Any) -> dict[str, Any]:
    """Build a complete, valid theme payload with optional overrides.

    Args:
        **overrides: Top-level keys to replace.

    Returns:
        A theme dict ready to be written as JSON.
    """
    light = _light()
    payload: dict[str, Any] = {
        "version": 1,
        "id": "custom",
        "name": "Custom",
        "colors": dict(light.colors),
        "shape": {token: value for token, value in light.shape.items()},
        "font": {
            "family": list(light.font.family),
            "size_pt": light.font.size_pt,
            "letter_spacing": light.font.letter_spacing,
            "mono_family": list(light.font.mono_family),
            "mono_size_pt": light.font.mono_size_pt,
            "title_size_px": light.font.title_size_px,
            "small_size_pt": light.font.small_size_pt,
            "uppercase": light.font.uppercase,
        },
    }
    payload.update(overrides)
    return payload


def _write(tmp_path: Path, payload: Any, name: str = "theme.json") -> Path:
    """Write a payload as a theme file.

    Args:
        tmp_path: pytest's per-test directory.
        payload: What to serialise.
        name: File name to use.

    Returns:
        The path written.
    """
    target = tmp_path / name
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


# ── Rendering ─────────────────────────────────────────────────────────────────

def test_the_template_still_styles_everything_the_pre_theme_sheet_did() -> None:
    """Verify no rule was lost on the way from v0.3.0 to the token template.

    The baseline is the stylesheet as it stood before themes existed. It used
    to be compared line for line, which proved that token extraction was
    faithful -- a one-time question, and one that has since been answered. What
    it cannot keep proving is anything about colour: the built-in themes are
    art-directed now, and pinning their values here would only turn this into a
    hand-maintained changelog of deliberate edits.

    So the comparison is structural. Additions are free -- a theme system exists
    to add -- and every removal has to be one of the two that were meant.
    """
    baseline = _rules(
        (RESOURCE_DIR / "stylesheet_light_baseline.qss").read_text(encoding="utf-8")
    )

    rendered = _rules(render_stylesheet(_light()))

    assert set(baseline) <= set(rendered), "a selector was dropped"
    lost = {
        (selector, prop)
        for selector, props in baseline.items()
        for prop in props - rendered.get(selector, set())
    }
    assert lost == DELIBERATE_REMOVALS


def test_no_colour_literals_survive_in_the_stylesheet() -> None:
    """Verify the rendered sheet's colours all came from the theme."""
    rendered = render_stylesheet(_light())
    theme_colours = {value.lower() for value in _light().colors.values()}

    used = {match.lower() for match in re.findall(r"#[0-9a-fA-F]{6}", rendered)}

    assert used <= theme_colours


def test_zero_radius_squares_the_ui() -> None:
    """Verify geometry tokens really reach the stylesheet.

    This is what lets a panel-style theme drop decoui's rounded corners.
    """
    light = _light()
    squared = Theme(
        id="squared",
        name="Squared",
        colors=light.colors,
        shape={token: 0 for token in light.shape},
        font=light.font,
    )

    rendered = render_stylesheet(squared)

    assert "border-radius: 6px" not in rendered
    assert "border-radius: 0px" in rendered


# ── Built-in themes ───────────────────────────────────────────────────────────

def test_builtin_light_is_complete() -> None:
    """Verify the shipped theme defines every token this version knows."""
    light = _light()

    assert set(light.colors) == COLOR_TOKENS
    assert set(light.shape) == SHAPE_TOKENS
    assert light.font.family[-1] == "sans-serif"


def test_active_theme_falls_back_to_light() -> None:
    """Verify widgets built outside gui_main() still find a theme.

    Tests construct pages directly, so the fallback is what keeps them working.
    """
    assert active_theme().id == "light"


# ── Loading and validation ────────────────────────────────────────────────────

def test_load_theme_reads_a_valid_file(tmp_path: Path) -> None:
    """Verify a well-formed file round-trips into an equivalent theme."""
    path = _write(tmp_path, _payload())

    theme = load_theme(path)

    assert theme.id == "custom"
    assert theme.name == "Custom"
    assert theme.colors == _light().colors


@pytest.mark.parametrize(
    ("overrides", "needle"),
    [
        ({"version": 2}, "version"),
        ({"id": "Not Valid"}, "id"),
        ({"name": ""}, "name"),
        ({"extends": "nope"}, "extends"),
    ],
)
def test_invalid_header_fields_are_rejected(
    tmp_path: Path, overrides: dict[str, Any], needle: str
) -> None:
    """Verify header validation names the offending key.

    Args:
        tmp_path: pytest's per-test directory.
        overrides: The field to corrupt.
        needle: Text the message must contain.
    """
    path = _write(tmp_path, _payload(**overrides))

    with pytest.raises(ThemeError) as excinfo:
        load_theme(path)

    assert needle in str(excinfo.value)
    assert str(path) in str(excinfo.value)


def test_missing_required_key_is_rejected(tmp_path: Path) -> None:
    """Verify an absent top-level key is reported, not defaulted."""
    payload = _payload()
    del payload["id"]
    path = _write(tmp_path, payload)

    with pytest.raises(ThemeError, match="id"):
        load_theme(path)


def test_incomplete_colour_set_is_rejected(tmp_path: Path) -> None:
    """Verify a theme that is not extending another must define every token."""
    payload = _payload()
    payload["colors"].pop("accent")
    path = _write(tmp_path, payload)

    with pytest.raises(ThemeError, match="accent"):
        load_theme(path)


def test_unknown_token_is_rejected(tmp_path: Path) -> None:
    """Verify a typo'd token name fails loudly instead of being ignored.

    Silently dropping it is the failure mode this whole check exists to stop:
    the author would see no error and no effect.
    """
    payload = _payload()
    payload["colors"]["bg.surfase"] = "#ffffff"
    path = _write(tmp_path, payload)

    with pytest.raises(ThemeError, match="bg.surfase"):
        load_theme(path)


@pytest.mark.parametrize("value", ["red", "#fff", "#gggggg", 16777215])
def test_malformed_colour_is_rejected(tmp_path: Path, value: Any) -> None:
    """Verify only #rrggbb is accepted.

    Args:
        tmp_path: pytest's per-test directory.
        value: A spelling decoui deliberately does not support.
    """
    payload = _payload()
    payload["colors"]["accent"] = value
    path = _write(tmp_path, payload)

    with pytest.raises(ThemeError, match="accent"):
        load_theme(path)


def test_negative_geometry_is_rejected(tmp_path: Path) -> None:
    """Verify a negative radius is caught before Qt silently ignores it."""
    payload = _payload()
    payload["shape"]["shape.radius_control"] = -4
    path = _write(tmp_path, payload)

    with pytest.raises(ThemeError, match="radius_control"):
        load_theme(path)


def test_unparsable_file_is_rejected(tmp_path: Path) -> None:
    """Verify a syntax error is reported as a theme problem, not a crash."""
    path = tmp_path / "broken.json"
    path.write_text("{ not json", encoding="utf-8")

    with pytest.raises(ThemeError, match="not valid JSON"):
        load_theme(path)


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    """Verify an absent file raises ThemeError rather than OSError.

    Callers on the startup path catch ThemeError only; an OSError escaping here
    would abort startup over a deleted theme.
    """
    with pytest.raises(ThemeError):
        load_theme(tmp_path / "absent.json")


# ── extends ───────────────────────────────────────────────────────────────────

def test_extends_inherits_everything_not_overridden(tmp_path: Path) -> None:
    """Verify a partial theme is a real convenience, not a trap."""
    path = _write(tmp_path, {
        "version": 1,
        "id": "tinted",
        "name": "Tinted",
        "extends": "light",
        "colors": {"accent": "#ff0000"},
    })

    theme = load_theme(path)

    assert theme.colors["accent"] == "#ff0000"
    assert theme.colors["bg.app"] == _light().colors["bg.app"]
    assert set(theme.colors) == COLOR_TOKENS
    assert theme.font.family == _light().font.family


def test_extends_still_rejects_unknown_tokens(tmp_path: Path) -> None:
    """Verify inheriting does not switch off token-name checking."""
    path = _write(tmp_path, {
        "version": 1,
        "id": "tinted",
        "name": "Tinted",
        "extends": "light",
        "colors": {"accent.strong": "#ff0000"},
    })

    with pytest.raises(ThemeError, match="accent.strong"):
        load_theme(path)


# ── Widgets that style themselves in code ─────────────────────────────────────

@pytest.mark.parametrize("status", ["running", "success", "error", "cancelled"])
def test_status_badges_come_from_the_theme(status: str) -> None:
    """Verify no status badge carries a hard-coded colour.

    Args:
        status: The badge state under test.
    """
    style = _status_style(status)
    theme = active_theme()

    assert theme.colors[_STATUS_INK[status]] in style
    assert f"{theme.shape['shape.radius_pill']:g}px" in style
    assert any(colour in style for colour in theme.colors.values())


def test_status_badges_stay_distinguishable() -> None:
    """Verify the four run states never render as the same colour.

    A theme that collapsed them would make a failed run look like a good one.
    """
    styles = {
        status: _status_style(status)
        for status in ("running", "success", "error", "cancelled")
    }

    assert len(set(styles.values())) == 4


def test_tag_pills_come_from_the_theme() -> None:
    """Verify the tag bar's own stylesheet is themed, not hard-coded."""
    theme = active_theme()

    style = _pill_style()

    assert theme.colors["accent"] in style
    assert theme.colors["border.button"] in style
    assert f"{theme.shape['shape.radius_pill']:g}px" in style


def test_font_keys_are_exhaustive() -> None:
    """Verify FONT_KEYS matches what a theme file must supply.

    Sizes carry their unit in the name on purpose: the interface mixes point
    and pixel sizing, and silently converting one into the other would change
    how a theme renders without the theme saying so.
    """
    assert FONT_KEYS == {
        "family",
        "size_pt",
        "letter_spacing",
        "mono_family",
        "mono_size_pt",
        "title_size_px",
        "small_size_pt",
        "uppercase",
    }
