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
| [tools/na8ve_applab_tool.py](tools/na8ve_applab_tool.py) | Developer CLI: `keygen`, `pubkey`, `build`, `pack` (strips `.c`/`.h`, hashes imports, signs `.n8pv`, validates Zero-Leak gate), and `verify-zip`. |
| [na8ve-developer-sdk/](na8ve-developer-sdk/README.md) | Starter project (`app.yaml`, `python/main.py`, `pvm/`, `sketch/`) with matching `pvm/app.n8pv` and `pvm/manifest.bin`. |
| [na8ve-developer-sdk-applab.zip](na8ve-developer-sdk-applab.zip) | Pre-packaged, Zero-Leak verified `.zip` archive ready for immediate import into Arduino App Lab. |
| [docs/01-getting-started-arduino-app-lab.md](docs/01-getting-started-arduino-app-lab.md) | Project layout, `app.yaml` brick variables, App Lab import/Run, and container lifecycle notes. |
| [docs/02-app-bricks-and-sandbox-api-reference.md](docs/02-app-bricks-and-sandbox-api-reference.md) | Full `CognitiveOS`, `MemoryGraph`, `VisionSaccade`, `ActPolicy`, and C sandbox (`n8_sdk.h`) reference. |
| [docs/03-coprocessor-sketch-and-actuation-guide.md](docs/03-coprocessor-sketch-and-actuation-guide.md) | Policy-gated STM32U585 actuation, MsgPack-RPC bridge dispatch, cooldowns, and `sketch.ino`. |

---

## Prerequisites

1. **Arduino App Lab** (`0.7.0+`) or `arduino-app-cli` (`0.8.4+`) connected to your Arduino Uno Q over USB.
2. **Python 3.10+** with `cryptography` (`pip install cryptography`) for RSA-3072 key generation and `.n8pv` signing.
3. **Zig (`0.13.x`)** on `PATH` (or pointed to by `NA8VE_ZIG`) when compiling custom C modules under `pvm/*.c`.

---

## Step 1: Acquire Hardware or Provision `na8ve-os` & Licence Key (`N8LC`)

You can acquire factory-flashed hardware from the **Shop** (`/shop`, **`10 Day Backorder` · Ships within 10 days**) or provision your own Arduino Uno Q from the **Firmware** (`/`) page in Chrome/Edge:

### Hardware Options (`Shop` — `10 Day Backorder`)

| SKU | Product | Includes | Price / Shipping |
| :--- | :--- | :--- | :--- |
| **`NA8-UNOQ-PRE`** | **Arduino Uno Q Pre-Flashed Enclave Edition** | QRB2210 + STM32U585 factory-flashed with **1M + 2M + Vision**, App Lab UI, and delegated `N8LC` + RSA-3072-PSS signing key. | **`$149.00`** · Free US Ground |
| **`NA8-DUO-BUNDLE`** | **na8ve Complete Edge Kit (Uno Q Pre-Flashed + XIAO ESP32-S3 Sense)** | Pre-flashed Uno Q + pre-flashed XIAO ESP32-S3 Sense kit paired with delegated RSA-3072-PSS signing key + USB-C cables. *(Seeed XIAO ESP32-S3 is available **only** as a Pre-Flashed ESP32 product — `NA8-XIAO-S3-PRE` `$49.00` standalone or inside this bundle.)* | **`$185.00`** *(Save `$13.00`)* · Free US Ground |

*(US Tracked Ground is free on `$100+` orders or `$9.00` under `$100`; Canada `$14.00`; International `$19.00`; 2-Day Express `$24.00` US / `$39.00` Intl. Track orders under **Track Existing Order**.)*

### Option A: Pre-Flashed / N8LC Licensed Uno Q (1M + 2M + Vision — `$69.00` BYO Licence)

Follow the **Purchase Licence Key (`N8LC`)** workflow on the **Firmware** (`/`) tab:

1. **Select Release:** Click **`na8ve-os · Uno Q (Pre-Flashed)`** (`$69.00`, models `bx-1m-l2-t036`, `bx-2m-t035`, `vn8v-tin66`; zero dev diagnostic probes).
2. **Prepare Your Developer App Signing Key (RSA-3072-PSS):**
   - **Browser method:** Click **`Generate & download app-key.pem`** to create an RSA-3072 keypair in Chrome/Edge Web Crypto and save `app-key.pem` to `~/.na8ve/app-key.pem`.
   - **CLI method:** Run `python tools/na8ve_applab_tool.py keygen --key ~/.na8ve/app-key.pem` (writes `app-key.pem` and `app-key.pub.bin`) and click **`Load pubkey.bin`** in the panel so your public key is delegated during licence minting.
