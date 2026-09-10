"""Theme definitions: the tokens a theme sets and the stylesheet they render to.

A theme is a small set of named values -- colours, geometry, typography -- that
the application stylesheet is built from. Themes ship as JSON so an end user can
add one without writing Python or rebuilding the application.

What a theme can and cannot change
----------------------------------

It changes **how existing widgets look**: colours, corner radii, border widths,
font family and spacing. It cannot add, remove or rearrange widgets, and it
cannot express gradients or bevels -- every colour token is one flat value.

Two parts of the UI deliberately do **not** follow the theme:

* The output console keeps its dark background and its per-level text colours
  (see :mod:`decoui.ui.log_window`). It reads as a terminal in every theme.
* Text casing. Qt's stylesheet dialect has no ``text-transform``, so a theme
  cannot upper-case labels; only the application's own strings decide that.

Token names are a public contract
---------------------------------

Theme files live on users' disks. Renaming a token silently breaks every custom
theme that sets it, which is why :data:`COLOR_TOKENS` and :data:`SHAPE_TOKENS`
are exhaustive and why every file carries a ``version``.

Identity: ``id`` vs ``name``
----------------------------

``id`` is the stable key -- persisted as the user's choice and used by
``extends``. ``name`` is only ever displayed, so a user may rename their own
theme without losing their selection.
"""
from __future__ import annotations

import json
import re
import traceback
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path
from string import Template
from typing import Any

#: Theme file format. Bumped only when the token set changes incompatibly.
SCHEMA_VERSION = 1

#: The theme used when nothing else applies, and the one every fallback lands
#: on. It is a built-in, so it is always available.
DEFAULT_THEME_ID = "light"

#: Settings key holding the theme id the user chose. It lives here rather than
#: beside the dialog that writes it because gui_main() reads the same key at
#: startup, and two spellings of one key fail silently: the choice is saved and
#: then never found again.
THEME_SETTING = "ui.theme"

#: A theme id: lowercase, digits and hyphens, starting with an alphanumeric.
_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")

#: Colours must be plain six-digit hex. No rgba(), no named colours, no
#: gradients -- one spelling keeps validation and theme authoring simple.
_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")

#: Every colour token, grouped by role.
COLOR_TOKENS: frozenset[str] = frozenset({
    # ── Surfaces, outermost first ────────────────────────────────────────────
    "bg.app",              # the window backdrop behind everything
    "bg.surface",          # a page or pane sitting on the backdrop
    "bg.topbar",           # the tag/settings bar across the top
    "bg.tab",              # an unselected tab
    "bg.tab_selected",     # the current tab, which reads as part of the page
    "bg.sidebar",          # the sidebar panel
    "bg.tree",             # the tool list inside it -- often inset from the panel
    "bg.tree_hover",
    "bg.tree_selected",    # decoupled from accent.soft: the tool list may want a
                           # filled dark selection while dropdowns and tables
                           # keep a light tint
    "bg.table",            # the history table
    "bg.header",           # its column headers
    "bg.gridline",
    # ── Controls ─────────────────────────────────────────────────────────────
    "bg.field",            # every text input, spin box, dropdown and check box
    "bg.button",
    "bg.button_hover",
    "bg.button_pressed",
    "bg.button_disabled",
    "bg.icon_hover",       # borderless icon buttons, e.g. a tab's close button
    "bg.icon_pressed",
    "bg.track",            # the progress bar's unfilled groove
    # ── Console ──────────────────────────────────────────────────────────────
    "bg.console",          # the output area, traditionally a dark terminal
    # ── Text, in descending emphasis ─────────────────────────────────────────
    "text.primary",
    "text.secondary",
    "text.muted",
    "text.disabled",
    "text.on_accent",      # over an accent fill: checked buttons, tag pills
    # One ink per filled control. They are separate because the fills they sit
    # on are chosen independently: a theme may want a bright Run button that
    # needs dark text while its Stop button stays dark and needs light text.
    "text.on_success",
    "text.on_danger",
    "text.on_neutral",
    "text.required",       # the asterisk marking a required field
    "text.link",           # cross-references in the Help window's pages. Its
                           # own token rather than `accent`: accent is a fill
                           # colour, and a link that matches the selection
                           # highlight reads as a selected thing, not a link.
    "text.button",
    "text.on_sidebar",     # the tool list -- separate so the sidebar may be dark
    "text.on_sidebar_selected",
    "text.on_topbar",      # likewise for the top bar, which may be a dark band
    "text.tab_selected",
    # ── Borders ──────────────────────────────────────────────────────────────
    "border.panel",        # around panels, tables and the sidebar
    "border.subtle",       # dividers that should barely register
    "border.field",
    "border.button",
    "border.button_hover",
    "border.button_disabled",
    "border.tab",
    "border.focus",        # the focused input's outline
    "border.console",      # the frame the console sits inside
    # ── Accent and semantics ─────────────────────────────────────────────────
    "accent",
    "accent.soft",         # selection fills
    "success", "success.hover",
    "danger", "danger.hover",
    "neutral",
    # ── Console log levels ───────────────────────────────────────────────────
    # One per level the log viewer knows. They live in the theme so a light
    # console is possible at all: the phosphor palette below only reads on a
    # dark ground.
    "console.stdout",
    "console.debug",
    "console.info",
    "console.warning",
    "console.error",
    "console.critical",
    # ── Scrollbars ───────────────────────────────────────────────────────────
    "scrollbar.handle",
    "scrollbar.handle_hover",
})

