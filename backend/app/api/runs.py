"""Run status and the live log as Server-Sent Events (M5)."""

import json
from collections.abc import Iterator
from typing import Any

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


def _events(run: Run) -> Iterator[str]:
    for line in run.follow():
        if line is None:
            yield ": keep-alive\n\n"  # an SSE comment; clients ignore it
        else:
            yield f"event: line\ndata: {json.dumps(line)}\n\n"
    yield f"event: exit\ndata: {json.dumps({'exitCode': run.exit_code, 'status': run.status})}\n\n"


# Plain `def` generator: it blocks while waiting for lines, so Starlette iterates it in a thread.
@router.get("/{run_id}/log")
def run_log(run_id: str) -> StreamingResponse:
    return StreamingResponse(
        _events(_run(run_id)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
