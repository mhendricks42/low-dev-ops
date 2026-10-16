from fastapi import FastAPI

from app.api import catalog, hcl

app = FastAPI(title="LowDevOps")
app.include_router(catalog.router)
app.include_router(hcl.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
