---
name: Bug Report
about: Create a report to help us improve na8ve-os or the Application SDK
title: '[BUG] '
labels: bug
assignees: ''
---

**Target Silicon**
- [ ] Seeed Studio XIAO ESP32-S3 Sense
- [ ] Arduino Uno Q (Qualcomm QRB2210 + STM32U585)
- [ ] Host Simulator / Test Harness (`core-host`)
- [ ] Other (please specify)

**Component Affected**
- [ ] Application SDK (`sdk/`)
- [ ] Host Build Tooling (`tools/build_app.py`, `tools/sign_app.py`, `tools/build_manifest.py`)
- [ ] Browser Flasher (WebUSB / WebSerial)
- [ ] Microkernel Core / Isolation (L1/L2)
- [ ] WAMR Application Sandbox (L3/L4)
- [ ] Memory Graph Engine (`excel.csv`)
- [ ] Recurrent Neural Engine / Accelerators
- [ ] Actuator Safety Monitor / GPIO

**Describe the Bug**
A clear and concise description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Manifest configuration: `...`
2. Application code / SDK call: `...`
3. Toolchain command: `...`
4. Console output / failure log: `...`

**Expected Behavior**
A clear and concise description of what you expected to happen.

**Console / Error Logs**
```text
Paste serial console or compiler logs here
```

**Environment**
- OS: [e.g. Ubuntu 24.04, Windows 11, macOS 14]
- Compiler / Toolchain: [e.g. Zig 0.13.0, Clang 18, MinGW-w64]
- Python Version: [e.g. 3.10.12]

