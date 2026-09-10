"""Standalone window listing how to use every loaded tool.

Opened from the top bar's Help button. It is a window rather than a tab so it
can sit beside the tool the reader is filling in -- the point of a help panel is
to be visible *while* working, which a tab in the same stack cannot do.

Everything shown here comes from :mod:`decoui.help`, which reads the docstrings
the tools already carry. Nothing has to be declared twice.
"""
from __future__ import annotations

from html import escape

from PySide6.QtCore import QPoint, QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPushButton,
    QSplitter,
    QTabBar,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QVBoxLayout,
    QWidget,
)

from ..assets import icon_path
from ..guide import GuidePage, guide_pages
from ..markup import (
    EXTERNAL_SCHEMES,
    LINK_SCHEME,
    inline as render_inline,
    reference,
    render,
)
from ..help import ToolHelp, ToolSetHelp, build_help
from ..i18n import t
from ..theme import active_theme, apply_label_case
from .icons import ICON_PX, theme_icon
from .sidebar_width import stored_sidebar_width

#: Role holding a tree item's page key. The key, not the object: it is what a
#: tab, a history entry and a written cross-reference all address a page by, so
#: keeping one identity everywhere means the tree can be matched against any of
#: them without a second lookup table.
_HELP_ROLE = Qt.ItemDataRole.UserRole

#: Key of the contents page for decoui's own section. A bare ``guide``, with
#: the pages under it as ``guide.<slug>`` -- the same shape as a toolset and
#: its tools, which are ``ClassName`` and ``ClassName.method``.
_GUIDE_INDEX = "guide"

#: Close-button geometry, matching :mod:`decoui.ui.main_window`. The two tab
#: strips are the same control doing the same job in two windows, and a reader
#: with both open should not be able to tell them apart.
_CLOSE_BUTTON_SIZE = 16
_CLOSE_ICON_SIZE = 10
#: Qt pins the tab's right-side widget to the tab rectangle's edge, which lands
#: on top of the tab border. The holder carries this much right margin so the
#: glyph is inset within the tab instead of straddling its boundary.
_CLOSE_BUTTON_INSET = 7


