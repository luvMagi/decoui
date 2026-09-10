"""Interface icons, drawn from SVG and inked from the active theme.

decoui used to write its icons as characters -- a gear, a magnifier, a broom --
straight into the interface strings. On Windows every one of those codepoints is
rendered through the colour emoji font, so they arrived as small pictures: the
only things in the window not made of flat ink, blurred at the size a toolbar
has room for, and stuck at whatever colour the font decided regardless of the
theme. A ``U+FE0E`` variation selector does not talk Qt out of it.

So decoui draws them. Each icon is one SVG stroked in the literal string
``currentColor``, and :func:`theme_icon` swaps that for a colour off the theme
before rendering. Qt's SVG renderer has no CSS cascade, so ``currentColor``
means nothing to it -- here it is a placeholder, chosen because it is what the
same trick is called in SVG proper.

**The colour is a token, not a constant.** Which token is the caller's to say,
because an icon is part of the text it sits beside: one inside a button is
button text and takes ``text.button``, one standing in for a placeholder takes
``text.muted``. Passing the wrong token is how you get an icon that stays dark
on a theme whose buttons went dark, so the tokens are named at each call site
rather than defaulted globally.

Icons are redrawn on a re-theme rather than restyled: they are pixmaps, and no
stylesheet reaches inside one. Any widget holding one needs a ``retheme()`` that
calls back here -- see :mod:`decoui.ui.retheme`.
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from ..assets import icon_path
from ..theme import active_theme

#: Edge of an interface icon, in logical pixels. Sized by eye against the text
#: it sits beside rather than derived from the font: an icon and a letter of the
#: same nominal size do not read as the same size.
ICON_PX = 18


def theme_icon(name: str, token: str = "text.button", *, ratio: float = 1.0) -> QIcon:
    """Render one shipped SVG in a colour taken from the active theme.

    Args:
        name: Icon file stem, as :func:`decoui.assets.icon_path` takes it.
        token: Colour token to ink it with. The default suits the common case,
            an icon on a push button; anything not on a button should say what
            it is instead of taking it.
        ratio: Device pixel ratio to render at, so the icon stays sharp on a
            scaled display. The pixmap is built that many times over and then
            told its own ratio, which is how Qt sizes it back down.

    Returns:
        An icon holding one pixmap, :data:`ICON_PX` logical pixels square. An
        icon that cannot be read or parsed comes back empty rather than raising:
        these are built while widgets are being constructed, and a missing file
        should cost one blank button, not the window.
    """
    path = icon_path(name)
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return QIcon()

    source = source.replace("currentColor", active_theme().colors[token])
    renderer = QSvgRenderer(QByteArray(source.encode("utf-8")))
    if not renderer.isValid():
        return QIcon()

    edge = round(ICON_PX * ratio)
    pixmap = QPixmap(edge, edge)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return QIcon(pixmap)
