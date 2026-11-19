# 1. Getting Started & Sketch Lifecycle

## Hardware & Board Selection in Arduino IDE

On the public distribution site, **Seeed Studio XIAO ESP32-S3 Sense** is offered **exclusively as a Pre-Flashed ESP32 product (`NA8-XIAO-S3-PRE`, `$49.00`, or paired in `NA8-DUO-BUNDLE`, `$185.00`, `10 Day Backorder`)** in the **Shop** (`/shop`). Your board arrives with the signed `na8ve-os` firmware and neural model partition already installed.

Once your pre-flashed board is connected and the **na8ve:esp32s3** board package is installed in Arduino IDE:

1. Open **Tools -> Board** and choose **Seeed XIAO ESP32-S3 Sense (na8ve-os)**.
2. Connect your board over USB-C and choose its serial port under **Tools -> Port** (for example `COM7`).
3. Pair your developer RSA-3072-PSS signing key (`~/.na8ve/app-key.pem`) once per board using `na8ve_arduino_tool.py pair --port COM7` (see the Arduino IDE SDK `README.md`).
4. Under **Tools -> na8ve-os Capability Grants**, pick only the capabilities your sketch uses (for example model inference, read-only store queries, sensor seam reads, and policy-checked actuation).

---

## Anatomy of a Barebone `na8ve-os` Sketch

Include `<Na8veOS.h>` plus whichever subsystem headers your app requires:

```cpp
#include <Na8veOS.h>
#include <Na8veModel.h>
#include <Na8veStore.h>
#include <Na8veAct.h>
#include <Na8veSeam.h>
```

Your sketch implements up to four standard Arduino hooks:

- **`void setup()`**: Runs once when your application initializes.
- **`void loop()`**: Optional periodic handler for polling cycles.
- **`void onMessage(int32_t from, int32_t op, const uint8_t *buf, int32_t len)`**: Runs whenever an incoming request arrives. Call `Na8ve.reply(...)` to answer synchronously.
- **`void onModelReply(const char *text, int32_t len, int32_t err)`**: Asynchronous callback invoked when a call to `Na8veModel.request(...)` finishes generating output.

### Minimal Echo + Diagnostics Pattern

```cpp
void setup() {
    Serial.println("my barebone na8ve-os app ready");
}

void onMessage(int32_t from, int32_t op, const uint8_t *buf, int32_t len) {
    (void)from;
    if (op == N8_OP_PING) {
        Na8ve.reply("pong my-app");
        return;
    }
    if (op == 0x10 && len > 0) {
        Na8veModel.request((const char *)buf, (size_t)len, 16);
        Na8ve.reply("OK queued");
        return;
    }
    Na8ve.reply("ERR op");
}

void onModelReply(const char *text, int32_t len, int32_t err) {
    if (err == 0 && len > 0) {
        Na8veAct.propose("fan", "low");
    }
}

void loop() {}
```

---

## Verifying, Testing, and Uploading

- **Host Test + Control Gate**: Add a `test_<sketch_name>.c` file next to your `.ino` sketch (see [test_na8ve_developer_sdk.c](../test_na8ve_developer_sdk.c)). Guard the entire test with `#ifdef N8_HOST_TEST` (Arduino compiles unguarded `.c` files in the sketch folder for `wasm32`) and include an `#ifdef EXPECT_MISMATCH` failure branch so **Verify** validates both expected behavior and a failing control check.
- **Replies vs. `Serial.print()`**: Use `Na8ve.reply(...)` inside `onMessage(...)` to return synchronous answers to callers. `Serial.print(...)` and `Serial.println(...)` emit compact metadata lines to the board's diagnostic log stream (and do not append trailing newlines).
- **Verify / Export**: Click **Verify** (or **Sketch -> Export Compiled Binary**) to compile, test, optimize, and package your `.n8pv` application container.
- **Upload**: Click **Upload** to send the application over USB directly to a paired board without rebooting `na8ve-os`. Configure `NA8VE_APP_KEY` if you store your developer signing key in a custom path.
