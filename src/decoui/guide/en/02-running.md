# Running a Tool

A tool's form is built from the parameters its function declares, so the fields
are whatever that particular tool needs.

* A field marked with a red asterisk is required and has no default.
* ``Parameters`` collapses the form once it is filled in, to give the output
  more room.
* ``Run`` starts the tool. While it runs, ``Run`` is replaced by ``Stop``.
* ``Reset`` puts every field back to its declared default.

Some tools ask for confirmation before they start; that is declared by the tool,
not something the application decides.

``Stop`` interrupts a running tool. A tool that is only computing or sleeping
stops promptly. One that is waiting on an external program stops only if its
author wired up cleanup for that case -- otherwise the page returns to idle
while the external program keeps going.

The progress bar sweeps back and forth when a tool has not said how much work
there is, and shows a real percentage when it has.
