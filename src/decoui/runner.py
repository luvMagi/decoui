"""gui_main() entry point.

One call starts the whole application: it finds the toolsets, validates their
declarations, builds the tree, creates one instance of each, runs the startup
hooks and shows the window. It does not return -- it ends in ``sys.exit()``.

The startup order is fixed and documented on :func:`gui_main`; the important
consequence is that ``__init__`` and ``on_startup()`` both run **before** the
event loop starts, so neither may wait on a timer, a signal or a worker thread.
See ``docs/startup-lifecycle.md``.

Failures during startup are collected rather than fatal: a toolset that cannot
be constructed is dropped, everything else stays usable, and all the failures
are reported together in one dialog over the window.
"""
from __future__ import annotations

import inspect
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence
from typing import Callable

from .decorators import _TOOL_ATTR, _TOOLSET_ATTR
from .i18n import LANGUAGE_SETTING, set_language, t
from .theme import (
    DEFAULT_THEME_ID,
    THEME_SETTING,
    Theme,
    discover_themes,
    render_stylesheet,
    resolve_theme,
    set_active_theme,
    set_active_theme_dir,
    theme_font,
)
from .registry import build_tree
from .storage.db import get_setting, init_db, set_db_path


def gui_main(
    title: str = "decoui",
    db_path: str | Path | None = None,
    on_startup: Callable[[], None] | None = None,
    toolsets: Sequence[type] | None = None,
    theme: str | None = None,
    theme_dir: str | Path | None = None,
    language: str | None = None,
) -> None:
    """Launch the decoui GUI application.

    Auto-discovers all @toolset classes visible in the caller's global scope,
    unless ``toolsets`` names them explicitly.

    Startup runs in a fixed order, so anything loaded early is available later:

      1. ``db_path`` is applied and the database is initialised
      2. the theme is resolved and applied          <- before any widget exists
      3. the toolset tree is built and validated
      4. ``on_startup()`` runs                     <- application hook
      5. every toolset class is instantiated       <- ``self`` exists from here
      6. each instance's own ``on_startup()`` method runs, if it defines one
      7. the window is shown and the event loop starts

    Failures in steps 2 and 4-6 do not stop the application: they are collected
    and reported in one dialog over the main window, and everything that did
    load stays usable. An unusable theme in particular is never fatal -- the
    application falls back to the built-in light theme and says so.

    Both hooks run on the GUI thread before the event loop starts. See
    docs/startup-lifecycle.md for what that rules out.

    Args:
        title:   Window title.
        db_path: Path to the SQLite history and settings database. Defaults to
            ~/.decoui/history.db.
        on_startup: Called once at step 3, for application-wide work: opening a
            shared connection, fetching a token, warming a cache. It runs
            before any toolset instance exists, so it cannot write to ``self``
            -- to load data a single toolset owns, give that class its own
            ``on_startup()`` method instead.
        toolsets: The @toolset classes to load. When given, the calling
            namespace is not scanned at all, so imports exist only for the
            classes named here and need no ``# noqa: F401``. When omitted,
            every @toolset class visible to the caller is discovered.

            The list order does not reach the navigation tree: build_tree()
            sorts toolsets and tools by label. Pass an explicit list to
            control *what* loads, not what order it appears in.
        theme: Id of the theme to start under. This is the application's
            *default*, not a lock: a theme the user picked in Settings wins
            over it, the same way db_path names a location while the data in it
            is the user's. Defaults to the built-in light theme.
        theme_dir: Directory scanned for user-supplied ``*.json`` themes.
            Defaults to ``~/.decoui/themes``. A missing directory is fine and
            is not created.
        language: Code for the language decoui's **own** interface is drawn in
            -- Run, Stop, the history columns. Like ``theme``, this is the
            application's default and the user's choice in Settings wins over
            it. A tool's own label, description and docstring are never
            translated: they belong to the application, not to decoui.
            Defaults to English.

    Raises:
        RuntimeError: If no @toolset class is visible in the calling namespace,
            or if ``toolsets`` is an empty sequence.
        TypeError: If ``toolsets`` holds anything that is not a @toolset class.
    """
    if db_path is not None:
        set_db_path(Path(db_path))

    if toolsets is None:
        # Walk up the call stack to find the first frame outside this module,
        # then collect every class decorated with @toolset from that namespace.
        caller_globals = _caller_globals()
        toolset_classes = [
            obj
            for obj in caller_globals.values()
            if isinstance(obj, type) and hasattr(obj, _TOOLSET_ATTR)
        ]

        if not toolset_classes:
            raise RuntimeError(
                "gui_main() found no @toolset classes in the calling namespace. "
                "Make sure to import them before calling gui_main()."
            )
    else:
        toolset_classes = _check_explicit_toolsets(toolsets)

    from PySide6.QtGui import QFont, QIcon
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(_icon_path())))

    # The database comes first: the user's theme and language choices live in
    # it. Both are applied before anything is built, because widgets read their
    # text and the colours they ink themselves with as they are constructed.
    # The theme can be swapped later (ui/retheme.py); the language cannot.
    init_db()
    # Language before the theme, and both before anything is built: the theme's
    # own failure dialog is written in decoui's interface language, so the
    # language has to be settled before there is anything to report.
    set_language(get_setting(LANGUAGE_SETTING) or language)
    problems = _apply_startup_theme(app, theme, theme_dir)

    tree = build_tree(*toolset_classes)

    # Startup hooks run here, before show(): whatever they cost is time the
    # user spends looking at nothing. Nothing below starts the event loop, so
    # neither hook may wait on a timer or a worker thread.
    problems += _run_startup_hook(on_startup)
    instances, init_problems = _create_instances(tree)
    problems += init_problems
    problems += _run_toolset_hooks(instances)

    # Toolsets that failed to construct have no instance to build pages from.
    tree = [ts for ts in tree if ts.cls in instances]

    from .ui.main_window import MainWindow
    window = MainWindow(tree, title=title, instances=instances)
    window.show()
    _show_startup_problems(problems, window)

    sys.exit(app.exec())


