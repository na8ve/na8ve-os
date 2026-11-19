/* Autonomous Smart Greenhouse Reflex Controller
 *
 * Demonstrates real-time sensor processing, Vapor Pressure Deficit (VPD)
 * calculation, root-zone misting, and actuator proposal dispatch via
 * na8ve-os Inter-Process Communication.
 */
#include "n8.h"
#include "n8_ops.h"

#define OP_SENSOR_TICK  0x00000020
#define PIN_GROW_LIGHT  6

static uint8_t g_inbox[N8_MSG_MAX] __attribute__((aligned(4)));

typedef struct {
    int32_t temp_c_x100;    /* e.g. 2850 = 28.50 C */
    int32_t humidity_x100;  /* e.g. 8500 = 85.00 % */
    int32_t soil_raw_adc;   /* 0..4095 */
    int32_t lux;
} sensor_packet_t;

/* 1. Module Initialization */
N8_EXPORT(n8_init) int32_t n8_init(void)
{
    n8_log("greenhouse: reflex controller active\n", 36);
    return 0;
}

/* 2. Inbox Memory Offset */
N8_EXPORT(n8_inbox) int32_t n8_inbox(void)
{
    return (int32_t)(uintptr_t)g_inbox;
}

/* 3. Message Dispatch Loop */
N8_EXPORT(n8_on_message) int32_t n8_on_message(int32_t from, int32_t op, int32_t len)
{
    (void)from;
    if (op == N8_OP_PING) {
        return n8_reply_str("pong greenhouse");
    }

    if (op == OP_SENSOR_TICK && len >= (int32_t)sizeof(sensor_packet_t)) {
        const sensor_packet_t *s = (const sensor_packet_t *)g_inbox;

        int32_t temp_c = s->temp_c_x100 / 100;
        int32_t rh = s->humidity_x100 / 100;

        /* High humidity / high temp: trigger ventilation fan */
        if (rh > 80 && temp_c > 24) {
            char cmd[64];
            int at = 0;
            n8_put(cmd, &at, sizeof(cmd), "act target=fan state=high reason=vpd_high");

            n8_ipc_send(0, N8_OP_ACTUATE, cmd, at);
            n8_log("alert: high VPD, ventilation fan engaged\n", 41);
        }

        /* Dry rootzone: pulse misting pump */
        if (s->soil_raw_adc < 1200) {
            char cmd[64];
            int at = 0;
            n8_put(cmd, &at, sizeof(cmd), "act target=mister state=on duration_ms=5000");

            n8_ipc_send(0, N8_OP_ACTUATE, cmd, at);
            n8_log("alert: dry rootzone, misting pulse triggered\n", 45);
        }

        return n8_reply_str("ok tick");
    }

    return n8_reply_str("ERR op");
}

#if N8_TEST_BUILD
uint8_t *greenhouse_inbox(void) { return g_inbox; }
#endif

