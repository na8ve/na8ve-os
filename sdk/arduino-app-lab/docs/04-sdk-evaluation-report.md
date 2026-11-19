# 4. First-Time User Evaluation Report (`na8ve-os` Arduino App Lab SDK)

**Date:** 2026-11-14  
**Persona:** First-time developer using `sdk/arduino-app-lab` to run the starter app and build a new edge-AI app on an Arduino Uno Q running `na8ve-os`.  
**Scope:** End-to-end verification of documentation, starter project (`na8ve-developer-sdk/` and `na8ve-developer-sdk-applab.zip`), `arduino-app-cli` / App Lab container runtime, `na8ve.app_bricks` Python APIs, C sandbox tooling (`pvm/`), and `Arduino_RouterBridge` STM32U585 coprocessor actuation.

---

## Executive Summary

| Area | Status | Summary |
| :--- | :--- | :--- |
| **Pre-packaged `.zip` import & run** | **Pass (with warning)** | Sketch compiles and flashes cleanly (`21,378` B flash), container enters `running` state, all 4 Bricks return JSON results. Emits a `WARN [skip]` on `NA8VE_SACCADE_CROPS`. |
| **App lifecycle (`start` / `stop` / `NA8VE_ONCE`)** | **Pass (with quirk)** | `NA8VE_ONCE=1` works cleanly. Graceful `SIGTERM` exit (`ExitCode: 0`) on `app stop` causes `arduino-app-cli 0.8.4` to display status as `failed` instead of `stopped`. |
| **`CognitiveOS` (`load_pvm`, `call_pvm`, `turn`)** | **Partial** | `turn()` executes live inference (~0.77–2.28s) and returns `state_sha256`, but `.width` always reports `8` regardless of `"int16"`/`"int32"`. `load_pvm()` accepts missing/empty `manifest.bin`. |
| **`MemoryGraph` (`remember`, `recall`, `retract`)** | **Pass (doc mismatch)** | All 3 tiers, `limit`/`truncated`, and all 3 retraction classes work as expected. However, `recall().items` returns `list[dict]`, not `list[str]` as documented. |
| **`VisionSaccade` (`look_once`, `@on_classification`)** | **Partial** | Returns top-5 classification and fires registered callbacks, but `@vis.on_classification` returns `None` (binding the decorated symbol to `None`), `app.yaml` uses the wrong env var name, and repeated calls return identical `lampshade (0.381)` results. |
| **`ActPolicy` & `Arduino_RouterBridge` actuation** | **Gap / Doc mismatch** | Policy checks reject unlisted actuators (`CX_ACT_E_UNLISTED`) and reserved pins (`CX_ACT_E_RESERVED_PIN`), **but `act.propose()` does NOT dispatch to `sketch.ino`**, does not enforce `cooldown_ms`, and does not validate state names. Explicit `Bridge.call()` works end-to-end. |
| **Custom C Sandbox (`pvm/sdk_starter_app.c`)** | **Blocked** | No build/pack script in `sdk/arduino-app-lab/`; repo's `tools/build_app.py` fails to link `sdk_starter_app.c` due to `n8` vs `na8ve` Wasm import mismatch, and `na8ve-developer-sdk/pvm/` omits `manifest.bin`. |

**Overall Verdict:** As a **Python-only starter demo**, `na8ve-developer-sdk-applab.zip` boots and runs smoothly on the board. However, as a **developer SDK for building a new app from scratch**, a first-time user will hit immediate friction from documentation-vs-runtime mismatches (especially `ActPolicy` not bridging to the MCU, `MemoryGraph` return types, and `NA8VE_SACCADE_CROPS` vs `NA8VE_SACCADE_COUNT`) and cannot compile or sign custom C sandbox `.n8pv` / `manifest.bin` modules using the documented SDK files alone.

---

## 1. Test Environment Observed

- **Laptop Host:** Windows 11 with **Arduino App Lab 0.7.0**, `serial-discovery` (1.5.2), `mdns-discovery` (1.1.0), connected over USB ADB (`<unoq-device-serial>`).
  - *Note:* Arduino App Lab 0.7.0 was running on the desktop without an active `adb forward` tunnel in this session; all board-side App Lab operations were exercised directly against the exact `arduino-app-cli` (0.8.4) runtime and Docker container stack that Arduino App Lab drives.
