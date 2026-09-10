"""The markup dialect decoui's help is written in, and its renderer.

One dialect, three sources: a tool's docstring, a toolset's docstring, and the
``.md`` files that carry decoui's own guide or an application's per-tool help.
They render through the same code, so an author learns the rules once.

The dialect is Markdown, with two departures that exist because the source is
sometimes a Python docstring rather than a file:

* ``literals`` in double backticks are accepted alongside Markdown's single
  backticks. Double is what reST uses, and reST is what a Python docstring is
  conventionally written in -- a project whose docstrings already say
  ``\\`\\`None\\`\\``` should not have to choose between its API docs and its
  help pages.
* Indentation-based code blocks are **not** recognised. A docstring's own
  indentation is an artefact of where it sits in the file, and though
  :func:`decoui.help.parse_docstring` normalises it, a four-space block in the
  source is far more likely to be a wrapped sentence than a code sample. Fence
  code with ``\\`\\`\\``` instead, which means the same thing everywhere.

Cross-references have a syntax of their own, ``[[key]]``, deliberately not
Markdown's link syntax. They point at a decoui page -- ``[[guide.themes]]``,
``[[MyTools.encode]]`` -- by a key that does not change when a page is
translated. Keeping them out of ``[text](target)`` is what lets that form mean
what it means everywhere else: an ordinary link to an ordinary URL.

Rendering is to HTML rather than to a ``QTextDocument``. Qt can parse Markdown
itself, and better than this module does, but it renders it to a document whose
fonts, code face and table borders are fixed -- the help window's whole
appearance comes from the theme, and a page that ignored the theme would be a
worse trade than a smaller dialect. Emitting HTML also lets decoui's own
generated structure (a title, a parameter table) sit in the same page as an
author's prose, which a whole-document parser cannot do.
"""
from __future__ import annotations

import re
from html import escape

#: URL scheme for a cross-reference. A scheme of decoui's own, so that
#: :meth:`decoui.ui.help_window.HelpWindow._navigate` can tell a jump between
#: help pages from a link that leaves the application.
LINK_SCHEME = "decoui"

#: Schemes a ``[text](target)`` link may use. Everything else renders as plain
#: text with the target shown, because a reader who cannot follow a link is
#: still owed the address.
#:
#: The list is short on purpose. ``file:`` would turn a help page into a way to
#: open arbitrary local paths, and the exotic schemes a desktop registers are
#: not worth auditing -- help text is written by whoever wrote the application,
#: so this is not a trust boundary, but it is a blast radius.
EXTERNAL_SCHEMES = frozenset({"http", "https", "mailto"})

#: Sphinx cross-reference roles. The target is useful to a reader, the role
#: prefix is not -- it is markup for a doc builder decoui does not run. Stripped
#: so ``:meth:`stop_child``` reads as ``stop_child`` rather than leaking syntax.
_ROLE_RE = re.compile(r":(?:func|meth|class|mod|data|attr|exc|obj|ref|py:\w+):(?=`)")

#: Inline spans, matched in one pass so that a code literal consumes its own
#: text before emphasis can look at it -- otherwise ``**kwargs`` inside a
#: literal would come out half-bold.
#:
#: Order is the precedence. Cross-references come first because ``[[a]]`` also
#: matches the link branch's ``[...]``; literals come before emphasis for the
#: reason above; and the two-backtick form comes before the one-backtick form
#: because the shorter one would otherwise match the opening pair of the longer.
_INLINE_RE = re.compile(
    r"\[\[(?P<ref>[^\]\n|]+?)(?:\|(?P<ref_label>[^\]\n]+?))?\]\]"
    r"|``(?P<lit2>.+?)``"
    r"|`(?P<lit1>.+?)`"
    r"|\[(?P<link_text>[^\]\n]*)\]\((?P<link_href>[^)\s]+)\)"
    r"|\*\*(?P<bold>\S.*?)\*\*"
    r"|~~(?P<strike>\S.*?)~~"
    r"|\*(?P<em>\S.*?)\*",
    re.DOTALL,
)

#: An ATX heading. Levels are shifted down one on the way out: ``<h1>`` is the
#: page's own title, written by decoui rather than by the author, so the first
#: heading an author can write has to land below it.
_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<text>.+?)\s*#*$")

