/* The pVM libc's stdlib.h (n8_libc.c): an allocator over the module's own linear memory. */
#ifndef N8_STDLIB_H
#define N8_STDLIB_H
#include <stddef.h>
void *malloc(size_t n);
void *calloc(size_t k, size_t n);
void *realloc(void *p, size_t n);
void free(void *p);
double strtod(const char *s, char **end);
void abort(void) __attribute__((noreturn));
#endif
