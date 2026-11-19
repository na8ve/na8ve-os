/* ask's host test: the pVM's own code built natively, this file mocking both the kernel (the host
 * functions, the inbox copy before each n8_on_message) and pVM #1 (the broker's reply, delivered
 * back to ask as a reply message).
 *
 *   cc -Isdk/include examples/broker-app/ask.c examples/broker-app/test_ask.c sdk/src/n8_util.c sdk/src/n8_model.c -o test_ask
 *
 * Built with -DEXPECT_MISMATCH it is its control: the broker answers "ERR broker rate", and the
 * "text received" check must fail. */
#include "n8.h"
#include "n8_model.h"

#include <stdio.h>
#include <string.h>

uint8_t *ask_inbox(void);

static char g_reply[N8_MSG_MAX + 1];
static int32_t g_sent_to = -1, g_sent_op = -1, g_sent_len = -1;
static uint8_t g_sent[N8_MSG_MAX];

/* ---- the kernel, played --------------------------------------------------------------------- */
void n8_log(const char *p, int32_t n) { fprintf(stderr, "pvm: %.*s\n", (int)n, p); }
int64_t n8_now_us(void) { return 1234; }
int32_t n8_flash_read(const char *label, int32_t off, void *dst, int32_t n) { return -1; }
int32_t n8_store_query(const char *q, int32_t qlen, int32_t k, void *out, int32_t cap) { return -1; }
int32_t n8_ipc_send(int32_t to, int32_t op, const void *p, int32_t n)
{
    g_sent_to = to;
    g_sent_op = op;
    g_sent_len = n;
    memcpy(g_sent, p, (size_t)n);
    return 0; /* queued: ask's entry has "allowed_ipc": [1] */
}
int32_t n8_reply(const void *p, int32_t n)
{
    if (n < 0 || n > N8_MSG_MAX) return -1;
    memcpy(g_reply, p, (size_t)n);
    g_reply[n] = 0;
    return 0;
}
int32_t n8_chat_in(void *d, int32_t c) { return -1; }
int32_t n8_emit(const char *p, int32_t n) { return -1; }
int32_t n8_tool(const char *j, int32_t n, char *o, int32_t c) { return -1; }
int32_t n8_session(const char *a, const char *b, int32_t v) { return -1; }
void n8_yield(void) {}

/* a message to ask from `from` */
static const char *deliver(int32_t from, int32_t op, const char *text)
{
    const int32_t n = text ? (int32_t)strlen(text) : 0;
    if (n) memcpy(ask_inbox(), text, (size_t)n);
    g_reply[0] = 0;
    n8_on_message(from, op, n);
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
    expect("ping", deliver(0, N8_OP_PING, NULL), "pong ask");
    expect("nothing yet", deliver(0, 0x11, NULL), "nothing asked");
    expect("ask", deliver(0, 0x10, "greenhouse"), "ok queued");
    /* the request went to pVM #1 as model.turn: [max N8_MODEL_MAX_BYTES][prompt] */
    const int request_ok = g_sent_to == 1 && g_sent_op == N8_OP_MODEL_TURN && g_sent_len == 11 && g_sent[0] == N8_MODEL_MAX_BYTES &&
                           memcmp(g_sent + 1, "greenhouse", 10) == 0;
    g_failed += !request_ok;
    printf("%s request to pVM #1: to=%d op=%d len=%d\n", request_ok ? "ok  " : "FAIL", (int)g_sent_to,
           (int)g_sent_op, (int)g_sent_len);
    expect("pending", deliver(0, 0x11, NULL), "pending");
    expect("busy", deliver(0, 0x10, "again"), "ERR busy");
    /* pVM #1's answer, delivered back as a reply (the op's high bit set) */
#ifdef EXPECT_MISMATCH
    deliver(1, N8_MODEL_REPLY, "ERR broker rate");
#else
    deliver(1, N8_MODEL_REPLY, "turn out=6869 bytes=12 us=900");
#endif
    const int replied_to_reply = g_reply[0] != 0; /* a reply needs no reply */
    g_failed += replied_to_reply;
    printf("%s no reply to the broker's reply\n", replied_to_reply ? "FAIL" : "ok  ");
#ifdef EXPECT_MISMATCH
    const int caught = strcmp(deliver(0, 0x11, NULL), "text hi") != 0;
    printf("control: the broker refuses; text %s\n", caught ? "differs, as required" : "DID NOT DIFFER");
    return caught && g_failed == 0 ? 0 : 1;
#else
    expect("text received", deliver(0, 0x11, NULL), "text hi");
    printf("%s\n", g_failed ? "FAILED" : "PASSED");
    return g_failed ? 1 : 0;
#endif
}
