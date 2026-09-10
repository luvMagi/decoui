# Themes

The gear button at the top right opens Settings, which lists every available
theme and starts on the one currently in effect.

Themes are applied at once. Choosing one restyles every window that is open,
without rebuilding anything: a tool that is running goes on running, forms keep
what was typed into them, and output already printed is re-inked in the new
colours. The console's scroll position is the one casualty -- it returns to the
newest line.

The **font family** box in the same dialog overrides the interface font the
theme asks for, and lands at once the same way a theme does. Type the faces you
want separated by commas -- `Georgia, serif` -- and they are tried in order, so
ending on a generic family (`sans-serif`, `serif`) keeps the interface readable
on a machine that has none of the others. Leave the box empty and the theme
decides; the greyed-out text behind an empty box is the stack it would use.

The override reaches the interface only. The console and the log viewer keep the
theme's monospaced face, because their output is aligned in columns and a
proportional font would scatter it. The theme's font *sizes* stay too -- this
chooses a face, not a scale.

The **language**, chosen in the same dialog, is the exception: it takes effect
the next time the application runs. Text is read as each widget is built, in far
more places than colour is, and there is nothing that can catch the rest the way
the stylesheet catches colour.

Four themes ship with decoui: a light default, and three panel-styled ones.

Your own themes are read from ``~/.decoui/themes`` -- one JSON file each, no
Python required. A theme file names its colours, corner radii and fonts; the
simplest way to write one is to start from a built-in with ``extends`` and
override only what you want to change.

A theme is presentation, so a broken one is never fatal: an unreadable file is
skipped and every other theme still loads, and a selection that cannot be
resolved falls back to the light theme. Either case is reported when the
application starts.

Your selection is stored by id, so renaming a theme does not lose it, and a
theme that is temporarily missing is not un-selected -- it takes effect again
once the file is back.
