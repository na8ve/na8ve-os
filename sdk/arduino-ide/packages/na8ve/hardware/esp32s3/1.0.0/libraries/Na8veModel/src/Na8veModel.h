/* libraries/Na8veModel/src/Na8veModel.h - Async Client for the na8ve-os Model Broker */
#ifndef Na8veModel_h
#define Na8veModel_h

#include <Arduino.h>
#include "n8_model.h"

class Na8veModelClass {
public:
    /* Queue a NUL-terminated prompt (<= 256 B) for asynchronous neural inference
     * using `cortex-mvp` via the model broker. Responses arrive in onModelReply().
     * Returns 0 if queued, N8_MODEL_E_BUSY (-1) if a turn is already in flight,
     * N8_MODEL_E_SIZE (-3) if prompt > 256 B, or a negative error if IPC grant is missing.
     * Rate-limit throttling (N8_MODEL_E_RATE = -2) is reported asynchronously via onModelReply(). */
    int32_t request(const char *prompt, uint8_t max_bytes = 32) {
        if (!prompt) return N8_MODEL_E_SIZE;
        return n8_model_request(prompt, (int32_t)strlen(prompt), (int32_t)max_bytes);
    }

    /* Explicit-length overload (all 3 arguments required so 2-arg (prompt, max_bytes)
     * never collides with integer literals). */
    int32_t request(const char *prompt, size_t len, uint8_t max_bytes) {
        return n8_model_request(prompt, (int32_t)len, (int32_t)max_bytes);
    }

    /* True while waiting for the model broker to reply via onModelReply() */
    bool pending(void) const {
        return n8_model_pending() != 0;
    }
};

static Na8veModelClass Na8veModel;

#endif /* Na8veModel_h */

