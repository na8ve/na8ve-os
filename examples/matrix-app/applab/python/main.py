#!/usr/bin/env python3
"""LED Matrix Cognitive Visualizer - the matrix example as an Arduino App Lab app.

The sandbox asks the model broker a question and lays the answer out for the 12x8 LED matrix:
  op 0x10 prompt <text> -> "ok queued"      op 0x11 status -> "text <answer> | stream i/n"
  op 0x14 stream all    -> each character proposed as a matrix glyph to the actuator policy table
  op 0x15 frame         -> the current 12x8 frame as text
The answer then scrolls on the board's LED matrix through the coprocessor sketch (sketch/sketch.ino,
its Bridge "scroll" handler). The dashboard on port 7000 asks the same model.
"""

import json
import os
import time

from na8ve.app_bricks import ActPolicy, CognitiveOS, MemoryGraph, mount_na8ve_dashboards

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OP_PING, OP_PROMPT, OP_STATUS, OP_STREAM_ALL, OP_FRAME = 0x01, 0x10, 0x11, 0x14, 0x15
PROMPT = os.environ.get("NA8VE_MATRIX_PROMPT", "Greet the greenhouse in one short line.")


def cognitive() -> CognitiveOS:
    return CognitiveOS(
        model=os.environ.get("NA8VE_MODEL_NAME", "bx-1m-l2-t036"),
        mode=os.environ.get("NA8VE_EXEC_MODE", "recurrent"),
        width=os.environ.get("NA8VE_STATE_WIDTH", "int32"),
    )


def to_matrix(text: str) -> str:
    """Scrolls the text on the LED matrix; the sketch's Bridge is there only when App Lab runs the app."""
    try:
        from arduino.app_utils import Bridge
    except ImportError:
        return "no bridge (not running under App Lab)"
    try:
        Bridge.call("scroll", text)
        return "scrolling"
    except Exception as exc:  # the coprocessor sketch not flashed or not answering
        return f"bridge: {exc}"


def run_cycle() -> dict:
    cog = cognitive()
    dom = cog.load_pvm(
        path=os.path.join(HERE, "pvm", "app.n8pv"),
        manifest_path=os.path.join(HERE, "pvm", "manifest.bin"),
    )

    def call(op: int, payload: bytes = b"") -> str:
        return cog.call_pvm(dom=dom, op=op, payload=payload).decode("utf-8", "replace")

    ping = call(OP_PING)
    asked = call(OP_PROMPT, PROMPT.encode("utf-8"))
    status = call(OP_STATUS)
    for _ in range(20):  # the broker's answer arrives between calls
        if status != "pending":
            break
        time.sleep(0.5)
        status = call(OP_STATUS)
    text = status[5:].split(" | stream ", 1)[0] if status.startswith("text ") else ""
    streamed = call(OP_STREAM_ALL) if text else ""
    frame = call(OP_FRAME) if text else ""
    return {
        "app": "matrix",
        "sandbox": {"domain": dom, "ping": ping, "asked": asked, "status": status, "streamed": streamed},
        "frame": frame,
        "led_matrix": to_matrix(text) if text else "nothing to show",
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
            act=ActPolicy(cooldown_ms=int(os.environ.get("NA8VE_ACT_COOLDOWN_MS", "100"))),
            app_name="LED Matrix Cognitive Visualizer",
            default_view="dashboard",
            extra_snapshot=lambda: summary,
        )
        App.run()
