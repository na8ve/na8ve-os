#!/usr/bin/env python3
"""Compose and validate na8ve-os's boot manifest (`docs/sdk-guide/05-compilation-signing-and-packaging-toolchain.md`).

    python tools/build_manifest.py MANIFEST.json --payloads DIR --out manifest.bin
                                   [--partitions partitions.csv]

MANIFEST.json names each pVM, its partition, core, budgets, IPC mask and grants; each pVM's
module length and SHA-256 come from its signed payload in DIR (`tools/sign_app.py`), or, for a
test manifest with no payload, from "payload_len" and "digest". The binary table format uses a
32-byte header, 96 bytes per pVM, and 32 bytes per grant (little-endian). Everything the target
parser checks is checked here first, so a bad manifest fails the build rather than boot: reserved
pins in grants, disallowed raw GPIO writes or flash writes, over-budget memory requests, duplicate
exclusive grants, or IPC bits to an absent pVM. With --partitions, each payload and flash grant
must fit its partition. Exit 2 and a reason on any failure; nothing is written."""
import argparse
import hashlib
import json
import pathlib
import re
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    import sign_pvm
except ImportError:
    import sign_app as sign_pvm

MAX_PVMS, MAX_GRANTS, NAME = 8, 32, 16
PAGE = 65536
LINEAR_MAX, LINEAR_TOTAL = 6 * 1024 * 1024, 6 * 1024 * 1024 + 512 * 1024
PSRAM_TOTAL = 512 * 1024
STACK_MIN, STACK_MAX, BUDGET_MAX = 4096, 65536, 600000
PAYLOAD_MAX = 1024 * 1024
GPIO_MAX = 48
KINDS = {"sensor": 1, "gpio": 2, "flash": 3, "psram": 4, "cloud": 5, "store": 6, "accel": 7, "chat": 8}
RIGHTS_OK = {"sensor": "r", "gpio": "r", "flash": "r", "psram": "rw", "cloud": "r", "store": "r", "accel": "r", "chat": "rw"}
NAME_RE = re.compile(r"^[A-Za-z0-9_\-:.]{1,16}$")


class Refused(Exception):
    pass


def reserved_pins() -> set[int]:
    """CX_PIN_RESERVED from cx_act.h: `(p) == n` and `((p) >= a && (p) <= b)` terms."""
    act_h = ROOT / "firmware" / "components" / "cx_act" / "include" / "cx_act.h"
    if act_h.is_file():
        lines = act_h.read_text(encoding="utf-8").splitlines()
        start = next((i for i, ln in enumerate(lines) if ln.startswith("#define CX_PIN_RESERVED(p)")), None)
        if start is not None:
            body, i = "", start
            while i < len(lines):
                body += lines[i] + "\n"
                if not lines[i].rstrip().endswith("\\"):
                    break
                i += 1
            pins = {int(n) for n in re.findall(r"\(p\) == (\d+)", body)}
            for a, b in re.findall(r"\(p\) >= (\d+) && \(p\) <= (\d+)", body):
                pins.update(range(int(a), int(b) + 1))
            if pins:
                return pins
    # Fallback default reserved pins on ESP32-S3 (microSD, mic, camera, flash, PSRAM, USB)
    pins = {7, 8, 9, 21, 41, 42, 19, 20}
    pins.update({10, 11, 12, 13, 14, 15, 16, 17, 18, 38, 39, 40, 47, 48})
    pins.update(range(26, 38))
    return pins


def partitions(path: pathlib.Path) -> dict[str, int]:
    out = {}
    for row in path.read_text(encoding="utf-8").splitlines():
        row = row.split("#")[0].strip()
        if not row:
            continue
        f = [c.strip() for c in row.split(",")]
        if len(f) >= 5 and f[3] and f[4]:
            out[f[0]] = int(f[4], 0)
    return out


def label(s: str, what: str, empty: bool = False) -> bytes:
    if s == "" and empty:
        return b"\0" * NAME
    if not NAME_RE.match(s):
        raise Refused(f"{what}: {s!r} is not 1-16 of [A-Za-z0-9_-:.]")
    return s.encode("ascii").ljust(NAME, b"\0")


