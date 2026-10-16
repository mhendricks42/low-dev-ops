"""The one way LowDevOps starts a subprocess: Conftest/Checkov/Trivy, az and terraform.

- An argument list, never a shell; the binary is resolved to an absolute path on PATH.
- Its own process group, so a timeout kills the tool and everything it started.
- An explicit environment: callers say what to drop and what to add.
- Either captured output, or a line callback for streamed logs (stderr merged into stdout).
"""

import os
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
from typing import IO

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


def _read(process: subprocess.Popen[str], on_line: Callable[[str], None] | None) -> tuple[str, str]:
    """Read the child's output to EOF without reaping it (reaping is the caller's job)."""
    if on_line is not None and process.stdout is not None:
        for line in process.stdout:
            on_line(line.rstrip("\n"))
        return "", ""
    chunks: dict[str, str] = {}

    def drain(name: str, stream: IO[str] | None) -> None:
        chunks[name] = stream.read() if stream is not None else ""

    readers = [
        threading.Thread(target=drain, args=("out", process.stdout), daemon=True),
        threading.Thread(target=drain, args=("err", process.stderr), daemon=True),
    ]
    for reader in readers:
        reader.start()
    for reader in readers:
        reader.join()
    return chunks.get("out", ""), chunks.get("err", "")


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
        text=True,
        errors="replace",  # odd bytes in a tool's output never abort the run
        start_new_session=True,
    )
    # The child is reaped only at the very end (under `lock`), so until then its pid and
    # group id stay reserved: killpg can never hit a reused pid.
    lock = threading.Lock()
    reaped = False
    timed_out = threading.Event()
    listening = threading.Event()
    listening.set()
    outcome: list[tuple[str, str]] = []
    failure: list[BaseException] = []

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

    def emit(line: str) -> None:
        if listening.is_set() and on_line is not None:  # nothing reaches it after run() returns
            on_line(line)

    def read() -> None:
        try:
            outcome.append(_read(process, emit if on_line else None))
        except BaseException as e:  # handed to the caller below
            failure.append(e)
        finally:
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    with suppress(OSError):
                        stream.close()

    # A separate reader, so a process that escaped the group (setsid) and keeps the output
    # pipe open can't hold the run open: we stop waiting for it once the tool has exited.
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    timer = threading.Timer(timeout, partial(kill_group, on_timeout=True))
    timer.daemon = True
    timer.start()
    try:
        while reader.is_alive() and not exited():
            reader.join(0.02)
        if failure:  # a callback or read error: leave no tool running
            kill_group()
        while not exited():  # the timer guarantees this ends
            time.sleep(0.02)
        kill_group()  # whatever the tool left behind in its group
        reader.join(READER_GRACE_SECONDS)
    finally:
        listening.clear()
        timer.cancel()
        kill_group()
        with lock:
            process.wait()
            reaped = True
    if failure:
        raise failure[0]
    if timed_out.is_set() or not outcome:
        raise ProcTimeout(f"{os.path.basename(tool)} took longer than {timeout:g} s")
    stdout, stderr = outcome[0]
    return Completed(process.returncode, stdout, stderr)
