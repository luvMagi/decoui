"""Map native Python type annotations to PySide6 widgets.

This module is the contract between a tool's signature and its form. Annotating
a parameter is the *only* way to choose its widget -- there is no widget
argument, no builder DSL, and nothing in ``@tool`` overrides what is decided
here.

Supported types::

    str            -> QLineEdit
    int            -> QSpinBox
    float          -> QDoubleSpinBox
    bool           -> QCheckBox
    list / list[X] -> QTextEdit (comma- and newline-separated)
    dict           -> QTextEdit (JSON / ast.literal_eval, raises on bad input)
    enum.Enum      -> QComboBox (dropdown)
    pathlib.Path   -> QLineEdit + file-picker + folder-picker buttons

Rules that decide what a tool actually receives
-----------------------------------------------

* **Anything unrecognised becomes a QLineEdit and is passed through as a str.**
  There is no error and no warning. A parameter annotated ``datetime``,
  ``set[str]``, a dataclass, or one of the marker types in :mod:`decoui.types`
  reaches the method as whatever the user typed. Annotate parameters with the
  types in the table above and convert inside the method if you need more.

* **Only single-Optional unions are unwrapped.** ``Optional[Path]`` and
  ``Path | None`` build the path widget; ``int | str`` has two non-None members,
  so it falls through to the text field.

* ``bool`` is checked before ``int`` on purpose -- ``bool`` is a subclass of
  ``int``, and testing in the other order would give every checkbox a spin box.

* ``Annotated[X, ...]`` never reaches this module. The registry strips it and
  stores the bare ``X``, so metadata cannot influence widget choice.

* **A list field cannot hold values containing commas.** The text is split on
  newlines *and* on commas (ASCII and fullwidth), then blanks are dropped.

* **An empty path field is not None.** ``pathlib.Path("")`` would be falsy, so
  an empty field becomes ``Path()`` -- which is ``Path('.')``, the current
  directory. Check for it explicitly if a tool treats "no path" as a case.

* **An Enum parameter receives the member**, not its name: the combo box stores
  the member as item data and hands it back untouched.

* Conversion failures never abort a run before it starts in silence: they are
  collected by :func:`coerce_params`, printed to the console as ERROR entries,
  and the run is refused. The offending value is left uncoerced in the dict.
"""
from __future__ import annotations

import enum
import inspect
import pathlib
import re
from typing import Any, get_args, get_origin

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QWidget,
)

from .i18n import t


# ── Marker subclass to distinguish dict QTextEdit from list QTextEdit ─────────
#
# dict and list both render as a QTextEdit, but their values are read back in
# completely different ways (JSON object vs. split-and-strip list). get_value()
# has only the widget to go on, so the dict case needs its own class.

class _DictTextEdit(QTextEdit):
    """QTextEdit that reads back as a dict rather than a list of lines."""


#: Floor for the two path-picker buttons. A minimum rather than a fixed width:
#: pinning them clipped every label longer than "File..." -- Japanese needs
#: 93px at the default size, and cockpit's capitals take "FOLDER..." to 110px.
#: The floor clears both with room to spare, and at it the two buttons come out
#: the same width, which is what makes them read as a pair.
_PICKER_MIN_WIDTH = 112

# ── Path widget: QLineEdit + file-picker + folder-picker ──────────────────────

class _PathWidget(QWidget):
    """Composite widget for pathlib.Path parameters.

    Attributes:
        committed: Emitted when the user finishes editing the path, either by
            leaving the line edit or by accepting a file/folder dialog.
    """

    committed = Signal()

    def __init__(self, parent=None):
        """Build the line edit and its two picker buttons.

        Args:
            parent: Qt parent widget.
        """
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._edit = QLineEdit(self)
        self._edit.editingFinished.connect(self.committed)
        layout.addWidget(self._edit)

        self._file_btn = QPushButton(t("field.file_button"), self)
        self._file_btn.setMinimumWidth(_PICKER_MIN_WIDTH)
        self._file_btn.setToolTip(t("field.file_tooltip"))
        self._file_btn.clicked.connect(self._pick_file)
        layout.addWidget(self._file_btn)

        self._dir_btn = QPushButton(t("field.folder_button"), self)
        self._dir_btn.setMinimumWidth(_PICKER_MIN_WIDTH)
        self._dir_btn.setToolTip(t("field.folder_tooltip"))
        self._dir_btn.clicked.connect(self._pick_dir)
        layout.addWidget(self._dir_btn)

    def _pick_file(self):
        """Open a file dialog and adopt the chosen path."""
        path, _ = QFileDialog.getOpenFileName(self, t("field.file_dialog"), self._edit.text())
        if path:
            self._edit.setText(path)
            self.committed.emit()

    def _pick_dir(self):
        """Open a directory dialog and adopt the chosen path."""
        path = QFileDialog.getExistingDirectory(self, t("field.folder_dialog"), self._edit.text())
        if path:
            self._edit.setText(path)
            self.committed.emit()

    def text(self) -> str:
        """Return the path text, matching the QLineEdit interface."""
        return self._edit.text()

    def setText(self, text: str) -> None:
        """Replace the path text.

        Args:
            text: The path to show.
        """
        self._edit.setText(text)

    def setPlaceholderText(self, text: str) -> None:
        """Set the hint shown while the path is empty.

        Args:
            text: The placeholder text.
        """
        self._edit.setPlaceholderText(text)


# ── Public API ────────────────────────────────────────────────────────────────

def build_widget(param_info, parent=None) -> QWidget:
    """Create the input widget for one parameter.

    Args:
        param_info: The ParamInfo built by the registry. Its ``annotation`` is
            already stripped of ``Annotated`` wrappers.
        parent: Qt parent for the new widget.

    Returns:
        A widget whose value is read with :func:`get_value` and written with
        :func:`set_value`. Never None: an unrecognised annotation yields a
        QLineEdit rather than an error.
    """
    ann = param_info.annotation
    default = param_info.default if param_info.has_default else inspect.Parameter.empty
    placeholder = param_info.placeholder

    inner = _unwrap_optional(ann)
    w = _build_for_type(inner, default, parent)

    if placeholder:
        _apply_placeholder(w, placeholder)

    return w


def get_value(widget: QWidget) -> Any:
    """Read the current value out of a widget built by :func:`build_widget`.

    The result is still raw: it matches the widget, not the annotation. A spin
    box gives an int, but a QLineEdit standing in for a Path gives a str.
    :func:`coerce_params` is what turns these into the declared types.

    Args:
        widget: A widget produced by :func:`build_widget`.

    Returns:
        The widget's value, or None for a widget type this module did not
        build.
    """
    # Order matters here as well: _DictTextEdit and _PathWidget must be tested
    # before their base classes further down.
    if isinstance(widget, QCheckBox):
        return widget.isChecked()
    if isinstance(widget, QSpinBox):
        return widget.value()
    if isinstance(widget, QDoubleSpinBox):
        return widget.value()
    if isinstance(widget, QComboBox):
        return widget.currentData()
    if isinstance(widget, _PathWidget):
        return widget.text()
    if isinstance(widget, _DictTextEdit):
        return _parse_dict(widget.toPlainText().strip())
    if isinstance(widget, QTextEdit):
        # The plain (non-dict) QTextEdit is the list field. Split on newlines and
        # on both comma characters, strip, drop blanks -- which also means a list
        # item can never contain a comma.
        raw = widget.toPlainText()
        items = [s.strip() for part in raw.splitlines() for s in re.split(r"[,，]", part)]
        return [x for x in items if x]
    if isinstance(widget, QLineEdit):
        return widget.text()
    return None


def set_value(widget: QWidget, value: Any) -> None:
    """Write a value into a widget, converting as the widget requires.

    Used for defaults, for cascade results and for replaying a past run's
    parameters. Values that do not fit are coerced rather than rejected: a combo
    box ignores a member it does not have, and anything else falls back to
    ``str(value)``.

    Args:
        widget: A widget produced by :func:`build_widget`.
        value: The value to display. None becomes an empty field.
    """
    if isinstance(widget, _PathWidget):
        widget.setText(str(value) if value is not None else "")
        return
    if isinstance(widget, QCheckBox):
        widget.setChecked(bool(value))
    elif isinstance(widget, QSpinBox):
        widget.setValue(int(value))
    elif isinstance(widget, QDoubleSpinBox):
        widget.setValue(float(value))
    elif isinstance(widget, QComboBox):
        if isinstance(value, enum.Enum):
            idx = widget.findData(value)
        else:
            idx = widget.findText(str(value))
        if idx >= 0:
            widget.setCurrentIndex(idx)
    elif isinstance(widget, _DictTextEdit):
        import json
        if isinstance(value, dict):
            widget.setPlainText(json.dumps(value, ensure_ascii=False, indent=2))
        else:
            widget.setPlainText(str(value) if value is not None else "")
    elif isinstance(widget, QTextEdit):
        if isinstance(value, list):
            widget.setPlainText("\n".join(str(x) for x in value))
        else:
            widget.setPlainText(str(value) if value is not None else "")
    elif isinstance(widget, QLineEdit):
        widget.setText(str(value) if value is not None else "")


