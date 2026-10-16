"""Runs: one at a time per key, with a log that readers can follow while it grows (M5).

A key is a project ("project:<name>") or a subscription's bootstrap ("bootstrap:<id>"). The
lock lives in this process: the API is single-user on localhost, and Terraform's state lock is
the second line of defence.
"""

import secrets
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from app import proc

Status = Literal["running", "succeeded", "failed"]
MAX_LINES = 20_000
TRUNCATED = "[… more output is in run.log in the project folder]"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class Run:
    id: str
    key: str
    kind: str
    status: Status = "running"
    exit_code: int | None = None
    started_at: str = field(default_factory=_now)
    finished_at: str | None = None
    lines: list[str] = field(default_factory=list)
    log_file: Path | None = None
    _changed: threading.Condition = field(default_factory=threading.Condition, repr=False)

    def append(self, line: str) -> None:
        with self._changed:
            # Memory keeps the first MAX_LINES for the browser; run.log keeps every line.
            if len(self.lines) < MAX_LINES:
                self.lines.append(line)
            elif self.lines[-1] != TRUNCATED:
                self.lines.append(TRUNCATED)
            if self.log_file is not None:
                with self.log_file.open("a") as f:
                    f.write(line + "\n")
            self._changed.notify_all()

    def finish(self, exit_code: int) -> None:
        with self._changed:
            self.exit_code = exit_code
            self.status = "succeeded" if exit_code == 0 else "failed"
            self.finished_at = _now()
            self._changed.notify_all()

    def wait(self, timeout: float | None = None) -> bool:
        with self._changed:
            return self._changed.wait_for(lambda: self.status != "running", timeout)

    def summary(self) -> dict[str, object]:
        return {
            "id": self.id,
            "key": self.key,
            "kind": self.kind,
            "status": self.status,
            "exitCode": self.exit_code,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
        }


class RunBusy(Exception):
    def __init__(self, run: Run) -> None:
        super().__init__(f"a {run.kind} run is already in progress ({run.id})")
        self.run = run


class RunRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: dict[str, Run] = {}
        self._runs: dict[str, Run] = {}  # every run of this process, for status and logs

    def start(
        self, key: str, kind: str, work: Callable[[Run], int], log_file: Path | None = None
    ) -> Run:
        with self._lock:
            active = self._active.get(key)
            if active is not None and active.status == "running":
                raise RunBusy(active)
            run = Run(id=secrets.token_hex(8), key=key, kind=kind, log_file=log_file)
            if active is not None:  # keep only the latest run per key (bounded memory)
                self._runs.pop(active.id, None)
            self._active[key] = run
            self._runs[run.id] = run
        threading.Thread(target=self._execute, args=(run, work), daemon=True).start()
        return run

    @staticmethod
    def _execute(run: Run, work: Callable[[Run], int]) -> None:
        code = 1  # unless work returns: a run never stays "running" (and its key locked)
        try:
            code = work(run)
        except Exception as e:  # any failure ends the run, with its message
            run.append(f"Error: {e}")
        except BaseException as e:  # a worker thread has no one to re-raise to
            run.append(f"Error: interrupted ({type(e).__name__})")
        finally:
            run.finish(code)

    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def current(self, key: str) -> Run | None:
        return self._active.get(key)


REGISTRY = RunRegistry()


@dataclass(frozen=True)
class Step:
    args: list[str]
    cwd: Path
    timeout: float
    env: Mapping[str, str]  # required: see app/proc.py


def run_steps(run: Run, steps: list[Step]) -> int:
    """Run steps in order, streaming their output into the run; stop at the first failure."""
    for step in steps:
        run.append(f"$ {' '.join(step.args)}")
        try:
            done = proc.run(
                step.args, cwd=step.cwd, timeout=step.timeout, env=step.env, on_line=run.append
            )
        except proc.ProcError as e:
            run.append(f"Error: {e}")
            return 1
        if done.returncode != 0:
            return done.returncode
    return 0
