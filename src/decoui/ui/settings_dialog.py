"""The application settings dialog.

Three settings, and all three about how decoui presents itself rather than about
what it does: the theme, the interface font, and the interface language. This
dialog is deliberately narrow -- it is not a drawer for everything that might
one day be configurable. Layout preferences decoui persists on its own (sidebar
width, window geometry) stay where they are; they are remembered, not chosen.

They differ in when they land, and the dialog says so before the user chooses. A
new **theme** and a new **font** are applied to every open window as the dialog
closes. A new **language** waits for the next launch: text is read as widgets
are built, in far more places than colour is, and there is no equivalent of the
application stylesheet to catch the rest.

The font box overrides one token, ``font.family``, and leaves the theme's sizes
and its monospaced stack alone -- see :func:`decoui.theme.with_font_family` for
why. Left empty it overrides nothing, which is why the box shows the running
theme's own stack as placeholder text rather than filling it in: an empty box
means "the theme decides", and pre-filling it would turn every visit to this
dialog into a font choice the user never made.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
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
    FONT_FAMILY_SETTING,
    THEME_SETTING,
    active_theme,
    active_theme_dir,
    builtin_themes,
    discover_themes,
    parse_font_family,
)
from .retheme import retheme_application


def _preselect(combo: QComboBox, *, stored: str | None, in_effect: str) -> None:
    """Point a combo box at the stored choice, or at what is really running.

    The two can disagree. The language applies on the next launch, so between
    the choice and the restart the stored value is not the running one; and a
    stored theme whose file has since gone missing is not running either. The
    stored value wins, because it is what the user last said they wanted; the
    running value is the fallback for when the stored one is unavailable.

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
    """Modal dialog for choosing the theme, the interface font and the language.

    Every field starts on **the stored choice** rather than on what the
    running window happens to be showing. That still matters for the language,
    which lands on the next launch: a user who picked one, pressed OK and
    reopened the dialog would otherwise find their choice apparently discarded
    -- it had been saved, but the dialog was reporting the still-running one.

    A stored choice that is no longer available falls back to what is actually
    in effect, which is the case the behaviour exists for: a theme whose file
    has gone missing should not leave the dialog pointing at something the user
    cannot see.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the dialog and preselect the stored theme, font and language.

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
        # Kept, because accept() applies the choice rather than only recording
        # it: it needs the theme itself, and re-reading the directory at that
        # point could hand back something different from what was on offer here.
        self._themes = themes
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

        # A plain line edit rather than a font picker: what a theme holds is a
        # *stack* tried in order, and the point of the last entry being a
        # generic family is that the application still renders on a machine that
        # has none of the named faces. A picker can only offer one installed
        # font, which is exactly the thing that does not travel.
        #
        # A name that matches nothing installed is not rejected. Qt simply falls
        # through to the next entry, which is the same thing it does for a theme
        # file naming a font this machine lacks -- and a box that refused every
        # face the user has not installed yet would be wrong the moment they
        # install one.
        self._font = QLineEdit(self)
        self._font.setText(get_setting(FONT_FAMILY_SETTING) or "")
        self._show_theme_font()
        self._combo.currentIndexChanged.connect(self._show_theme_font)
        self._initial_family = parse_font_family(self._font.text())

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
        form.addRow(t("settings.font_family"), self._font)
        form.addRow(t("settings.language"), self._language)

        # Permanent, not a reaction to changing the selection: the user should
        # know which of the two waits for a restart *before* they choose, not
        # after.
        note = QLabel(t("settings.apply_note"), self)
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

    def _show_theme_font(self, _index: int = 0) -> None:
        """Put the selected theme's own font stack behind the empty font box.

        Re-run whenever the theme selection moves, so the hint describes the
        theme the user is about to get rather than the one they arrived under.
        Without that, someone switching theme and leaving the font box empty
        would be told the wrong thing about what an empty box means for them.

        Args:
            _index: The combo box row, which the signal supplies and this does
                not need -- it reads the selection back off the box. Defaulted
                so ``__init__`` can call it directly for the first fill.
        """
        theme = self._themes.get(self.selected_theme_id())
        if theme is not None:
            self._font.setPlaceholderText(", ".join(theme.font.family))

    def selected_font_family(self) -> tuple[str, ...]:
        """Return the font stack currently typed into the box.

        Returns:
            The families in the order given, or an empty tuple when the box says
            nothing usable -- which is the value that means "leave the theme's
            own stack alone".
        """
        return parse_font_family(self._font.text())

    def selected_language(self) -> str:
        """Return the language code currently shown in the combo box.

        Returns:
            The selected language's code.
        """
        return str(self._language.currentData())

    def accept(self) -> None:
        """Persist the choices, and apply the theme to the running application.

        Only changed values are written: an unchanged one would be a pointless
        database round-trip and would make the settings table's timestamps
        misleading.

        The theme is compared against what is actually in effect, not against
        what was stored. The two can disagree -- a stored theme whose file has
        since gone missing leaves the dialog offering the running one instead --
        and it is the running one a re-theme would be redoing.

        The font is compared parsed rather than as typed, so that re-spacing the
        same names is not a change. What gets stored is the parsed form joined
        back up: the box is then re-read exactly as it will be applied, and a
        stray trailing comma does not survive to puzzle whoever reads the
        settings table.
        """
        chosen = self.selected_theme_id()
        if chosen != self._initial_id:
            set_setting(THEME_SETTING, chosen)
        family = self.selected_font_family()
        if family != self._initial_family:
            set_setting(FONT_FAMILY_SETTING, ", ".join(family))
        language = self.selected_language()
        if language != self._initial_language:
            set_setting(LANGUAGE_SETTING, language)

        # A font change re-themes even when the theme itself did not move: the
        # family reaches the window through the same three routes a theme does
        # -- the application stylesheet, the application font, and the widgets
        # that build their own style -- and only this pass covers all three.
        theme = self._themes.get(chosen)
        if theme is not None and (
            chosen != active_theme().id or family != self._initial_family
        ):
            retheme_application(theme)

        super().accept()
