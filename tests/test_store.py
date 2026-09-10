"""Tests for the application settings store.

What is guarded here is mostly isolation and durability: that one namespace
cannot read or overwrite another's rows, that decoui's own settings are out of
reach, and that a value comes back as the type it went in as. The upsert
itself is one SQL statement and is not the interesting part.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from decoui import Store, store
from decoui.storage.db import get_setting, init_db, set_db_path, set_setting


@pytest.fixture()
def db(tmp_path: Path) -> Iterator[Path]:
    """Point the store at a throwaway database.

    Yields:
        The database file, already created.
    """
    path = tmp_path / "history.db"
    set_db_path(path)
    init_db()
    yield path


# ── Naming ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["ui", "UI", "Ui", "decoui", "DECOUI"])
def test_decouis_own_namespaces_are_refused(db: Path, name: str) -> None:
    """Verify an application cannot write where decoui keeps its settings.

    ``ui`` already holds the chosen theme, the interface language and the
    sidebar width. Writing there would be changing the user's settings, not the
    application's, so it is refused rather than left to discipline.

    Args:
        db: The throwaway database.
        name: A reserved name, in whatever case it was written.
    """
    with pytest.raises(ValueError, match="reserved"):
        store(name)


@pytest.mark.parametrize("name", ["a.b", "", "9lives", "has space", "dots.everywhere"])
def test_a_namespace_may_not_contain_a_dot_or_start_with_a_digit(
    db: Path, name: str
) -> None:
    """Verify malformed namespaces are refused at construction.

    The dot is what separates the namespace from the key. Allowed inside a
    namespace, ``a`` + ``b.c`` and ``a.b`` + ``c`` would address the same row.

    Args:
        db: The throwaway database.
        name: A name that must not be accepted.
    """
    with pytest.raises(ValueError):
        store(name)


def test_the_default_namespace_is_app(db: Path) -> None:
    """Verify an application that needs only one namespace need not name it."""
    assert store().namespace == "app"


# ── Isolation ─────────────────────────────────────────────────────────────────

def test_namespaces_do_not_see_each_other(db: Path) -> None:
    """Verify the same key in two namespaces is two rows."""
    store("alpha")["shared_name"] = 1
    store("beta")["shared_name"] = 2

    assert store("alpha")["shared_name"] == 1
    assert store("beta")["shared_name"] == 2


def test_one_namespace_is_not_a_prefix_of_another(db: Path) -> None:
    """Verify ``app`` does not collect ``app2``'s keys.

    The namespace is a key prefix, so the separator has to be part of the
    match. Without the dot, every namespace would swallow every longer one.
    """
    store("app")["mine"] = "a"
    store("app2")["theirs"] = "b"

    assert store("app").keys() == ["mine"]
    assert store("app2").keys() == ["theirs"]


def test_an_underscore_in_a_namespace_is_not_a_wildcard(db: Path) -> None:
    """Verify listing a namespace escapes LIKE's own metacharacters.

    ``_`` matches any character in a LIKE pattern. Unescaped, namespace
    ``my_ns`` would list rows belonging to ``myXns``.
    """
    store("my_ns")["mine"] = 1
    set_setting("myXns.theirs", '"not mine"')

    assert store("my_ns").keys() == ["mine"]


def test_decouis_own_settings_are_untouched_by_a_store(db: Path) -> None:
    """Verify a store writes nowhere near the rows decoui reads at startup."""
    set_setting("ui.theme", "nasa")

    store("theme")["theme"] = "cockpit"

    assert get_setting("ui.theme") == "nasa"


# ── Values ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value", [
    "text", 42, 3.5, True, False, None, ["a", 1], {"k": [1, 2]},
])
def test_a_value_comes_back_as_the_type_it_went_in_as(db: Path, value: object) -> None:
    """Verify JSON carries the type, so no caller has to convert by hand.

    Args:
        db: The throwaway database.
        value: A value JSON can carry.
    """
    prefs = store("types")
    prefs["v"] = value

    assert prefs["v"] == value
    assert type(prefs["v"]) is type(value)


def test_a_stored_none_is_not_a_missing_key(db: Path) -> None:
    """Verify ``None`` is a value, not an absence.

    Otherwise a setting could never be set to "nothing" without being erased.
    """
    prefs = store("nulls")
    prefs["v"] = None

    assert "v" in prefs
    assert prefs.get("v", "default") is None
    assert "absent" not in prefs


def test_a_value_json_cannot_carry_is_refused(db: Path) -> None:
    """Verify an unstorable value raises where it was written.

    Coerced to ``str`` it would be stored as ``'<object object at 0x...>'`` and
    fail later, somewhere else, with nothing pointing back at this line.
    """
    with pytest.raises(TypeError, match="cannot store"):
        store("bad")["v"] = object()


def test_a_row_written_before_this_module_existed_still_reads(db: Path) -> None:
    """Verify a plain string left by ``set_setting`` does not raise.

    decoui's own settings, and any application that reached for ``set_setting``
    directly, hold bare text -- ``light``, not ``"light"``. Those rows are in
    databases that already exist.
    """
    set_setting("legacy.mode", "light")

    assert store("legacy").get("mode") == "light"


# ── Mapping behaviour ─────────────────────────────────────────────────────────

def test_writing_a_key_twice_replaces_it(db: Path) -> None:
    """Verify the upsert: absent it is inserted, present it is updated."""
    prefs = store("upsert")
    prefs["env"] = "staging"
    prefs["env"] = "prod"

    assert prefs["env"] == "prod"
    assert len(prefs) == 1


def test_a_missing_key_raises_on_subscript_but_not_on_get(db: Path) -> None:
    """Verify the two readers differ the way a mapping's do."""
    prefs = store("reads")

    assert prefs.get("nope", "fallback") == "fallback"
    with pytest.raises(KeyError):
        prefs["nope"]


def test_deleting_a_key_that_was_never_written_is_not_an_error(db: Path) -> None:
    """Verify delete states an outcome rather than a transition."""
    store("deletes").delete("never_there")


def test_keys_and_items_report_the_namespace_without_its_prefix(db: Path) -> None:
    """Verify a store hands back the keys the caller used.

    Without a listing, a key written by mistake could not be found again short
    of opening the database file.
    """
    prefs = store("listing")
    prefs["b"] = 2
    prefs["a"] = 1

    assert prefs.keys() == ["a", "b"]
    assert prefs.items() == [("a", 1), ("b", 2)]
    assert list(prefs) == ["a", "b"]


def test_two_handles_on_one_namespace_share_its_rows(db: Path) -> None:
    """Verify a namespace is shared state, which is what makes it shareable.

    This is the case an automatic per-class namespace could not express, and
    the reason the name is the caller's to choose.
    """
    store("shared")["k"] = "written here"

    assert store("shared")["k"] == "written here"
    assert isinstance(store("shared"), Store)
