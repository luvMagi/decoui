"""Standalone window listing how to use every loaded tool.

Opened from the top bar's Help button. It is a window rather than a tab so it
can sit beside the tool the reader is filling in -- the point of a help panel is
to be visible *while* working, which a tab in the same stack cannot do.

Everything shown here comes from :mod:`decoui.help`, which reads the docstrings
the tools already carry. Nothing has to be declared twice.
"""
from __future__ import annotations

import re
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..guide import GuidePage, guide_pages
from ..help import ToolHelp, ToolSetHelp, build_help
from ..i18n import t
from ..theme import active_theme, apply_label_case

#: Role holding a tree item's payload: a ToolHelp, a GuidePage, or None on a
#: group row, which the renderer distinguishes by type.
_HELP_ROLE = Qt.ItemDataRole.UserRole


class HelpWindow(QMainWindow):
    """Browsable reference for the tools loaded in this session.

    The left tree mirrors the sidebar; the right pane renders the selected
    tool's docstring as a page. Search filters the tree by tool label, toolset
    label and summary text, so a reader who knows what they want to do can find
    it without knowing which group it landed in.
    """

    def __init__(self, tree: list, parent: QWidget | None = None) -> None:
        """Collect help from the tree and show it.

        Args:
            tree: The toolset tree from build_tree().
            parent: Kept for placement only; the window is top-level either way.
        """
        super().__init__(parent=None)
        self.setWindowTitle(t("help.title"))
        self.resize(940, 660)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._sets: list[ToolSetHelp] = build_help(tree)
        self._guide: tuple[GuidePage, ...] = guide_pages()

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel(t("common.search"), central))
        self._search = QLineEdit(central)
        self._search.setPlaceholderText(t("help.search_placeholder"))
        self._search.textChanged.connect(self._rebuild_tree)
        search_row.addWidget(self._search)
        layout.addLayout(search_row)

        splitter = QSplitter(Qt.Orientation.Horizontal, central)

        self._tree = QTreeWidget(splitter)
        self._tree.setHeaderHidden(True)
        self._tree.currentItemChanged.connect(self._show_current)
        splitter.addWidget(self._tree)

        self._page = QTextBrowser(splitter)
        self._page.setOpenExternalLinks(False)
        splitter.addWidget(self._page)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 680])
        layout.addWidget(splitter)

        bottom = QHBoxLayout()
        close_btn = QPushButton(t("common.close"), central)
        close_btn.clicked.connect(self.close)
        bottom.addStretch()
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

        apply_label_case(central)
        self._rebuild_tree()

    def _rebuild_tree(self) -> None:
        """Refill the tree, honouring the current search text.

        A group whose own label matches keeps all its tools, so searching for a
        group name is a way to browse it rather than a way to empty it.
        """
        needle = self._search.text().strip().casefold()
        self._tree.clear()

        first_tool: QTreeWidgetItem | None = None

        # decoui's own pages come first: a reader who does not yet know what
        # Replay does is not helped by an alphabetical list of somebody's tools.
        guide_matches = needle in t("help.guide_group").casefold()
        pages = [
            page for page in self._guide
            if not needle or guide_matches or needle in page.title.casefold()
        ]
        if pages:
            guide_root = QTreeWidgetItem(self._tree, [t("help.guide_group")])
            guide_root.setData(0, _HELP_ROLE, None)
            guide_root.setExpanded(True)
            for page in pages:
                child = QTreeWidgetItem(guide_root, [page.title])
                child.setData(0, _HELP_ROLE, page)
                if first_tool is None:
                    first_tool = child

        for group in self._sets:
            group_matches = needle in group.label.casefold()
            tools = [
                tool for tool in group.tools
                if not needle
                or group_matches
                or needle in tool.label.casefold()
                or needle in tool.summary.casefold()
            ]
            if not tools:
                continue

            parent = QTreeWidgetItem(self._tree, [group.label])
            parent.setData(0, _HELP_ROLE, None)
            parent.setExpanded(True)
            for tool in tools:
                child = QTreeWidgetItem(parent, [tool.label])
                child.setData(0, _HELP_ROLE, tool)
                if first_tool is None:
                    first_tool = child

        if first_tool is not None:
            self._tree.setCurrentItem(first_tool)
        else:
            self._page.setHtml(self._wrap(f"<p class='muted'>{t('help.no_match')}</p>"))

    def _show_current(
        self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None = None
    ) -> None:
        """Render whatever the tree has selected.

        Args:
            current: The newly selected item, or None when the tree emptied.
            _previous: Unused; part of Qt's signal.
        """
        if current is None:
            return
        payload = current.data(0, _HELP_ROLE)
        if isinstance(payload, GuidePage):
            self._page.setHtml(self._wrap(_guide_html(payload)))
            return
        if isinstance(payload, ToolHelp):
            self._page.setHtml(self._wrap(_tool_html(payload)))
            return
        # A group row: decoui's own section, or one of the toolsets.
        if current.text(0) == t("help.guide_group"):
            self._page.setHtml(self._wrap(_guide_index_html(self._guide)))
            return
        group = next((g for g in self._sets if g.label == current.text(0)), None)
        self._page.setHtml(self._wrap(_group_html(group) if group else ""))

    def _wrap(self, body: str) -> str:
        """Put rendered help inside a themed HTML document.

        QTextBrowser does not read the application stylesheet, so the theme's
        colours and fonts are inlined here instead.

        Args:
            body: The page's inner HTML.

        Returns:
            A complete HTML document.
        """
        theme = active_theme()
        colors, font = theme.colors, theme.font
        return f"""<html><head><style>
body {{
  background: {colors['bg.surface']};
  color: {colors['text.primary']};
  font-family: {', '.join(font.family)};
  font-size: {font.size_pt}pt;
}}
h1 {{ font-size: {font.title_size_px}px; margin: 0 0 2px 0; }}
h2 {{ font-size: {font.size_pt + 1}pt; margin: 18px 0 6px 0;
     color: {colors['text.secondary']};
     border-bottom: 1px solid {colors['border.subtle']}; padding-bottom: 3px; }}
p  {{ margin: 6px 0; line-height: 145%; }}
.summary {{ color: {colors['text.secondary']}; margin: 0 0 10px 0; }}
.muted   {{ color: {colors['text.muted']}; }}
code {{ font-family: {', '.join(font.mono_family)};
        background: {colors['bg.field']}; padding: 1px 4px; }}
table {{ border-collapse: collapse; width: 100%; margin: 4px 0 2px 0; }}
th {{ background: {colors['bg.header']}; color: {colors['text.secondary']};
      text-align: left; padding: 5px 8px;
      border-bottom: 1px solid {colors['border.panel']}; }}
td {{ padding: 5px 8px; border-bottom: 1px solid {colors['bg.gridline']};
      vertical-align: top; }}
.req {{ color: {colors['text.required']}; font-weight: bold; }}
.type {{ font-family: {', '.join(font.mono_family)};
         color: {colors['text.muted']}; }}
ul {{ margin: 6px 0 6px 0; }}
li {{ margin: 3px 0; line-height: 145%; }}
</style></head><body>{body}</body></html>"""


