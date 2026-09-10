Prints three lines in each language decoui's own interface ships in, so that a
theme's font stack can be judged against every script at once rather than one
script at a time.

The output goes to the console, which draws in the theme's `mono_family`. That
is the stack most likely to have a hole in it: a code face often ships Latin
and nothing else, and the gap only shows when something asks it for a
character it has not got.

## What each line is for

| Line | Carries | Look for |
|------|---------|----------|
| 1 | Prose in the language's own script | Whether every character has a glyph at all |
| 2 | Digits, box drawing, half- and full-width forms | Whether the columns line up |
| 3 | Punctuation and diacritics | A run that is visibly a different face |

The `[xx-XX]` tag in front of each block is deliberately ASCII. It is the fixed
point the eye measures the rest of the line against.

## Reading the result

A run of characters in a different face is the stack falling through, which is
not a fault by itself -- falling through is what a stack is for. It is a fault
when it looks like one:

* letters of two different weights inside one word
* a baseline that shifts mid-line
* digits wider in one language's block than in another's

Any of those means the face that caught those characters does not belong beside
the one in front of it. Put a face that covers both earlier in the stack.

> This tool judges `mono_family`. To judge the interface face instead, change
> language in Settings and read the sidebar and the buttons.

Set the stack in Settings, or in a theme file:

```json
"font": {
  "family": ["Tahoma", "BIZ UDPGothic", "Noto Sans JP", "sans-serif"],
  "mono_family": ["Cascadia Mono", "M PLUS 1 Code", "monospace"]
}
```

See [[guide.themes]] for what else a theme file carries.
