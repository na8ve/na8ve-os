# na8ve-os Developer SDK

A minimal starter app for building autonomous, offline edge AI applications on **na8ve-os** inside **Arduino App Lab**.

`na8ve-os` runs an on-device recurrent byte-level neural engine, a bounded three-tier graph memory store (`sensory`, `episodic`, `semantic`), and sandboxed application modules inside isolated execution domains. Models never drive GPIO pins directly; physical actions are mediated by `act_policy` before reaching `/var/run/arduino-router.sock` and the microcontroller bridge.

> **Editions & Keys:** On **Community Beta 1M** (`na8ve-os-unoq`, free WebUSB on **Firmware**), **`bx-1m-l2-t036` (`int32`)** is active. To run **2M (`bx-2m-t035`)** and **Vision (`vn8v-tin66`)** alongside custom `.n8pv` modules signed by your workstation key (`~/.na8ve/app-key.pem`), provision your board with the **`$69.00` Purchase Licence Key (`N8LC`)** flow on **Firmware** (`na8ve-os-unoq-preflashed`) or order factory pre-flashed hardware in the **Shop** (`NA8-UNOQ-PRE` `$149.00` or `NA8-DUO-BUNDLE` `$185.00`, `10 Day Backorder`). See [../README.md](../README.md).

---

## Project Layout

| Path | Purpose |
| :--- | :--- |
| `app.yaml` | App metadata and `na8ve:*` Brick configuration (`cognitive_os`, `vision_saccade` with `NA8VE_SACCADE_COUNT`, `memory_graph`, `act_policy`). |
| `python/main.py` | Barebone Python starter calling all four `na8ve.app_bricks` subsystems. |
| `pvm/app.n8pv`, `pvm/manifest.bin` | Compiled sandbox application module and 76-byte capability manifest loaded at runtime. |
| `pvm/sdk_starter_app.c`, `pvm/n8_sdk.h`, `pvm/manifest.json` | Local C sandbox source template (stripped automatically when packaging with `tools/na8ve_applab_tool.py pack`). |
| `sketch/sketch.ino`, `sketch/sketch.yaml` | Coprocessor sketch registering `"fan"`, `"light"`, and `"matrix.glyph"` handlers via `Arduino_RouterBridge`. |

---

## Python Brick APIs (`na8ve.app_bricks`)

```python
from na8ve.app_bricks import ActPolicy, CognitiveOS, MemoryGraph, VisionSaccade

cog = CognitiveOS(model="bx-1m-l2-t036", mode="recurrent", width="int32")
mem = MemoryGraph(default_tier="episodic", max_hops=2)
vis = VisionSaccade(model="vn8v-tin66", saccades=8, confidence_threshold=0.25)
act = ActPolicy(cooldown_ms=250)
```

- **Sandboxed App Module**: `dom = cog.load_pvm(path, manifest_path)` and `cog.call_pvm(dom=dom, op=1, payload=b"ping")` (or `op=0x20` for `OP_SENSOR_TICK`)
- **Cognitive Turn**: `res = cog.turn(prompt, max_bytes=64)` (`res.reply`, `res.width`, `res.latency_ms`, `res.state_sha256`, `res.proposed_act`)
- **Three-Tier Memory Graph**: `mem.remember(text, tier="episodic" | "sensory" | "semantic", importance=0.8)`, `mem.recall(query, limit=4, max_hops=2)` (returns `RecallReport.items: list[dict]` plus `.truncated`, `.hopCapped`, `.fanOutClipped`), and `mem.retract(memory_id, retraction_class="standard")`
- **Vision Saccade**: `vis.look_once()` and `@vis.on_classification` decorator
- **Policy-Gated Actuation**: `act.propose("fan", "low")` / `act.propose("light", "on")` / `act.propose("matrix.glyph", "ok")` and `act.status()`

---

## Building & Running in Arduino App Lab

1. To recompile and package after modifying `pvm/sdk_starter_app.c`:

   ```bash
   python ../tools/na8ve_applab_tool.py pack \
     --app-dir . \
     --key ~/.na8ve/app-key.pem \
     --out ../na8ve-developer-sdk-applab.zip
   ```

2. Import the verified `.zip` (or copy this folder) into Arduino App Lab and click **Run** to load the sandbox module, write and recall memories, run a recurrent turn, evaluate an 8-saccade vision pass, and dispatch policy-approved coprocessor actions.
