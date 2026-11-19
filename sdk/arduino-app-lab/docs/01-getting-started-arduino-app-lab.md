# 1. Getting Started with Arduino App Lab

## Provisioning Your Arduino Uno Q (`Firmware` vs. `Shop`)

Before opening Arduino App Lab, ensure your Uno Q is running **`na8ve-os`**:

* **Free Community Beta 1M (`Firmware` `/`, `na8ve-os-unoq`):** Installs `na8ve-osd`, App Lab UI, `cortex-mvp`, STM32U585 bridge, and **1M (`bx-1m-l2-t036`, `int32`) only**.
* **Pre-Flashed / N8LC Licensed (`Firmware` `/`, `$69.00` licence key on BYO board, or ordered in `Shop` `/shop` on `10 Day Backorder` via `NA8-UNOQ-PRE` `$149.00` or `NA8-DUO-BUNDLE` `$185.00`):** Unlocks **1M (`bx-1m-l2-t036`) + 2M (`bx-2m-t035`) + Vision (`vn8v-tin66`)** and binds your RSA-3072-PSS key (`~/.na8ve/app-key.pem`). Use the **Purchase Licence Key (`N8LC`)** flow (`Generate & download app-key.pem` or `Load pubkey.bin` -> **Buy** or attach `.n8lc` -> **Connect & install** -> **Save minted `.n8lc`**; see [../README.md](../README.md)).
* **Standalone Pre-Packaged Applications (`Apps` `/apps`):** Download ready-to-import App Lab `.zip` archives or execute one-click USB deployment directly onto the Uno Q `/home/arduino/na8ve-os/apps/` staging partition. These apps are 100% free and do not touch underlying operating system firmware or model partitions.

> *(Note: Need the companion ESP32-S3 target? XIAO ESP32-S3 Sense is available only as a Pre-Flashed ESP32 product — `NA8-XIAO-S3-PRE` `$49.00` or inside `NA8-DUO-BUNDLE` `$185.00` — programmed with [../../arduino-ide/README.md](../../arduino-ide/README.md).)*

## Project Structure

Every **na8ve-os** App Lab project follows this layout:

```text
my-first-app/
├── app.yaml            # App metadata and na8ve:* Brick bindings
├── README.md           # Project summary
├── python/
│   └── main.py         # Python controller using na8ve.app_bricks
├── pvm/
│   ├── app.n8pv        # Compiled, stripped, and signed sandbox module
│   └── manifest.bin    # Binary 76-byte N8MF capability & SHA-256 manifest
└── sketch/
    ├── sketch.ino      # Microcontroller bridge & LED matrix sketch
    └── sketch.yaml     # Board platform & Arduino_RouterBridge libraries
```

> **Keep your sources local:** Author your C sandbox locally using `pvm/n8_sdk.h`, `pvm/*.c`, and `pvm/manifest.json`. Always build archives with `tools/na8ve_applab_tool.py pack`, which compiles `pvm/app.n8pv` + `pvm/manifest.bin` and strips all `.c`, `.h`, `.wasm`, private keys, and `manifest.json` files from the `.zip`. On paired hardware, both `app.n8pv` and its matching `manifest.bin` are strictly required at runtime.

---

## Configuring `app.yaml`

Declare the four `na8ve:*` Bricks in `app.yaml`. Note that vision saccade count uses **`NA8VE_SACCADE_COUNT`**:

```yaml
name: my-first-app
description: Custom edge AI app running on na8ve-os.
ports: []
bricks:
- na8ve:cognitive_os:
    model: na8ve-1m-recurrent-qrb2210
    variables:
      NA8VE_MODEL_NAME: bx-1m-l2-t036
      NA8VE_EXEC_MODE: recurrent
      NA8VE_STATE_WIDTH: int32
      NA8VE_PVM_PATH: /app/pvm/app.n8pv
- na8ve:vision_saccade:
    model: na8ve-vision-tin66-qrb2210
    variables:
      NA8VE_VISION_MODEL: vn8v-tin66
      NA8VE_SACCADE_COUNT: '8'
      NA8VE_CONFIDENCE_THRESHOLD: '0.25'
- na8ve:memory_graph:
    variables:
      NA8VE_DEFAULT_TIER: episodic
      NA8VE_MAX_RECALL_HOPS: '2'
- na8ve:act_policy:
    variables:
      NA8VE_ACT_COOLDOWN_MS: '250'
```

*Note on `arduino-app-cli app new`:* `arduino-app-cli 0.8.4` creates `app.yaml` with `bricks: []` even when `-b` flags are passed; copy the `bricks:` section above into new projects or start directly from `na8ve-developer-sdk/`.

---

## Building & Importing `.zip` Bundles

If you copy `na8ve-developer-sdk/` directly into `/home/arduino/ArduinoApps/`, its `pvm/` directory already contains synchronized `app.n8pv` and `manifest.bin` files matching the starter C source.

Whenever you edit `pvm/sdk_starter_app.c` or `pvm/manifest.json`:

```bash
python tools/na8ve_applab_tool.py pack \
  --app-dir ./na8ve-developer-sdk \
  --key ~/.na8ve/app-key.pem \
  --out ./na8ve-developer-sdk-applab.zip
```

1. Open **Arduino App Lab** and select your connected **Arduino Uno Q**.
2. Import the verified `.zip` bundle (or run `arduino-app-cli app import <zip>`). Both flat archives (`app.yaml` at archive root) and nested archives (`<app-name>/app.yaml`) are accepted.
3. Click **Run**:
   - App Lab compiles `sketch/sketch.ino` and flashes the STM32U585 coprocessor.
   - App Lab launches the Python container (`python/main.py`) with `APP_HOME` set.
   - Output appears in the **Console** panel.

---

## Container Lifecycle & One-Shot CLI Testing

Inside `python/main.py`, flush output immediately and block cleanly on `SIGTERM` when running inside App Lab (`APP_HOME` set):

```python
if __name__ == "__main__":
    print(json.dumps(main(), indent=2), flush=True)
    if os.environ.get("APP_HOME") and not os.environ.get("NA8VE_ONCE"):
        running = [True]
        signal.signal(signal.SIGTERM, lambda *_: running.__setitem__(0, False))
        while running[0]:
            time.sleep(1.0)
```

- **One-shot smoke test inside a running container:**
  ```bash
  docker exec -e NA8VE_ONCE=1 <container-name> python3 /app/python/main.py
  ```
- **App Lab / `arduino-app-cli 0.8.4` stop status quirk:** If you run `arduino-app-cli app stop <app-id>`, containers handling `SIGTERM` and exiting with `ExitCode: 0` may display status `failed` in `arduino-app-cli app list` (a known upstream Compose exit-code mapping behavior in `arduino-app-cli 0.8.4`) even though teardown succeeded cleanly. For daemonized loops using Arduino's `App.run(user_loop=...)`, integrate `CognitiveOS.execute()` and `VisionSaccade.loop()`.
