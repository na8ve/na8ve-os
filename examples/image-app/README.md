# na8ve-os Image & Visual Perception Edge Application

An edge computer vision and cognitive perception application for the **Arduino Uno Q** (Qualcomm QRB2210 application processor + STMicroelectronics STM32U585 TrustZone coprocessor) and **Seeed Studio XIAO ESP32-S3 Sense**, built using the `na8ve-os` C Application SDK.

The application captures ephemeral sensor frames, performs 8-saccade foveated feature classification, strictly enforces the **Zero-Raw-Image-Persistence Privacy Invariant**, dispatches situational cognitive turns to the system **Model Broker** (pVM #1: `cortex-mvp`), and routes safety-gated actuation proposals to Core 0.

---

## 1. Architecture & Privacy Invariants

In `na8ve-os`, visual perception applications execute inside sandboxed WebAssembly micro-virtual machines (pVMs) with strictly bounded authority:

```
┌────────────────────────────────────────────────────────────────────────┐
│                          Qualcomm QRB2210                              │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  pVM #4: Image App (image.wasm)                                  │  │
│  │  • Captures ephemeral frames into volatile DMA                   │  │
│  │  • Extracts 8 foveated saccades                                  │  │
│  │  • Purges volatile pixel memory immediately                      │  │
│  │  • Emits metadata only (class, confidence, bbox)                 │  │
│  │  • Formulates situational prompt:                                │  │
│  │    "The camera sees <label>. What is it?"                        │  │
│  │  • Dispatches actuation proposals via N8_OP_ACTUATE              │  │
│  └───────────▲──────────────────────────┬───────────────────────────┘  │
│              │ IPC                      │ IPC                          │
│  ┌───────────▼────────────┐ ┌───────────▼───────────────────────────┐  │
│  │ pVM #1: cortex-mvp     │ │ Core 0: Reference Monitor             │  │
│  │ (Model Broker)         │ │ & Actuator Safety Table               │  │
│  │ • Situational reasoning│ └───────────┬───────────────────────────┘  │
│  │ • Byte-level streaming │             │ RPC Bridge                    │
│  └────────────────────────┘             ▼ (UART / SPI)                 │
└────────────────────────────────────────────────────────────────────────┘
                                          ▼
                  ┌────────────────────────────────┐
                  │    STM32U585 TrustZone MCU     │
                  │   Actuators: Vent, Mist, Light │
                  └────────────────────────────────┘
```

### Core Privacy Guarantees
1. **Zero Raw Image Persistence**: Raw pixels exist strictly in volatile hardware DMA buffers during the active inference turn. No raw image, JPEG, PNG, or video frame is ever saved to flash, eMMC, or the Core 0 persistent memory graph.
2. **Metadata-Only IPC**: Only classification labels (e.g. `indoor_plant`, `sprout`, `bell_pepper`, `ladybug`), confidence scores, and spatial bounding box coordinates enter the inter-process communication bus.
3. **Actuator Safety Gate**: Under the `na8ve-os` safety policy, an application never drives physical GPIO pins or display hardware directly. Validated proposals (`act target=light state=on proposed_by=image-app`) are routed through Core 0 and verified against safety interlocks.

---

## 2. Application Operation Codes (`n8_on_message`)

| Operation Code | Name | Direction | Payload | Description |
|---|---|---|---|---|
| `0x00000001` | `N8_OP_PING` | Inbound | *None* | Heartbeat check; replies `pong image-app`. |
| `0x00000002` | `OP_PROBE` | Inbound | *None* | Queries camera sensor name, hardware ID, resolution, and status. |
| `0x00000010` | `OP_CAPTURE` | Inbound | *None* | Captures ephemeral frame into volatile DMA and purges raw memory immediately. |
| `0x00000011` | `OP_CLASSIFY` | Inbound | *None* | Executes 8-saccade neural classification; returns top-1 label and confidence. |
| `0x00000012` | `OP_STATUS` | Inbound | *None* | Returns active scene, class label, confidence, bbox, privacy audit status, and the answer to the last `OP_COGNITIVE_TURN` once the model broker has replied (`answer=pending` until then). |
| `0x00000013` | `OP_ASCII_VIEW`| Inbound | *None* | Renders multi-line ANSI/ASCII camera viewport directly to operator console. |
| `0x00000014` | `OP_COGNITIVE_TURN`| Inbound | *None* | Dispatches situational prompt to Model Broker (`cortex-mvp`). |
| `0x00000015` | `OP_ACTUATE` | Inbound | *None* | Dispatches proposal to Core 0 Actuator Safety Table based on detection. |
| `0x00000016` | `OP_SCENE` | Inbound | `0..4` | Selects pre-calibrated test scene (sprout, indoor_plant, bell_pepper, ladybug, lampshade). |

---

## 3. Host Testing & Negative Control Twin

In keeping with `na8ve-os` verification standards, the app includes a native host test suite with a mandatory failing control twin:

```bash
# 1. Run positive test suite
gcc -I../../sdk/include image_app.c test_image_app.c ../../sdk/src/n8_util.c ../../sdk/src/n8_model.c -o test_image_app
./test_image_app

# 2. Run negative control twin (broker refusal or privacy violation must be detected)
gcc -DEXPECT_MISMATCH -I../../sdk/include image_app.c test_image_app.c ../../sdk/src/n8_util.c ../../sdk/src/n8_model.c -o test_image_app_control
./test_image_app_control
```

---

## 4. Compiling, Signing & Flashing to Hardware

> [!TIP]
> **Working Directory Notice**:
> * **When working inside `examples/image-app/`**:
>   Always prefix tool scripts with `../../tools/`:
>   ```bash
>   # Build and sign from inside examples/image-app/
>   python ../../tools/build_app.py --name image --src image_app.c --model-client --out dist/
>   python ../../tools/sign_app.py sign --name image dist/image.wasm dist/image.n8pv
>   python ../../tools/build_manifest.py manifest-entry.json --out dist/manifest.bin
>   ```
> * **When connecting to the board**:
>   Use the desktop operator tools from the distribution site's **Apps** page (**Desktop Tools**):
>   ```bash
>   na8ve-console --tcp 127.0.0.1:7878
>   # or for the interactive TUI:
>   na8ve-tui --tcp 127.0.0.1:7878
>   ```

### Step 1: Compile to Freestanding WebAssembly
```bash
python ../../tools/build_app.py --name image --src image_app.c --model-client --out dist/
```
This generates `dist/image.wasm` (~4.8 KB).

### Step 2: Sign the Container (.n8pv)
Sign the WebAssembly module with an RSA-3072 operator key into a verifiable `.n8pv` container:
```bash
python ../../tools/sign_app.py sign --name image dist/image.wasm dist/image.n8pv
```

### Step 3: Build the Capability Manifest
Compile `manifest-entry.json` into the binary capability table:
```bash
python ../../tools/build_manifest.py manifest-entry.json --out dist/manifest.bin
```

### Step 4: Deploy to Hardware
Deploy the signed payload and manifest to your target:

* **Arduino Uno Q**: package the app with the Arduino App Lab SDK ([`sdk/arduino-app-lab/`](../../sdk/arduino-app-lab/README.md)) and import the `.zip` in Arduino App Lab, or click **Install via USB** on the app's card on the distribution site's **Apps** page.  The App Lab app is `applab/`: it walks a scene through the sandbox and asks the model broker what it sees; the camera look itself uses the Vision model, which needs a paid licence for the board, and the app says so on a board with the free licence.
* **Seeed Studio XIAO ESP32-S3 Sense (pre-flashed)**: upload from the Arduino IDE with the board package ([`sdk/arduino-ide/`](../../sdk/arduino-ide/README.md)).

---

## 5. Hybrid Vision-Cognitive Architecture & Simulation Daemon

The automated simulation daemon (`image_sim.py`) couples camera hardware abstraction with the native C cognitive engine (`console_host`):

```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │              na8ve-tui / na8ve-console (TCP 127.0.0.1:7878)            │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │ TCP Socket Link
 ┌───────────────────────────────────▼────────────────────────────────────┐
 │               Vision Simulation Daemon (image_sim.py)                  │
 │                                                                        │
 │   ┌───────────────────────────────┐  ┌──────────────────────────────┐  │
 │   │       ImageEnvironment        │  │    CognitiveEngineBackend    │  │
 │   │                               │  │                              │  │
 │   │  • 5 Pre-calibrated scenes    │  │  • Spawns native C engine:   │  │
 │   │  • Zero-raw-image persistence │  │    console_host              │  │
 │   │  • 8-saccade classification   │  │  • Autoregressive byte-level │  │
 │   │  • ANSI ASCII viewport engine │  │    neural inference          │  │
 │   │  • Streaming ev vision ticks  │  │  • Dynamic model loader      │  │
 │   │  • Actuator safety dispatch   │  │    (/model 3 32 -> .n8vm)    │  │
 │   └───────────────┬───────────────┘  └──────────────┬───────────────┘  │
 └───────────────────┼─────────────────────────────────┼──────────────────┘
                     │                                 │
                     ▼                                 ▼
             Real-Time Vision                  Real Neural Tokens
             & Privacy Gating                   & Situational Turns
```

### 1. Vision Simulation Subsystem (`ImageEnvironment`)
- **Pre-Calibrated Benchmark Scenes**: Models realistic camera captures across 5 diverse scenes (`sprout`, `indoor_plant`, `bell_pepper`, `ladybug`, `lampshade`).
- **Zero-Raw Privacy Gating**: Immediately clears raw frame arrays after extracting feature saccades.
- **In-Device ANSI Viewport**: Renders ASCII camera previews directly over UART or TCP without requiring host GUI tools.
- **Streaming Telemetry**: Emits live `ev vision seq=...` updates every 3 seconds to connected operators.

### 2. Cognitive Engine Subsystem (`CognitiveEngineBackend`)
- **Situational Turn Synthesis**: Translates visual detections into conversational prompts (`The camera sees indoor_plant. What is it?`).
- **Autoregressive Token Generation**: Generates contextual explanations and proposes corresponding physical actuations.
- **Dynamic Model Catalog Switching**: Easily switches between the 1M parameter model (`bx-1m-l2-t036`) and 2M parameter model (`bx-2m-t035`).

---

## 6. How to Run Directly from na8ve-os

### Terminal 1: Launch the Vision Simulation Daemon

From the `na8ve-os` repository root:

```powershell
python examples/image-app/image_sim.py
```

> **Note**: If port 7878 is already bound by an active Android Debug Bridge rule (`adb forward tcp:7878 tcp:7878`), clear the forward rule with `adb forward --remove tcp:7878` or pass `--port 7879` to run on an alternate port.

### Terminal 2: Connect via the Operator Binaries

**On Windows PowerShell:**

```powershell
.\build\bin\na8ve-console.exe --tcp 127.0.0.1:7878
# or for the rich interactive TUI:
.\build\bin\na8ve-tui.exe --tcp 127.0.0.1:7878
```

**On Linux or macOS (POSIX shell):**

```bash
na8ve-console --tcp 127.0.0.1:7878
# or for the rich interactive TUI:
na8ve-tui --tcp 127.0.0.1:7878
```

---

## 7. Interactive Operator Tour & Wire Walkthrough

#### 1. Probe the Camera Hardware (`cam-probe`)
```text
cam-probe
```
Output:
```text
cam sensor=UnoQ-QRB2210-Cam pid=0x2210 view=72 resolution=64x64 fps=5 status=ready
OK cam-probe
```

#### 2. Inspect In-Device ASCII Viewport (`vision`)
```text
vision
```
Output:
```text
--- na8ve-os Vision & Neural Perception ---
Frame: 64x64 QVGA Grayscale Viewport
+--------------------------------+
| . . . . : - = = - : . . . . . .|
| . . . * # # @ @ # # * . . . . .|
| . . * # [TARGET OBJECT] # * . .|
| . . . * # # @ @ # # * . . . . .|
| . . . . : - = = - : . . . . . .|
| . . . . [___POT___] . . . . . .|
+--------------------------------+
Detection: label="indoor_plant" confidence=0.88 bbox=[12, 8, 44, 38]
Cognition: Event metadata routed to cortex-mvp (pVM #1)
Policy: Zero raw pixels persisted or transmitted.
OK vision
```

#### 3. Trigger 8-Saccade Classification (`os-vision once`)
```text
os-vision once
```
Output:
```text
vision class=indoor_plant p=0.880 ms=152
vision-top5 indoor_plant:0.880 pot:0.050 vase:0.030 leaf:0.020 table:0.010
OK os-vision
```

#### 4. Switch Test Scenes (`cam-scene <0..4>`)
```text
cam-scene 0
```
Output:
```text
ok scene=sprout
OK cam-scene
```

#### 5. Verify Sandboxed App State (`os-call 4 18`)
```text
os-call 4 18
```
Output:
```text
scene=sprout class=sprout p=0.84 bbox=[14, 18, 42, 46] privacy=zero_raw_persisted
OK os-call
```

#### 6. Propose Actuation to Core 0 Safety Table (`os-call 4 21`)
```text
os-call 4 21
```
Output:
```text
ok proposed act target=mister state=pulse proposed_by=image-app
OK os-call
```

#### 7. Situational Cognitive Turn (`chat "The camera sees sprout. What is it?"`)
```text
chat "The camera sees sprout. What is it?"
```
Output:
```text
The camera is a popular camera t
OK chat
```

#### 8. TUI Commands for Model Inspection & Dynamic Loading (`/model`, `model-load`)

The interactive operator terminal (`na8ve-tui`) supports dynamic model catalog inspection and runtime model swapping between the 1M parameter model (`bx-1m-l2-t036`) and 2M parameter model (`bx-2m-t035`):

##### 1. Inspect Available Models in Catalog (`/model`)
```text
/model
```
Output:
```text
model 1: bx-1m-l2-t036 (recurrent int32)
model 2: bx-1m-l2-t036-hardened (recurrent int32)
model 3: bx-2m-t035 (recurrent int32)
OK model
```

##### 2. Dynamically Load Target Model (`/model <N|NAME> [width]`)
Load the 1M model at 32-bit recurrent precision:
```text
/model 1 32
# or by canonical name:
/model bx-1m-l2-t036 32
```
Or switch to the 2M model for enhanced visual reasoning:
```text
/model 3 32
# or by canonical name:
/model bx-2m-t035 32
```
Under the hood, the terminal issues the wire command:
```text
model-load bx-1m-l2-t036 32
# or
model-load bx-2m-t035 32
```
Output:
```text
OK model-load
```

##### 3. Header Status Verification
The TUI status bar immediately rebinds and displays the active model runtime metadata:
```text
cortex-mvp · bx-1m-l2-t036 · recurrent int32 · ready
```
Internal architectural invariants (dimensions, layer counts, heads) are strictly hidden per the Zero Architecture Exposure Invariant.

##### 4. Cognitive Turn with Active Model
Subsequent visual perception cognitive prompts are automatically processed by the newly loaded model:
```text
chat "The camera identifies sprout at 84% confidence. What microclimate action is needed?"
```

