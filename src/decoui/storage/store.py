"""A small persistent key/value store for the applications built on decoui.

A tool often has one thing worth remembering between runs -- the environment
last deployed to, the folder last exported into, whether the user wanted the
verbose flag on. That is too little to justify a file of its own and too
important to lose, and decoui already keeps a database open for exactly this
shape of data.

::

    from decoui import store

    prefs = store("deploy")
    prefs["last_env"] = "staging"      # written if absent, replaced if not
    prefs.get("last_env", "dev")

**What this is not.** It is a settings store, not an application database:
small values, addressed one at a time, with no queries and no relations. A tool
with real data of its own should open its own file. Kept to that, this stays
two SQL statements; let it grow and it becomes a worse ORM than the one you
would have chosen deliberately.

Three decisions worth knowing about:

* **The namespace is the caller's to choose**, not derived from the class. Some
  settings belong to one toolset and some are shared by all of them, and a
  namespace taken from the class name can only ever express the first.
* **The namespace lives in the key**, as ``namespace.key``, rather than in a
  column of its own. ``app_setting`` is shared with existing installations and
  ``init_db()`` has no migration step -- a new column would simply not appear
  in any database that already exists, and the first query naming it would
  fail on startup. A prefix needs no schema change at all, and since ``key`` is
  the table's primary key, listing a namespace is still an index range scan.
* **Values are stored as JSON**, so the column keeps its own type information
  and a ``type`` column would be redundant as well.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterator

from .db import delete_setting, get_setting, set_setting, settings_with_prefix

#: A namespace name. No dots, because the dot is what separates the namespace
#: from the key: with them allowed, namespace ``a`` key ``b.c`` and namespace
#: ``a.b`` key ``c`` would both land on the row ``a.b.c``.
_NAMESPACE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")

#: Namespaces decoui keeps for itself. ``ui`` already holds the chosen theme,
#: the interface language and the sidebar width; an application writing there
#: would be changing the user's settings rather than its own. Refused outright
#: rather than left to discipline -- the whole point of a namespace is that it
#: is enforced somewhere.
_RESERVED = frozenset({"ui", "decoui"})


class Store:
    """One namespace of the application settings table.

    Behaves as a mapping. Every read and every write goes to the database
    immediately -- there is no caching, so two toolsets sharing a namespace see
    each other's writes, and a value survives whatever happens to the process
    next.

    Safe to use from a tool body: every database call opens and closes its own
    connection, so it works from the worker thread a tool runs on as well as
    from the GUI thread.

    Attributes:
        namespace: The prefix every key in this store is written under.
    """

    def __init__(self, namespace: str) -> None:
        """Bind a store to one namespace.

        Args:
            namespace: Letters, digits, ``_`` and ``-``, starting with a letter
                or underscore. No dots.

        Raises:
            ValueError: If the name is malformed, or is one decoui reserves.
        """
        if not isinstance(namespace, str) or not _NAMESPACE_RE.match(namespace):
            raise ValueError(
                f"namespace must be letters, digits, '_' or '-' and contain no "
                f"'.', got {namespace!r}"
            )
        if namespace.casefold() in _RESERVED:
            raise ValueError(
                f"{namespace!r} is reserved for decoui's own settings; "
                f"choose a name of your own"
            )
        self.namespace = namespace

    def _row_key(self, key: str) -> str:
        """Return the database key one of this store's keys is written under.

        Args:
            key: The caller's key. May contain dots; only the namespace may not.

        Returns:
            ``namespace.key``.

        Raises:
            ValueError: If the key is empty.
        """
        if not isinstance(key, str) or not key:
            raise ValueError(f"key must be a non-empty string, got {key!r}")
        return f"{self.namespace}.{key}"

    def get(self, key: str, default: Any = None) -> Any:
        """Return a stored value, or a default when there is none.

        Args:
            key: The key to read.
            default: Returned when the key has never been written. Returned as
                given -- it is not stored, and not JSON round-tripped.

        Returns:
            The value that was stored, decoded from JSON.
        """
        raw = get_setting(self._row_key(key))
        if raw is None:
            return default
        return _decode(raw)

    def set(self, key: str, value: Any) -> None:
        """Write a value, replacing whatever was there.

        The same call whether or not the key exists: absent it is inserted,
        present it is updated. There is nothing to register first.

        Args:
            key: The key to write.
            value: Anything JSON can carry -- ``str``, ``int``, ``float``,
                ``bool``, ``None``, and lists and dicts of those.

        Raises:
            TypeError: If the value cannot be encoded. Not degraded to a string:
                silently storing ``"<MyObject object at 0x...>"`` would fail
                later, somewhere else, with nothing pointing back to here.
        """
        set_setting(self._row_key(key), _encode(value, key))

    def delete(self, key: str) -> None:
        """Remove a key.

        Args:
            key: The key to drop. Removing one that was never written is not an
                error.
        """
        delete_setting(self._row_key(key))

    def keys(self) -> list[str]:
        """Return this namespace's keys, without the namespace on them.

        Returns:
            Sorted keys. Without this a key written by mistake -- a typo, a
            scheme since abandoned -- would sit in the database with no way to
            find it short of opening the file.
        """
        prefix = f"{self.namespace}."
        return [key[len(prefix):] for key, _ in settings_with_prefix(prefix)]

    def items(self) -> list[tuple[str, Any]]:
        """Return every key and value in this namespace.

        Returns:
            Sorted ``(key, value)`` pairs, values decoded. One query, rather
            than one per key.
        """
        prefix = f"{self.namespace}."
        return [
            (key[len(prefix):], _decode(raw))
            for key, raw in settings_with_prefix(prefix)
        ]

    def __getitem__(self, key: str) -> Any:
        """Return a stored value.

        Args:
            key: The key to read.

        Returns:
            The stored value.

        Raises:
            KeyError: If the key has never been written. Use :meth:`get` for a
                default instead.
        """
        raw = get_setting(self._row_key(key))
        if raw is None:
            raise KeyError(key)
        return _decode(raw)

    def __setitem__(self, key: str, value: Any) -> None:
        """Write a value. See :meth:`set`.

        Args:
            key: The key to write.
            value: Anything JSON can carry.
        """
        self.set(key, value)

    def __delitem__(self, key: str) -> None:
        """Remove a key. See :meth:`delete`.

        Args:
            key: The key to drop.
        """
        self.delete(key)

    def __contains__(self, key: str) -> bool:
        """Report whether a key has a stored value.

        Args:
            key: The key to look for.

        Returns:
            True when it has been written and not deleted.
        """
        return get_setting(self._row_key(key)) is not None

    def __iter__(self) -> Iterator[str]:
        """Iterate this namespace's keys.

        Returns:
            An iterator over :meth:`keys`.
        """
        return iter(self.keys())

    def __len__(self) -> int:
        """Return how many keys this namespace holds.

        Returns:
            The key count.
        """
        return len(self.keys())

    def __repr__(self) -> str:
        """Return a debugging representation naming the namespace.

        Returns:
            ``Store('deploy')``.
        """
        return f"Store({self.namespace!r})"


def store(namespace: str = "app") -> Store:
    """Return the store for one namespace.

    Args:
        namespace: Which namespace to address. Two calls with the same name
            reach the same rows, from anywhere in the application -- that is
            how a setting shared by every tool is shared. Defaults to ``app``,
            for the common case of an application that only needs one.

    Returns:
        A store bound to that namespace. Cheap to build; there is no connection
        to keep, so there is no reason to hold on to one beyond convenience.

    Raises:
        ValueError: If the name is malformed or reserved.
    """
    return Store(namespace)


def _encode(value: Any, key: str) -> str:
    """Serialise one value for storage.

    Args:
        value: The value to store.
        key: The key it is being written under, for the error message.

    Returns:
        Its JSON form.

    Raises:
        TypeError: If JSON cannot carry it.
    """
    try:
        return json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"cannot store {type(value).__name__} under {key!r}: the settings "
            f"store holds JSON -- str, int, float, bool, None, list, dict"
        ) from exc


def _decode(raw: str) -> Any:
    """Read one stored value back.

    Args:
        raw: The text held in the ``value`` column.

    Returns:
        The decoded value, or the raw text when it is not JSON at all. That
        fallback is for rows written before this module existed: decoui's own
        settings, and any application that reached for ``set_setting``
        directly, store plain strings -- ``light``, not ``"light"``. Raising on
        those would turn a readable value into a crash.
    """
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw
