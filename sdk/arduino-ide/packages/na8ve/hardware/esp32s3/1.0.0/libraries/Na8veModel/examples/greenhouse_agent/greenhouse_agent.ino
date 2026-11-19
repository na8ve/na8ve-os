/* greenhouse_agent.ino - Sandboxed pVM application for Seeed XIAO ESP32-S3 Sense */
#include <Na8veOS.h>
#include <Na8veModel.h>
#include <Na8veStore.h>
#include <Na8veAct.h>
#include <Na8veSeam.h>

static char g_last_decision[64];
static int32_t g_last_len = 0;
static int32_t g_last_act_rc = -1;

void setup() {
    Serial.println("greenhouse_agent: initialized");
}

void onMessage(int32_t from, int32_t op, const uint8_t *buf, int32_t len) {
    (void)from;

    /* Op 1: Health ping */
    if (op == N8_OP_PING) {
        Na8ve.reply("pong greenhouse_agent");
        return;
    }

    /* Op 0x10 (16): Sensor afferent -> recall context + request cognitive turn */
    if (op == 0x10 && len > 0) {
        Na8veRecallResult mem;
        Na8veStore.recall("greenhouse threshold", &mem);

        /* Queue async turn to model broker */
        int32_t rc = Na8veModel.request((const char *)buf, (size_t)len, 16);
        if (rc == 0) {
            Na8ve.reply("OK turn-queued");
        } else if (rc == N8_MODEL_E_SIZE) {
            Na8ve.reply("ERR prompt-too-long");
        } else {
            Na8ve.reply("ERR busy");
        }
        return;
    }

    /* Op 0x11 (17): Read last decision */
    if (op == 0x11) {
        if (g_last_len > 0) {
            char out[128];
            int at = 0;
            n8_put(out, &at, sizeof(out), "decision=");
            n8_put(out, &at, sizeof(out), g_last_decision);
            n8_put(out, &at, sizeof(out), g_last_act_rc == 0 ? " act=acted" : " act=checked");
            Na8ve.reply(out, (size_t)at);
        } else {
            Na8ve.reply("PENDING");
        }
        return;
    }

    /* Op 0x12 (18): Direct policy-mediated actuator proposal test */
    if (op == 0x12) {
        char verdict[160] = {0};
        int32_t rc = Na8veAct.propose("fan", "low", verdict, sizeof(verdict));
        g_last_act_rc = rc;
        if (verdict[0]) {
            Na8ve.reply(verdict);
        } else {
            Na8ve.reply(rc == 0 ? "OK acted" : "ERR refused");
        }
        return;
    }

    Na8ve.reply("ERR op");
}

void onModelReply(const char *text, int32_t len, int32_t err) {
    if (err != 0) {
        Serial.println("greenhouse_agent: broker error");
        return;
    }
    /* Save reply (sanitized to printable ASCII) bounded to 48 bytes */
    int32_t k = 0;
    for (int32_t i = 0; i < len && k < 48; i++) {
        char c = text[i];
        if (c >= 32 && c < 127) {
            g_last_decision[k++] = c;
        }
    }
    if (k == 0) {
        memcpy(g_last_decision, "fan=low", 8);
        k = 7;
    } else {
        g_last_decision[k] = '\0';
    }
    g_last_len = k;

    /* Propose validated actuator action against the greenhouse safety policy table */
    g_last_act_rc = Na8veAct.propose("fan", "low");
    Serial.print("greenhouse_agent decision: ");
    Serial.println(g_last_decision);
}

void loop() {
    /* Optional periodic tick work */
}
