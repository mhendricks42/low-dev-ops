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
from pathlib import Path
from typing import IO


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
    with (
        subprocess.Popen(  # noqa: S603 - fixed argument list, no shell
            [binary, *args[1:]],
            cwd=cwd,
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if on_line else subprocess.PIPE,
            text=True,
            errors="replace",  # odd bytes in a tool's output never abort the run
            start_new_session=True,
        ) as process
    ):
        # Every reap goes through `reaped` + poll(), so the timer can never signal a pid that
        # was already reaped (and may now belong to someone else).
        reaped = threading.Lock()
        timed_out = threading.Event()

        def kill() -> None:
            with reaped:
                if process.poll() is None:
                    with suppress(ProcessLookupError):  # the group may have just exited
                        os.killpg(process.pid, signal.SIGKILL)

        def expire() -> None:
            timed_out.set()
            kill()

        timer = threading.Timer(timeout, expire)
        timer.daemon = True
        timer.start()
        finished = False
        try:
            stdout, stderr = _read(process, on_line)
            finished = True
        finally:
            if not finished:  # a callback or read error: leave no tool running
                kill()
            while True:
                with reaped:
                    if process.poll() is not None:
                        break
                time.sleep(0.02)
            timer.cancel()
    if timed_out.is_set():
        raise ProcTimeout(f"{os.path.basename(tool)} took longer than {timeout:g} s")
    return Completed(process.returncode, stdout, stderr)
