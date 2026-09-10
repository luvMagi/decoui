"""Tag filter bar."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QPaintEvent, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QStyle,
    QStyleOption,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QWidget,
)

from ..i18n import t
from ..theme import active_theme


def _pill_style() -> str:
    """Build the tag pill stylesheet from the active theme.

    Pills set their own style rather than inheriting the global QPushButton
    rules, because they are the one control that is fully rounded.

    Returns:
        A stylesheet for one pill button.
    """
    theme = active_theme()
    colors, shape = theme.colors, theme.shape
    return (
        "QPushButton {"
        f"  border-radius: {shape['shape.radius_pill']:g}px;"
        "  padding: 2px 12px;"
        "  min-height: 26px;"
        f"  font-size: {theme.font.small_size_pt:g}pt;"
        f"  border: {shape['shape.border_width']:g}px solid {colors['border.button']};"
        f"  background: {colors['bg.surface']};"
        f"  color: {colors['text.secondary']};"
        "}"
        "QPushButton:checked {"
        f"  background: {colors['accent']};"
        f"  color: {colors['text.on_accent']};"
        f"  border-color: {colors['accent']};"
        "}"
        "QPushButton:hover:!checked {"
        f"  background: {colors['bg.button_hover']};"
        f"  border-color: {colors['border.button_hover']};"
        "}"
    )


class TagBar(QWidget):
    """Row of toggle pills, one per tag declared by any @toolset.

    Despite the name this is the window's top bar: it also carries the settings
    button, which has nowhere else to live while decoui has no menu bar.

    Attributes:
        tags_changed: Emitted with the set of active tags whenever a pill is
            toggled. The sidebar treats the set as an AND filter.
        settings_requested: Emitted when the settings button is pressed.
        help_requested: Emitted when the help button is pressed.
    """

    tags_changed = Signal(set)   # set of active tag strings
    settings_requested = Signal()
    help_requested = Signal()

    def __init__(self, all_tags: list[str], parent=None):
        """Build one pill per tag.

        Args:
            all_tags: Every tag found across the loaded toolsets.
            parent: Qt parent widget.
        """
        super().__init__(parent)
        self._active: set[str] = set()
        self._buttons: dict[str, QPushButton] = {}

        # Named so the stylesheet can give the top bar a band of its own. Left
        # to the generic QWidget rule it painted the same colour as the tab
        # strip and the page below it, and read as no band at all.
        self.setObjectName("tagBar")
        self.setFixedHeight(52)

        outer = QHBoxLayout(self)
        # A wider left inset than the other three: this is the first thing on
        # the window's top edge, and at 4px the label sat flush against the
        # frame. The extra spacing after the label keeps the first pill from
        # crowding it.
        outer.setContentsMargins(12, 2, 6, 2)
        outer.setSpacing(10)

        label = QLabel(t("topbar.tags"), self)
        outer.addWidget(label)
        self._label = label

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(40)
        # A QScrollArea draws a sunken panel border by default. Here it runs
        # right alongside the first pill's own border, and the two read as one
        # smudged line. Nothing about this area should be visible at all.
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        scroll.setVerticalScrollBarPolicy(
            __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        container = QWidget(scroll)
        container.setObjectName("tagStrip")
        row = QHBoxLayout(container)
        # Left inset inside the scrolling area as well as outside it: at zero
        # the first pill sits flush against the viewport edge, where its border
        # is clipped by the boundary.
        row.setContentsMargins(6, 0, 0, 0)
        row.setSpacing(6)

        all_btn = QPushButton(t("common.all"), container)
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
        self._scroll = scroll
        self._container = container

        # Added to the *outer* layout, deliberately: inside the scroll area it
        # would drift off-screen as soon as there were enough tags to scroll.
        # Out here it stays pinned to the top-right corner whatever happens.
        help_btn = QPushButton(t("topbar.help"), self)
        help_btn.setFixedWidth(36)
        help_btn.setToolTip(t("topbar.help_tooltip"))
        help_btn.clicked.connect(self.help_requested)
        outer.addWidget(help_btn)
        self._help_btn = help_btn

        settings_btn = QPushButton(t("topbar.settings"), self)
        settings_btn.setFixedWidth(36)
        settings_btn.setToolTip(t("topbar.settings_tooltip"))
        settings_btn.clicked.connect(self.settings_requested)
        outer.addWidget(settings_btn)
        self._settings_btn = settings_btn

        self._apply_styles()

    def _apply_styles(self) -> None:
        """Write every colour this bar sets on itself, from the active theme.

        Called from ``__init__`` and again from :meth:`retheme`, so the bar has
        exactly one description of its own colours rather than one per entry
        point that could drift from the other.
        """
        colors = active_theme().colors

        # Without this the label paints the generic QWidget background from the
        # application stylesheet, punching a lighter rectangle out of the bar's
        # band -- which is why the band looked as if it started after the label.
        self._label.setStyleSheet(
            f"background: transparent; color: {colors['text.on_topbar']};"
        )

        # A QScrollArea paints through a separate viewport widget, and the
        # generic QWidget rule in the application stylesheet reaches that
        # viewport. Asking for a transparent background is not enough to win
        # that cascade, so the band colour is painted onto the area, its
        # viewport and the pill container explicitly.
        #
        # Each selector names one widget by id. A stylesheet set on a widget
        # reaches its whole subtree, so the unqualified form would put the band
        # colour behind every pill as well -- harmless only for as long as each
        # pill keeps a stylesheet of its own to override it. history_page paid
        # this bill once already, with a transparent background that turned
        # every control in the filter row black.
        band = f"background: {colors['bg.topbar']};"
        self._scroll.setStyleSheet(f"QScrollArea {{ {band} border: none; }}")
        self._scroll.viewport().setStyleSheet(
            f"QWidget#qt_scrollarea_viewport {{ {band} }}"
        )
        self._container.setStyleSheet(f"QWidget#tagStrip {{ {band} }}")

        pill_style = _pill_style()
        self._all_btn.setStyleSheet(pill_style)
        for btn in self._buttons.values():
            btn.setStyleSheet(pill_style)

    def retheme(self) -> None:
        """Repaint the bar under the theme that has just become active.

        The band and the pills are the top bar's own work -- neither survives a
        stylesheet swap on its own. See :mod:`decoui.ui.retheme`.
        """
        self._apply_styles()

    def paintEvent(self, event: QPaintEvent) -> None:
        """Draw the stylesheet background Qt would otherwise skip.

        A plain QWidget subclass does not render ``background-color`` from a
        stylesheet on its own -- without this the bar's band is simply not
        painted, and whatever is behind it shows through. This is the sequence
        Qt's own documentation prescribes for the case.

        Args:
            event: The paint event, unused beyond triggering the draw.
        """
        option = QStyleOption()
        option.initFrom(self)
        painter = QPainter(self)
        self.style().drawPrimitive(
            QStyle.PrimitiveElement.PE_Widget, option, painter, self
        )

    def _toggle_tag(self, tag: str, checked: bool):
        """Add or remove one tag from the active set.

        Args:
            tag: The tag whose pill was clicked.
            checked: Its new state.
        """
        if checked:
            self._active.add(tag)
        else:
            self._active.discard(tag)
        self._all_btn.setChecked(len(self._active) == 0)
        self.tags_changed.emit(set(self._active))

    def _clear_all(self):
        """Deselect every pill, restoring the unfiltered sidebar."""
        self._active.clear()
        for btn in self._buttons.values():
            btn.setChecked(False)
        self._all_btn.setChecked(True)
        self.tags_changed.emit(set())