#: Geometry tokens. Setting the radii to 0 squares the whole UI off, which is
#: what separates the panel-style themes from the default rounded look.
SHAPE_TOKENS: frozenset[str] = frozenset({
    "shape.radius_bar",       # progress bar and its chunk
    "shape.radius_small",     # check indicator, tab close button, scrollbars
    # The console is a control, not a panel: it sits in the same column as the
    # buttons above it and is read as one framed element with them, so it
    # follows their radius rather than the table's.
    "shape.radius_control",   # buttons, inputs, dropdowns, tabs, tree rows, console
    "shape.radius_panel",     # tables and the description box
    "shape.radius_pill",      # tag pills and status badges
    "shape.border_width",
    "shape.border_width_emphasis",
    # Qt draws outset/inset borders as a bevel from the border colour alone, so
    # a panel look is reachable without the gradients this format cannot carry.
    "shape.border_style",
})

#: The border styles Qt renders. Anything else is refused rather than silently
#: dropped, since a misspelt style leaves a control with no border at all.
BORDER_STYLES: frozenset[str] = frozenset({
    "solid", "outset", "inset", "ridge", "groove", "double",
})

#: Required keys of the "font" object. Sizes carry their unit in the name: the
#: interface mixes point and pixel sizing and a theme should say which it means
#: rather than have one silently converted into the other.
FONT_KEYS: frozenset[str] = frozenset({
    "uppercase",        # render tags, tabs and buttons in capitals
    "family",           # base UI stack, used for everything but the console
    "size_pt",          # base UI size
    "letter_spacing",   # extra tracking, in pixels; 0 leaves the font alone
    "mono_family",      # the console and the log viewer
    "mono_size_pt",
    "title_size_px",    # a tool page's heading
    "small_size_pt",    # tag pills, the Output label, the console's own buttons
})


class ThemeError(ValueError):
    """Raised when a theme file cannot be read as a valid theme.

    Carries the offending file and key in its message: a theme is usually
    hand-written, so the message is the only debugging aid its author gets.
    """


@dataclass(frozen=True)
class FontSpec:
    """Typography for one theme.

    Attributes:
        family: Font families in preference order. Qt falls through them, so
            the last entry should be a generic family (``monospace``,
            ``sans-serif``) or the theme lands on Qt's default on machines that
            have none of the named faces.
        size_pt: Base point size for the application font.
        letter_spacing: Extra spacing in pixels. Qt applies this through the
            stylesheet; 0 leaves the font's own metrics alone.
        mono_family: Families for the console and the log viewer. Output is
            column-aligned by the tools that produce it, so this one has to
            stay monospaced whatever the rest of the theme does.
        mono_size_pt: Point size for that output.
        title_size_px: Pixel size of a tool page's heading.
        small_size_pt: Point size for secondary controls -- tag pills, the
            Output label, the console's Copy and View Log buttons.
        uppercase: Render tags, tab titles and button labels in capitals. Qt's
            stylesheet dialect has no ``text-transform``, so this is applied
            through the widget's font instead -- the underlying strings are
            never modified, which keeps tab titles matching tool ids.
    """

    family: tuple[str, ...]
    size_pt: int
    letter_spacing: float
    mono_family: tuple[str, ...]
    mono_size_pt: int
    title_size_px: int
    small_size_pt: int
    uppercase: bool


