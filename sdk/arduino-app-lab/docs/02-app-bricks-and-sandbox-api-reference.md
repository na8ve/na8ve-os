# 2. App Bricks & Sandbox API Reference

## Python Bricks (`na8ve.app_bricks`)

Import the four Bricks inside `python/main.py`:

```python
from na8ve.app_bricks import ActPolicy, CognitiveOS, MemoryGraph, VisionSaccade
```

### 1. `CognitiveOS` (Turns & Sandbox Execution)

```python
cog = CognitiveOS(
    model="bx-1m-l2-t036",   # "bx-1m-l2-t036" (1M) or "bx-2m-t035" (2M)
    mode="recurrent",        # "recurrent" or "window"
    width="int32",           # State width: "int32" (Master default), "int16", or "int8"
)
```

- **`cog.load_pvm(path=None, manifest_path=None) -> int`**:
  Admits a compiled `app.n8pv` alongside its 76-byte `manifest.bin` capability descriptor and returns an assigned `domain_id` (`>= 2`). When running inside App Lab, the client includes `st_ino` of `path` so the daemon resolves the exact container app file reliably, and missing/invalid `manifest.bin` raises `EnclaveError` (`CX_OS_E_MANIFEST`).
- **`cog.call_pvm(dom, op, payload=b"") -> bytes`**:
  Synchronously invokes operation `op` inside admitted domain `dom` and returns reply bytes (for example `op=1` ping or `op=0x20` `OP_SENSOR_TICK` with a packed 16-byte `sensor_packet_t`).
- **`cog.turn(prompt, max_bytes=128) -> TurnResult`**:
  Runs an on-device neural turn and returns a `TurnResult`:
  - `.reply` (`str`)
  - `.model` (`str`)
  - `.mode` (`str`)
  - `.width` (`int`): numeric width actually active (`8`, `16`, or `32`)
  - `.state_sha256` (`str`): 64-char SHA-256 digest of live state
  - `.latency_ms` (`float`)
  - `.proposed_act` (`Optional[str]`): action tag proposed by the turn, if any
- **`cog.register_action(act_name, callback)`**:
  Registers a Python callback `callback(act_name)` automatically invoked when `turn()` emits a matching `proposed_act`.
- **`cog.execute()`**:
  Compatibility hook for `arduino.app_utils.App.run()` lifecycles.

---

### 2. `MemoryGraph` (Three-Tier Graph Store)

```python
mem = MemoryGraph(default_tier="episodic", max_hops=2)
```

- **`mem.remember(text, tier=None, importance=0.5) -> int`**:
  Stores a live fact under `"sensory"`, `"episodic"`, or `"semantic"` and returns its integer `memory_id`.
- **`mem.recall(query, limit=8, max_hops=None) -> RecallReport`**:
  Runs a bounded multi-hop query and returns:
  - `.items` (`list[dict[str, object]]`): list of matched memory dictionaries (`{"id": int, "tier": str, "text": str, "importance": float}`)
  - `.truncated` (`bool`): `True` if candidate matches exceeded `limit`
  - `.hopCapped` (`bool`): `True` if graph traversal hit `max_hops`
  - `.fanOutClipped` (`bool`): `True` if branch fan-out was capped
- **`mem.retract(memory_id, retraction_class="standard") -> str`**:
  Retracts a memory unconditionally (`"standard"`, `"instant-undo"`, or `"forensic"`) and returns the updated `state_sha256` digest.

---

### 3. `VisionSaccade` (Foveated Visual Classification)

```python
vis = VisionSaccade(model="vn8v-tin66", saccades=8, confidence_threshold=0.25)
```

- **`vis.look_once() -> VisionLookResult`**:
  Evaluates a foveated pass (`saccades` crops, live camera / host frame buffer—fails explicitly with `EnclaveError: CX_VISION_E_UNAVAILABLE` if the vision engine is offline rather than fabricating stale outputs) and returns:
  - `.class_name` (`str`)
  - `.confidence` (`float`)
  - `.top5` (`list[tuple[str, float]]`)
  - `.saccades` (`int`)
  - `.latency_ms` (`float`)
  - `.model` (`str`), `.mode` (`str`), `.width` (`int`)
