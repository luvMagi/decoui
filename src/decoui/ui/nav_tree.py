"""Left sidebar navigation tree (ToolSet → Tool)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ..registry import ToolInfo, ToolSetInfo


class NavTree(QWidget):
    tool_selected = Signal(object)   # ToolInfo
    history_requested = Signal()

    def __init__(self, tree: list[ToolSetInfo], parent=None):
        super().__init__(parent)
        self._tree = tree
        self._active_tags: set[str] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._search = QLineEdit(self)
        self._search.setPlaceholderText("🔍 Search tools...")
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        self._tw = QTreeWidget(self)
        self._tw.setHeaderHidden(True)
        self._tw.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._tw)

        self._populate()

    def _populate(self):
        self._tw.clear()
        query = self._search.text().lower()

        for ts in self._tree:
            # Hide entire toolset if active tags don't match
            if self._active_tags and not self._active_tags.issubset(set(ts.tags)):
                continue

            ts_item = QTreeWidgetItem(self._tw, [ts.label])
            ts_item.setData(0, Qt.ItemDataRole.UserRole, ts)
            if ts.description:
                ts_item.setToolTip(0, ts.description)
            font = ts_item.font(0)
            font.setBold(True)
            ts_item.setFont(0, font)

            visible_tools = 0
            for tool in ts.tools:
                if query and query not in tool.label.lower():
                    continue
                t_item = QTreeWidgetItem(ts_item, [tool.label])
                t_item.setData(0, Qt.ItemDataRole.UserRole, tool)
                visible_tools += 1

            if visible_tools == 0 and query:
                self._tw.invisibleRootItem().removeChild(ts_item)
            else:
                ts_item.setExpanded(True)

    def _filter(self):
        self._populate()

    def set_active_tags(self, tags: set[str]):
        self._active_tags = tags
        self._populate()

    def _on_item_clicked(self, item: QTreeWidgetItem, _col: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, ToolInfo):
            self.tool_selected.emit(data)
