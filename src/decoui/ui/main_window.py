"""Main window with persistent sidebar layout and tabbed tool pages.

Holds the tag bar, the searchable sidebar and a tab area of open tool pages,
plus the shared History page. Sidebar width and window geometry are persisted in
the ``app_setting`` table and restored on the next launch.

Two behaviours worth knowing when writing tools:

* **Each toolset is instantiated once** and that single instance backs every
  page built from it, for the whole session. Instance state set in ``__init__``
  or ``on_startup()`` is therefore shared between a toolset's tools -- and
  outlives any individual run.
* **Closing a tab does not stop a running tool.** The page and its execution
  engine keep going; the run finishes and is recorded as usual.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..assets import tab_close_icon_path
from ..registry import ToolInfo, ToolSetInfo
from ..storage.db import get_setting, set_setting
from .history_page import HistoryPage
from .nav_tree import NavTree
from ..i18n import t
from ..theme import apply_label_case
from .settings_dialog import SettingsDialog
from .tag_bar import TagBar
from .tool_page import ToolPage

_SIDEBAR_WIDTH_SETTING = "ui.sidebar.width"
_DEFAULT_SIDEBAR_WIDTH = 220

_CLOSE_BUTTON_SIZE = 16
_CLOSE_ICON_SIZE = 10
#: Qt pins the tab's right-side widget to the tab rectangle's edge, which lands
#: on top of the tab border. The holder carries this much right margin so the
#: glyph is inset within the tab instead of straddling its boundary.
_CLOSE_BUTTON_INSET = 7


class MainWindow(QMainWindow):
    """Host navigation, persistent layout state, and parallel tool tabs."""

    def __init__(
        self,
        tree: list[ToolSetInfo],
        title: str = "decoui",
        instances: dict[type, object] | None = None,
    ) -> None:
        """Build the main application window.

        Args:
            tree: Registered toolsets and tools displayed in the sidebar.
            title: Application-specific suffix for the window title.
            instances: Toolset instances created during startup. Classes absent
                from the map are instantiated on first use.
        """
        super().__init__()
        self.setWindowTitle(t("app.window_title", title=title))
        self.resize(1100, 700)

        self._tree = tree
        self._tool_pages: dict[str, ToolPage] = {}
        self._instances: dict[type, object] = dict(instances or {})
        self._help_window: QWidget | None = None

        # Collect all tags
        all_tags: list[str] = sorted({
            tag
            for ts in tree
            for tag in ts.tags
        })

        # {tool_id: "ToolSet Label: Tool Label"} sorted by display label
        tool_labels: dict[str, str] = dict(sorted(
            {
                tool.tool_id: f"{ts.label}: {tool.label}"
                for ts in tree
                for tool in ts.tools
            }.items(),
            key=lambda kv: kv[1],
        ))

        # Central widget
        central = QWidget(self)
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Tag bar
        self._tag_bar = TagBar(all_tags, central)
        outer.addWidget(self._tag_bar)

        # Splitter
        self._splitter = QSplitter(Qt.Orientation.Horizontal, central)
        # The default handle is a few pixels wide and the stylesheet paints it
        # as a hairline, which leaves almost nothing to aim at. Widening the
        # handle keeps the divider looking thin while giving the pointer a
        # target it can actually hit; the :hover rule makes it discoverable.
        self._splitter.setHandleWidth(6)
        outer.addWidget(self._splitter)

        # Sidebar
        sidebar = QWidget(self._splitter)
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)

        self._nav = NavTree(tree, sidebar)
        sidebar_layout.addWidget(self._nav)

        history_btn = QPushButton(t("nav.history"), sidebar)
        history_btn.clicked.connect(self._show_history)
        sidebar_layout.addWidget(history_btn)

        self._splitter.addWidget(sidebar)
        self._splitter.setStretchFactor(0, 0)

        # Stacked widget (main area)
        self._stack = QStackedWidget(self._splitter)
        # A QStackedWidget's minimum width is the widest of *all* its pages, so
        # without this the History page's filter row fixed the minimum width of
        # the content area -- and therefore capped how far the sidebar could be
        # dragged -- even while a tool page was showing. Naming a minimum here
        # lets the content area shrink; a page narrower than it wants simply
        # clips, which is the user's own choice when they drag the divider.
        self._stack.setMinimumWidth(400)
        self._splitter.addWidget(self._stack)
        # ...and the content area must honour that minimum rather than being
        # collapsed away entirely. A splitter ignores a child's minimum width
        # while that child is collapsible, so without this the divider could be
        # dragged all the way across and the tool page would vanish.
        self._splitter.setCollapsible(1, False)
        self._splitter.setStretchFactor(1, 1)

        # History page
        self._history_page = HistoryPage(tool_labels, self._stack)
        self._history_page.replay_requested.connect(self._replay)
        self._history_page.close_requested.connect(self._close_history)
        self._stack.addWidget(self._history_page)

        # Tool tabs
        self._tabs = QTabWidget(self._stack)
        self._tabs.setDocumentMode(True)
        self._tabs.setMovable(True)
        tab_bar = self._tabs.tabBar()
        tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tab_bar.customContextMenuRequested.connect(self._show_tab_context_menu)
        self._stack.addWidget(self._tabs)

        # Welcome placeholder
        self._welcome = QWidget(self._stack)
        self._stack.addWidget(self._welcome)
        self._stack.setCurrentWidget(self._welcome)

        # Persist splitter changes after dragging settles.
        self._settings_timer = QTimer(self)
        self._settings_timer.setSingleShot(True)
        self._settings_timer.setInterval(250)
        self._settings_timer.timeout.connect(self._save_sidebar_width)
        self._splitter.splitterMoved.connect(self._schedule_sidebar_width_save)
        self._restore_sidebar_width()

        # Signals
        self._nav.tool_selected.connect(self._show_tool)
        self._tag_bar.tags_changed.connect(self._nav.set_active_tags)
        self._tag_bar.settings_requested.connect(self._open_settings)
        self._tag_bar.help_requested.connect(self._open_help)

        # Capitals, when the theme asks for them. Done after everything is
        # built so it reaches the tag pills, the tab bar and every button.
        apply_label_case(self)

    def _open_help(self) -> None:
        """Open the help window, or raise the one already open.

        One window, not one per press: help is a reference the reader keeps
        beside the form, and a second copy of the same page helps nobody.

        The reference is dropped on ``destroyed`` rather than being appended to
        a list. ``WA_DeleteOnClose`` destroys the underlying C++ object, so a
        kept reference is a dead wrapper that raises ``RuntimeError`` the moment
        anything touches it.
        """
        if self._help_window is not None:
            self._help_window.raise_()
            self._help_window.activateWindow()
            return

        from .help_window import HelpWindow
        window = HelpWindow(self._tree, self)
        window.destroyed.connect(self._forget_help_window)
        self._help_window = window
        window.show()

    def _forget_help_window(self) -> None:
        """Clear the help window reference once Qt has destroyed it."""
        self._help_window = None

    def _open_settings(self) -> None:
        """Open the settings dialog.

        The dialog does its own work: it records the choices, and applies a new
        theme to every open window before it closes. Nothing is left for this
        window to do -- a re-theme reaches it through the same pass as any other
        window, not because it happens to be the one that opened the dialog.
        """
        SettingsDialog(self).exec()

    def _get_instance(self, cls: type) -> object:
        """Return the shared instance for a registered toolset class."""
        if cls not in self._instances:
            self._instances[cls] = cls()
        return self._instances[cls]

    def _show_tool(self, tool_info: ToolInfo) -> None:
        """Open or activate a tool in the tabbed work area."""
        tid = tool_info.tool_id
        if tid not in self._tool_pages:
            # Find the owning toolset class
            cls = next(
                ts.cls for ts in self._tree
                if any(t.tool_id == tid for t in ts.tools)
            )
            instance = self._get_instance(cls)
            page = ToolPage(tool_info, instance, self._tabs)
            page.history_requested.connect(self._show_history_for_tool)
            self._tool_pages[tid] = page
        page = self._tool_pages[tid]
        tab_index = self._tabs.indexOf(page)
        if tab_index < 0:
            tab_index = self._tabs.addTab(page, tool_info.label)
            self._tabs.setTabToolTip(tab_index, tool_info.tool_id)
            self._install_close_button(tab_index)
        self._tabs.setCurrentIndex(tab_index)
        self._stack.setCurrentWidget(self._tabs)

    def _install_close_button(self, index: int) -> None:
        """Attach a close button to a tab, inset from the tab's right edge.

        Qt's own close button is not used: styling ``QTabBar::tab:selected``
        suppresses its glyph on the active tab, and its position is fixed at
        the tab boundary regardless of stylesheet padding or margins.
        """
        tab_bar = self._tabs.tabBar()
        holder = QWidget(tab_bar)
        holder.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, _CLOSE_BUTTON_INSET, 0)
        row.setSpacing(0)

        button = QToolButton(holder)
        button.setObjectName("tabCloseButton")
        button.setIcon(QIcon(str(tab_close_icon_path())))
        button.setIconSize(QSize(_CLOSE_ICON_SIZE, _CLOSE_ICON_SIZE))
        button.setFixedSize(_CLOSE_BUTTON_SIZE, _CLOSE_BUTTON_SIZE)
        button.setToolTip(t("tabs.close"))
        button.setCursor(Qt.CursorShape.ArrowCursor)
        button.clicked.connect(lambda: self._close_tab_holding(holder))
        row.addWidget(button)

        tab_bar.setTabButton(index, QTabBar.ButtonPosition.RightSide, holder)

    def _close_tab_holding(self, holder: QWidget) -> None:
        """Close the tab whose close button lives in the provided holder.

        The index is resolved on click because tabs are movable and closable,
        so an index captured at creation time goes stale.
        """
        tab_bar = self._tabs.tabBar()
        for index in range(tab_bar.count()):
            if tab_bar.tabButton(index, QTabBar.ButtonPosition.RightSide) is holder:
                self._close_tool_tab(index)
                return

    def _close_history(self) -> None:
        """Leave the history view for whatever the user was looking at.

        Falls back to the welcome page when no tool tab is open, which is the
        case this exists for: the history page filled the content area and the
        only route out was opening a tool.
        """
        if self._tabs.count() > 0:
            self._stack.setCurrentWidget(self._tabs)
        else:
            self._stack.setCurrentWidget(self._welcome)

    def _close_tool_tab(self, index: int) -> None:
        """Hide a tool tab while preserving its page and running task."""
        if index < 0 or index >= self._tabs.count():
            return
        self._tabs.removeTab(index)
        if self._tabs.count() == 0:
            self._stack.setCurrentWidget(self._welcome)

    def _close_other_tabs(self, index: int) -> None:
        """Hide every tool tab except the tab at the provided index."""
        if index < 0 or index >= self._tabs.count():
            return
        selected_page = self._tabs.widget(index)
        for tab_index in range(self._tabs.count() - 1, -1, -1):
            if self._tabs.widget(tab_index) is not selected_page:
                self._tabs.removeTab(tab_index)
        self._tabs.setCurrentWidget(selected_page)
        self._stack.setCurrentWidget(self._tabs)

    def _close_all_tabs(self) -> None:
        """Hide every tool tab and return to the welcome page."""
        while self._tabs.count() > 0:
            self._tabs.removeTab(self._tabs.count() - 1)
        self._stack.setCurrentWidget(self._welcome)

    def _create_tab_context_menu(self, index: int) -> QMenu:
        """Create tab actions bound to the tab at the provided index.

        Args:
            index: Index of the tab that was right-clicked.

        Returns:
            A context menu containing close actions for the selected tab.
        """
        menu = QMenu(self)
        close_tab_action = menu.addAction(t("tabs.close"))
        close_other_tabs_action = menu.addAction(t("tabs.close_others"))
        close_all_tabs_action = menu.addAction(t("tabs.close_all"))
        close_other_tabs_action.setEnabled(self._tabs.count() > 1)
        close_tab_action.triggered.connect(
            lambda _checked=False: self._close_tool_tab(index)
        )
        close_other_tabs_action.triggered.connect(
            lambda _checked=False: self._close_other_tabs(index)
        )
        close_all_tabs_action.triggered.connect(
            lambda _checked=False: self._close_all_tabs()
        )
        return menu

    def _show_tab_context_menu(self, position: QPoint) -> None:
        """Show close actions for the tab under the pointer."""
        tab_bar = self._tabs.tabBar()
        tab_index = tab_bar.tabAt(position)
        if tab_index < 0:
            return
        menu = self._create_tab_context_menu(tab_index)
        menu.exec(tab_bar.mapToGlobal(position))
        menu.deleteLater()

    def _show_history(self) -> None:
        """Refresh and display the execution history page."""
        self._history_page.refresh()
        self._stack.setCurrentWidget(self._history_page)

    def _show_history_for_tool(self, tool_id: str) -> None:
        """Display execution history filtered to one tool."""
        self._history_page.show_for_tool(tool_id)
        self._stack.setCurrentWidget(self._history_page)

    def _replay(self, tool_id: str, param_map: dict[str, object]) -> None:
        """Open a tool tab and restore parameters from an execution record."""
        # Find and show the tool page, then restore params
        tool_info = next(
            (t for ts in self._tree for t in ts.tools if t.tool_id == tool_id),
            None,
        )
        if tool_info is None:
            return
        self._show_tool(tool_info)
        page = self._tool_pages.get(tool_id)
        if page:
            page.restore_params(param_map)

    def _restore_sidebar_width(self) -> None:
        """Restore the sidebar width from application settings."""
        stored_width = get_setting(_SIDEBAR_WIDTH_SETTING)
        try:
            sidebar_width = (
                int(stored_width)
                if stored_width is not None
                else _DEFAULT_SIDEBAR_WIDTH
            )
        except ValueError:
            sidebar_width = _DEFAULT_SIDEBAR_WIDTH
        sidebar_width = max(0, sidebar_width)
        content_width = max(1, self.width() - sidebar_width)
        self._splitter.setSizes([sidebar_width, content_width])

    def _schedule_sidebar_width_save(self, _position: int, _index: int) -> None:
        """Debounce persistence while the splitter handle is being dragged."""
        self._settings_timer.start()

    def _save_sidebar_width(self) -> None:
        """Persist the current sidebar width in the application database."""
        sizes = self._splitter.sizes()
        if sizes:
            set_setting(_SIDEBAR_WIDTH_SETTING, str(sizes[0]))

    def closeEvent(self, event: QCloseEvent) -> None:
        """Flush pending layout settings before the main window closes."""
        self._settings_timer.stop()
        self._save_sidebar_width()
        super().closeEvent(event)