#: A code fence: three or more backticks or tildes, optionally followed by a
#: language. The language is captured and dropped -- decoui does no syntax
#: highlighting -- but accepted, because every author writes it and rejecting it
#: would put the word "python" in the first line of their sample.
_FENCE_RE = re.compile(r"^(?P<fence>`{3,}|~{3,})\s*(?P<lang>[^`\s]*)\s*$")

#: A list marker: bullet or number, with the indentation that decides nesting.
_ITEM_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<marker>[*+-]|\d{1,9}[.)])[ \t]+(?P<text>.*)$"
)

#: A thematic break. Checked before the list rule, since ``---`` also opens a
#: bullet as far as that rule is concerned.
_RULE_RE = re.compile(r"^[ \t]*(?:-[ \t]*){3,}$|^[ \t]*(?:\*[ \t]*){3,}$"
                      r"|^[ \t]*(?:_[ \t]*){3,}$")

#: The row under a table's header, which is what tells a run of pipe-separated
#: lines from a paragraph that merely contains pipes.
_TABLE_DELIM_RE = re.compile(r"^[ \t]*\|?[ \t]*:?-{1,}:?[ \t]*(\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$")

#: A blockquote line.
_QUOTE_RE = re.compile(r"^[ \t]*>[ \t]?(?P<text>.*)$")

#: Column alignment from a table's delimiter row.
_ALIGN_RE = re.compile(r"^(?P<left>:)?-+(?P<right>:)?$")


def _link_scheme(href: str) -> str:
    """Return the lowercase scheme of a link target, or an empty string.

    Args:
        href: The target exactly as it was written.

    Returns:
        The part before the first colon, lowercased, when the target looks like
        an absolute URL. A relative target has no scheme and returns ``""``,
        which is what keeps a bare word from being treated as one.
    """
    head, colon, _ = href.partition(":")
    if not colon or not head or not head.replace("+", "").replace("-", "").replace(".", "").isalnum():
        return ""
    return head.lower()


def inline(text: str, links: frozenset[str] = frozenset()) -> str:
    """Escape one run of prose and render its inline markup as HTML.

    Args:
        text: Raw text, already free of block structure.
        links: Page keys that resolve in this session. A ``[[reference]]`` to
            anything else renders as its own text with no link on it: which
            tools exist is up to the application that loaded them, so help
            cannot be written against a fixed set, and a dead link is worse
            than plain prose.

    Returns:
        HTML-safe text with its markup rendered.
    """
    escaped = _ROLE_RE.sub("", escape(text))

    def render(match: re.Match[str]) -> str:
        if (ref := match.group("ref")) is not None:
            # The label goes back through the same pass, so a reference may
            # carry markup of its own -- [[guide.themes|**Themes**]]. It cannot
            # nest: the label pattern excludes "]", so there is no second
            # reference inside this one to recurse into.
            written = match.group("ref_label")
            label = _INLINE_RE.sub(render, written) if written else ref
            if ref.strip() not in links:
                return label
            return f'<a href="{LINK_SCHEME}:{ref.strip()}">{label}</a>'
        if (literal := match.group("lit2") or match.group("lit1")) is not None:
            return f"<code>{literal}</code>"
        if (href := match.group("link_href")) is not None:
            # The label goes back through the same pass, so a link may carry
            # markup of its own. It cannot nest: the label pattern excludes
            # "]", so there is no second link inside this one to recurse into.
            label = _INLINE_RE.sub(render, match.group("link_text")) or href
            if _link_scheme(href) not in EXTERNAL_SCHEMES:
                # Shown rather than swallowed. A target decoui will not follow
                # is usually a mistake -- a cross-reference written with the
                # wrong brackets, most often -- and hiding it makes that
                # mistake invisible to the person who can fix it.
                return f"{label} ({href})" if label != href else href
            return f'<a href="{href}">{label}</a>'
        if (bold := match.group("bold")) is not None:
            return f"<b>{bold}</b>"
        if (strike := match.group("strike")) is not None:
            return f"<s>{strike}</s>"
        return f"<i>{match.group('em')}</i>"

    return _INLINE_RE.sub(render, escaped)


