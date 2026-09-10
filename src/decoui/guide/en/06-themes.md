# Themes

The gear button at the top right opens Settings, which lists every available
theme and starts on the one currently in effect.

Themes are applied once, when the application starts, so a change takes effect
the **next** time it runs. Nothing about the open window changes when the dialog
closes; the dialog says so before you choose.

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
