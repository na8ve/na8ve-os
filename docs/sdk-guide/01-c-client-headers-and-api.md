# 01 — C Client Headers & System API Reference

The core application interface is defined in [`sdk/n8.h`](../../sdk/) and accompanied by operation definitions in [`sdk/n8_ops.h`](../../sdk/). 

This document provides the exhaustive specification of all exported application symbols, kernel host imports, error conventions, and operation codes.

---

## 1. Compiler Directives & Linkage Macros

When compiling for WebAssembly target (`__wasm__`), the SDK annotates symbols with Clang/LLVM attribute directives:

```c
#if defined(__wasm__) && !defined(N8_HOST_TEST)
#define N8_IMPORT(name) __attribute__((import_module("na8ve"), import_name(#name)))
#define N8_EXPORT(name) __attribute__((export_name(#name)))
#else
#define N8_IMPORT(name)
#define N8_EXPORT(name)
#endif
```

* In **Wasm builds**, every imported host function is bound to the `na8ve` Wasm import module.
* In **Host test builds** (`N8_HOST_TEST` or native compilation), the macros collapse to standard C declarations, allowing unit test files to provide mock implementations without linker errors.

---

## 2. Mandatory Application Exports

Every na8ve-os pVM binary must export exactly three entrypoints. If any of these symbols are missing, the kernel's loader (`cx_os.c` or `unoq_pvm_guest.c`) refuses the module:

### 2.1 `n8_init`
```c
N8_EXPORT(n8_init) int32_t n8_init(void);
```
* **Purpose:** Called once at boot time (or on module reload) before any incoming messages are delivered.
* **Return Value:** Must return `0` on success. Returning a non-zero value causes the kernel to fail-stop the pVM (`CX_FAULT_INIT_FAILED`).
* **Constraints:** Must not perform long-running loops or blocking I/O; subject to the boot budget (typically 500 ms).

### 2.2 `n8_inbox`
```c
N8_EXPORT(n8_inbox) int32_t n8_inbox(void);
```
* **Purpose:** Returns the linear memory offset (address) of the application's statically allocated receive buffer.
* **Return Value:** Memory address `(int32_t)(uintptr_t)g_inbox`.
* **Buffer Requirements:** The backing array must be at least `N8_MSG_MAX` (1,024 bytes) in size and aligned to 4 bytes:
  ```c
  static uint8_t g_inbox[N8_MSG_MAX] __attribute__((aligned(4)));
  ```

### 2.3 `n8_on_message`
```c
N8_EXPORT(n8_on_message) int32_t n8_on_message(int32_t from, int32_t op, int32_t len);
```
* **Purpose:** Message dispatch loop called whenever a message arrives.
* **Parameters:**
  * `from`: The sender's pVM ID (`0` represents the kernel/console; `1` represents pVM #1 `cortex-mvp`; `2+` represent peer pVMs).
  * `op`: The 32-bit operation identifier (see §4).
  * `len`: Number of valid payload bytes present in the inbox (`0 <= len <= 1024`).
* **Return Value:** Returns `0` on standard completion, or non-zero to report an unhandled fault.

---

## 3. Kernel Host Imports (Mediated Services)

Host services are invoked as direct C function calls. Under the hood, the kernel reference monitor checks the caller's manifest grants on every invocation.

### 3.1 System Services (Universal Authority)

#### `n8_log`
```c
N8_IMPORT(log) void n8_log(const char *p, int32_t n);
```
* **Description:** Writes `n` bytes from buffer `p` to the kernel console output ring.
* **Constraints:** Output is automatically prefixed with the pVM name and line-clipped to 256 bytes per call.

#### `n8_now_us`
```c
N8_IMPORT(now_us) int64_t n8_now_us(void);
```
* **Description:** Returns the monotonic system uptime in microseconds since boot.
* **Hardware source:** On Uno Q, reads ARMv8 Generic Timer (`CNTVCT_EL0`); on ESP32-S3, reads `esp_timer_get_time()`.

