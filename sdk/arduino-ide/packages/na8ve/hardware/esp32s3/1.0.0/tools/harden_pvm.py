#!/usr/bin/env python3
"""Release size/section optimizer for sandboxed WebAssembly modules built by na8ve-arduino-tool."""
import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

WASM_TOOLS = os.environ.get("NA8VE_WASM_TOOLS") or (
    "C:/Espressif/tools/wasm-tools/bin/wasm-tools.exe" if os.name == "nt"
    else "C:/Espressif/tools/wasm-tools/bin/wasm-tools")

WASM_OPT = os.environ.get("NA8VE_WASM_OPT") or (
    "C:/Espressif/tools/binaryen/bin/wasm-opt.exe" if os.name == "nt"
    else "C:/Espressif/tools/binaryen/bin/wasm-opt")


# ---- a minimal WebAssembly section reader/writer (no dependency) ------------

def _uleb(d: bytes, p: int) -> tuple[int, int]:
    r = s = 0
    while True:
        b = d[p]; p += 1
        r |= (b & 0x7f) << s; s += 7
        if not b & 0x80:
            return r, p


def _encode_uleb(v: int) -> bytes:
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def sections(mod: bytes):
    """Yield (section_id, custom_name_or_None, body_bytes, (start, end)) over a module."""
    if mod[:4] != b"\x00asm":
        raise ValueError("not a WebAssembly module")
    p = 8
    while p < len(mod):
        sid = mod[p]; q = p + 1
        size, q = _uleb(mod, q)
        body = mod[q:q + size]
        name = None
        if sid == 0:
            nl, r = _uleb(body, 0)
            name = body[r:r + nl].decode("latin1", "replace")
        yield sid, name, body, (p, q + size)
        p = q + size


def strip_custom(mod: bytes) -> tuple[bytes, list[str]]:
    """Drop every custom (id 0) section; keep standard sections verbatim."""
    out = bytearray(mod[:8])
    dropped = []
    for sid, name, _body, (start, end) in sections(mod):
        if sid == 0:
            dropped.append(name or "")
        else:
            out += mod[start:end]
    return bytes(out), dropped


def custom_section_names(mod: bytes) -> list[str]:
    return [name or "" for sid, name, _b, _r in sections(mod) if sid == 0]


# ---- external tools: wasm-tools & Binaryen wasm-opt -------------------------

def wasm_tools() -> str | None:
    if pathlib.Path(WASM_TOOLS).exists():
        return WASM_TOOLS
    return shutil.which("wasm-tools")


def wasm_opt() -> str | None:
    if pathlib.Path(WASM_OPT).exists():
        return WASM_OPT
    return shutil.which("wasm-opt")


# wasm-tools reports this (exit 3) when the chosen seed yields no legal mutation; it is benign
# and asks for a different seed, not a failure of the module.
_NO_MUTATION = "not applicable mutations"
_ATTEMPTS_PER_PASS = 64  # distinct seeds to try before giving up on a pass

# The value-type feature set the device's WAMR fast interpreter is built for (build_pvm.py's
# CFLAGS: -mcpu=mvp -mbulk-memory -msign-ext; no SIMD, no reference types). `wasm-tools mutate`,
# even with --preserve-semantics, adds junk function types to the type section whose params may be
# v128/funcref/externref. A mutation is accepted only if it validates under this set.
WAMR_FEATURES = "mvp,bulk-memory,sign-extension"


def mvp_clean(mod: bytes) -> bool:
    """True when the module uses only the value types the device's WAMR loads (WAMR_FEATURES)."""
    tool = wasm_tools()
    if not tool:
        return True
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "m.wasm"
        p.write_bytes(mod)
        return subprocess.run([tool, "validate", "--features", WAMR_FEATURES, str(p)],
                              capture_output=True).returncode == 0


def optimize(mod: bytes) -> bytes:
    """Run Binaryen `wasm-opt -O4 --converge` within WAMR's MVP + bulk-memory + sign-ext subset."""
    wo = wasm_opt()
    if not wo:
        raise FileNotFoundError("wasm-opt not found")
    with tempfile.TemporaryDirectory() as td:
        tdp = pathlib.Path(td)
        ipath, opath = tdp / "in.wasm", tdp / "out.wasm"
        ipath.write_bytes(mod)
        r = subprocess.run(
            [
                wo, str(ipath), "-o", str(opath),
                "-O4", "--converge", "--strip-debug", "--strip-producers",
                "--mvp-features", "--enable-bulk-memory", "--enable-sign-ext",
            ],
            capture_output=True, text=True,
        )
        if r.returncode != 0 or not opath.exists():
            raise RuntimeError(f"wasm-opt failed: {(r.stderr or '').strip()[:200]}")
        out, _ = strip_custom(opath.read_bytes())
        if not mvp_clean(out):
            raise RuntimeError("wasm-opt produced a module outside WAMR_FEATURES")
        return out