@dataclass(frozen=True)
class Theme:
    """One complete look: every token, resolved.

    A Theme is always complete -- ``extends`` is flattened at load time, so
    nothing here is ever a partial override.

    Attributes:
        id: Stable key. Persisted as the user's choice, referenced by
            ``extends``.
        name: Display name. Shown in the settings dialog and nowhere else.
        colors: Every token in :data:`COLOR_TOKENS`, mapped to ``#rrggbb``.
        shape: Every token in :data:`SHAPE_TOKENS`, in pixels.
        font: Typography for this theme.
    """

    id: str
    name: str
    colors: dict[str, str]
    shape: dict[str, float]
    font: FontSpec

    def placeholders(self) -> dict[str, str]:
        """Return the substitution mapping for the stylesheet template.

        Returns:
            ``$``-placeholder name to rendered value. Dots in token names become
            underscores, since ``$bg.app`` would end the placeholder at the dot.
            Pixel values arrive with their unit already attached.
        """
        values: dict[str, str] = {
            token.replace(".", "_"): value for token, value in self.colors.items()
        }
        for token, number in self.shape.items():
            key = token.replace(".", "_")
            if isinstance(number, str):
                values[key] = number
            else:
                values[key] = f"{number:g}px"
        values["font_letter_spacing"] = f"{self.font.letter_spacing:g}px"
        values["font_family"] = ", ".join(self.font.family)
        values["font_size"] = f"{self.font.size_pt:g}pt"
        values["font_mono_family"] = ", ".join(self.font.mono_family)
        values["font_mono_size"] = f"{self.font.mono_size_pt:g}pt"
        values["font_title_size"] = f"{self.font.title_size_px:g}px"
        values["font_small_size"] = f"{self.font.small_size_pt:g}pt"
        return values


def _require(mapping: Any, key: str, source: str) -> Any:
    """Read a required key, reporting the file when it is missing.

    Args:
        mapping: The object being validated.
        key: The key that must be present.
        source: File path, for the error message.

    Returns:
        The value stored under the key.

    Raises:
        ThemeError: If the value is not a mapping or the key is absent.
    """
    if not isinstance(mapping, dict):
        raise ThemeError(f"{source}: expected an object, got {type(mapping).__name__}")
    if key not in mapping:
        raise ThemeError(f"{source}: missing required key '{key}'")
    return mapping[key]


def _check_tokens(
    values: Any, allowed: frozenset[str], group: str, source: str, *, complete: bool
) -> dict[str, Any]:
    """Validate one token group against the names this version defines.

    Args:
        values: The group's object from the file.
        allowed: The tokens this version knows.
        group: Group name, for messages.
        source: File path, for messages.
        complete: Whether every token must be present. False for a theme that
            extends another and only overrides part of it.

    Returns:
        The validated group.

    Raises:
        ThemeError: On an unknown token name, or a missing one when complete.
    """
    if not isinstance(values, dict):
        raise ThemeError(f"{source}: '{group}' must be an object")
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ThemeError(
            f"{source}: unknown {group} token(s) {unknown}; "
            f"this decoui defines {sorted(allowed)}"
        )
    if complete:
        missing = sorted(allowed - set(values))
        if missing:
            raise ThemeError(f"{source}: '{group}' is missing {missing}")
    return values


def _check_colors(values: dict[str, Any], source: str) -> dict[str, str]:
    """Verify every colour is a six-digit hex string.

    Args:
        values: The validated colour group.
        source: File path, for messages.

    Returns:
        The same mapping, narrowed to str values.

    Raises:
        ThemeError: If any value is not ``#rrggbb``.
    """
    for token, value in values.items():
        if not isinstance(value, str) or not _COLOR_PATTERN.match(value):
            raise ThemeError(
                f"{source}: colors['{token}'] must be '#rrggbb', got {value!r}"
            )
    return dict(values)


def _check_shape(values: dict[str, Any], source: str) -> dict[str, float]:
    """Verify every geometry value is a non-negative number.

    Args:
        values: The validated shape group.
        source: File path, for messages.

    Returns:
        The same mapping, narrowed to numbers.

    Raises:
        ThemeError: If any value is not a number, or is negative.
    """
    result: dict[str, float] = {}
    for token, value in values.items():
        if token == "border_style" or token.endswith(".border_style"):
            if value not in BORDER_STYLES:
                raise ThemeError(
                    f"{source}: shape['{token}'] must be one of "
                    f"{sorted(BORDER_STYLES)}, got {value!r}"
                )
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ThemeError(
                f"{source}: shape['{token}'] must be a number, got {value!r}"
            )
        if value < 0:
            raise ThemeError(f"{source}: shape['{token}'] must not be negative")
        result[token] = float(value)
    return {**{k: v for k, v in values.items() if k not in result}, **result}


