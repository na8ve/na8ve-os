/* test_greenhouse_agent.c - Host unit test & mandatory failing control twin */
#ifdef N8_HOST_TEST
#include <assert.h>
#include <string.h>
#include "n8.h"

int main(void) {
    assert(n8_init() == 0);

    /* 1. Deliver op 1 (PING) and verify reply */
    int32_t rc = n8_test_send_message(0, N8_OP_PING, NULL, 0);
    assert(rc == 0);
#ifdef EXPECT_MISMATCH
    /* Mandatory failing control twin: assert wrong reply string so control fails as required */
    assert(strcmp(n8_test_last_reply(), "wrong-reply") == 0);
#else
    assert(strcmp(n8_test_last_reply(), "pong greenhouse_agent") == 0);
#endif

    /* 2. Deliver op 0x10 (sensor afferent) and verify turn queued */
    const char *obs = "temp_c=31.2 humidity=38%";
    rc = n8_test_send_message(0, 0x10, obs, (int32_t)strlen(obs));
    assert(rc == 0);
    assert(strcmp(n8_test_last_reply(), "OK turn-queued") == 0);

    /* 3. Simulate broker reply (from=1, op=0x80000004) and check op 0x11 decision */
    const char *broker_reply = "turn out=66616e3d6c6f77 bytes=16 us=12000";
    rc = n8_test_send_message(1, (int32_t)0x80000004u, broker_reply, (int32_t)strlen(broker_reply));
    assert(rc == 0);
    rc = n8_test_send_message(0, 0x11, NULL, 0);
    assert(rc == 0);
    assert(strstr(n8_test_last_reply(), "decision=fan=low") != NULL);

    return 0;
}
#endif /* N8_HOST_TEST */
