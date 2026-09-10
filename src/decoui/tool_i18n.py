"""Translations for an **application's own** tool text.

:mod:`decoui.i18n` covers the strings decoui itself puts on screen -- Run, Stop,
the history columns. This module covers the other half: the labels, descriptions
and field text an application writes into its own ``@toolset`` and ``@tool``
declarations. decoui cannot translate those from its own catalogues, because it
has never seen them.

Why it cannot be done in the decorator
--------------------------------------

The obvious thing to write is ``@tool(label=t("my.key"))``, and it does not
work: a decorator's arguments are evaluated when the module is **imported**, and
an application imports its toolsets before it calls :func:`decoui.gui_main`,
which is what settles the language. The label would resolve against whatever
language happened to be active at import -- in practice always the default.

So the strings stay in the source in whatever language they were written in, and
this module replaces them later, in :func:`decoui.registry.build_tree`. That
runs after ``set_language()``, and everything downstream -- the sidebar, tab
titles, form labels, the Help panel, the tool name on a history row -- is built
from what it returns. One substitution reaches all of them.

The catalogue
-------------

One JSON file per language in a directory the application names::

    gui_main(toolsets=[...], i18n_dir="i18n")

    i18n/ja-JP.json
    i18n/zh-CN.json

Keys are the identity decoui already uses everywhere else: ``ClassName`` for a
toolset, ``ClassName.method`` for a tool -- the same keys a help page writes a
cross-reference to. One identity, not a second naming scheme to keep in step.

::

    {
      "FieldTools": {
        "label": "フィールド",
        "description": "注釈とウィジェットの対応。",
        "brief": "どの注釈がどのウィジェットになるか。"
      },
      "FieldTools.all_widgets": {
        "label": "すべてのウィジェット",
        "description": "対応しているすべての型のフィールドを 1 つずつ。",
        "brief": "各フィールドの入力内容を返します。",
        "returns": "受け取った値の要約。",
        "raises": "RuntimeError: 指定されたステップに達したとき。",
        "params": {
          "text":  {"label": "テキスト", "placeholder": "文字列", "brief": "必須項目。"},
          "ratio": {"label": "比率 (0-1)"}
        }
      }
    }

Every field is optional, at every level. A key that is absent leaves the string
the source wrote, so a half-finished catalogue yields a half-translated
interface rather than a broken one -- the same guarantee decoui's own
catalogues give.

Where each field lands
----------------------

=================  ==========================================================
``label``          the sidebar, the tab title, the page heading. From
                   ``@toolset(label=)`` / ``@tool(label=)``.
``description``    the bordered box under a tool's title. From
                   ``@tool(description=)``.
``brief``          the one-line summary: the Help page's subtitle and the row
                   in a contents table. From the **docstring's first line**.
``prose``          the paragraphs under it. From the **docstring's body**. A
                   tool that declares ``help=`` and has a file for this
                   language uses that file instead: Markdown is the richer
                   route and wins, and this one is for the common case of two
                   sentences that would be more ceremony than text in a file
                   of their own. A **toolset** has no ``help=``, so for a group
                   page this is the only route.
``returns``        the Help page's *Returns* section. From ``Returns:``.
``raises``         the Help page's *Raises* section. From ``Raises:``.
``params.<name>``  ``label`` and ``placeholder`` are the form's field text,
                   from ``@tool(labels=/placeholders=)`` or from ``F`` on the
                   annotation. ``brief`` is the field's row in the Help page's
                   parameter table, from that parameter's ``Args:`` entry.
=================  ==========================================================

The first two are decorator arguments, and could in principle have been written
in the source in every language at once. The rest come from the **docstring**,
which cannot: a docstring is one piece of text in one language, and it is also
the API documentation the developer reads. Translating it in the catalogue is
what lets both audiences have it in their own language.

Long-form help
--------------

Anything longer than a paragraph or two belongs in Markdown rather than in a
JSON string literal: ``@tool(help="help/deploy.md")`` resolves
``help/<language>/deploy.md`` first, so a page with headings, tables and code
samples is translated by translating a file a translator can actually work in.
When such a file resolves it wins over this catalogue's ``prose``.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

#: The loaded catalogue for the running language: key to its entry. Empty when
#: no directory was named or the file for this language does not exist, which
#: is the ordinary case for an application that ships one language.
_CATALOGUE: dict[str, dict[str, Any]] = {}


def load_catalogue(directory: str | Path | None, language: str) -> list[str]:
    """Make one language's tool catalogue the live one.

    Args:
        directory: Where the application keeps its ``<language>.json`` files, or
            None to clear whatever was loaded.
        language: The language to look for. A file that is not there is not an
            error: an application that ships English only names a directory it
            has no translations in yet, and must still start.

    Returns:
        Problems to report, as human-readable lines. Empty when the file loaded
        or was simply absent. Never raises: an unusable catalogue costs an
        untranslated interface, which is not a reason to refuse to start.
    """
    global _CATALOGUE
    _CATALOGUE = {}
    if directory is None:
        return []

    path = Path(directory) / f"{language}.json"
    if not path.is_file():
        return []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"{path}: {exc}"]

    if not isinstance(payload, dict):
        return [f"{path}: the top level must be an object of keys to entries"]

    problems = [
        f"{path}: entry for '{key}' must be an object, got {type(value).__name__}"
        for key, value in payload.items()
        if not isinstance(value, dict)
    ]
    _CATALOGUE = {k: v for k, v in payload.items() if isinstance(v, dict)}
    return problems


def entry(key: str) -> dict[str, Any]:
    """Return the catalogue entry for one toolset or tool.

    Args:
        key: ``ClassName`` or ``ClassName.method``.

    Returns:
        The entry, or an empty mapping when the catalogue does not have it.
        Callers therefore never have to test for absence, only for the field
        they want.
    """
    return _CATALOGUE.get(key, {})


def translated(key: str, field: str, fallback: str) -> str:
    """Return one translated string, or what the source wrote.

    Args:
        key: ``ClassName`` or ``ClassName.method``.
        field: One of ``"label"``, ``"description"``, ``"brief"``,
            ``"returns"`` or ``"raises"``.
        fallback: The value from the declaration, used when the catalogue has
            nothing for this key and field.

    Returns:
        The translation, or ``fallback``. A non-string in the catalogue is
        ignored rather than rendered: a label is what goes in the sidebar, and
        a number there would be a typo made visible in the worst place.
    """
    value = entry(key).get(field)
    return value if isinstance(value, str) else fallback


def param_text(key: str, field: str, fallback: dict[str, str]) -> dict[str, str]:
    """Merge the catalogue's per-parameter text over a declaration's own.

    Args:
        key: ``ClassName.method``.
        field: ``"label"``, ``"placeholder"`` or ``"brief"``.
        fallback: The mapping this overlays, keyed by parameter name: from
            ``@tool(labels=...)``, ``@tool(placeholders=...)``, or the
            docstring's parsed ``Args:`` entries.

    Returns:
        A new mapping: the declaration's entries, with the catalogue's on top.
        Merged rather than replaced, so translating one field of a form does not
        silently drop the text on the others.
    """
    params = entry(key).get("params")
    if not isinstance(params, dict):
        return dict(fallback)

    merged = dict(fallback)
    for name, spec in params.items():
        if isinstance(spec, dict) and isinstance(spec.get(field), str):
            merged[name] = spec[field]
    return merged


@contextmanager
def catalogue_suspended() -> Iterator[None]:
    """Run a block with no catalogue loaded, then put back the one there was.

    Yields:
        Nothing.

    Note:
        Needed by :func:`dump_template`, which has to see the strings the source
        wrote. ``build_tree`` applies whatever is loaded, so dumping a template
        while a translation is live would emit that translation back out --
        producing a file that looks finished and says nothing new.
    """
    global _CATALOGUE
    saved = _CATALOGUE
    _CATALOGUE = {}
    try:
        yield
    finally:
        _CATALOGUE = saved


def _entry(*fields: tuple[str, str]) -> dict[str, str]:
    """Build a catalogue entry from name/value pairs, dropping the empty ones.

    Args:
        *fields: ``(name, value)`` pairs in the order they should appear.

    Returns:
        The non-empty ones. A tool with no ``Raises:`` section gets no
        ``raises`` key rather than an empty string: the template is a list of
        what there is to translate, and a blank line is not one of them.
    """
    return {name: value for name, value in fields if value}


def dump_template(tree: list) -> dict[str, dict[str, Any]]:
    """Build a catalogue template from the strings an application wrote.

    Every string this module can translate, in the shape the catalogue takes,
    with the source text as the value. A translator overwrites the values and
    deletes what they do not want to translate.

    Args:
        tree: Toolsets, as :func:`decoui.registry.build_tree` returns them. Only
            the classes are read: the tree is rebuilt here with no catalogue
            loaded, so what comes out is the source text even when a translation
            is in effect.

    Returns:
        Key to entry, ready to be written as JSON. Keys are ordered as the tree
        is -- a toolset, then its tools -- so the file reads in the order the
        sidebar does.
    """
    from .help import build_help
    from .registry import build_tree

    with catalogue_suspended():
        rebuilt = build_tree(*[ts.cls for ts in tree])
        groups = {group.set_id: group for group in build_help(rebuilt)}

        out: dict[str, dict[str, Any]] = {}
        for ts in rebuilt:
            group = groups[ts.cls.__name__]
            out[ts.cls.__name__] = _entry(
                ("label", ts.label),
                ("description", ts.description),
                ("brief", group.summary),
                ("prose", group.description),
            )
            helps = {entry.tool_id: entry for entry in group.tools}
            for info in ts.tools:
                entry = helps[info.tool_id]
                params = {
                    param.name: _entry(
                        ("label", param.label or ""),
                        ("placeholder", param.placeholder),
                        ("brief", next(
                            (p.text for p in entry.params if p.name == param.name),
                            "",
                        )),
                    )
                    for param in info.params
                }
                out[info.tool_id] = _entry(
                    ("label", info.label),
                    ("description", info.description),
                    ("brief", entry.summary),
                    # Only when it is the docstring's. A tool whose prose comes
                    # from a Markdown file is translated by translating that
                    # file, and putting its text in the template too would
                    # invite two answers to one question.
                    ("prose", "" if info.help else entry.description),
                    ("returns", entry.returns),
                    ("raises", entry.raises),
                ) | ({"params": params} if any(params.values()) else {})
        return out