- **`@vis.on_classification`**:
  True Python decorator registering `callback(VisionLookResult)` when `.confidence >= confidence_threshold`, and returning `callback` unchanged so the decorated function remains callable.
- **`vis.start_stream(fps=4)`** & **`vis.loop()`**:
  Stream control and `App.run(user_loop=vis.loop)` helper.

---

### 4. `ActPolicy` (Policy-Gated Hardware Actuation)

```python
act = ActPolicy(cooldown_ms=250)
```

- **`act.propose(act_id, *args) -> ActProposalResult`**:
  Evaluates a physical actuation proposal against all 5 policy stages (reserved pin rejection, compiled allowlist, allowed state check, per-actuator monotonic cooldown check, and audit log) and dispatches approved commands over `/var/run/arduino-router.sock` to the STM32U585 bridge:
  - `.approved` (`bool`)
  - `.act_id` (`str`)
  - `.reason` (`str`)
  - `.audit_seq` (`int`)
  Policy violations raise `EnclaveError` with codes including `CX_ACT_E_UNLISTED`, `CX_ACT_E_RESERVED_PIN`, `CX_ACT_E_INVALID_STATE`, or `CX_ACT_E_COOLDOWN`.
- **`act.status() -> list[dict]`**:
  Returns compiled actuator entries (`fan`, `light`, `buzzer`, `matrix.glyph`), their bound GPIO/peripheral targets, allowed states, cooldown window, and reserved pin mask (`7..21,26..42,47..48`).

---

## C Sandbox Authoring (`pvm/n8_sdk.h` & `pvm/sdk_starter_app.c`)

Include [`n8_sdk.h`](../na8ve-developer-sdk/pvm/n8_sdk.h) inside freestanding `pvm/*.c` modules:

### Lifecycle Entrypoints (`N8_EXPORT`)
- `int32_t n8_init(void)`: Initialization hook called once; return `0` on success.
- `int32_t n8_inbox(void)`: Returns the aligned address of `g_inbox[N8_MSG_MAX]` (`1024` bytes).
- `int32_t n8_on_message(int32_t from, int32_t op, int32_t len)`: Message handler (handles `N8_OP_PING` = `0x01`, `OP_SENSOR_TICK` = `0x20`).
- `int32_t pvm_main(int32_t op, int32_t ptr, int32_t len)`: Direct RPC handler invoked by `cog.call_pvm(dom, op, payload)`.

### Host Imports (`N8_IMPORT`)
- `n8_log(msg, len)`: Emit a short diagnostic log line.
- `n8_reply(buf, len)` / `n8_reply_str(str)`: Return bytes to `cog.call_pvm(...)`.
- `n8_ipc_send(target_dom, op, buf, len)`: Send an inter-domain IPC message to an allowed domain (`allowed_ipc`).
- `n8_store_query(query, query_len, k, out, cap)`: Bounded read-only memory lookup (requires `"store"` grant).

### Capability Manifest (`pvm/manifest.json`)

```json
{
  "name": "sdk-starter",
  "dom_id": 2,
  "budget_ms": 50,
  "mem_bytes": 65536,
  "grants": ["store", "act"],
  "allowed_ipc": [1]
}
```

Compile, map imports to the App Lab ABI, sign (`--key ~/.na8ve/app-key.pem` for buyer-paired hardware), strip `.c`/`.h` sources, and pack using `tools/na8ve_applab_tool.py`:

```bash
python tools/na8ve_applab_tool.py pack \
  --app-dir ./na8ve-developer-sdk \
  --key ~/.na8ve/app-key.pem \
  --out ./na8ve-developer-sdk-applab.zip
```
