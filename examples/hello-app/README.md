# Hello App: Developer Quickstart Example

A minimal na8ve-os application demonstrating state persistence across message dispatches, monotonic clock readings, and persistent memory graph recall.

## Files

| File | Description |
|---|---|
| `hello.c` | Application code: handles ping (`op 1`), stores a name (`op 0x10`), greets with uptime (`op 0x11`), and queries the memory graph (`op 0x12`). |
| `manifest-entry.json` | Capability manifest: grants 64 KB linear memory, 8 KB stack, and `store` query access. |
| `test_hello.c` | Native host unit test harness with positive assertions and failing control twin (`-DEXPECT_MISMATCH`). |

## Host Testing & Verification

Run native host unit tests before targeting silicon:

```bash
# Compile and run positive test
gcc -I../../sdk/include hello.c test_hello.c ../../sdk/src/n8_util.c -o test_hello
./test_hello

# Compile and run negative control twin (must fail as required)
gcc -DEXPECT_MISMATCH -I../../sdk/include hello.c test_hello.c ../../sdk/src/n8_util.c -o test_hello_control
./test_hello_control
```

## Compiling for WebAssembly Target

To compile the application into a relocatable, freestanding WebAssembly module:

```bash
python ../../tools/build_app.py --name hello --src hello.c --out dist/
```
