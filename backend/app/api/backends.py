"""The shared state backend per subscription: read it, or bootstrap it (M5)."""

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from fastapi import Path as PathParam
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app import bootstrap, settings
from app.runner.runs import REGISTRY, Run, RunBusy

router = APIRouter(prefix="/api/backends")

GUID = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
SubscriptionId = Annotated[str, PathParam(pattern=GUID)]


class BootstrapRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    location: str = Field(pattern=r"^[a-z0-9]{2,40}$")  # an Azure region name, e.g. westeurope
    confirm_subscription_id: str


@router.get("/{subscription_id}")
def get_backend(subscription_id: SubscriptionId) -> dict[str, Any]:
    backend = settings.load().backends.get(subscription_id)
    if backend is None:
        raise HTTPException(
            404, detail={"message": "no state backend recorded for this subscription"}
        )
    return backend.model_dump(by_alias=True)


@router.post("/{subscription_id}/bootstrap", status_code=202)
def start_bootstrap(subscription_id: SubscriptionId, body: BootstrapRequest) -> dict[str, str]:
    # The subscription-confirm step: the user typed or ticked the exact id they mean.
    if body.confirm_subscription_id.lower() != subscription_id.lower():
        raise HTTPException(422, detail={"message": "confirm the subscription id to bootstrap"})

    def work(run: Run) -> int:
        bootstrap.ensure_backend(subscription_id, body.location, say=run.append)
        return 0

    try:
        run = REGISTRY.start(f"bootstrap:{subscription_id.lower()}", "bootstrap", work)
    except RunBusy as e:
        raise HTTPException(409, detail={"message": str(e), "runId": e.run.id}) from e
    return {"runId": run.id}
