/* The rest of a libc the console's chat needs in a pVM (os-chat-001): snprintf and vsnprintf for
 * the formats cx_account.c, cx_mask.c, cx_json.c and the chat use (%s %c %d %i %u %x with 0, -,
 * width, precision and .*, the l, ll and z lengths, %f with a precision), the one sscanf form the
 * account reads ("[m:%lld] %n"), strtod, the string and ctype functions, and expf/logf. Nothing
 * here reaches outside the pVM's memory: no file, no locale, no errno. */
#include <ctype.h>
#include <math.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ---- strings ------------------------------------------------------------------------------- */

void *memchr(const void *s, int c, size_t n)
{
    const unsigned char *p = s;
    for (size_t i = 0; i < n; i++)
        if (p[i] == (unsigned char)c) return (void *)(p + i);
    return NULL;
}

char *strchr(const char *s, int c)
{
    for (;; s++) {
        if (*s == (char)c) return (char *)s;
        if (!*s) return NULL;
    }
}

char *strstr(const char *h, const char *n)
{
    const size_t k = strlen(n);
    for (; *h; h++)
        if (strncmp(h, n, k) == 0) return (char *)h;
    return k ? NULL : (char *)h;
}

int strncmp(const char *a, const char *b, size_t n)
{
    for (size_t i = 0; i < n; i++) {
        const unsigned char x = (unsigned char)a[i], y = (unsigned char)b[i];
        if (x != y || !x) return x - y;
    }
    return 0;
}

size_t strspn(const char *s, const char *set)
{
    size_t n = 0;
    while (s[n] && strchr(set, s[n])) n++;
    return n;
}

size_t strcspn(const char *s, const char *set)
{
    size_t n = 0;
    while (s[n] && !strchr(set, s[n])) n++;
    return n;
}

/* ---- ctype, the C locale ------------------------------------------------------------------- */

int isspace(int c) { return c == ' ' || (c >= '\t' && c <= '\r'); }
int isdigit(int c) { return c >= '0' && c <= '9'; }
int isalpha(int c) { return (c | 32) >= 'a' && (c | 32) <= 'z'; }
int isalnum(int c) { return isalpha(c) || isdigit(c); }
int isupper(int c) { return c >= 'A' && c <= 'Z'; }
int islower(int c) { return c >= 'a' && c <= 'z'; }
int ispunct(int c) { return c > 32 && c < 127 && !isalnum(c); }
int isxdigit(int c) { return isdigit(c) || ((c | 32) >= 'a' && (c | 32) <= 'f'); }
int tolower(int c) { return isupper(c) ? c + 32 : c; }
int toupper(int c) { return islower(c) ? c - 32 : c; }

/* ---- numbers ------------------------------------------------------------------------------- */

/* A decimal, as JSON writes one: sign, digits, a fraction, an exponent. Exact for the integers and
 * short decimals a reading carries; a long one may differ from a libc's in its last bit */
double strtod(const char *s, char **end)
{
    const char *p = s;
    while (isspace((unsigned char)*p)) p++;
    const bool neg = *p == '-';
    if (*p == '-' || *p == '+') p++;
    double v = 0;
    int digits = 0, scale = 0;
    for (; isdigit((unsigned char)*p); p++, digits++) v = v * 10 + (*p - '0');
    if (*p == '.') {
        for (p++; isdigit((unsigned char)*p); p++, digits++, scale--) v = v * 10 + (*p - '0');
    }
    if (!digits) {
        if (end) *end = (char *)s;
        return 0;
    }
    if (*p == 'e' || *p == 'E') {
        const char *q = p + 1;
        const bool eneg = *q == '-';
        if (*q == '-' || *q == '+') q++;
        if (isdigit((unsigned char)*q)) {
            int e = 0;
            for (; isdigit((unsigned char)*q); q++) e = e < 10000 ? e * 10 + (*q - '0') : e;
            scale += eneg ? -e : e;
            p = q;
        }
    }
    double f = 1;
    for (int i = scale < 0 ? -scale : scale; i > 0; i--) f *= 10;
    v = scale < 0 ? v / f : v * f;
    if (end) *end = (char *)p;
    return neg ? -v : v;
}

