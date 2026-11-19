/* The pVM libc's string.h (n8_libc.c): wasm32 freestanding. */
#ifndef N8_STRING_H
#define N8_STRING_H
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
void *memcpy(void *d, const void *s, size_t n);
void *memmove(void *d, const void *s, size_t n);
void *memset(void *d, int c, size_t n);
int memcmp(const void *a, const void *b, size_t n);
size_t strlen(const char *s);
int strcmp(const char *a, const char *b);
int strncmp(const char *a, const char *b, size_t n);
void *memchr(const void *s, int c, size_t n);
char *strchr(const char *s, int c);
char *strstr(const char *h, const char *n);
size_t strspn(const char *s, const char *set);
size_t strcspn(const char *s, const char *set);
#ifdef __cplusplus
}
#endif
#endif
