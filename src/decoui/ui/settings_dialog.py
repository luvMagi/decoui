"""The application settings dialog.

One dialog, one setting: which theme to run under. It is deliberately narrow --
it exists because the theme mechanism needs a way in, not as a drawer for
everything that might one day be configurable. Layout preferences that decoui
already persists on its own (sidebar width, window geometry) stay where they
are; they are remembered, not chosen.

Themes are applied once at startup, so this dialog records a choice and says so.
Nothing about the running window changes when it closes.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..storage.db import set_setting
from ..theme import (
    THEME_SETTING,
    active_theme,
    active_theme_dir,
    builtin_themes,
    discover_themes,
)


class SettingsDialog(QDialog):
    """Modal dialog for choosing the theme.

    The combo box lists every theme available right now -- built-in and
    user-supplied alike -- and starts on the one **actually in effect**. That
    matters when the stored choice could not be loaded: the dialog then shows
    the theme the user is really looking at, not the one they asked for.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the dialog and select the running theme.

        Args:
            parent: Qt parent, used to centre the dialog over the window.
        """
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(360)

        # Problems are ignored here: they were already reported at startup, and
        # a dialog is not the place to re-raise them. A theme that failed to
        # load simply is not in the list.
        #
        # The guard is not for those: it is for anything load_theme() might one
        # day let through that is *not* a ThemeError. This runs inside a Qt slot,
        # where an escaping exception leaves the event loop rather than merely
        # losing the list, so the gear button would stop opening Settings at all.
        # The built-ins are always enough to render a usable dialog.
        try:
            themes, _ = discover_themes(active_theme_dir())
        except Exception:
            themes = builtin_themes()
        current = active_theme()

        self._combo = QComboBox(self)
        # Sorted by display name so the list is stable; duplicates are left as
        # they are, since the names are the user's own.
        for theme in sorted(themes.values(), key=lambda item: item.name.casefold()):
            self._combo.addItem(theme.name, theme.id)
        index = self._combo.findData(current.id)
        if index >= 0:
            self._combo.setCurrentIndex(index)
        self._initial_id = self._combo.currentData()

        form = QFormLayout()
        form.addRow("Theme:", self._combo)

        # Permanent, not a reaction to changing the selection: the user should
        # know a restart is coming *before* they choose, not after.
        note = QLabel("Changes take effect after restart.", self)
        note.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addStretch()
        layout.addWidget(buttons)

    def selected_theme_id(self) -> str:
        """Return the theme id currently shown in the combo box.

        Returns:
            The selected theme's id.
        """
        return str(self._combo.currentData())

    def accept(self) -> None:
        """Persist the choice, but only when it actually changed.

        Writing an unchanged value would be a pointless database round-trip and
        would make the settings table's timestamps misleading.
        """
        chosen = self.selected_theme_id()
        if chosen != self._initial_id:
            set_setting(THEME_SETTING, chosen)
        super().accept()
