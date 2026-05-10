"""Main window with QSplitter layout."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QMainWindow,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from ..registry import ToolInfo, ToolSetInfo
from .history_page import HistoryPage
from .nav_tree import NavTree
from .tag_bar import TagBar
from .tool_page import ToolPage


class MainWindow(QMainWindow):
    def __init__(self, tree: list[ToolSetInfo], title: str = "decoui"):
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
        splitter = QSplitter(Qt.Orientation.Horizontal, central)
        outer.addWidget(splitter)

        # Sidebar
        sidebar = QWidget(splitter)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)

        self._nav = NavTree(tree, sidebar)
        sidebar_layout.addWidget(self._nav)

        history_btn = QPushButton("📜 History", sidebar)
        history_btn.clicked.connect(self._show_history)
        sidebar_layout.addWidget(history_btn)

        splitter.addWidget(sidebar)
        splitter.setStretchFactor(0, 0)

        # Stacked widget (main area)
        self._stack = QStackedWidget(splitter)
        splitter.addWidget(self._stack)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 880])

        # History page
        self._history_page = HistoryPage(tool_labels, self._stack)
        self._history_page.replay_requested.connect(self._replay)
        self._stack.addWidget(self._history_page)

        # Welcome placeholder
        welcome = QWidget(self._stack)
        self._stack.addWidget(welcome)
        self._stack.setCurrentWidget(welcome)

        # Signals
        self._nav.tool_selected.connect(self._show_tool)
        self._tag_bar.tags_changed.connect(self._nav.set_active_tags)

    def _get_instance(self, cls: type) -> object:
        if cls not in self._instances:
            self._instances[cls] = cls()
        return self._instances[cls]

    def _show_tool(self, tool_info: ToolInfo):
        tid = tool_info.tool_id
        if tid not in self._tool_pages:
            # Find the owning toolset class
            cls = next(
                ts.cls for ts in self._tree
                if any(t.tool_id == tid for t in ts.tools)
            )
            instance = self._get_instance(cls)
            page = ToolPage(tool_info, instance, self._stack)
            self._stack.addWidget(page)
            self._tool_pages[tid] = page
        self._stack.setCurrentWidget(self._tool_pages[tid])

    def _show_history(self):
        self._history_page.refresh()
        self._stack.setCurrentWidget(self._history_page)

    def _replay(self, tool_id: str, param_map: dict):
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
