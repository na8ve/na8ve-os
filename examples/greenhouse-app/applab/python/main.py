#!/usr/bin/env python3
"""Smart Greenhouse Reflex Agent - the greenhouse example as an Arduino App Lab app.

1. Admits the example's sandbox (pvm/app.n8pv + pvm/manifest.bin): its signature covers the code
   and the manifest, so the board runs exactly what was signed, with exactly its grants.
2. Calls it: a ping, then a sensor tick (op 0x20). On a hot, humid, dry reading the sandbox itself
   proposes the fan and the mister, which the board's actuator policy table decides.
3. Asks the board's model about the same reading, with the greenhouse's facts in memory.
4. Serves the dashboard on port 7000: its chat is the same board turn.
5. Shows on the LED matrix what the dashboard shows: it reads the dashboard's own stream and sends
   each new line to the coprocessor sketch (sketch/sketch.ino), which scrolls it.
"""

import json
import os
import struct
import threading
import time
import urllib.request

from na8ve.app_bricks import ActPolicy, CognitiveOS, MemoryGraph, mount_na8ve_dashboards
from na8ve.app_bricks._ipc import EnclaveError

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OP_PING = 0x01
OP_SENSOR_TICK = 0x20
PORT = 7000
READING = {"temp_c": 30.0, "rh": 85.0, "soil_adc": 1000, "lux": 420}

FACTS = (
    ("semantic", "bed-1 grows basil and tomatoes; the fan ventilates the greenhouse", 0.8),
    ("semantic", "the mister wets the rootzone when the soil reads dry", 0.8),
    ("episodic", "bed-1 read 30.0 C and 85 % humidity with a dry soil reading", 0.7),
)


def cognitive() -> CognitiveOS:
    return CognitiveOS(
        model=os.environ.get("NA8VE_MODEL_NAME", "bx-1m-l2-t036"),
        mode=os.environ.get("NA8VE_EXEC_MODE", "recurrent"),
        width=os.environ.get("NA8VE_STATE_WIDTH", "int32"),
    )


def run_cycle() -> dict:
    cog = cognitive()
    mem = MemoryGraph(default_tier="semantic", max_hops=2)

    dom = cog.load_pvm(
        path=os.path.join(HERE, "pvm", "app.n8pv"),
        manifest_path=os.path.join(HERE, "pvm", "manifest.bin"),
    )
    ping = cog.call_pvm(dom=dom, op=OP_PING).decode("utf-8", "replace")

    # temperature and humidity in hundredths, the soil sensor's raw reading, light in lux
    reading = struct.pack("<iiii", round(READING["temp_c"] * 100), round(READING["rh"] * 100),
                          READING["soil_adc"], READING["lux"])
    tick = cog.call_pvm(dom=dom, op=OP_SENSOR_TICK, payload=reading).decode("utf-8", "replace")

    for tier, text, importance in FACTS:
        mem.remember(text, tier=tier, importance=importance)
    recall = mem.recall("bed-1", limit=4, max_hops=2)

    try:
        turn = cog.turn("Bed-1 reads 30 C, 85 % humidity and dry soil. Should the fan run?", max_bytes=96)
        answer = {"reply": turn.reply, "model": turn.model, "latency_ms": round(turn.latency_ms, 1)}
    except EnclaveError as exc:
        # no licence for the model, or no model on the board yet (its copy comes with its licence)
        if not exc.code.startswith(("CX_LIC_E_", "CX_MODEL_E_")):
            raise
        answer = {"reply": "", "unavailable": str(exc)}

    return {
        "app": "greenhouse",
        "reading": READING,
        "sandbox": {"domain": dom, "ping": ping, "sensor_tick": tick},
        "memory": {"recalled": len(recall.items), "truncated": recall.truncated},
        "answer": answer,
    }


def matrix_line(event: dict) -> str:
    """One event of the dashboard's stream, in the words the 12x8 matrix scrolls."""
    if not event.get("ok"):
        return "enclave " + str(event.get("err", "offline"))[:40]
    parts = []
    reading = (event.get("extra") or {}).get("reading")
    if reading:
        parts.append(f"{reading['temp_c']:.1f}C {reading['rh']:.0f}%RH")
    for act in event.get("actuators", []):
        parts.append(f"{act.get('name')} {act.get('state')}")
    parts.append(f"audit {(event.get('telemetry') or {}).get('audit_seq', 0)}")
    return " | ".join(parts)


def stream_to_matrix() -> None:
    """Follows the dashboard's own event stream and sends the matrix each line that differs."""
    from arduino.app_utils import Bridge

    last = None
    while True:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/stream", timeout=30) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    text = matrix_line(json.loads(line[5:]))
                    if text != last:
                        Bridge.call("show", text)
                        print(f"matrix: {text}", flush=True)
                        last = text
        except Exception as exc:  # the dashboard not up yet, or the sketch not answering
            print(f"matrix stream: {exc}", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    summary = run_cycle()
    print(json.dumps(summary, indent=2), flush=True)
    if os.environ.get("APP_HOME") and not os.environ.get("NA8VE_ONCE"):
        from arduino.app_bricks.web_ui import WebUI
        from arduino.app_utils import App

        mount_na8ve_dashboards(
            WebUI(),
            cognitive=cognitive(),
            store=MemoryGraph(default_tier="semantic", max_hops=2),
            act=ActPolicy(cooldown_ms=int(os.environ.get("NA8VE_ACT_COOLDOWN_MS", "200"))),
            app_name="Smart Greenhouse Reflex Agent",
            default_view="dashboard",
            extra_snapshot=lambda: summary,
        )
        threading.Thread(target=stream_to_matrix, name="matrix-stream", daemon=True).start()
        App.run()