class HelpWindow(QMainWindow):
    """Browsable reference for the tools loaded in this session.

    The left tree mirrors the sidebar; the right side is a tab strip, one tab
    per page opened, exactly as the main window opens one tab per tool. Search
    filters the tree by tool label, toolset label and summary text, so a reader
    who knows what they want to do can find it without knowing whose toolset it
    landed in.

    Pages cross-reference each other. A page is addressed by a key --
    ``guide.themes``, ``MyTools``, ``MyTools.encode`` -- and a key survives
    translation, so a link written once works in every language.

    Navigation is the pair a reader expects from anything with links: back and
    forward, over the pages actually visited. It runs **across** tabs rather
    than inside one, because every page opens in a tab of its own -- per-tab
    history would have exactly one entry in it and nothing to go back to. Going
    back to a page whose tab was closed opens it again.
    """

    def __init__(self, tree: list, parent: QWidget | None = None) -> None:
        """Collect help from the tree and show it.

        Args:
            tree: The toolset tree from build_tree().
            parent: Kept for placement only; the window is top-level either way.
        """
        super().__init__(parent=None)
        self.setWindowTitle(t("help.title"))
        # Wider than the window needs for prose alone. Help pages now carry
        # tables and fenced code, and both have a width below which they stop
        # being readable rather than merely getting taller: a table starts
        # wrapping inside its cells, and a code sample wraps mid-line, which is
        # the one place a line break changes the meaning.
        self.resize(1180, 760)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._sets: list[ToolSetHelp] = build_help(tree)
        self._guide: tuple[GuidePage, ...] = guide_pages()
        self._pages = self._index_pages()
        #: Every key that resolves. Handed to the renderers, which draw a
        #: cross-reference to anything else as plain text.
        self._links = frozenset(self._pages)

        self._open_tabs: dict[str, QTextBrowser] = {}
        self._history: list[str] = []
        self._at = -1
        # Depth rather than a flag: syncing the tree can re-enter through the
        # tab strip, and a flag would be cleared by the inner exit.
        self._quiet = 0

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
        self._tree.currentItemChanged.connect(self._on_tree_selection)
        splitter.addWidget(self._tree)

        right = QWidget(splitter)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # Drawn, not typed. These carried the characters U+2190 and U+2192,
        # which render at whatever weight the interface font gives an arrow --
        # noticeably lighter than everything around them in most faces, and
        # lighter still under a theme that asks for a condensed one. A triangle
        # of decoui's own is the same weight in every theme, and matches the
        # icons on the top bar. See :mod:`decoui.ui.icons`.
        nav_row = QHBoxLayout()
        nav_row.setSpacing(4)
        self._back_btn = QPushButton(right)
        self._back_btn.setToolTip(t("help.back_tooltip"))
        self._back_btn.clicked.connect(self._go_back)
        self._forward_btn = QPushButton(right)
        self._forward_btn.setToolTip(t("help.forward_tooltip"))
        self._forward_btn.clicked.connect(self._go_forward)
        for button in (self._back_btn, self._forward_btn):
            button.setFixedSize(32, 32)
            button.setIconSize(QSize(ICON_PX, ICON_PX))
            # The application stylesheet spends 14px of padding either side,
            # which is right for a word and leaves an icon nothing.
            button.setStyleSheet("QPushButton { padding: 0px; }")
        nav_row.addWidget(self._back_btn)
        nav_row.addWidget(self._forward_btn)
        nav_row.addStretch()
        right_layout.addLayout(nav_row)

        self._tabs = QTabWidget(right)
        self._tabs.setDocumentMode(True)
        self._tabs.setMovable(True)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        tab_bar = self._tabs.tabBar()
        tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tab_bar.customContextMenuRequested.connect(self._show_tab_context_menu)
        right_layout.addWidget(self._tabs)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        # The tree opens at the width the main window's sidebar is set to, so
        # that help placed beside the form it explains lines up with it rather
        # than reading as a misalignment. The reading pane takes whatever is
        # left, which is where the extra window width was wanted anyway.
        #
        # Read, not written: dragging this handle re-proportions the page being
        # read, and having that quietly resize the main window's sidebar too
        # would be a side effect nobody asked this splitter for.
        tree_width = stored_sidebar_width()
        splitter.setSizes([tree_width, max(1, self.width() - tree_width)])
        layout.addWidget(splitter)

        bottom = QHBoxLayout()
        close_btn = QPushButton(t("common.close"), central)
        close_btn.clicked.connect(self.close)
        bottom.addStretch()
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

        self._apply_icons()
        apply_label_case(central)
        self._rebuild_tree()
        self._open_first()

    def _apply_icons(self) -> None:
        """Draw the navigation arrows in the active theme's button ink.

        Icons are pixmaps and no stylesheet reaches inside one, so a re-theme
        redraws rather than restyles -- see :mod:`decoui.ui.retheme`.
        """
        ratio = self.devicePixelRatioF()
        self._back_btn.setIcon(theme_icon("nav-back", ratio=ratio))
        self._forward_btn.setIcon(theme_icon("nav-forward", ratio=ratio))

    # ── The page index ────────────────────────────────────────────────────────

    def _index_pages(self) -> dict[str, GuidePage | ToolHelp | ToolSetHelp]:
        """Map every addressable page to the object that renders it.

        Returns:
            Key to payload. The guide's contents page is deliberately absent:
            it renders from the whole page tuple rather than from one object,
            and :meth:`_render` handles it by key.
        """
        pages: dict[str, GuidePage | ToolHelp | ToolSetHelp] = {}
        for page in self._guide:
            pages[page.page_id] = page
        for group in self._sets:
            pages[group.set_id] = group
            for tool in group.tools:
                pages[tool.tool_id] = tool
        return pages

    def _render(self, key: str) -> str:
        """Build the HTML body for one page.

        Args:
            key: The page to render.

        Returns:
            Inner HTML, ready for :meth:`_wrap`.
        """
        if key == _GUIDE_INDEX:
            return _guide_index_html(self._guide, self._links)
        payload = self._pages.get(key)
        if isinstance(payload, GuidePage):
            return _guide_html(payload, self._links)
        if isinstance(payload, ToolHelp):
            return _tool_html(payload, self._links)
        if isinstance(payload, ToolSetHelp):
            return _group_html(payload, self._links)
        return ""

    def _title_for(self, key: str) -> str:
        """Return the tab label for one page.

        Args:
            key: The page.

        Returns:
            Its heading, which is what the reader just clicked on.
        """
        if key == _GUIDE_INDEX:
            return t("help.guide_group")
        payload = self._pages.get(key)
        if isinstance(payload, GuidePage):
            return payload.title
        if isinstance(payload, (ToolHelp, ToolSetHelp)):
            return payload.label
        return key

    # ── Opening pages ─────────────────────────────────────────────────────────

    def _open_first(self) -> None:
        """Show something on opening: the guide's contents, or the first page."""
        if self._guide:
            self._navigate(_GUIDE_INDEX)
        elif self._pages:
            self._navigate(next(iter(self._pages)))

    def _navigate(self, key: str) -> None:
        """Go to a page, recording the move in the history.

        Args:
            key: The page to open. Anything unknown is ignored rather than
                raising: keys reach here from prose that decoui did not write.
        """
        self._show(key, record=True)

    def _show(self, key: str, *, record: bool) -> None:
        """Open or raise one page's tab.

        Args:
            key: The page to show.
            record: Whether this counts as a visit. False for back and forward,
                which move through the history rather than adding to it.
        """
        if key != _GUIDE_INDEX and key not in self._pages:
            return
        if key == _GUIDE_INDEX and not self._guide:
            return

        browser = self._open_tabs.get(key)
        if browser is None:
            browser = self._new_tab(key)

        self._quiet += 1
        try:
            self._tabs.setCurrentWidget(browser)
            self._select_in_tree(key)
        finally:
            self._quiet -= 1

        if record:
            self._record(key)
        self._update_nav()

    def _new_tab(self, key: str) -> QTextBrowser:
        """Build the page and give it a tab.

        Args:
            key: The page to build.

        Returns:
            Its browser widget, already added to the tab strip.
        """
        browser = QTextBrowser(self._tabs)
        # Links are followed by decoui, not by the browser: left to itself
        # QTextBrowser treats an anchor as a document to load and blanks the
        # page when it cannot find one.
        browser.setOpenLinks(False)
        browser.setOpenExternalLinks(False)
        browser.anchorClicked.connect(self._follow)
        browser.setHtml(self._wrap(self._render(key)))
        self._open_tabs[key] = browser
        index = self._tabs.addTab(browser, self._title_for(key))
        self._tabs.setTabToolTip(index, key)
        self._install_close_button(index)
        return browser

    def _follow(self, url: QUrl) -> None:
        """Follow a clicked link: another help page, or the outside world.

        A cross-reference carries decoui's own scheme and moves this window. An
        ordinary URL is handed to the desktop, which opens it in the browser --
        the help window is not one, and rendering a fetched page inside a
        QTextBrowser would be both worse to read and a way to put the network
        in front of a reader who only meant to click a footnote.

        Args:
            url: The clicked anchor.

        Note:
            The scheme is checked again here even though
            :func:`decoui.markup.inline` already refused to build an anchor for
            anything outside :data:`decoui.markup.EXTERNAL_SCHEMES`. The two
            checks guard different things: that one decides what looks like a
            link, this one decides what is handed to the desktop, and the second
            is the one that matters if a page is ever rendered from HTML that
            did not come through the renderer.
        """
        scheme = url.scheme().lower()
        if scheme == LINK_SCHEME:
            self._navigate(
                url.path() or url.toString().removeprefix(f"{LINK_SCHEME}:")
            )
            return
        if scheme in EXTERNAL_SCHEMES:
            QDesktopServices.openUrl(url)

    def _install_close_button(self, index: int) -> None:
        """Attach a close button to a tab, inset from the tab's right edge.

        Qt's own close button is not used, for the reason
        :meth:`decoui.ui.main_window.MainWindow._install_close_button` gives:
        its position is fixed at the tab boundary regardless of stylesheet
        padding, so it sits on top of the tab's own border.

        Args:
            index: Position of the tab that was just added.
        """
        tab_bar = self._tabs.tabBar()
        holder = QWidget(tab_bar)
        holder.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, _CLOSE_BUTTON_INSET, 0)
        row.setSpacing(0)

        button = QToolButton(holder)
        button.setObjectName("tabCloseButton")
        button.setIcon(QIcon(str(icon_path("tab-close"))))
        button.setIconSize(QSize(_CLOSE_ICON_SIZE, _CLOSE_ICON_SIZE))
        button.setFixedSize(_CLOSE_BUTTON_SIZE, _CLOSE_BUTTON_SIZE)
        button.setToolTip(t("tabs.close"))
        button.setCursor(Qt.CursorShape.ArrowCursor)
        button.clicked.connect(lambda: self._close_tab_holding(holder))
        row.addWidget(button)

        tab_bar.setTabButton(index, QTabBar.ButtonPosition.RightSide, holder)

    def _close_tab_holding(self, holder: QWidget) -> None:
        """Close the tab whose close button lives in the provided holder.

        The index is resolved on click because tabs are movable, so an index
        captured at creation time goes stale.

        Args:
            holder: The widget the pressed button sits in.
        """
        tab_bar = self._tabs.tabBar()
        for index in range(tab_bar.count()):
            if tab_bar.tabButton(index, QTabBar.ButtonPosition.RightSide) is holder:
                self._close_tab(index)
                return

    def _close_other_tabs(self, index: int) -> None:
        """Close every tab except the one at the provided index.

        Args:
            index: The tab to keep.
        """
        if index < 0 or index >= self._tabs.count():
            return
        keep = self._tabs.widget(index)
        for position in range(self._tabs.count() - 1, -1, -1):
            if self._tabs.widget(position) is not keep:
                self._close_tab(position)
        self._tabs.setCurrentWidget(keep)

    def _close_all_tabs(self) -> None:
        """Close every tab, leaving the window empty but still navigable.

        The history survives: back still works, and following it reopens the
        page it lands on. Closing a tab has never meant forgetting it.
        """
        while self._tabs.count() > 0:
            self._close_tab(self._tabs.count() - 1)

    def _create_tab_context_menu(self, index: int) -> QMenu:
        """Create tab actions bound to the tab at the provided index.

        Args:
            index: Index of the tab that was right-clicked.

        Returns:
            A context menu containing close actions for that tab.
        """
        menu = QMenu(self)
        close_tab_action = menu.addAction(t("tabs.close"))
        close_other_tabs_action = menu.addAction(t("tabs.close_others"))
        close_all_tabs_action = menu.addAction(t("tabs.close_all"))
        close_other_tabs_action.setEnabled(self._tabs.count() > 1)
        close_tab_action.triggered.connect(
            lambda _checked=False: self._close_tab(index)
        )
        close_other_tabs_action.triggered.connect(
            lambda _checked=False: self._close_other_tabs(index)
        )
        close_all_tabs_action.triggered.connect(
            lambda _checked=False: self._close_all_tabs()
        )
        return menu

    def _show_tab_context_menu(self, position: QPoint) -> None:
        """Show close actions for the tab under the pointer.

        Args:
            position: Click position, in tab bar coordinates.
        """
        tab_bar = self._tabs.tabBar()
        tab_index = tab_bar.tabAt(position)
        if tab_index < 0:
            return
        menu = self._create_tab_context_menu(tab_index)
        menu.exec(tab_bar.mapToGlobal(position))
        menu.deleteLater()

    def _close_tab(self, index: int) -> None:
        """Close one tab, leaving its page in the history.

        Args:
            index: Position in the tab strip.
        """
        widget = self._tabs.widget(index)
        key = next((k for k, w in self._open_tabs.items() if w is widget), None)
        self._tabs.removeTab(index)
        if key is not None:
            del self._open_tabs[key]
        self._update_nav()

    # ── History ───────────────────────────────────────────────────────────────

    def _record(self, key: str) -> None:
        """Add one visit to the history.

        Anything ahead of the current position is dropped, which is what makes
        forward mean "the way I came back from" rather than "some page I saw
        once".

        Args:
            key: The page just arrived at.
        """
        if 0 <= self._at < len(self._history) and self._history[self._at] == key:
            return
        del self._history[self._at + 1:]
        self._history.append(key)
        self._at = len(self._history) - 1

    def _go_back(self) -> None:
        """Return to the previously visited page, reopening its tab if closed."""
        if self._at <= 0:
            return
        self._at -= 1
        self._show(self._history[self._at], record=False)

    def _go_forward(self) -> None:
        """Undo one back step."""
        if self._at >= len(self._history) - 1:
            return
        self._at += 1
        self._show(self._history[self._at], record=False)

    def _update_nav(self) -> None:
        """Enable each arrow only when there is somewhere for it to go."""
        self._back_btn.setEnabled(self._at > 0)
        self._forward_btn.setEnabled(self._at < len(self._history) - 1)

    # ── Keeping the three views in step ───────────────────────────────────────

    def _on_tab_changed(self, index: int) -> None:
        """Follow a tab the reader raised themselves.

        Args:
            index: The newly current tab, or -1 when the last one closed.
        """
        if self._quiet or index < 0:
            return
        widget = self._tabs.widget(index)
        key = next((k for k, w in self._open_tabs.items() if w is widget), None)
        if key is None:
            return
        self._quiet += 1
        try:
            self._select_in_tree(key)
        finally:
            self._quiet -= 1
        self._record(key)
        self._update_nav()

    def _on_tree_selection(
        self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None = None
    ) -> None:
        """Open whatever the tree moved to.

        Args:
            current: The newly selected row, or None when the tree emptied.
            _previous: Unused; part of Qt's signal.
        """
        if self._quiet or current is None:
            return
        key = current.data(0, _HELP_ROLE)
        if key:
            self._navigate(key)

    def _select_in_tree(self, key: str) -> None:
        """Move the tree's selection onto one page, without opening anything.

        Args:
            key: The page now showing. A page whose row the search has filtered
                away simply leaves the selection where it is.
        """
        iterator = QTreeWidgetItemIterator(self._tree)
        while iterator.value():
            item = iterator.value()
            if item.data(0, _HELP_ROLE) == key:
                self._tree.setCurrentItem(item)
                return
            iterator += 1

    # ── Theming ───────────────────────────────────────────────────────────────

    def retheme(self) -> None:
        """Re-render every open page under a new theme.

        All of them, not only the visible one: QTextBrowser does not read the
        application stylesheet, so each document carries the theme's colours
        inlined and each has to be rebuilt. A tab left in the old palette would
        surface the moment the reader clicked it.
        """
        for key, browser in self._open_tabs.items():
            browser.setHtml(self._wrap(self._render(key)))
        self._apply_icons()

    # ── The tree ──────────────────────────────────────────────────────────────

    def _rebuild_tree(self) -> None:
        """Refill the tree, honouring the current search text.

        A group whose own label matches keeps all its tools, so searching for a
        group name is a way to browse it rather than a way to empty it.

        Filtering never opens or closes a tab: typing is a way of looking for
        something, and a tab per keystroke is not what the reader asked for.
        """
        needle = self._search.text().strip().casefold()
        self._quiet += 1
        try:
            self._tree.clear()
            matched = False

            # decoui's own pages come first: a reader who does not yet know what
            # Replay does is not helped by an alphabetical list of somebody's tools.
            guide_matches = needle in t("help.guide_group").casefold()
            pages = [
                page for page in self._guide
                if not needle or guide_matches or needle in page.title.casefold()
            ]
            if pages:
                guide_root = QTreeWidgetItem(self._tree, [t("help.guide_group")])
                guide_root.setData(0, _HELP_ROLE, _GUIDE_INDEX)
                guide_root.setExpanded(True)
                matched = True
                for page in pages:
                    child = QTreeWidgetItem(guide_root, [page.title])
                    child.setData(0, _HELP_ROLE, page.page_id)

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
                matched = True

                parent = QTreeWidgetItem(self._tree, [group.label])
                parent.setData(0, _HELP_ROLE, group.set_id)
                parent.setExpanded(True)
                for tool in tools:
                    child = QTreeWidgetItem(parent, [tool.label])
                    child.setData(0, _HELP_ROLE, tool.tool_id)

            if not matched:
                # Said in the tree rather than on a page: the pages are tabs
                # the reader opened, and emptying one of them to report a
                # search result would throw away what they were reading.
                empty = QTreeWidgetItem(self._tree, [t("help.no_match")])
                empty.setDisabled(True)

            self._select_in_tree(self._current_key() or "")
        finally:
            self._quiet -= 1

    def _current_key(self) -> str | None:
        """Return the key of the page on screen, if any.

        Returns:
            The current tab's key, or None when no tab is open.
        """
        widget = self._tabs.currentWidget()
        return next((k for k, w in self._open_tabs.items() if w is widget), None)

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
h1 {{ font-size: {font.title_size_px}px; margin: 0 0 0.4em 0; }}
h2 {{ font-size: {font.size_pt + 1}pt; margin: 1.8em 0 0.5em 0;
     color: {colors['text.secondary']};
     border-bottom: 1px solid {colors['border.subtle']}; padding-bottom: 3px; }}