def _check_explicit_toolsets(toolsets: Sequence[type]) -> list[type]:
    """Validate the explicit toolsets list handed to gui_main().

    Args:
        toolsets: The sequence passed as ``gui_main(toolsets=...)``.

    Returns:
        The same classes as a list, in the caller's order.

    Raises:
        RuntimeError: If the sequence is empty. This is kept distinct from the
            auto-discovery failure so the message can say which one happened.
        TypeError: If an entry is not a class decorated with @toolset.
    """
    toolset_classes = list(toolsets)
    if not toolset_classes:
        raise RuntimeError(
            "gui_main(toolsets=[]) was given an empty list. Pass the @toolset "
            "classes to load, or omit the argument to discover them from the "
            "calling namespace."
        )

    for candidate in toolset_classes:
        if not (isinstance(candidate, type) and hasattr(candidate, _TOOLSET_ATTR)):
            name = getattr(candidate, "__name__", repr(candidate))
            raise TypeError(
                f"gui_main(toolsets=...) got {name}, which is not decorated "
                f"with @toolset"
            )
    return toolset_classes


def _apply_startup_theme(
    app, theme: str | None, theme_dir: str | Path | None
) -> list[StartupProblem]:
    """Resolve and apply the theme, collecting whatever went wrong.

    Args:
        app: The QApplication to style.
        theme: The application's default theme id, or None.
        theme_dir: Directory of user themes, or None for the default.

    Returns:
        Problems to report once the window is up. Never raises: a theme is
        presentation, and refusing to start over one would be out of all
        proportion to what it costs the user.

    Note:
        The stored choice outranks the ``theme`` argument. If it names
        something unavailable, the fallback is the built-in light theme rather
        than the argument -- the setting is treated as temporarily unresolvable,
        not as wrong.
    """
    set_active_theme_dir(theme_dir)
    try:
        themes, discovery_problems = discover_themes(theme_dir)
        requested = get_setting(THEME_SETTING) or theme
        active, resolve_problems = resolve_theme(themes, requested)
    except Exception:
        # Nothing above is supposed to raise: one unusable file becomes one
        # ThemeProblem inside discover_themes, so the rest of the directory
        # still loads. This path exists only so that a defect in theme loading
        # can never be what stops an application from opening -- reaching it
        # costs the user every theme they wrote, so it is a bug, not a policy.
        from .theme import builtin_themes as _builtin
        active = _builtin()[DEFAULT_THEME_ID]
        _apply_theme(app, active)
        return [StartupProblem(
            source=t("theme.problem_source"),
            summary=t("theme.problem_summary"),
            detail=traceback.format_exc(),
        )]

    _apply_theme(app, active)
    return [
        StartupProblem(source=p.source, summary=p.summary, detail=p.detail)
        for p in (*discovery_problems, *resolve_problems)
    ]


@dataclass(frozen=True)
class StartupProblem:
    """One failure recorded while starting the application.

    Attributes:
        source: What failed, in user-facing terms.
        summary: One-line reason, shown in the dialog body.
        detail: Full traceback, shown behind the dialog's Details button.
    """

    source: str
    summary: str
    detail: str


def _run_startup_hook(on_startup: Callable[[], None] | None) -> list[StartupProblem]:
    """Run the application startup hook, if one was given.

    Called at step 3: QApplication exists, the database is initialised, but no
    toolset instance exists and the event loop has not started. Two consequences
    the hook author has to live with, documented in docs/startup-lifecycle.md:

      * No ``self`` to write to -- that is what ToolSet.on_startup() is for.
      * No event loop -- timers do not fire and QThreadPool results never
        arrive, so waiting on a background thread here deadlocks startup.

    A failure is reported but never fatal: the rest of the application is still
    usable, and a dialog is a better diagnosis than a window that refuses to
    open.

    Args:
        on_startup: Zero-argument callable, or None.

    Returns:
        One problem if the hook raised, otherwise an empty list.
    """
    if on_startup is None:
        return []
    try:
        on_startup()
    except Exception as exc:
        return [StartupProblem(
            source=f"on_startup={_callable_name(on_startup)}",
            summary=f"{type(exc).__name__}: {exc}",
            detail=traceback.format_exc(),
        )]
    return []


