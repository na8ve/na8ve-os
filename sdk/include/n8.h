/* The pVM side of na8ve-os's typed interface:
 * what an application module imports from the runtime, every call re-checked against the caller's
 * capability grants, and what it exports.
 *
 * Built for wasm32 (tools/build_app.py); built natively for host unit tests of the app's own logic
 * (-DN8_HOST_TEST), where the imports are provided by test stubs. */
#ifndef N8_H
#define N8_H

#include <stdint.h>

#include "n8_ops.h"

/* N8_HOST_TEST: a host test built natively against mock runtime stubs.
 * N8_TEST_BUILD is 1 in any host-test build (native or WASI) and 0 in the pVM's own build: guard a
 * test's door into the inbox with `#if N8_TEST_BUILD`, not `#ifndef __wasm__`. */
#if !defined(__wasm__) || defined(N8_HOST_TEST)
#define N8_TEST_BUILD 1
#else
#define N8_TEST_BUILD 0
#endif
#if defined(__wasm__) && !defined(N8_HOST_TEST)
#define N8_IMPORT(name) __attribute__((import_module("na8ve"), import_name(#name)))
#define N8_EXPORT(name) __attribute__((export_name(#name)))
#else
#define N8_IMPORT(name)
#define N8_EXPORT(name)
#endif

/* ---- imports: the host functions (kernel services) ---------------------------------------- */
N8_IMPORT(log) void n8_log(const char *p, int32_t n);
N8_IMPORT(now_us) int64_t n8_now_us(void);
/* n bytes at off of a flash grant's partition into dst: 0, or the pVM is contained (no grant) */
N8_IMPORT(flash_read) int32_t n8_flash_read(const char *label, int32_t off, void *dst, int32_t n);
/* a bounded store query (the recall's top k, k <= 8): the rows as text into out; its length, or -1 */
N8_IMPORT(store_query) int32_t n8_store_query(const char *q, int32_t qlen, int32_t k, void *out, int32_t cap);
/* a message to another pVM, through the gate: 0, or negative (no IPC bit: the sender is contained) */
N8_IMPORT(ipc_send) int32_t n8_ipc_send(int32_t to, int32_t op, const void *p, int32_t n);
/* the answer to the message being handled */
N8_IMPORT(reply) int32_t n8_reply(const void *p, int32_t n);

/* the console's chat (os-chat-001), through the `chat` grant on "board"; without it, contained.
 * chat_in: the request the kernel holds for this call (a settings line, then the prompt's bytes);
 *       its length, or -1 outside a chat
 * emit: one console line of the model's (`b `, `# `, `score `, `say `, `done `, `check `), no
 *       line break; any other line and the pVM is contained (os-chat-004)
 * tool: a call (the bytes between <call> and </call>; n 0 for a "</call>" with no "<call>") run by
 *       the kernel's own path, which prints its tool, act and result lines; the Result's JSON into
 *       out, its length. An act needs the grant's w
 * session: chat-session's memory for a proposal the table decided (needs w)
 * yield: between model steps, as the console's chat: the kernel's other tasks run */
N8_IMPORT(chat_in) int32_t n8_chat_in(void *dst, int32_t cap);
N8_IMPORT(emit) int32_t n8_emit(const char *p, int32_t n);
N8_IMPORT(tool) int32_t n8_tool(const char *json, int32_t n, char *out, int32_t cap);
N8_IMPORT(session) int32_t n8_session(const char *name, const char *state, int32_t verdict);
N8_IMPORT(yield) void n8_yield(void);

/* ---- exports: what every pVM gives the kernel -------------------------------------------- */
/* n8_init() -> 0; n8_inbox() -> the address of its N8_MSG_MAX-byte inbox in its own memory;
 * n8_on_message(from, op, len) -> 0: the message's bytes are already in the inbox (copied
 * there by the kernel before the call: Wasm-IO's TOCTOU rule) */
int32_t n8_init(void);
int32_t n8_inbox(void);
int32_t n8_on_message(int32_t from, int32_t op, int32_t len);

/* a reply of text, NUL not sent */
int32_t n8_reply_str(const char *s);
/* small formatting without a libc: append to b[*at], at most cap - 1, always terminated */
void n8_put(char *b, int *at, int cap, const char *s);
void n8_put_u(char *b, int *at, int cap, uint64_t v);
void n8_put_hex(char *b, int *at, int cap, const uint8_t *p, int n);

#endif