def _fence_block(lines: list[str], start: int) -> tuple[str, int]:
    """Render a fenced code block, and say where it ended.

    Args:
        lines: Every line of the source.
        start: Index of the opening fence.

    Returns:
        The block as HTML and the index of the first line after it. An
        unterminated fence runs to the end of the source rather than being
        rejected: the author's intent is not in doubt, only their typing.
    """
    opening = _FENCE_RE.match(lines[start])
    assert opening is not None
    marker = opening.group("fence")[0]
    width = len(opening.group("fence"))

    body: list[str] = []
    index = start + 1
    while index < len(lines):
        closing = _FENCE_RE.match(lines[index])
        if (closing is not None
                and closing.group("fence")[0] == marker
                and len(closing.group("fence")) >= width
                and not closing.group("lang")):
            index += 1
            break
        body.append(lines[index])
        index += 1

    return f"<pre>{escape(chr(10).join(body))}</pre>", index


def _cells(line: str) -> list[str]:
    """Split one table row on its pipes.

    Args:
        line: The row as written, with or without the outer pipes that are
            conventional but optional.

    Returns:
        The cell texts, stripped.
    """
    stripped = line.strip().removeprefix("|").removesuffix("|")
    return [cell.strip() for cell in stripped.split("|")]


def _table_block(
    lines: list[str], start: int, links: frozenset[str]
) -> tuple[str, int] | None:
    """Render a pipe table if one starts here, and say where it ended.

    Args:
        lines: Every line of the source.
        start: Index of what may be the header row.
        links: Page keys that resolve, passed through to :func:`inline`.

    Returns:
        The table as HTML and the index after it, or None when these lines are
        not a table. A header row alone is not enough -- the delimiter row under
        it is what distinguishes a table from a sentence containing pipes.
    """
    if start + 1 >= len(lines) or "|" not in lines[start]:
        return None
    if not _TABLE_DELIM_RE.match(lines[start + 1]):
        return None

    aligns: list[str] = []
    for spec in _cells(lines[start + 1]):
        match = _ALIGN_RE.match(spec)
        if match is None:
            aligns.append("")
        elif match.group("left") and match.group("right"):
            aligns.append(" align='center'")
        elif match.group("right"):
            aligns.append(" align='right'")
        else:
            aligns.append("")

    def row(line: str, tag: str) -> str:
        out = []
        for column, cell in enumerate(_cells(line)):
            align = aligns[column] if column < len(aligns) else ""
            out.append(f"<{tag}{align}>{inline(cell, links)}</{tag}>")
        return f"<tr>{''.join(out)}</tr>"

    rows = [row(lines[start], "th")]
    index = start + 2
    while index < len(lines) and lines[index].strip() and "|" in lines[index]:
        rows.append(row(lines[index], "td"))
        index += 1
    return f"<table>{''.join(rows)}</table>", index


def _list_block(lines: list[str], start: int, links: frozenset[str]) -> tuple[str, int]:
    """Render a list, nested to whatever depth its indentation describes.

    Args:
        lines: Every line of the source.
        start: Index of the first item.
        links: Page keys that resolve, passed through to :func:`inline`.

    Returns:
        The list as HTML and the index of the first line after it.

    Note:
        Nesting is by indentation only, and a level is opened by any increase --
        Markdown proper ties the step to the parent marker's width, which is
        precise and which nobody writing help text has ever counted on purpose.
    """
    stack: list[tuple[int, str]] = []   # (indent, tag)
    out: list[str] = []
    index = start

    def close_to(indent: int) -> None:
        while stack and stack[-1][0] > indent:
            out.append(f"</li></{stack.pop()[1]}>")

    while index < len(lines):
        line = lines[index]
        match = _ITEM_RE.match(line)
        if match is None:
            if line.strip() and stack:
                # A plainer line under an item continues it: a docstring wraps
                # at the source width, and that wrap is not a new paragraph.
                out.append(" " + inline(line.strip(), links))
                index += 1
                continue
            break

        indent = len(match.group("indent").expandtabs(4))
        tag = "ol" if match.group("marker")[0].isdigit() else "ul"

        if not stack or indent > stack[-1][0]:
            out.append(f"<{tag}><li>")
            stack.append((indent, tag))
        else:
            close_to(indent)
            if stack and stack[-1][1] != tag:
                out.append(f"</li></{stack.pop()[1]}>")
                out.append(f"<{tag}><li>")
                stack.append((indent, tag))
            else:
                out.append("</li><li>")
        out.append(inline(match.group("text").strip(), links))
        index += 1

    while stack:
        out.append(f"</li></{stack.pop()[1]}>")
    return "".join(out), index


