#!/usr/bin/env python3
"""Sign a pVM payload container for na8ve-os (`docs/sdk-guide/05-compilation-signing-and-packaging-toolchain.md`).

    python tools/sign_app.py keygen [--key PATH]                 an RSA-3072 app key, off the repository
    python tools/sign_app.py pubkey [--key PATH] --out PUB.bin   the public half, for the OS image
    python tools/sign_app.py sign [--key PATH] --name NAME IN.wasm OUT.n8pv

The private key is read from an operator keystore path (`--key`, `NA8VE_APP_KEY`, or default
`~/.na8ve/app-key.pem`), never from inside the repository: `keygen` and `sign` refuse a key path
inside the repository. The payload is a 64-byte header (`N8PV`, version 1, header length 64,
module length, signature length 384, name, the module's SHA-256), the module, then an RSASSA-PSS
signature (SHA-256, MGF1-SHA-256, 32-byte salt) over the module's SHA-256."""
import argparse
import hashlib
import os
import pathlib
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_KEY = (
    os.environ.get("NA8VE_APP_KEY")
    or os.environ.get("CX_OS_APP_KEY")
    or str(pathlib.Path.home() / ".na8ve" / "app-key.pem")
)
MAGIC, VERSION, HEADER, SIG = b"N8PV", 1, 64, 384


def _crypto():
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa, utils
    return hashes, serialization, padding, rsa, utils


def outside_repo(path: pathlib.Path) -> pathlib.Path:
    p = path.resolve()
    if p == ROOT or ROOT in p.parents:
        sys.exit(f"{p}: a private key is never kept in the repository (07); use an operator keystore path")
    return p


def load_key(path: str):
    _, serialization, _, _, _ = _crypto()
    p = outside_repo(pathlib.Path(path))
    if not p.exists():
        sys.exit(f"{p}: no key; `python tools/sign_pvm.py keygen --key {p}` makes one")
    return serialization.load_pem_private_key(p.read_bytes(), password=None)


def pubkey_bytes(key) -> bytes:
    """The modulus big-endian (384 bytes) and the exponent little-endian (4)."""
    nums = key.public_key().public_numbers()
    if nums.n.bit_length() != 3072:
        sys.exit("the key is not RSA-3072")
    return nums.n.to_bytes(SIG, "big") + struct.pack("<I", nums.e)


def sign_bytes(key, module: bytes, name: str) -> bytes:
    hashes, _, padding, _, utils = _crypto()
    digest = hashlib.sha256(module).digest()
    sig = key.sign(digest, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
                   utils.Prehashed(hashes.SHA256()))
    if len(sig) != SIG:
        sys.exit("signature is not 384 bytes")
    nm = name.encode("ascii")
    if not 0 < len(nm) <= 16:
        sys.exit(f"name {name!r}: 1 to 16 characters")
    header = MAGIC + struct.pack("<HHII", VERSION, HEADER, len(module), SIG) + nm.ljust(16, b"\0") + digest
    assert len(header) == HEADER
    return header + module + sig


def read_payload(data: bytes) -> tuple[bytes, bytes, str]:
    """(module, signature, name) from an .n8pv file, its header checked."""
    if len(data) < HEADER or data[:4] != MAGIC:
        raise ValueError("not an .n8pv payload")
    version, hlen, mlen, slen = struct.unpack_from("<HHII", data, 4)
    if version != VERSION or hlen != HEADER or slen != SIG or len(data) != HEADER + mlen + SIG:
        raise ValueError("an .n8pv payload's header does not match its length")
    module = data[HEADER:HEADER + mlen]
    if hashlib.sha256(module).digest() != data[32:64]:
        raise ValueError("an .n8pv payload's digest is not its module's")
    return module, data[HEADER + mlen:], data[16:32].rstrip(b"\0").decode("ascii")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("keygen")
    p.add_argument("--key", default=DEFAULT_KEY)
    p = sub.add_parser("pubkey")
    p.add_argument("--key", default=DEFAULT_KEY)
    p.add_argument("--out", required=True)
    p = sub.add_parser("sign")
    p.add_argument("--key", default=DEFAULT_KEY)
    p.add_argument("--name", required=True)
    p.add_argument("module")
    p.add_argument("out")
    a = ap.parse_args()
    if a.cmd == "keygen":
        _, serialization, _, rsa, _ = _crypto()
        p = outside_repo(pathlib.Path(a.key))
        if p.exists():
            sys.exit(f"{p} exists; a key is never overwritten")
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption()))
        print(f"key {p} (RSA-3072); its public half: python tools/sign_pvm.py pubkey --out <file>")
        return 0
    key = load_key(a.key)
    if a.cmd == "pubkey":
        pathlib.Path(a.out).write_bytes(pubkey_bytes(key))
        print(f"pubkey {a.out} sha256={hashlib.sha256(pubkey_bytes(key)).hexdigest()}")
        return 0
    module = pathlib.Path(a.module).read_bytes()
    if module[:4] != b"\0asm":
        sys.exit(f"{a.module} is not a WebAssembly module")
    out = sign_bytes(key, module, a.name)
    pathlib.Path(a.out).write_bytes(out)
    print(f"signed {a.out} name={a.name} module={len(module)} sha256={hashlib.sha256(module).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