- **Target Board:** Arduino Uno Q (`Linux TinyClaw 6.16.7 ... aarch64`, QRB2210 MPU + STM32U585 Cortex-M33 MCU).
- **Board Daemons Running:**
  - `arduino-app-cli daemon --port 8800` (v0.8.4)
  - `arduino-router` (`/var/run/arduino-router.sock` <-> `/dev/ttyHS1` at 115200 baud)
  - `na8ve-unoq-console --daemon --port 7878`
  - `na8ve-applab-daemon --sock /home/arduino/ArduinoApps/.na8ve-os-master.sock --db /var/na8ve/store/applab_store.db`
- **Container Image:** `ghcr.io/arduino/app-bricks/python-apps-base:0.8.0` (Python 3.13.9, with `na8ve.app_bricks` and `arduino.app_utils`).
- **Installed Bricks (`arduino-app-cli brick list`):**
  - `na8ve:cognitive_os` (`NA8VE_MODEL_NAME`, `NA8VE_EXEC_MODE`, `NA8VE_STATE_WIDTH`, `NA8VE_PVM_PATH`)
  - `na8ve:vision_saccade` (`NA8VE_VISION_MODEL`, `NA8VE_SACCADE_COUNT`, `NA8VE_CONFIDENCE_THRESHOLD`)
  - `na8ve:memory_graph` (`NA8VE_DEFAULT_TIER`, `NA8VE_MAX_RECALL_HOPS`)
  - `na8ve:act_policy` (`NA8VE_ACT_COOLDOWN_MS`)

---

## 2. Walkthrough of First-Time Developer Scenarios

### Scenario A: Running the Pre-Packaged Zip (`na8ve-developer-sdk-applab.zip`)

1. Verified the pre-installed `user:na8ve-developer-sdk-applab` files on the board match `na8ve-developer-sdk-applab.zip` byte-for-byte.
2. Started via `arduino-app-cli --log-level info app start user:na8ve-developer-sdk-applab`:
   - Immediately logged a configuration warning:
     ```text
     WARN [skip] variable does not exist into the brick definition variable=NA8VE_SACCADE_CROPS brick=na8ve:vision_saccade
     ```
   - Compiled `sketch/sketch.ino` (`arduino:zephyr` 0.54.1, `Arduino_RouterBridge` 0.3.0, `Arduino_LED_Matrix` 0.1.3): `21,378` bytes flash (2%), `5,076` bytes dynamic RAM (3%).
   - Flashed STM32U585 via OpenOCD and started `na8ve-developer-sdk-applab-main-1`.
3. Container `stdout` produced:
   ```json
   {
     "app": "na8ve-developer-sdk",
     "sandbox": { "domain_id": 2, "reply": "ok:sdk-starter:op=1" },
     "memory": { "recalled_count": 1, "truncated": false, "hopCapped": false, "fanOutClipped": false },
     "turn": { "model": "bx-1m-l2-t036", "mode": "recurrent", "width": 8, "latency_ms": 1057.1, "reply": "<call>{\"tool\":\"readings_latest\",\"subject\":\"green" },
     "vision": { "model": "vn8v-tin66", "saccades": 8, "top_class": "lampshade", "confidence": 0.381 },
     "actuation": {
       "fan": { "approved": true, "audit_seq": 1 },
       "matrix.glyph": { "approved": true, "audit_seq": 2 }
     }
   }
   ```
4. Stopped via `arduino-app-cli app stop user:na8ve-developer-sdk-applab`:
   - The Python `SIGTERM` loop in `docs/01` exited cleanly with `ExitCode: 0`, after which `arduino-app-cli app list` reported the app's status as **`failed`** instead of `stopped` (a `docker compose stop` / `arduino-app-cli 0.8.4` state-mapping quirk when a service exits `0`).

### Scenario B: Copying `na8ve-developer-sdk/` Directly (as Suggested in `README.md`)

`README.md` instructs users they can either import `na8ve-developer-sdk-applab.zip` *or* copy `na8ve-developer-sdk/` into their App Lab workspace.

- **Finding 1 (Missing `manifest.bin` & diverging `app.n8pv`):**  
  `na8ve-developer-sdk/pvm/` contains `app.n8pv`, `manifest.json`, `n8_sdk.h`, and `sdk_starter_app.c` — **there is no `manifest.bin`**, even though `python/main.py` passes `manifest_path=os.path.join(here, "pvm", "manifest.bin")`. Furthermore, `na8ve-developer-sdk/pvm/app.n8pv` (SHA-256 `e2db1398...`) is a different binary than the one inside `na8ve-developer-sdk-applab.zip` (SHA-256 `64819731...`).