/* Paragraph spacing is set in em, and has to clear the line spacing inside a
   paragraph: at 145% those lines sit 22px apart, so the 6px margins this
   started with packed the paragraphs tighter than their own lines and the
   blank line between them stopped reading as a break at all. Qt honours em
   here, so this scales with a theme that sets a different body size. */
p  {{ margin: 1em 0; line-height: 145%; }}
.summary {{ color: {colors['text.secondary']}; margin: 0 0 1em 0; }}
/* Its own token, not `accent`: accent is a fill colour, and a link inked to
   match the selection highlight reads as something already selected. */
a {{ color: {colors['text.link']}; }}
.muted   {{ color: {colors['text.muted']}; }}
code {{ font-family: {', '.join(font.mono_family)};
        background: {colors['bg.field']}; padding: 1px 4px; }}
/* A fenced block, which is the only way to write a code sample: see
   decoui.markup for why indentation is not the other way. It is inked like the
   console rather than like an inline literal -- a sample is a thing to read as
   a block, and the console is the reader's reference for what code looks like
   in this application. */
pre {{ font-family: {', '.join(font.mono_family)};
       background: {colors['bg.console']}; color: {colors['console.stdout']};
       border: 1px solid {colors['border.console']};
       padding: 8px 10px; margin: 1em 0; }}
