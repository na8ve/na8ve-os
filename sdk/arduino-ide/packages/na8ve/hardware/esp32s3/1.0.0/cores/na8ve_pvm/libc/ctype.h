/* ctype for a pVM, the C locale (n8_stdio.c) */
#ifndef N8_CTYPE_H
#define N8_CTYPE_H

#ifdef __cplusplus
extern "C" {
#endif

int isspace(int c);
int isdigit(int c);
int isalpha(int c);
int isalnum(int c);
int isupper(int c);
int islower(int c);
int ispunct(int c);
int isxdigit(int c);
int tolower(int c);
int toupper(int c);

#ifdef __cplusplus
}
#endif

#endif
