#!/usr/bin/env python3
"""Vision Saccade Classifier - the image example as an Arduino App Lab app.

The sandbox holds five calibrated test scenes and never keeps a raw frame: it captures into a
volatile buffer and purges it at once. This app walks one scene through it:
  0x16 scene <0..4>, 0x10 capture, 0x11 classify, 0x14 ask the model broker what it sees,
  0x15 propose the scene's actuator, 0x12 status (with the model's answer once it arrives)
The camera itself is the Vision model's (vn8v), which needs a paid licence for the board: on a board
with the free licence the app says so, and everything else still runs.
"""

import json
import os
import time

from na8ve.app_bricks import ActPolicy, CognitiveOS, MemoryGraph, VisionSaccade, mount_na8ve_dashboards
from na8ve.app_bricks._ipc import EnclaveError

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OP_PING, OP_PROBE = 0x01, 0x02
OP_CAPTURE, OP_CLASSIFY, OP_STATUS = 0x10, 0x11, 0x12
OP_COGNITIVE_TURN, OP_ACTUATE, OP_SCENE = 0x14, 0x15, 0x16
SCENE = os.environ.get("NA8VE_IMAGE_SCENE", "1")  # 0 sprout, 1 indoor_plant, 2 bell_pepper, 3 ladybug, 4 lampshade


def vision() -> VisionSaccade:
    return VisionSaccade(
        model=os.environ.get("NA8VE_VISION_MODEL", "vn8v-tin66"),
        saccades=int(os.environ.get("NA8VE_SACCADE_COUNT", "8")),
        confidence_threshold=float(os.environ.get("NA8VE_CONFIDENCE_THRESHOLD", "0.25")),
    )


def run_cycle() -> dict:
    cog = CognitiveOS()
    dom = cog.load_pvm(
        path=os.path.join(HERE, "pvm", "app.n8pv"),
        manifest_path=os.path.join(HERE, "pvm", "manifest.bin"),
    )

    def call(op: int, payload: bytes = b"") -> str:
        return cog.call_pvm(dom=dom, op=op, payload=payload).decode("utf-8", "replace")

    steps = {
        "ping": call(OP_PING),
        "probe": call(OP_PROBE),
        "scene": call(OP_SCENE, SCENE.encode("ascii")),
        "capture": call(OP_CAPTURE),
        "classify": call(OP_CLASSIFY),
        "ask": call(OP_COGNITIVE_TURN),
        "actuate": call(OP_ACTUATE),
    }
    status = call(OP_STATUS)
    for _ in range(20):  # the broker's answer arrives between calls
        if "answer=pending" not in status:
            break
        time.sleep(0.5)
        status = call(OP_STATUS)
    steps["status"] = status

    # a look through the board's camera, where the board's licence includes the Vision model
    try:
        look = vision().look_once()
        camera = {"class": look.class_name, "confidence": round(look.confidence, 3), "saccades": look.saccades}
    except EnclaveError as exc:
        if not exc.code.startswith("CX_LIC_E_"):
            raise
        camera = {"unavailable": str(exc)}

    return {"app": "image", "sandbox": {"domain": dom, **steps}, "camera": camera}


if __name__ == "__main__":
    summary = run_cycle()
    print(json.dumps(summary, indent=2), flush=True)
    if os.environ.get("APP_HOME") and not os.environ.get("NA8VE_ONCE"):
        from arduino.app_bricks.web_ui import WebUI
        from arduino.app_utils import App

        mount_na8ve_dashboards(
            WebUI(),
            cognitive=CognitiveOS(),
            store=MemoryGraph(default_tier="sensory", max_hops=2),
            vision=vision(),
            act=ActPolicy(cooldown_ms=250),
            app_name="Vision Saccade Classifier",
            default_view="vision",
            extra_snapshot=lambda: summary,
        )
        App.run()