#: reST inline literals, which is how a Python docstring marks code. Double
#: backticks are the real form; single backticks are accepted because they are
#: written by habit often enough that rendering them raw looks like a bug.
#: Inline spans, matched in one pass so that a code literal consumes its own
#: text before emphasis can look at it -- otherwise ``**kwargs`` inside a
#: literal would come out half-bold.
_INLINE_RE = re.compile(
    r"``(?P<lit2>.+?)``"
    r"|`(?P<lit1>.+?)`"
    r"|\*\*(?P<bold>\S.*?)\*\*"
    r"|\*(?P<em>\S.*?)\*",
    re.DOTALL,
)

#: Sphinx cross-reference roles. The target is useful to a reader, the role
#: prefix is not -- it is markup for a doc builder decoui does not run. Stripped
#: so ``:meth:`stop_child``` reads as ``stop_child`` rather than leaking syntax.
_ROLE_RE = re.compile(r":(?:func|meth|class|mod|data|attr|exc|obj|ref|py:\w+):(?=`)")

#: A line opening a bullet in reST prose: ``* text`` or ``- text``.
_BULLET_RE = re.compile(r"^\s*[*-]\s+(?P<text>.*)$")


def _inline(text: str) -> str:
    """Escape prose and render its inline markup as HTML.

    Handles what a docstring and a guide page have in common: ``literals``,
    ``**bold**``, ``*emphasis*``, and Sphinx role prefixes, which are stripped
    because the target is useful to a reader and the role name is markup for a
    doc builder decoui does not run.

    Args:
        text: Raw text from a docstring or a guide page.

    Returns:
        HTML-safe text with its markup rendered.
    """
    escaped = _ROLE_RE.sub("", escape(text))

    def render(match: re.Match[str]) -> str:
        if (literal := match.group("lit2") or match.group("lit1")) is not None:
            return f"<code>{literal}</code>"
        if (bold := match.group("bold")) is not None:
            return f"<b>{bold}</b>"
        return f"<i>{match.group('em')}</i>"

    return _INLINE_RE.sub(render, escaped)