- **Finding 2 (Silent acceptance of missing `manifest.bin`):**  
  When we copied `na8ve-developer-sdk/` to the board (`user:na8ve-sdk-eval-copy`) and started it, `cog.load_pvm("/app/pvm/app.n8pv", "/app/pvm/manifest.bin")` **did not fail** despite `manifest.bin` not existing on disk (nor when passed `manifest_path=""`). It admitted `domain_id=2` and returned `b"ok:sdk-starter:op=1"`.

### Scenario C: Building a New App from Scratch (`na8ve-eval-user-app`)

Pretending to be a first-time developer writing a new app from the documentation:

1. **CLI Scaffolding (`arduino-app-cli app new`):**  
   Running `arduino-app-cli app new na8ve-eval-user-app -b na8ve:cognitive_os -b na8ve:vision_saccade -b na8ve:memory_graph -b na8ve:act_policy` created `app.yaml` with `bricks: []` (the `-b` flags did not populate `app.yaml`), and generated `python/main.py` using `from arduino.app_utils import App; App.run(user_loop=loop)` rather than the `SIGTERM` loop in `docs/01`.
2. **Brick Variable Fix:**  
   Replacing `NA8VE_SACCADE_CROPS: '8'` (from `docs/01` and starter `app.yaml`) with `NA8VE_SACCADE_COUNT: '8'` (matching `arduino-app-cli brick details na8ve:vision_saccade` and `vision_saccade.py`) completely eliminated the `WARN [skip]` message on startup.
3. **End-to-End Coprocessor Actuation Test (`ActPolicy` vs `Arduino_RouterBridge`):**  
   We added call counters (`g_fan_calls`, `g_light_calls`, `g_glyph_calls`) and a `Bridge.provide("get_counts", ...)` RPC in `sketch/sketch.ino` to verify whether `act.propose(...)` triggers the microcontroller handlers as described in `docs/03`:
   - `counts_before`: `"fan=0,light=0,glyph=0"`
   - After `act.propose("fan", "low")`, `act.propose("light", "on")`, `act.propose("matrix.glyph", "ok")` (all returned `approved: true`, `reason: "cx_act policy approved"`):
     - `counts_after_act_propose`: **`"fan=0,light=0,glyph=0"`**
   - After calling `Bridge.call("fan", "low")`, `Bridge.call("light", "on")`, `Bridge.call("matrix.glyph", "ok")` explicitly via `arduino.app_utils.Bridge`:
     - `counts_after_bridge_call`: **`"fan=1,light=1,glyph=1"`** (and incremented to `"fan=2,light=2,glyph=2"` on a subsequent `NA8VE_ONCE=1` run).

   **Key Takeaway:** `ActPolicy.propose()` currently acts as a policy/audit check inside `na8ve-applab-daemon` only; it does **not** forward approved commands over `Arduino_RouterBridge` to `sketch.ino`. Developers must currently import `Bridge` from `arduino.app_utils` and issue `Bridge.call(...)` themselves after `act.propose(...)` approves.

4. **One-Shot CLI Testing (`NA8VE_ONCE=1`) & Zip Import/Export:**  
   - `docker exec -e NA8VE_ONCE=1 <container> python3 /app/python/main.py` ran cleanly and exited immediately as documented in `docs/01`.
   - `arduino-app-cli app export` produces a nested archive (`<app-name>/app.yaml`, etc.), whereas `na8ve-developer-sdk-applab.zip` uses a flat layout (`app.yaml` at archive root). `arduino-app-cli app import` accepted both layouts cleanly.

---

## 3. Detailed Brick & Sandbox API Findings

### 3.1 `CognitiveOS` (`na8ve:cognitive_os`)

- **`cog.turn(prompt, max_bytes=48)`:**
  - Tested `mode` in `{"recurrent", "window"}` and `width` in `{"int8", "int16", "int32"}`.
  - Latency was ~`770 ms` (`max_bytes=32`) to `~2250 ms` (`max_bytes=48`), returning unique `state_sha256` digests per call and live byte-level model output.
  - **Issue:** `TurnResult.width` always returned integer `8` even when `width="int16"` or `width="int32"` was passed. (`docs/02` lists `.width` as `str / int`, whereas `cognitive_os.py` types it as `int` and `na8ve-applab-daemon` hardcodes `"width":8` in its JSON response.)
  - **Doc omission:** `TurnResult` also includes `.proposed_act`, and `CognitiveOS` exposes `.register_action()` and `.execute()` (for `App.run()`), none of which appear in `docs/02`.
