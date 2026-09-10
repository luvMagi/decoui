"""The dialog that says a restart is needed, in the language just chosen.

Everything else in the settings dialog lands the moment it is pressed. The
**language** does not: text is read as each widget is built, in far more places
than colour is, so decoui reads it once at startup and does not swap it in a
running window. A user who picks a language and sees nothing change has been
given no way to tell "not yet" from "did not work".

Two decisions make this dialog worth having rather than being one more
click-through:

**It is written in the language the user chose**, not the one still on screen.
A Japanese reader who has just asked for Japanese should be told in Japanese --
that is also the clearest possible confirmation that the choice was understood.
The running language cannot be moved to say it, because every other widget is
still drawn in the old one, so the text comes from
:func:`decoui.i18n.t_in` rather than from ``t``.

**Its button is locked for a moment.** A dialog whose button can be hit before
the eye has reached the text is a dialog that gets dismissed unread, and this
one carries the only warning the user will get. The countdown is visible on the
button, so the wait reads as deliberate rather than as the application hanging.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..i18n import language_name, t_in
from ..theme import active_theme

#: Seconds the button stays locked. Long enough to stop a reflex click landing
#: on a dialog that was never read, short enough not to feel like a punishment.
LOCK_SECONDS = 3


class RestartNoticeDialog(QDialog):
    """Modal notice that the chosen language waits for the next launch.

    Attributes:
        language: The code the notice is written in, which is also the language
            being announced.
    """

    def __init__(self, language: str, parent: QWidget | None = None) -> None:
        """Build the notice and start its countdown.

        Args:
            language: The language the user chose. Everything on this dialog is
                read from that catalogue, whatever the running language is.
            parent: Qt parent, used to centre the dialog.
        """
        super().__init__(parent)
        self.language = language
        self._remaining = LOCK_SECONDS

        theme = active_theme()
        self.setWindowTitle(t_in(language, "settings.restart_title"))
        self.setModal(True)
        self.setMinimumWidth(460)

        heading = QLabel(t_in(language, "settings.restart_title"), self)
        heading.setWordWrap(True)
        # Bigger than the surrounding interface on purpose: this is the one
        # thing on screen that the user has to actually read, and a notice set
        # at body size reads as a form label. title_size_px is the theme's own
        # answer to "how big is a heading", so a theme that scales its type
        # scales this too.
        heading.setStyleSheet(
            f"font-size: {theme.font.title_size_px:g}px; font-weight: bold;"
            f" color: {theme.colors['text.primary']};"
        )

        body = QLabel(
            t_in(
                language,
                "settings.restart_body",
                language=language_name(language),
            ),
            self,
        )
        body.setWordWrap(True)
        body.setStyleSheet(f"color: {theme.colors['text.secondary']};")

        self._button = QPushButton(self)
        self._button.setEnabled(False)
        self._button.setDefault(True)
        self._button.clicked.connect(self.accept)
        self._show_countdown()

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self._button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(heading)
        layout.addWidget(body)
        layout.addSpacing(4)
        layout.addLayout(buttons)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ── The countdown ─────────────────────────────────────────────────────────

    @property
    def locked(self) -> bool:
        """Whether the notice is still refusing to be dismissed.

        Returns:
            True until the countdown has run out.
        """
        return self._remaining > 0

    def _show_countdown(self) -> None:
        """Write the button's label for the current state of the countdown."""
        if self.locked:
            self._button.setText(
                t_in(self.language, "settings.restart_wait", seconds=self._remaining)
            )
        else:
            self._button.setText(t_in(self.language, "common.ok"))

    def _tick(self) -> None:
        """Count one second off, and unlock the button when they run out."""
        self._remaining -= 1
        self._show_countdown()
        if not self.locked:
            self._timer.stop()
            self._button.setEnabled(True)
            self._button.setFocus()

    # ── Refusing to be dismissed early ────────────────────────────────────────

    def keyPressEvent(self, event) -> None:
        """Swallow Escape while the countdown runs.

        Args:
            event: The key event.

        Note:
            Without this the lock is decoration: Escape closes a QDialog by
            default, so the one keystroke most likely to be pressed reflexively
            would dismiss the notice faster than the button ever could.
        """
        if self.locked and event.key() == Qt.Key.Key_Escape:
            event.ignore()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Refuse the title bar's close button while the countdown runs.

        Args:
            event: The close event.
        """
        if self.locked:
            event.ignore()
            return
        super().closeEvent(event)
