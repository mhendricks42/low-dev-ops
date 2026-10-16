"""Create (or check) the shared Terraform state backend of one subscription (M5, PRD).

Every step reads first and creates only what is missing, so running it again changes nothing.
Runs as the signed-in user through `az`; the result is recorded in settings.json.
"""

import hashlib
import time
from collections.abc import Callable

from app import azure, settings

RESOURCE_GROUP = "rg-lowdevops-state"
CONTAINER = "tfstate"
DATA_ROLE = "Storage Blob Data Contributor"
TAGS = "managedBy=lowdevops"
RETRY_DELAY_SECONDS = 10
RETRY_ATTEMPTS = 12  # about 2 minutes for a new role assignment to take effect


def storage_account_name(subscription_id: str) -> str:
    # CAF `st` + a stable suffix: storage names are global, 3-24 lowercase letters and digits.
    return "stlowdevops" + hashlib.sha256(subscription_id.encode()).hexdigest()[:10]


def ensure_backend(
    subscription_id: str, location: str, say: Callable[[str], None]
) -> settings.Backend:
    sub = ["--subscription", subscription_id]
    rg = ["--resource-group", RESOURCE_GROUP]
    account = storage_account_name(subscription_id)

    def exists(args: list[str]) -> bool:
        try:
            azure.az([*args, *sub])
        except azure.NotFound:
            return False
        return True

    if exists(["group", "show", "--name", RESOURCE_GROUP]):
        say(f"Resource group {RESOURCE_GROUP} exists.")
    else:
        say(f"Creating resource group {RESOURCE_GROUP} in {location}…")
        azure.az(
            [
                "group",
                "create",
                "--name",
                RESOURCE_GROUP,
                "--location",
                location,
                "--tags",
                TAGS,
                *sub,
            ]
        )

    try:
        account_id = str(
            azure.az(["storage", "account", "show", "--name", account, *rg, *sub])["id"]
        )
        say(f"Storage account {account} exists.")
    except azure.NotFound:
        say(f"Creating storage account {account} (TLS 1.2, no public blobs, no shared keys)…")
        azure.az([
            "storage", "account", "create", "--name", account, *rg, "--location", location,
            "--kind", "StorageV2", "--sku", "Standard_ZRS", "--min-tls-version", "TLS1_2",
            "--https-only", "true", "--allow-blob-public-access", "false",
            "--allow-shared-key-access", "false", "--tags", TAGS, *sub,
        ])  # fmt: skip
        account_id = str(
            azure.az(["storage", "account", "show", "--name", account, *rg, *sub])["id"]
        )

    props = azure.az(
        [
            "storage",
            "account",
            "blob-service-properties",
            "show",
            "--account-name",
            account,
            *rg,
            *sub,
        ]
    )
    if (
        props.get("isVersioningEnabled")
        and (props.get("deleteRetentionPolicy") or {}).get("enabled")
        and (props.get("containerDeleteRetentionPolicy") or {}).get("enabled")
    ):
        say("Blob versioning and soft delete are on.")
    else:
        say("Turning on blob versioning and 30-day soft delete…")
        azure.az([
            "storage", "account", "blob-service-properties", "update",
            "--account-name", account, *rg,
            "--enable-versioning", "true", "--enable-delete-retention", "true",
            "--delete-retention-days", "30", "--enable-container-delete-retention", "true",
            "--container-delete-retention-days", "30", *sub,
        ])  # fmt: skip

    user_id = str(azure.az(["ad", "signed-in-user", "show"])["id"])
    role = ["--role", DATA_ROLE, "--scope", account_id]
    if azure.az(["role", "assignment", "list", "--assignee", user_id, *role, *sub]):
        say(f"You already have {DATA_ROLE} on the account.")
    else:
        say(f"Giving you {DATA_ROLE} on the account (state is read with Entra ID, not keys)…")
        azure.az([
            "role", "assignment", "create", "--assignee-object-id", user_id,
            "--assignee-principal-type", "User", *role, *sub,
        ])  # fmt: skip

    container = ["--name", CONTAINER, "--account-name", account, "--auth-mode", "login", *sub]
    if (azure.az(["storage", "container", "exists", *container]) or {}).get("exists"):
        say(f"Container {CONTAINER} exists.")
    else:
        say(f"Creating container {CONTAINER}…")
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                azure.az(["storage", "container", "create", *container])
                break
            except azure.AzError as e:
                if "403" not in str(e) and "AuthorizationPermission" not in str(e):
                    raise
                if attempt == RETRY_ATTEMPTS:
                    raise
                say(
                    "Not allowed yet, waiting for the role assignment to take effect "
                    f"({attempt}/{RETRY_ATTEMPTS})…"
                )
                time.sleep(RETRY_DELAY_SECONDS)

    backend = settings.Backend(
        resource_group=RESOURCE_GROUP,
        storage_account=account,
        container=CONTAINER,
        location=location,
    )
    current = settings.load()
    settings.save(
        current.model_copy(update={"backends": {**current.backends, subscription_id: backend}})
    )
    say(f"State backend ready: {account}/{CONTAINER}, recorded in settings.json.")
    return backend
