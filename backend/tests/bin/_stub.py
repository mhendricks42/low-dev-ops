"""Stand-in for conftest, checkov and trivy in tests: replays recorded real output.

LOWDEVOPS_STUB_DIR picks the fixture dir holding <tool>.json (default: the clean fixture).
LOWDEVOPS_STUB_MODE=garbage prints non-JSON; =crash exits 3. LOWDEVOPS_STUB_LOG gets argv.
"""

import json
import os
import sys
from pathlib import Path

CLEAN = Path(__file__).resolve().parents[1] / "fixtures" / "guardrails" / "clean"


def main(tool: str) -> int:
    log = os.environ.get("LOWDEVOPS_STUB_LOG")
    if log:
        with open(log, "a") as f:
            f.write(json.dumps([tool, *sys.argv[1:], os.getcwd()]) + "\n")
    mode = os.environ.get("LOWDEVOPS_STUB_MODE", "")
    if mode == "crash":
        print(f"{tool}: simulated crash", file=sys.stderr)
        return 3
    if mode == "garbage":
        print("this is not JSON")
        return 0
    source = Path(os.environ.get("LOWDEVOPS_STUB_DIR", CLEAN)) / f"{tool}.json"
    sys.stdout.write(source.read_text())
    return 0
