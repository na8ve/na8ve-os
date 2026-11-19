/* Host unit test for the Greenhouse Reflex Controller.
 *
 * Simulates incoming sensor packets, evaluates reflex decisions, and verifies
 * actuation commands dispatched to Core 0.
 *
 * Compiling and running:
 *   gcc -I../../sdk/include greenhouse.c test_greenhouse.c ../../sdk/src/n8_util.c -o test_greenhouse
 *   ./test_greenhouse
 *
 * Compiling failing control twin:
 *   gcc -DEXPECT_MISMATCH -I../../sdk/include greenhouse.c test_greenhouse.c ../../sdk/src/n8_util.c -o test_greenhouse_control
 *   ./test_greenhouse_control
 */
#include "n8.h"
#include "n8_ops.h"

#include <stdio.h>
#include <string.h>

#define OP_SENSOR_TICK 0x00000020

typedef struct {
    int32_t temp_c_x100;
    int32_t humidity_x100;
    int32_t soil_raw_adc;
    int32_t lux;
} sensor_packet_t;

uint8_t *greenhouse_inbox(void);

static char g_reply[N8_MSG_MAX + 1];
static int g_actuate_calls = 0;
static char g_last_act[64];

/* Mocked host services */
void n8_log(const char *p, int32_t n) { (void)p; (void)n; }
int64_t n8_now_us(void) { return 1000000LL; }
int32_t n8_flash_read(const char *label, int32_t off, void *dst, int32_t n) { return -1; }
int32_t n8_store_query(const char *q, int32_t qlen, int32_t k, void *out, int32_t cap) { return -1; }

int32_t n8_ipc_send(int32_t to, int32_t op, const void *p, int32_t n)
{
    if (to == 0 && op == N8_OP_ACTUATE) {
        g_actuate_calls++;
        int cpy = n < (int32_t)sizeof(g_last_act) - 1 ? n : (int32_t)sizeof(g_last_act) - 1;
        memcpy(g_last_act, p, (size_t)cpy);
        g_last_act[cpy] = 0;
        return 0;
    }
    return -1;
}

int32_t n8_reply(const void *p, int32_t n)
{
    if (n < 0 || n > N8_MSG_MAX) return -1;
    memcpy(g_reply, p, (size_t)n);
    g_reply[n] = 0;
    return 0;
}

/* Stubs for unused SDK declarations */
int32_t n8_chat_in(void *d, int32_t c) { return -1; }
int32_t n8_emit(const char *p, int32_t n) { return -1; }
int32_t n8_tool(const char *j, int32_t n, char *o, int32_t c) { return -1; }
int32_t n8_session(const char *a, const char *b, int32_t v) { return -1; }
void n8_yield(void) {}

static const char *send_packet(int32_t op, const void *data, size_t len)
{
    if (len > 0) memcpy(greenhouse_inbox(), data, len);
    g_reply[0] = 0;
    n8_on_message(0, op, (int32_t)len);
    return g_reply;
}

int main(void)
{
    if (n8_init() != 0) return 1;

    /* Ping check */
    if (strcmp(send_packet(N8_OP_PING, NULL, 0), "pong greenhouse") != 0) {
        printf("FAIL: ping reply mismatch\n");
        return 1;
    }
    printf("ok ping\n");

    /* Normal environment: 22C, 60% RH, 2000 ADC soil */
    sensor_packet_t normal = { .temp_c_x100 = 2200, .humidity_x100 = 6000, .soil_raw_adc = 2000, .lux = 500 };
    send_packet(OP_SENSOR_TICK, &normal, sizeof(normal));
    if (g_actuate_calls != 0) {
        printf("FAIL: unexpected actuation on normal reading\n");
        return 1;
    }
    printf("ok normal environment (0 actuations)\n");

    /* Critical environment: 28C, 85% RH, 900 ADC soil (dry rootzone + high VPD) */
    sensor_packet_t alert = { .temp_c_x100 = 2800, .humidity_x100 = 8500, .soil_raw_adc = 900, .lux = 600 };
    send_packet(OP_SENSOR_TICK, &alert, sizeof(alert));

#ifdef EXPECT_MISMATCH
    /* Control twin: expects zero actuations, which must fail on alert conditions */
    const int caught = (g_actuate_calls != 0);
    printf("control: expected mismatch; caught=%d\n", caught);
    return caught ? 0 : 1;
#else
    if (g_actuate_calls != 2) {
        printf("FAIL: expected 2 actuations (fan + pump), got %d\n", g_actuate_calls);
        return 1;
    }
    printf("ok alert environment (2 actuations dispatched: fan and misting pump)\n");
    printf("PASSED\n");
    return 0;
#endif
}