/* expf and logf through double: the float result is the correctly rounded one but for ties too
 * close to see. The console's libm may round its last bit otherwise (a printed p= or bits= can
 * differ in its last digit, never a byte the model chose: the choice is the int32 logits') */
static const double LN2 = 0.69314718055994530942;

/* expf in single precision, which the board's FPU has (it has no double): x = k ln2 + r, |r| <= ln2/2,
 * e^r by its series to r^6 (about 1 ulp), times 2^k built in the exponent bits */
float expf(float x)
{
    if (x != x) return x;
    if (x > 88.72f) return __builtin_inff();
    if (x < -103.97f) return 0.0f;
    const float k = __builtin_floorf(x * 1.44269504f + 0.5f);
    const float r = (x - k * 0.693145752f) - k * 1.42860677e-6f; /* ln2 in two parts: k * hi is exact */
    const float p = 1.0f + r * (1.0f + r * (0.5f + r * (0.166666672f + r * (0.0416666679f + r * (0.00833333377f + r * 0.00138888892f)))));
    int e = (int)k;
    float s = p;
    while (e > 127) { s *= 1.70141183e38f; e -= 127; }
    while (e < -126) { s *= 1.17549435e-38f; e += 126; }
    union { uint32_t u; float f; } two = {.u = (uint32_t)(e + 127) << 23};
    return s * two.f;
}

double log(double x)
{
    if (x < 0 || x != x) return __builtin_nan("");
    if (x == 0) return -__builtin_inf();
    if (x == __builtin_inf()) return x;
    double m = x;
    int e = 0;
    while (m >= 2) { m *= 0.5; e++; }
    while (m < 1) { m *= 2; e--; }
    if (m > 1.4142135623730951) { m *= 0.5; e++; }
    /* log(m) = 2 atanh((m - 1) / (m + 1)), |z| < 0.172 */
    const double z = (m - 1) / (m + 1), z2 = z * z;
    double t = z, s = 0;
    for (int i = 1; i < 60; i += 2) {
        s += t / i;
        t *= z2;
    }
    return 2 * s + e * LN2;
}

float logf(float x) { return (float)log((double)x); }

/* ---- formatting ---------------------------------------------------------------------------- */

typedef struct {
    char *b;
    size_t cap, n; /* n counts every byte, written or not, as vsnprintf's result does */
} out_t;

static void put(out_t *o, char c)
{
    if (o->n + 1 < o->cap) o->b[o->n] = c;
    o->n++;
}

static void pad(out_t *o, int k, char c)
{
    while (k-- > 0) put(o, c);
}

static void field(out_t *o, const char *s, int len, int width, bool left, char padc, bool neg)
{
    const int body = len + (neg ? 1 : 0);
    if (!left && padc == ' ') pad(o, width - body, ' ');
    if (neg) put(o, '-');
    if (!left && padc == '0') pad(o, width - body, '0');
    for (int i = 0; i < len; i++) put(o, s[i]);
    if (left) pad(o, width - body, ' ');
}

static int utoa(unsigned long long v, unsigned base, bool upper, char *buf)
{
    const char *dig = upper ? "0123456789ABCDEF" : "0123456789abcdef";
    char t[24];
    int n = 0;
    do {
        t[n++] = dig[v % base];
        v /= base;
    } while (v);
    for (int i = 0; i < n; i++) buf[i] = t[n - 1 - i];
    return n;
}

/* %.Nf: rounded half away from zero at N digits, as the console's values print */
static int ftoa(double v, int prec, char *buf, bool *neg)
{
    *neg = v < 0 || (v == 0 && 1 / v < 0);
    if (*neg) v = -v;
    if (v != v) return (int)(memcpy(buf, "nan", 3), 3);
    if (v > 1e18) return (int)(memcpy(buf, "inf", 3), 3);
    double scale = 1;
    for (int i = 0; i < prec; i++) scale *= 10;
    const unsigned long long whole = (unsigned long long)(v * scale + 0.5);
    const unsigned long long ip = whole / (unsigned long long)scale, fp = whole % (unsigned long long)scale;
    int n = utoa(ip, 10, false, buf);
    if (prec > 0) {
        buf[n++] = '.';
        char t[24];
        const int k = utoa(fp, 10, false, t);
        for (int i = k; i < prec; i++) buf[n++] = '0';
        memcpy(buf + n, t, (size_t)k);
        n += k;
    }
    return n;
}

