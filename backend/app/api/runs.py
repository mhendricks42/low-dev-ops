"""Run status and the live log as Server-Sent Events (M5)."""

import json
from collections.abc import AsyncIterator
from typing import Any

import anyio
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.runner.runs import REGISTRY, Run

router = APIRouter(prefix="/api/runs")


def _run(run_id: str) -> Run:
    run = REGISTRY.get(run_id)
    if run is None:
        raise HTTPException(404, detail={"message": f"no run '{run_id}'"})
    return run


@router.get("/{run_id}")
def run_status(run_id: str) -> dict[str, Any]:
    return _run(run_id).summary()


POLL_SECONDS = 0.2
KEEPALIVE_SECONDS = 15.0


async def _events(run: Run) -> AsyncIterator[str]:
    """Poll the run's lines without holding a worker thread (each open stream would pin one)."""
    sent, quiet = 0, 0.0
    while True:
        done = run.status != "running"  # read before the lines, so no line is missed
        lines = run.lines[sent:]
        for line in lines:
            yield f"event: line\ndata: {json.dumps(line)}\n\n"
        sent += len(lines)
        if done and sent >= len(run.lines):
            break
        quiet = 0.0 if lines else quiet + POLL_SECONDS
        if quiet >= KEEPALIVE_SECONDS:
            yield ": keep-alive\n\n"  # an SSE comment; clients ignore it
            quiet = 0.0
        await anyio.sleep(POLL_SECONDS)
    yield f"event: exit\ndata: {json.dumps({'exitCode': run.exit_code, 'status': run.status})}\n\n"


@router.get("/{run_id}/log")
def run_log(run_id: str) -> StreamingResponse:
    return StreamingResponse(
        _events(_run(run_id)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