def _bullets(block: str) -> str | None:
    """Render a block as a list when it is one.

    Args:
        block: One blank-line-delimited block of docstring prose.

    Returns:
        The block as ``<ul>``, or None when it does not open with a bullet.
        A bullet's text may wrap onto following, more-indented lines.
    """
    lines = block.splitlines()
    if not lines or not _BULLET_RE.match(lines[0]):
        return None

    items: list[list[str]] = []
    for line in lines:
        match = _BULLET_RE.match(line)
        if match:
            items.append([match.group("text")])
        elif items and line.strip():
            items[-1].append(line.strip())
        # A blank line inside a list separates items, not paragraphs; ignored.

    rendered = "".join(f"<li>{_inline(' '.join(item))}</li>" for item in items)
    return f"<ul>{rendered}</ul>"


def _paragraphs(text: str, css_class: str = "") -> str:
    """Render blank-line-separated prose as HTML paragraphs and lists.

    A block that opens with ``*`` or ``-`` becomes a list; everything else
    becomes a paragraph with its wrapped lines rejoined, since a line break
    inside a docstring paragraph is an artefact of the source width, not of
    what the author meant.

    Args:
        text: Raw docstring prose.
        css_class: Class applied to every paragraph, if any. Lists never take
            it -- it exists for the summary, which is never a list.

    Returns:
        The prose as HTML, or an empty string when there is no text.
    """
    if not text.strip():
        return ""
    attr = f" class='{css_class}'" if css_class else ""
    out: list[str] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        rendered = _bullets(block)
        if rendered is not None:
            out.append(rendered)
        else:
            out.append(f"<p{attr}>{_inline(block.strip()).replace(chr(10), ' ')}</p>")
    return "".join(out)


def _guide_html(page: GuidePage) -> str:
    """Render one of decoui's own pages.

    Args:
        page: The guide page to show.

    Returns:
        HTML for the right-hand pane.
    """
    return f"<h1>{escape(page.title)}</h1>{_paragraphs(page.body)}"


def _guide_index_html(pages: tuple[GuidePage, ...]) -> str:
    """Render the contents page for decoui's own section.

    Args:
        pages: The guide pages, in reading order.

    Returns:
        HTML for the right-hand pane.
    """
    parts = [
        f"<h1>{escape(t('help.guide_group'))}</h1>",
        f"<p class='summary'>{t('help.guide_summary')}</p><table>",
    ]
    for page in pages:
        first = page.body.split("\n\n")[0] if page.body else ""
        parts.append(
            f"<tr><td><b>{escape(page.title)}</b></td>"
            f"<td>{_inline(first.replace(chr(10), ' '))}</td></tr>"
        )
    parts.append("</table>")
    return "".join(parts)


def _group_html(group: ToolSetHelp) -> str:
    """Render a toolset's own page.

    Args:
        group: The toolset to describe.

    Returns:
        HTML for the right-hand pane.
    """
    parts = [f"<h1>{escape(group.label)}</h1>"]
    if group.summary:
        parts.append(_paragraphs(group.summary, "summary"))
    parts.append(_paragraphs(group.description))
    parts.append(f"<h2>{t('help.tools')}</h2><table>")
    for tool in group.tools:
        parts.append(
            f"<tr><td><b>{escape(tool.label)}</b></td>"
            f"<td>{_inline(tool.summary)}</td></tr>"
        )
    parts.append("</table>")
    return "".join(parts)


def _tool_html(tool: ToolHelp) -> str:
    """Render one tool's page.

    Args:
        tool: The tool to describe.

    Returns:
        HTML for the right-hand pane.
    """
    parts = [f"<h1>{escape(tool.label)}</h1>"]
    if tool.summary:
        parts.append(_paragraphs(tool.summary, "summary"))
    parts.append(_paragraphs(tool.description))

    if tool.params:
        parts.append(f"<h2>{t('help.parameters')}</h2><table>")
        parts.append(
            f"<tr><th>{t('help.column.field')}</th>"
            f"<th>{t('help.column.type')}</th>"
            f"<th>{t('help.column.default')}</th>"
            f"<th>{t('help.column.description')}</th></tr>"
        )
        for param in tool.params:
            mark = " <span class='req'>*</span>" if param.required else ""
            text = _inline(param.text) if param.text else (
                "<span class='muted'>—</span>"
            )
            parts.append(
                f"<tr><td><b>{escape(param.label)}</b>{mark}</td>"
                f"<td class='type'>{escape(param.type_name)}</td>"
                f"<td class='type'>{escape(param.default)}</td>"
                f"<td>{text}</td></tr>"
            )
        parts.append("</table>")
        if any(p.required for p in tool.params):
            parts.append(
                f"<p class='muted'><span class='req'>*</span> {t('help.required')}</p>"
            )

    if tool.returns:
        parts.append(f"<h2>{t('help.returns')}</h2>" + _paragraphs(tool.returns))
    if tool.raises:
        parts.append(f"<h2>{t('help.raises')}</h2>" + _paragraphs(tool.raises))
    return "".join(parts)