def grant_bytes(g: dict, owner: str, reserved: set[int], parts: dict | None) -> tuple[bytes, int]:
    kind = g.get("kind")
    if kind not in KINDS:
        raise Refused(f"{owner}: grant kind {kind!r}")
    rights = g.get("rights", "r")
    if not rights or set(rights) - set("rwx"):
        raise Refused(f"{owner}: rights {rights!r}")
    if set(rights) - set(RIGHTS_OK[kind]):
        raise Refused(f"{owner}: {kind} may not have rights {rights!r} (a model never drives a pin; flash is read only)")
    r = (1 if "r" in rights else 0) | (2 if "w" in rights else 0) | (4 if "x" in rights else 0)
    a = b = 0
    lab = b"\0" * NAME
    if kind == "gpio":
        a = int(g["pin"])
        if not 0 <= a <= GPIO_MAX:
            raise Refused(f"{owner}: gpio {a}")
        if a in reserved:
            raise Refused(f"{owner}: pin {a} is reserved (cx_act.h CX_PIN_RESERVED)")
    elif kind == "flash":
        lab = label(g["label"], f"{owner}: flash label")
        a, b = int(g.get("offset", 0)), int(g["length"])
        if b <= 0 or a < 0:
            raise Refused(f"{owner}: flash range")
        if parts is not None and (g["label"] not in parts or a + b > parts[g["label"]]):
            raise Refused(f"{owner}: flash {g['label']} [{a}, {a + b}) is not inside a partition of the table")
    elif kind == "psram":
        b = int(g["length"])
        if not 0 < b <= PSRAM_TOTAL:
            raise Refused(f"{owner}: psram {b}")
    elif kind == "store":
        if g.get("label", "query") != "query":
            raise Refused(f"{owner}: the store grants only query")
        lab = label("query", owner)
    elif kind == "accel":
        raise Refused(f"{owner}: accel is not a grant an app can hold")
    elif kind == "chat":  # the console's chat, streamed by the pVM (os-chat-001)
        if g.get("label") != "board":
            raise Refused(f"{owner}: the chat grants only board")
        lab = label("board", owner)
    else:
        lab = label(g["label"], f"{owner}: {kind} name")
    excl = 1 if g.get("exclusive", False) else 0
    out = struct.pack("<BBBBII", KINDS[kind], r, excl, 0, a, b) + lab + b"\0" * 4
    assert len(out) == 32
    return out, b if kind == "psram" else 0


