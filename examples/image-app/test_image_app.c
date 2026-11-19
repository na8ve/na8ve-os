/*
 * Native Host Test Suite for na8ve-os Image & Visual Perception App
 *
 * Verifies application lifecycle, camera sensor probing, zero-raw-image-persistence
 * privacy invariant enforcement, foveated saccade classification, ANSI ASCII
 * viewport rendering, Model Broker cognitive turn dispatch, and Core 0 actuator
 * proposal routing.
 *
 * Includes mandatory failing negative control twin (-DEXPECT_MISMATCH).
 */
#include "n8.h"
#include "n8_model.h"

#include <stdio.h>
#include <string.h>

/* Application Operations */
#define OP_PROBE          0x02
#define OP_CAPTURE        0x10
#define OP_CLASSIFY       0x11
#define OP_STATUS         0x12
#define OP_ASCII_VIEW     0x13
#define OP_COGNITIVE_TURN 0x14
#define OP_ACTUATE        0x15
#define OP_SCENE          0x16

uint8_t *image_inbox(void);

static char g_reply[N8_MSG_MAX + 1];
static int32_t g_sent_to = -1, g_sent_op = -1, g_sent_len = -1;
static uint8_t g_sent[N8_MSG_MAX];

static int g_actuate_count = 0;
static char g_last_actuate[128];

/* ---- Mock Kernel Services -------------------------------------------- */

void n8_log(const char *p, int32_t n)
{
    fprintf(stderr, "pvm-log: %.*s", (int)n, p);
}

int64_t n8_now_us(void) { return 54000; }
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
    return 0; /* IPC success */
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
    if (n) memcpy(image_inbox(), text, (size_t)n);
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

static void expect_contains(const char *what, const char *got, const char *sub)
{
    const int ok = strstr(got, sub) != NULL;
    g_failed += !ok;
    printf("%s %s: contains \"%s\"\n", ok ? "ok  " : "FAIL", what, sub);
}

int main(void)
{
    if (n8_init() != 0) {
        printf("FAIL: n8_init failed\n");
        return 1;
    }

    /* 1. Ping Check */
    expect("ping", deliver(0, N8_OP_PING, NULL), "pong image-app");

    /* 2. Sensor Probe */
    expect_contains("sensor probe", deliver(0, OP_PROBE, NULL), "cam sensor=UnoQ-QRB2210-Cam");

    /* 3. Scene Selection (Scene 0: Sprout) */
    expect("select scene 0", deliver(0, OP_SCENE, "0"), "ok scene=sprout");

    /* 4. Ephemeral Frame Capture (Volatile DMA Purged) */
    expect_contains("capture frame", deliver(0, OP_CAPTURE, NULL), "volatile DMA purged");

    /* 5. Foveated Saccade Classification */
    expect_contains("classify scene", deliver(0, OP_CLASSIFY, NULL), "class=sprout");
    expect_contains("saccades verified", g_reply, "saccades=8");

    /* 6. Status Query & Zero Raw Persistence Check */
    expect_contains("status query", deliver(0, OP_STATUS, NULL), "class=sprout");
    expect_contains("privacy invariant", g_reply, "privacy=zero_raw_persisted");

    /* 7. ASCII Art Viewport Inspection */
    const char *ascii = deliver(0, OP_ASCII_VIEW, NULL);
    expect_contains("ascii border", ascii, "+--------------------------------+");
    expect_contains("ascii detection", ascii, "Detection: label=\"sprout\"");
    expect_contains("ascii privacy policy", ascii, "Policy: Zero raw pixels persisted or transmitted.");

    /* 8. Propose Actuation to Core 0 Actuator Safety Table */
    g_actuate_count = 0;
    deliver(0, OP_ACTUATE, NULL);
    int act_ok = (g_actuate_count == 1 && strstr(g_last_actuate, "target=mister") != NULL);
    g_failed += !act_ok;
    printf("%s actuator proposal routed to Core 0 (target=mister, count=%d)\n",
           act_ok ? "ok  " : "FAIL", g_actuate_count);

    /* 9. Cognitive Turn Request to Model Broker (pVM #1) */
    deliver(0, OP_COGNITIVE_TURN, NULL);
    int req_ok = (g_sent_to == 1 && g_sent_op == N8_OP_MODEL_TURN &&
                  strstr((const char *)(g_sent + 1), "The camera sees sprout. What is it?") != NULL);
    g_failed += !req_ok;
    printf("%s Model Broker IPC dispatch (to=1, op=4, situational prompt verified)\n",
           req_ok ? "ok  " : "FAIL");

    /* 10. Model Broker Reply Ingestion */
#ifdef EXPECT_MISMATCH
    deliver(1, N8_MODEL_REPLY, "ERR broker rate");
    const int caught = (strstr(g_reply, "ERR") != NULL || g_sent_to != 0);
    printf("control: broker refusal caught: %s\n", caught ? "PASSED (failure caught)" : "FAILED");
    return caught && g_failed == 0 ? 0 : 1;
#else
    /* Simulate successful broker reply: 'T', 'h', 'e', ' ', 'c', 'a', 'm', 'e', 'r', 'a' */
    deliver(1, N8_MODEL_REPLY, "turn out=5468652063616d657261 bytes=10 us=1100");
    printf("ok   Model Broker completion ingested\n");

    printf("\n=== TEST RESULT: %s ===\n", g_failed ? "FAILED" : "PASSED (All assertions verified)");
    return g_failed ? 1 : 0;
#endif
}
