/* hello's host test (`docs/sdk-guide/04-host-testing-and-negative-controls.md`): the pVM's own code
 * built natively, with this file mocking the host imports before each n8_on_message dispatch.
 *
 *   cc -Isdk/include examples/hello-app/hello.c examples/hello-app/test_hello.c sdk/src/n8_util.c -o test_hello
 *
 * Built with -DEXPECT_MISMATCH it is its control: the store answers nothing, and the recall check
 * must fail. */
#include "n8.h"

#include <stdio.h>
#include <string.h>

uint8_t *hello_inbox(void);

static char g_reply[N8_MSG_MAX + 1];
static int g_store_calls;

/* ---- the kernel, played: the host functions ---------------------------------------------- */
void n8_log(const char *p, int32_t n) { fprintf(stderr, "pvm: %.*s\n", (int)n, p); }
int64_t n8_now_us(void) { return 1234; }
int32_t n8_flash_read(const char *label, int32_t off, void *dst, int32_t n) { return -1; }
int32_t n8_ipc_send(int32_t to, int32_t op, const void *p, int32_t n) { return -1; }
int32_t n8_store_query(const char *q, int32_t qlen, int32_t k, void *out, int32_t cap)
{
    g_store_calls++;
#ifdef EXPECT_MISMATCH
    return 0;
#else
    const char rows[] = "id=7 score=0.9100\n";
    if (qlen != 3 || memcmp(q, "Ada", 3) != 0 || k != 3 || cap < (int32_t)sizeof rows) return -1;
    memcpy(out, rows, sizeof rows - 1);
    return (int32_t)sizeof rows - 1;
#endif
}
int32_t n8_reply(const void *p, int32_t n)
{
    if (n < 0 || n > N8_MSG_MAX) return -1;
    memcpy(g_reply, p, (size_t)n);
    g_reply[n] = 0;
    return 0;
}

/* the SDK declares these; hello does not call them */
int32_t n8_chat_in(void *d, int32_t c) { return -1; }
int32_t n8_emit(const char *p, int32_t n) { return -1; }
int32_t n8_tool(const char *j, int32_t n, char *o, int32_t c) { return -1; }
int32_t n8_session(const char *a, const char *b, int32_t v) { return -1; }
void n8_yield(void) {}

/* ---- one message, as the runner delivers it ------------------------------------------------ */
static const char *send(int32_t op, const char *text)
{
    const int32_t n = text ? (int32_t)strlen(text) : 0;
    if (n) memcpy(hello_inbox(), text, (size_t)n);
    g_reply[0] = 0;
    n8_on_message(0, op, n);
    return g_reply;
}

static int g_failed;
static void expect(const char *what, const char *got, const char *want)
{
    const int ok = strcmp(got, want) == 0;
    g_failed += !ok;
    printf("%s %s: %s\n", ok ? "ok  " : "FAIL", what, got);
}

int main(void)
{
    if (n8_init() != 0) return 1;
    expect("ping", send(N8_OP_PING, NULL), "pong hello");
    expect("greet", send(0x11, NULL), "hello world, greeting 1 at 1234 us");
    expect("name", send(0x10, "Ada\n"), "ok");
    expect("greet", send(0x11, NULL), "hello Ada, greeting 2 at 1234 us");
    expect("unknown op", send(0x7f, NULL), "ERR op");
#ifdef EXPECT_MISMATCH
    const int caught = strcmp(send(0x12, NULL), "id=7 score=0.9100\n") != 0;
    printf("control: the store answers nothing; recall %s\n", caught ? "differs, as required" : "DID NOT DIFFER");
    return caught && g_failed == 0 ? 0 : 1;
#else
    expect("recall", send(0x12, NULL), "id=7 score=0.9100\n");
    printf("%s (%d store call)\n", g_failed ? "FAILED" : "PASSED", g_store_calls);
    return g_failed ? 1 : 0;
#endif
}