int vsnprintf(char *b, size_t cap, const char *f, va_list ap)
{
    out_t o = {b, cap, 0};
    for (; *f; f++) {
        if (*f != '%') {
            put(&o, *f);
            continue;
        }
        f++;
        bool left = false;
        char padc = ' ';
        for (;; f++) {
            if (*f == '-') left = true;
            else if (*f == '0') padc = '0';
            else break;
        }
        int width = 0, prec = -1;
        if (*f == '*') {
            width = va_arg(ap, int);
            f++;
        } else
            while (isdigit((unsigned char)*f)) width = width * 10 + (*f++ - '0');
        if (*f == '.') {
            f++;
            prec = 0;
            if (*f == '*') {
                prec = va_arg(ap, int);
                f++;
            } else
                while (isdigit((unsigned char)*f)) prec = prec * 10 + (*f++ - '0');
        }
        int lng = 0;
        while (*f == 'l' || *f == 'z' || *f == 'h') {
            if (*f == 'l' || *f == 'z') lng++;
            f++;
        }
        char buf[48];
        switch (*f) {
        case 'd':
        case 'i': {
            const long long v = lng >= 2 ? va_arg(ap, long long) : lng == 1 ? va_arg(ap, long) : va_arg(ap, int);
            const unsigned long long u = v < 0 ? 0ull - (unsigned long long)v : (unsigned long long)v;
            field(&o, buf, utoa(u, 10, false, buf), width, left, padc, v < 0);
            break;
        }
        case 'u':
        case 'x':
        case 'X': {
            const unsigned long long v = lng >= 2 ? va_arg(ap, unsigned long long)
                                         : lng == 1 ? va_arg(ap, unsigned long)
                                                    : va_arg(ap, unsigned);
            field(&o, buf, utoa(v, *f == 'u' ? 10 : 16, *f == 'X', buf), width, left, padc, false);
            break;
        }
        case 'c': buf[0] = (char)va_arg(ap, int); field(&o, buf, 1, width, left, ' ', false); break;
        case 's': {
            const char *s = va_arg(ap, const char *);
            if (!s) s = "(null)";
            int n = 0;
            while ((prec < 0 || n < prec) && s[n]) n++;
            field(&o, s, n, width, left, ' ', false);
            break;
        }
        case 'f': {
            bool neg;
            const int n = ftoa(va_arg(ap, double), prec < 0 ? 6 : prec, buf, &neg);
            field(&o, buf, n, width, left, padc, neg);
            break;
        }
        case '%': put(&o, '%'); break;
        default: return -1; /* a format this libc does not have: refused, not guessed */
        }
    }
    if (cap) b[o.n < cap ? o.n : cap - 1] = 0;
    return (int)o.n;
}

int snprintf(char *b, size_t cap, const char *f, ...)
{
    va_list ap;
    va_start(ap, f);
    const int n = vsnprintf(b, cap, f, ap);
    va_end(ap);
    return n;
}

/* sscanf for the one form the account reads: literal characters, spaces (any run of white space),
 * %lld and %n. Any other conversion stops it */
int sscanf(const char *s, const char *f, ...)
{
    va_list ap;
    va_start(ap, f);
    const char *p = s;
    int got = 0;
    for (; *f; f++) {
        if (isspace((unsigned char)*f)) {
            while (isspace((unsigned char)*p)) p++;
        } else if (f[0] == '%' && f[1] == 'n') {
            *va_arg(ap, int *) = (int)(p - s);
            f++;
        } else if (f[0] == '%' && f[1] == 'l' && f[2] == 'l' && f[3] == 'd') {
            const bool neg = *p == '-';
            const char *q = p + (neg || *p == '+');
            if (!isdigit((unsigned char)*q)) break;
            long long v = 0;
            for (; isdigit((unsigned char)*q); q++) v = v * 10 + (*q - '0');
            *va_arg(ap, long long *) = neg ? -v : v;
            got++;
            p = q;
            f += 3;
        } else if (*f == '%') {
            break;
        } else if (*p == *f) {
            p++;
        } else {
            break;
        }
    }
    va_end(ap);
    return got;
}
