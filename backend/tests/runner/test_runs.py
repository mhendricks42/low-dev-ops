"""Run framework: one run per key, logged lines, and an SSE log that ends with the exit code."""

import json
import sys
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.runner.runs import REGISTRY, Run, RunBusy, RunRegistry, Step, run_steps

client = TestClient(app, base_url="http://127.0.0.1:8000")
PY = sys.executable


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
        Step([PY, "-c", "print('first step')"], cwd=tmp_path, timeout=10),
        Step([PY, "-c", "import sys; print('boom'); sys.exit(4)"], cwd=tmp_path, timeout=10),
        Step([PY, "-c", "print('never')"], cwd=tmp_path, timeout=10),
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
        lambda r: run_steps(r, [Step([PY, "-c", script], cwd=tmp_path, timeout=10)]),
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