def build(spec: dict, payloads: pathlib.Path | None, parts: dict | None, wrong_digest: str = "", manifest_dir: pathlib.Path | None = None) -> bytes:
    reserved = reserved_pins()
    if "pvms" in spec:
        pvms = spec["pvms"]
    elif "name" in spec:
        pvms = [spec]
    elif isinstance(spec, list):
        pvms = spec
    else:
        pvms = []
    if not 1 <= len(pvms) <= MAX_PVMS:
        raise Refused(f"{len(pvms)} pvms: 1 to {MAX_PVMS}")
    ids = [int(p["id"]) for p in pvms]
    entries, grants = [], []
    linear = psram = 0
    seen_names, seen_parts = set(), set()
    exclusive = []  # (kind, target) held
    for p in pvms:
        pid, name, part = int(p["id"]), p["name"], p["partition"]
        if not 1 <= pid <= MAX_PVMS or ids.count(pid) != 1:
            raise Refused(f"pvm id {pid}")
        if name in seen_names or part in seen_parts:
            raise Refused(f"{name}: a name or partition twice")
        seen_names.add(name)
        seen_parts.add(part)
        core = int(p.get("core", 1))
        if core not in (0, 1):
            raise Refused(f"{name}: core {core}")
        if "payload" in p:
            payload_path = None
            if payloads is not None and (payloads / p["payload"]).is_file():
                payload_path = payloads / p["payload"]
            elif manifest_dir is not None:
                if (manifest_dir / p["payload"]).is_file():
                    payload_path = manifest_dir / p["payload"]
                elif (manifest_dir / "dist" / p["payload"]).is_file():
                    payload_path = manifest_dir / "dist" / p["payload"]
            if payload_path is None and pathlib.Path(p["payload"]).is_file():
                payload_path = pathlib.Path(p["payload"])

            if payload_path is not None:
                data = payload_path.read_bytes()
                if data.startswith(b"N8PV"):
                    module, _, _ = sign_pvm.read_payload(data)
                else:
                    module = data
                plen, digest = len(module), hashlib.sha256(module).digest()
            else:
                plen = int(p.get("payload_len", 4096))
                digest_hex = p.get("digest", "")
                digest = bytes.fromhex(digest_hex) if digest_hex else hashlib.sha256(name.encode("ascii")).digest()
        else:
            plen = int(p.get("payload_len", 4096))
            digest_hex = p.get("digest", "")
            digest = bytes.fromhex(digest_hex) if digest_hex else hashlib.sha256(name.encode("ascii")).digest()
        if name == wrong_digest:  # os-ota-001's unhealthy image: a digest its payload does not have
            digest = bytes([digest[0] ^ 0x80]) + digest[1:]
        if not 8 <= plen <= PAYLOAD_MAX or len(digest) != 32:
            raise Refused(f"{name}: payload {plen} bytes")
        # a licensed app's licence is the partition's last kilobyte (na8ve-devs scope-08 §4): its payload stops short
        room = (parts[part] - 1024 if p.get("licensed", False) else parts[part]) if parts is not None and part in parts else 0
        if parts is not None and (part not in parts or sign_pvm.HEADER + plen + sign_pvm.SIG > room):
            raise Refused(f"{name}: the payload does not fit partition {part}"
                          + (" before its licence" if p.get("licensed", False) else ""))
        ml, stack, budget = int(p["mem_linear"]), int(p.get("stack", 16384)), int(p.get("budget_ms", 10000))
        if ml < PAGE or ml % PAGE or ml > LINEAR_MAX:
            raise Refused(f"{name}: linear memory {ml}")
        if not STACK_MIN <= stack <= STACK_MAX or stack % 16:
            raise Refused(f"{name}: stack {stack}")
        if not 0 < budget <= BUDGET_MAX:
            raise Refused(f"{name}: budget {budget}")
        mask = 0
        for t in p.get("allowed_ipc", []):
            t = int(t)
            if t == pid:
                raise Refused(f"{name}: allowed_ipc {t}")
            mask |= 1 << t
        first, its_psram = len(grants), 0
        for g in p.get("grants", []):
            gb, ps = grant_bytes(g, name, reserved, parts)
            its_psram += ps
            if g["kind"] != "psram":
                tgt = (g["kind"], g.get("pin"), g.get("label"), g.get("offset", 0), g.get("length"))
                for k, other, excl in exclusive:
                    same = k[0] == tgt[0] and (k[1:3] == tgt[1:3] if tgt[0] != "flash" else
                                              k[2] == tgt[2] and k[3] < tgt[3] + tgt[4] and tgt[3] < k[3] + k[4])
                    if same and (excl or g.get("exclusive", False)) and other != name:
                        raise Refused(f"{name}: {g['kind']} {g.get('label') or g.get('pin')} is held exclusively by {other}")
                exclusive.append((tgt, name, g.get("exclusive", False)))
            grants.append(gb)
        flags = (1 if p.get("required", False) else 0) | (2 if p.get("licensed", False) else 0)
        linear += ml
        psram += its_psram
        entries.append(struct.pack("<BBBBHH", pid, core, flags, 0, first, len(grants) - first) +
                       label(name, "name") + label(part, "partition") + struct.pack("<I", plen) + digest +
                       struct.pack("<IIIII", ml, its_psram, mask, stack, budget))
    if len(grants) > MAX_GRANTS:
        raise Refused(f"{len(grants)} grants: at most {MAX_GRANTS}")
    if linear > LINEAR_TOTAL:
        raise Refused(f"linear memory {linear} in all: at most {LINEAR_TOTAL}")
    if psram > PSRAM_TOTAL:
        raise Refused(f"psram {psram} in all")
    total = 32 + 96 * len(entries) + 32 * len(grants)
    header = b"N8MF" + struct.pack("<HBBII", 1, len(entries), len(grants), int(spec.get("seq", 1)), total) + b"\0" * 16
    out = header + b"".join(entries) + b"".join(grants)
    assert len(out) == total
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--payloads")
    ap.add_argument("--partitions")
    ap.add_argument("--out")
    ap.add_argument("--test-wrong-digest", default="", metavar="NAME",
                    help="a test image only: NAME's digest one bit off, so pvmfw must refuse it (os-ota-001)")
    a = ap.parse_args()
    spec = json.loads(pathlib.Path(a.manifest).read_text(encoding="utf-8"))
    try:
        out = build(spec, pathlib.Path(a.payloads) if a.payloads else None,
                    partitions(pathlib.Path(a.partitions)) if a.partitions else None, a.test_wrong_digest,
                    manifest_dir=pathlib.Path(a.manifest).resolve().parent)
    except (Refused, KeyError, ValueError, OSError) as e:
        print(f"manifest refused: {e}", file=sys.stderr)
        return 2
    if a.out:
        pathlib.Path(a.out).write_bytes(out)
    print(f"manifest {a.out or '(checked)'} bytes={len(out)} pvms={out[6]} grants={out[7]} "
          f"sha256={hashlib.sha256(out).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
