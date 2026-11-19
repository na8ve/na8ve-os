# na8ve-os Arduino IDE SDK

Everything required to author, verify, sign, and upload sandboxed WebAssembly (`.n8pv`) applications onto a pre-flashed **na8ve-os** Seeed XIAO ESP32-S3 Sense board from the Arduino IDE or `arduino-cli`.

The base `na8ve-os` firmware and on-device neural model ship **pre-installed on the hardware**. On the public distribution site, **Seeed Studio XIAO ESP32-S3 Sense** does **not** have a public browser WebSerial OS flasher—it is available **exclusively as a Pre-Flashed ESP32 product** in the **Shop** (`10 Day Backorder`, ships within 10 days):

- **`NA8-XIAO-S3-PRE` (`$49.00`)** — *na8ve-os · XIAO ESP32-S3 Sense Pre-Flashed Kit* (`240 MHz` dual LX7, `8 MB` octal PSRAM, `8 MB` Flash, OV2640 camera, PDM mic, microSD slot, factory-flashed signed runtime & neural model partition; `$9.00` US Tracked Ground shipping under `$100.00`).
- **`NA8-DUO-BUNDLE` (`$185.00`, Save `$13.00`)** — *na8ve Complete Edge Kit (Uno Q Pre-Flashed + XIAO ESP32-S3 Sense)* (pairs both pre-flashed boards with delegated RSA-3072-PSS key provisioning and free US Tracked Ground shipping).

This SDK contains only the application-side compiler wrapper, Arduino API headers/libraries, capability/packaging tools, and starter documentation.

---

## Contents

| Path                                                                            | Purpose                                                                                                                                                                                        |
| :------------------------------------------------------------------------------ | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [packages/na8ve/hardware/esp32s3/1.0.0/](packages/na8ve/hardware/esp32s3/1.0.0/) | Arduino Boards Manager platform (`na8ve:esp32s3`): `Na8veOS`, `Na8veModel`, `Na8veStore`, `Na8veAct`, `Na8veSeam` headers, capability menus, and `.n8pv` packaging/upload tools. |
| [na8ve_developer_sdk/](na8ve_developer_sdk/)                                     | Barebone starter sketch, host unit test + `EXPECT_MISMATCH` control, and developer documentation.                                                                                            |

---

## Installing the Board Package

1. Ensure the host toolchain prerequisites are installed:
   - **Arduino IDE 2.x** (or `arduino-cli`)
   - **Python 3.10+** on `PATH` with `cryptography` and `pyserial` (`pip install cryptography pyserial`)
   - **Zig (`0.13.x`)** on `PATH` (for compiling sketches to `wasm32-freestanding`)
   - *(Optional, when hardening is enabled in Arduino IDE)* Binaryen `wasm-opt` / `wasm-tools` on `PATH` (or `NA8VE_WASM_OPT` / `NA8VE_WASM_TOOLS`)
2. Copy [packages/na8ve](packages/na8ve) into your local Arduino packages directory:
   - **Windows**: `%LOCALAPPDATA%\Arduino15\packages\na8ve` (`platform.txt` currently uses Windows `.cmd` tool wrappers)
   - *(Note for macOS / Linux)*: Place under `~/Library/Arduino15/packages/na8ve` or `~/.arduino15/packages/na8ve` and adapt the `.cmd` wrappers in `platform.txt` to invoke Python directly.
3. Restart Arduino IDE (or re-run `arduino-cli core list`) and verify that **Seeed XIAO ESP32-S3 Sense (na8ve-os)** (`na8ve:esp32s3:xiao_esp32s3_na8ve`) is selectable.

---

## First-Time Key Setup & Board Pairing

Applications uploaded to a pre-flashed board must be signed with your developer RSA-3072-PSS key (`NA8VE_APP_KEY`, defaulting to `~/.na8ve/app-key.pem`). Never store private keys inside a sketch or SDK directory.

1. **Generate your developer signing key** *(once per workstation — or click `Generate & download app-key.pem` in the browser **Firmware** UI if also provisioning an Uno Q)*:

   ```bash
   python packages/na8ve/hardware/esp32s3/1.0.0/tools/sign_pvm.py keygen --key %USERPROFILE%\.na8ve\app-key.pem
   ```
2. **Pair the key with your Pre-Flashed `NA8-XIAO-S3-PRE` board over USB** (once per board, replacing `COM7` with your serial port):

   ```bash
   python packages/na8ve/hardware/esp32s3/1.0.0/tools/na8ve_arduino_tool.py pair --port COM7 --key %USERPROFILE%\.na8ve\app-key.pem
   ```

   *(If you ordered **`NA8-DUO-BUNDLE`** (`$185.00`), your delegated RSA-3072-PSS keypair is provisioned across the kit; if you keep a custom key path locally, set `NA8VE_APP_KEY` in your environment before launching Arduino IDE / `arduino-cli`.)*

---

## Pre-Built Standalone Applications & One-Click USB Install

In addition to custom sketch development, pre-built, cryptographically signed standalone sandbox applications for Seeed Studio XIAO ESP32-S3 Sense are available directly on the web distribution portal under the **Apps** menu (`/apps`):

- **`na8ve-developer-sdk-esp32`** — Verified SDK starter template with ping/pong IPC and model broker hooks.
- **`greenhouse-agent-esp32`** — Autonomous environmental agent proposing validated actuator actions.
- **`hello-app-esp32`** (`Minimal Standalone Sandbox`) — Minimal latency benchmark and ping/echo verification service.
- **`broker-app-esp32`** (`Edge IPC Query Coordinator`) — Text generation query forwarder to onboard System 2 model broker (`cortex-mvp`).

### Apps Portal Features & Zero Base-Firmware Overwrite Policy

On the web distribution site (`/apps`):
- **Live Search & Filter Tabs in Same Row**: Filter specifically by `XIAO ESP32-S3 · Arduino IDE` with the filter tabs and search bar locked to the same horizontal row.
- **Hardware Specifications**: Each card highlights the `Espressif ESP32-S3R8 (Xtensa LX7 @ 240 MHz, 8MB PSRAM, OV2640, PDM mic)` target with the `XTENSA LX7` badge.
- **Action Hierarchy**: Click **Install via USB** directly above the **Package** download button to flash the `.n8pv` payload straight from Chrome or Edge.
- **Never touch or overwrite the base firmware**: Only the dedicated isolated user application sandbox is written. The operating system and its models remain completely untouched.
- **Zero License Fee**: All standalone SDK applications are 100% free and open-source.
- **Instant Launch on Boot**: Once deployed to the user application sandbox via the browser USB flasher or `esptool.py`, the application automatically boots into sandboxed execution upon device power-up or reset.

---

## Next Steps

- Follow [na8ve_developer_sdk/README.md](na8ve_developer_sdk/README.md) and [01-getting-started.md](na8ve_developer_sdk/docs/01-getting-started.md) to configure capability grants, run the host test gate on **Verify**, and upload your `.n8pv` application over USB.
- See [02-sdk-api-reference.md](na8ve_developer_sdk/docs/02-sdk-api-reference.md) for the complete `Na8ve`, `Na8veModel`, `Na8veStore`, `Na8veAct`, and `Na8veSeam` C/C++ API.
