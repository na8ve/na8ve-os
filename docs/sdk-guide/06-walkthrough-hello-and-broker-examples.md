# 06 — End-to-End App Walkthroughs: `hello-pvm` & `broker-pvm`

This guide walks through building, testing, signing, and running two canonical reference applications included with the SDK:

1. **`hello-pvm`** ([`examples/hello-pvm/`](../../examples/hello-app/)): A stateful app that stores a user name in linear memory across messages, greets with a monotonic timestamp, and queries semantic memories from SQLite using its manifest grant (`store query r`).
2. **`broker-pvm`** ([`examples/broker-pvm/`](../../examples/broker-app/)): A cognitive client app that holds no model privileges and asynchronously delegates neural text generation to pVM #1 (`cortex-mvp`) via the Model Broker API (`n8_model.h`).

---

## 1. Walkthrough 1: `hello-pvm`

### 1.1 Manifest Entry (`manifest-entry.json`)
```json
{
  "id": 2,
  "name": "hello",
  "partition": "pvm_1",
  "core": 0,
  "payload": "hello.n8pv",
  "mem_linear": 65536,
  "stack": 8192,
  "budget_ms": 2000,
  "allowed_ipc": [],
  "grants": [
    {"kind": "store", "label": "query", "rights": "r"}
  ]
}
```
* **Memory Ceiling:** 64 KiB (`mem_linear`).
* **Operand Stack:** 8 KiB shadow stack at address `0x0`.
* **Grants:** Granted read access to semantic queries (`store query r`).

### 1.2 Implementation Highlights (`hello.c`)
```c
#include "n8.h"
#include <string.h>

#define OP_NAME   0x10
#define OP_GREET  0x11
#define OP_RECALL 0x12

static uint8_t g_inbox[N8_MSG_MAX];
static char g_name[32] = "world";   /* State persists across messages */
static uint32_t g_greetings;

N8_EXPORT(n8_init) int32_t n8_init(void) { return 0; }
N8_EXPORT(n8_inbox) int32_t n8_inbox(void) { return (int32_t)(uintptr_t)g_inbox; }

static void set_name(int32_t len) {
    int n = len < (int32_t)sizeof(g_name) - 1 ? len : (int32_t)sizeof(g_name) - 1;
    while (n > 0 && (g_inbox[n - 1] == '\n' || g_inbox[n - 1] == ' ')) n--;
    if (n == 0) return (void)n8_reply_str("ERR empty name");
    memcpy(g_name, g_inbox, (size_t)n);
    g_name[n] = '\0';
    n8_reply_str("ok");
}

static void greet(void) {
    char r[96];
    int at = 0;
    g_greetings++;
    n8_put(r, &at, sizeof(r), "hello ");
    n8_put(r, &at, sizeof(r), g_name);
    n8_put(r, &at, sizeof(r), ", greeting ");
    n8_put_u(r, &at, sizeof(r), g_greetings);
    n8_put(r, &at, sizeof(r), " at ");
    n8_put_u(r, &at, sizeof(r), (uint64_t)n8_now_us());
    n8_put(r, &at, sizeof(r), " us");
    n8_reply_str(r);
}

static void recall(void) {
    static char rows[N8_MSG_MAX - 16];
    /* Without a `store` grant, calling this triggers containment fault */
    const int32_t n = n8_store_query(g_name, (int32_t)strlen(g_name), 3, rows, sizeof(rows) - 1);
    if (n < 0) return (void)n8_reply_str("ERR store");
    if (n == 0) return (void)n8_reply_str("no memories");
    n8_reply(rows, n);
}

N8_EXPORT(n8_on_message) int32_t n8_on_message(int32_t from, int32_t op, int32_t len) {
    (void)from;
    if (len < 0 || len > N8_MSG_MAX) return n8_reply_str("ERR len"), 0;
    switch (op) {
    case N8_OP_PING: n8_reply_str("pong hello"); break;
    case OP_NAME: set_name(len); break;
    case OP_GREET: greet(); break;
    case OP_RECALL: recall(); break;
    default: n8_reply_str("ERR op");
    }
    return 0;
}
```

