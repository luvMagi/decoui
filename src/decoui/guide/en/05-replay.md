# Replaying Parameters

Replay restores the arguments of an earlier run into the form. It does **not**
re-run anything -- nothing executes until you press ``Run`` yourself. That is
deliberate: it lets you replay a destructive run, change one field, and only
then decide to go ahead.

There are two ways in:

* From a tool page, ``Replay`` opens history already filtered to that tool, so
  you are choosing among that tool's own runs rather than everything.
* From history, select any row and press ``Replay Params``.

The stored snapshot is text, so a value is restored in its written form and
converted again when the tool next runs. A file path, for instance, comes back
as its string form rather than as a path object -- which the tool then re-reads
exactly as it would from anything you typed.
