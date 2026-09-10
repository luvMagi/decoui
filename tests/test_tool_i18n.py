"""Tests for translating an application's own tool text."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from decoui import tool, toolset
from decoui.help import build_help
from decoui.registry import build_tree
from decoui.tool_i18n import load_catalogue


@toolset(label="Deploy Tools", tags=["ops"], description="English description.")
class _Deploy:
    """English toolset summary.

    English toolset prose.
    """

    @tool(
        label="Restore",
        description="English tool description.",
        placeholders={"archive": "pick a file", "note": "optional"},
        labels={"archive": "Archive"},
    )
    def restore(self, archive: str = "", note: str = "") -> None:
        """English tool summary.

        Args:
            archive: Which archive.
            note: A note.
        """

    @tool(label="Untranslated", description="Left alone.")
    def untouched(self) -> None:
        """Also left alone."""


@pytest.fixture(autouse=True)
def _clear_catalogue() -> Iterator[None]:
    """Make sure a catalogue never outlives the test that loaded it.

    Yields:
        Nothing. The catalogue is module-global -- that is what lets
        ``build_tree`` reach it without being handed one -- so a test that left
        it loaded would translate every toolset the rest of the suite builds.
    """
    yield
    load_catalogue(None, "en")


def _catalogue(tmp_path: Path, payload: object, language: str = "ja-JP") -> Path:
    """Write a catalogue file and return the directory holding it.

    Args:
        tmp_path: pytest's per-test directory.
        payload: What to write, serialised as JSON.
        language: The file's language code.

    Returns:
        The directory to hand to :func:`load_catalogue`.
    """
    directory = tmp_path / "i18n"
    directory.mkdir(exist_ok=True)
    (directory / f"{language}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    return directory


def _tool_of(tree: list, name: str):
    """Look one tool up by method name.

    Args:
        tree: The built tree.
        name: The method's attribute name.

    Returns:
        Its ToolInfo.
    """
    return next(t for ts in tree for t in ts.tools if t.method_name == name)


# ── Applying a catalogue ──────────────────────────────────────────────────────

def test_labels_and_descriptions_are_replaced(tmp_path: Path) -> None:
    """Verify the catalogue reaches the toolset and its tools."""
    directory = _catalogue(tmp_path, {
        "_Deploy": {"label": "デプロイ", "description": "日本語の説明。"},
        "_Deploy.restore": {"label": "復元", "description": "日本語のツール説明。"},
    })

    assert load_catalogue(directory, "ja-JP") == []
    tree = build_tree(_Deploy)

    assert tree[0].label == "デプロイ"
    assert tree[0].description == "日本語の説明。"
    assert _tool_of(tree, "restore").label == "復元"
    assert _tool_of(tree, "restore").description == "日本語のツール説明。"


def test_an_absent_key_keeps_what_the_source_wrote(tmp_path: Path) -> None:
    """Verify a half-finished catalogue yields a half-translated interface.

    This is the guarantee that makes the feature usable before it is finished:
    a translator adding one tool at a time never breaks the others.
    """
    directory = _catalogue(tmp_path, {"_Deploy.restore": {"label": "復元"}})
    load_catalogue(directory, "ja-JP")

    tree = build_tree(_Deploy)

    assert _tool_of(tree, "restore").label == "復元"
    assert _tool_of(tree, "restore").description == "English tool description."
    assert _tool_of(tree, "untouched").label == "Untranslated"
    assert tree[0].label == "Deploy Tools"


def test_parameter_text_is_merged_not_replaced(tmp_path: Path) -> None:
    """Verify translating one field does not drop the text on the others."""
    directory = _catalogue(tmp_path, {
        "_Deploy.restore": {"params": {"archive": {"label": "アーカイブ"}}}
    })
    load_catalogue(directory, "ja-JP")

    params = {p.name: p for p in _tool_of(build_tree(_Deploy), "restore").params}

    assert params["archive"].label == "アーカイブ"
    # Not named in the catalogue, so the declaration's text survives.
    assert params["archive"].placeholder == "pick a file"
    assert params["note"].placeholder == "optional"


def test_the_help_summary_prefers_the_catalogue(tmp_path: Path) -> None:
    """Verify a translated tool is not English again on its Help page.

    The summary is otherwise the docstring's first line, which the catalogue
    cannot reach. Without this the sidebar reads as translated and Help does
    not, which is worse than either on its own.
    """
    directory = _catalogue(tmp_path, {
        "_Deploy": {"brief": "日本語のツールセット要約。"},
        "_Deploy.restore": {"brief": "日本語のツール要約。"},
    })
    load_catalogue(directory, "ja-JP")

    group = build_help(build_tree(_Deploy))[0]

    assert group.summary == "日本語のツールセット要約。"
    assert next(t for t in group.tools if t.label == "Restore").summary == (
        "日本語のツール要約。"
    )


def test_without_a_catalogue_the_summary_is_still_the_docstring(
    tmp_path: Path
) -> None:
    """Verify the new priority did not displace the existing behaviour."""
    load_catalogue(None, "en")

    group = build_help(build_tree(_Deploy))[0]

    assert group.summary == "English toolset summary."
    assert next(t for t in group.tools if t.label == "Restore").summary == (
        "English tool summary."
    )


def test_every_docstring_derived_field_can_be_translated(tmp_path: Path) -> None:
    """Verify the whole Help page can be translated, not only its title.

    A docstring is one piece of text in one language, and it is also the API
    documentation the developer reads. Everything it contributes to the Help
    page therefore has to be replaceable from the catalogue.
    """
    directory = _catalogue(tmp_path, {
        "_Deploy.restore": {
            "brief": "アーカイブから復元します。",
            "returns": "復元されたもの。",
            "raises": "OSError: アーカイブが読めないとき。",
            "params": {"archive": {"brief": "どのアーカイブか。"}},
        }
    })
    load_catalogue(directory, "ja-JP")

    entry = next(
        t for t in build_help(build_tree(_Deploy))[0].tools if t.label == "Restore"
    )
    archive = next(p for p in entry.params if p.name == "archive")

    assert entry.summary == "アーカイブから復元します。"
    assert entry.returns == "復元されたもの。"
    assert entry.raises == "OSError: アーカイブが読めないとき。"
    assert archive.text == "どのアーカイブか。"
    # Not translated, so the docstring's own Args: entry survives.
    assert next(p for p in entry.params if p.name == "note").text == "A note."


# ── Not being there, and being wrong ──────────────────────────────────────────

def test_no_directory_is_not_an_error() -> None:
    """Verify an application that names nothing is simply untranslated."""
    assert load_catalogue(None, "ja-JP") == []

    assert build_tree(_Deploy)[0].label == "Deploy Tools"


def test_a_missing_language_file_is_not_an_error(tmp_path: Path) -> None:
    """Verify naming a directory before translating anything still starts.

    An application ships the directory from the first commit and fills it in
    later; a language nobody has translated yet must not be a startup failure.
    """
    directory = _catalogue(tmp_path, {"_Deploy": {"label": "デプロイ"}})

    assert load_catalogue(directory, "de-DE") == []
    assert build_tree(_Deploy)[0].label == "Deploy Tools"


def test_unreadable_json_is_reported_rather_than_raised(tmp_path: Path) -> None:
    """Verify a malformed catalogue costs the translation, not the launch."""
    directory = tmp_path / "i18n"
    directory.mkdir()
    (directory / "ja-JP.json").write_text("{ not json", encoding="utf-8")

    problems = load_catalogue(directory, "ja-JP")

    assert len(problems) == 1
    assert "ja-JP.json" in problems[0]
    assert build_tree(_Deploy)[0].label == "Deploy Tools"


def test_a_malformed_entry_is_skipped_and_the_rest_still_applies(
    tmp_path: Path
) -> None:
    """Verify one bad entry does not cost the whole file."""
    directory = _catalogue(tmp_path, {
        "_Deploy": "this should have been an object",
        "_Deploy.restore": {"label": "復元"},
    })

    problems = load_catalogue(directory, "ja-JP")
    tree = build_tree(_Deploy)

    assert len(problems) == 1
    assert "_Deploy" in problems[0]
    assert tree[0].label == "Deploy Tools"
    assert _tool_of(tree, "restore").label == "復元"


def test_a_non_string_label_is_ignored(tmp_path: Path) -> None:
    """Verify a typo in the catalogue cannot put a number in the sidebar."""
    directory = _catalogue(tmp_path, {"_Deploy": {"label": 42}})
    load_catalogue(directory, "ja-JP")

    assert build_tree(_Deploy)[0].label == "Deploy Tools"


# ── The example's own catalogue ───────────────────────────────────────────────

def test_the_example_catalogue_names_only_tools_that_exist() -> None:
    """Verify the shipped Japanese catalogue has not drifted from the code.

    A key that matches nothing is silently ignored at runtime, which is exactly
    how a catalogue rots after a rename.
    """
    from decoui.example import I18N_DIR, TOOLSETS

    load_catalogue(None, "en")
    tree = build_tree(*TOOLSETS)
    known = {ts.cls.__name__ for ts in tree} | {
        t.tool_id for ts in tree for t in ts.tools
    }

    catalogue = json.loads(
        (I18N_DIR / "ja-JP.json").read_text(encoding="utf-8")
    )
    unknown = sorted(set(catalogue) - known)

    assert not unknown, f"catalogue names things that no longer exist: {unknown}"


def test_the_example_catalogue_names_only_parameters_that_exist() -> None:
    """Verify no catalogue entry describes a field that was renamed away."""
    from decoui.example import I18N_DIR, TOOLSETS

    load_catalogue(None, "en")
    tree = build_tree(*TOOLSETS)
    params = {
        t.tool_id: {p.name for p in t.params} for ts in tree for t in ts.tools
    }

    catalogue = json.loads(
        (I18N_DIR / "ja-JP.json").read_text(encoding="utf-8")
    )
    stale = [
        f"{key}.{name}"
        for key, entry in catalogue.items()
        for name in entry.get("params", {})
        if name not in params.get(key, set())
    ]

    assert not stale, f"catalogue describes fields that do not exist: {stale}"
