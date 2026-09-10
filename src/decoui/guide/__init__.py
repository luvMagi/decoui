"""decoui's own help: how the application itself works.

This is the other half of the Help panel. :mod:`decoui.help` collects what the
*tools* do, from their docstrings; this package carries what **decoui** does --
where history lives, what Replay actually replays, how the log window filters,
how a theme is changed. None of that is discoverable from a tool's docstring,
because none of it belongs to any tool.

The pages are data, not code: one directory per language under this package,
one file per page. That is deliberate. This text is decoui's own and will be
translated, and prose frozen into Python string constants is the worst possible
carrier for that -- a second language would mean a second copy of the module.
As files, a translation is a directory somebody drops in beside ``en``.

Each file is plain text in the same dialect a docstring uses -- a ``# Title``
first line, then blank-line-separated paragraphs, ``*`` bullets and ``literals``
in double backticks -- so the Help window renders it with the same code that
renders a tool's page. There is no second markup dialect to learn or maintain.

Page ids follow the key shape the rest of the Help system uses,
``guide.<slug>``, so the id is stable across languages: translating a page never
changes what addresses it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from importlib import resources

from ..i18n import DEFAULT_LANGUAGE, active_language

#: Leading sort digits in a page filename. They fix reading order -- a reader
#: working through the guide should meet the window before its history -- and
#: are not part of the page id.
_ORDER_PREFIX = re.compile(r"^\d+[-_]")


@dataclass(frozen=True)
class GuidePage:
    """One page of built-in help about the application itself.

    Attributes:
        page_id: Stable key, ``guide.<slug>``, taken from the filename. Never
            shown, and identical across languages: it is what a translation is
            looked up by.
        title: Heading, and the label in the Help window's tree.
        body: The page's prose, in the dialect described in this module's
            docstring.
    """

    page_id: str
    title: str
    body: str


def available_languages() -> list[str]:
    """Return the language codes that have a guide directory.

    Returns:
        Sorted codes, e.g. ``['en']``. A language appears here as soon as its
        directory exists, whether decoui shipped it or a user added it.
    """
    root = resources.files(__package__)
    return sorted(
        entry.name for entry in root.iterdir()
        if entry.is_dir() and not entry.name.startswith(("_", "."))
    )


@cache
def _load(language: str) -> tuple[GuidePage, ...]:
    """Read one language's pages from disk, once per process.

    Args:
        language: The directory name to read.

    Returns:
        The pages in filename order, or an empty tuple when the directory does
        not exist. Missing is not an error here -- :func:`guide_pages` treats it
        as "fall back to English".
    """
    directory = resources.files(__package__).joinpath(language)
    if not directory.is_dir():
        return ()

    pages: list[GuidePage] = []
    for entry in sorted(directory.iterdir(), key=lambda item: item.name):
        if not entry.name.endswith(".md"):
            continue
        text = entry.read_text(encoding="utf-8")
        title, _, body = text.partition("\n")
        slug = _ORDER_PREFIX.sub("", entry.name.removesuffix(".md"))
        pages.append(GuidePage(
            page_id=f"guide.{slug}",
            title=title.lstrip("# ").strip(),
            body=body.strip(),
        ))
    return tuple(pages)


def guide_pages(language: str | None = None) -> tuple[GuidePage, ...]:
    """Return decoui's built-in help pages in the requested language.

    Args:
        language: Language code, or None to follow the language the application
            is running under. A code with no directory falls back to English
            rather than returning nothing -- a reader whose language decoui only
            half supports should still get help, just not in their language.

    Returns:
        The pages in reading order.
    """
    wanted = language or active_language()
    pages = _load(wanted)
    if not pages and wanted != DEFAULT_LANGUAGE:
        return _load(DEFAULT_LANGUAGE)
    return pages