### 3.2 Inter-Process Communication (IPC)

#### `n8_ipc_send`
```c
N8_IMPORT(ipc_send) int32_t n8_ipc_send(int32_t to, int32_t op, const void *p, int32_t n);
```
* **Description:** Asynchronously queues a message to destination `to` with operation `op` and payload `p` (`n` bytes).
* **Security Check:** Gated strictly by the caller's manifest `allowed_ipc` array.
* **Return Value:**
  * `0`: Message successfully queued in receiver's ring buffer.
  * `-1` (`CX_FAULT_IPC_DENIED`): Caller manifest does not allow sending to `to`. The calling pVM is placed into fail-stop containment.
  * `-2` (`CX_FAULT_QUEUE_FULL`): Destination queue is full.

#### `n8_reply`
```c
N8_IMPORT(reply) int32_t n8_reply(const void *p, int32_t n);
```
* **Description:** Sends an in-place response to the sender of the active `n8_on_message` call.
* **Constraints:** Must only be called while handling a message. Payload length $n \le 1024$ bytes.
* **Return Value:** `0` on success, or negative on buffer overflow.

### 3.3 Storage & Memory Graph

#### `n8_store_query`
```c
N8_IMPORT(store_query) int32_t n8_store_query(const char *q, int32_t qlen, int32_t k, void *out, int32_t cap);
```
* **Description:** Executes a semantic recall search query `q` against the on-board SQLite memory graph.
* **Security Check:** Requires manifest grant: `{"kind": "store", "label": "query", "rights": "r"}`.
* **Parameters:**
  * `q`: Query string (entity name, tag, or semantic phrase).
  * `qlen`: Length of query string ($\le 64$ bytes).
  * `k`: Maximum matches to return ($1 \le k \le 8$).
  * `out`: Destination buffer for newline-delimited result records (`id=<n> score=<f>`).
  * `cap`: Buffer capacity ($\ge 256$ bytes recommended).
* **Return Value:** Number of bytes written to `out`, or `-1` if access is denied.

### 3.4 Flash Read Access

#### `n8_flash_read`
```c
N8_IMPORT(flash_read) int32_t n8_flash_read(const char *label, int32_t off, void *dst, int32_t n);
```
* **Description:** Reads `n` bytes from partition `label` at offset `off` into `dst`.
* **Security Check:** Requires manifest grant: `{"kind": "flash", "label": "<label>", "rights": "r"}`.

---

## 4. Operation Codes Reference (`n8_ops.h`)

Operation codes classify the semantics of messages passed between the kernel, the console, and pVMs:

| Op Code | Identifier | Direction | Semantics |
|---|---|---|---|
| `0x00000001` | `N8_OP_PING` | Inbound | Ping diagnostic. App replies with uptime or status. |
| `0x00000004` | `N8_OP_MODEL_TURN` | Inbound | Request a neural inference turn from the model broker. |
| `0x80000004` | `N8_MODEL_REPLY` | Inbound | Response from broker carrying generated text. |
| `0x00000010` .. `0x000000FF` | User Defined | Custom | Application-specific operation codes. |

---

## 5. SDK Helper Routines

To ensure small binary footprints without needing standard `printf` libraries, `n8.h` provides minimal string formatting helpers:

```c
/* Write string to reply buffer */
int32_t n8_reply_str(const char *s);

/* Safe string formatting without dynamic memory allocation */
void n8_put(char *b, int *at, int cap, const char *s);
void n8_put_u(char *b, int *at, int cap, uint64_t v);
void n8_put_hex(char *b, int *at, int cap, const uint8_t *p, int n);
```

#### Example Usage
```c
char buf[128];
int at = 0;
n8_put(buf, &at, sizeof(buf), "result status=ok count=");
n8_put_u(buf, &at, sizeof(buf), 42);
n8_put(buf, &at, sizeof(buf), " hash=");
n8_put_hex(buf, &at, sizeof(buf), hash_bytes, 8);
n8_reply(buf, at);
```

