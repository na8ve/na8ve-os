#!/usr/bin/env python3
"""Device certificate formatting helper for na8ve-os Arduino IDE pairing."""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import struct
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sign_pvm  # noqa: E402

MAGIC, VERSION, SIZE, SIGNED, SIG = b"N8LC", 1, 1024, 76, 384
FLAG_PAID = 1


def parse_mac(s: str) -> bytes:
    b = bytes.fromhex(s.replace(":", "").replace("-", ""))
    if len(b) != 6:
        raise ValueError(f"MAC {s!r}: six bytes")
    return b


def body(name: str, seq: int, mac: bytes, ref: str, paid: bool = True, issued: int | None = None) -> bytes:
    nm = name.encode("ascii")
    if not 0 < len(nm) <= 16 or len(mac) != 6:
        raise ValueError("a name of 1-16 characters and a six-byte MAC")
    b = MAGIC + struct.pack("<I", VERSION) + nm.ljust(16, b"\0") + struct.pack("<I", seq) + mac + \
        struct.pack("<HQ", FLAG_PAID if paid else 0, int(time.time()) if issued is None else issued) + \
        hashlib.sha256(ref.encode("utf-8")).digest()
    assert len(b) == SIGNED
    return b


def mint(key, name: str, seq: int, mac: bytes, ref: str, paid: bool = True, issued: int | None = None) -> bytes:
    hashes, _, padding, _, utils = sign_pvm._crypto()
    b = body(name, seq, mac, ref, paid, issued)
    sig = key.sign(hashlib.sha256(b).digest(), padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
                   utils.Prehashed(hashes.SHA256()))
    out = b + sig + b"\0" * (SIZE - SIGNED - SIG)
    assert len(out) == SIZE
    return out


def verify(pub: bytes, lic: bytes, name: str, seq: int, mac: bytes) -> str:
    """'' when the certificate is valid for this app, sequence, and board MAC; otherwise the reason it failed."""
    hashes, _, padding, rsa, utils = sign_pvm._crypto()
    if len(lic) != SIZE or lic[:4] != MAGIC or struct.unpack_from("<I", lic, 4)[0] != VERSION:
        return "format"
    key = rsa.RSAPublicNumbers(struct.unpack_from("<I", pub, SIG)[0], int.from_bytes(pub[:SIG], "big")).public_key()
    try:
        key.verify(lic[SIGNED:SIGNED + SIG], hashlib.sha256(lic[:SIGNED]).digest(),
                   padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), utils.Prehashed(hashes.SHA256()))
    except Exception:  # noqa: BLE001  cryptography's InvalidSignature
        return "signature"
    if lic[8:24].rstrip(b"\0") != name.encode("ascii"):
        return "name"
    if struct.unpack_from("<I", lic, 24)[0] != seq:
        return "seq"
    if lic[28:34] != mac:
        return "mac"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mint")
    m.add_argument("--key", required=True)
    m.add_argument("--name", required=True)
    m.add_argument("--seq", type=int, required=True)
    m.add_argument("--mac", required=True)
    m.add_argument("--ref", required=True)
    m.add_argument("--out", required=True)
    p = sub.add_parser("pubkey")
    p.add_argument("--key", required=True)
    p.add_argument("--out", required=True)
    a = ap.parse_args()
    key = sign_pvm.load_key(a.key)
    if a.cmd == "pubkey":
        pathlib.Path(a.out).write_bytes(sign_pvm.pubkey_bytes(key))
        return 0
    pathlib.Path(a.out).write_bytes(mint(key, a.name, a.seq, parse_mac(a.mac), a.ref))
    return 0


if __name__ == "__main__":
    sys.exit(main())
