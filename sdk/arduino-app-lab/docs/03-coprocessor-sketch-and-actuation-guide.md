# 3. Coprocessor Sketch & Actuation Guide

On **Arduino Uno Q**, Python applications and neural turns never toggle microcontroller pins directly. Every actuation request passes through `na8ve-applab-daemon` (`cx_act`) before reaching the STM32U585 coprocessor:

1. `python/main.py` calls `act.propose(target, state)` via `ActPolicy`.
2. `cx_act` validates the request across five mandatory policy stages:
   - **Reserved-pin guard (`CX_ACT_E_RESERVED_PIN`)**: Pins and names touching SPI/SD/PDM/system buses (`gpio7..21`, `gpio26..42`, `gpio47..48`, `sd_cs`, etc.) are rejected unconditionally.
   - **Allowlist check (`CX_ACT_E_UNLISTED`)**: Only compiled targets (`fan`, `light`, `buzzer`, `matrix.glyph`) are permitted.
   - **State allowlist (`CX_ACT_E_INVALID_STATE`)**:
     - `fan`: `"off"`, `"low"`, `"high"`
     - `light`: `"off"`, `"on"`, `"dim"`
     - `buzzer`: `"off"`, `"beep"`, `"alarm"`
     - `matrix.glyph`: `"ok"`, `"alert"`, `"idle"`, `"pulse"`
   - **Per-actuator cooldown (`CX_ACT_E_COOLDOWN`)**: Back-to-back calls inside `cooldown_ms` (`NA8VE_ACT_COOLDOWN_MS`, default `250` ms) are blocked.
   - **Audit logging & dispatch**: Approved requests receive an incrementing `audit_seq` and are dispatched by the daemon over `/var/run/arduino-router.sock` using MsgPack-RPC (`[0, msgid, target, [state]]`) to your `sketch/sketch.ino` handlers.
3. Your microcontroller sketch executes only the safe registered `Bridge.provide(target, handler)` callbacks. *(Calling `arduino.app_utils.Bridge.call(...)` directly remains compatible for custom non-policy telemetry helpers such as reading counters, while physical actuators should always go through `act.propose(...)`.)*

---

## Inspecting Policy Rules at Runtime

```python
act = ActPolicy(cooldown_ms=250)
print(act.status())
```

---

## `sketch/sketch.yaml`

Configure the `arduino:zephyr` profile with `Arduino_RouterBridge (0.3.0)` (`Arduino_LED_Matrix` is built into the `arduino:zephyr` platform):

```yaml
profiles:
  default:
    platforms:
      - platform: arduino:zephyr
    libraries:
      - Arduino_RouterBridge (0.3.0)
      - dependency: Arduino_RPClite (0.2.1)
      - dependency: ArxContainer (0.7.0)
      - dependency: ArxTypeTraits (0.3.2)
      - dependency: DebugLog (0.8.4)
      - dependency: MsgPack (0.4.2)
default_profile: default
```

---

## `sketch/sketch.ino` Reference

Register bridge providers inside `setup()` using `Arduino_LED_Matrix` (4-word `uint32_t[4]` frames for Uno Q):

```cpp
#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>

Arduino_LED_Matrix matrix;

static const uint32_t GLYPH_SDK_READY[4] = {
    0x00182442,
    0x42241800,
    0x00000000,
    0x00000000
};

void on_fan(String state) {
    (void)state;
    matrix.loadFrame(GLYPH_SDK_READY);
}

void on_light(String state) {
    digitalWrite(LED_BUILTIN, state == "off" ? LOW : HIGH);
}

void on_matrix_glyph(String glyph_name) {
    (void)glyph_name;
    matrix.loadFrame(GLYPH_SDK_READY);
}

void setup() {
    pinMode(LED_BUILTIN, OUTPUT);
    matrix.begin();
    Bridge.begin();
    Bridge.provide("fan", on_fan);
    Bridge.provide("light", on_light);
    Bridge.provide("matrix.glyph", on_matrix_glyph);
}

void loop() {
    delay(50);
}
```
