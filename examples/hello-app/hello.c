/* hello: the developer guide's example pVM (`docs/sdk-guide/06-walkthrough-hello-and-broker-examples.md`).
 * It keeps a name between messages, greets with a count and the time, and asks the store about
 * the name through its one grant (`store query r`). Built with `sdk/include`.
 *
 * Ops (its own, from 0x10; op 1 is the convention every pVM answers):
 *   0x01 ping                 -> "pong hello"
 *   0x10 name  <text>         -> "ok"            keeps up to 31 bytes of text as the name
 *   0x11 greet                -> "hello <name>, greeting <n> at <t> us"
 *   0x12 recall               -> the store's rows for the name (needs the store grant), or "ERR store"
 *   anything else             -> "ERR op" */
#include "n8.h"

#include <string.h>

#define OP_NAME 0x10
#define OP_GREET 0x11
#define OP_RECALL 0x12

static uint8_t g_inbox[N8_MSG_MAX]; /* the kernel copies each message here before the call */
static char g_name[32] = "world";   /* kept for the whole boot: a pVM's memory persists between messages */
static uint32_t g_greetings;

N8_EXPORT(n8_init) int32_t n8_init(void) { return 0; }
N8_EXPORT(n8_inbox) int32_t n8_inbox(void) { return (int32_t)(uintptr_t)g_inbox; }

static void set_name(int32_t len)
{
    int n = len < (int32_t)sizeof g_name - 1 ? (int)len : (int)sizeof g_name - 1;
    while (n > 0 && (g_inbox[n - 1] == '\n' || g_inbox[n - 1] == ' ')) n--;
    if (n == 0) return (void)n8_reply_str("ERR empty name");
    memcpy(g_name, g_inbox, (size_t)n);
    g_name[n] = 0;
    n8_reply_str("ok");
}

static void greet(void)
{
    char r[96];
    int at = 0;
    g_greetings++;
    n8_put(r, &at, sizeof r, "hello ");
    n8_put(r, &at, sizeof r, g_name);
    n8_put(r, &at, sizeof r, ", greeting ");
    n8_put_u(r, &at, sizeof r, g_greetings);
    n8_put(r, &at, sizeof r, " at ");
    n8_put_u(r, &at, sizeof r, (uint64_t)n8_now_us());
    n8_put(r, &at, sizeof r, " us");
    n8_reply_str(r);
}

static void recall(void)
{
    static char rows[N8_MSG_MAX - 16];
    /* without a `store` grant this call contains the pVM: the kernel never returns here */
    const int32_t n = n8_store_query(g_name, (int32_t)strlen(g_name), 3, rows, sizeof rows - 1);
    if (n < 0) return (void)n8_reply_str("ERR store");
    if (n == 0) return (void)n8_reply_str("no memories");
    n8_reply(rows, n);
}

N8_EXPORT(n8_on_message) int32_t n8_on_message(int32_t from, int32_t op, int32_t len)
{
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

#if N8_TEST_BUILD
uint8_t *hello_inbox(void) { return g_inbox; } /* for the host test, which plays the kernel */
#endif
