#!/usr/bin/env python3
"""Barebone na8ve-os Developer SDK starter app for Arduino App Lab."""

import json
import os
import signal
import time
from na8ve.app_bricks import (
    ActPolicy,
    CognitiveOS,
    MemoryGraph,
    VisionSaccade,
    mount_na8ve_dashboards,
)
from na8ve.app_bricks._ipc import EnclaveError


def main() -> dict:
    cog = CognitiveOS(
        model=os.environ.get("NA8VE_MODEL_NAME", "bx-1m-l2-t036"),
        mode=os.environ.get("NA8VE_EXEC_MODE", "recurrent"),
        width=os.environ.get("NA8VE_STATE_WIDTH", "int32"),
    )
    mem = MemoryGraph(default_tier="episodic", max_hops=2)
    vis = VisionSaccade(
        model=os.environ.get("NA8VE_VISION_MODEL", "vn8v-tin66"),
        saccades=8,
        confidence_threshold=0.25,
    )
    act = ActPolicy(cooldown_ms=250)

    # 1. Load & invoke the sandbox module (pvm/app.n8pv + pvm/manifest.bin)
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dom = cog.load_pvm(
        path=os.path.join(here, "pvm", "app.n8pv"),
        manifest_path=os.path.join(here, "pvm", "manifest.bin"),
    )
    pvm_reply = cog.call_pvm(dom=dom, op=1, payload=b"ping").decode("utf-8", errors="replace")

    # 2. Three-tier Memory Graph: write, bounded recall, and retraction
    mid = mem.remember("sdk_demo: sensor temp=26.4C humidity=84%", tier="sensory", importance=0.60)
    recalled = mem.recall("sdk_demo", limit=4, max_hops=2)
    mem.retract(mid, retraction_class="standard")

    # 3. Recurrent byte-level cognitive turn
    turn_res = cog.turn("Sensor humidity is 84% at 26.4C. Next action:", max_bytes=48)

    # 4. 8-saccade vision pass. The Vision model needs a paid licence for the board: with the free
    #    licence the enclave refuses it, and the app reports that instead of stopping
    try:
        look_res = vis.look_once()
        vision = {
            "model": look_res.model,
            "saccades": look_res.saccades,
            "top_class": look_res.class_name,
            "confidence": round(look_res.confidence, 3),
        }
    except EnclaveError as exc:
        if not exc.code.startswith("CX_LIC_E_"):
            raise
        vision = {"unavailable": str(exc)}

    # 5. Policy-gated actuation proposals
    act_fan = act.propose("fan", "low")
    act_matrix = act.propose("matrix.glyph", "ok")

    return {
        "app": "na8ve-developer-sdk",
        "sandbox": {"domain_id": dom, "reply": pvm_reply},
        "memory": {
            "recalled_count": len(recalled.items),
            "truncated": recalled.truncated,
            "hopCapped": recalled.hopCapped,
            "fanOutClipped": recalled.fanOutClipped,
        },
        "turn": {
            "model": turn_res.model,
            "mode": turn_res.mode,
            "width": turn_res.width,
            "latency_ms": round(turn_res.latency_ms, 1),
            "reply": turn_res.reply,
        },
        "vision": vision,
        "actuation": {
            "fan": {"approved": act_fan.approved, "audit_seq": act_fan.audit_seq},
            "matrix.glyph": {"approved": act_matrix.approved, "audit_seq": act_matrix.audit_seq},
        },
    }


if __name__ == "__main__":
    summary = main()
    print(json.dumps(summary, indent=2), flush=True)
    if os.environ.get("APP_HOME") and not os.environ.get("NA8VE_ONCE"):
        from arduino.app_bricks.web_ui import WebUI
        from arduino.app_utils import App

        ui = WebUI()
        mount_na8ve_dashboards(
            ui,
            cognitive=CognitiveOS(
                model=os.environ.get("NA8VE_MODEL_NAME", "bx-1m-l2-t036"),
                mode=os.environ.get("NA8VE_EXEC_MODE", "recurrent"),
                width=os.environ.get("NA8VE_STATE_WIDTH", "int32"),
            ),
            store=MemoryGraph(default_tier="episodic", max_hops=2),
            vision=VisionSaccade(
                model=os.environ.get("NA8VE_VISION_MODEL", "vn8v-tin66"),
                saccades=8,
                confidence_threshold=0.25,
            ),
            act=ActPolicy(cooldown_ms=250),
            app_name="na8ve-os Developer SDK",
            default_view="dashboard",
            extra_snapshot=lambda: summary,
        )
        App.run()
