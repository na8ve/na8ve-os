/* libraries/Na8veStore/src/Na8veStore.h - Bounded Read-Only Memory Recall */
#ifndef Na8veStore_h
#define Na8veStore_h

#include <Arduino.h>

struct Na8veRecallHit {
    int64_t id;
    int32_t score_milli; /* score * 10000 */
};

struct Na8veRecallResult {
    Na8veRecallHit hits[8];
    uint8_t count;
    bool truncated;
    char raw[512];
};

class Na8veStoreClass {
public:
    /* Bounded recall (max k=8). Sets res->truncated if the kernel clipped the result. */
    int32_t recall(const char *query, Na8veRecallResult *res, int32_t k = 4) {
        if (!query || !res) return -1;
        memset(res, 0, sizeof(*res));
        int32_t n = n8_store_query(query, (int32_t)strlen(query), k, res->raw, sizeof(res->raw) - 1);
        if (n < 0) return n;
        res->raw[n] = '\0';
        res->truncated = (strstr(res->raw, "truncated=1") != nullptr);
        /* Parse "id=<n>" and optional "score=<float>" per hit line */
        const char *p = res->raw;
        while ((p = strstr(p, "id=")) != nullptr && res->count < 8) {
            p += 3;
            int64_t id = 0;
            while (*p >= '0' && *p <= '9') {
                id = id * 10 + (*p - '0');
                p++;
            }
            int32_t score_milli = 0;
            const char *eol = strchr(p, '\n');
            const char *sp = strstr(p, "score=");
            if (sp && (!eol || sp < eol)) {
                sp += 6;
                int32_t sign = 1;
                if (*sp == '-') { sign = -1; sp++; }
                int32_t whole = 0;
                while (*sp >= '0' && *sp <= '9') {
                    whole = whole * 10 + (*sp - '0');
                    sp++;
                }
                int32_t frac = 0;
                int32_t digits = 0;
                if (*sp == '.') {
                    sp++;
                    while (*sp >= '0' && *sp <= '9') {
                        if (digits < 4) {
                            frac = frac * 10 + (*sp - '0');
                            digits++;
                        }
                        sp++;
                    }
                }
                while (digits < 4) {
                    frac *= 10;
                    digits++;
                }
                score_milli = sign * (whole * 10000 + frac);
            }
            res->hits[res->count].id = id;
            res->hits[res->count].score_milli = score_milli;
            res->count++;
        }
        return (int32_t)res->count;
    }
};

static Na8veStoreClass Na8veStore;

#endif /* Na8veStore_h */

