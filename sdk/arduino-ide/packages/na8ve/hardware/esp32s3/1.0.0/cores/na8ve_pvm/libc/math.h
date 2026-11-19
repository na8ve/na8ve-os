/* The pVM libc's math.h: WebAssembly's own f64.floor and f64.sqrt, and ldexpf (n8_libc.c). */
#ifndef N8_MATH_H
#define N8_MATH_H

#ifdef __cplusplus
extern "C" {
#endif

static inline double floor(double x) { return __builtin_floor(x); }
static inline double sqrt(double x) { return __builtin_sqrt(x); }
float ldexpf(float x, int e);
float expf(float x); /* n8_stdio.c: through double */
float logf(float x);
double log(double x);
#define INFINITY __builtin_inff()

#ifdef __cplusplus
}
#endif

#endif
