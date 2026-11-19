# na8ve-os Arduino App Lab SDK (Arduino Uno Q)

Everything required to author, compile, sign, verify, and deploy Arduino App Lab applications (`na8ve:*` Python Bricks, sandboxed `.n8pv` modules, and STM32U585 coprocessor sketches) onto an **Arduino Uno Q** running **na8ve-os**.

The operating system, enclave daemon, and models are installed onto the Uno Q itself—this SDK contains only the application-side build/signing CLI, C sandbox headers, Python starter code, and documentation, with zero OS source code or models in app bundles.

---

## Architecture: Three Distinct Layers

| Layer | Where It Lives | What It Contains |
| :--- | :--- | :--- |
| **1. Hardware OS & Models** | Installed on the Uno Q over WebUSB via the **Firmware** (`/`) page (or ordered factory-provisioned in the **Shop** `/shop`, `10 Day Backorder`) | `na8ve-osd`, `na8ve-applab-daemon`, STM32U585 bridge, and `.n8vm` models: **Community Beta 1M** (`na8ve-os-unoq`, free, `bx-1m-l2-t036` `int32` only) or **Pre-Flashed / N8LC Licensed** (`na8ve-os-unoq-preflashed`, `$69.00` BYO licence or `$149.00` `NA8-UNOQ-PRE` / `$185.00` `NA8-DUO-BUNDLE`, adding **2M** `bx-2m-t035` and **Vision** `vn8v-tin66`). Never distributed in this SDK. |
| **2. Buyer Purchase Licence & Key Pairing (`N8LC`)** | Minted from your `$69.00` **Buy** checkout session on **Firmware** (`/`) (or provisioned on Shop orders) into `.n8lc` + `/etc/na8ve-os/` | Binds your purchased Uno Q hardware serial / MAC identity (`aa:bb:cc:dd:ee:ff`) to your workstation's RSA-3072-PSS public key (`~/.na8ve/app-key.pem`) so `pvmfw` admits apps you sign with your private key. |
| **3. Arduino App Lab SDK** *(this directory)* | Your development workstation (`sdk/arduino-app-lab/`) | `tools/na8ve_applab_tool.py`, [na8ve-developer-sdk/](na8ve-developer-sdk/README.md), [na8ve-developer-sdk-applab.zip](na8ve-developer-sdk-applab.zip), and guides [01](docs/01-getting-started-arduino-app-lab.md)–[03](docs/03-coprocessor-sketch-and-actuation-guide.md). |

---

## Contents

| Path | Purpose |
| :--- | :--- |
| [tools/na8ve_applab_tool.py](tools/na8ve_applab_tool.py) | Developer CLI: `keygen`, `pubkey`, `build`, `pack` (leaves `.c`/`.h` out of the package, maps imports to the App Lab ABI, signs `.n8pv`, checks the package), and `verify-zip`. |
| [na8ve-developer-sdk/](na8ve-developer-sdk/README.md) | Starter project (`app.yaml`, `python/main.py`, `pvm/`, `sketch/`) with matching `pvm/app.n8pv` and `pvm/manifest.bin`. |
| [na8ve-developer-sdk-applab.zip](na8ve-developer-sdk-applab.zip) | Pre-packaged `.zip` archive ready for immediate import into Arduino App Lab. |
| [docs/01-getting-started-arduino-app-lab.md](docs/01-getting-started-arduino-app-lab.md) | Project layout, `app.yaml` brick variables, App Lab import/Run, and container lifecycle notes. |
| [docs/02-app-bricks-and-sandbox-api-reference.md](docs/02-app-bricks-and-sandbox-api-reference.md) | Full `CognitiveOS`, `MemoryGraph`, `VisionSaccade`, `ActPolicy`, and C sandbox (`n8_sdk.h`) reference. |
| [docs/03-coprocessor-sketch-and-actuation-guide.md](docs/03-coprocessor-sketch-and-actuation-guide.md) | Policy-gated STM32U585 actuation, MsgPack-RPC bridge dispatch, cooldowns, and `sketch.ino`. |

---

## Prerequisites

