from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api import azure, backends, catalog, guardrails, hcl, projects, runs
from app.api.guard import LocalOnlyMiddleware

app = FastAPI(title="LowDevOps")
app.include_router(azure.router)
app.include_router(backends.router)
app.include_router(catalog.router)
app.include_router(guardrails.router)
app.include_router(hcl.router)
app.include_router(projects.router)
app.include_router(runs.router)
app.add_middleware(LocalOnlyMiddleware)
# Outermost: a DNS-rebinding page reaches 127.0.0.1 under its own host name; refuse it.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
