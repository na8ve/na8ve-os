#!/usr/bin/env python3
"""na8ve-arduino-tool: Post-build verifier, optimizer, signer, and USB deployer
for the na8ve:esp32s3 Arduino IDE Boards Manager package.

Commands:
  build-pvm   Enforces capability policy, runs optional host test + control,
              strips metadata sections, optimizes/hardens, signs .n8pv, and writes bundle ZIP.
  size        Reports PROGRAM_BYTES and DATA_BYTES for Arduino IDE / arduino-cli.
  export-zip  Copies compiled .n8pv and submission .zip into the sketch folder.
  pair        Associates a developer board identity with the local signing key.
  upload      Streams signed .n8pv over USB CDC-ACM to the running board.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zipfile

TOOLS_DIR = pathlib.Path(__file__).resolve().parent
_PARENT = TOOLS_DIR.parent
PLATFORM_DIR = _PARENT if (_PARENT / "cores").exists() else (_PARENT / "arduino-core" / "na8ve" / "esp32s3" / "1.0.0")
sys.path.insert(0, str(TOOLS_DIR))

import harden_pvm  # noqa: E402
import licence     # noqa: E402
import sign_pvm    # noqa: E402

ALLOWED_IMPORTS = {"log", "now_us", "store_query", "ipc_send", "reply", "tool", "yield"}
REQUIRED_EXPORTS = {"memory", "n8_init", "n8_inbox", "n8_on_message"}
MAX_APP_PAYLOAD = 64512
# your own signing key: NA8VE_APP_KEY, else ~/.na8ve/app-key.pem
DEFAULT_KEY = pathlib.Path(os.environ.get("NA8VE_APP_KEY") or str(pathlib.Path.home() / ".na8ve" / "app-key.pem"))
ZIG_EXE = pathlib.Path(shutil.which("zig") or "C:/Espressif/tools/ziglang/ziglang/zig.exe")


def _read_leb_u32(b: bytes, p: int) -> tuple[int, int]:
    res = shift = 0
    while True:
        byte = b[p]
        p += 1
        res |= (byte & 0x7F) << shift
        if (byte & 0x80) == 0:
            return res, p
        shift += 7


def _read_leb_s32(b: bytes, p: int) -> tuple[int, int]:
    res = shift = 0
    while True:
        byte = b[p]
        p += 1
        res |= (byte & 0x7F) << shift
        shift += 7
        if (byte & 0x80) == 0:
            if byte & 0x40 and shift < 64:
                res -= 1 << shift
            return res, p


def inspect_wasm(wasm_bytes: bytes) -> dict:
    """Parse WebAssembly 1.0 sections to audit imports, exports, memory pages, stack, and custom sections."""
    if len(wasm_bytes) < 8 or wasm_bytes[:4] != b"\x00asm" or wasm_bytes[4:8] != b"\x01\x00\x00\x00":
        raise ValueError("not a valid WebAssembly 1.0 module")
    p = 8
    end = len(wasm_bytes)
    imports: list[tuple[str, str, int]] = []
    exports: dict[str, int] = {}
    memory_limits: tuple[int, int | None] | None = None
    global0_init: int | None = None
    custom_sections = 0

    while p < end:
        sec_id = wasm_bytes[p]
        p += 1
        sec_len, p = _read_leb_u32(wasm_bytes, p)
        sec_end = p + sec_len
        sp = p
        if sec_id == 0:
            custom_sections += 1
        elif sec_id == 2:  # Import section
            cnt, sp = _read_leb_u32(wasm_bytes, sp)
            for _ in range(cnt):
                mlen, sp = _read_leb_u32(wasm_bytes, sp)
                mod = wasm_bytes[sp:sp + mlen].decode("utf-8", "replace")
                sp += mlen
                nlen, sp = _read_leb_u32(wasm_bytes, sp)
                nm = wasm_bytes[sp:sp + nlen].decode("utf-8", "replace")
                sp += nlen
                kind = wasm_bytes[sp]
                sp += 1
                if kind == 0:
                    _, sp = _read_leb_u32(wasm_bytes, sp)
                elif kind == 1:
                    sp += 1
                    flag = wasm_bytes[sp]
                    sp += 1
                    _, sp = _read_leb_u32(wasm_bytes, sp)
                    if flag & 1:
                        _, sp = _read_leb_u32(wasm_bytes, sp)
                elif kind == 2:
                    flag = wasm_bytes[sp]
                    sp += 1
                    lo, sp = _read_leb_u32(wasm_bytes, sp)
                    hi = None
                    if flag & 1:
                        hi, sp = _read_leb_u32(wasm_bytes, sp)
                    memory_limits = (lo, hi)
                elif kind == 3:
                    sp += 2
                imports.append((mod, nm, kind))
        elif sec_id == 5:  # Memory section
            cnt, sp = _read_leb_u32(wasm_bytes, sp)
            if cnt > 0:
                flag = wasm_bytes[sp]
                sp += 1
                lo, sp = _read_leb_u32(wasm_bytes, sp)
                hi = None
                if flag & 1:
                    hi, sp = _read_leb_u32(wasm_bytes, sp)
                memory_limits = (lo, hi)
        elif sec_id == 6:  # Global section
            cnt, sp = _read_leb_u32(wasm_bytes, sp)
            for idx in range(cnt):
                sp += 2  # valtype + mutability
                opcode = wasm_bytes[sp]
                sp += 1
                val = None
                if opcode == 0x41:  # i32.const
                    val, sp = _read_leb_s32(wasm_bytes, sp)
                elif opcode == 0x42:
                    _, sp = _read_leb_s32(wasm_bytes, sp)
                elif opcode == 0x43:
                    sp += 4
                elif opcode == 0x44:
                    sp += 8
                elif opcode == 0x23:
                    _, sp = _read_leb_u32(wasm_bytes, sp)
                while sp < sec_end and wasm_bytes[sp] != 0x0B:
                    sp += 1
                sp += 1  # end (0x0B)
                if idx == 0:
                    global0_init = val
        elif sec_id == 7:  # Export section
            cnt, sp = _read_leb_u32(wasm_bytes, sp)
            for _ in range(cnt):
                nlen, sp = _read_leb_u32(wasm_bytes, sp)
                nm = wasm_bytes[sp:sp + nlen].decode("utf-8", "replace")
                sp += nlen
                kind = wasm_bytes[sp]
                sp += 1
                _, sp = _read_leb_u32(wasm_bytes, sp)
                exports[nm] = kind
        p = sec_end

    return {
        "imports": imports,
        "exports": exports,
        "memory": memory_limits,
        "global0_init": global0_init,
        "custom_sections": custom_sections,
    }


def run_host_test_gate(sketch_dir: pathlib.Path, sketch_name: str) -> None:
    """If test_<sketch>.c exists in sketch_dir, compile and run both the positive test and its
    mandatory failing _control twin (-DEXPECT_MISMATCH)."""
    stem = sketch_name[:-4] if sketch_name.endswith(".ino") else sketch_name
    test_file = sketch_dir / f"test_{stem}.c"
    if not test_file.exists():
        return
    test_src = test_file.read_text(encoding="utf-8")
    if "EXPECT_MISMATCH" not in test_src:
        raise ValueError(f"{test_file.name}: missing mandatory failing control (#ifdef EXPECT_MISMATCH)")

    ino_file = sketch_dir / f"{stem}.ino"
    core_dir = PLATFORM_DIR / "cores" / "na8ve_pvm"
    var_dir = PLATFORM_DIR / "variants" / "xiao_esp32s3_sense"
    lib_root = PLATFORM_DIR / "libraries"

    harness_cpp = r'''
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include "Arduino.h"

static char g_last_reply[1024];
static int32_t g_last_reply_len = 0;
static char g_last_log[1024];

extern "C" {
void n8_log(const char *msg, int32_t len) {
    int32_t c = len < 1023 ? len : 1023;
    if (c > 0 && msg) memcpy(g_last_log, msg, (size_t)c);
    g_last_log[c > 0 ? c : 0] = '\0';
}
int64_t n8_now_us(void) {
    static int64_t t = 1000000;
    t += 600000;
    return t;
}
int32_t n8_store_query(const char *q, int32_t qlen, int32_t k, char *out, int32_t cap) {
    (void)q; (void)qlen; (void)k;
    const char *mock = "id=1 score=0.9120\n";
    int32_t n = (int32_t)strlen(mock);
    if (n < cap) memcpy(out, mock, (size_t)n + 1);
    return n;
}
int32_t n8_ipc_send(int32_t to, int32_t op, const void *buf, int32_t len) {
    (void)buf; (void)len;
    return (to == 1 && (op == 1 || op == 4)) ? 0 : -11;
}
int32_t n8_reply(const void *buf, int32_t len) {
    int32_t c = len < 1023 ? len : 1023;
    if (c > 0 && buf) memcpy(g_last_reply, buf, (size_t)c);
    g_last_reply[c > 0 ? c : 0] = '\0';
    g_last_reply_len = c;
    return 0;
}
int32_t n8_tool(const char *json, int32_t len, char *out, int32_t cap) {
    (void)len;
    const char *resp = (json && strstr(json, "\"act\""))
        ? "{\"act\":\"fan\",\"state\":\"low\",\"verdict\":\"acted\"}"
        : "{\"subject\":\"device\",\"temp_c\":39.5,\"age_s\":0}";
    int32_t n = (int32_t)strlen(resp);
    if (n < cap) memcpy(out, resp, (size_t)n + 1);
    return n;
}
void n8_yield(void) {}
extern "C" uint8_t *n8_test_inbox_ptr(void);
const char *n8_test_last_reply(void) { return g_last_reply; }
int32_t n8_test_send_message(int32_t from, int32_t op, const void *data, int32_t len) {
    g_last_reply[0] = '\0';
    uint8_t *in = n8_test_inbox_ptr();
    if (len > 0 && data) memcpy(in, data, (size_t)len);
    return n8_on_message(from, op, len);
}
}
'''
    with tempfile.TemporaryDirectory(prefix="n8-ard-test-") as td:
        work = pathlib.Path(td)
        sketch_cpp = work / "sketch_combined.cpp"
        ino_text = ino_file.read_text(encoding="utf-8") if ino_file.exists() else ""
        sketch_cpp.write_text('#include "Arduino.h"\n' + ino_text + "\n" + harness_cpp, encoding="utf-8")

        inc_flags = [
            f"-I{core_dir}",
            f"-I{var_dir}",
            f"-I{lib_root / 'Na8veModel' / 'src'}",
            f"-I{lib_root / 'Na8veStore' / 'src'}",
            f"-I{lib_root / 'Na8veAct' / 'src'}",
            f"-I{lib_root / 'Na8veSeam' / 'src'}",
            f"-I{sketch_dir}",
        ]
        host_cxx_bin = shutil.which("g++")
        for role, is_control in (("test", False), ("control", True)):
            exe = work / f"{role}.exe"
            defs = ["-DN8_HOST_TEST=1"] + (["-DEXPECT_MISMATCH=1"] if is_control else [])
            cxx_prefix = [host_cxx_bin] if host_cxx_bin else [str(ZIG_EXE), "c++"]
            cmd = [
                *cxx_prefix, "-O1", *defs, *inc_flags,
                str(sketch_cpp),
                str(core_dir / "main.cpp"),
                str(core_dir / "n8_model.c"),
                str(core_dir / "n8_util.c"),
                str(test_file),
                "-o", str(exe),
            ]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(f"host {role} compilation failed:\n{r.stderr}")
            run_r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
            if not is_control and run_r.returncode != 0:
                raise RuntimeError(f"host unit test {test_file.name} failed (exit {run_r.returncode}):\n{run_r.stderr}")
            if is_control and run_r.returncode == 0:
                raise RuntimeError(f"mandatory control twin for {test_file.name} did NOT fail as required (exit 0)")


def parse_grant_args(args: argparse.Namespace) -> tuple[list[int], list[dict], str]:
    """Validate requested application grants and format CSV for upload."""
    if args.grant_accel:
        raise ValueError("policy refused: third-party Arduino pVMs cannot request 'accel' (use Na8veModel broker)")
    if args.grant_chat:
        raise ValueError("policy refused: third-party Arduino pVMs cannot request 'chat' (exclusive to cortex-mvp)")
    ipc_list: list[int] = []
    csv_parts: list[str] = []
    for target in args.grant_ipc or []:
        t = int(target)
        if t != 1:
            raise ValueError(f"policy refused: allowed_ipc [{t}] invalid; third-party apps may only send to broker slot 1")
        if 1 not in ipc_list:
            ipc_list.append(1)
            csv_parts.append("ipc:1")
    grants: list[dict] = []
    for st in args.grant_store or []:
        label, _, rights = st.partition(":")
        if label != "query" or rights != "r":
            raise ValueError(f"policy refused: store grant {st!r} must be 'query:r'")
        grants.append({"kind": "store", "label": "query", "rights": "r",
                       "why": "Read bounded context from the single-writer memory graph."})
        csv_parts.append("store:r")
    if args.grant_act:
        grants.append({"kind": "sensor", "label": "act", "rights": "r",
                       "why": "Submit actuator state proposals to the board actuator safety policy table."})
        csv_parts.append("act")
    if args.grant_seam:
        grants.append({"kind": "sensor", "label": "seam", "rights": "r",
                       "why": "Read metadata-only sensor subjects from the kernel observation seam."})
        csv_parts.append("seam")
    return ipc_list, grants, (",".join(csv_parts) if csv_parts else "none")


def cmd_build_pvm(args: argparse.Namespace) -> int:
    try:
        ipc_list, grants, grants_csv = parse_grant_args(args)
    except ValueError as e:
        sys.stderr.write(f"na8ve-arduino-tool: {e}\n")
        return 1

    raw_wasm_path = pathlib.Path(args.wasm)
    if not raw_wasm_path.exists():
        sys.stderr.write(f"na8ve-arduino-tool: missing raw wasm {raw_wasm_path}\n")
        return 1
    raw_bytes = raw_wasm_path.read_bytes()

    try:
        info = inspect_wasm(raw_bytes)
    except ValueError as e:
        sys.stderr.write(f"na8ve-arduino-tool: {e}\n")
        return 1

    # Gate 1: Check Wasm imports and exports against application sandbox policy
    for mod, nm, kind in info["imports"]:
        if mod != "na8ve" or kind != 0:
            sys.stderr.write(f"na8ve-arduino-tool: forbidden import {mod}.{nm} (kind={kind})\n")
            return 1
        if nm not in ALLOWED_IMPORTS:
            sys.stderr.write(
                f"na8ve-arduino-tool: policy refused: import 'na8ve.{nm}' is not permitted by the application sandbox policy\n"
            )
            return 1
        if nm == "ipc_send" and 1 not in ipc_list:
            sys.stderr.write("na8ve-arduino-tool: module imports ipc_send but --grant-ipc=1 was not declared\n")
            return 1
        if nm == "store_query" and not any(g["kind"] == "store" for g in grants):
            sys.stderr.write("na8ve-arduino-tool: module imports store_query but --grant-store=query:r was not declared\n")
            return 1
        if nm == "tool" and not (args.grant_act or args.grant_seam):
            sys.stderr.write("na8ve-arduino-tool: module imports tool but neither --grant-act nor --grant-seam was declared\n")
            return 1

    missing_exp = REQUIRED_EXPORTS - set(info["exports"].keys())
    if missing_exp:
        sys.stderr.write(f"na8ve-arduino-tool: missing required WIT exports: {sorted(missing_exp)}\n")
        return 1

    if not info["memory"] or info["memory"][1] is None or info["memory"][1] * 65536 > args.linear:
        sys.stderr.write(f"na8ve-arduino-tool: linear memory {info['memory']} exceeds ceiling {args.linear}\n")
        return 1

    # Gate 2: Run host unit test + mandatory failing control if present
    sketch_dir = pathlib.Path(args.sketch_dir) if args.sketch_dir else raw_wasm_path.parent
    raw_name = args.name[:-4] if args.name.endswith(".ino") else args.name
    try:
        run_host_test_gate(sketch_dir, raw_name)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"na8ve-arduino-tool: host test gate refused: {e}\n")
        return 1

    # Gate 3: Strip metadata sections, optimize WebAssembly, and harden
    if args.harden:
        hardened_bytes, _rep = harden_pvm.harden(
            raw_bytes,
            passes=args.harden_passes,
            seed=args.seed,
            require_mutate=False,
            optimize_ir=True,
        )
    else:
        hardened_bytes, _dropped = harden_pvm.strip_custom(raw_bytes)

    post_info = inspect_wasm(hardened_bytes)
    if post_info["custom_sections"] != 0:
        sys.stderr.write("na8ve-arduino-tool: custom sections remained after hardening\n")
        return 1

    # Gate 4: Sign .n8pv application container
    clean_name = "".join(c if (c.isalnum() or c in "_-") else "_" for c in raw_name)[:16].rstrip("_-") or "arduino_app"
    key_path = pathlib.Path(args.key)
    if not key_path.exists():
        sys.stderr.write(
            f"na8ve-arduino-tool: signing key not found at {key_path} "
            "(set NA8VE_APP_KEY or generate one with `python tools/sign_pvm.py keygen --key <path>`)\n"
        )
        return 1
    key = sign_pvm.load_key(key_path)
    n8pv_bytes = sign_pvm.sign_bytes(key, hardened_bytes, clean_name)
    if len(n8pv_bytes) > MAX_APP_PAYLOAD:
        sys.stderr.write(
            f"na8ve-arduino-tool: signed payload {len(n8pv_bytes)} B exceeds app ceiling {MAX_APP_PAYLOAD} B\n"
        )
        return 1

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(n8pv_bytes)
    if args.elf_alias:
        pathlib.Path(args.elf_alias).write_bytes(n8pv_bytes)

    # Gate 5: Submission Bundle (.zip)
    if args.zip_out:
        manifest_entry = {
            "name": clean_name,
            "version": "1.0.0",
            "summary": f"Arduino IDE pVM application ({clean_name}) for na8ve-os ESP32-S3.",
            "core": 0,
            "mem_linear": args.linear,
            "stack": args.stack,
            "budget_ms": args.budget_ms,
            "allowed_ipc": ipc_list,
            "grants": grants,
            "grants_csv": grants_csv,
        }
        receipt = {
            "name": clean_name,
            "raw_wasm_bytes": len(raw_bytes),
            "hardened_wasm_bytes": len(hardened_bytes),
            "hardened_wasm_sha256": hashlib.sha256(hardened_bytes).hexdigest(),
            "n8pv_bytes": len(n8pv_bytes),
            "n8pv_sha256": hashlib.sha256(n8pv_bytes).hexdigest(),
            "custom_sections": post_info["custom_sections"],
            "grants_csv": grants_csv,
        }
        zip_path = pathlib.Path(args.zip_out)
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest-entry.json", json.dumps(manifest_entry, indent=2) + "\n")
            zf.writestr("receipt.json", json.dumps(receipt, indent=2) + "\n")
            zf.writestr(f"{clean_name}.n8pv", n8pv_bytes)
            if sketch_dir.exists():
                for f in sorted(sketch_dir.iterdir()):
                    if f.is_file() and f.suffix in (".ino", ".c", ".cpp", ".h", ".md"):
                        zf.write(f, arcname=f.name)

    print(
        f"na8ve-arduino-tool: built {out_path.name} ({len(n8pv_bytes)} B, wasm={len(hardened_bytes)} B, "
        f"custom_sections=0, grants={grants_csv})"
    )
    return 0


def cmd_size(args: argparse.Namespace) -> int:
    n8pv = pathlib.Path(args.n8pv)
    size_b = n8pv.stat().st_size if n8pv.exists() else 0
    print(f"PROGRAM_BYTES: {size_b}")
    print("DATA_BYTES: 8192")
    return 0


def cmd_export_zip(args: argparse.Namespace) -> int:
    src_zip = pathlib.Path(args.src)
    src_n8pv = pathlib.Path(args.n8pv)
    dst_dir = pathlib.Path(args.dst_dir)
    if src_zip.exists() and dst_dir.exists():
        shutil.copy2(src_zip, dst_dir / src_zip.name)
    if src_n8pv.exists() and dst_dir.exists():
        shutil.copy2(src_n8pv, dst_dir / src_n8pv.name)
    return 0


class SerialConsole:
    """Connects to the running na8ve-os USB CDC-ACM console without asserting RTS/DTR reset."""
    def __init__(self, port: str):
        import serial
        self.s = serial.Serial()
        self.s.port = port
        self.s.baudrate = 115200
        self.s.timeout = 0.5
        self.s.dtr = False
        self.s.rts = False
        self.s.open()
        self.buf = b""

    def close(self) -> None:
        self.s.close()

    def read_line(self, timeout: float = 30.0) -> str:
        import re
        log_re = re.compile(
            r"^(?:[EWIDV] \(\d+\) |ESP-ROM:|Build:|rst:0x|configsip:|SPIWP:|mode:|load:0x|entry 0x|"
            r"Saved PC:|Guru Meditation|Backtrace:|Core +\d|Rebooting|abort\(\)|\*\*\*ERROR)"
        )
        end = time.time() + timeout
        while True:
            while b"\n" not in self.buf:
                if time.time() > end:
                    raise TimeoutError("timeout waiting for na8ve-os console reply")
                self.buf += self.s.read(self.s.in_waiting or 1)
            raw, _, self.buf = self.buf.partition(b"\n")
            text = raw.decode("utf-8", "replace").rstrip("\r")
            if not log_re.match(text):
                return text

    def sync(self) -> None:
        nonce = str(int(time.time() * 1000))
        self.s.write(f"\nhello {nonce}\n".encode("utf-8"))
        end = time.time() + 10.0
        while time.time() < end:
            try:
                ln = self.read_line(timeout=1.5)
                if ln.startswith(f"OK hello {nonce}"):
                    return
            except TimeoutError:
                self.s.write(f"\nhello {nonce}\n".encode("utf-8"))
        raise TimeoutError("board did not respond to hello on USB console")

    def cmd(self, line: str, timeout: float = 30.0) -> list[str]:
        self.s.write((line + "\n").encode("utf-8"))
        out = []
        while True:
            ln = self.read_line(timeout=timeout)
            out.append(ln)
            if ln.startswith("OK") or ln.startswith("ERR"):
                return out


def mint_dev_licence(key, mac_str: str, seq: int = 0, name: str = "*dev-pvm1*", ref: str = "arduino-ide-dev") -> bytes:
    """Mint a 1,024-byte N8LC certificate bound to `mac_str`, embedding the developer RSA-3072 public
    modulus at offset 460..843 and setting flags=0x0003 (paid + dev board delegation)."""
    hashes, _, padding, _, utils = sign_pvm._crypto()
    mac = licence.parse_mac(mac_str)
    pub = sign_pvm.pubkey_bytes(key)
    mod_n = pub[:384]
    ref_digest = hashlib.sha256(mod_n).digest()
    nm = name.encode("ascii")[:16].ljust(16, b"\x00")
    flags = 0x0003
    issued = int(time.time())
    body = (
        b"N8LC"
        + struct.pack("<I", 1)
        + nm
        + struct.pack("<I", seq)
        + mac
        + struct.pack("<HQ", flags, issued)
        + ref_digest
    )
    assert len(body) == 76
    sig = key.sign(
        hashlib.sha256(body).digest(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
        utils.Prehashed(hashes.SHA256()),
    )
    tail = mod_n + b"\x00" * (1024 - 76 - 384 - 384)
    lic = body + sig + tail
    assert len(lic) == 1024
    return lic


def cmd_pair(args: argparse.Namespace) -> int:
    key = sign_pvm.load_key(pathlib.Path(args.key))
    con = SerialConsole(args.port)
    try:
        con.sync()
        mac_lines = con.cmd("os-mac")
        if not mac_lines[-1].startswith("OK os-mac mac="):
            sys.stderr.write(f"na8ve-arduino-tool: os-mac failed: {mac_lines}\n")
            return 1
        mac_str = mac_lines[-1].split("mac=", 1)[1].strip()
        if args.override_mac:
            mac_str = args.override_mac
        lic = mint_dev_licence(key, mac_str, seq=args.seq, name=args.name)
        # Write in two 512-byte chunks to stay well inside console line limits
        for off in (0, 512):
            chunk_hex = lic[off:off + 512].hex()
            res = con.cmd(f"os-pvm-licence {off} {chunk_hex}")
            if not res[-1].startswith("OK"):
                sys.stderr.write(f"na8ve-arduino-tool: os-pvm-licence failed at {off}: {res}\n")
                return 1
        print(f"na8ve-arduino-tool: paired developer certificate for MAC {mac_str} (name={args.name})")
        return 0
    finally:
        con.close()


def cmd_upload(args: argparse.Namespace) -> int:
    if args.slot not in ("pvm_1", "onchip", "default"):
        sys.stderr.write(
            f"na8ve-arduino-tool: unsupported upload slot {args.slot!r} (only on-chip app slot is supported)\n"
        )
        return 1
    try:
        _, _, grants_csv = parse_grant_args(args)
    except ValueError as e:
        sys.stderr.write(f"na8ve-arduino-tool: {e}\n")
        return 1

    n8pv_path = pathlib.Path(args.n8pv)
    if not n8pv_path.exists():
        sys.stderr.write(f"na8ve-arduino-tool: payload {n8pv_path} does not exist\n")
        return 1
    data = n8pv_path.read_bytes()
    if len(data) > MAX_APP_PAYLOAD:
        sys.stderr.write(f"na8ve-arduino-tool: payload {len(data)} B > {MAX_APP_PAYLOAD} B ceiling\n")
        return 1
    sha_hex = hashlib.sha256(data).hexdigest()

    t0 = time.time()
    con = SerialConsole(args.port)
    try:
        con.sync()
        begin_res = con.cmd(f"os-pvm-begin {len(data)} {sha_hex} {grants_csv}")
        if not begin_res[-1].startswith("OK"):
            sys.stderr.write(f"na8ve-arduino-tool: {begin_res[-1]}\n")
            return 1

        chunk_size = 512
        for off in range(0, len(data), chunk_size):
            part = data[off:off + chunk_size]
            c_res = con.cmd(f"os-pvm-chunk {off} {part.hex()}")
            if not c_res[-1].startswith("OK"):
                sys.stderr.write(f"na8ve-arduino-tool: chunk at {off} failed: {c_res[-1]}\n")
                return 1

        commit_res = con.cmd("os-pvm-commit")
        if not commit_res[-1].startswith("OK"):
            sys.stderr.write(f"na8ve-arduino-tool: {commit_res[-1]}\n")
            return 1

        dt = time.time() - t0
        print(f"na8ve-arduino-tool: uploaded {n8pv_path.name} ({len(data)} B) to {args.port} in {dt:.2f}s -> {commit_res[-1]}")
        return 0
    finally:
        con.close()


def _add_grant_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--grant-ipc", action="append", default=[], help="IPC target domain (only 1 is allowed)")
    p.add_argument("--grant-store", action="append", default=[], help="Store grant (query:r)")
    p.add_argument("--grant-act", action="store_true", help="Allow policy-mediated actuator proposals")
    p.add_argument("--grant-seam", action="store_true", help="Allow metadata-only sensor seam reads")
    p.add_argument("--grant-accel", action="store_true", help="Forbidden on third-party pVMs")
    p.add_argument("--grant-chat", action="store_true", help="Forbidden on third-party pVMs")


def main() -> int:
    ap = argparse.ArgumentParser(prog="na8ve-arduino-tool")
    sub = ap.add_subparsers(dest="cmd", required=True)

    bp = sub.add_parser("build-pvm")
    bp.add_argument("--wasm", required=True)
    bp.add_argument("--sketch-dir", default="")
    bp.add_argument("--name", required=True)
    bp.add_argument("--linear", type=int, default=65536)
    bp.add_argument("--stack", type=int, default=8192)
    bp.add_argument("--budget-ms", type=int, default=2000)
    bp.add_argument("--harden", action="store_true")
    bp.add_argument("--strip-only", action="store_true")
    bp.add_argument("--harden-passes", type=int, default=4)
    bp.add_argument("--seed", type=lambda x: int(x, 0), default=0x6E385056)
    bp.add_argument("--key", default=str(DEFAULT_KEY))
    bp.add_argument("--out", required=True)
    bp.add_argument("--zip-out", default="")
    bp.add_argument("--elf-alias", default="")
    _add_grant_flags(bp)

    sz = sub.add_parser("size")
    sz.add_argument("--n8pv", required=True)
    sz.add_argument("--wasm", default="")

    ex = sub.add_parser("export-zip")
    ex.add_argument("--src", required=True)
    ex.add_argument("--n8pv", required=True)
    ex.add_argument("--dst-dir", required=True)

    pr = sub.add_parser("pair")
    pr.add_argument("--port", required=True)
    pr.add_argument("--key", default=str(DEFAULT_KEY))
    pr.add_argument("--name", default="*dev-pvm1*")
    pr.add_argument("--seq", type=int, default=0)
    pr.add_argument("--override-mac", default="")

    up = sub.add_parser("upload")
    up.add_argument("--port", required=True)
    up.add_argument("--slot", default="pvm_1")
    up.add_argument("--n8pv", required=True)
    up.add_argument("--verbose", action="store_true")
    _add_grant_flags(up)

    args = ap.parse_args()
    if args.cmd == "build-pvm":
        return cmd_build_pvm(args)
    if args.cmd == "size":
        return cmd_size(args)
    if args.cmd == "export-zip":
        return cmd_export_zip(args)
    if args.cmd == "pair":
        return cmd_pair(args)
    if args.cmd == "upload":
        return cmd_upload(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
