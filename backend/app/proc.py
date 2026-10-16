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
from collections.abc import Callable, Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path


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


def _kill_group(process: subprocess.Popen[str]) -> None:
    with suppress(ProcessLookupError):  # the whole group may have just exited
        os.killpg(process.pid, signal.SIGKILL)


def run(
    args: list[str],
    *,
    cwd: Path,
    timeout: float,
    env: Mapping[str, str] | None = None,
    on_line: Callable[[str], None] | None = None,
) -> Completed:
    tool = args[0]
    binary = shutil.which(tool)
    if binary is None:
        raise ProcError(f"{tool} is not installed")
    timed_out = threading.Event()
    with (
        subprocess.Popen(  # noqa: S603 - fixed argument list, no shell
            [binary, *args[1:]],
            cwd=cwd,
            env=dict(env) if env is not None else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if on_line else subprocess.PIPE,
            text=True,
            start_new_session=True,
        ) as process
    ):

        def expire() -> None:
            timed_out.set()
            _kill_group(process)

        timer = threading.Timer(timeout, expire)
        timer.daemon = True
        timer.start()
        try:
            if on_line is not None and process.stdout is not None:
                for line in process.stdout:
                    on_line(line.rstrip("\n"))
                process.wait()
                stdout, stderr = "", ""
            else:
                stdout, stderr = process.communicate()
        finally:
            timer.cancel()
    if timed_out.is_set():
        raise ProcTimeout(f"{os.path.basename(tool)} took longer than {timeout:g} s")
    return Completed(process.returncode, stdout, stderr)