- **`cog.load_pvm(path, manifest_path)` & `cog.call_pvm(dom, op, payload)`:**
  - `op=1` returned `b"ok:sdk-starter:op=1"`.
  - `op=0x20` (`OP_SENSOR_TICK` in `sdk_starter_app.c`) with a 16-byte packed `sensor_packet_t` returned `b"ok:sdk-starter:op=32"` (note: `sdk_starter_app.c` specifies `n8_reply_str("ok:sdk-starter:sensor_tick")`, and its `pvm_main` only handles `op == 1`).
  - `op=99` raised `EnclaveError: CX_DOM_QUARANTINED: Stage-2 MMU bounds fault contained`.
  - Missing `.n8pv` path raised `EnclaveError: CX_OS_E_IO: Failed to stage .n8pv into root-only staging directory`.
  - Missing or empty `manifest_path` did not raise an error.

### 3.2 `MemoryGraph` (`na8ve:memory_graph`)

- Tested `remember()` across `"sensory"`, `"episodic"`, and `"semantic"` tiers, returning integer IDs (`10543`–`10545`).
- Tested `recall(query, limit=2)` with 3 matches: returned 2 items with `truncated=True`, `hopCapped=False`, `fanOutClipped=False`.
- Tested `retract()` with `"standard"`, `"instant-undo"`, and `"forensic"`: each returned a new `state_sha256` and removed the item from subsequent `recall()` queries.
- **Doc mismatch:** `docs/02` states `RecallResult.items` is `list[str]`. In reality, it is `list[dict]` (e.g., `{'id': 10545, 'tier': 'semantic', 'text': '...', 'importance': 0.7}`). Calling string methods directly on `recalled.items[0]` raises `AttributeError`.

### 3.3 `VisionSaccade` (`na8ve:vision_saccade`)

- `look_once()` executed in ~`422–426 ms` (via daemon; `480 ms` directly on `na8ve-unoq-console` TCP `7878`) and returned `VisionLookResult` with `saccades=8`, `class_name='lampshade'`, `confidence=0.381`, and `top5`.
- **Observations / Gaps:**
  - Repeated calls across different containers and direct `os-vision once` queries returned identical fixed scores (`lampshade: 0.381, candle: 0.104, jellyfish: 0.059, drumstick: 0.037, flagpole: 0.036`), which also appear as a literal string in `/usr/local/bin/na8ve-applab-daemon`.
  - `@vis.on_classification`: In `vision_saccade.py`, `on_classification()` returns `None` instead of the decorated function. Using `@vis.on_classification` as a Python decorator (as shown in `docs/02`) registers the callback (it fired twice during testing), but rebinds the decorated function variable to `None`.
  - `app.yaml` and `docs/01` use `NA8VE_SACCADE_CROPS`, whereas `vision_saccade.py` and the installed brick schema read `NA8VE_SACCADE_COUNT`.

### 3.4 `ActPolicy` (`na8ve:act_policy`)

- Tested `act.propose()` and `act.status()` (undocumented method returning `fan`, `light`, `buzzer`, `matrix.glyph` and `reserved_pins: "7..21,26..42,47..48"`):
  - **Enforced:** Unlisted actuators (`act.propose("servo", "90")`, `"21"`) raise `CX_ACT_E_UNLISTED`. Reserved pin names (`"gpio21"`, `"GPIO21"`, `"pin21"`, `"reserved"`, `"sd_cs"`, `"gpio42"`) raise `CX_ACT_E_RESERVED_PIN`.
  - **Not enforced:**
    1. **Cooldown (`cooldown_ms=250`):** Two back-to-back calls to `act.propose("fan", "low")` within <10 ms both returned `approved=True` (`audit_seq` 10 and 11).
    2. **State validation:** `act.propose("fan", "turbo")` returned `approved=True` even though `act.status()` lists allowed states as `["off", "low", "high"]`.
    3. **Router dispatch:** As shown in Scenario C, approved proposals are not sent to `Arduino_RouterBridge` automatically.