def _create_instances(tree: list) -> tuple[dict[type, object], list[StartupProblem]]:
    """Instantiate every registered toolset class before the window appears.

    Creating them eagerly makes ``__init__`` a reliable place to declare state:
    it runs once, after on_startup, and always before the event loop starts.

    A class whose ``__init__`` raises is skipped — there is no object to hang a
    tool page on — but the other toolsets still load.

    Args:
        tree: The toolset tree returned by build_tree().

    Returns:
        A mapping of toolset class to its shared instance, and the failures.
    """
    instances: dict[type, object] = {}
    problems: list[StartupProblem] = []
    for toolset_info in tree:
        try:
            instances[toolset_info.cls] = toolset_info.cls()
        except Exception as exc:
            problems.append(StartupProblem(
                source=f"@toolset('{toolset_info.label}')",
                summary=f"{toolset_info.cls.__name__}.__init__ raised "
                        f"{type(exc).__name__}: {exc}",
                detail=traceback.format_exc(),
            ))
    return instances, problems


def _run_toolset_hooks(instances: dict[type, object]) -> list[StartupProblem]:
    """Call ``on_startup()`` on every toolset instance that defines one.

    Called at step 5, after construction and after the application hook, so a
    toolset can declare its attributes in ``__init__`` and fill them here. A
    failure leaves the instance in place with whatever ``__init__`` declared, so
    its tools still open with fallback values -- which is the whole reason to
    keep ``__init__`` trivial.

    Order between toolsets follows build_tree()'s alphabetical sort and must not
    be relied on; cross-toolset setup belongs in the application hook.

    Args:
        instances: Toolset instances created by _create_instances().

    Returns:
        One problem per hook that raised.
    """
    problems: list[StartupProblem] = []
    for cls, instance in instances.items():
        hook = getattr(instance, "on_startup", None)
        if not callable(hook) or hasattr(hook, _TOOL_ATTR):
            continue
        try:
            hook()
        except Exception as exc:
            problems.append(StartupProblem(
                source=f"{cls.__name__}.on_startup()",
                summary=f"{type(exc).__name__}: {exc}",
                detail=traceback.format_exc(),
            ))
    return problems


def _show_startup_problems(problems: list[StartupProblem], parent=None) -> None:
    """Report startup failures in a modal dialog over the main window.

    Args:
        problems: Failures collected during startup; nothing is shown if empty.
        parent: Widget the dialog is modal to.
    """
    if not problems:
        return

    from PySide6.QtWidgets import QMessageBox

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(t("startup.title"))
    box.setText(t("startup.text", count=len(problems)))
    box.setInformativeText(
        "\n".join(f"• {problem.source}\n    {problem.summary}" for problem in problems)
    )
    box.setDetailedText(
        "\n\n".join(f"--- {problem.source} ---\n{problem.detail}" for problem in problems)
    )
    box.exec()


def _callable_name(target: Callable) -> str:
    """Return a readable name for a callback, for use in error messages.

    Args:
        target: Any callable.

    Returns:
        Its qualified name, or its repr when it has none.
    """
    return getattr(target, "__qualname__", None) or repr(target)


# The application stylesheet now lives in decoui.theme, rendered from the
# active theme's tokens. See theme.render_stylesheet().



def _apply_fonts(app, theme: Theme) -> None:
    """Set the application font from the theme.

    Args:
        app: The QApplication to configure.
        theme: The theme supplying the font.
    """
    app.setFont(theme_font(theme))


def _apply_theme(app, theme: Theme) -> None:
    """Install a theme: its stylesheet, its font, and the record of what is live.

    This is the startup path, running before any widget exists. Changing theme
    later goes through :func:`decoui.ui.retheme.retheme_application`, which does
    the same three things and then walks the open windows -- widgets that style
    themselves in code have to be told, because a stylesheet swap does not reach
    what they set on themselves.

    Args:
        app: The QApplication to configure.
        theme: The theme to apply.
    """
    set_active_theme(theme)
    _apply_fonts(app, theme)
    app.setStyleSheet(render_stylesheet(theme))


def _icon_path() -> Path:
    """Resolve icon.png whether running from source or installed wheel."""
    from importlib.resources import files
    try:
        ref = files("decoui") / "icon.png"
        # as_file gives a real Path even inside a zip/wheel
        from importlib.resources import as_file
        from contextlib import ExitStack
        _stack = ExitStack()
        return Path(str(_stack.enter_context(as_file(ref))))
    except Exception:
        return Path(__file__).parent / "icon.png"


def _caller_globals() -> dict:
    """Return the global namespace of the first frame outside decoui itself."""
    this_pkg = __name__.split(".")[0]
    for frame_info in inspect.stack():
        module = frame_info.frame.f_globals.get("__name__", "")
        if not module.startswith(this_pkg):
            return frame_info.frame.f_globals
    return {}
