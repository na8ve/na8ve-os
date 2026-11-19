#!/usr/bin/env python3
"""Build and package an application for na8ve-os.

Compiles freestanding C application code into WebAssembly (wasm32-freestanding),
links against the na8ve-os Micro-Libc runtime, and optionally signs the binary
into an .n8pv container ready for deployment.

Usage:
    python tools/build_app.py --name my_app --src app.c --out dist/
    python tools/build_app.py --name my_app --src app.c --out dist/ --key path/to/app.pem
"""
import argparse
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SDK_INC = ROOT / "sdk" / "include"
SDK_SRC = ROOT / "sdk" / "src"

ZIG_DEFAULT = os.environ.get("CX_ZIG", "C:/Espressif/tools/ziglang/ziglang/zig.exe")


def find_compiler():
    if pathlib.Path(ZIG_DEFAULT).exists():
        return [ZIG_DEFAULT, "cc"], [ZIG_DEFAULT, "wasm-ld"]
    zig_path = shutil.which("zig")
    if zig_path:
        return [zig_path, "cc"], [zig_path, "wasm-ld"]
    clang_path = shutil.which("clang")
    wasm_ld_path = shutil.which("wasm-ld")
    if clang_path and wasm_ld_path:
        return [clang_path], [wasm_ld_path]
    return None, None


def main() -> int:
    ap = argparse.ArgumentParser(description="Compile and package a na8ve-os application.")
    ap.add_argument("--name", required=True, help="Application name (1-16 characters)")
    ap.add_argument("--src", nargs="+", required=True, help="Application source C files")
    ap.add_argument("--out", required=True, help="Output directory")
    ap.add_argument("--key", default="", help="Optional path to PEM signing key")
    ap.add_argument("--max-memory", type=int, default=65536, help="Linear memory ceiling in bytes (multiple of 64KB)")
    ap.add_argument("--stack", type=int, default=8192, help="Stack size in bytes (default 8192)")
    ap.add_argument("--model-client", action="store_true", help="Link the async model broker client")
    ap.add_argument("--debug", action="store_true", help="Keep debug symbols")

    args = ap.parse_args()

    cc, ld = find_compiler()
    if not cc:
        sys.exit("Error: No suitable WebAssembly C compiler found. Install zig 0.13.0 or clang/llvm.")

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    obj_dir = out_dir / "obj" / args.name
    obj_dir.mkdir(parents=True, exist_ok=True)

    cflags = [
        "-target", "wasm32-freestanding",
        "-mcpu=mvp", "-mbulk-memory", "-msign-ext",
        "-O2", "-std=c11", "-ffreestanding",
        "-fno-builtin-printf", "-Wall",
        "-Werror=implicit-function-declaration",
        "-I", str(SDK_INC),
        "-I", str(SDK_INC / "libc"),
    ]
    if args.debug:
        cflags.append("-g")
    else:
        cflags.append("-g0")

    common_srcs = [
        SDK_SRC / "n8_libc.c",
        SDK_SRC / "n8_util.c",
        SDK_SRC / "n8_stdio.c",
    ]
    if args.model_client:
        common_srcs.append(SDK_SRC / "n8_model.c")

    all_srcs = [pathlib.Path(s) for s in args.src] + common_srcs
    objs = []

    for src_file in all_srcs:
        obj_file = obj_dir / f"{src_file.stem}.o"
        cmd = [*cc, *cflags, "-c", str(src_file), "-o", str(obj_file)]
        res = subprocess.call(cmd)
        if res != 0:
            sys.exit(f"Compilation failed for {src_file}")
        objs.append(str(obj_file))

    wasm_out = out_dir / f"{args.name}.wasm"
    init_mem = min(args.max_memory, 131072) if args.max_memory > 65536 else args.max_memory

    ld_flags = [
        "--no-entry",
        "--stack-first",
        "-z", f"stack-size={args.stack}",
        f"--initial-memory={init_mem}",
        f"--max-memory={args.max_memory}",
        "--export=n8_init",
        "--export=n8_inbox",
        "--export=n8_on_message",
        f"--allow-undefined-file={SDK_SRC / 'n8_imports.txt'}",
        "-o", str(wasm_out),
        *objs
    ]
    if not args.debug:
        ld_flags.append("--strip-all")

    res = subprocess.call([*ld, *ld_flags])
    if res != 0:
        sys.exit(f"Linking failed for {wasm_out}")

    wasm_opt = shutil.which("wasm-opt")
    if wasm_opt and not args.debug:
        opt_cmd = [wasm_opt, "-O4", "--enable-bulk-memory", "--strip-debug", "--strip-producers", str(wasm_out), "-o", str(wasm_out)]
        subprocess.call(opt_cmd)

    module_bytes = wasm_out.read_bytes()
    digest = hashlib.sha256(module_bytes).hexdigest()
    print(f"Built {wasm_out} ({len(module_bytes)} bytes, SHA-256: {digest})")

    if args.key:
        sys.path.insert(0, str(ROOT / "tools"))
        import sign_app
        key = sign_app.load_key(args.key)
        signed_payload = sign_app.sign_bytes(key, module_bytes, args.name)
        n8pv_out = out_dir / f"{args.name}.n8pv"
        n8pv_out.write_bytes(signed_payload)
        print(f"Signed {n8pv_out} ({len(signed_payload)} bytes)")

    return 0


if __name__ == "__main__":
    sys.exit(main())

