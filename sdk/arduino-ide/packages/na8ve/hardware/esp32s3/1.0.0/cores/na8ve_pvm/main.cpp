/* cores/na8ve_pvm/main.cpp - Bridges Arduino setup()/loop()/onMessage() to WAMR WIT */
#include "Arduino.h"
#include "n8_model.h"

Na8veSerial Serial;
Na8veRuntime Na8ve;

static uint8_t g_inbox[N8_MSG_MAX];

extern "C" N8_EXPORT(n8_init) int32_t n8_init(void) {
    setup();
    return 0;
}

extern "C" N8_EXPORT(n8_inbox) int32_t n8_inbox(void) {
    return (int32_t)(uintptr_t)g_inbox;
}

#ifdef N8_HOST_TEST
extern "C" uint8_t *n8_test_inbox_ptr(void) {
    return g_inbox;
}
#endif

extern "C" N8_EXPORT(n8_on_message) int32_t n8_on_message(int32_t from, int32_t op, int32_t len) {
    if (len < 0 || len > N8_MSG_MAX) {
        n8_reply_str("ERR len");
        return 0;
    }

    /* 1. Asynchronous reply from the model broker (reply bit 0x80000000) */
    if ((op & 0x80000000) && from == N8_MODEL_BROKER) {
        char decoded[N8_MODEL_MAX_BYTES + 1] = {0};
        int32_t n = n8_model_parse(g_inbox, len, decoded, sizeof(decoded));
        if (onModelReply) {
            onModelReply(decoded, n >= 0 ? n : 0, n < 0 ? n : 0);
        }
        return 0;
    }

    /* 2. Custom sketch message handler (if defined by the developer) */
    if (onMessage) {
        onMessage(from, op, g_inbox, len);
        return 0;
    }

    /* 3. Default handlers: Op 1 = Ping, Op 0x10 = Run one Arduino loop() tick */
    if (op == N8_OP_PING) {
        n8_reply_str("pong arduino-pvm");
        return 0;
    }
    if (op == 0x10) {
        loop();
        n8_reply_str("OK loop");
        return 0;
    }

    n8_reply_str("ERR op");
    return 0;
}

