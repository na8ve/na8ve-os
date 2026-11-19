# 02 — Freestanding Runtime & Micro-Libc

Traditional standard C libraries (glibc, musl, newlib) rely on POSIX system calls (`brk`, `sbrk`, `mmap`, `write`, `open`) and maintain substantial internal state (thread-local errno, locales, stream file descriptors, buffer locks). In **na8ve-os**, applications execute in a strict freestanding WebAssembly environment where the kernel provides zero POSIX syscalls.

The **na8ve-os Micro-Libc** (`firmware/pvm/sdk/n8_libc.c`, `n8_stdio.c`, `n8_util.c`) is an ultralight, zero-syscall, zero-dynamic-allocation implementation designed specifically for embedded pVM sandboxes.

---

## 1. Architectural Principles

1. **Zero Kernel Reach:** No libc function ever triggers a trap, hypercall, or kernel context switch. All operations occur strictly within the pVM's bounded linear WebAssembly memory.
2. **Zero Ambient Allocations:** Standard library functions do not call dynamic allocators. All work buffers, formatting strings, and tables are caller-provided or statically allocated.
3. **Deterministic Memory Trapping:** If an application accesses memory past its manifest-configured `mem_linear` ceiling, the underlying engine (WAMR) immediately halts execution.
4. **Hardware Acceleration via Wasm Primitives:** When compiled with `-mbulk-memory`, memory manipulation leverages native WebAssembly opcodes (`memory.copy`, `memory.fill`) executed at silicon speed by the JIT/interpreter.

---

## 2. Component Files

The freestanding runtime is split across several small modules in [`sdk/`](../../sdk/):

```
firmware/pvm/sdk/
├── n8_libc.c        # Core memory and string primitives: memcpy, memmove, memset, memcmp, strlen
├── n8_stdio.c       # Safe snprintf, vsnprintf, sscanf, strtod, math (expf, logf)
├── n8_util.c        # Formatted output utilities (n8_put, n8_put_u, n8_put_hex, n8_reply_str)
├── n8_act_input.c   # Parses structured JSON action inputs for actuators
└── libc/            # Freestanding C standard headers
    ├── ctype.h      # isdigit, isspace, isalpha, tolower, toupper
    ├── math.h       # expf, logf, fabsf
    ├── stdio.h      # snprintf, vsnprintf, NULL, size_t
    ├── stdlib.h     # strtod, strtol, abs
    └── string.h     # memcpy, memset, memmove, memcmp, strlen, strcmp, strstr
```

---

## 3. Memory & String Operations (`n8_libc.c`)

### 3.1 Bulk-Memory vs. Aligned Loop Emulation
When targeting WAMR on ARMv8-A or ESP32-S3, the compiler is configured with `-mbulk-memory`:
```c
#if defined(__wasm_bulk_memory__)
void *memcpy(void *d, const void *s, size_t n) {
    __builtin_memcpy(d, s, n); /* Lowers to Wasm opcode: memory.copy */
    return d;
}

void *memset(void *d, int c, size_t n) {
    __builtin_memset(d, c, n); /* Lowers to Wasm opcode: memory.fill */
    return d;
}
#else
/* Fallback: 32-bit aligned word copies */
void *memcpy(void *d, const void *s, size_t n) {
    unsigned char *a = d;
    const unsigned char *b = s;
    if ((((uintptr_t)a | (uintptr_t)b) & 3) == 0)
        for (; n >= 4; n -= 4, a += 4, b += 4) 
            *(uint32_t *)a = *(const uint32_t *)b;
    while (n--) *a++ = *b++;
    return d;
}
#endif
```

### 3.2 Implemented String Functions
* `size_t strlen(const char *s);`
* `int memcmp(const void *a, const void *b, size_t n);`
* `void *memchr(const void *s, int c, size_t n);`
* `char *strchr(const char *s, int c);`
* `char *strstr(const char *haystack, const char *needle);`
* `int strncmp(const char *a, const char *b, size_t n);`

---

## 4. Bounded Formatting & I/O (`n8_stdio.c`, `n8_util.c`)

### 4.1 Bounded `snprintf` and `vsnprintf`
`n8_stdio.c` provides a compact implementation of `vsnprintf` supporting the exact format specifiers needed for system telemetry, logging, and JSON parsing:
* Supported format specifiers: `%s`, `%c`, `%d`, `%i`, `%u`, `%x`, `%f`.
* Supported flags: `0` (zero-padding), `-` (left-alignment), width, precision, `.*`.
* Supported size prefixes: `l` (`long`), `ll` (`long long`), `z` (`size_t`).
* **Guarantee:** The output buffer is **always** NUL-terminated, even on truncation.

### 4.2 Allocation-Free String Builders (`n8_util.c`)
For fast, deterministic responses without `snprintf` parsing overhead, the SDK provides `n8_put_*` routines that maintain an in-place write pointer `at`:

```c
void n8_put(char *b, int *at, int cap, const char *s);
void n8_put_u(char *b, int *at, int cap, uint64_t v);
void n8_put_hex(char *b, int *at, int cap, const uint8_t *p, int n);
int32_t n8_reply_str(const char *s);
```

#### Operational Invariant
* If `*at >= cap - 1`, subsequent writes are silently dropped, preventing buffer overruns.
* `b[cap - 1]` is always set to `\0`.

---

## 5. Linear Memory & Stack Layout

When `tools/build_pvm.py` links an application with `wasm-ld`, it enforces the **`--stack-first`** memory layout:

```
+-----------------------------------------------------------------+
| Offset 0x00000 .. [stack_size]                                  |
| Shadow Operand Stack (e.g. 8 KiB or 16 KiB)                     |
| (Grows downwards; hitting 0x0 triggers instant hardware fault)  |
+-----------------------------------------------------------------+
| Data & BSS Sections (Global variables, static buffers)          |
| - g_inbox[N8_MSG_MAX]                                           |
| - Application state variables                                   |
+-----------------------------------------------------------------+
| Unused Linear Memory / Heap Arena                               |
| - Bounded by manifest "mem_linear" (e.g. 64 KiB or 192 KiB)     |
+-----------------------------------------------------------------+
```

### Why `--stack-first`?
In standard WebAssembly, the stack is placed after the global data section. If a stack overflow occurs, it silently corrupts application global state before faulting. With `--stack-first`:
1. The stack starts at the bottom of memory.
2. An unbounded recursive call or stack allocation immediately attempts to write below offset `0`, triggering an instant out-of-bounds trap in WAMR.
3. Global variables and the inbox buffer remain completely pristine and uncorrupted.