### 3.5 Custom C Sandbox Authoring (`pvm/sdk_starter_app.c` & `pvm/n8_sdk.h`)

A developer following `docs/02` to modify `pvm/sdk_starter_app.c` and recompile `pvm/app.n8pv` + `pvm/manifest.bin` hits a dead end:

1. **No build instructions or packaging tool in `sdk/arduino-app-lab/`:** There is no Makefile, script, or documentation explaining how to compile `.c` -> `.n8pv` or `manifest.json` -> `manifest.bin` (`N8MF` 76-byte format).
2. **Incompatible with parent repo's `tools/build_app.py`:** Running `python tools/build_app.py --name sdk-starter --src sdk/arduino-app-lab/na8ve-developer-sdk/pvm/sdk_starter_app.c --out <dir>` fails at `wasm-ld`:
   ```text
   wasm-ld: error: import name mismatch for symbol: n8_reply
   >>> defined as n8_reply in sdk_starter_app.o
   >>> defined as reply in n8_util.o
   wasm-ld: error: import module mismatch for symbol: n8_reply
   >>> defined as n8 in sdk_starter_app.o
   >>> defined as na8ve in n8_util.o
   ```
   `pvm/n8_sdk.h` declares imports under module `"n8"` (`n8_reply`, `n8_log`, `n8_ipc_send`, `n8_store_query`), whereas the repo runtime (`sdk/src/n8_util.c` and `sdk/src/n8_imports.txt`) uses module `"na8ve"` (`reply`, `log`, `ipc_send`, `store_query`).
3. **Incompatible manifest format:** `pvm/manifest.json` uses `{"dom_id": 2, "budget_ms": 50, "mem_bytes": 65536, "grants": ["store", "act"], "allowed_ipc": [1]}` matching the 76-byte `N8MF` `manifest.bin` in the zip, which differs from the parent repo's `tools/build_manifest.py` schema.

---

## 4. Recommended Fixes (Prioritized)

1. **Fix `ActPolicy` -> `Arduino_RouterBridge` integration (or update `docs/03`):** Either have `na8ve-applab-daemon` dispatch approved proposals over `/var/run/arduino-router.sock` (and enforce `cooldown_ms` and allowed `states`), or document that developers must call `arduino.app_utils.Bridge.call(target, state)` after `act.propose(target, state)` approves.
2. **Align `NA8VE_SACCADE_COUNT` across docs and starter `app.yaml`:** Update `sdk/arduino-app-lab/na8ve-developer-sdk/app.yaml` and `docs/01-getting-started-arduino-app-lab.md` from `NA8VE_SACCADE_CROPS` to `NA8VE_SACCADE_COUNT` (and rebuild `na8ve-developer-sdk-applab.zip`).
3. **Sync `na8ve-developer-sdk/pvm/` with `na8ve-developer-sdk-applab.zip`:** Include `manifest.bin` in `na8ve-developer-sdk/pvm/` and ensure `app.n8pv` matches the zip so copying `na8ve-developer-sdk/` works identically.
4. **Fix `docs/02` API discrepancies:**
   - Document `RecallResult.items` as `list[dict]` (`{"id", "tier", "text", "importance"}`) rather than `list[str]`.
   - Fix `VisionSaccade.on_classification` to return `callback` so `@vis.on_classification` works as a true decorator (or document it as `vis.on_classification(fn)`).
   - Document `ActPolicy.status()`, `TurnResult.proposed_act`, and `App.run()` compatibility hooks (`CognitiveOS.execute`, `VisionSaccade.loop`).
5. **Provide a self-contained C sandbox build/manifest guide or tool (or mark C `.n8pv` authoring as preview):** Document the standalone `clang`/`zig` command for `n8_sdk.h` (`import_module("n8")`) and provide a packager for the 76-byte `N8MF` `manifest.bin` + 52-byte-header `N8PV` format, or note how developer signing keys are provisioned on the board.
6. **Investigate `arduino-app-cli` `failed` status on clean stop & `TurnResult.width`:** Consider exiting with the `App.run()` lifecycle pattern or documenting why `app stop` transitions `ExitCode: 0` containers to `failed` in `arduino-app-cli 0.8.4`, and return the configured width (`8`/`16`/`32`) from `na8ve-applab-daemon` for `CognitiveOS.turn()`.

