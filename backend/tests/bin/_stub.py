"""Stand-in for conftest, checkov and trivy in tests: replays recorded real output.

LOWDEVOPS_STUB_DIR picks the fixture dir holding <tool>.json (default: the clean fixture).
LOWDEVOPS_STUB_MODE: garbage prints non-JSON, wrong-shape prints {}, crash exits 3, hang never
finishes. LOWDEVOPS_STUB_LOG gets argv and which scanner config variables were visible.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

CLEAN = Path(__file__).resolve().parents[1] / "fixtures" / "guardrails" / "clean"


def main(tool: str) -> int:
    log = os.environ.get("LOWDEVOPS_STUB_LOG")
    if log:
        with open(log, "a") as f:
            config = sorted(k for k in os.environ if k.startswith(("TRIVY_", "CKV_", "CONFTEST_")))
            f.write(
                json.dumps([tool, *sys.argv[1:], f"env:{','.join(config)}", os.getcwd()]) + "\n"
            )
    mode = os.environ.get("LOWDEVOPS_STUB_MODE", "")
    if mode == "crash":
        print(f"{tool}: simulated crash", file=sys.stderr)
        return 3
    if mode == "garbage":
        print("this is not JSON")
        return 0
    if mode == "wrong-shape":  # what Checkov/Trivy print for a plan they could not read
        print("{}")
        return 0
    if mode == "hang":  # starts a worker, then never finishes; the timeout must kill both
        child = subprocess.Popen(["sleep", "300"])  # noqa: S607
        Path(os.environ["LOWDEVOPS_STUB_LOG"] + ".child").write_text(str(child.pid))
        time.sleep(300)
    source = Path(os.environ.get("LOWDEVOPS_STUB_DIR", CLEAN)) / f"{tool}.json"
    sys.stdout.write(source.read_text())
    return 0