### 1.3 Native Host Testing
```bash
# Compile and run positive test
gcc -I sdk/include \
    examples/hello-app/hello.c \
    examples/hello-app/test_hello.c \
    sdk/src/n8_util.c \
    -o test_hello

./test_hello
# Output:
# ok   ping: pong hello
# ok   default greet: hello world, greeting 1 at 1234 us
# ok   name: ok
# ok   named greet: hello Ada, greeting 2 at 1234 us
# ok   recall: id=7 score=0.9100
# PASSED

# Compile and run negative control twin
gcc -I sdk/include \
    examples/hello-app/hello.c \
    examples/hello-app/test_hello.c \
    sdk/src/n8_util.c \
    -DEXPECT_MISMATCH \
    -o test_hello_control

./test_hello_control
# Output: control: the store answers nothing; recall differs, as required
```

---

## 2. Walkthrough 2: `broker-pvm`

### 2.1 Manifest Entry (`manifest-entry.json`)
```json
{
  "id": 2,
  "name": "ask",
  "partition": "pvm_1",
  "core": 0,
  "payload": "ask.n8pv",
  "mem_linear": 65536,
  "stack": 8192,
  "budget_ms": 2000,
  "allowed_ipc": [1],
  "grants": []
}
```
* **Grants:** `[]` (empty: zero hardware or storage grants).
* **`allowed_ipc`:** `[1]` (specifically entitled to message pVM #1 `cortex-mvp`).

### 2.2 Implementation Highlights (`ask.c`)
```c
#include "n8.h"
#include "n8_model.h"

#define OP_ASK    0x10
#define OP_ANSWER 0x11

static uint8_t g_inbox[N8_MSG_MAX];
static char g_text[N8_MODEL_MAX_BYTES + 1];
static int32_t g_status = 1; /* 1: nothing asked; 0: received; negative: error */

N8_EXPORT(n8_init) int32_t n8_init(void) { return 0; }
N8_EXPORT(n8_inbox) int32_t n8_inbox(void) { return (int32_t)(uintptr_t)g_inbox; }

static void ask(int32_t len) {
    /* Queue a turn to pVM #1 requesting at most 16 generated tokens */
    const int32_t rc = n8_model_request((const char *)g_inbox, len, 16);
    if (rc == N8_MODEL_E_BUSY) return (void)n8_reply_str("ERR busy");
    if (rc == N8_MODEL_E_SIZE) return (void)n8_reply_str("ERR size");
    if (rc != 0) return (void)n8_reply_str("ERR gate");
    g_status = 1;
    n8_reply_str("ok queued");
}

static void answer(void) {
    char r[96];
    int at = 0;
    if (n8_model_pending()) return (void)n8_reply_str("pending");
    if (g_status == 1) return (void)n8_reply_str("nothing asked");
    if (g_status < 0) {
        n8_put(r, &at, sizeof(r), "ERR ");
        n8_put(r, &at, sizeof(r), g_status == N8_MODEL_E_RATE ? "rate" : "broker");
        return (void)n8_reply_str(r);
    }
    n8_put(r, &at, sizeof(r), "text ");
    n8_put(r, &at, sizeof(r), g_text);
    n8_reply_str(r);
}

N8_EXPORT(n8_on_message) int32_t n8_on_message(int32_t from, int32_t op, int32_t len) {
    if (len < 0 || len > N8_MSG_MAX) return n8_reply_str("ERR len"), 0;

    /* Catch asynchronous completion from the model broker */
    if (op == N8_MODEL_REPLY && from == N8_MODEL_BROKER) {
        const int32_t n = n8_model_parse(g_inbox, len, g_text, sizeof(g_text));
        g_status = n < 0 ? n : 0;
        return 0; /* Replies need no reply of their own */
    }

    switch (op) {
    case N8_OP_PING: n8_reply_str("pong ask"); break;
    case OP_ASK: ask(len); break;
    case OP_ANSWER: answer(); break;
    default: n8_reply_str("ERR op");
    }
    return 0;
}
```

### 2.3 On-Board Interaction via the TUI / Console
Once flashed to the device, applications are controlled through the console using `os-call`:

```text
# 1. Ping the app in slot 2
os-call 2 1
> pong ask
OK

# 2. Submit a prompt to generate tokens
os-call 2 0x10 "greenhouse temperature"
> ok queued
OK

# 3. Check for completion
os-call 2 0x11
> text  is regulated at 24C
OK
```
If the app submits a prompt within 500 ms of the previous request, the broker immediately rejects it:
```text
os-call 2 0x10 "rapid fire"
> ok queued
OK
os-call 2 0x11
> ERR rate
OK
```
This demonstrates the complete, end-to-end security mediation enforced by the na8ve-os Model Broker!

