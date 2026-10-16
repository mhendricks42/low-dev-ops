"""Who is signed in to the Azure CLI, and in which subscription (M5)."""

from fastapi import APIRouter, HTTPException

from app import azure

router = APIRouter(prefix="/api/azure")


@router.get("/account")
def get_account() -> dict[str, str]:
    try:
        a = azure.account()
    except azure.NotLoggedIn as e:
        raise HTTPException(401, detail={"message": str(e)}) from e
    except azure.AzError as e:
        raise HTTPException(502, detail={"message": f"Azure CLI failed: {e}"}) from e
    return {
        "user": a.user,
        "subscriptionId": a.subscription_id,
        "subscriptionName": a.subscription_name,
        "tenantId": a.tenant_id,
    }
