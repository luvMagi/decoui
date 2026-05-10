"""Tag filter bar."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QWidget


class TagBar(QWidget):
    tags_changed = Signal(set)   # set of active tag strings

    def __init__(self, all_tags: list[str], parent=None):
        super().__init__(parent)
        self._active: set[str] = set()
        self._buttons: dict[str, QPushButton] = {}

        self.setFixedHeight(42)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(4, 2, 4, 2)

        label = QLabel("Tags:", self)
        outer.addWidget(label)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(38)
        scroll.setHorizontalScrollBarPolicy(
            __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        scroll.setVerticalScrollBarPolicy(
            __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        container = QWidget(scroll)
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        all_btn = QPushButton("All", container)
        all_btn.setCheckable(True)
        all_btn.setChecked(True)
        all_btn.clicked.connect(self._clear_all)
        row.addWidget(all_btn)
        self._all_btn = all_btn

        for tag in sorted(all_tags):
            btn = QPushButton(tag, container)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, t=tag: self._toggle_tag(t, checked))
            row.addWidget(btn)
            self._buttons[tag] = btn

        row.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll)

    def _toggle_tag(self, tag: str, checked: bool):
        if checked:
            self._active.add(tag)
        else:
            self._active.discard(tag)
        self._all_btn.setChecked(len(self._active) == 0)
        self.tags_changed.emit(set(self._active))

    def _clear_all(self):
        self._active.clear()
        for btn in self._buttons.values():
            btn.setChecked(False)
        self._all_btn.setChecked(True)
        self.tags_changed.emit(set())
