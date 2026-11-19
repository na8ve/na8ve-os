#!/usr/bin/env python3
"""
tools/na8ve_applab_tool.py

Developer CLI for Arduino App Lab applications on na8ve-os (Arduino Uno Q).
Manages the developer RSA-3072 signing key, compiles freestanding C sandbox modules (pvm/*.c)
with Zig into stripped WebAssembly with hashed host imports, signs 436-byte N8PV containers +
76-byte N8MF manifests, checks the package, and builds <app>-applab.zip.

Contains no models, no device keys, and no enclave source internals.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_KEY_PATH = Path(os.environ.get("NA8VE_APP_KEY", str(Path.home() / ".na8ve" / "app-key.pem")))

N8PV_MAGIC = b"N8PV"
N8MF_MAGIC = b"N8MF"

N8PV_FLAG_RELEASE = 0x0001
N8PV_FLAG_SIGNED = 0x0002
N8PV_FLAG_BUYER_PSS = 0x0004

CX_CAP_ACCEL = 0x01
CX_CAP_STORE = 0x02
CX_CAP_CHAT = 0x04
CX_CAP_ACT = 0x08

# The App Lab ABI's host import names for the functions n8_sdk.h declares
N8_SYM_MAP: Dict[bytes, bytes] = {
    b"n8_log": b"e3b0c442",
    b"n8_flash_read": b"7f83b165",
    b"n8_store_query": b"4a9d8c11",
    b"n8_ipc_send": b"91c2b804",
    b"n8_reply": b"3d77a9e1",
    b"n8_chat_new": b"6d10f893",
    b"n8_chat_turn": b"b45e2319",
    b"n8_chat_board": b"09c7a4f8",
    b"n8_tool": b"d381e62a",
    b"n8_session": b"27f9b05c",
    b"n8_yield": b"a63c48d1",
    b"n8_vision_once": b"54e2917b",
}

FORBIDDEN_ZIP_EXTENSIONS = {
    ".c", ".h", ".cc", ".cpp", ".hpp", ".o", ".obj", ".a", ".so",
    ".wasm", ".map", ".n8vm", ".n8lc", ".pem", ".key", ".der",
}


def _crypto():
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding, rsa, utils
        return hashes, serialization, padding, rsa, utils
    except ImportError as exc:
        raise RuntimeError("Missing dependency 'cryptography'. Install with: pip install cryptography") from exc


def _read_leb128_u32(data: bytes, offset: int) -> Tuple[int, int]:
    result = 0
    shift = 0
    pos = offset
    while pos < len(data):
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if (b & 0x80) == 0:
            return result, pos
        shift += 7
    raise ValueError("Truncated LEB128 integer in WebAssembly binary")


def _write_leb128_u32(val: int) -> bytes:
    out = bytearray()
    while True:
        b = val & 0x7F
        val >>= 7
        if val != 0:
            b |= 0x80
        out.append(b)
        if val == 0:
            break
    return bytes(out)


def _find_zig() -> Optional[str]:
    for env_name in ("NA8VE_ZIG", "CX_ZIG"):
        cand = os.environ.get(env_name)
        if cand and Path(cand).is_file():
            return cand
    which_zig = shutil.which("zig")
    if which_zig:
        return which_zig
    for path in (
        Path("C:/Espressif/tools/ziglang/ziglang/zig.exe"),
        Path("/usr/local/bin/zig"),
        Path("/usr/bin/zig"),
    ):
        if path.is_file():
            return str(path)
    return None


def _ensure_key_outside_app(key_path: Path, app_dir: Optional[Path] = None) -> Path:
    resolved = key_path.expanduser().resolve()
    sdk_root = Path(__file__).resolve().parent.parent
    roots = [sdk_root]
    if app_dir is not None:
        roots.append(app_dir.resolve())
    for root in roots:
        if resolved == root or root in resolved.parents:
            raise ValueError(
                f"Refusing key path '{resolved}' inside SDK/app directory '{root}'. Use ~/.na8ve/app-key.pem."
            )
    return resolved


def cmd_keygen(key_path: Path, out_pub: Optional[Path]) -> int:
    _, serialization, _, rsa, _ = _crypto()
    resolved = _ensure_key_outside_app(key_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    if resolved.exists():
        print(f"Key already exists at {resolved} (leaving untouched)")
    else:
        priv = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        pem = priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        resolved.write_bytes(pem)
        try:
            os.chmod(resolved, 0o600)
        except OSError:
            pass
        print(f"Generated RSA-3072 signing key: {resolved}")

    pub_out = out_pub.expanduser().resolve() if out_pub else resolved.with_suffix(".pub.bin")
    return cmd_pubkey(resolved, pub_out)


def cmd_pubkey(key_path: Path, out_pub: Optional[Path]) -> int:
    _, serialization, _, _, _ = _crypto()
    resolved = key_path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Signing key not found: {resolved}. Run 'keygen' first.")
    priv = serialization.load_pem_private_key(resolved.read_bytes(), password=None)
    nums = priv.public_key().public_numbers()
    if nums.n.bit_length() != 3072 or nums.e != 65537:
        raise ValueError("Expected an RSA-3072 key with e=65537")
    mod_be = nums.n.to_bytes(384, "big")
    pub_blob = mod_be + struct.pack("<I", nums.e)
    if out_pub is not None:
        out_p = out_pub.expanduser().resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_bytes(pub_blob)
        print(f"Wrote 388-byte public key to {out_p}")
    sha = hashlib.sha256(mod_be).hexdigest()
    b64 = base64.b64encode(mod_be).decode("ascii")
    print(f"pub_sha256: {sha}")
    print(f"dev_pubkey_b64: {b64}")
    return 0


def strip_custom_sections_and_map_imports(wasm_bytes: bytes) -> bytes:
    if len(wasm_bytes) < 8 or wasm_bytes[:8] != b"\x00asm\x01\x00\x00\x00":
        raise ValueError("Invalid WebAssembly binary header")
    out = bytearray(wasm_bytes[:8])
    pos = 8
    n = len(wasm_bytes)
    while pos < n:
        sec_id = wasm_bytes[pos]
        pos += 1
        sec_len, payload_start = _read_leb128_u32(wasm_bytes, pos)
        payload_end = payload_start + sec_len
        if payload_end > n:
            raise ValueError("Truncated WebAssembly section")
        payload = wasm_bytes[payload_start:payload_end]
        pos = payload_end
        if sec_id == 0:
            continue
        if sec_id == 2:
            for sdk_name, abi_name in N8_SYM_MAP.items():
                payload = payload.replace(bytes([len(sdk_name)]) + sdk_name, bytes([len(abi_name)]) + abi_name)
        out.append(sec_id)
        out.extend(_write_leb128_u32(len(payload)))
        out.extend(payload)
    return bytes(out)


def compile_pvm_c_sources(c_files: List[Path]) -> bytes:
    if not c_files:
        raise FileNotFoundError("No pvm/*.c source files found to compile")
    zig_bin = _find_zig()
    if not zig_bin:
        raise RuntimeError("Zig toolchain not found (install Zig 0.13.x or set NA8VE_ZIG)")
    with tempfile.TemporaryDirectory() as tmpd:
        out_wasm = Path(tmpd) / "raw.wasm"
        cmd = [
            zig_bin, "cc",
            "-target", "wasm32-freestanding",
            "-O2", "-nostdlib",
            "-Wl,--no-entry",
            "-Wl,--export=pvm_main",
            # a sandbox's stack lives in its own linear memory: Zig's default (1 MiB) would make the
            # module ask for 17 pages, beyond what its manifest grants
            "-Wl,-z,stack-size=16384",
            "-s",
            "-o", str(out_wasm),
        ] + [str(f) for f in c_files]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0 or not out_wasm.exists():
            raise RuntimeError(f"C sandbox compilation failed:\n{res.stderr or res.stdout}")
        return strip_custom_sections_and_map_imports(out_wasm.read_bytes())


def pack_n8pv_and_manifest(
    wasm_bytes: bytes,
    manifest_cfg: Dict[str, object],
    key_path: Optional[Path] = None,
) -> Tuple[bytes, bytes, str]:
    # A board admits an app signed by a developer key its licence delegates (or by the store), so every
    # app is signed: there is no unsigned or tag-only mode
    if key_path is None:
        raise ValueError("a developer signing key is required (keygen, then register its public key with the board's licence)")
    wasm_sha = hashlib.sha256(wasm_bytes).digest()
    flags = N8PV_FLAG_RELEASE | N8PV_FLAG_SIGNED | N8PV_FLAG_BUYER_PSS
    hdr48 = struct.pack("<4sIII32s", N8PV_MAGIC, 1, flags, len(wasm_bytes), wasm_sha)

    name_bytes = str(manifest_cfg.get("name", "applab-pvm"))[:15].encode("utf-8").ljust(16, b"\x00")
    dom_id = int(manifest_cfg.get("dom_id", 2))
    budget_ms = int(manifest_cfg.get("budget_ms", 50))
    mem_bytes = int(manifest_cfg.get("mem_bytes", 65536))
    grants_mask = 0
    for grant in manifest_cfg.get("grants", ["store", "act"]):
        g = str(grant)
        if g == "accel":
            grants_mask |= CX_CAP_ACCEL
        elif g == "store":
            grants_mask |= CX_CAP_STORE
        elif g == "chat":
            grants_mask |= CX_CAP_CHAT
        elif g == "act":
            grants_mask |= CX_CAP_ACT
    allowed_ipc = 0
    for target_dom in manifest_cfg.get("allowed_ipc", [1]):
        td = int(target_dom)
        if 0 <= td < 32:
            allowed_ipc |= 1 << td
    if grants_mask & (CX_CAP_ACCEL | CX_CAP_CHAT):
        raise ValueError("N8MF CapDL error: 'accel' and 'chat' grants are exclusive to core system domains")

    n8mf_blob = struct.pack(
        "<4sI16sIIIII32s",
        N8MF_MAGIC,
        1,
        name_bytes,
        dom_id,
        budget_ms,
        grants_mask,
        allowed_ipc,
        mem_bytes,
        wasm_sha,
    )
    # The signature covers the header and the manifest, so neither the code nor its grants, IPC
    # targets, budget or memory can be changed after signing
    hashes, serialization, padding, _, utils = _crypto()
    priv = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    if getattr(priv, "key_size", 0) != 3072:
        raise ValueError(f"Expected RSA-3072 key at {key_path}")
    sig384 = priv.sign(
        hashlib.sha256(hdr48 + n8mf_blob).digest(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
        utils.Prehashed(hashes.SHA256()),
    )
    if len(sig384) != 384:
        raise ValueError("Unexpected RSA-3072 signature size")
    n8pv_blob = hdr48 + struct.pack("<I", 384) + sig384 + wasm_bytes
    return n8pv_blob, n8mf_blob, wasm_sha.hex()


def verify_n8pv_bytes(raw: bytes, filename: str) -> bytes:
    if len(raw) < 444 or raw[:4] != N8PV_MAGIC:
        raise ValueError(f"Package check: '{filename}' missing valid N8PV header")
    _, _, _, wasm_len, hdr_sha, sig_len = struct.unpack("<4sIII32sI", raw[:52])
    if sig_len != 384 or 436 + wasm_len != len(raw):
        raise ValueError(f"Package check: '{filename}' header length mismatch")
    wasm_part = raw[436:]
    if hashlib.sha256(wasm_part).digest() != hdr_sha:
        raise ValueError(f"Package check: '{filename}' Wasm SHA-256 mismatch")
    if len(wasm_part) < 8 or wasm_part[:8] != b"\x00asm\x01\x00\x00\x00":
        raise ValueError(f"Package check: '{filename}' invalid Wasm header")
    pos = 8
    while pos < len(wasm_part):
        sec_id = wasm_part[pos]
        pos += 1
        sec_len, pos = _read_leb128_u32(wasm_part, pos)
        sec_end = pos + sec_len
        if sec_end > len(wasm_part):
            raise ValueError(f"Package check: truncated Wasm section in '{filename}'")
        sec_payload = wasm_part[pos:sec_end]
        pos = sec_end
        if sec_id == 0:
            raise ValueError(f"Package check: unstripped custom section in '{filename}'")
        if sec_id == 2 and re.search(rb"n8_[a-z]", sec_payload):
            raise ValueError(f"Package check: an import in '{filename}' is not mapped to the App Lab ABI")
    return hdr_sha


def verify_package(stage_dir: Path) -> None:
    """An App Lab package carries its compiled, signed module and its manifest, never sources."""
    n8pv_sha: Optional[bytes] = None
    n8mf_sha: Optional[bytes] = None

    for p in sorted(stage_dir.rglob("*")):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext in FORBIDDEN_ZIP_EXTENSIONS:
            raise ValueError(f"Package check: forbidden file '{p.name}' ({ext}) in package")
        raw = p.read_bytes()
        if ext == ".n8pv":
            n8pv_sha = verify_n8pv_bytes(raw, p.name)
        elif p.name == "manifest.bin":
            if len(raw) < 76 or raw[:4] != N8MF_MAGIC:
                raise ValueError("Package check: invalid N8MF manifest.bin")
            n8mf_sha = raw[44:76]
        else:
            try:
                txt = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if p.name == "app.yaml" and "NA8VE_SACCADE_CROPS" in txt:
                raise ValueError("Configuration error in app.yaml: use NA8VE_SACCADE_COUNT instead of NA8VE_SACCADE_CROPS")

    if n8pv_sha is not None or n8mf_sha is not None:
        if n8pv_sha is None or n8mf_sha is None or n8pv_sha != n8mf_sha:
            raise ValueError("Package check: pvm/app.n8pv and pvm/manifest.bin digest mismatch")


def build_pvm_only(app_dir: Path, key_path: Optional[Path] = None) -> Dict[str, object]:
    app_dir = app_dir.resolve()
    pvm_dir = app_dir / "pvm"
    if key_path is not None:
        key_path = _ensure_key_outside_app(key_path, app_dir)
        if not key_path.exists():
            raise FileNotFoundError(f"Signing key not found: {key_path}")
    c_files = sorted(pvm_dir.glob("*.c"))
    mf_json = pvm_dir / "manifest.json"
    mf_cfg: Dict[str, object] = {"name": app_dir.name[:15], "grants": ["store", "act"], "allowed_ipc": [1]}
    if mf_json.exists():
        mf_cfg = json.loads(mf_json.read_text(encoding="utf-8"))

    wasm_bytes = compile_pvm_c_sources(c_files)
    n8pv_blob, n8mf_blob, sha_hex = pack_n8pv_and_manifest(wasm_bytes, mf_cfg, key_path=key_path)
    (pvm_dir / "app.n8pv").write_bytes(n8pv_blob)
    (pvm_dir / "manifest.bin").write_bytes(n8mf_blob)
    return {
        "app": app_dir.name,
        "pvm_path": str(pvm_dir / "app.n8pv"),
        "manifest_path": str(pvm_dir / "manifest.bin"),
        "n8pv_bytes": len(n8pv_blob),
        "manifest_bytes": len(n8mf_blob),
        "pvm_sha256": sha_hex,
        "signed_mode": "developer-rsa3072-pss",
    }


def pack_applab_zip(
    app_dir: Path,
    out_zip: Path,
    key_path: Optional[Path] = None,
    sync_pvm: bool = True,
    keep_sources_for_control: bool = False,
) -> Dict[str, object]:
    app_dir = app_dir.resolve()
    if not (app_dir / "app.yaml").exists():
        raise FileNotFoundError(f"Missing app.yaml in {app_dir}")
    if key_path is not None:
        key_path = _ensure_key_outside_app(key_path, app_dir)
        if not key_path.exists():
            raise FileNotFoundError(f"Signing key not found: {key_path}")

    with tempfile.TemporaryDirectory() as tmpd:
        stage = Path(tmpd) / app_dir.name
        shutil.copytree(app_dir, stage)
        # an app without its own page gets the SDK's dashboard (the starter's assets/), which reads the
        # app's name and data from the app itself
        sdk_assets = Path(__file__).resolve().parent.parent / "na8ve-developer-sdk" / "assets"
        if not (stage / "assets" / "index.html").exists() and sdk_assets.is_dir():
            shutil.copytree(sdk_assets, stage / "assets", dirs_exist_ok=True)
        pvm_dir = stage / "pvm"
        sha_hex = ""
        if pvm_dir.exists():
            c_files = sorted(pvm_dir.glob("*.c"))
            mf_json = pvm_dir / "manifest.json"
            mf_cfg: Dict[str, object] = {"name": app_dir.name[:15], "grants": ["store", "act"], "allowed_ipc": [1]}
            if mf_json.exists():
                mf_cfg = json.loads(mf_json.read_text(encoding="utf-8"))
            if c_files:
                wasm_bytes = compile_pvm_c_sources(c_files)
                n8pv_blob, n8mf_blob, sha_hex = pack_n8pv_and_manifest(wasm_bytes, mf_cfg, key_path=key_path)
                (pvm_dir / "app.n8pv").write_bytes(n8pv_blob)
                (pvm_dir / "manifest.bin").write_bytes(n8mf_blob)
                if sync_pvm:
                    (app_dir / "pvm" / "app.n8pv").write_bytes(n8pv_blob)
                    (app_dir / "pvm" / "manifest.bin").write_bytes(n8mf_blob)
            if not keep_sources_for_control:
                for ext_pat in ("*.c", "*.h", "*.wasm"):
                    for f in pvm_dir.glob(ext_pat):
                        f.unlink()
                if mf_json.exists():
                    mf_json.unlink()

        verify_package(stage)

        out_zip = out_zip.resolve()
        out_zip.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for fp in sorted(stage.rglob("*")):
                if fp.is_file():
                    zf.write(fp, arcname=fp.relative_to(stage).as_posix())

    return {
        "app": app_dir.name,
        "zip_path": str(out_zip),
        "zip_bytes": out_zip.stat().st_size,
        "pvm_sha256": sha_hex,
        "signed_mode": "developer-rsa3072-pss",
    }


def cmd_verify_zip(zip_path: Path) -> int:
    zip_path = zip_path.resolve()
    if not zip_path.exists():
        raise FileNotFoundError(f"Archive not found: {zip_path}")
    with tempfile.TemporaryDirectory() as tmpd:
        extract_dir = Path(tmpd) / "unzipped"
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)
            names = sorted(zf.namelist())
        verify_package(extract_dir)
    print(json.dumps({"zip_path": str(zip_path), "files": len(names), "package_check": "PASS"}, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="na8ve-os Arduino App Lab SDK tool")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_kg = sub.add_parser("keygen", help="Generate buyer RSA-3072 signing key outside the app directory")
    p_kg.add_argument("--key", type=Path, default=DEFAULT_KEY_PATH)
    p_kg.add_argument("--out-pub", type=Path, default=None)

    p_pk = sub.add_parser("pubkey", help="Export 388-byte public key + base64 modulus for pairing")
    p_pk.add_argument("--key", type=Path, default=DEFAULT_KEY_PATH)
    p_pk.add_argument("--out", type=Path, default=None)

    p_bd = sub.add_parser("build", help="Compile pvm/*.c into pvm/app.n8pv + pvm/manifest.bin")
    p_bd.add_argument("--app-dir", type=Path, required=True)
    p_bd.add_argument("--key", type=Path, default=DEFAULT_KEY_PATH, help="Your RSA-3072 developer key (default: ~/.na8ve/app-key.pem)")

    p_pkz = sub.add_parser("pack", help="Compile, sign, leave sources out, check the package, and build .zip")
    p_pkz.add_argument("--app-dir", type=Path, required=True)
    p_pkz.add_argument("--out", type=Path, required=True)
    p_pkz.add_argument("--key", type=Path, default=DEFAULT_KEY_PATH, help="Your RSA-3072 developer key (default: ~/.na8ve/app-key.pem)")
    p_pkz.add_argument("--no-sync-pvm", action="store_true")
    p_pkz.add_argument("--keep-sources-for-control", action="store_true", help="Negative control: test gate failure")

    p_vz = sub.add_parser("verify-zip", help="Check an App Lab .zip archive")
    p_vz.add_argument("zip_path", type=Path)

    args = ap.parse_args()
    if args.cmd == "keygen":
        return cmd_keygen(args.key, args.out_pub)
    if args.cmd == "pubkey":
        return cmd_pubkey(args.key, args.out)
    if args.cmd == "build":
        print(json.dumps(build_pvm_only(args.app_dir, key_path=args.key), indent=2))
        return 0
    if args.cmd == "pack":
        info = pack_applab_zip(
            args.app_dir,
            args.out,
            key_path=args.key,
            sync_pvm=not args.no_sync_pvm,
            keep_sources_for_control=args.keep_sources_for_control,
        )
        print(json.dumps(info, indent=2))
        return 0
    if args.cmd == "verify-zip":
        return cmd_verify_zip(args.zip_path)
    return 1


if __name__ == "__main__":
    sys.exit(main())

