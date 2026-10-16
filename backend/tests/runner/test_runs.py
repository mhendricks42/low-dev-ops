"""Run framework: one run per key, logged lines, and an SSE log that ends with the exit code."""

import inspect
import json
import os
import sys
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import proc
from app.api import runs as runs_api
from app.main import app
from app.runner import runs
from app.runner.runs import REGISTRY, Run, RunBusy, RunRegistry, Step, run_steps

client = TestClient(app, base_url="http://127.0.0.1:8000")
PY = sys.executable
ENV = proc.inherited_env()


def wait(run: Run) -> None:
    assert run.wait(timeout=20), "run did not finish"


def test_one_run_per_key_and_a_second_start_is_busy() -> None:
    registry = RunRegistry()
    release = threading.Event()
    first = registry.start("project:a", "plan", lambda run: 0 if release.wait(20) else 1)
    with pytest.raises(RunBusy) as busy:
        registry.start("project:a", "apply", lambda run: 0)
    assert busy.value.run is first
    other = registry.start("project:b", "plan", lambda run: 0)  # other keys are independent
    wait(other)
    release.set()
    wait(first)
    again = registry.start("project:a", "apply", lambda run: 0)  # free once finished
    wait(again)
    assert (first.status, again.status) == ("succeeded", "succeeded")


def test_steps_stream_lines_and_stop_at_the_first_failure(tmp_path: Path) -> None:
    steps = [
        Step([PY, "-c", "print('first step')"], cwd=tmp_path, timeout=10, env=ENV),
        Step(
            [PY, "-c", "import sys; print('boom'); sys.exit(4)"], cwd=tmp_path, timeout=10, env=ENV
        ),
        Step([PY, "-c", "print('never')"], cwd=tmp_path, timeout=10, env=ENV),
    ]
    run = RunRegistry().start("k", "plan", lambda r: run_steps(r, steps))
    wait(run)
    assert (run.status, run.exit_code) == ("failed", 4)
    assert "first step" in run.lines and "boom" in run.lines and "never" not in run.lines


def test_an_exception_fails_the_run_with_its_message() -> None:
    def explode(run: Run) -> int:
        raise RuntimeError("az is not installed")

    run = RunRegistry().start("k", "bootstrap", explode)
    wait(run)
    assert (run.status, run.exit_code) == ("failed", 1)
    assert run.lines[-1] == "Error: az is not installed"


@pytest.mark.parametrize("code", [0, 3])
def test_the_log_stream_ends_with_the_exit_code(tmp_path: Path, code: int) -> None:
    # EC3: lines in order, then an `exit` event with the exit code, then the stream closes.
    script = (
        "import sys, time\n"
        "for i in range(3):\n"
        "    print('line', i, flush=True)\n"
        "    time.sleep(0.05)\n"
        f"sys.exit({code})"
    )
    run = REGISTRY.start(
        f"test:{code}",
        "plan",
        lambda r: run_steps(r, [Step([PY, "-c", script], cwd=tmp_path, timeout=10, env=ENV)]),
    )
    with client.stream("GET", f"/api/runs/{run.id}/log") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = [e for e in response.read().decode().split("\n\n") if e]
    parsed = [
        (
            e.split("\n")[0].removeprefix("event: "),
            json.loads(e.split("\n")[1].removeprefix("data: ")),
        )
        for e in events
    ]
    lines = [data for kind, data in parsed if kind == "line"]
    assert [line for line in lines if line.startswith("line")] == ["line 0", "line 1", "line 2"]
    assert parsed[-1] == (
        "exit",
        {"exitCode": code, "status": "succeeded" if code == 0 else "failed"},
    )


def test_run_status_and_unknown_runs() -> None:
    run = REGISTRY.start("test:status", "plan", lambda r: 0)
    wait(run)
    data = client.get(f"/api/runs/{run.id}").json()
    assert {k: data[k] for k in ("id", "kind", "status", "exitCode")} == {
        "id": run.id,
        "kind": "plan",
        "status": "succeeded",
        "exitCode": 0,
    }
    assert client.get("/api/runs/not-a-run").status_code == 404
    assert client.get("/api/runs/not-a-run/log").status_code == 404


def test_memory_keeps_a_capped_log_but_the_file_keeps_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runs, "MAX_LINES", 5)
    log = tmp_path / "run.log"
    run = Run(id="r", key="k", kind="plan")
    run.log_to(os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600))
    for i in range(8):
        run.append(f"line {i}")
    run.finish(0)
    assert run.lines == [*(f"line {i}" for i in range(5)), runs.TRUNCATED]
    assert log.read_text().splitlines() == [f"line {i}" for i in range(8)]
    assert run.log_fd is None  # closed with the run


def test_only_the_latest_run_per_key_is_kept() -> None:
    registry = RunRegistry()
    first = registry.start("project:a", "plan", lambda r: 0)
    wait(first)
    second = registry.start("project:a", "apply", lambda r: 0)
    wait(second)
    assert registry.get(first.id) is None and registry.get(second.id) is second


def test_a_run_always_finishes_even_on_base_exceptions() -> None:
    def interrupted(run: Run) -> int:
        raise KeyboardInterrupt

    registry = RunRegistry()
    run = registry.start("k", "plan", interrupted)
    assert run.wait(20) and run.status == "failed"
    wait(registry.start("k", "plan", lambda r: 0))  # the key is free again


def test_the_log_stream_holds_no_worker_thread() -> None:
    # Each open stream would otherwise pin one of the API's ~40 worker threads (EventSource
    # reconnects can open many), so the generator is async and only polls.
    assert inspect.isasyncgenfunction(runs_api._events)