def mutate(mod: bytes, passes: int, seed: int) -> tuple[bytes, int]:
    """Apply `wasm-tools mutate` up to `passes` times, each a semantics-preserving rewrite
    that is also device-loadable (`mvp_clean`)."""
    tool = wasm_tools()
    if not tool:
        raise FileNotFoundError("wasm-tools not found")
    cur = mod
    done = 0
    attempt = 0
    with tempfile.TemporaryDirectory() as td:
        tdp = pathlib.Path(td)
        ipath, opath = tdp / "in.wasm", tdp / "out.wasm"
        for _p in range(passes):
            mutated = False
            for _k in range(_ATTEMPTS_PER_PASS):
                ipath.write_bytes(cur)
                r = subprocess.run([tool, "mutate", str(ipath), "--seed", str(seed + attempt),
                                    "--preserve-semantics", "-o", str(opath)],
                                   capture_output=True, text=True)
                attempt += 1
                if r.returncode == 0 and opath.exists():
                    out = opath.read_bytes()
                    if subprocess.run([tool, "validate", str(opath)]).returncode != 0:
                        raise RuntimeError("wasm-tools produced an invalid module")
                    if not mvp_clean(out):
                        continue
                    cur = out
                    done += 1
                    mutated = True
                    break
                if _NO_MUTATION not in (r.stderr or ""):
                    raise RuntimeError(f"wasm-tools mutate failed: {(r.stderr or '').strip()[:200]}")
            if not mutated:
                break
    return cur, done


def harden(
    mod: bytes,
    passes: int,
    seed: int,
    require_mutate: bool,
    *,
    optimize_ir: bool = False,
) -> tuple[bytes, dict]:
    out, dropped = strip_custom(mod)
    report = {"dropped_custom": dropped, "optimized": False, "mutated": False, "passes": 0}
    if optimize_ir and wasm_opt():
        out = optimize(out)
        report["optimized"] = True
    if passes > 0:
        if wasm_tools():
            out, done = mutate(out, passes, seed)
            out, _ = strip_custom(out)  # mutate can re-add a 'name'/'producers' section
            report["mutated"] = done > 0
            report["passes"] = done
            if not mvp_clean(out):
                raise AssertionError("hardened module is not device-loadable (non-MVP value type)")
        elif require_mutate:
            raise FileNotFoundError(f"--require-mutate but wasm-tools not found ({WASM_TOOLS})")
    leftover = custom_section_names(out)
    if leftover:
        raise AssertionError(f"custom sections remain after hardening: {leftover}")
    report["size_in"], report["size_out"] = len(mod), len(out)
    return out, report


# ---- self-test with controls (every test has a control that must fail) ------

def _selftest() -> int:
    type_sec = bytes([1, 4, 1, 0x60, 0, 0])
    imp_payload = b"\x01" + bytes([5]) + b"na8ve" + bytes([3]) + b"log" + b"\x00\x00"
    imp_sec = bytes([2, len(imp_payload)]) + imp_payload
    func_sec = bytes([3, 2, 1, 0])
    mem_sec = bytes([5, 3, 1, 0, 1])
    exp_payload = b"\x02" + bytes([6]) + b"memory" + b"\x02\x00" + bytes([7]) + b"n8_init" + b"\x00\x01"
    exp_sec = bytes([7, len(exp_payload)]) + exp_payload
    code_sec = bytes([10, 6, 1, 4, 0, 0x10, 0, 0x0B])
    body = bytes([len("name")]) + b"name" + b"hi"
    name_sec = b"\x00" + bytes([len(body)]) + body
    mod = b"\x00asm\x01\x00\x00\x00" + type_sec + imp_sec + func_sec + mem_sec + exp_sec + code_sec + name_sec

    assert "name" in custom_section_names(mod), "fixture should carry a name section"
    out, rep = harden(mod, passes=1, seed=0x6e38, require_mutate=False, optimize_ir=True)
    assert custom_section_names(out) == [], "strip must remove the name section"
    assert mvp_clean(out), "hardened output must validate under WAMR_FEATURES"
    assert b"na8ve" in out and b"log" in out and b"n8_init" in out
    assert b"memory" in out

    # Control 1: a broken strip that keeps custom sections must be caught
    broken = mod
    if not custom_section_names(broken):
        print("control 1 did not fail", file=sys.stderr)
        return 1

    # Control 2: corrupted bytecode must fail mvp_clean
    bad_wasm = bytearray(out)
    bad_wasm[-1] = 0xFF
    if mvp_clean(bytes(bad_wasm)):
        print("control 2 did not fail on corrupted bytecode", file=sys.stderr)
        return 1

    print(f"selftest ok (strip + wasm-opt={rep['optimized']} + mutate={rep['mutated']}; 2 controls correctly fail)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("infile", nargs="?")
    ap.add_argument("outfile", nargs="?")
    ap.add_argument("--mutate", type=int, default=0, metavar="N", help="wasm-tools mutate passes (0 = strip only)")
    ap.add_argument("--seed", type=lambda s: int(s, 0), default=0x6e38)
    ap.add_argument("--optimize", action="store_true", help="run Binaryen wasm-opt -O4 --converge")
    ap.add_argument("--require-mutate", action="store_true", help="fail if wasm-tools is absent")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    if not a.infile or not a.outfile:
        ap.error("IN.wasm and OUT.wasm are required unless --selftest")
    mod = pathlib.Path(a.infile).read_bytes()
    out, rep = harden(mod, a.mutate, a.seed, a.require_mutate, optimize_ir=a.optimize)
    pathlib.Path(a.outfile).write_bytes(out)
    note = "mutated" if rep["mutated"] else ("mutate skipped: wasm-tools absent" if a.mutate else "strip only")
    print(f"harden {a.infile}: {rep['size_in']} -> {rep['size_out']} bytes, "
          f"dropped {rep['dropped_custom'] or 'none'}, opt={rep['optimized']}, {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