/* Headings an author writes, which start at h2: h1 is the page title and is
   decoui's, not theirs. Sized down the scale rather than by a fixed step, so a
   theme that sets a larger body size keeps the hierarchy legible. */
h3 {{ font-size: {font.size_pt}pt; margin: 1.4em 0 0.4em 0;
      color: {colors['text.secondary']}; }}
h4, h5, h6 {{ font-size: {font.size_pt}pt; margin: 1.2em 0 0.3em 0;
              color: {colors['text.muted']}; }}
/* Tinted rather than ruled down the left edge, which is the usual way to draw
   a quote and which Qt's rich-text CSS silently drops -- border-left on a block
   element is not in the subset QTextBrowser implements, so it rendered as a
   bare indent that read like a stray paragraph. */
blockquote {{ margin: 1em 0; padding: 6px 10px;
              background: {colors['bg.header']};
              color: {colors['text.secondary']}; }}
hr {{ height: 1px; background: {colors['border.subtle']}; border: none;
      margin: 1.4em 0; }}
ol {{ margin: 1em 0; }}
table {{ border-collapse: collapse; width: 100%; margin: 4px 0 2px 0; }}
th {{ background: {colors['bg.header']}; color: {colors['text.secondary']};
      text-align: left; padding: 5px 8px;
      border-bottom: 1px solid {colors['border.panel']}; }}