def _check_font(values: Any, source: str, *, complete: bool) -> dict[str, Any]:
    """Validate the font object.

    Args:
        values: The file's "font" object.
        source: File path, for messages.
        complete: Whether all keys must be present.

    Returns:
        The validated object.

    Raises:
        ThemeError: On unknown or missing keys, or a malformed family list.
    """
    if not isinstance(values, dict):
        raise ThemeError(f"{source}: 'font' must be an object")
    unknown = sorted(set(values) - FONT_KEYS)
    if unknown:
        raise ThemeError(f"{source}: unknown font key(s) {unknown}")
    if complete:
        missing = sorted(FONT_KEYS - set(values))
        if missing:
            raise ThemeError(f"{source}: 'font' is missing {missing}")
    for key in ("family", "mono_family"):
        if key not in values:
            continue
        family = values[key]
        if not isinstance(family, list) or not family:
            raise ThemeError(f"{source}: font['{key}'] must be a non-empty list")
        if not all(isinstance(item, str) for item in family):
            raise ThemeError(f"{source}: font['{key}'] must hold strings")
    if "uppercase" in values and not isinstance(values["uppercase"], bool):
        raise ThemeError(f"{source}: font['uppercase'] must be true or false")
    for key in ("size_pt", "mono_size_pt", "title_size_px", "small_size_pt"):
        if key in values and (
            isinstance(values[key], bool)
            or not isinstance(values[key], (int, float))
            or values[key] <= 0
        ):
            raise ThemeError(f"{source}: font['{key}'] must be a positive number")
    # Checked separately from the sizes: 0 means "leave the font alone" and a
    # negative value tightens, so the positive-number rule does not apply.
    if "letter_spacing" in values and (
        isinstance(values["letter_spacing"], bool)
        or not isinstance(values["letter_spacing"], (int, float))
    ):
        raise ThemeError(f"{source}: font['letter_spacing'] must be a number")
    return values


def _theme_from_payload(payload: Any, source: str) -> Theme:
    """Build a Theme from parsed JSON, resolving ``extends``.

    Args:
        payload: The parsed file contents.
        source: File path, for messages.

    Returns:
        A complete Theme.

    Raises:
        ThemeError: If anything about the file is invalid.
    """
    version = _require(payload, "version", source)
    if version != SCHEMA_VERSION:
        raise ThemeError(
            f"{source}: 'version' is {version!r}, this decoui reads {SCHEMA_VERSION}"
        )

    theme_id = _require(payload, "id", source)
    if not isinstance(theme_id, str) or not _ID_PATTERN.match(theme_id):
        raise ThemeError(
            f"{source}: 'id' must be lowercase letters, digits and hyphens, "
            f"got {theme_id!r}"
        )
    name = _require(payload, "name", source)
    if not isinstance(name, str) or not name.strip():
        raise ThemeError(f"{source}: 'name' must be a non-empty string")

    unknown_keys = sorted(set(payload) - {"version", "id", "name", "extends",
                                          "colors", "shape", "font"})
    if unknown_keys:
        raise ThemeError(f"{source}: unknown top-level key(s) {unknown_keys}")

    # `extends` always resolves against the themes shipped with decoui, never
    # against whatever is currently loaded: a file dropped into the user's theme
    # directory must not be able to change what another theme inherits.
    base = payload.get("extends")
    if base is not None:
        if not isinstance(base, str):
            raise ThemeError(f"{source}: 'extends' must be a theme id")
        builtins = builtin_themes()
        if base not in builtins:
            raise ThemeError(
                f"{source}: 'extends' names unknown built-in theme {base!r}; "
                f"available: {sorted(builtins)}"
            )
        parent = builtins[base]
        colors, shape = dict(parent.colors), dict(parent.shape)
        font = {
            "family": list(parent.font.family),
            "size_pt": parent.font.size_pt,
            "letter_spacing": parent.font.letter_spacing,
            "mono_family": list(parent.font.mono_family),
            "mono_size_pt": parent.font.mono_size_pt,
            "title_size_px": parent.font.title_size_px,
            "small_size_pt": parent.font.small_size_pt,
            "uppercase": parent.font.uppercase,
        }
    else:
        colors, shape, font = {}, {}, {}

    complete = base is None
    colors.update(_check_colors(
        _check_tokens(payload.get("colors", {}), COLOR_TOKENS, "colors", source,
                      complete=complete),
        source,
    ))
    shape.update(_check_shape(
        _check_tokens(payload.get("shape", {}), SHAPE_TOKENS, "shape", source,
                      complete=complete),
        source,
    ))
    font.update(_check_font(payload.get("font", {}), source, complete=complete))

    return Theme(
        id=theme_id,
        name=name,
        colors=colors,
        shape=shape,
        font=FontSpec(
            family=tuple(font["family"]),
            size_pt=int(font["size_pt"]),
            letter_spacing=float(font["letter_spacing"]),
            mono_family=tuple(font["mono_family"]),
            mono_size_pt=int(font["mono_size_pt"]),
            title_size_px=int(font["title_size_px"]),
            small_size_pt=int(font["small_size_pt"]),
            uppercase=bool(font["uppercase"]),
        ),
    )


