/* cores/na8ve_pvm/Arduino.h - Arduino API over the na8ve-os pVM WIT Boundary */
#ifndef Arduino_h
#define Arduino_h

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
#include "n8.h"
#include "n8_ops.h"
#include "pins_arduino.h"

#ifdef __cplusplus
extern "C" {
#endif

void setup(void);
void loop(void);

/* Optional message handler for IPC/console calls (os-call 2 <op> <hex>) */
void onMessage(int32_t from, int32_t op, const uint8_t *buf, int32_t len) __attribute__((weak));

/* Optional callback when the model broker replies to Na8veModel.request() */
void onModelReply(const char *text, int32_t len, int32_t err) __attribute__((weak));

static inline unsigned long micros(void) { return (unsigned long)n8_now_us(); }
static inline unsigned long millis(void) { return (unsigned long)(n8_now_us() / 1000LL); }

static inline void delay(unsigned long ms) {
    int64_t end = n8_now_us() + (int64_t)ms * 1000LL;
    while (n8_now_us() < end) {
        n8_yield(); /* Yields to core 0 store task, console, and FreeRTOS IDLE0 */
    }
}

static inline void yield(void) { n8_yield(); }

#ifdef __cplusplus
} /* extern "C" */

/* Serial.print / Serial.println routed through the kernel's metadata-only n8_log gate */
class Na8veSerial {
public:
    void begin(unsigned long baud = 115200) { (void)baud; }
    void print(const char *s) {
        if (s) n8_log(s, (int32_t)strlen(s));
    }
    void println(const char *s) {
        if (s) n8_log(s, (int32_t)strlen(s));
    }
    void print(int v) {
        char b[24];
        int at = 0;
        if (v < 0) { b[at++] = '-'; v = -v; }
        n8_put_u(b, &at, sizeof(b), (uint64_t)v);
        n8_log(b, at);
    }
    void println(int v) { print(v); }
};

extern Na8veSerial Serial;

class Na8veRuntime {
public:
    int32_t reply(const void *buf, size_t len) { return n8_reply(buf, (int32_t)len); }
    int32_t reply(const char *str) { return n8_reply_str(str); }
    int32_t send(uint8_t target_pvm, uint32_t op, const void *buf, size_t len) {
        return n8_ipc_send((int32_t)target_pvm, (int32_t)op, buf, (int32_t)len);
    }
    int64_t nowUs(void) const { return n8_now_us(); }
    void yield(void) const { n8_yield(); }
    void log(const char *s) const {
        if (s) n8_log(s, (int32_t)strlen(s));
    }
};

extern Na8veRuntime Na8ve;
#endif /* __cplusplus */

#endif /* Arduino_h */

