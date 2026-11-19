/* libraries/Na8veAct/src/Na8veAct.h - Policy-Mediated Actuator Proposals */
#ifndef Na8veAct_h
#define Na8veAct_h

#include <Arduino.h>

class Na8veActClass {
public:
    /* Propose an actuator state change ("fan", "low") to the board's actuator safety policy table.
     * An application or model never drives a physical pin directly.
     * Returns 0 if approved and acted, -1 if refused by policy/cooldown. */
    int32_t propose(const char *actuator, const char *state, char *verdict_out = nullptr, size_t cap = 0) {
        if (!actuator || !state) return -1;
        char json[128];
        int at = 0;
        n8_put(json, &at, sizeof(json), "{\"act\":\"");
        n8_put(json, &at, sizeof(json), actuator);
        n8_put(json, &at, sizeof(json), "\",\"state\":\"");
        n8_put(json, &at, sizeof(json), state);
        n8_put(json, &at, sizeof(json), "\"}");

        char res[256] = {0};
        int32_t n = n8_tool(json, at, res, sizeof(res) - 1);
        if (verdict_out && cap > 0 && n > 0) {
            size_t c = (size_t)n < (cap - 1) ? (size_t)n : (cap - 1);
            memcpy(verdict_out, res, c);
            verdict_out[c] = '\0';
        }
        return (n >= 0 && strstr(res, "\"acted\"") != nullptr) ? 0 : -1;
    }
};

static Na8veActClass Na8veAct;

#endif /* Na8veAct_h */

