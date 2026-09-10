"""The application settings dialog.

Two settings, and both for the same reason: the theme and the interface language
are each applied once at startup and never swapped in a running window, so each
needs somewhere to be chosen ahead of the next launch. This dialog is
deliberately narrow -- it is not a drawer for everything that might one day be
configurable. Layout preferences decoui persists on its own (sidebar width,
window geometry) stay where they are; they are remembered, not chosen.

The dialog records choices and says a restart is needed. Nothing about the
running window changes when it closes.
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

from ..storage.db import get_setting, set_setting
from ..i18n import (
    LANGUAGE_SETTING,
    active_language,
    available_languages,
    language_name,
    t,
)
from ..theme import (
    THEME_SETTING,
    active_theme,
    active_theme_dir,
    builtin_themes,
    discover_themes,
)


def _preselect(combo: QComboBox, *, stored: str | None, in_effect: str) -> None:
    """Point a combo box at the stored choice, or at what is really running.

    Both of this dialog's settings apply on the next launch, so between the
    choice and the restart the two disagree. The stored value wins, because it
    is what the user last said they wanted; the running value is the fallback
    for when the stored one has since become unavailable.

    Args:
        combo: The box to move. Its items must carry their id as item data.
        stored: The persisted choice, or None when nothing was ever chosen.
        in_effect: Id of what the application actually started under.
    """
    for candidate in (stored, in_effect):
        if candidate is None:
            continue
        index = combo.findData(candidate)
        if index >= 0:
            combo.setCurrentIndex(index)
            return


class SettingsDialog(QDialog):
    """Modal dialog for choosing the theme and the interface language.

    Both settings take effect on the next launch, so each dropdown starts on
    **the stored choice** rather than on what the running window happens to be
    showing. Otherwise a user who picked a theme, pressed OK and reopened the
    dialog would find their choice apparently discarded -- it had been saved,
    but the dialog was reporting the still-running old one.

    A stored choice that is no longer available falls back to what is actually
    in effect, which is the case the previous behaviour existed for: a theme
    whose file has gone missing should not leave the dialog pointing at
    something the user cannot see.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the dialog and preselect the stored theme and language.

        Args:
            parent: Qt parent, used to centre the dialog over the window.
        """
        super().__init__(parent)
        self.setWindowTitle(t("settings.title"))
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
        self._combo = QComboBox(self)
        # Sorted by display name so the list is stable; duplicates are left as
        # they are, since the names are the user's own.
        for theme in sorted(themes.values(), key=lambda item: item.name.casefold()):
            self._combo.addItem(theme.name, theme.id)
        _preselect(
            self._combo,
            stored=get_setting(THEME_SETTING),
            in_effect=active_theme().id,
        )
        self._initial_id = self._combo.currentData()

        # Languages are labelled by their own name for themselves -- a reader
        # looking for their language recognises "Deutsch", not "German", and by
        # definition cannot read the current interface language well enough for
        # the alternative to help.
        self._language = QComboBox(self)
        for code in available_languages():
            self._language.addItem(language_name(code), code)
        _preselect(
            self._language,
            stored=get_setting(LANGUAGE_SETTING),
            in_effect=active_language(),
        )
        self._initial_language = self._language.currentData()

        form = QFormLayout()
        form.addRow(t("settings.theme"), self._combo)
        form.addRow(t("settings.language"), self._language)

        # Permanent, not a reaction to changing the selection: the user should
        # know a restart is coming *before* they choose, not after.
        note = QLabel(t("settings.restart_note"), self)
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

    def selected_language(self) -> str:
        """Return the language code currently shown in the combo box.

        Returns:
            The selected language's code.
        """
        return str(self._language.currentData())

    def accept(self) -> None:
        """Persist the choices, but only those that actually changed.

        Writing an unchanged value would be a pointless database round-trip and
        would make the settings table's timestamps misleading.
        """
        chosen = self.selected_theme_id()
        if chosen != self._initial_id:
            set_setting(THEME_SETTING, chosen)
        language = self.selected_language()
        if language != self._initial_language:
            set_setting(LANGUAGE_SETTING, language)
        super().accept()
