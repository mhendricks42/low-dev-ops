"""app/proc.py: the one way LowDevOps starts a subprocess (scanners, az, terraform)."""

import os
import sys
import time
from pathlib import Path

import pytest

from app import proc

PY = sys.executable


def test_captures_output_and_exit_code(tmp_path: Path) -> None:
    done = proc.run(
        [PY, "-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"],
        cwd=tmp_path,
        timeout=10,
        env=proc.inherited_env(),
    )
    assert (done.returncode, done.stdout, done.stderr) == (3, "out\n", "err\n")


def test_streams_lines_as_they_arrive_with_stderr_merged(tmp_path: Path) -> None:
    lines: list[str] = []
    code = (
        "import sys, time\n"
        "print('one', flush=True)\n"
        "print('two', file=sys.stderr, flush=True)\n"
        "time.sleep(0.1)\n"
        "print('three')"
    )
    done = proc.run(
        [PY, "-c", code], cwd=tmp_path, timeout=10, env=proc.inherited_env(), on_line=lines.append
    )
    assert done.returncode == 0
    assert lines == ["one", "two", "three"]


def test_missing_binary_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(proc.ProcError, match="not installed"):
        proc.run(["lowdevops-no-such-tool"], cwd=tmp_path, timeout=10, env=proc.inherited_env())


@pytest.mark.parametrize("stream", [False, True])
def test_timeout_kills_the_whole_process_group(tmp_path: Path, stream: bool) -> None:
    pid_file = tmp_path / "child.pid"
    code = (
        "import subprocess, sys, time\n"
        "child = subprocess.Popen(['sleep', '300'])\n"
        f"open({str(pid_file)!r}, 'w').write(str(child.pid))\n"
        "print('started', flush=True)\ntime.sleep(300)"
    )
    started = time.monotonic()
    with pytest.raises(proc.ProcTimeout, match="took longer than 1 s"):
        proc.run(
            [PY, "-c", code],
            cwd=tmp_path,
            timeout=1,
            env=proc.inherited_env(),
            on_line=(lambda _: None) if stream else None,
        )
    assert time.monotonic() - started < 20
    child = int(pid_file.read_text())
    for _ in range(50):
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    pytest.fail(f"worker {child} survived the timeout")


def test_env_is_exactly_what_the_caller_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SECRET_FROM_API", "x")
    env = proc.inherited_env(drop_prefixes=("SECRET_",), extra={"ADDED": "1"})
    assert "SECRET_FROM_API" not in env and env["ADDED"] == "1" and "PATH" in env
    code = "import os; print(os.environ.get('SECRET_FROM_API', '-'), os.environ['ADDED'])"
    assert proc.run([PY, "-c", code], cwd=tmp_path, timeout=10, env=env).stdout == "- 1\n"


def test_a_failing_line_callback_still_kills_the_child(tmp_path: Path) -> None:
    # If reading the output fails (callback error, full disk), the tool must not keep running.
    pid_file = tmp_path / "pid"
    code = (
        "import os, time\n"
        f"open({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
        "print('x', flush=True)\n"
        "time.sleep(300)"
    )

    def explode(_: str) -> None:
        raise OSError("disk full")

    started = time.monotonic()
    with pytest.raises(OSError, match="disk full"):
        proc.run(
            [PY, "-c", code], cwd=tmp_path, timeout=60, env=proc.inherited_env(), on_line=explode
        )
    assert time.monotonic() - started < 10  # killed at once, not when the 60 s timeout fires
    pid = int(pid_file.read_text())
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    pytest.fail(f"child {pid} survived")


def test_undecodable_output_is_replaced_not_fatal(tmp_path: Path) -> None:
    code = "import sys; sys.stdout.buffer.write(b'ok \\xff\\n')"
    lines: list[str] = []
    proc.run(
        [PY, "-c", code], cwd=tmp_path, timeout=10, env=proc.inherited_env(), on_line=lines.append
    )
    assert lines == ["ok �"]


def test_a_quick_exit_is_never_reported_as_a_timeout(tmp_path: Path) -> None:
    # The timer must not fire on (or signal) a child that already exited and was reaped.
    for _ in range(20):
        assert (
            proc.run(
                [PY, "-c", "pass"], cwd=tmp_path, timeout=0.05, env=proc.inherited_env()
            ).returncode
            == 0
        )


def test_env_must_be_given() -> None:
    # No implicit inheritance: every caller decides what reaches the child.
    with pytest.raises(TypeError):
        proc.run([PY, "-c", "pass"], cwd=Path("."), timeout=10)  # type: ignore[call-arg]
