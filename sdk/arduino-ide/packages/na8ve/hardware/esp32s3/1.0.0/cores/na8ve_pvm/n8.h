/* The na8ve-os pVM SDK: the third-party WIT boundary.
 *
 * A pVM is a freestanding WebAssembly 1.0 module in its own linear memory. It exports three
 * things to the engine:
 *   n8_init() -> 0 on startup
 *   n8_inbox() -> the offset in its own memory of a 1,024-byte receive buffer
 *   n8_on_message(from, op, len) -> 0 after handling `len` bytes at n8_inbox()
 *
 * Everything outside its linear memory goes through the imports below, in module "na8ve", which
 * the kernel gates against the manifest. A pointer and length that step outside the pVM's own
 * memory trap in the engine before the kernel sees them; a call the manifest did not grant
 * contains the pVM (its state becomes quarantined for the rest of the boot) and traps the call.
 *
 * Notice that kernel-private neural, raw partition, and console stream imports are
 * intentionally absent from this third-party Arduino SDK. Third-party sketches use `Na8veModel`. */
#ifndef N8_H
#define N8_H

#include <stddef.h>
#include <stdint.h>

#include "n8_ops.h"

#ifdef __cplusplus
extern "C" {
#endif

#if defined(__wasm__) && !defined(N8_HOST_TEST)
#define N8_IMPORT(name) __attribute__((import_module("na8ve"), import_name(#name)))
#define N8_EXPORT(name) __attribute__((export_name(#name)))
#else
#define N8_IMPORT(name)
#define N8_EXPORT(name)
#endif

/* Metadata only: a diagnostic line of at most 120 bytes, never a transcript or a secret. */
N8_IMPORT(log) void n8_log(const char *msg, int32_t len);
N8_IMPORT(now_us) int64_t n8_now_us(void);

/* Store recall: needs a store grant on "query" with R. Bounded to at most 8 hits. */
N8_IMPORT(store_query) int32_t n8_store_query(const char *q, int32_t qlen, int32_t k, char *out, int32_t cap);

/* Send `op` with `len` bytes (at most N8_MSG_MAX) to domain `to`. Needs bit `to` in allowed_ipc. */
N8_IMPORT(ipc_send) int32_t n8_ipc_send(int32_t to, int32_t op, const void *buf, int32_t len);

/* Answer the message now in n8_on_message with `len` bytes. */
N8_IMPORT(reply) int32_t n8_reply(const void *buf, int32_t len);

/* Policy-checked tool call (`{"act":...}` or `{"tool":"readings_latest",...}`), gated by `act`/`seam` grant. */
N8_IMPORT(tool) int32_t n8_tool(const char *json, int32_t len, char *out, int32_t cap);

/* Yield a tick to other tasks and the watchdog. */
N8_IMPORT(yield) void n8_yield(void);

int32_t n8_reply_str(const char *s);
void n8_put(char *b, int *at, int cap, const char *s);
void n8_put_u(char *b, int *at, int cap, uint64_t v);
void n8_put_hex(char *b, int *at, int cap, const uint8_t *p, int n);

/* Exported by the pVM, called by the engine. */
int32_t n8_init(void);
int32_t n8_inbox(void);
int32_t n8_on_message(int32_t from, int32_t op, int32_t len);

#ifdef N8_HOST_TEST
/* Host test helpers provided by the test harness when compiled with -DN8_HOST_TEST */
const char *n8_test_last_reply(void);
int32_t n8_test_send_message(int32_t from, int32_t op, const void *data, int32_t len);
#endif

#ifdef __cplusplus
}
#endif

#endif /* N8_H */

