"""Tests for the developer switch and the two translation-template dumps."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from decoui import F, tool, toolset
from decoui.help import dump_help_pages
from decoui.i18n import set_language
from decoui.registry import build_tree
from decoui.storage.db import init_db, set_db_path, set_setting
from decoui.tool_i18n import dump_template, load_catalogue
from decoui.ui.settings_dialog import (
    DEVELOPER_SETTING,
    SettingsDialog,
    developer_mode,
)

from typing import Annotated

Dump = Annotated[str, F(label="Dump file", placeholder="Pick a .dump")]


@toolset(label="Ops", tags=["ops"], description="Declared description.")
class _Ops:
    """Toolset summary.

    Toolset prose.
    """

    @tool(label="Restore", description="Declared tool description.",
          labels={"note": "Note"}, help="pages/restore.md")
    def restore(self, archive: Dump = "", note: str = "") -> str:
        """Tool summary line.

        Prose paragraph with a ``literal`` and a :meth:`role` in it.

        Args:
            archive: Which archive to read.
            note: Anything worth recording.

        Returns:
            What was restored.

        Raises:
            OSError: If the archive cannot be read.
        """
        return ""

    @tool(label="Bare")
    def bare(self) -> None:
        """Only a summary, no prose."""


@pytest.fixture()
def app_db(qt_app: QApplication, tmp_path: Path) -> Iterator[None]:
    """Give the dialog a database and English, and leave nothing behind.

    Yields:
        Nothing.
    """
    set_db_path(tmp_path / "history.db")
    init_db()
    set_language("en")
    yield
    load_catalogue(None, "en")


# ── The switch ────────────────────────────────────────────────────────────────

def test_the_dumps_are_absent_from_a_shipped_application(app_db: None) -> None:
    """Verify an end user never meets tools meant for whoever wrote the app.

    Developer mode is off unless the row says so, and there is no control for
    it in the dialog -- a switch labelled "developer options" among the theme
    and the language would be a switch shipped to the end user too.
    """
    dialog = SettingsDialog(tree=build_tree(_Ops))

    assert not developer_mode()
    assert dialog._dump_btn.isHidden()
    assert dialog._dump_help_btn.isHidden()
    assert not dialog.findChildren(type(dialog._dump_btn), "developerToggle")


def test_setting_the_row_by_hand_reveals_the_dumps(app_db: None) -> None:
    """Verify the documented way in works: set the row, reopen the dialog."""
    set_setting(DEVELOPER_SETTING, "1")

    dialog = SettingsDialog(tree=build_tree(_Ops))

    assert developer_mode()
    assert not dialog._dump_btn.isHidden()
    assert not dialog._dump_help_btn.isHidden()


@pytest.mark.parametrize("stored", ["0", "", "true", "yes", "1 "])
def test_only_an_exact_one_turns_it_on(app_db: None, stored: str) -> None:
    """Verify a switch this consequential is not tripped by a near miss."""
    set_setting(DEVELOPER_SETTING, stored)

    assert not developer_mode()
    assert SettingsDialog(tree=build_tree(_Ops))._dump_btn.isHidden()


def test_without_a_tree_there_is_nothing_to_dump(app_db: None) -> None:
    """Verify a dialog built with no toolsets offers the buttons disabled."""
    dialog = SettingsDialog()

    assert not dialog._dump_btn.isEnabled()
    assert not dialog._dump_help_btn.isEnabled()


# ── The catalogue template ────────────────────────────────────────────────────

def test_the_template_collects_every_source_of_text(app_db: None) -> None:
    """Verify the dump gathers what the code declares, from all three places.

    The decorators, the docstring, and ``F`` on the annotation each contribute,
    and a translator should not have to know which was which.
    """
    template = dump_template(build_tree(_Ops))

    assert template["_Ops"] == {
        "label": "Ops",
        "description": "Declared description.",
        "brief": "Toolset summary.",
        "prose": "Toolset prose.",
    }
    entry = template["_Ops.restore"]
    assert entry["label"] == "Restore"                       # @tool(label=)
    assert entry["description"] == "Declared tool description."
    assert entry["brief"] == "Tool summary line."            # docstring line 1
    assert entry["returns"] == "What was restored."          # Returns:
    assert entry["raises"] == "OSError: If the archive cannot be read."
    assert entry["params"]["archive"] == {
        "label": "Dump file",                                # F on the annotation
        "placeholder": "Pick a .dump",                       # F on the annotation
        "brief": "Which archive to read.",                   # Args:
    }
    assert entry["params"]["note"]["label"] == "Note"        # @tool(labels=)


def test_a_tool_with_a_help_file_gets_no_prose_in_the_template(
    app_db: None
) -> None:
    """Verify the template does not offer a second answer to one question.

    ``_Ops.restore`` declares ``help=``, so its prose is translated by
    translating that Markdown file. Putting the same text in the catalogue too
    would give a translator two places to write it and decoui one rule for
    which wins.
    """
    entry = dump_template(build_tree(_Ops))["_Ops.restore"]

    assert "prose" not in entry


def test_the_template_omits_what_is_not_there(app_db: None) -> None:
    """Verify a tool with nothing to say produces no empty keys.

    The template is a list of what there is to translate, and a blank line is
    not one of them.
    """
    entry = dump_template(build_tree(_Ops))["_Ops.bare"]

    assert entry == {"label": "Bare", "brief": "Only a summary, no prose."}


def test_the_template_is_the_source_even_while_a_translation_is_live(
    app_db: None, tmp_path: Path
) -> None:
    """Verify dumping under a translation does not write that translation back.

    ``build_tree`` applies whatever catalogue is loaded, so the dump has to
    suspend it -- otherwise the template looks finished and says nothing new.
    """
    directory = tmp_path / "i18n"
    directory.mkdir()
    (directory / "ja-JP.json").write_text(
        json.dumps({"_Ops": {"label": "運用"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    load_catalogue(directory, "ja-JP")
    tree = build_tree(_Ops)
    assert tree[0].label == "運用", "the translation should be live"

    assert dump_template(tree)["_Ops"]["label"] == "Ops"
    # ...and the live tree is untouched by the dump.
    assert build_tree(_Ops)[0].label == "運用"


def test_the_template_round_trips_as_a_catalogue(
    app_db: None, tmp_path: Path
) -> None:
    """Verify what comes out is something load_catalogue accepts back in."""
    directory = tmp_path / "i18n"
    directory.mkdir()
    (directory / "en.json").write_text(
        json.dumps(dump_template(build_tree(_Ops)), ensure_ascii=False),
        encoding="utf-8",
    )

    assert load_catalogue(directory, "en") == []
    assert build_tree(_Ops)[0].label == "Ops"


# ── The help pages ────────────────────────────────────────────────────────────

def test_help_pages_are_named_for_where_they_belong(app_db: None) -> None:
    """Verify a declared help= decides the file name, so the dump drops in."""
    pages = dump_help_pages(build_tree(_Ops))

    assert "restore.md" in pages, "help='pages/restore.md' should name the file"
    assert "_Ops.restore.md" not in pages


def test_a_tool_with_no_prose_gets_no_page(app_db: None) -> None:
    """Verify an empty file is not written for a one-line docstring."""
    pages = dump_help_pages(build_tree(_Ops))

    assert not any("bare" in name for name in pages)


def test_help_pages_come_out_as_plain_markdown(app_db: None) -> None:
    """Verify the docstring dialect is normalised on the way out.

    The file is opened in a translator's Markdown editor, where reST's double
    backticks are a code span containing a backtick and ``:meth:`` is syntax
    from a doc builder that editor has never heard of.
    """
    page = dump_help_pages(build_tree(_Ops))["restore.md"]

    assert "`literal`" in page
    assert "``literal``" not in page
    assert ":meth:" not in page
    assert "`role`" in page


def test_the_prose_is_the_docstring_not_the_help_file(
    app_db: None, tmp_path: Path
) -> None:
    """Verify a page already translated is not what gets dumped as a template.

    Dumping under a Japanese interface must not write the Japanese file back
    out, which is the one thing a template must not do.
    """
    page = dump_help_pages(build_tree(_Ops))["restore.md"]

    assert page.startswith("Prose paragraph")
