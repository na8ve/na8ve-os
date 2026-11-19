#!/usr/bin/env python3
"""na8ve-os Image & Visual Perception Hybrid Simulation Daemon

Simulates the complete na8ve-os visual perception and cognitive cycle:
  - Hardware camera sensor abstraction with zero-raw-image-persistence privacy gating
  - Real-time foveated saccade neural classification (8 saccades -> label, prob, bbox)
  - ANSI ASCII camera viewport generation for operator consoles & TUIs
  - Autoregressive cognitive turn coupling with native C cognitive engine (console_host)
  - Core 0 Actuator Safety Table enforcement
  - Multi-client TCP socket server on port 7878 for na8ve-console & na8ve-tui
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import select
import socket
import subprocess
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

SCENES = [
    {
        "name": "sprout",
        "label": "sprout",
        "confidence": 0.84,
        "bbox": [14, 18, 42, 46],
        "top5": [("sprout", 0.84), ("moss", 0.06), ("mushroom", 0.04), ("grass", 0.03), ("seaweed", 0.01)],
        "actuator_target": "mister",
        "actuator_action": "pulse",
        "ascii_art": [
            "+--------------------------------+",
            "| . . . . . . . . . . . . . . . .|",
            "| . . . . . \\   / . . . . . . . .|",
            "| . . . . . (o o) . . . . . . . .|",
            "| . . . . . . | . . . . . . . . .|",
            "| . . . . . . | . . . . . . . . .|",
            "| . . . ~~~~~~~~~~~ . . . . . . .|",
            "+--------------------------------+"
        ]
    },
    {
        "name": "indoor_plant",
        "label": "indoor_plant",
        "confidence": 0.88,
        "bbox": [12, 8, 44, 38],
        "top5": [("indoor_plant", 0.88), ("pot", 0.05), ("vase", 0.03), ("leaf", 0.02), ("table", 0.01)],
        "actuator_target": "light",
        "actuator_action": "on",
        "ascii_art": [
            "+--------------------------------+",
            "| . . . . : - = = - : . . . . . .|",
            "| . . . * # # @ @ # # * . . . . .|",
            "| . . * # [TARGET OBJECT] # * . .|",
            "| . . . * # # @ @ # # * . . . . .|",
            "| . . . . : - = = - : . . . . . .|",
            "| . . . . [___POT___] . . . . . .|",
            "+--------------------------------+"
        ]
    },
    {
        "name": "bell_pepper",
        "label": "bell_pepper",
        "confidence": 0.91,
        "bbox": [16, 12, 48, 44],
        "top5": [("bell_pepper", 0.91), ("cucumber", 0.04), ("apple", 0.02), ("zucchini", 0.01), ("gourd", 0.01)],
        "actuator_target": "vent",
        "actuator_action": "open",
        "ascii_art": [
            "+--------------------------------+",
            "| . . . . . . || . . . . . . . . |",
            "| . . . . . /----\\ . . . . . . . |",
            "| . . . . (  PEPPER ) . . . . . .|",
            "| . . . .  \\______/ . . . . . . .|",
            "| . . . . . . . . . . . . . . . .|",
            "| . . . . . . . . . . . . . . . .|",
            "+--------------------------------+"
        ]
    },
    {
        "name": "ladybug",
        "label": "ladybug",
        "confidence": 0.79,
        "bbox": [20, 22, 36, 38],
        "top5": [("ladybug", 0.79), ("beetle", 0.11), ("ant", 0.04), ("fly", 0.03), ("spider", 0.02)],
        "actuator_target": "buzzer",
        "actuator_action": "chirp",
        "ascii_art": [
            "+--------------------------------+",
            "| . . . . . \\ / . . . . . . . . .|",
            "| . . . . . (o) . . . . . . . . .|",
            "| . . . . / *|* \\ . . . . . . . .|",
            "| . . . . ( *|* ) . . . . . . . .|",
            "| . . . . \\__v__/ . . . . . . . .|",
            "| . . . . . . . . . . . . . . . .|",
            "+--------------------------------+"
        ]
    },
    {
        "name": "lampshade",
        "label": "lampshade",
        "confidence": 0.85,
        "bbox": [18, 10, 46, 40],
        "top5": [("lampshade", 0.85), ("candle", 0.06), ("lantern", 0.04), ("flashlight", 0.03), ("bulb", 0.01)],
        "actuator_target": "light",
        "actuator_action": "on",
        "ascii_art": [
            "+--------------------------------+",
            "| . . . . /======\\ . . . . . . . |",
            "| . . .  /  LAMP  \\ . . . . . . .|",
            "| . . . /==========\\ . . . . . . |",
            "| . . . . . . || . . . . . . . . |",
            "| . . . . . . || . . . . . . . . |",
            "| . . . . . /====\\ . . . . . . . |",
            "+--------------------------------+"
        ]
    }
]

class ImageEnvironment:
    """Simulates camera hardware state, foveated saccades, and actuator policies."""
    def __init__(self):
        self.scene_idx = 1 # Default: indoor_plant
        self.preview_active = False
        self.preview_fps = 5
        self.preview_last_keep = time.time()
        self.acts = {
            "light": "off",
            "vent": "closed",
            "buzzer": "off",
            "mister": "off"
        }

    def set_scene(self, idx: int) -> bool:
        if 0 <= idx < len(SCENES):
            self.scene_idx = idx
            return True
        return False

    def current_scene(self) -> dict:
        return SCENES[self.scene_idx]

    def render_ascii(self) -> list[str]:
        s = self.current_scene()
        lines = [
            "--- na8ve-os Vision & Neural Perception ---",
            "Frame: 64x64 QVGA Grayscale Viewport"
        ]
        lines.extend(s["ascii_art"])
        lines.append(f'Detection: label="{s["label"]}" confidence={s["confidence"]:.2f} bbox={s["bbox"]}')
        lines.append("Cognition: Event metadata routed to cortex-mvp (pVM #1)")
        lines.append("Policy: Zero raw pixels persisted or transmitted.")
        return lines


class CognitiveEngineBackend:
    """Manages child process to native C console_host for real neural turns."""
    def __init__(self):
        self.binary = self._find_binary()
        self.p = None
        self.current_model = "cortex-mvp"
        if self.binary:
            try:
                self.p = subprocess.Popen(
                    [str(self.binary)],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    encoding="utf-8",
                    errors="replace"
                )
                self.p.stdout.readline() # Drain banner
                # Pre-load default model
                for _ in self.call_stream("model-load flash 32"):
                    pass
            except Exception as e:
                print(f"[!] Warning: failed to start native C engine: {e}")
                self.p = None

    def _find_binary(self) -> pathlib.Path | None:
        candidates = [
            ROOT / "core-host/build/console_host.exe",
            ROOT / "core-host/build/console_host_greenhouse.exe",
            ROOT / "build/bin/console_host.exe"
        ]
        for c in candidates:
            if c.exists():
                return c
        return None

    def _find_model(self, name_or_path: str) -> pathlib.Path | None:
        """A model file the developer names (NA8VE_MODEL) or one in the working folder."""
        named = os.environ.get("NA8VE_MODEL", "")
        if named and pathlib.Path(named).is_file():
            return pathlib.Path(named).resolve()
        base = pathlib.Path(str(name_or_path).replace("\\", "/").split("/")[-1]).stem
        here = pathlib.Path.cwd() / f"{base}.n8vm"
        if base and here.is_file():
            return here.resolve()
        found = sorted(pathlib.Path.cwd().glob("*.n8vm"))
        return found[0].resolve() if found else None

    def _sanitize_line(self, line: str) -> str:
        # Zero exposure of model internal architecture invariants
        if line.startswith("model "):
            tokens = line.split()
            safe_tokens = []
            for t in tokens:
                k = t.split("=")[0]
                if k in ("d", "nh", "N", "L", "payload", "sram_heads", "sram_bytes", "tables_sram", "enc_copy", "encv_copy", "dect") or "sig" in k:
                    continue
                if k == "name":
                    val = t.split("=")[1]
                    safe_tokens.append(f"name={val}")
                else:
                    safe_tokens.append(t)
            if not any(st.startswith("width=") for st in safe_tokens):
                safe_tokens.append("width=32")
            return " ".join(safe_tokens)
        return line

    def call_stream(self, line: str):
        if not self.p:
            return

        # Translate model-load
        if line.startswith("model-load"):
            rest = line[10:].strip()
            if not rest:
                model_arg, width_arg = "flash", "32"
            else:
                rparts = rest.rsplit(" ", 1)
                if len(rparts) == 2 and any(rparts[1].startswith(d) for d in ("4", "8", "16", "32")):
                    model_arg, width_arg = rparts[0].strip(), rparts[1].strip()
                else:
                    model_arg, width_arg = rest, "32"
            resolved = self._find_model(model_arg)
            if resolved:
                cmd_to_send = f"model-load {resolved} {width_arg}"
                self.current_model = resolved.stem
            else:
                cmd_to_send = line
        else:
            cmd_to_send = line

        try:
            self.p.stdin.write(cmd_to_send.strip() + "\n")
            self.p.stdin.flush()
            while True:
                l = self.p.stdout.readline()
                if not l:
                    break
                l = l.strip()
                yield self._sanitize_line(l)
                if l.startswith("OK") or l.startswith("ERR"):
                    break
        except Exception:
            pass


class ImageAppServer:
    """Multiplexing TCP server implementing wire protocol on port 7878."""
    def __init__(self, host: str = "127.0.0.1", port: int = 7878):
        self.host = host
        self.port = port
        self.env = ImageEnvironment()
        self.engine = CognitiveEngineBackend()
        self.srv_sock = None
        self.clients = []
        self.running = False
        self.lock = threading.Lock()

    def start(self):
        self.srv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv_sock.bind((self.host, self.port))
        self.srv_sock.listen(8)
        self.running = True
        print(f"[*] na8ve-os Image App Daemon listening on {self.host}:{self.port}")

        threading.Thread(target=self._accept_loop, daemon=True).start()
        threading.Thread(target=self._telemetry_loop, daemon=True).start()

    def _accept_loop(self):
        while self.running:
            try:
                csock, caddr = self.srv_sock.accept()
                with self.lock:
                    self.clients.append(csock)
                threading.Thread(target=self._client_handler, args=(csock, caddr), daemon=True).start()
            except Exception:
                break

    def _client_handler(self, csock: socket.socket, caddr):
        f = csock.makefile("r", encoding="utf-8", errors="replace")
        try:
            while self.running:
                line = f.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                for reply in self.dispatch(line):
                    csock.sendall((reply + "\n").encode("utf-8"))
        except Exception:
            pass
        finally:
            with self.lock:
                if csock in self.clients:
                    self.clients.remove(csock)
            csock.close()

    def broadcast(self, msg: str):
        with self.lock:
            dead = []
            for c in self.clients:
                try:
                    c.sendall((msg + "\n").encode("utf-8"))
                except Exception:
                    dead.append(c)
            for d in dead:
                self.clients.remove(d)

    def _telemetry_loop(self):
        seq = 0
        while self.running:
            time.sleep(3.0)
            seq += 1
            s = self.env.current_scene()
            self.broadcast(f'ev vision seq={seq} scene={s["name"]} label="{s["label"]}" conf={s["confidence"]:.2f} priv=zero_raw')

    def dispatch(self, cmd_line: str):
        parts = cmd_line.split()
        verb = parts[0].lower() if parts else ""

        if verb == "ping":
            yield "pong na8ve-os"
            yield "OK ping"
            return

        if verb == "cam-probe":
            yield "cam sensor=UnoQ-QRB2210-Cam pid=0x2210 view=72 resolution=64x64 fps=5 status=ready"
            yield "OK cam-probe"
            return

        if verb == "cam-scene":
            if len(parts) > 1:
                try:
                    idx = int(parts[1])
                    if self.env.set_scene(idx):
                        yield f"ok scene={self.env.current_scene()['name']}"
                        yield "OK cam-scene"
                        return
                except ValueError:
                    pass
            yield "ERR usage: cam-scene <0..4>"
            return

        if verb == "cam-preview":
            sub = parts[1] if len(parts) > 1 else ""
            if sub == "on":
                self.env.preview_active = True
                yield "ok preview started"
                yield "OK cam-preview"
                return
            elif sub == "keep":
                self.env.preview_last_keep = time.time()
                yield "ok keepalive"
                yield "OK cam-preview"
                return
            elif sub == "off":
                self.env.preview_active = False
                yield "ok preview stopped"
                yield "OK cam-preview"
                return
            yield "ERR usage: cam-preview on|keep|off"
            return

        if verb == "vision":
            for line in self.env.render_ascii():
                yield line
            yield "OK vision"
            return

        if verb == "os-vision":
            sub = parts[1] if len(parts) > 1 else "once"
            s = self.env.current_scene()
            if sub == "once":
                yield f'vision class={s["label"]} p={s["confidence"]:.3f} ms=152'
                top5_str = " ".join(f"{lbl}:{prob:.3f}" for lbl, prob in s["top5"])
                yield f"vision-top5 {top5_str}"
                yield "OK os-vision"
                return
            yield "OK os-vision"
            return

        if verb == "os-info":
            yield "os image=na8ve-os-unoq-0.1.0 cores=4 ram_mb=4096"
            yield "os manifest v=1 build=1762300800 pvms=4 grants=14 routes=2"
            yield "os pvm id=1 name=cortex-mvp state=running core=1 prio=5 budget_ms=600000 stack=65536 mem=268435456 grants=6 faults=0"
            yield "os pvm id=2 name=matrix state=running core=0 prio=3 budget_ms=2000 stack=8192 mem=65536 grants=0 faults=0"
            yield "os pvm id=3 name=netprobe state=running core=2 prio=3 budget_ms=1000 stack=32768 mem=67108864 grants=3 faults=0"
            yield "os pvm id=4 name=image-app state=running core=3 prio=4 budget_ms=5000 stack=65536 mem=134217728 grants=5 faults=0"
            yield "OK os-info"
            return

        if verb == "os-call":
            if len(parts) >= 3 and parts[1] in ("4", "image"):
                op = int(parts[2])
                s = self.env.current_scene()
                if op == 1:
                    yield "pong image-app"
                    yield "OK os-call"
                    return
                elif op == 2: # Probe
                    yield "cam sensor=UnoQ-QRB2210-Cam pid=0x2210 view=72 resolution=64x64 fps=5 status=ready"
                    yield "OK os-call"
                    return
                elif op == 16: # Capture (0x10)
                    yield f"ok captured scene={s['name']} (volatile DMA purged)"
                    yield "OK os-call"
                    return
                elif op == 17: # Classify (0x11)
                    yield f"class={s['label']} p={s['confidence']:.2f} ms=152 saccades=8"
                    yield "OK os-call"
                    return
                elif op == 18: # Status (0x12)
                    yield f"scene={s['name']} class={s['label']} p={s['confidence']:.2f} bbox={s['bbox']} privacy=zero_raw_persisted"
                    yield "OK os-call"
                    return
                elif op == 19: # ASCII View (0x13)
                    for line in self.env.render_ascii():
                        yield line
                    yield "OK os-call"
                    return
                elif op == 20: # Cognitive Turn (0x14)
                    yield "ok queued"
                    yield "OK os-call"
                    return
                elif op == 21: # Actuate (0x15)
                    tgt = s["actuator_target"]
                    act = s["actuator_action"]
                    self.env.acts[tgt] = act
                    yield f"ok proposed act target={tgt} state={act} proposed_by=image-app"
                    yield "OK os-call"
                    return

        if verb in ("chat", "ask", "say"):
            prompt = " ".join(parts[1:])
            if self.engine.p:
                p_hex = f"User: {prompt}\nAssistant: ".encode("utf-8").hex()
                for r in self.engine.call_stream(f"chat 32 3 {p_hex}"):
                    yield r
                return
            else:
                s = self.env.current_scene()
                yield f"b Starting cognitive turn on scene: {s['label']}..."
                yield f"The camera identifies {s['label']} with {s['confidence']*100:.0f}% confidence."
                yield "done us=84000"
                yield "OK chat"
                return

        if verb == "acts":
            for k, v in self.env.acts.items():
                yield f"act name={k} state={v} guard=free"
            yield "table n=4 ok=1"
            yield "OK acts"
            return

        if verb in ("model", "/model"):
            yield "model 1: bx-1m-l2-t036 (recurrent int32)"
            yield "model 2: bx-1m-l2-t036-hardened (recurrent int32)"
            yield "model 3: bx-2m-t035 (recurrent int32)"
            yield "OK model"
            return

        if verb == "model-load":
            if self.engine and self.engine.p:
                for line in self.engine.call_stream(cmd_line):
                    yield line
                return
            else:
                target = parts[1] if len(parts) > 1 else "bx-1m-l2-t036"
                width = parts[2] if len(parts) > 2 else "32"
                yield f"model name={target} width={width} loaded=1"
                yield "OK model-load"
                return

        # Default fallback
        yield f"ERR unknown command: {verb}"

def main():
    parser = argparse.ArgumentParser(description="na8ve-os Image Perception App Simulation Daemon")
    parser.add_argument("--host", default="127.0.0.1", help="Bind IP address")
    parser.add_argument("--port", type=int, default=7878, help="TCP port (default 7878)")
    args = parser.parse_args()

    server = ImageAppServer(host=args.host, port=args.port)
    server.start()

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.running = False

if __name__ == "__main__":
    main()

