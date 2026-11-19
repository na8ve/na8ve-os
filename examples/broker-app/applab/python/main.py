#!/usr/bin/env python3
"""Inter-Sandbox Model Broker - the broker example as an Arduino App Lab app.

The sandbox never touches the model. It asks the model broker (pVM 1) over IPC, the only target
its manifest allows, and the broker answers it with the board's own turn:
  op 0x10 ask <question>  -> "ok queued" (or "ERR busy" / "ERR size" / "ERR gate")
  op 0x11 answer          -> the answer, "pending", or "nothing asked"
The dashboard on port 7000 asks the same model directly.
"""

import json
import os
import time

from na8ve.app_bricks import CognitiveOS, MemoryGraph, mount_na8ve_dashboards

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OP_PING = 0x01
OP_ASK = 0x10
OP_ANSWER = 0x11
QUESTION = os.environ.get("NA8VE_BROKER_QUESTION", "Should the greenhouse fan run at 30 C and 85 % humidity?")


def cognitive() -> CognitiveOS:
    return CognitiveOS(
        model=os.environ.get("NA8VE_MODEL_NAME", "bx-1m-l2-t036"),
        mode=os.environ.get("NA8VE_EXEC_MODE", "recurrent"),
        width=os.environ.get("NA8VE_STATE_WIDTH", "int32"),
    )


def run_cycle() -> dict:
    cog = cognitive()
    dom = cog.load_pvm(
        path=os.path.join(HERE, "pvm", "app.n8pv"),
        manifest_path=os.path.join(HERE, "pvm", "manifest.bin"),
    )

    def call(op: int, payload: bytes = b"") -> str:
        return cog.call_pvm(dom=dom, op=op, payload=payload).decode("utf-8", "replace")

    ping = call(OP_PING)
    asked = call(OP_ASK, QUESTION.encode("utf-8"))
    answer = call(OP_ANSWER)
    for _ in range(20):  # the broker answers between calls; a busy model can take a moment
        if answer != "pending":
            break
        time.sleep(0.5)
        answer = call(OP_ANSWER)
    return {
        "app": "broker",
        "sandbox": {"domain": dom, "ping": ping},
        "question": QUESTION,
        "asked": asked,
        "answer": answer,
    }


if __name__ == "__main__":
    summary = run_cycle()
    print(json.dumps(summary, indent=2), flush=True)
    if os.environ.get("APP_HOME") and not os.environ.get("NA8VE_ONCE"):
        from arduino.app_bricks.web_ui import WebUI
        from arduino.app_utils import App

        mount_na8ve_dashboards(
            WebUI(),
            cognitive=cognitive(),
            store=MemoryGraph(default_tier="episodic", max_hops=2),
            app_name="Inter-Sandbox Model Broker",
            default_view="dashboard",
            extra_snapshot=lambda: summary,
        )
        App.run()
