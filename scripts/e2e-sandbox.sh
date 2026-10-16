#!/usr/bin/env bash
# M5 human gate (EC6): bootstrap -> plan -> apply against a real sandbox subscription, through the
# app's own API, then destroy what it created. A HUMAN RUNS THIS. Claude never does: it changes
# real Azure resources (docs/specs/M5/spec.md).
#
# Needs: az login (as you), terraform, uv, curl, python3. Uses the az CLI's default subscription
# unless LOWDEVOPS_SANDBOX_SUBSCRIPTION is set. Exits non-zero at the first failed step.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
port=${LOWDEVOPS_SANDBOX_PORT:-8765}
api="http://127.0.0.1:$port"
location=westeurope # the project's naming uses the matching region code, weu
sub=${LOWDEVOPS_SANDBOX_SUBSCRIPTION:-$(az account show --query id --output tsv)}
tenant=$(az account show --subscription "$sub" --query tenantId --output tsv)
suffix=$(python3 -c 'import secrets, string; print("".join(secrets.choice(string.ascii_lowercase) for _ in range(5)))')
name="sandbox-$suffix"
workspace=$(mktemp -d "${TMPDIR:-/tmp}/lowdevops-sandbox-XXXXXX")
api_pid=""
backend=""

step() { printf '\n==> %s\n' "$*"; }
json() { python3 -c "import json, sys; print(eval(sys.argv[1], {}, {'d': json.load(sys.stdin)}))" "$1"; }

cleanup() {
  status=$?
  # An app run (e.g. an apply after Ctrl-C) is in its own session: wait until none is running,
  # or the destroy below would fail on the state lock and miss what the apply creates.
  if [ -n "$api_pid" ] && kill -0 "$api_pid" 2>/dev/null; then
    while curl -sf "$api/api/projects/$name/runs/current" 2>/dev/null |
      python3 -c 'import json, sys; r = json.load(sys.stdin)["run"]; sys.exit(0 if r and r["status"] == "running" else 1)'; do
      echo "Waiting for the app's current run to finish before cleaning up…"
      sleep 5
    done
    kill "$api_pid" 2>/dev/null || true
    wait "$api_pid" 2>/dev/null || true
  fi
  if [ -d "$workspace/$name/.terraform" ]; then
    step "Cleanup: terraform destroy in $workspace/$name (outside the app: destroy-all is out of scope)"
    # A clean environment, like the app's: only your az login, never ARM_CLIENT_*, TF_VAR_* etc.
    # (LOWDEVOPS_FAKE_TF_STATE only matters for a dry run against backend/tests/bin.)
    (cd "$workspace/$name" && env -i PATH="$PATH" HOME="$HOME" \
      ${AZURE_CONFIG_DIR:+AZURE_CONFIG_DIR="$AZURE_CONFIG_DIR"} \
      ${LOWDEVOPS_FAKE_TF_STATE:+LOWDEVOPS_FAKE_TF_STATE="$LOWDEVOPS_FAKE_TF_STATE"} \
      ARM_USE_CLI=true ARM_SUBSCRIPTION_ID="$sub" TF_IN_AUTOMATION=1 \
      terraform destroy -input=false -no-color -auto-approve) || {
      echo "!! destroy failed: remove resource group rg-$suffix-dev-weu by hand" >&2
      status=1
    }
  fi
  if [ -n "$backend" ]; then
    step "Left in place on purpose: the shared state backend ($backend, resource group rg-lowdevops-state)"
    echo "It holds the state blob $name.tfstate. Every project in subscription $sub shares it."
    echo "To remove the blob: az storage blob delete --auth-mode login --account-name ${backend%%/*} \\"
    echo "  --container-name ${backend##*/} --name $name.tfstate --subscription $sub"
  fi
  rm -rf "$workspace"
  exit "$status"
}
trap cleanup EXIT

# Wait for a run, printing its log as it streams; fail unless it succeeded.
follow() {
  curl -sSN "$api/api/runs/$1/log" | sed -n 's/^data: //p'
  [ "$(curl -sSf "$api/api/runs/$1" | json 'd["status"]')" = succeeded ]
}

step "Starting the API on $api (workspace $workspace)"
(cd "$root/backend" && LOWDEVOPS_WORKSPACE="$workspace" \
  exec uv run uvicorn app.main:app --host 127.0.0.1 --port "$port") &
api_pid=$!
for _ in $(seq 60); do curl -sf "$api/api/health" >/dev/null && break || sleep 1; done
curl -sSf "$api/api/health" >/dev/null

step "Signed in as"
curl -sSf "$api/api/azure/account" | json '"%s on %s (%s)" % (d["user"], d["subscriptionName"], d["subscriptionId"])'

step "Saving project $name: one resource group, rg-$suffix-dev-weu, in subscription $sub"
python3 - "$root/backend/tests/fixtures/valid/rg/project.json" "$name" "$suffix" "$sub" "$tenant" \
  >"$workspace/body.json" <<'EOF'
import json, sys
path, name, suffix, sub, tenant = sys.argv[1:]
p = json.load(open(path))
p["meta"]["name"] = name
p["subscription"].update(id=sub, tenantId=tenant)
p["naming"]["workload"] = suffix
p["resources"][0]["inputs"]["name"] = f"rg-{suffix}-dev-weu"
print(json.dumps({"project": p}))
EOF
curl -sS --fail-with-body -X PUT -H 'Content-Type: application/json' --data @"$workspace/body.json" \
  "$api/api/projects/$name" | json '"issues: %s" % d["issues"]'

if curl -sf "$api/api/backends/$sub" >/dev/null; then
  step "State backend already recorded"
else
  step "Bootstrapping the state backend (idempotent: reuses what already exists)"
  run=$(curl -sS --fail-with-body -X POST -H 'Content-Type: application/json' \
    --data "{\"location\": \"$location\", \"confirmSubscriptionId\": \"$sub\"}" \
    "$api/api/backends/$sub/bootstrap" | json 'd["runId"]')
  follow "$run"
fi
backend=$(curl -sSf "$api/api/backends/$sub" | json '"%s/%s" % (d["storageAccount"], d["container"])')
echo "$backend"

step "Planning"
run=$(curl -sS --fail-with-body -X POST -H 'Content-Type: application/json' --data "{\"subscriptionId\": \"$sub\"}" \
  "$api/api/projects/$name/runs/plan" | json 'd["runId"]')
follow "$run"
curl -sSf "$api/api/projects/$name/runs/current" >"$workspace/current.json"
json '"%s; guardrails: apply_allowed=%s" % (d["plan"]["summary"]["text"], d["plan"]["guardrails"]["apply_allowed"])' <"$workspace/current.json"
sha=$(json 'd["plan"]["planSha256"]' <"$workspace/current.json")

step "Applying the reviewed plan"
run=$(curl -sS --fail-with-body -X POST -H 'Content-Type: application/json' \
  --data "{\"planSha256\": \"$sha\", \"confirmName\": \"$name\", \"confirmDestroy\": false}" \
  "$api/api/projects/$name/runs/apply" | json 'd["runId"]')
follow "$run"

step "Checking the resource group exists"
az group show --name "rg-$suffix-dev-weu" --subscription "$sub" --query id --output tsv

step "Sandbox gate passed"
