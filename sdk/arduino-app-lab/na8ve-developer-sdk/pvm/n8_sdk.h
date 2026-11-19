/*
 * pvm/n8_sdk.h - Core na8ve-os C Application SDK Header
 *
 * Freestanding sandbox application interface for na8ve-os.
 */

#ifndef N8_SDK_H
#define N8_SDK_H

#include <stdint.h>
#include <stddef.h>

#define N8_EXPORT(name) __attribute__((export_name(#name)))
#define N8_IMPORT(name) __attribute__((import_module("n8"), import_name(#name)))

/* Maximum message inbox payload size in sandbox linear memory */
#define N8_MSG_MAX          1024

/* Standard System Opcodes */
#define N8_OP_PING          0x00000001
#define N8_OP_ACTUATE       0x00000010  /* to pVM 0: "act target=<actuator> state=<state>", a
                                         * proposal the board's actuator policy table decides */
#define OP_SENSOR_TICK      0x00000020

/* Capability Grant Bitmask Flags */
#define N8_CAP_ACCEL        0x01
#define N8_CAP_STORE        0x02
#define N8_CAP_CHAT         0x04
#define N8_CAP_ACT          0x08

/*---------------- Host Service Imports ----------------*/

N8_IMPORT(n8_log)
extern int32_t n8_log(const char *msg, int32_t len);

N8_IMPORT(n8_ipc_send)
extern int32_t n8_ipc_send(int32_t target_dom, int32_t op, const uint8_t *buf, int32_t len);

N8_IMPORT(n8_store_query)
extern int32_t n8_store_query(const char *query, int32_t query_len, int32_t k, uint8_t *out, int32_t cap);

N8_IMPORT(n8_reply)
extern int32_t n8_reply(const uint8_t *buf, int32_t len);

/*---------------- Freestanding String & Buffer Helpers ----------------*/

static inline void n8_put(char *dst, int *at, int cap, const char *src) {
    while (*src && *at + 1 < cap) {
        dst[(*at)++] = *src++;
    }
    if (*at < cap) {
        dst[*at] = '\0';
    }
}

static inline void n8_put_u(char *dst, int *at, int cap, uint32_t val) {
    char tmp[12];
    int i = 0;
    if (val == 0) {
        tmp[i++] = '0';
    } else {
        while (val > 0 && i < (int)sizeof(tmp)) {
            tmp[i++] = (char)('0' + (val % 10u));
            val /= 10u;
        }
    }
    while (i > 0 && *at + 1 < cap) {
        dst[(*at)++] = tmp[--i];
    }
    if (*at < cap) {
        dst[*at] = '\0';
    }
}

static inline int32_t n8_reply_str(const char *s) {
    int32_t len = 0;
    while (s[len]) len++;
    return n8_reply((const uint8_t *)s, len);
}

#endif /* N8_SDK_H */

