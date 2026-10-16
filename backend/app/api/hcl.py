from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.hcl import HclParseError
from app.hcl.generate import generate
from app.hcl.parse import parse
from app.model import Project

router = APIRouter(prefix="/api/hcl")


class GenerateRequest(BaseModel):
    project: Project


class ParseRequest(BaseModel):
    hcl: str = Field(max_length=1_000_000)  # the parser is linear, but cap untrusted input
    previous: Project


@router.post("/generate")
def generate_hcl(body: GenerateRequest) -> dict[str, str]:
    return {"hcl": generate(body.project)}


@router.post("/parse")
def parse_hcl(body: ParseRequest) -> dict[str, Any]:
    try:
        project = parse(body.hcl, body.previous)
    except HclParseError as e:
        raise HTTPException(422, detail={"message": str(e), "line": e.line}) from e
    return {"project": project.model_dump(mode="json", by_alias=True)}
