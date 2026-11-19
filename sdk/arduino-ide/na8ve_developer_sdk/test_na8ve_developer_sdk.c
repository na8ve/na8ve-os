/* test_na8ve_developer_sdk.c - Host unit test and control check */
#ifdef N8_HOST_TEST
#include <assert.h>
#include <string.h>
#include "n8.h"

int main(void) {
    assert(n8_init() == 0);

    /* 1. Op 1 (PING) health verification */
    int32_t rc = n8_test_send_message(0, N8_OP_PING, NULL, 0);
    assert(rc == 0);
#ifdef EXPECT_MISMATCH
    /* Control check: assert mismatched reply so broken behavior fails */
    assert(strcmp(n8_test_last_reply(), "wrong-sdk-reply") == 0);
#else
    assert(strcmp(n8_test_last_reply(), "pong na8ve-developer-sdk") == 0);
#endif

    /* 2. Op 0x10 (cognitive turn request) */
    const char *obs = "temp_c=29.5 humidity=82%";
    rc = n8_test_send_message(0, 0x10, obs, (int32_t)strlen(obs));
    assert(rc == 0);
    assert(strcmp(n8_test_last_reply(), "OK sdk-turn-queued") == 0);

    /* 3. Op 0x11 (pending decision state before async model callback) */
    rc = n8_test_send_message(0, 0x11, NULL, 0);
    assert(rc == 0);
    assert(strcmp(n8_test_last_reply(), "PENDING") == 0);

    /* 4. Op 0x12 (4-subsystem SDK diagnostic self-test) */
    rc = n8_test_send_message(0, 0x12, NULL, 0);
    assert(rc == 0);
    assert(strstr(n8_test_last_reply(), "OK sdk store_hits=1") != NULL);
    assert(strstr(n8_test_last_reply(), "score_milli=9120") != NULL);
    assert(strstr(n8_test_last_reply(), "seam=ok") != NULL);

    return 0;
}
#endif /* N8_HOST_TEST */