def load_theme(path: str | Path, *, encoding: str = "utf-8") -> Theme:
    """Read one theme file.

    Args:
        path: The ``.json`` file to read.
        encoding: Text encoding of the file.

    Returns:
        The theme it defines.

    Raises:
        ThemeError: If the file is unreadable, is not text in ``encoding``, is
            not JSON, or is not a valid theme. Callers on the startup path must
            catch this -- a broken theme is never a reason to refuse to start.
            Nothing else escapes: every way one file can be bad has to arrive
            as a ThemeError, or discover_themes() loses the whole directory
            instead of skipping the one file.
    """
    source = str(path)
    try:
        raw = Path(path).read_text(encoding=encoding)
    except OSError as exc:
        raise ThemeError(f"{source}: cannot be read ({exc})") from exc
    except UnicodeDecodeError as exc:
        # The common way in: an editor that defaults to the system code page
        # rather than UTF-8, which only shows up once the file has a non-ASCII
        # character in it -- typically an accented theme name.
        raise ThemeError(
            f"{source}: is not valid {encoding} text ({exc}); save it as UTF-8"
        ) from exc
    except LookupError as exc:
        raise ThemeError(f"{source}: unknown encoding {encoding!r} ({exc})") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ThemeError(f"{source}: not valid JSON ({exc})") from exc
    return _theme_from_payload(payload, source)


@cache
def _builtin_themes() -> dict[str, Theme]:
    """Read and validate the bundled themes once per process.

    The files ship inside the package, so they cannot change while decoui is
    running and there is nothing to invalidate. Callers go through
    :func:`builtin_themes`, which hands out a copy.

    Returns:
        Theme id to Theme, for every ``.json`` under ``decoui/themes``.

    Raises:
        ThemeError: If a bundled theme is invalid. Unlike a user's theme this
            is a packaging defect, so it is not survivable.
    """
    themes: dict[str, Theme] = {}
    package = resources.files(__package__).joinpath("themes")
    for entry in sorted(package.iterdir(), key=lambda item: item.name):
        if not entry.name.endswith(".json"):
            continue
        payload = json.loads(entry.read_text(encoding="utf-8"))
        theme = _theme_from_payload(payload, f"<built-in {entry.name}>")
        themes[theme.id] = theme
    return themes


def builtin_themes() -> dict[str, Theme]:
    """Return the themes shipped inside the package.

    Returns:
        A fresh mapping of theme id to Theme. The mapping is the caller's --
        :func:`discover_themes` adds the user's themes straight into it -- but
        the Theme objects in it are shared and must be treated as read-only.
        Nothing in decoui writes to a Theme: ``extends`` copies the parent's
        ``colors`` and ``shape`` before overriding them.

    Raises:
        ThemeError: If a bundled theme is invalid.
    """
    return dict(_builtin_themes())


@dataclass(frozen=True)
class ThemeProblem:
    """One theme that could not be used, reported without stopping startup.

    Deliberately mirrors runner.StartupProblem's shape so gui_main() can fold
    these into the same dialog. It is defined here rather than imported so this
    module stays free of any dependency on the runner.

    Attributes:
        source: What failed, in user-facing terms -- normally the file path.
        summary: One line explaining the problem.
        detail: Full traceback, shown behind the dialog's Details button.
    """

    source: str
    summary: str
    detail: str


def default_theme_dir() -> Path:
    """Return the directory decoui reads user-supplied themes from.

    Returns:
        ``~/.decoui/themes``, next to the history database.

    Note:
        The directory is **not** created. An empty one in every user's home
        would be litter for the majority who never write a theme.
    """
    return Path.home() / ".decoui" / "themes"


def _user_theme_dir(theme_dir: str | Path | None) -> Path:
    """Resolve the directory a caller named for its user themes.

    ``~`` is expanded, because the obvious thing to pass -- and what the README
    shows -- is the string ``"~/.decoui/themes"``. Without this it would become
    a *relative* ``./~/.decoui/themes``, which simply does not exist, and a
    missing theme directory is not an error: the user would get no themes and no
    message saying why.

    Args:
        theme_dir: What the caller passed, or None for the default.

    Returns:
        The directory to scan.
    """
    if theme_dir is None:
        return default_theme_dir()
    return Path(theme_dir).expanduser()


