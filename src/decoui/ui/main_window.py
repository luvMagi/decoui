"""Main window with persistent sidebar layout and tabbed tool pages."""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QMainWindow,
    QMenu,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..registry import ToolInfo, ToolSetInfo
from ..storage.db import get_setting, set_setting
from .history_page import HistoryPage
from .nav_tree import NavTree
from .tag_bar import TagBar
from .tool_page import ToolPage

_SIDEBAR_WIDTH_SETTING = "ui.sidebar.width"
_DEFAULT_SIDEBAR_WIDTH = 220


class MainWindow(QMainWindow):
    """Host navigation, persistent layout state, and parallel tool tabs."""

    def __init__(self, tree: list[ToolSetInfo], title: str = "decoui") -> None:
        """Build the main application window.

        Args:
            tree: Registered toolsets and tools displayed in the sidebar.
            title: Application-specific suffix for the window title.
        """
        super().__init__()
        self.setWindowTitle(f"decoui — {title}")
        self.resize(1100, 700)

        self._tree = tree
        self._tool_pages: dict[str, ToolPage] = {}
        self._instances: dict[type, object] = {}

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
        outer.addWidget(self._splitter)

        # Sidebar
        sidebar = QWidget(self._splitter)
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)

        self._nav = NavTree(tree, sidebar)
        sidebar_layout.addWidget(self._nav)

        history_btn = QPushButton("History", sidebar)
        history_btn.clicked.connect(self._show_history)
        sidebar_layout.addWidget(history_btn)

        self._splitter.addWidget(sidebar)
        self._splitter.setStretchFactor(0, 0)

        # Stacked widget (main area)
        self._stack = QStackedWidget(self._splitter)
        self._splitter.addWidget(self._stack)
        self._splitter.setStretchFactor(1, 1)

        # History page
        self._history_page = HistoryPage(tool_labels, self._stack)
        self._history_page.replay_requested.connect(self._replay)
        self._stack.addWidget(self._history_page)

        # Tool tabs
        self._tabs = QTabWidget(self._stack)
        self._tabs.setDocumentMode(True)
        self._tabs.setMovable(True)
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._close_tool_tab)
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
        self._tabs.setCurrentIndex(tab_index)
        self._stack.setCurrentWidget(self._tabs)

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

    def _create_tab_context_menu(self, index: int) -> QMenu:
        """Create tab actions bound to the tab at the provided index.

        Args:
            index: Index of the tab that was right-clicked.

        Returns:
            A context menu containing close actions for the selected tab.
        """
        menu = QMenu(self)
        close_tab_action = menu.addAction("Close Tab")
        close_other_tabs_action = menu.addAction("Close Others")
        close_other_tabs_action.setEnabled(self._tabs.count() > 1)
        close_tab_action.triggered.connect(
            lambda _checked=False: self._close_tool_tab(index)
        )
        close_other_tabs_action.triggered.connect(
            lambda _checked=False: self._close_other_tabs(index)
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
