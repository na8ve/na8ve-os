/* ask: an app that holds no accelerator grant and asks pVM #1 for a model turn through the broker
 * (`docs/sdk-guide/06-walkthrough-hello-and-broker-examples.md`). Op 0x10 with a prompt queues a turn;
 * the answer arrives later as a reply message; op 0x11 returns what came back. */
#include "n8.h"
#include "n8_model.h"

#include <string.h>

#define OP_ASK 0x10
#define OP_ANSWER 0x11

static uint8_t g_inbox[N8_MSG_MAX];
static char g_text[N8_MODEL_MAX_BYTES + 1];
static int32_t g_status = 1; /* 1: nothing asked yet; 0: text received; negative: N8_MODEL_E_* */

N8_EXPORT(n8_init) int32_t n8_init(void) { return 0; }
N8_EXPORT(n8_inbox) int32_t n8_inbox(void) { return (int32_t)(uintptr_t)g_inbox; }

static void ask(int32_t len)
{
    const int32_t rc = n8_model_request((const char *)g_inbox, len, N8_MODEL_MAX_BYTES);
    if (rc == N8_MODEL_E_BUSY) return (void)n8_reply_str("ERR busy");
    if (rc == N8_MODEL_E_SIZE) return (void)n8_reply_str("ERR size");
    if (rc != 0) return (void)n8_reply_str("ERR gate");
    g_status = 1;
    n8_reply_str("ok queued");
}

static void answer(void)
{
    char r[96];
    int at = 0;
    if (n8_model_pending()) return (void)n8_reply_str("pending");
    if (g_status == 1) return (void)n8_reply_str("nothing asked");
    if (g_status < 0) {
        n8_put(r, &at, sizeof r, "ERR ");
        n8_put(r, &at, sizeof r, g_status == N8_MODEL_E_RATE ? "rate" : g_status == N8_MODEL_E_MODEL ? "no-model" : "broker");
        return (void)n8_reply_str(r);
    }
    n8_put(r, &at, sizeof r, "text ");
    n8_put(r, &at, sizeof r, g_text);
    n8_reply_str(r);
}

N8_EXPORT(n8_on_message) int32_t n8_on_message(int32_t from, int32_t op, int32_t len)
{
    if (len < 0 || len > N8_MSG_MAX) return n8_reply_str("ERR len"), 0;
    if (op == N8_MODEL_REPLY && from == N8_MODEL_BROKER) {
        /* the broker's answer: a reply needs no reply of its own */
        const int32_t n = n8_model_parse(g_inbox, len, g_text, sizeof g_text);
        g_status = n < 0 ? n : 0;
        return 0;
    }
    switch (op) {
    case N8_OP_PING: n8_reply_str("pong ask"); break;
    case OP_ASK: ask(len); break;
    case OP_ANSWER: answer(); break;
    default: n8_reply_str("ERR op");
    }
    return 0;
}

#if N8_TEST_BUILD
uint8_t *ask_inbox(void) { return g_inbox; } /* for the host test, which plays the kernel */
#endif
