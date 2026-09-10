"""Left sidebar navigation tree (ToolSet → Tool)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ..i18n import t
from ..registry import ToolInfo, ToolSetInfo
from .icons import theme_icon


class NavTree(QWidget):
    """Searchable sidebar listing every toolset and its tools.

    Groups come from ``@toolset(label=...)``, leaves from ``@tool(label=...)``,
    both already sorted by label in the registry. Search and tag filters only
    hide rows -- nothing is unloaded, and a hidden tool is still reachable
    through history replay.
    """
    tool_selected = Signal(object)   # ToolInfo
    history_requested = Signal()

    def __init__(self, tree: list[ToolSetInfo], parent=None):
        """Build the tree widget over a tool tree.

        Args:
            tree: The toolsets to list.
            parent: Qt parent widget.
        """
        super().__init__(parent)
        self._tree = tree
        self._active_tags: set[str] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._search = QLineEdit(self)
        self._search.setPlaceholderText(t("nav.search_placeholder"))
        self._search.textChanged.connect(self._filter)
        # addAction, not a character in the placeholder: a placeholder is text
        # and disappears the moment anything is typed, which took the magnifier
        # with it. A leading action is part of the field and stays put.
        self._search_icon = self._search.addAction(
            theme_icon("search", "text.muted", ratio=self.devicePixelRatioF()),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        layout.addWidget(self._search)

        self._tw = QTreeWidget(self)
        self._tw.setHeaderHidden(True)
        self._tw.setIndentation(max(1, self._tw.indentation() // 2))
        self._tw.itemClicked.connect(self._on_item_clicked)
        self._tw.currentItemChanged.connect(self._on_current_changed)
        layout.addWidget(self._tw)

        self._populate()

    def retheme(self) -> None:
        """Redraw the search field's magnifier in the new theme's ink.

        Icons are pixmaps and no stylesheet reaches inside one; everything else
        in the sidebar is dressed by the application stylesheet. See
        :mod:`decoui.ui.retheme`.
        """
        self._search_icon.setIcon(
            theme_icon("search", "text.muted", ratio=self.devicePixelRatioF())
        )

    def _populate(self):
        """Rebuild the visible rows from the search text and active tags."""
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
        """Re-run filtering after the search box changed."""
        self._populate()

    def set_active_tags(self, tags: set[str]):
        """Restrict the tree to toolsets carrying all of these tags.

        Args:
            tags: Active tag set. Empty means no tag filtering. The match is an
                AND: a toolset must carry every active tag to stay visible.
        """
        self._active_tags = tags
        self._populate()

    def _on_current_changed(self, current: QTreeWidgetItem, _prev):
        """Announce the newly highlighted tool.

        Args:
            current: The item now selected.
            _prev: The previous item, unused.
        """
        if current:
            self._on_item_clicked(current, 0)

    def _on_item_clicked(self, item: QTreeWidgetItem, _col: int):
        """Announce a click, which opens the tool even if already selected.

        Args:
            item: The clicked item.
            _col: The clicked column, unused.
        """
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, ToolInfo):
            self.tool_selected.emit(data)
