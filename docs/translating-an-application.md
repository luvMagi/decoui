# Translating an application

decoui translates **its own** interface — Run, Stop, the history columns — from
catalogues it ships. It cannot translate yours: the labels, descriptions and
field text you write into `@toolset` and `@tool` are strings it has never seen.
This is how you translate those.

## Why not in the decorator

The obvious thing to write is `@tool(label=t("my.key"))`, and it does not work.
A decorator's arguments are evaluated when the module is **imported**, and an
application imports its toolsets before it calls `gui_main()` — which is what
settles the language. The label would resolve against whatever language was
active at import, in practice always the default.

So the strings stay in your source in whatever language you wrote them, and
decoui replaces them later, in `build_tree()`. That runs after the language is
settled, and everything downstream is built from what it returns — the sidebar,
tab titles, form labels, the Help panel, the tool name on a history row. One
substitution reaches all of them.

## The catalogue

One JSON file per language, in a directory you name:

```python
gui_main(toolsets=[...], i18n_dir="i18n")
```

```
myapp/
  i18n/
    ja-JP.json
    zh-CN.json
```

Keys are the identity decoui already uses everywhere else: `ClassName` for a
toolset, `ClassName.method` for a tool — the same keys a help page writes a
cross-reference to.

```json
{
  "OpsTools": {
    "label": "運用",
    "description": "デプロイと復元。",
    "brief": "本番環境に対する操作。",
    "prose": "破壊的な操作には確認が入ります。"
  },
  "OpsTools.restore": {
    "label": "復元",
    "brief": "アーカイブから復元します。",
    "returns": "復元された内容。",
    "raises": "OSError: アーカイブが読めないとき。",
    "params": {
      "archive": {
        "label": "アーカイブ",
        "placeholder": ".dump を選択",
        "brief": "読み込むアーカイブ。"
      }
    }
  }
}
```

Every field is optional, at every level. **A key that is absent leaves the
string your source wrote**, so a half-finished catalogue gives you a
half-translated interface rather than a broken one — a translator can add one
tool at a time without breaking the others.

### Where each field lands

| Field | On screen | Written in your code as |
|---|---|---|
| `label` | sidebar, tab title, page heading | `@toolset(label=)` / `@tool(label=)` |
| `description` | the bordered box under a tool's title | `@tool(description=)` |
| `brief` | the Help page's subtitle, and the row in a contents table | the docstring's **first line** |
| `prose` | the paragraphs under it | the docstring's **body** |
| `returns` | the Help page's *Returns* section | `Returns:` |
| `raises` | the Help page's *Raises* section | `Raises:` |
| `params.<name>.label` | the form's field label | `@tool(labels=)`, or `F(label=)` on the annotation |
| `params.<name>.placeholder` | the field's hint text | `@tool(placeholders=)`, or `F(placeholder=)` |
| `params.<name>.brief` | the field's row in the Help parameter table | that parameter's `Args:` entry |

The first two are decorator arguments, and could in principle have been written
in every language at once. The rest come from the **docstring**, which cannot:
a docstring is one piece of text in one language, and it is also the API
documentation your developers read.

## Long-form help

Anything longer than a paragraph or two belongs in Markdown rather than a JSON
string literal:

```python
@tool(label="Restore", help="help/restore.md")
```

The path is relative to the module the toolset class is defined in, and decoui
inserts a language directory into it:

```
help/<language>/restore.md
help/en/restore.md
help/restore.md
```

The first match wins. **When a Markdown file resolves it wins over the
catalogue's `prose`** — it is the richer route, with headings, tables and code
samples. The catalogue's `prose` is for the common case of two sentences, which
would be more ceremony than text in a file of their own.

A **toolset** has no `help=`, so for a group page the catalogue is the only
route its prose has.

## Developer mode

decoui can write both starting points for you — a catalogue template holding
every translatable string your code declares, and a Markdown file per tool
holding its prose. Both live behind a hidden switch.

**There is deliberately no control for it in the Settings dialog.** Everything
else there is a choice decoui offers the people you ship to, and a checkbox
labelled "developer options" among them is a checkbox shipped to them too — one
that reveals, to an end user, a button that writes files into your source
layout.

Turning it on is a deliberate act by whoever builds the application:

1. **Launch the application once.** That creates the settings database — at
   `~/.decoui/history.db`, or wherever `gui_main(db_path=...)` points.
2. **Set the row** with any SQLite tool — a DB browser, your IDE's database
   view, or the shell:

   ```sql
   INSERT INTO app_setting (key, value, updated_at)
   VALUES ('decoui.developer', '1', datetime('now'))
   ON CONFLICT(key) DO UPDATE SET value = '1', updated_at = datetime('now');
   ```

   `updated_at` is `NOT NULL`, so it has to be given a value — a row inserted
   without one is rejected.

3. **Reopen Settings.** Two buttons are now at the bottom of the dialog.

Only the exact string `1` turns it on. Absent, `0`, `true`, a stray space —
all off. A switch with these consequences should not be tripped by a near miss.

### Dump default i18n JSON…

Writes a catalogue holding every translatable string your code declares, with
your own text as every value. Overwrite the values; delete what you do not want
translated.

It is read from your **declarations**, not from the running interface, so
dumping while a translation is loaded still produces the source text. A template
that wrote the existing translation back out would look finished and say nothing
new.

### Dump default help Markdown…

Writes each tool's docstring prose as a `.md` file, in the shape `help=` reads
back. A tool that declares `help="help/restore.md"` is written as `restore.md`,
so the dump drops straight into place; one that declares nothing is written as
`ClassName.method.md` and needs a `help=` added before decoui will read it.

Two things it does on purpose:

- **A file already in the folder is left alone**, and counted as skipped. The
  obvious place to dump is the folder you already keep help in, and a
  hand-written page there is worth more than the docstring paragraph this would
  replace it with.
- **The output is plain Markdown**, not the docstring dialect. reST's
  ``` ``literal`` ``` becomes `` `literal` `` and Sphinx role prefixes are
  stripped, because the file is opened in a translator's Markdown editor.

## Keeping a catalogue honest

A key that matches nothing is silently ignored, which is exactly how a catalogue
rots after a rename. Two lines of test catch it:

```python
def test_catalogue_names_only_things_that_exist():
    tree = build_tree(*TOOLSETS)
    known = {ts.cls.__name__ for ts in tree} | {
        t.tool_id for ts in tree for t in ts.tools
    }
    catalogue = json.loads(Path("i18n/ja-JP.json").read_text(encoding="utf-8"))

    assert not set(catalogue) - known
```

decoui's own example does this — see `tests/test_tool_i18n.py`.