def completion_target(widget: QWidget) -> QLineEdit | None:
    """Return the line edit a completer should attach to.

    Args:
        widget: A widget produced by build_widget().

    Returns:
        The widget itself for a plain QLineEdit, the inner line edit for a path
        widget, or None when the widget cannot host a completer.
    """
    if isinstance(widget, _PathWidget):
        return widget._edit
    if isinstance(widget, QLineEdit):
        return widget
    return None


def supports_completion(annotation: Any) -> bool:
    """Report whether a parameter annotation maps to a completable widget.

    Args:
        annotation: The parameter's type annotation.

    Returns:
        True when the annotation builds a QLineEdit or a path widget.
    """
    ann = _unwrap_optional(annotation)
    if ann is pathlib.Path:
        return True
    if ann is dict or get_origin(ann) is dict:
        return False
    if ann is list or get_origin(ann) is list:
        return False
    if ann in (bool, int, float):
        return False
    if isinstance(ann, type) and issubclass(ann, enum.Enum):
        return False
    return True


def coerce_params(tool_info, raw: dict) -> tuple[dict, list[str]]:
    """Cast widget values to the types declared in the method signature.

    This is what makes a tool receive a real ``Path``, ``int`` or Enum member
    rather than the string the user typed.

    Args:
        tool_info: The ToolInfo whose params describe the target types.
        raw: Widget values keyed by parameter name, from :func:`get_value`.

    Returns:
        A ``(coerced, errors)`` pair. ``errors`` holds one formatted traceback
        per parameter that could not be cast; a non-empty list means the caller
        must refuse to run. Failed parameters keep their raw value in
        ``coerced``, so the dict is always complete.

    Note:
        An unannotated parameter, or one annotated ``str``, is passed through
        untouched. Empty path fields become ``Path()`` -- the current directory,
        not None.
    """
    import traceback
    from typing import get_args, get_origin

    coerced: dict = {}
    errors: list[str] = []
    param_map = {p.name: p for p in tool_info.params}

    for name, value in raw.items():
        param = param_map.get(name)
        if param is None:
            coerced[name] = value
            continue

        ann = _unwrap_optional(param.annotation)
        origin = get_origin(ann)
        args = get_args(ann)

        try:
            if ann is inspect.Parameter.empty or ann is str:
                coerced[name] = value
            elif ann is pathlib.Path:
                coerced[name] = pathlib.Path(value) if value else pathlib.Path()
            elif ann is bool:
                coerced[name] = bool(value)
            elif ann is int:
                coerced[name] = int(value)
            elif ann is float:
                coerced[name] = float(value)
            elif ann is dict or origin is dict:
                if isinstance(value, dict):
                    coerced[name] = value
                elif isinstance(value, str):
                    coerced[name] = _parse_dict(value)
                elif isinstance(value, list):
                    # fallback: QTextEdit list branch was hit, re-join and parse
                    coerced[name] = _parse_dict("\n".join(value))
                else:
                    raise TypeError(f"Cannot convert {type(value).__name__} to dict")
            elif ann is list or origin is list:
                item_type = args[0] if args else str
                if isinstance(value, list):
                    coerced[name] = value if item_type is str else [item_type(x) for x in value]
                else:
                    coerced[name] = value
            elif isinstance(ann, type) and issubclass(ann, enum.Enum):
                # QComboBox.currentData() returns the Enum member directly
                coerced[name] = value
            else:
                coerced[name] = value
        except Exception:
            errors.append(
                f"Parameter '{name}': failed to cast {value!r} to {ann}\n"
                + traceback.format_exc()
            )
            coerced[name] = value

    return coerced, errors


# ── Internal helpers ──────────────────────────────────────────────────────────

def _unwrap_optional(ann) -> Any:
    """Reduce ``Optional[X]`` / ``X | None`` to ``X``.

    Args:
        ann: Any annotation.

    Returns:
        The single non-None member of a two-member union, or the annotation
        unchanged. A union with two or more real types is left alone and will
        therefore fall through to the text field.
    """
    import types as _types
    origin = get_origin(ann)
    args = get_args(ann)
    if origin is _types.UnionType or str(origin) == "typing.Union":
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return ann


