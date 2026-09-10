# Writing help

> [Project README](../README.md) · [Complete reference](reference.md)

A decoui application's Help window is built from three sources, all written in
one markup dialect:

| Source | Where it comes from | What it becomes |
|--------|--------------------|-----------------|
| Tool docstring | `@tool`-decorated method | Summary, prose, parameter table, Returns, Raises |
| Toolset docstring | `@toolset`-decorated class | The group's page |
| Markdown file | `@tool(help="...")` | Replaces the tool's **prose** only |

decoui's own pages under `src/decoui/guide/<language>/` use the same dialect.

## The dialect

It is Markdown, with two departures that exist because the source is sometimes a
Python docstring rather than a file.

**Double-backtick literals are accepted.** ` ``None`` ` and `` `None` `` both
render as code. Double is what reST uses, and reST is what a Python docstring is
conventionally written in — a project whose docstrings already say ` ``None`` `
should not have to choose between its API docs and its help pages.

**Indented code blocks are not recognised.** A docstring's indentation is an
artefact of where it sits in the file, and a four-space block in the source is
far more likely to be a wrapped sentence than a code sample. Fence code instead:

````
```python
print("hi")
```
````

Everything else is ordinary Markdown: `**bold**`, `*emphasis*`, `~~strikethrough~~`,
ATX headings, ordered and unordered lists (nested by indentation), pipe tables
with `:---:` alignment, blockquotes, and `---` thematic breaks.

Headings shift down one level on the way out: `#` renders as `<h2>`, because
`<h1>` is the page title and decoui writes that, not the author.

Sphinx role prefixes are stripped, so `` :meth:`stop_child` `` reads as
`stop_child` rather than leaking syntax.

## Two kinds of link

This is the part that differs from Markdown, and it is deliberate.

**`[[key]]` is a cross-reference** to another decoui help page. The key is
`guide.themes`, `MyTools`, or `MyTools.encode` — never a file name or a title,
because a key does not change when a page is translated. Use `[[key|label]]` to
give it different text.

A reference to a page that does not exist in this session renders as its own
text with no link on it. Which tools exist is up to the application that loaded
them, so help cannot be written against a fixed set, and a dead link is worse
than plain prose.

**`[text](url)` is an ordinary link** and opens in the reader's browser. Only
`http`, `https` and `mailto` are followed; anything else renders as text with
the target shown in parentheses, so a mistake stays visible to whoever can fix
it. `file:` is excluded on purpose — help text is written by whoever wrote the
application, so this is not a trust boundary, but it is a blast radius.

Keeping cross-references out of `[text](target)` is what lets that form mean
what it means everywhere else.

## Help in a file

When a tool's help outgrows its docstring, or wants translating, point at a
Markdown file:

```python
@tool(label="Deploy", help="doc/deploy.md")
def deploy(self, service: str = "web") -> str:
    """Deploy one service.

    Args:
        service: Which service to ship.

    Returns:
        A confirmation.
    """
```

The path is relative to the directory of the module the **toolset class** is
defined in, and decoui inserts a language directory into it:

```
<module_dir>/doc/<language>/deploy.md
<module_dir>/doc/<DEFAULT_LANGUAGE>/deploy.md
<module_dir>/doc/deploy.md
```

The first match wins. The third is for an application that has help but only one
language, which should not have to make an `en` directory to say so.

The directory is yours to name rather than fixed at `help/`, because a fixed
name is one an application may already have taken — decoui itself could not use
that convention, having a `decoui.help` module sitting exactly where the
directory would go.

Paths are confined to the module's directory. A name that climbs out with `..`,
or that is absolute, resolves to nothing.

### What the file replaces

**Only the prose.** These still come from the docstring:

* the **summary** — it is also the tool's one-line entry in the contents table
* the **parameter table** — built from the signature, described by `Args:`
* **Returns** and **Raises**

A file sitting beside the module cannot be checked against the code, and help
that silently disagrees with the form on screen is worse than help that is
merely brief.

A missing or unreadable file falls back to the docstring's prose. Help is
presentation, and no application should fail to start over it.

## Why decoui renders this itself

Qt can parse Markdown — `QTextDocument.setMarkdown()` — and better than decoui
does. It is not used, for two reasons.

It renders to a document whose fonts, code face and table borders are fixed. The
help window's whole appearance comes from the theme, and a page that ignored the
theme would be a worse trade than a smaller dialect.

And a whole-document parser takes the whole document. A tool's page interleaves
decoui's own generated structure — a title, a parameter table — with the
author's prose, which means the renderer has to emit fragments that compose.

The dialect lives in `src/decoui/markup.py`.
