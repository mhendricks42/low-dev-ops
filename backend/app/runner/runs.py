"""Runs: one at a time per key, with a log that readers can follow while it grows (M5).

A key is a project ("project:<name>") or a subscription's bootstrap ("bootstrap:<id>"). The
lock lives in this process: the API is single-user on localhost, and Terraform's state lock is
the second line of defence.
"""

import secrets
import threading
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Literal

from app import proc

Status = Literal["running", "succeeded", "failed"]


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
            self.lines.append(line)
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

    def follow(self, idle_timeout: float = 15.0) -> Iterator[str | None]:
        """Lines from the start, then new ones as they come; None after `idle_timeout` quiet
        seconds (a keep-alive), ending once the run has finished and every line was sent."""
        sent = 0
        while True:
            with self._changed:
                self._changed.wait_for(partial(self._has_news, sent), idle_timeout)
                batch, done = self.lines[sent:], self.status != "running"
            if not batch and not done:
                yield None
            yield from batch
            sent += len(batch)
            if done and sent == len(self.lines):
                return

    def _has_news(self, sent: int) -> bool:
        return len(self.lines) > sent or self.status != "running"

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
            self._active[key] = run
            self._runs[run.id] = run
        threading.Thread(target=self._execute, args=(run, work), daemon=True).start()
        return run

    @staticmethod
    def _execute(run: Run, work: Callable[[Run], int]) -> None:
        try:
            code = work(run)
        except Exception as e:
            run.append(f"Error: {e}")
            code = 1
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
    env: Mapping[str, str] | None = None


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
