/* The pVM's libc, wasm32 only: memory functions on WebAssembly's bulk-memory instructions, and a
 * first-fit allocator over the module's own linear memory, grown a page at a time up to the
 * ceiling the kernel instantiated it with (the manifest's mem_linear). Nothing here reaches the
 * kernel: a pVM's memory is its own, and an access past it traps in the engine. */
#include <stddef.h>
#include <stdint.h>

#include "libc/stdlib.h"
#include "libc/string.h"

#if defined(__wasm_bulk_memory__)
void *memcpy(void *d, const void *s, size_t n)
{
    __builtin_memcpy(d, s, n); /* memory.copy */
    return d;
}

void *memmove(void *d, const void *s, size_t n)
{
    __builtin_memmove(d, s, n); /* memory.copy is defined for overlap */
    return d;
}

void *memset(void *d, int c, size_t n)
{
    __builtin_memset(d, c, n); /* memory.fill */
    return d;
}
#else /* the MVP's instructions only: loops, a word at a time where both ends allow */
void *memcpy(void *d, const void *s, size_t n)
{
    unsigned char *a = d;
    const unsigned char *b = s;
    if ((((uintptr_t)a | (uintptr_t)b) & 3) == 0)
        for (; n >= 4; n -= 4, a += 4, b += 4) *(uint32_t *)a = *(const uint32_t *)b;
    while (n--) *a++ = *b++;
    return d;
}

void *memmove(void *d, const void *s, size_t n)
{
    unsigned char *a = d;
    const unsigned char *b = s;
    if (a <= b || a >= b + n) return memcpy(d, s, n);
    while (n--) a[n] = b[n];
    return d;
}

void *memset(void *d, int c, size_t n)
{
    unsigned char *a = d;
    while (n--) *a++ = (unsigned char)c;
    return d;
}
#endif

int memcmp(const void *a, const void *b, size_t n)
{
    const unsigned char *x = a, *y = b;
    for (size_t i = 0; i < n; i++)
        if (x[i] != y[i]) return x[i] < y[i] ? -1 : 1;
    return 0;
}

size_t strlen(const char *s)
{
    size_t n = 0;
    while (s[n]) n++;
    return n;
}

int strcmp(const char *a, const char *b)
{
    while (*a && *a == *b) a++, b++;
    return (unsigned char)*a - (unsigned char)*b;
}

void abort(void) { __builtin_trap(); } /* unreachable: the engine traps, the kernel contains */

/* compiler-rt's 128-bit product, which wasm32 code calls for a 64 x 64 -> 128 multiply: the low
 * 128 bits, from 32-bit halves, so it never calls itself */
typedef union {
    __int128 all;
    struct {
        uint64_t lo, hi;
    } s;
} n8_ti_t;

__int128 __multi3(__int128 a, __int128 b)
{
    n8_ti_t x = {.all = a}, y = {.all = b}, r;
    const uint64_t a0 = x.s.lo & 0xFFFFFFFFu, a1 = x.s.lo >> 32, b0 = y.s.lo & 0xFFFFFFFFu, b1 = y.s.lo >> 32;
    uint64_t t = a0 * b0;
    const uint64_t w0 = t & 0xFFFFFFFFu;
    t = a1 * b0 + (t >> 32);
    const uint64_t w1 = t & 0xFFFFFFFFu, w2 = t >> 32;
    t = a0 * b1 + w1;
    r.s.lo = t << 32 | w0;
    r.s.hi = a1 * b1 + w2 + (t >> 32) + x.s.hi * y.s.lo + x.s.lo * y.s.hi;
    return r.all;
}

float ldexpf(float x, int e)
{
    while (e > 0) { x *= 2.0f; e--; }
    while (e < 0) { x *= 0.5f; e++; }
    return x;
}

/* ---- the allocator: 16-byte blocks, a free list by address, neighbours merged ---------- */

typedef struct blk {
    size_t size;      /* the block's bytes, its header included */
    struct blk *next; /* the next free block, by address */
    size_t pad[2];
} blk_t;
_Static_assert(sizeof(blk_t) == 16, "a 16-byte header keeps every block 16-aligned");

extern unsigned char __heap_base;
static uintptr_t g_top, g_end;
static blk_t *g_free;

static size_t up16(size_t n) { return (n + 15) & ~(size_t)15; }

static int grow(size_t need)
{
    const size_t pages = (need + 65535) / 65536;
    if (__builtin_wasm_memory_grow(0, pages) == (size_t)-1) return 0;
    g_end += pages * 65536;
    return 1;
}

void *malloc(size_t n)
{
    if (!g_top) {
        g_top = up16((uintptr_t)&__heap_base);
        g_end = __builtin_wasm_memory_size(0) * 65536;
    }
    if (n > 0x7FFFFFF0u) return NULL;
    const size_t want = up16(n ? n : 1) + sizeof(blk_t);
    for (blk_t **pp = &g_free; *pp; pp = &(*pp)->next) {
        blk_t *b = *pp;
        if (b->size < want) continue;
        if (b->size - want >= 64) { /* split: the rest stays free, in b's place */
            blk_t *rest = (blk_t *)((uintptr_t)b + want);
            rest->size = b->size - want;
            rest->next = b->next;
            *pp = rest;
            b->size = want;
        } else {
            *pp = b->next;
        }
        return b + 1;
    }
    if (g_top + want > g_end && !grow(g_top + want - g_end)) return NULL;
    blk_t *b = (blk_t *)g_top;
    b->size = want;
    g_top += want;
    return b + 1;
}

void free(void *p)
{
    if (!p) return;
    blk_t *b = (blk_t *)p - 1, *prev = NULL, **pp = &g_free;
    while (*pp && *pp < b) {
        prev = *pp;
        pp = &(*pp)->next;
    }
    b->next = *pp;
    *pp = b;
    if (b->next && (uintptr_t)b + b->size == (uintptr_t)b->next) { /* merge with the one after */
        b->size += b->next->size;
        b->next = b->next->next;
    }
    if (prev && (uintptr_t)prev + prev->size == (uintptr_t)b) { /* and the one before */
        prev->size += b->size;
        prev->next = b->next;
        b = prev;
    }
    if ((uintptr_t)b + b->size == g_top) { /* the last block: back to the top */
        if (prev == b) {
            blk_t **q = &g_free;
            while (*q != b) q = &(*q)->next;
            *q = b->next;
        } else {
            *pp = b->next;
        }
        g_top = (uintptr_t)b;
    }
}

void *calloc(size_t k, size_t n)
{
    if (n && k > (size_t)-1 / n) return NULL;
    void *p = malloc(k * n);
    if (p) memset(p, 0, k * n);
    return p;
}

void *realloc(void *p, size_t n)
{
    if (!p) return malloc(n);
    blk_t *b = (blk_t *)p - 1;
    if (b->size - sizeof(blk_t) >= n) return p;
    void *q = malloc(n);
    if (!q) return NULL;
    memcpy(q, p, b->size - sizeof(blk_t));
    free(p);
    return q;
}
