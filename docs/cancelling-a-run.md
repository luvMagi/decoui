# Cancelling a run

Stop is the hardest promise decoui makes, because Python cannot keep it on its
own. This is what actually happens when the button is pressed, and what a tool
has to do to be stoppable.

## The mechanism

Pressing Stop calls `ExecutionEngine.cancel()` on the GUI thread, which does two
things in this order:

1. runs the tool's `@tool(on_cancel=...)` hook, if it declared one;
2. calls `ToolWorker.cancel()`, which kills any child processes registered by
   `run_process` and then injects `_WorkerCancelled` into the worker thread via
   `PyThreadState_SetAsyncExc`.

CPython raises that injected exception **at the next bytecode boundary**. A
thread parked inside a C call does not reach one. `proc.wait()`,
`socket.recv()`, a long `time.sleep()` — the exception stays pending until the
call returns by itself, and the tool's `finally` does not run either.

That is the whole difficulty: *whatever is holding the thread has to be released
from outside*. Everything below follows from it.

## Shelling out

Use `run_process`. It is the supported way and it is shorter than the
alternatives:

```python
from decoui import run_process, tool, toolset

@toolset(label="Ops")
class Ops:
    @tool(label="Dump")
    def dump(self, database: str = "app") -> str:
        result = run_process(["pg_dump", "-d", database, "-f", "dump.sql"])
        if result.cancelled:
            return "Stopped."
        return f"pg_dump exited {result.returncode}."
```

No handle to keep, no `on_cancel` to declare. `run_process` registers the child
with the running worker, so Stop kills it — and everything it spawned. It also
streams the child's output into the page console line by line, which plain
`subprocess` cannot: decoui replaces `sys.stdout` with an object that has no
`fileno()`, so a child left to inherit stdout writes past the console rather
than into it.

`result.cancelled` distinguishes "decoui killed it" from "the program failed".
With `check=True` a failing program raises `ProcessError`; a *cancelled* one
never does, because the non-zero status is decoui's doing and turning every Stop
into an error would be the opposite of what the user asked for.

`shell=True` is refused. A shell is an extra process between decoui and the
program, it is what makes quoting a security question, and it is what leaves a
grandchild holding the connection open after the shell is killed.

### What the alternatives actually do

Measured, not assumed — every row is a test in
`tests/test_stop_external_process.py`, driving the real engine against a real
child process.

| How the tool calls it | Stop works? |
|---|---|
| `run_process(...)` | **yes**, including the process tree |
| `Popen` + `wait()` + `on_cancel` that terminates | yes |
| `Popen` + `communicate()` + `on_cancel` that terminates | yes |
| `subprocess.run(...)`, no hook | **no** |
| `subprocess.run(...)`, *with* a hook | **no** — the hook has no handle |
| `Popen` + `on_cancel`, child spawns a grandchild | child dies, **grandchild survives** |
| child ignores SIGTERM | no on POSIX; yes on Windows, where `terminate()` is `TerminateProcess` |

`subprocess.run()` is what everyone writes first, and it keeps its handle to
itself — so there is nothing for a hook to terminate even when one is declared.
That is the shape a real incident had.

## Blocking on something that is not a process

For anything else that parks the thread in a C call — a socket read, a database
driver, a lock — the rule is the same and `run_process` cannot help. Declare a
hook and release the thing from it:

```python
@tool(label="Query", on_cancel="stop")
def query(self) -> None:
    self.conn = driver.connect(...)
    self.conn.execute(long_query)

def stop(self) -> None:
    conn = getattr(self, "conn", None)
    if conn is not None:
        conn.cancel()          # whatever this driver's escape hatch is
```

Three properties the hook must have:

* **It runs on the GUI thread**, while the worker is still blocked. Do not make
  it slow, and do not make it wait for the worker.
* **It must be idempotent.** A Stop that arrives before the tool has assigned
  the state the hook reads does nothing, and a second Stop is the user's only
  way out of that. Hence `getattr(self, "conn", None)`, not `self.conn`.
* **It must not raise to be useful.** One that does is caught, logged into the
  run's own console, and cancellation continues — but the thing it was supposed
  to release stays held.

`timeout=` goes through the same path, so an overrunning run is cleaned up
exactly as a pressed Stop is.

## What a stopped run leaves behind

* Status `cancelled` in the history, never `success`. A tool that returns
  normally after Stop was pressed is still recorded as cancelled: the user asked
  for it to stop, and a partial result must not look like a whole one.
* The return value is dropped.
* Console lines already emitted are kept.
* A run that cannot be stopped holds one thread of
  `QThreadPool.globalInstance()` for as long as it lasts. The pool has more than
  one, so a wedged tool costs its own tab and not the application — but the
  budget is finite, and enough of them would exhaust it.
