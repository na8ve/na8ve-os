/*
 * Native Host Test Suite for Arduino Uno Q LED Matrix Streaming App
 *
 * Verifies application lifecycle, Model Broker request routing, asynchronous
 * response ingestion, 12x8 LED framebuffer glyph mapping, and Core 0 actuator
 * proposal dispatch (N8_OP_ACTUATE).
 *
 * Includes mandatory failing negative control twin (-DEXPECT_MISMATCH).
 */
#include "n8.h"
#include "n8_model.h"

#include <stdio.h>
#include <string.h>

/* Application Operations */
#define OP_PROMPT       0x10
#define OP_STATUS       0x11
#define OP_STREAM_STEP  0x12
#define OP_CLEAR        0x13
#define OP_STREAM_ALL   0x14
#define OP_FRAME_ASCII  0x15
#define OP_SCROLL_STEP  0x16

uint8_t *matrix_inbox(void);
const uint8_t *matrix_framebuffer(void);

static char g_reply[N8_MSG_MAX + 1];
static int32_t g_sent_to = -1, g_sent_op = -1, g_sent_len = -1;
static uint8_t g_sent[N8_MSG_MAX];

static int g_actuate_count = 0;
static char g_last_actuate[96];

/* ---- Mock Kernel Services -------------------------------------------- */

void n8_log(const char *p, int32_t n)
{
    fprintf(stderr, "pvm-log: %.*s", (int)n, p);
}

int64_t n8_now_us(void) { return 42000; }
int32_t n8_flash_read(const char *label, int32_t off, void *dst, int32_t n) { return -1; }
int32_t n8_store_query(const char *q, int32_t qlen, int32_t k, void *out, int32_t cap) { return -1; }

int32_t n8_ipc_send(int32_t to, int32_t op, const void *p, int32_t n)
{
    g_sent_to = to;
    g_sent_op = op;
    g_sent_len = n;
    if (n > 0 && n <= N8_MSG_MAX) {
        memcpy(g_sent, p, (size_t)n);
    }
    if (to == 0 && op == N8_OP_ACTUATE) {
        g_actuate_count++;
        int cpy = n < (int32_t)sizeof(g_last_actuate) - 1 ? n : (int32_t)sizeof(g_last_actuate) - 1;
        memcpy(g_last_actuate, p, (size_t)cpy);
        g_last_actuate[cpy] = '\0';
    }
    return 0; /* IPC success (allowed_ipc: [0, 1]) */
}

int32_t n8_reply(const void *p, int32_t n)
{
    if (n < 0 || n > N8_MSG_MAX) return -1;
    memcpy(g_reply, p, (size_t)n);
    g_reply[n] = '\0';
    return 0;
}

int32_t n8_chat_in(void *d, int32_t c) { return -1; }
int32_t n8_emit(const char *p, int32_t n) { return -1; }
int32_t n8_tool(const char *j, int32_t n, char *o, int32_t c) { return -1; }
int32_t n8_session(const char *a, const char *b, int32_t v) { return -1; }
void n8_yield(void) {}

static const char *deliver(int32_t from, int32_t op, const char *text)
{
    const int32_t n = text ? (int32_t)strlen(text) : 0;
    if (n) memcpy(matrix_inbox(), text, (size_t)n);
    g_reply[0] = '\0';
    n8_on_message(from, op, n);
    return g_reply;
}

static int g_failed = 0;

static void expect(const char *what, const char *got, const char *want)
{
    const int ok = strcmp(got, want) == 0;
    g_failed += !ok;
    printf("%s %s: got \"%s\", want \"%s\"\n", ok ? "ok  " : "FAIL", what, got, want);
}