1. **Arduino App Lab** (`0.7.0+`) or `arduino-app-cli` (`0.8.4+`) connected to your Arduino Uno Q over USB.
2. **Python 3.10+** with `cryptography` (`pip install cryptography`) for RSA-3072 key generation and `.n8pv` signing.
3. **Zig (`0.13.x`)** on `PATH` (or pointed to by `NA8VE_ZIG`) when compiling custom C modules under `pvm/*.c`.

---

## Step 1: Get na8ve-os and a Board Licence

Install na8ve-os on your Arduino Uno Q from the **Firmware** page of [dev.na8ve.com](https://dev.na8ve.com) in Chrome or Edge, or order a pre-flashed board from the **Shop**:

- **Community (free):** the 1M model, through a free checkout that licenses your board.
- **Pre-Flashed (licensed):** the 1M, 2M and Vision models.

1. Open the release on the **Firmware** page: **Community** for the free licence, **Pre-Flashed** for a paid one.
2. Create your app signing key if you will sign your own apps (optional for Community, required for Pre-Flashed): click **Generate & download app-key.pem** and keep it as `~/.na8ve/app-key.pem`, or run `python sdk/arduino-app-lab/tools/na8ve_applab_tool.py keygen --key ~/.na8ve/app-key.pem` and click **Load pubkey.bin**. The board's licence then lets it run apps you sign with that key.
3. Click **Get the free licence** (Community) or **Buy** (Pre-Flashed) and complete the checkout. You can also paste the session key of an earlier checkout, or attach an `.n8lc` licence file.
4. Connect the board over USB-C and click **Connect & install**. The licence is bound to that board.
5. Click **Save minted .n8lc** to keep a copy of the board's licence.

The **Apps** page also installs the example apps (`na8ve-developer-sdk`, `matrix-app`, `greenhouse-app`, `image-app`, `broker-app`) over USB, and offers each one's App Lab `.zip`. Installing an app writes only its own sandbox.

---

## Step 2: Import the Starter App or Pack Your Own

### Quick Import (Zero Compile Needed)

1. Open **Arduino App Lab** -> select your **Arduino Uno Q** -> **Import App** -> choose [na8ve-developer-sdk-applab.zip](na8ve-developer-sdk-applab.zip) (or copy [na8ve-developer-sdk/](na8ve-developer-sdk/README.md) directly).
2. Click **Run** to flash `sketch/sketch.ino` onto the STM32U585, launch `python/main.py` inside the container, and inspect the live JSON status report in the Console.

### Build, Sign & Pack Custom C Sandbox Apps

When you customize `pvm/sdk_starter_app.c` or create a new app directory:

```bash
# Compile pvm/*.c to Wasm, map its imports to the App Lab ABI, sign with your RSA-3072 key,
# leave .c/.h/.wasm/manifest.json out of the zip, and check the package:
python tools/na8ve_applab_tool.py pack \
  --app-dir ./na8ve-developer-sdk \
  --key ~/.na8ve/app-key.pem \
  --out ./dist/my-app-applab.zip

# Independently verify any exported or built .zip archive before importing:
python tools/na8ve_applab_tool.py verify-zip ./dist/my-app-applab.zip
```

Import the verified `.zip` into Arduino App Lab (or run `arduino-app-cli app import ./dist/my-app-applab.zip`) and click **Run**.

---

## Next Steps

- [01-getting-started-arduino-app-lab.md](docs/01-getting-started-arduino-app-lab.md) — `app.yaml` schema, clean `SIGTERM` loop, `NA8VE_ONCE=1`, and CLI quirks.
- [02-app-bricks-and-sandbox-api-reference.md](docs/02-app-bricks-and-sandbox-api-reference.md) — Exact return types for `CognitiveOS`, `MemoryGraph`, `VisionSaccade`, `ActPolicy`, and C `n8_sdk.h` opcodes.
- [03-coprocessor-sketch-and-actuation-guide.md](docs/03-coprocessor-sketch-and-actuation-guide.md) — Allowed actuators, state validation, rate-limit cooldowns, and `Arduino_RouterBridge` handlers.
