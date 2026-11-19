# Broker App: Cognitive Neural Inference via Model Broker

Demonstrates how an application with no direct model access submits asynchronous inference turns to the system cognitive engine using the na8ve-os Model Broker client.

## Files

| File | Description |
|---|---|
| `ask.c` | Application code: queues an asynchronous model turn (`op 0x10`) and retrieves generated text (`op 0x11`). |
| `manifest-entry.json` | Capability manifest: grants `allowed_ipc: [1]` (permission to message the model broker). |
| `test_ask.c` | Native host unit test simulating the kernel and model broker, with negative control twin (`-DEXPECT_MISMATCH`). |

## Host Testing & Verification

```bash
# Compile and run positive test
gcc -I../../sdk/include ask.c test_ask.c ../../sdk/src/n8_util.c ../../sdk/src/n8_model.c -o test_ask
./test_ask

# Compile and run failing control twin (broker refusal must be caught)
gcc -DEXPECT_MISMATCH -I../../sdk/include ask.c test_ask.c ../../sdk/src/n8_util.c ../../sdk/src/n8_model.c -o test_ask_control
./test_ask_control
```

## Compiling for WebAssembly Target

```bash
python ../../tools/build_app.py --name ask --src ask.c --model-client --out dist/
```

## Arduino Uno Q (Arduino App Lab)

`applab/` is this example as an Arduino App Lab app, built on the App Lab Bricks (`arduino:web_ui`, `na8ve:cognitive_os`, `na8ve:memory_graph`). Install it with **Install via USB** on the distribution site's **Apps** page, or package it with the Arduino App Lab SDK ([`sdk/arduino-app-lab/`](../../sdk/arduino-app-lab/README.md)) and import the `.zip` in Arduino App Lab. It runs on a board with the free licence.

`python/main.py` admits this sandbox, asks the model broker a question through it (op `0x10`), reads the answer back (op `0x11`), and serves the dashboard through the WebUI brick on port 7000, whose chat asks the same model.