int main(void)
{
    if (n8_init() != 0) {
        printf("FAIL: n8_init failed\n");
        return 1;
    }

    /* 1. Ping */
    expect("ping", deliver(0, N8_OP_PING, NULL), "pong matrix");

    /* 2. Initial Status */
    expect("initial status", deliver(0, OP_STATUS, NULL), "nothing asked");

    /* 3. Send Prompt */
    expect("prompt dispatch", deliver(0, OP_PROMPT, "test prompt"), "ok queued");

    /* Verify IPC routed to Model Broker (pVM #1) */
    int req_ok = (g_sent_to == 1 && g_sent_op == N8_OP_MODEL_TURN &&
                  g_sent_len == 12 && g_sent[0] == 32 &&
                  memcmp(g_sent + 1, "test prompt", 11) == 0);
    g_failed += !req_ok;
    printf("%s broker IPC dispatch (to=1, op=4, len=12)\n", req_ok ? "ok  " : "FAIL");

    /* 4. Pending State */
    expect("pending status", deliver(0, OP_STATUS, NULL), "pending");

    /* 5. Busy Refusal */
    expect("busy rejection", deliver(0, OP_PROMPT, "second prompt"), "ERR busy");

    /* Reset actuator count before broker response */
    g_actuate_count = 0;

    /* 6. Model Broker Inbound Reply */
#ifdef EXPECT_MISMATCH
    deliver(1, N8_MODEL_REPLY, "ERR broker rate");
#else
    /* out=484921 -> 'H'(0x48), 'I'(0x49), '!'(0x21) */
    deliver(1, N8_MODEL_REPLY, "turn out=484921 bytes=16 us=850");
#endif

    const int replied_to_reply = (g_reply[0] != '\0');
    g_failed += replied_to_reply;
    printf("%s no reply sent to broker reply\n", replied_to_reply ? "FAIL" : "ok  ");

#ifdef EXPECT_MISMATCH
    const char *status_reply = deliver(0, OP_STATUS, NULL);
    const int caught = (strcmp(status_reply, "text HI! | stream 1/3") != 0);
    printf("control: broker refusal or mismatch correctly flagged: %s\n",
           caught ? "PASSED (failure caught)" : "FAILED (silent pass)");
    return caught && g_failed == 0 ? 0 : 1;
#else
    /* 7. Verify Auto-Streaming of First Character 'H' */
    expect("auto-streamed status", deliver(0, OP_STATUS, NULL), "text HI! | stream 1/3");

    int act_ok = (g_actuate_count == 1 && strstr(g_last_actuate, "char=H") != NULL);
    g_failed += !act_ok;
    printf("%s first char 'H' actuation proposal dispatched to Core 0 (count=%d)\n",
           act_ok ? "ok  " : "FAIL", g_actuate_count);

    /* Check 12x8 framebuffer columns for 'H' (cols 3..7) */
    const uint8_t *fb = matrix_framebuffer();
    int fb_ok = (fb[0] == 0 && fb[1] == 0 && fb[2] == 0 &&
                 fb[3] == 0x7F && fb[5] == 0x08 && fb[7] == 0x7F &&
                 fb[8] == 0 && fb[11] == 0);
    g_failed += !fb_ok;
    printf("%s 12x8 LED framebuffer glyph mapping verified\n", fb_ok ? "ok  " : "FAIL");

    /* 8. ASCII Frame Visual Verification */
    const char *ascii = deliver(0, OP_FRAME_ASCII, NULL);
    int ascii_ok = (strstr(ascii, "+------------+") != NULL && strstr(ascii, "|...*...*....|") != NULL);
    g_failed += !ascii_ok;
    printf("%s 12x8 ASCII art terminal rendering verified\n", ascii_ok ? "ok  " : "FAIL");

    /* 9. Step to Second Character 'I' */
    expect("step to 'I'", deliver(0, OP_STREAM_STEP, NULL), "char 'I' pos=2/3");
    int act2_ok = (g_actuate_count == 2 && strstr(g_last_actuate, "char=I") != NULL);
    g_failed += !act2_ok;
    printf("%s char 'I' actuation proposal dispatched (count=%d)\n", act2_ok ? "ok  " : "FAIL", g_actuate_count);

    /* 10. Step to Third Character '!' */
    expect("step to '!'", deliver(0, OP_STREAM_STEP, NULL), "char '!' pos=3/3");
    int act3_ok = (g_actuate_count == 3 && strstr(g_last_actuate, "char=!") != NULL);
    g_failed += !act3_ok;
    printf("%s char '!' actuation proposal dispatched (count=%d)\n", act3_ok ? "ok  " : "FAIL", g_actuate_count);

    /* 11. Stream End */
    expect("stream complete", deliver(0, OP_STREAM_STEP, NULL), "stream done");

    /* 12. Marquee Scroll Step */
    expect("marquee scroll step", deliver(0, OP_SCROLL_STEP, NULL), "scroll col=1/30");
    int act4_ok = (g_actuate_count == 4 && strstr(g_last_actuate, "cols=") != NULL);
    g_failed += !act4_ok;
    printf("%s marquee column scroll actuation dispatched (count=%d)\n", act4_ok ? "ok  " : "FAIL", g_actuate_count);

    /* 13. Clear Matrix */
    expect("clear matrix", deliver(0, OP_CLEAR, NULL), "ok cleared");
    int clear_ok = (g_actuate_count == 5 && strstr(g_last_actuate, "state=clear") != NULL);
    g_failed += !clear_ok;
    printf("%s clear matrix proposal dispatched to Core 0 (count=%d)\n", clear_ok ? "ok  " : "FAIL", g_actuate_count);

    printf("\n=== TEST RESULT: %s ===\n", g_failed ? "FAILED" : "PASSED (All assertions verified)");
    return g_failed ? 1 : 0;
#endif
}

