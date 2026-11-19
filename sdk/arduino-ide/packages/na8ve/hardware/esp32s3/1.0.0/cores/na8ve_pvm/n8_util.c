/* n8.h's small helpers, without a libc: built into every pVM, and natively for the host test. */
#include "n8.h"

#include <string.h>

int32_t n8_reply_str(const char *s) { return n8_reply(s, (int32_t)strlen(s)); }

void n8_put(char *b, int *at, int cap, const char *s)
{
    while (*s && *at < cap - 1) b[(*at)++] = *s++;
    b[*at] = 0;
}

void n8_put_u(char *b, int *at, int cap, uint64_t v)
{
    char t[24];
    int n = 0;
    do t[n++] = (char)('0' + v % 10); while ((v /= 10) && n < 23);
    while (n && *at < cap - 1) b[(*at)++] = t[--n];
    b[*at] = 0;
}

void n8_put_hex(char *b, int *at, int cap, const uint8_t *p, int n)
{
    static const char k[] = "0123456789abcdef";
    for (int i = 0; i < n && *at < cap - 2; i++) {
        b[(*at)++] = k[p[i] >> 4];
        b[(*at)++] = k[p[i] & 15];
    }
    b[*at] = 0;
}