def discover_themes(
    theme_dir: str | Path | None = None,
) -> tuple[dict[str, Theme], list[ThemeProblem]]:
    """Collect every usable theme: the built-in ones plus the user's.

    Args:
        theme_dir: Directory of user themes. Defaults to
            :func:`default_theme_dir`. A missing directory is not an error.

    Returns:
        A ``(themes, problems)`` pair. ``themes`` maps id to Theme and always
        contains at least the built-ins. ``problems`` lists the files that
        could not be used and the ids two *user* files both claimed -- never a
        reason to stop, only something to tell the user about afterwards.

    Note:
        A user theme with the same id as a built-in replaces it in this mapping,
        silently: that is the supported way to re-skin a built-in, and reporting
        it would mean a dialog on every launch for as long as the file exists.
        ``extends`` still resolves against the built-in (see :func:`load_theme`),
        so dropping a file into this directory cannot change what somebody
        else's theme inherits.

        Files are read in filename order so two themes claiming one id resolve
        the same way on every run.
    """
    themes = builtin_themes()
    origins = {theme_id: "built-in" for theme_id in themes}
    problems: list[ThemeProblem] = []

    directory = _user_theme_dir(theme_dir)
    if not directory.is_dir():
        return themes, problems

    for path in sorted(directory.glob("*.json")):
        try:
            theme = load_theme(path)
        except ThemeError as exc:
            problems.append(ThemeProblem(
                source=f"Theme file {path}",
                summary=str(exc),
                detail=traceback.format_exc(),
            ))
            continue
        # Taking over a built-in id is a supported thing to do -- it is how a
        # user re-skins the theme decoui starts on -- so it is silent. Two of
        # the user's *own* files claiming one id is not: one of them loses, the
        # choice is alphabetical, and nothing else would say which.
        if theme.id in themes and origins[theme.id] != "built-in":
            problems.append(ThemeProblem(
                source=f'Theme "{theme.id}"',
                summary=(
                    f"{path} replaces {origins[theme.id]}, which claims the "
                    f"same id"
                ),
                detail=f"previous: {origins[theme.id]}\nreplacement: {path}",
            ))
        themes[theme.id] = theme
        origins[theme.id] = str(path)

    return themes, problems


def resolve_theme(
    themes: dict[str, Theme], requested: str | None
) -> tuple[Theme, list[ThemeProblem]]:
    """Pick the theme to run under, falling back rather than failing.

    Args:
        themes: Everything :func:`discover_themes` found.
        requested: The wanted theme id, or None to take the default.

    Returns:
        A ``(theme, problems)`` pair. The theme is always usable.

    Note:
        A request naming a theme that is not there is reported and then ignored.
        The stored preference is **not** cleared: the file may be missing only
        on this machine, and clearing it would quietly lose a choice the user
        would expect back once the file reappears.
    """
    problems: list[ThemeProblem] = []
    if requested and requested in themes:
        return themes[requested], problems
    if requested:
        problems.append(ThemeProblem(
            source=f'Theme "{requested}"',
            summary=(
                f"no theme with id {requested!r} is available; falling back to "
                f"{DEFAULT_THEME_ID!r}. Available: {sorted(themes)}"
            ),
            detail=f"requested: {requested}\navailable: {sorted(themes)}",
        ))
    return themes[DEFAULT_THEME_ID], problems


#: The theme the application is currently running under. decoui applies a theme
#: once at startup and never swaps it, so widgets built later read it from here
#: rather than having it threaded through every constructor. This mirrors how
#: `storage.db` keeps the database path.
_ACTIVE_THEME: Theme | None = None


#: The directory user themes were read from at startup. The settings dialog has
#: to scan the same one gui_main() did, and it has no other way to learn it.
_ACTIVE_THEME_DIR: Path | None = None


def set_active_theme_dir(theme_dir: str | Path | None) -> None:
    """Record which directory user themes were loaded from.

    Args:
        theme_dir: The directory gui_main() was given, or None for the default.
    """
    global _ACTIVE_THEME_DIR
    # Expanded here too, so the settings dialog scans the directory
    # discover_themes() actually read rather than the literal string.
    _ACTIVE_THEME_DIR = Path(theme_dir).expanduser() if theme_dir is not None else None


def active_theme_dir() -> Path:
    """Return the directory user themes are read from.

    Returns:
        The directory recorded by :func:`set_active_theme_dir`, or
        :func:`default_theme_dir` when the application did not name one.
    """
    if _ACTIVE_THEME_DIR is None:
        return default_theme_dir()
    return _ACTIVE_THEME_DIR


def set_active_theme(theme: Theme) -> None:
    """Record the theme the application is running under.

    Called from gui_main() before any widget is built, and again from
    :func:`decoui.ui.retheme.retheme_application` when the user picks a
    different one. It records; applying the theme is the caller's job.

    Args:
        theme: The theme whose stylesheet was applied.
    """
    global _ACTIVE_THEME
    _ACTIVE_THEME = theme