def _quote_block(lines: list[str], start: int, links: frozenset[str]) -> tuple[str, int]:
    """Render a blockquote, and say where it ended.

    Args:
        lines: Every line of the source.
        start: Index of the first quoted line.
        links: Page keys that resolve.

    Returns:
        The quote as HTML and the index after it. Its contents go back through
        the whole block renderer, so a quote may hold anything a page may hold.
    """
    body: list[str] = []
    index = start
    while index < len(lines):
        match = _QUOTE_RE.match(lines[index])
        if match is None:
            break
        body.append(match.group("text"))
        index += 1
    return f"<blockquote>{render(chr(10).join(body), links)}</blockquote>", index


def render(
    text: str, links: frozenset[str] = frozenset(), *, css_class: str = ""
) -> str:
    """Render one piece of help text as HTML.

    Args:
        text: The source, in the dialect this module's docstring describes.
        links: Page keys that resolve in this session, for ``[[references]]``.
        css_class: Class applied to top-level paragraphs, if any. It exists for
            the summary line, which is styled apart from the prose under it;
            nothing structural takes it.

    Returns:
        The text as HTML, or an empty string when there is nothing to render.
    """
    if not text.strip():
        return ""

    lines = text.expandtabs(4).splitlines()
    attr = f" class='{css_class}'" if css_class else ""
    out: list[str] = []
    paragraph: list[str] = []

    def flush() -> None:
        """Emit whatever plain lines have accumulated, as one paragraph."""
        if not paragraph:
            return
        # Joined with spaces: a line break inside a paragraph is an artefact of
        # the source width, not something the author asked for.
        body = inline(" ".join(line.strip() for line in paragraph), links)
        out.append(f"<p{attr}>{body}</p>")
        paragraph.clear()

    index = 0
    while index < len(lines):
        line = lines[index]

        if not line.strip():
            flush()
            index += 1
            continue

        if _FENCE_RE.match(line):
            flush()
            html, index = _fence_block(lines, index)
            out.append(html)
            continue

        if _RULE_RE.match(line):
            flush()
            out.append("<hr>")
            index += 1
            continue

        if (heading := _HEADING_RE.match(line)) is not None:
            flush()
            level = min(len(heading.group("hashes")) + 1, 6)
            out.append(
                f"<h{level}>{inline(heading.group('text'), links)}</h{level}>"
            )
            index += 1
            continue

        if _QUOTE_RE.match(line):
            flush()
            html, index = _quote_block(lines, index, links)
            out.append(html)
            continue

        table = _table_block(lines, index, links)
        if table is not None:
            flush()
            html, index = table
            out.append(html)
            continue

        if _ITEM_RE.match(line):
            flush()
            html, index = _list_block(lines, index, links)
            out.append(html)
            continue

        paragraph.append(line)
        index += 1

    flush()
    return "".join(out)


def reference(key: str, label: str, links: frozenset[str]) -> str:
    """Render one already-known key as a link, or as plain text.

    Used where the target comes from decoui's own data rather than from prose --
    a row in a contents table -- so there is nothing to parse, only the same
    question of whether the target is reachable.

    Args:
        key: The page key to point at.
        label: Visible text. Escaped here; callers pass it raw.
        links: Keys that resolve to a page in this session.

    Returns:
        An anchor, or the escaped label alone.
    """
    if key not in links:
        return escape(label)
    return f'<a href="{LINK_SCHEME}:{key}">{escape(label)}</a>'


#: A reST inline literal: the double-backtick form a Python docstring uses.
_REST_LITERAL_RE = re.compile(r"``(.+?)``", re.DOTALL)


def as_markdown(text: str) -> str:
    """Normalise decoui's docstring dialect to plain Markdown.

    decoui reads both spellings, so this changes nothing about how a page
    renders here. It matters on the way **out**: a ``.md`` file dumped for a
    translator is opened in a Markdown editor, where ``` ``literal`` ``` is not
    a code span but a code span containing a backtick, and ``:meth:`` is
    syntax from a doc builder that editor has never heard of.

    Args:
        text: Prose in the dialect, as a docstring writes it.

    Returns:
        The same prose as ordinary Markdown.
    """
    return _REST_LITERAL_RE.sub(r"`\1`", _ROLE_RE.sub("", text))