3. **Purchase or Attach Your `N8LC` Licence:**
   - Click **`Buy`** (`$69.00`) to complete Stripe checkout (auto-fills your checkout session token `cs_live_...` / `cs_test_...`), **or** paste an existing checkout session token, **or** click **`Attach pre-minted .n8lc licence file`** (`1,024` bytes).
4. **Target MAC & Connect:** Optionally enter the board MAC (`aa:bb:cc:dd:ee:ff`, or leave blank to read it from USB serial), pick **`Install OS`**, **`Clean na8ve-os reinstall`**, or **`Factory reset`**, and click **`Connect & install`** (anti-brick guarantee: `hyp_a` flashes before `boot_a`; `_b` recovery stays untouched).
5. **Back Up `.n8lc`:** Click **`Save minted .n8lc`** to save your `1,024-byte` MAC-bound licence locally alongside `~/.na8ve/app-key.pem`.

### Option B: Free Community Beta 1M Uno Q (`na8ve-os-unoq`)

Select **`na8ve-os · Uno Q (Community Beta 1M)`** (`0.1.0-beta.1`, free) on **Firmware** (`/`) and click **`Connect & install`** over WebUSB to install the App Lab UI, `cortex-mvp`, STM32U585 bridge, and **1M Master only** (`bx-1m-l2-t036`, `int32`). Note that `Vision` (`vn8v-tin66`) and `2M` (`bx-2m-t035`) require the **Pre-Flashed / N8LC Licensed** edition.

### Option C: Standalone Free App Lab Applications (`Apps` Tab `/apps`)

The distribution site provides an **`Apps`** tab (`/apps`) featuring pre-compiled, signed standalone sandbox application packages ready for immediate one-click USB installation or `.zip` export:

* **`Developer SDK Starter App`** (`na8ve-developer-sdk`, `na8ve-developer-sdk-applab.zip`)
* **`LED Matrix Cognitive Visualizer`** (`matrix-app`, `matrix-applab.zip`)
* **`Smart Greenhouse Reflex Agent`** (`greenhouse-app`, `greenhouse-applab.zip`)
* **`Vision Saccade Classifier`** (`image-app`, `image-applab.zip`)
* **`Inter-Sandbox Model Broker`** (`broker-app`, `broker-applab.zip`)

**Apps Portal Features & Zero Firmware Overwrite:**
- **Same-Row Controls**: Segmented filter tabs (`Arduino Uno Q · App Lab`) and search bar locked side-by-side in the same horizontal row.
- **Hardware Specification Banner**: Each Uno Q card displays `Qualcomm QRB2210 (Quad Cortex-A53 @ 2.0 GHz) + STM32U585 Coprocessor` with the `KVM STAGE-2` badge.
- **Action Layout**: One-click **Install via USB** button positioned vertically above the **Package** download button.
- **Zero Firmware Overwrite:** These applications are 100% free and contain **zero underlying OS firmware, bootloaders, or models**. When installed via USB, they stage into `/home/arduino/na8ve-os/apps/` without touching the running OS. Power cycle or start your board to run immediately.

---

## Step 2: Import the Starter App or Pack Your Own

### Quick Import (Zero Compile Needed)

1. Open **Arduino App Lab** -> select your **Arduino Uno Q** -> **Import App** -> choose [na8ve-developer-sdk-applab.zip](na8ve-developer-sdk-applab.zip) (or copy [na8ve-developer-sdk/](na8ve-developer-sdk/README.md) directly).
2. Click **Run** to flash `sketch/sketch.ino` onto the STM32U585, launch `python/main.py` inside the container, and inspect the live JSON status report in the Console.

### Build, Sign & Pack Custom C Sandbox Apps

When you customize `pvm/sdk_starter_app.c` or create a new app directory:

```bash
# Compile pvm/*.c -> stripped Wasm, hash host imports, sign with your RSA-3072 key,
# strip .c/.h/.wasm/manifest.json from the zip, and run the Zero-Leak Release Gate:
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
