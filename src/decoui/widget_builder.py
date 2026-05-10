"""Map native Python type annotations to PySide6 widgets.

Supported types:
  str            → QLineEdit
  int            → QSpinBox
  float          → QDoubleSpinBox
  bool           → QCheckBox
  list / list[X] → QTextEdit (comma- and newline-separated)
  dict           → QTextEdit (JSON / ast.literal_eval, raises on bad input)
  enum.Enum      → QComboBox (dropdown)
"""
from __future__ import annotations

import enum
import inspect
import re
from typing import Any, get_args, get_origin

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QLineEdit,
    QSpinBox,
    QTextEdit,
    QWidget,
)


# ── Marker subclass to distinguish dict QTextEdit from list QTextEdit ─────────

class _DictTextEdit(QTextEdit):
    pass


# ── Public API ────────────────────────────────────────────────────────────────

def build_widget(param_info, parent=None) -> QWidget:
    ann = param_info.annotation
    default = param_info.default if param_info.has_default else inspect.Parameter.empty
    placeholder = param_info.placeholder

    inner = _unwrap_optional(ann)
    w = _build_for_type(inner, default, parent)

    if placeholder:
        _apply_placeholder(w, placeholder)

    return w


def get_value(widget: QWidget) -> Any:
    if isinstance(widget, QCheckBox):
        return widget.isChecked()
    if isinstance(widget, QSpinBox):
        return widget.value()
    if isinstance(widget, QDoubleSpinBox):
        return widget.value()
    if isinstance(widget, QComboBox):
        return widget.currentData()
    if isinstance(widget, _DictTextEdit):
        return _parse_dict(widget.toPlainText().strip())
    if isinstance(widget, QTextEdit):
        raw = widget.toPlainText()
        items = [s.strip() for part in raw.splitlines() for s in re.split(r"[,，]", part)]
        return [x for x in items if x]
    if isinstance(widget, QLineEdit):
        return widget.text()
    return None


def set_value(widget: QWidget, value: Any) -> None:
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


def coerce_params(tool_info, raw: dict) -> tuple[dict, list[str]]:
    """Cast widget values to the types declared in the method signature."""
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
    import types as _types
    origin = get_origin(ann)
    args = get_args(ann)
    if origin is _types.UnionType or str(origin) == "typing.Union":
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return ann


def _build_for_type(ann, default, parent) -> QWidget:
    import json

    # dict → _DictTextEdit
    if ann is dict or get_origin(ann) is dict:
        w = _DictTextEdit(parent)
        w.setMinimumHeight(80)
        w.setMaximumHeight(200)
        w.setPlaceholderText('{"key": "value"}')
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
    if isinstance(widget, (QLineEdit, QTextEdit)):
        widget.setPlaceholderText(text)
