/*
 * pvm/sdk_starter_app.c - Reference na8ve-os Developer SDK C Sandbox Application
 *
 * Implements the three standard lifecycle entrypoints (n8_init, n8_inbox,
 * n8_on_message) plus pvm_main for direct RPC invocation from Arduino App Lab.
 */

#include "n8_sdk.h"

#define PIN_GROW_LIGHT  6

static uint8_t g_inbox[N8_MSG_MAX] __attribute__((aligned(4)));

typedef struct {
    int32_t temp_c_x100;    /* e.g. 2850 = 28.50 C */
    int32_t humidity_x100;  /* e.g. 8500 = 85.00 % */
    int32_t soil_raw_adc;   /* 0..4095 */
    int32_t lux;
} sensor_packet_t;

N8_EXPORT(n8_init) int32_t n8_init(void) {
    n8_log("sdk-starter: application sandbox initialized\n", 45);
    return 0;
}

N8_EXPORT(n8_inbox) int32_t n8_inbox(void) {
    return (int32_t)(uintptr_t)g_inbox;
}

N8_EXPORT(n8_on_message) int32_t n8_on_message(int32_t from, int32_t op, int32_t len) {
    (void)from;
    if (op == N8_OP_PING) {
        n8_reply_str("ok:sdk-starter:op=1");
        return 0;
    }

    if (op == OP_SENSOR_TICK && len >= (int32_t)sizeof(sensor_packet_t)) {
        sensor_packet_t *s = (sensor_packet_t *)g_inbox;
        int32_t temp_c = s->temp_c_x100 / 100;
        int32_t rh = s->humidity_x100 / 100;

        if (rh > 80 && temp_c > 24) {
            char cmd[64];
            int at = 0;
            n8_put(cmd, &at, sizeof(cmd), "act target=fan state=high reason=vpd_high");
            n8_ipc_send(0, N8_OP_ACTUATE, (const uint8_t *)cmd, at);
        }

        if (s->soil_raw_adc < 1200) {
            char cmd[64];
            int at = 0;
            n8_put(cmd, &at, sizeof(cmd), "act target=mister state=on duration_ms=5000");
            n8_ipc_send(0, N8_OP_ACTUATE, (const uint8_t *)cmd, at);
        }
        n8_reply_str("ok:sdk-starter:sensor_tick");
        return 0;
    }

    return 0;
}

N8_EXPORT(pvm_main) int32_t pvm_main(int32_t op, int32_t ptr, int32_t len) {
    if (op == N8_OP_PING) {
        static const uint8_t ipc_msg[] = "sdk-starter:heartbeat=ok";
        n8_ipc_send(1, N8_OP_PING, ipc_msg, (int32_t)(sizeof(ipc_msg) - 1));
        n8_reply_str("ok:sdk-starter:op=1");
        return 0;
    }
    if (op == OP_SENSOR_TICK && len >= (int32_t)sizeof(sensor_packet_t)) {
        if (ptr != 0) {
            const uint8_t *src = (const uint8_t *)(uintptr_t)ptr;
            int32_t copy_len = len > N8_MSG_MAX ? N8_MSG_MAX : len;
            for (int32_t i = 0; i < copy_len; i++) {
                g_inbox[i] = src[i];
            }
        }
        return n8_on_message(1, op, len);
    }
    return -1;
}

