# 3. SDK Verification Report (ESP32-S3 Arduino IDE)

**Verification Date:** 2026-11-14  
**Package:** `sdk/arduino-ide/na8ve_developer_sdk` + Boards Manager platform `na8ve:esp32s3` v`1.0.0`  
**Target Hardware:** Seeed XIAO ESP32-S3 Sense (`na8ve:esp32s3:xiao_esp32s3_na8ve`, USB `0x303A:0x1001`, `COM7`)  
**Toolchain:** Arduino CLI (`arduino-cli`), bundled `zig` WebAssembly toolchain via `na8ve-zig`, host C++ test runner, Python 3

---

## 1. Summary

All issues surfaced in the initial first-time developer walkthrough have been resolved and re-verified on live Seeed XIAO ESP32-S3 Sense hardware (`COM7`):

- **Self-contained toolchain:** `na8ve-arduino-tool.cmd`, `na8ve_arduino_tool.py`, and its packaging helpers are bundled inside the `na8ve:esp32s3` platform directory and resolve `cores/`, `variants/`, and `libraries/` relative to the installed platform folder with zero external repository dependencies.
- **Reliable parallel `--clean` builds on Windows:** `platform.txt` invokes Zig through `tools/na8ve-zig.cmd` / `na8ve_zig.py`, serializing Zig cache access with a non-blocking OS file lock so multi-core `--clean` compiles complete cleanly without `-j 1`.
- **Unambiguous C++ APIs & accurate error/field behavior:**
  - `Na8veModel.request(prompt, max_bytes)` compiles without overload ambiguity (`Na8veModel.request(prompt, len, max_bytes)` requires all 3 arguments).
  - Synchronous vs. asynchronous error codes match runtime behavior (`N8_MODEL_E_BUSY` = `-1` and `N8_MODEL_E_SIZE` = `-3` from `Na8veModel.request()`; `N8_MODEL_E_RATE` = `-2`, `N8_MODEL_E_MODEL` = `-4`, `N8_MODEL_E_REPLY` = `-5` via `onModelReply()`).
  - `Na8veStore.recall()` populates both `hits[i].id` and `hits[i].score_milli` (`score * 10000`).
  - `Na8veSeam.read("device", ...)` queries the onboard temperature sensor cleanly across SDK headers, starter sketch, and docs.
- **Complete capability & slot gates:** Build-time capability checks enforce `ipc_send`, `store_query`, and `tool` declarations, and unsupported deployment slot flags fail loudly.

---

## 2. Post-Fix Verification Matrix (`COM7`)

| Check | Command / Scope | Observed Result |
| :--- | :--- | :--- |
| **Board Discovery & Menus** | `arduino-cli board list` & `board details --fqbn na8ve:esp32s3:xiao_esp32s3_na8ve` | **Pass** — detected `Seeed XIAO ESP32-S3 Sense (na8ve-os)` on `COM7`; `grants`, `target_slot`, and `harden` menus clean. |
| **Parallel `--clean` Compile** | Consecutive `arduino-cli compile --clean --fqbn na8ve:esp32s3:xiao_esp32s3_na8ve` runs on `na8ve_developer_sdk` and `greenhouse_agent` | **Pass** — all `--clean` builds passed out-of-the-box (`4,225 B` flash payload, `8,192 B` RAM, host test + `EXPECT_MISMATCH` control + size optimization + `.n8pv` signing). |
| **Capability & Slot Controls** | `grants=pure_compute`, `grants=broker_only`, and `--slot sd` control checks | **Pass (all failed as required)** — rejected undeclared `tool` grant (`exit 1`) and unsupported `sd` upload slot (`exit 1`). |
| **2-Arg Overload & Live Subsystems** | Compiled/uploaded verification sketch calling `Na8veModel.request(prompt, 48)`, `Na8veStore.recall()`, `Na8veSeam.read("device")` | **Pass** — `0.23s` upload (`3,393 B`); `Seam("device")` = `42.2 C`, `Store` `score_milli=6709`, `Model` 48-byte async reply returned via `onModelReply()`. |
| **Starter Sketch Upload & E2E (`COM7`)** | `arduino-cli compile --upload -p COM7 --fqbn na8ve:esp32s3:xiao_esp32s3_na8ve sdk/arduino-ide/na8ve_developer_sdk` | **Pass** — `0.27s` upload (`4,225 B`, `name=na8ve_developer state=running`). `PING`, `BAD_OP`, `0x12` (`store_hits=2 score_milli=4901 seam=ok act={"verdict":"acted"}`), `260-B` prompt (`ERR prompt-too-long`), `0x10` turn queue, and `0x11` async reply (`act=checked`) all verified. |
