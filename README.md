<div align="center">
  <p><strong>English</strong> · <a href="README-ZH-CN.md">简体中文</a> · <a href="README-JP.md">日本語</a> · <a href="README-KR.md">한국어</a></p>
  <img src="docs/images/icon.png" width="96" alt="decoui icon">
  <h1>decoui</h1>
  <p><strong>Turn annotated Python methods into native desktop tools people can actually use.</strong></p>
  <p>Decorator-driven GUI framework for Python · Built with PySide6</p>

  <p>
    <a href="https://pypi.org/project/decoui/"><img src="https://img.shields.io/pypi/v/decoui?label=PyPI&color=3775A9" alt="PyPI version"></a>
    <img src="https://img.shields.io/pypi/pyversions/decoui?label=Python" alt="Supported Python versions">
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-green" alt="Apache 2.0 license"></a>
  </p>
</div>

decoui turns function signatures into forms, executions into live logs, and every run into a traceable record. You keep writing Python business logic; decoui supplies the Qt window, background execution, history, replay, settings, and help system.

![decoui application preview](docs/images/preview-theme_preview_diagonal.png)

## What decoui does for you

| From code to desktop tool | What decoui provides |
|---|---|
| **① Annotate** | Describe existing Python methods with `@toolset`, `@tool`, and type annotations. |
| **② Collect** | Discover toolsets automatically, or choose them explicitly with `toolsets=[...]`. |
| **③ Launch** | Generate a searchable sidebar, tag filters, parallel tool tabs, and a shared settings entry point. |
| **④ Fill** | Map Python types to native widgets, with autocomplete, cascading values, and lazy defaults when needed. |
| **⑤ Trace** | Run work in the background, capture `print` and `logging`, persist parameters and logs, and replay previous inputs. |
| **⑥ Ship** | Apply themes, i18n catalogues, and collected help content to turn an internal script into a usable desktop application. |

## Help and localization, built in

### Turn docstrings into user-facing help

**Document the method once.** decoui automatically collects docstrings into searchable, navigable help pages—complete with summaries, parameters, return values, exceptions, and cross-references.

<p align="center">
  <img src="docs/images/auto-summary-help.png" width="100%" alt="decoui automatically collects docstrings into user-facing help pages">
</p>

### Make every user feel at home

**One interface, many languages.** Select the interface language and provide application catalogues for your own labels, fields, descriptions, and help content—without rebuilding the UI.

<p align="center">
  <img src="docs/images/i18n-support.png" width="100%" alt="decoui interface language selection and i18n support">
</p>

## More than a generated form

- **Themes** — Four built-in looks: Light, Cockpit, Mission Control, and Industrial 1980s. Extend or replace them with JSON, and switch themes without interrupting running tools.
- **Internationalization (i18n)** — decoui ships its own interface catalogues. Your tool labels, fields, descriptions, and help content can use separate application catalogues.
- **Collected help** — Build summaries, parameter tables, return values, and error documentation from docstrings. Add long-form Markdown and cross-reference other help pages.
- **Reliable execution** — Run tools on background threads with progress reporting, timeouts, cancellation, and streamed child-process output.
- **History and replay** — Persist every run in SQLite, filter the history, inspect full logs, and restore an earlier parameter snapshot.

## Start in 30 seconds

```bash
pip install decoui
```

Requires Python 3.10 or later. decoui depends on the smaller `PySide6-Essentials` package by default, without pulling in the complete `PySide6-Addons` payload.

```python
import logging

from decoui import gui_main, tool, toolset


@toolset(label="Text Tools", tags=["text"])
class TextTools:
    @tool(
        label="Count Characters",
        description="Count characters, words, and lines.",
        placeholders={"content": "Paste text here..."},
    )
    def count(self, content: str = "") -> None:
        words = len(content.split())
        logging.info("%d chars / %d words", len(content), words)


if __name__ == "__main__":
    gui_main(title="My Tools")
```

Run the file. `gui_main()` discovers every `@toolset` in the caller's namespace and builds the complete application around it.

```bash
python app.py
```

## Types become forms

| Python type | Generated control |
|---|---|
| `str` | Single-line text field |
| `int` / `float` | Numeric input |
| `bool` | Checkbox |
| `list` / `dict` | Multi-line editor |
| `Enum` | Dropdown |
| `pathlib.Path` | Path field with file and directory pickers |

Add `completions`, `cascade`, and `defaults` for autocomplete, dependent fields, and runtime defaults. The underlying methods remain ordinary Python and can still be called and tested without the GUI.

## Documentation

The detailed material has moved out of this README so you can jump directly to the guide you need:

- [Complete API and behavior reference](docs/reference.md) — decorators, type mapping, form assistance, themes, storage, history, and more
- [Startup lifecycle](docs/startup-lifecycle.md) — initialization order, loading data, and failure handling
- [Application translation](docs/translating-an-application.md) — localizing tool text and long-form help
- [Help authoring](docs/help-authoring.md) — docstrings, Markdown, and cross-references
- [Cancellation and child processes](docs/cancelling-a-run.md) — implementing Stop, timeouts, and cleanup correctly
- [Design and implementation](docs/design.md) — module structure, execution engine, storage, and UI architecture

For a complete example covering every supported feature, explore [`src/decoui/example/`](src/decoui/example/) and run:

```bash
python -m decoui.example
```

## Where it fits

Data processors, operations utilities, batch-job launchers, internal productivity tools, and Python scripts intended for non-developers—especially when the business logic already exists and only needs a reliable desktop entry point.

> decoui is currently in Alpha. Please share real-world issues and feedback through [GitHub Issues](https://github.com/luvmagi/decoui/issues).

## License

[Apache-2.0](LICENSE)
