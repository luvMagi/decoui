"""decoui's own interface text, in whatever language the user picked.

This covers the strings decoui itself puts on screen -- Run, Stop, the history
columns, the settings dialog. It does **not** cover a tool's own label,
description or docstring: those belong to the application that wrote the tool,
and decoui has no business translating them.

A catalogue is one JSON file per language, ``<code>.json``, next to this module.
Adding a language means dropping a file in; nothing here has to change. English
is the source language, so ``en.json`` is the only catalogue guaranteed to be
complete -- every other one falls back to it key by key, which means a partial
translation shows translated text where it exists and English where it does not,
rather than failing.

Like the theme, the language is applied once at startup and not swapped in a
running window: widgets read their text when they are built, so a live swap
would leave every already-built label stale. See :func:`decoui.i18n.set_language`.
"""
from __future__ import annotations

import json
from functools import cache
from importlib import resources

#: The language decoui is written in, and the fallback for every key that a
#: another catalogue does not translate.
DEFAULT_LANGUAGE = "en"

#: Settings key holding the chosen language code. Mirrors THEME_SETTING; both
#: are read once at startup by gui_main().
LANGUAGE_SETTING = "ui.language"

#: Key holding a language's own name for itself, used to label it in the
#: settings dropdown. A reader looking for their language recognises
#: "Deutsch", not "German".
_ENDONYM_KEY = "language.name"


@cache
def _catalogue(language: str) -> dict[str, str]:
    """Read one language's catalogue, once per process.

    Args:
        language: The language code, i.e. the filename without ``.json``.

    Returns:
        Key to translated string, or an empty mapping when the file is absent
        or unreadable. A broken catalogue must not stop the application: text
        is presentation, and English is always there to fall back on.
    """
    source = resources.files(__package__).joinpath(f"{language}.json")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(k): str(v) for k, v in payload.items()}


def available_languages() -> list[str]:
    """Return the language codes that have a catalogue.

    Returns:
        Sorted codes, always including :data:`DEFAULT_LANGUAGE`.
    """
    root = resources.files(__package__)
    codes = {
        entry.name.removesuffix(".json")
        for entry in root.iterdir()
        if entry.name.endswith(".json")
    }
    codes.add(DEFAULT_LANGUAGE)
    return sorted(codes)


def language_name(language: str) -> str:
    """Return a language's name for itself, for the settings dropdown.

    Args:
        language: The code to name.

    Returns:
        The catalogue's own ``language.name``, or the bare code when it does
        not declare one.
    """
    return _catalogue(language).get(_ENDONYM_KEY) or language


#: The language in effect. Set once by gui_main() before any widget is built,
#: exactly as the active theme is. None means "nothing applied yet", which is
#: the case in tests and anywhere a widget is built outside gui_main().
_ACTIVE_LANGUAGE: str | None = None


def set_language(language: str | None) -> None:
    """Record the language the application is running under.

    Called once, from gui_main(), before any widget exists. decoui does not
    re-translate a running window -- widgets read their text as they are built,
    so a swap would leave everything already on screen in the old language.
    Changing language means restarting, which is what the settings dialog says.

    Args:
        language: The code to use, or None to fall back to English.
    """
    global _ACTIVE_LANGUAGE
    _ACTIVE_LANGUAGE = language or DEFAULT_LANGUAGE


def active_language() -> str:
    """Return the language in effect.

    Returns:
        The code set by :func:`set_language`, or :data:`DEFAULT_LANGUAGE` when
        nothing has been applied.
    """
    return _ACTIVE_LANGUAGE or DEFAULT_LANGUAGE


def t(key: str, /, **fields: object) -> str:
    """Return one interface string in the active language.

    Args:
        key: Catalogue key, e.g. ``'tool.run'``.
        **fields: Values for the string's ``{placeholders}``.

    Returns:
        The translated text. Never raises, and never returns nothing:

        * a key missing from the active catalogue falls back to English
        * a key missing from English too returns the key itself, which is ugly
          on screen and therefore gets reported rather than passing unnoticed
        * a string whose placeholders do not match ``fields`` is returned
          unformatted, so a translator's typo costs one bad label rather than a
          crash in the middle of the interface
    """
    language = active_language()
    text = _catalogue(language).get(key)
    if text is None and language != DEFAULT_LANGUAGE:
        text = _catalogue(DEFAULT_LANGUAGE).get(key)
    if text is None:
        return key
    if not fields:
        return text
    try:
        return text.format(**fields)
    except (KeyError, IndexError, ValueError):
        return text