def active_theme() -> Theme:
    """Return the running theme, for widgets that style themselves in code.

    Most styling comes from the application stylesheet. A few widgets set their
    own -- status badges, tag pills -- and read their colours from here.

    Returns:
        The theme set by :func:`set_active_theme`, or the built-in default when
        nothing has been applied. The fallback matters for tests and for any
        tool page built outside gui_main().

    Note:
        Called from the log console's per-line path, so the fallback reads the
        cached built-ins directly rather than through :func:`builtin_themes`,
        which would copy the mapping only to index one key out of it.
    """
    if _ACTIVE_THEME is None:
        return _builtin_themes()[DEFAULT_THEME_ID]
    return _ACTIVE_THEME


def theme_font(theme: Theme):
    """Build the application font a theme asks for.

    The families are tried in order and Qt falls back through them, so the same
    theme renders on Windows, macOS and Linux without per-platform code.

    Args:
        theme: The theme supplying the family stack and point size.

    Returns:
        A QFont ready for ``QApplication.setFont``.
    """
    from PySide6.QtGui import QFont

    font = QFont()
    font.setFamilies(list(theme.font.family))
    font.setPointSize(theme.font.size_pt)
    return font


def apply_label_case(widget) -> None:
    """Render a widget's label in the case the theme asks for.

    Qt's stylesheet dialect has no ``text-transform``, so this goes through the
    font instead. The widget's ``text()`` is left alone -- only its rendering
    changes -- which matters because tab titles double as lookup keys and a tag
    pill's text is the tag itself.

    Both cases are set, not just capitals: switching from an uppercase theme to
    a mixed-case one has to be able to undo what the first one did, and a
    widget's font keeps whatever capitalization was last written to it.

    Only widgets that disagree with the theme are touched. ``setFont`` marks a
    widget's font as its own and stops it inheriting the application's, so a
    theme that never asked for capitals leaves every font exactly as Qt
    resolved it.

    Args:
        widget: Any widget with a font. Applied to it and to every push button
            and tab bar beneath it.

    Note:
        Under a re-theme this must run **after** the new stylesheet is
        installed. The QSS ``QWidget`` rule pins each control's family and
        size, which is what stops the capitals reaching the console and the
        input fields; run first, it has nothing to be pinned by.
    """
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QPushButton, QTabBar

    wanted = (
        QFont.Capitalization.AllUppercase
        if active_theme().font.uppercase
        else QFont.Capitalization.MixedCase
    )
    targets = [widget]
    targets += widget.findChildren(QPushButton)
    targets += widget.findChildren(QTabBar)
    for target in targets:
        font = target.font()
        if font.capitalization() == wanted:
            continue
        font.setCapitalization(wanted)
        target.setFont(font)


def render_stylesheet(theme: Theme) -> str:
    """Build the application stylesheet for a theme.

    Args:
        theme: The theme to render.

    Returns:
        A complete Qt stylesheet.

    Raises:
        KeyError: If the template references a token the theme lacks, which can
            only happen if the template and the token sets drift apart.
    """
    return _STYLESHEET_TEMPLATE.substitute(theme.placeholders())