def _build_for_type(ann, default, parent) -> QWidget:
    """Pick and construct the widget for one resolved annotation.

    Args:
        ann: The annotation, already unwrapped of Optional.
        default: The parameter's default, or ``inspect.Parameter.empty``.
        parent: Qt parent for the new widget.

    Returns:
        The widget for this type, pre-filled with the default when there is one.
        Falls back to a QLineEdit for every type not listed below -- including
        every ``str`` subclass, which is why the marker types in
        :mod:`decoui.types` do not select widgets.
    """
    import json

    # pathlib.Path → _PathWidget
    if ann is pathlib.Path:
        w = _PathWidget(parent)
        if default is not inspect.Parameter.empty and default is not None:
            w.setText(str(default))
        return w

    # dict → _DictTextEdit
    if ann is dict or get_origin(ann) is dict:
        w = _DictTextEdit(parent)
        w.setMinimumHeight(80)
        w.setMaximumHeight(200)
        w.setPlaceholderText(t("field.dict_placeholder"))
        if default is not inspect.Parameter.empty and isinstance(default, dict):
            w.setPlainText(json.dumps(default, ensure_ascii=False, indent=2))
        return w

    # bool → QCheckBox  (before int: bool is subclass of int)
    if ann is bool:
        w = QCheckBox(parent)
        if default is not inspect.Parameter.empty:
            w.setChecked(bool(default))
        return w

    # int → QSpinBox
    if ann is int:
        w = QSpinBox(parent)
        w.setRange(-(2 ** 31), 2 ** 31 - 1)
        if default is not inspect.Parameter.empty:
            w.setValue(int(default))
        return w

    # float → QDoubleSpinBox
    if ann is float:
        w = QDoubleSpinBox(parent)
        w.setRange(-1e15, 1e15)
        w.setSingleStep(0.1)
        w.setDecimals(4)
        if default is not inspect.Parameter.empty:
            w.setValue(float(default))
        return w

    # Enum → QComboBox (dropdown)
    if isinstance(ann, type) and issubclass(ann, enum.Enum):
        w = QComboBox(parent)
        for member in ann:
            w.addItem(member.name, member)
        if default is not inspect.Parameter.empty and isinstance(default, ann):
            idx = w.findData(default)
            if idx >= 0:
                w.setCurrentIndex(idx)
        return w

    # list / list[X] → QTextEdit
    origin = get_origin(ann)
    if ann is list or origin is list:
        w = QTextEdit(parent)
        w.setMinimumHeight(80)
        w.setMaximumHeight(160)
        if default is not inspect.Parameter.empty and isinstance(default, list):
            w.setPlainText("\n".join(str(x) for x in default))
        return w

    # str / unknown → QLineEdit
    w = QLineEdit(parent)
    if default is not inspect.Parameter.empty and default is not None:
        w.setText(str(default))
    return w


def _parse_dict(raw: str) -> dict:
    """Parse raw text as dict.

    Tries in order:
      1. json.loads        — standard JSON, handles indentation/newlines
      2. ast.literal_eval  — Python dict literal with single quotes etc.
    Raises ValueError with a clear message if both fail.
    """
    if not raw:
        return {}

    import ast
    import json

    # 1. Standard JSON (handles indented / multiline input natively)
    json_err_msg = ""
    try:
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError(f"JSON parsed but got {type(result).__name__}, expected object")
        return result
    except json.JSONDecodeError as e:
        json_err_msg = str(e)

    # 2. Python dict literal (single quotes, trailing commas, etc.)
    try:
        result = ast.literal_eval(raw)
        if not isinstance(result, dict):
            raise ValueError(f"Literal parsed but got {type(result).__name__}, expected dict")
        return result
    except Exception as e:
        raise ValueError(
            f"Cannot parse as dict.\n"
            f"JSON error: {json_err_msg}\n"
            f"Literal error: {e}"
        ) from e
    return result


def _apply_placeholder(widget: QWidget, text: str) -> None:
    """Set placeholder text on the widgets that can show it.

    Args:
        widget: Any widget built here.
        text: The placeholder to show while the field is empty.

    Note:
        Silently does nothing for check boxes, spin boxes and combo boxes, which
        have nowhere to put it -- a placeholder declared for such a parameter is
        accepted by validation and then ignored.
    """
    if isinstance(widget, (_PathWidget, QLineEdit, QTextEdit)):
        widget.setPlaceholderText(text)
