"""Load and save projects as <workspace>/<name>/project.json, plus the generated main.tf."""

import os
import re
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from fastapi import Path as PathParam
from pydantic import BaseModel, ValidationError

from app.api.catalog import CATALOG
from app.catalog.check_project import check_project
from app.hcl.generate import generate
from app.model import Project

router = APIRouter(prefix="/api/projects")

NAME_PATTERN = r"^[a-z][a-z0-9-]{0,62}$"
Name = Annotated[str, PathParam(pattern=NAME_PATTERN)]


class SaveRequest(BaseModel):
    project: Project


def _workspace() -> Path:
    return Path(os.environ.get("LOWDEVOPS_WORKSPACE", "~/lowdevops")).expanduser()


def _project_dir(name: str) -> Path:
    # The pattern already rules out "/" and "..". Re-check after resolve() so a symlink
    # inside the workspace cannot point a write somewhere else.
    if not re.fullmatch(NAME_PATTERN, name):
        raise HTTPException(422, detail={"message": "invalid project name"})
    root = _workspace().resolve()
    if (root / name).is_symlink():
        raise HTTPException(422, detail={"message": "project directory is a symlink"})
    target = (root / name).resolve()
    if target.parent != root:
        raise HTTPException(422, detail={"message": "project path leaves the workspace"})
    return target


def _write_atomic(path: Path, text: str) -> None:
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, suffix=".tmp") as f:
        try:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        except BaseException:
            os.unlink(f.name)
            raise
    try:
        os.replace(f.name, path)  # replaces a symlink at `path` rather than writing through it
    except BaseException:
        os.unlink(f.name)
        raise


@router.get("")
def list_projects() -> dict[str, list[str]]:
    root = _workspace()
    if not root.is_dir():
        return {"names": []}
    names = [
        p.name
        for p in root.iterdir()
        if re.fullmatch(NAME_PATTERN, p.name) and (p / "project.json").is_file()
    ]
    return {"names": sorted(names)}


@router.get("/{name}")
def get_project(name: Name) -> dict[str, Any]:
    path = _project_dir(name) / "project.json"
    if path.is_symlink():
        raise HTTPException(422, detail={"message": "project.json is a symlink"})
    if not path.is_file():
        raise HTTPException(404, detail={"message": f"no project '{name}'"})
    try:
        project = Project.model_validate_json(path.read_text())
    except ValidationError as e:
        raise HTTPException(422, detail={"message": f"project.json is invalid: {e}"}) from e
    return {"project": project.model_dump(mode="json", by_alias=True)}


@router.put("/{name}")
def save_project(name: Name, body: SaveRequest) -> dict[str, Any]:
    project = body.project
    if project.meta.name != name:
        raise HTTPException(422, detail={"message": "meta.name must equal the project name"})
    # Render both files before writing either, so a failure never leaves them out of step.
    hcl = generate(project)
    text = project.model_dump_json(by_alias=True, indent=2) + "\n"
    directory = _project_dir(name)
    directory.mkdir(parents=True, exist_ok=True)
    _write_atomic(directory / "project.json", text)
    _write_atomic(directory / "main.tf", hcl)
    return {"issues": [asdict(i) for i in check_project(project, CATALOG)]}