td {{ padding: 5px 8px; border-bottom: 1px solid {colors['bg.gridline']};
      vertical-align: top; }}
.req {{ color: {colors['text.required']}; font-weight: bold; }}
.type {{ font-family: {', '.join(font.mono_family)};
         color: {colors['text.muted']}; }}
/* The list sits apart from the prose around it by a paragraph's worth, while
   its own items stay tight -- that difference is what makes a list read as one
   thing rather than as more paragraphs. */
ul {{ margin: 1em 0; }}
li {{ margin: 0.15em 0; line-height: 145%; }}
</style></head><body>{body}</body></html>"""


def _guide_html(page: GuidePage, links: frozenset[str] = frozenset()) -> str:
    """Render one of decoui's own pages.

    Args:
        page: The guide page to show.
        links: Keys that resolve to a page, for cross-references in its prose.

    Returns:
        HTML for the right-hand pane.
    """
    return f"<h1>{escape(page.title)}</h1>{render(page.body, links)}"


def _guide_index_html(
    pages: tuple[GuidePage, ...], links: frozenset[str] = frozenset()
) -> str:
    """Render the contents page for decoui's own section.

    Args:
        pages: The guide pages, in reading order.
        links: Keys that resolve to a page. Each row's title becomes one, so
            the contents page is a way in rather than only a list.

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
            f"<tr><td><b>{reference(page.page_id, page.title, links)}</b></td>"
            f"<td>{render_inline(first.replace(chr(10), ' '), links)}</td></tr>"
        )
    parts.append("</table>")
    return "".join(parts)