# The stylesheet is a string.Template rather than an f-string or str.format
# target: QSS is full of braces, and `$` never appears in it, so `$token` is the
# only placeholder syntax that does not collide with the language itself.
_STYLESHEET_TEMPLATE = Template("""
QWidget {
    background-color: $bg_app;
    color: $text_primary;
    font-family: $font_family;
    font-size: $font_size;
    letter-spacing: $font_letter_spacing;
}
QMainWindow > QWidget,
QStackedWidget > QWidget {
    background-color: $bg_surface;
}
/* Top bar */
QWidget#tagBar {
    background-color: $bg_topbar;
    color: $text_on_topbar;
    border-bottom: $shape_border_width solid $border_panel;
}
/* Sidebar */
QWidget#sidebar {
    background-color: $bg_sidebar;
    border-right: $shape_border_width solid $border_subtle;
}
QWidget#sidebar QLineEdit {
    background-color: $bg_field;
}
/* Tree */
QTreeWidget {
    background-color: $bg_tree;
    color: $text_on_sidebar;
    border: none;
    outline: none;
    padding: 2px;
}
QTreeWidget::item {
    padding: 4px 6px;
    border-radius: $shape_radius_control;
}
QTreeWidget::item:hover {
    background-color: $bg_tree_hover;
}
QTreeWidget::item:selected {
    background-color: $bg_tree_selected;
    color: $text_on_sidebar_selected;
}
/* Splitter */
QSplitter::handle:horizontal {
    background-color: $bg_app;
    border-left: $shape_border_width solid $border_subtle;
}
QSplitter::handle:horizontal:hover {
    background-color: $accent_soft;
}
/* Tabs */
QTabWidget::pane {
    border: none;
    background-color: $bg_surface;
}
/* The tab widget runs in document mode, where Qt renders neither the pane
   frame nor a border on the tab bar. The line separating the tab row from the
   page is therefore drawn by the page itself -- see ToolPage._build_ui. */
QTabBar::tab {
    background-color: $bg_tab;
    border: $shape_border_width $shape_border_style $border_tab;
    border-bottom: none;
    border-top-left-radius: $shape_radius_control;
    border-top-right-radius: $shape_radius_control;
    padding: 7px 12px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: $bg_tab_selected;
    color: $text_tab_selected;
}
/* Close affordance installed by MainWindow; Qt's built-in one is unusable here
   because styling QTabBar::tab stops it being painted on the selected tab and
   its position cannot be nudged in from the tab edge. */
QToolButton#tabCloseButton {
    background-color: transparent;
    border: none;
    border-radius: $shape_radius_small;
}
QToolButton#tabCloseButton:hover {
    background-color: $bg_icon_hover;
}
QToolButton#tabCloseButton:pressed {
    background-color: $bg_icon_pressed;
}
/* Buttons */
QPushButton {
    background-color: $bg_button;
    border: $shape_border_width $shape_border_style $border_button;
    border-radius: $shape_radius_control;
    padding: 4px 14px;
    color: $text_button;
    min-height: 26px;
}
QPushButton:hover {
    background-color: $bg_button_hover;
    border-color: $border_button_hover;
}
QPushButton:pressed {
    background-color: $bg_button_pressed;
}
QPushButton:checked {
    background-color: $accent;
    color: $text_on_accent;
    border-color: $accent;
}
QPushButton:disabled {
    color: $text_disabled;
    border-color: $border_button_disabled;
    background-color: $bg_button_disabled;
}
QPushButton#run_btn {
    background-color: $success;
    color: $text_on_success;
    border-color: $success;
    font-weight: bold;
}
QPushButton#run_btn:hover {
    background-color: $success_hover;
    border-color: $success_hover;
}
QPushButton#stop_btn {
    background-color: $danger;
    color: $text_on_danger;
    border-color: $danger;
}
QPushButton#stop_btn:hover {
    background-color: $danger_hover;
    border-color: $danger_hover;
}
/* Inputs */
QLineEdit {
    background-color: $bg_field;
    border: $shape_border_width solid $border_field;
    border-radius: $shape_radius_control;
    padding: 4px 8px;
    min-height: 24px;
}
QLineEdit:focus {
    border-color: $border_focus;
}
QTextEdit {
    background-color: $bg_field;
    border: $shape_border_width solid $border_field;
    border-radius: $shape_radius_control;
    padding: 4px 8px;
}
QTextEdit:focus {
    border-color: $border_focus;
}
QSpinBox, QDoubleSpinBox {
    background-color: $bg_field;
    border: $shape_border_width solid $border_field;
    border-radius: $shape_radius_control;
    padding: 3px 8px 3px 8px;
    min-height: 26px;
}
QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: $border_focus;
}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    width: 0;
    border: none;
    background: none;
}
QComboBox {
    background-color: $bg_field;
    border: $shape_border_width solid $border_field;
    border-radius: $shape_radius_control;
    padding: 3px 8px;
    min-height: 26px;
}
QComboBox:focus {
    border-color: $border_focus;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: $bg_field;
    border: $shape_border_width solid $border_field;
    selection-background-color: $accent_soft;
    selection-color: $text_primary;
    outline: none;
}
QCheckBox {
    spacing: 6px;
    background: transparent;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: $shape_border_width_emphasis solid $border_field;
    border-radius: $shape_radius_small;
    background: $bg_field;
}
QCheckBox::indicator:checked {
    background-color: $accent;
    border-color: $accent;
}
/* Progress */
QProgressBar {
    border: none;
    border-radius: $shape_radius_bar;
    background-color: $bg_track;
}
QProgressBar::chunk {
    background-color: $accent;
    border-radius: $shape_radius_bar;
}
/* Table */
QTableWidget {
    background-color: $bg_table;
    border: $shape_border_width solid $border_subtle;
    border-radius: $shape_radius_panel;
    gridline-color: $bg_gridline;
    outline: none;
}
QHeaderView::section {
    background-color: $bg_header;
    border: none;
    border-bottom: $shape_border_width solid $border_subtle;
    padding: 6px 8px;
    font-weight: bold;
    color: $text_muted;
}
QTableWidget::item {
    padding: 4px 8px;
}
QTableWidget::item:selected {
    background-color: $accent_soft;
    color: $text_primary;
}
/* Scrollbars */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: $scrollbar_handle;
    border-radius: $shape_radius_small;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: $scrollbar_handle_hover;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: $scrollbar_handle;
    border-radius: $shape_radius_small;
    min-width: 24px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
""")
