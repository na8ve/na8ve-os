/* The model broker's client: see n8_model.h */
#include "n8_model.h"

#include "n8.h"

#include <string.h>

static int g_pending;
static uint8_t g_req[1 + N8_MODEL_MAX_PROMPT];

int32_t n8_model_pending(void) { return g_pending; }

int32_t n8_model_request(const char *prompt, int32_t n, int32_t max_bytes)
{
    if (g_pending) return N8_MODEL_E_BUSY;
    if (n < 0 || n > N8_MODEL_MAX_PROMPT) return N8_MODEL_E_SIZE;
    if (max_bytes < 1) max_bytes = 1;
    if (max_bytes > N8_MODEL_MAX_BYTES) max_bytes = N8_MODEL_MAX_BYTES;
    g_req[0] = (uint8_t)max_bytes;
    if (n > 0) memcpy(g_req + 1, prompt, (size_t)n);
    const int32_t rc = n8_ipc_send(N8_MODEL_BROKER, N8_OP_MODEL_TURN, g_req, 1 + n);
    if (rc == 0) g_pending = 1;
    return rc;
}

static int nibble(uint8_t c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static int starts(const uint8_t *p, int32_t len, const char *s)
{
    const int32_t k = (int32_t)strlen(s);
    return len >= k && memcmp(p, s, (size_t)k) == 0;
}

int32_t n8_model_parse(const uint8_t *inbox, int32_t len, char *out, int32_t cap)
{
    g_pending = 0;
    if (cap > 0) out[0] = 0;
    if (starts(inbox, len, "ERR broker rate")) return N8_MODEL_E_RATE;
    if (starts(inbox, len, "ERR broker size")) return N8_MODEL_E_SIZE;
    if (starts(inbox, len, "ERR no-model")) return N8_MODEL_E_MODEL;
    if (!starts(inbox, len, "turn out=")) return N8_MODEL_E_REPLY;
    int32_t at = 9, k = 0;
    while (at + 1 < len && inbox[at] != ' ') {
        const int hi = nibble(inbox[at]), lo = nibble(inbox[at + 1]);
        if (hi < 0 || lo < 0) return N8_MODEL_E_REPLY;
        if (k + 1 < cap) out[k++] = (char)(hi << 4 | lo);
        at += 2;
    }
    if (cap > 0) out[k < cap ? k : cap - 1] = 0;
    return k;
}
