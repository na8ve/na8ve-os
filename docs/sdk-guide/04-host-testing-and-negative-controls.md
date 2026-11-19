# 04 — Host Testing & Negative Controls

Developing applications directly on embedded microcontrollers slows iteration and makes automated regression testing fragile. The **na8ve-os SDK** embraces the **Cortex Standard of Evidence**:

1. **Host-Native Execution:** The application's core logic compiles natively against standard host C compilers (MinGW `gcc`/`clang` on Windows, GCC/Clang on Linux) before touching device silicon.
2. **Every Test Has a Failing Control Twin:** A test that cannot fail proves nothing. Every test suite includes a negative control build (e.g. `-DEXPECT_MISMATCH`) simulating an invariant breach or error condition; the control **must** fail or exit with a non-zero code to confirm the test harness is genuinely verifying behavior.

---

## 1. How Host Testing Works (`N8_TEST_BUILD`)

In [`sdk/n8.h`](../../sdk/):

```c
#if !defined(__wasm__) || defined(N8_HOST_TEST)
#define N8_TEST_BUILD 1
#else
#define N8_TEST_BUILD 0
#endif
```

* When compiling for host testing, `N8_IMPORT` and `N8_EXPORT` collapse to standard C linkage.
* The test harness file (e.g., `test_app.c`) defines `main()` and supplies mock implementations of the host kernel functions (`n8_log`, `n8_now_us`, `n8_store_query`, `n8_ipc_send`, `n8_reply`).

---

## 2. Emulating the Kernel Message Loop

To match the on-board hardware behavior, the host test harness must emulate the kernel runner's **TOCTOU-safe** message delivery:

1. Retrieve the app's inbox address via `app_inbox()`.
2. Copy the incoming message payload into the inbox buffer.
3. Call `n8_on_message(from, op, len)`.
4. Capture the app's response emitted via `n8_reply()`.

```c
static char g_reply[N8_MSG_MAX + 1];

/* Mock implementation of n8_reply */
int32_t n8_reply(const void *p, int32_t n) {
    if (n < 0 || n > N8_MSG_MAX) return -1;
    memcpy(g_reply, p, (size_t)n);
    g_reply[n] = 0;
    return 0;
}

/* Helper emulating the kernel runner's delivery */
static const char *deliver(int32_t from, int32_t op, const char *text) {
    const int32_t n = text ? (int32_t)strlen(text) : 0;
    if (n > 0) {
        memcpy(my_app_inbox(), text, (size_t)n);
    }
    g_reply[0] = '\0';
    n8_on_message(from, op, n);
    return g_reply;
}
```

---

## 3. Mocking Kernel Host Services

A minimal test harness stubs the host functions the application is entitled to use:

```c
/* Mock logging: redirect to stderr */
void n8_log(const char *p, int32_t n) {
    fprintf(stderr, "[pVM LOG] %.*s\n", (int)n, p);
}

/* Mock timer */
int64_t n8_now_us(void) {
    return 1000000; /* Fixed 1.0s timestamp */
}

/* Mock semantic store query */
int32_t n8_store_query(const char *q, int32_t qlen, int32_t k, void *out, int32_t cap) {
#ifdef EXPECT_MISMATCH
    /* Negative control: database answers nothing */
    return 0;
#else
    const char mock_row[] = "id=42 score=0.9850\n";
    if (qlen == 5 && memcmp(q, "light", 5) == 0) {
        memcpy(out, mock_row, sizeof(mock_row) - 1);
        return (int32_t)(sizeof(mock_row) - 1);
    }
    return 0;
#endif
}

/* Mock IPC send: capture message queued for peer */
static int32_t g_last_to, g_last_op;
static uint8_t g_last_payload[N8_MSG_MAX];

int32_t n8_ipc_send(int32_t to, int32_t op, const void *p, int32_t n) {
    g_last_to = to;
    g_last_op = op;
    memcpy(g_last_payload, p, (size_t)n);
    return 0; /* Simulated queue success */
}
```

---

## 4. Designing Negative Controls (`-DEXPECT_MISMATCH`)

A negative control deliberately violates an invariant to prove that the test suite actually inspects the output:

```c
int main(void) {
    if (n8_init() != 0) return 1;

    /* Positive assertion */
    const char *resp = deliver(0, 0x10, "test_query");

#ifdef EXPECT_MISMATCH
    /* In the control build, the mock engine corrupted the response.
     * The test MUST observe that the response is NOT the expected string. */
    int caught = (strcmp(resp, "expected_result") != 0);
    printf("Control run: %s\n", caught ? "PASSED (failure was caught)" : "FAILED (silent pass!)");
    return caught ? 0 : 1;
#else
    if (strcmp(resp, "expected_result") != 0) {
        fprintf(stderr, "FAIL: got '%s', want 'expected_result'\n", resp);
        return 1;
    }
    printf("PASSED\n");
    return 0;
#endif
}
```

---

## 5. Building and Running Host Tests

### 5.1 Native Compilation Command (MinGW / GCC)
```bash
# 1. Compile and run positive test suite
gcc -I firmware/pvm/sdk \
    examples/hello-pvm/hello.c \
    examples/hello-pvm/test_hello.c \
    firmware/pvm/sdk/n8_util.c \
    -o test_hello

./test_hello
# Expected exit code: 0

# 2. Compile and run negative control twin
gcc -I firmware/pvm/sdk \
    examples/hello-pvm/hello.c \
    examples/hello-pvm/test_hello.c \
    firmware/pvm/sdk/n8_util.c \
    -DEXPECT_MISMATCH \
    -o test_hello_control

./test_hello_control
# Expected exit code: 0 (verifying control failure caught)
```

### 5.2 Automated CMake Test Integration
In `core-host/CMakeLists.txt`, test targets are registered using `cx_test()`:
```cmake
cx_test(test_hello 
    SRC examples/hello-pvm/hello.c examples/hello-pvm/test_hello.c
    LIBS cx_platform
)
```
This automatically builds and executes both `test_hello` and `test_hello_control` during `ctest`.

