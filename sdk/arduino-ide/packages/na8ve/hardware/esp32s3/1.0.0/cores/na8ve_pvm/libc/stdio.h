/* stdio for a pVM: formatting into memory only, no stream (n8_stdio.c) */
#ifndef N8_STDIO_H
#define N8_STDIO_H
#include <stdarg.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
int snprintf(char *b, size_t cap, const char *f, ...) __attribute__((format(printf, 3, 4)));
int vsnprintf(char *b, size_t cap, const char *f, va_list ap) __attribute__((format(printf, 3, 0)));
int sscanf(const char *s, const char *f, ...);
#ifdef __cplusplus
}
#endif
#endif