def _group_html(group: ToolSetHelp, links: frozenset[str] = frozenset()) -> str:
    """Render a toolset's own page.

    Args:
        group: The toolset to describe.
        links: Keys that resolve to a page. Each tool in the table becomes one.

    Returns:
        HTML for the right-hand pane.
    """
    parts = [f"<h1>{escape(group.label)}</h1>"]
    if group.summary:
        parts.append(render(group.summary, links, css_class="summary"))
    parts.append(render(group.description, links))
    parts.append(f"<h2>{t('help.tools')}</h2><table>")
    for tool in group.tools:
        parts.append(
            f"<tr><td><b>{reference(tool.tool_id, tool.label, links)}</b></td>"
            f"<td>{render_inline(tool.summary, links)}</td></tr>"
        )
    parts.append("</table>")
    return "".join(parts)


def _tool_html(tool: ToolHelp, links: frozenset[str] = frozenset()) -> str:
    """Render one tool's page.

    Args:
        tool: The tool to describe.
        links: Keys that resolve to a page, for cross-references in its prose.

    Returns:
        HTML for the right-hand pane.
    """
    parts = [f"<h1>{escape(tool.label)}</h1>"]
    if tool.summary:
        parts.append(render(tool.summary, links, css_class="summary"))
    parts.append(render(tool.description, links))

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
            text = render_inline(param.text, links) if param.text else (
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
        parts.append(
            f"<h2>{t('help.returns')}</h2>" + render(tool.returns, links)
        )
    if tool.raises:
        parts.append(
            f"<h2>{t('help.raises')}</h2>" + render(tool.raises, links)
        )
    return "".join(parts)
