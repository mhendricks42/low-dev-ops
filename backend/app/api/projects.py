"""Load and save projects as <workspace>/<name>/project.json, plus the generated main.tf."""

import errno
import os
import re
import secrets
import stat
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from fastapi import Path as PathParam
from pydantic import BaseModel, ValidationError

from app.api.catalog import CATALOG
from app.api.guard import MAX_BODY_BYTES
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


# All project file access goes through directory fds opened with O_NOFOLLOW, so a path is
# never resolved again after the check: swapping a directory for a symlink cannot redirect a
# write (M3.1, closes the race M3 accepted). POSIX only; the app runs in the Linux container.
if not {os.open, os.mkdir, os.rename, os.unlink} <= os.supports_dir_fd:  # replace uses renameat too
    raise RuntimeError("this platform lacks dir_fd support (POSIX required)")
_NOFOLLOW_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


@contextmanager
def _open_project_dir(name: str, *, create: bool) -> Iterator[int]:
    if not re.fullmatch(NAME_PATTERN, name):
        raise HTTPException(422, detail={"message": "invalid project name"})
    root = _workspace().resolve()  # the workspace root is the user's own setting
    if create:
        root.mkdir(parents=True, exist_ok=True)
    elif not root.is_dir():
        raise HTTPException(404, detail={"message": f"no project '{name}'"})
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        if create:
            with suppress(FileExistsError):
                os.mkdir(name, 0o755, dir_fd=root_fd)
        try:
            dir_fd = os.open(name, _NOFOLLOW_DIR, dir_fd=root_fd)
        except FileNotFoundError as e:
            raise HTTPException(404, detail={"message": f"no project '{name}'"}) from e
        except OSError as e:
            if e.errno == errno.ELOOP:
                raise HTTPException(
                    422, detail={"message": "project directory is a symlink"}
                ) from e
            if e.errno == errno.ENOTDIR:
                raise HTTPException(
                    422, detail={"message": "project path is not a directory"}
                ) from e
            raise
    finally:
        os.close(root_fd)
    try:
        yield dir_fd
    finally:
        os.close(dir_fd)


def _write_atomic(dir_fd: int, filename: str, text: str) -> None:
    tmp = f".{filename}.{secrets.token_hex(8)}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dir_fd)
    try:
        try:
            data = memoryview(text.encode())
            while data:
                data = data[os.write(fd, data) :]
            os.fsync(fd)
        finally:
            os.close(fd)
        # Replaces a symlink at `filename` rather than writing through it.
        os.replace(tmp, filename, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
    except BaseException:
        with suppress(FileNotFoundError):
            os.unlink(tmp, dir_fd=dir_fd)
        raise
    os.fsync(dir_fd)


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


def _read_project(dir_fd: int, name: str) -> tuple[Project, bytes]:
    """project.json of an opened project dir: the model and the exact bytes it was read from."""
    try:
        fd = os.open("project.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
    except FileNotFoundError as e:
        raise HTTPException(404, detail={"message": f"no project '{name}'"}) from e
    except OSError as e:
        if e.errno == errno.ELOOP:
            raise HTTPException(422, detail={"message": "project.json is a symlink"}) from e
        raise
    try:
        # O_NONBLOCK so a FIFO cannot block the open; then only a small regular file is read.
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise HTTPException(422, detail={"message": "project.json is not a regular file"})
        if info.st_size > MAX_BODY_BYTES:
            raise HTTPException(422, detail={"message": "project.json is too large"})
        data = os.read(fd, MAX_BODY_BYTES + 1)
    finally:
        os.close(fd)
    if len(data) > MAX_BODY_BYTES:  # grew after the fstat
        raise HTTPException(422, detail={"message": "project.json is too large"})
    try:
        return Project.model_validate_json(data), data
    except ValidationError as e:
        raise HTTPException(422, detail={"message": f"project.json is invalid: {e}"}) from e


@router.get("/{name}")
def get_project(name: Name) -> dict[str, Any]:
    with _open_project_dir(name, create=False) as dir_fd:
        project, _ = _read_project(dir_fd, name)
    return {"project": project.model_dump(mode="json", by_alias=True)}


@router.put("/{name}")
def save_project(name: Name, body: SaveRequest) -> dict[str, Any]:
    project = body.project
    if project.meta.name != name:
        raise HTTPException(422, detail={"message": "meta.name must equal the project name"})
    # Render both files before writing either, so a failure never leaves them out of step.
    hcl = generate(project)
    text = project.model_dump_json(by_alias=True, indent=2) + "\n"
    with _open_project_dir(name, create=True) as dir_fd:
        _write_atomic(dir_fd, "project.json", text)
        _write_atomic(dir_fd, "main.tf", hcl)
    return {"issues": [asdict(i) for i in check_project(project, CATALOG)]}
