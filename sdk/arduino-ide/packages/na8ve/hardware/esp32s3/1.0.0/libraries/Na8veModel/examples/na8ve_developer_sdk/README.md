# na8ve-os Developer SDK (Arduino IDE)

A barebone starter project and guide for building offline, AI-native applications on a **Pre-Flashed `na8ve-os` XIAO ESP32-S3 Sense** (`NA8-XIAO-S3-PRE`, `$49.00` or bundled in `NA8-DUO-BUNDLE`, `$185.00`, `10 Day Backorder`) inside the **Arduino IDE**.

`na8ve-os` ships factory-flashed on the Pre-Flashed ESP32 product with an on-device recurrent byte-level neural engine, a bounded three-tier graph memory store (`sensory`, `episodic`, `semantic`), and isolated user sketches. There is no public WebSerial OS flasher for ESP32-S3; Arduino IDE compiles and uploads your signed `.n8pv` sketch directly onto the pre-flashed board. Applications never drive GPIO pins directly; physical actions pass through `Na8veAct` and the actuator safety policy before touching hardware.

---

## Project Layout

| Path | Purpose |
| :--- | :--- |
| [na8ve_developer_sdk.ino](na8ve_developer_sdk.ino) | Barebone starter sketch using `Na8veModel`, `Na8veStore`, `Na8veAct`, and `Na8veSeam`. |
| [test_na8ve_developer_sdk.c](test_na8ve_developer_sdk.c) | Host unit test and `EXPECT_MISMATCH` control check run on **Verify**. |
| [docs/01-getting-started.md](docs/01-getting-started.md) | Arduino IDE board selection, sketch lifecycle (`setup`, `loop`, `onMessage`, `onModelReply`), and upload workflow. |
| [docs/02-sdk-api-reference.md](docs/02-sdk-api-reference.md) | Complete C/C++ reference for `<Na8veOS.h>`, `Na8veModel`, `Na8veStore`, `Na8veAct`, and `Na8veSeam`. |

---

## Quick Start

1. Open **Tools -> Board** in Arduino IDE and select **Seeed XIAO ESP32-S3 Sense (na8ve-os)**.
2. Select your board's USB serial port under **Tools -> Port**.
3. Open [na8ve_developer_sdk.ino](na8ve_developer_sdk.ino), review capability options under **Tools -> na8ve-os Capability Grants**, and click **Verify** to compile and run `test_na8ve_developer_sdk.c`.
4. Click **Upload** to stream your compiled `.n8pv` application over USB to the board without reflashing the base OS or neural models.
