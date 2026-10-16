"""The one way LowDevOps starts a subprocess: Conftest/Checkov/Trivy, az and terraform.

- An argument list, never a shell; the binary is resolved to an absolute path on PATH.
- Its own process group, so a timeout kills the tool and everything it started.
- An explicit environment: callers say what to drop and what to add.
- Either captured output, or a line callback for streamed logs (stderr merged into stdout).
"""

import codecs
import os
import selectors
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from functools import partial
from pathlib import Path

# How long to wait for output still in the pipe after the tool exited.
READER_GRACE_SECONDS = 2


class ProcError(Exception):
    pass


class ProcTimeout(ProcError):
    pass


@dataclass(frozen=True)
class Completed:
    returncode: int
    stdout: str  # empty when streamed
    stderr: str  # empty when streamed (merged into the lines)


def inherited_env(
    drop_prefixes: Iterable[str] = (), extra: Mapping[str, str] | None = None
) -> dict[str, str]:
    prefixes = tuple(drop_prefixes)
    env = {k: v for k, v in os.environ.items() if not (prefixes and k.startswith(prefixes))}
    return {**env, **(extra or {})}


def run(
    args: list[str],
    *,
    cwd: Path,
    timeout: float,
    env: Mapping[str, str],
    on_line: Callable[[str], None] | None = None,
) -> Completed:
    """`env` is required: nothing reaches a child unless the caller passed it on purpose."""
    tool = args[0]
    binary = shutil.which(tool)
    if binary is None:
        raise ProcError(f"{tool} is not installed")
    process = subprocess.Popen(  # noqa: S603 - fixed argument list, no shell
        [binary, *args[1:]],
        cwd=cwd,
        env=dict(env),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if on_line else subprocess.PIPE,
        start_new_session=True,
    )
    # The child is reaped only at the very end (under `lock`), so until then its pid and
    # group id stay reserved: killpg can never hit a reused pid.
    lock = threading.Lock()
    reaped = False
    timed_out = threading.Event()

    def exited() -> bool:
        flags = os.WEXITED | os.WNOHANG | os.WNOWAIT  # look, don't reap
        return os.waitid(os.P_PID, process.pid, flags) is not None

    def kill_group(*, on_timeout: bool = False) -> None:
        with lock:
            if reaped:
                return
            if on_timeout and not exited():
                timed_out.set()  # only a tool that was still running timed out
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)

    # Output is read here, on the caller's thread, from non-blocking selects: no reader
    # threads to leak, and no callback can run after run() returns.
    names = {}
    for name, stream in (("out", process.stdout), ("err", process.stderr)):
        if stream is not None:
            names[stream.fileno()] = name
    decoders = {
        name: codecs.getincrementaldecoder("utf-8")(errors="replace") for name in names.values()
    }
    chunks: dict[str, list[str]] = {name: [] for name in names.values()}
    pending = ""
    selector = selectors.DefaultSelector()
    timer = threading.Timer(timeout, partial(kill_group, on_timeout=True))
    timer.daemon = True
    try:
        for fd in names:
            selector.register(fd, selectors.EVENT_READ)
        timer.start()
        grace_ends: float | None = None
        while selector.get_map():
            if grace_ends is None and exited():
                kill_group()  # whatever the tool left behind in its group
                grace_ends = time.monotonic() + READER_GRACE_SECONDS
            if grace_ends is not None and time.monotonic() > grace_ends:
                break  # a detached process still holds the pipe: stop listening to it
            for key, _ in selector.select(0.05):
                data = os.read(key.fd, 65536)
                name = names[key.fd]
                if not data:
                    selector.unregister(key.fd)
                text = decoders[name].decode(data, final=not data)
                if on_line is None:
                    chunks[name].append(text)
                    continue
                pending += text
                *lines, pending = pending.split("\n")
                for line in lines:
                    on_line(line.removesuffix("\r"))
        if on_line is not None and pending:
            on_line(pending.removesuffix("\r"))
        while not exited():  # the timer guarantees this ends
            time.sleep(0.02)
    finally:  # also on a callback error: leave no tool running
        timer.cancel()
        if timer.ident is not None:  # started: a timer already firing finishes first
            timer.join()
        kill_group()
        selector.close()
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()
        with lock:
            process.wait()
            reaped = True
    if timed_out.is_set():
        raise ProcTimeout(f"{os.path.basename(tool)} took longer than {timeout:g} s")

    def joined(name: str) -> str:
        return "".join(chunks.get(name, [])).replace("\r\n", "\n")

    return Completed(process.returncode, joined("out"), joined("err"))
