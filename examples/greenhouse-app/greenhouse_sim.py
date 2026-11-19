#!/usr/bin/env python3
"""na8ve-os Automated Greenhouse Simulation Daemon

Simulates real-time streaming environmental telemetry, Vapor Pressure Deficit (VPD)
reflex loops, on-device memory graph mutations, and safety-gated actuation for
the na8ve-os Greenhouse Demo.

Integrates with the native C cognitive engine (console_host_greenhouse) for real
autoregressive neural inference, SQLite episodic memory graph storage, and
compiled actuator table safety enforcement while providing live simulated physics.

Usage:
  python tools/greenhouse_daemon.py
  python tools/greenhouse_daemon.py --port 7878
  python tools/greenhouse_daemon.py --tick-interval 1.5
  python tools/greenhouse_daemon.py --stdio
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import os
import pathlib
import queue
import socket
import subprocess
import sys
import threading
import time
from typing import Generator

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 25 Canonical Greenhouse Seed Facts from seed-device.txt
SEED_FACTS = [
    "greenhouse | contains | bed-1",
    "greenhouse | contains | bed-2",
    "greenhouse | contains | the water tank",
    "greenhouse | located_in | the back garden",
    "bed-1 | grows | basil",
    "bed-1 | grows | tomatoes",
    "bed-2 | grows | lettuce",
    "bed-2 | grows | mint",
    "basil | needs | full sun",
    "tomatoes | needs | six hours of light",
    "lettuce | needs | partial shade",
    "pump | waters | bed-1",
    "pump | waters | bed-2",
    "pump | draws_from | the water tank",
    "fan | cools | greenhouse",
    "vent | ventilates | greenhouse",
    "mister | humidifies | bed-2",
    "light | lights | bed-1",
    "[greenhouse|target_temp] 24 C",
    "[greenhouse|target_humidity] 60 percent",
    "[pump|schedule] every morning at 07:00 for two minutes",
    "[light|schedule] on from 06:00 to 20:00",
    "[tank|capacity] 40 litres",
    "[vent|rule] open above 28 C, only with the door shut",
    "[bed-1|last_watered] 2026-10-13 at 07:00",
]


class CognitiveEngineBackend:
    """Manages the native C cognitive engine process (console_host_greenhouse).

    Provides real autoregressive forward passes, SQLite episodic memory graph storage,
    graph queries, and actuator table enforcement.
    """

    def __init__(self, broadcast_fn=None):
        self.broadcast_fn = broadcast_fn or (lambda line: None)
        self.binary_path = self._find_binary()
        self.p: subprocess.Popen | None = None
        self.lock = threading.Lock()
        self.line_queue: queue.Queue[str] = queue.Queue()
        self.current_model = None
        if self.binary_path:
            self._start_process()

    def _find_binary(self) -> pathlib.Path | None:
        candidates = [
            ROOT / "core-host/build/console_host_greenhouse.exe",
            ROOT / "core-host/build/console_host.exe",
            ROOT.parent / "na8ve-os/build/bin/console_host_greenhouse.exe",
            ROOT.parent / "na8ve-os/build/bin/console_host.exe",
            pathlib.Path.cwd() / "build/bin/console_host_greenhouse.exe",
            pathlib.Path.cwd() / "build/bin/console_host.exe",
            pathlib.Path(__file__).resolve().parent / "console_host_greenhouse.exe",
            pathlib.Path(sys.executable).parent / "console_host_greenhouse.exe",
        ]
        posix_candidates = [pathlib.Path(str(c)[:-4]) for c in candidates if str(c).endswith(".exe")]
        for c in candidates + posix_candidates:
            if c.exists() and c.is_file():
                return c.resolve()
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

    def _start_process(self):
        try:
            self.p = subprocess.Popen(
                [str(self.binary_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
            )
            t = threading.Thread(target=self._reader, daemon=True)
            t.start()
            time.sleep(0.1)

            # Seed initial 25 greenhouse facts into store
            print(f"[ENGINE] Seeding {len(SEED_FACTS)} greenhouse facts into cognitive store...")
            for fact in SEED_FACTS:
                self.call(f"remember {fact}", timeout=1.0)

            # Pre-load default model if available
            print(f"[ENGINE] Pre-loading neural model bx-1m-l2-t036...")
            self.call("model-load flash 32", timeout=5.0)
            self.current_model = "bx-1m-l2-t036"
        except Exception as e:
            print(f"[ENGINE] Error starting cognitive engine: {e}")
            self.p = None

    def _reader(self):
        if not self.p or not self.p.stdout:
            return
        for line in self.p.stdout:
            line_str = line.rstrip("\r\n")
            if line_str.startswith("mx ") or line_str.startswith("ev "):
                self.broadcast_fn(line_str)
            self.line_queue.put(line_str)

    def _sanitize_line(self, line: str) -> str:
        # Emit only public runtime metadata keys (zero exposure of internal structure)
        if line.startswith("model "):
            allowed = ("name", "layout", "width", "bytes", "mode", "at")
            safe_tokens = []
            for t in line.split():
                if "=" not in t:
                    safe_tokens.append(t)
                    continue
                k, v = t.split("=", 1)
                if k not in allowed:
                    continue
                if k == "name":
                    safe_tokens.append(f"name={pathlib.Path(v).stem}.n8vm")
                else:
                    safe_tokens.append(t)
            if not any(st.startswith("width=") for st in safe_tokens):
                safe_tokens.append("width=32")
            return " ".join(safe_tokens)
        return line

    def call_stream(self, cmd_line: str, timeout: float = 10.0) -> Generator[str, None, None]:
        if not self.p or self.p.poll() is not None:
            yield "ERR engine not running"
            return

        with self.lock:
            # Drain queue
            while not self.line_queue.empty():
                try:
                    self.line_queue.get_nowait()
                except queue.Empty:
                    break

            # Handle model-load translation
            if cmd_line.startswith("model-load"):
                rest = cmd_line[10:].strip()
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
                    cmd_to_send = cmd_line
            else:
                cmd_to_send = cmd_line

            try:
                self.p.stdin.write(cmd_to_send + "\n")
                self.p.stdin.flush()
            except Exception as e:
                yield f"ERR write: {e}"
                return

            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    line = self.line_queue.get(timeout=0.1)
                    line_clean = self._sanitize_line(line)
                    yield line_clean
                    if line.startswith("OK") or line.startswith("ERR"):
                        break
                except queue.Empty:
                    pass

    def call(self, cmd_line: str, timeout: float = 10.0) -> list[str]:
        return list(self.call_stream(cmd_line, timeout=timeout))

    def stop(self):
        if self.p:
            try:
                self.p.stdin.close()
                self.p.terminate()
            except Exception:
                pass
            self.p = None


class GreenhouseEnvironment:
    """Physics and environmental simulation model for a smart greenhouse."""

    def __init__(self):
        self.lock = threading.Lock()
        # Initial environmental state matching baseline Hackster / Demo runs
        self.temp_c = 26.4
        self.humidity_pct = 84.2
        self.soil_adc = 1140  # <1200 = dry rootzone trigger threshold
        self.lux = 520
        self.chip_temp_c = 41.5
        self.tank_water = True
        self.door_shut = True

        # Actuators
        self.act_fan = "off"        # off, low, high
        self.act_light = "off"      # off, on
        self.act_buzzer = "off"     # off, on
        self.act_pump = "off"       # off, on
        self.act_vent = "closed"    # closed, open
        self.act_mister = "off"     # off, on

        # Actuation timing / duty tracking
        self.last_fan_act_us = 0
        self.last_pump_act_us = 0
        self.mist_pulse_remaining_s = 0.0

        # Memory ID counter
        self.next_mem_id = 100

        # Step count
        self.step = 0

    def calculate_vpd(self) -> float:
        """Calculate Vapor Pressure Deficit (VPD) in kPa."""
        vp_sat = 0.61078 * math.exp((17.27 * self.temp_c) / (self.temp_c + 237.3))
        vp_actual = vp_sat * (self.humidity_pct / 100.0)
        return max(0.0, vp_sat - vp_actual)

    def update_physics(self, dt: float) -> list[str]:
        """Update environmental physics and evaluate reflex controller rules."""
        events: list[str] = []
        now_ts = int(time.time())
        with self.lock:
            self.step += 1

            # Environmental drift
            if self.act_fan == "high":
                self.temp_c = max(22.0, self.temp_c - 0.45 * dt)
                self.humidity_pct = max(55.0, self.humidity_pct - 1.8 * dt)
            elif self.act_fan == "low":
                self.temp_c = max(23.0, self.temp_c - 0.20 * dt)
                self.humidity_pct = max(60.0, self.humidity_pct - 0.8 * dt)
            else:
                self.temp_c = min(32.5, self.temp_c + 0.12 * dt)
                self.humidity_pct = min(92.0, self.humidity_pct + 0.35 * dt)

            # Misting and root-zone water absorption
            if self.mist_pulse_remaining_s > 0:
                self.mist_pulse_remaining_s = max(0.0, self.mist_pulse_remaining_s - dt)
                self.soil_adc = min(2400, self.soil_adc + int(260 * dt))
                self.humidity_pct = min(95.0, self.humidity_pct + 1.2 * dt)
                if self.mist_pulse_remaining_s <= 0:
                    self.act_pump = "off"
                    self.act_mister = "off"
                    events.append('ev actuate target=mist_pump state=OFF reason="pulse_complete"')
                    events.append("act name=pump kind=digital pin=5 state=off reason=pulse_complete")
            else:
                # Soil moisture dries out naturally over time
                self.soil_adc = max(800, self.soil_adc - int(15 * dt))

            # Light heating effect
            if self.act_light == "on":
                self.temp_c += 0.08 * dt
                self.lux = min(1200, self.lux + int(40 * dt))
            else:
                self.lux = max(180, self.lux - int(20 * dt))

            vpd = self.calculate_vpd()

            # Reflex Rule 1: High VPD (> 1.4 kPa) requires misting
            if vpd > 1.40 and self.act_mister == "off" and self.mist_pulse_remaining_s <= 0:
                if self.tank_water:
                    self.act_mister = "on"
                    self.act_pump = "on"
                    self.mist_pulse_remaining_s = 5.0
                    events.append(f'ev reflex rule="vpd_high" vpd={vpd:.2f} action="mist_pulse" duration_ms=5000')
                    events.append('ev actuate target=mist_pump state=ON reason="vpd_exceeded"')
                    events.append("act name=pump kind=digital pin=5 state=on reason=vpd_exceeded")
                else:
                    events.append('ev safety interlock=FAIL target=mist_pump reason="tank_water_empty"')

            # Reflex Rule 2: High Humidity (> 85%) requires fan exhaust
            if self.humidity_pct > 85.0 and self.act_fan == "off":
                self.act_fan = "high"
                events.append(f'ev reflex rule="humidity_high" rh={self.humidity_pct:.1f} action="fan_high"')
                events.append('ev actuate target=fan state=HIGH reason="rh_threshold"')
                events.append("act name=fan kind=pwm pin=4 state=high reason=rh_threshold")
            elif self.humidity_pct < 70.0 and self.act_fan == "high":
                self.act_fan = "off"
                events.append(f'ev reflex rule="humidity_restored" rh={self.humidity_pct:.1f} action="fan_off"')
                events.append('ev actuate target=fan state=OFF reason="rh_normal"')
                events.append("act name=fan kind=pwm pin=4 state=off reason=rh_normal")

            # Reflex Rule 3: Root-zone depletion (ADC < 1200)
            if self.soil_adc < 1200 and self.act_pump == "off" and self.mist_pulse_remaining_s <= 0:
                if self.tank_water:
                    self.act_pump = "on"
                    self.mist_pulse_remaining_s = 4.0
                    events.append(f'ev reflex rule="soil_dry" adc={self.soil_adc} action="irrigate_pulse"')
                    events.append('ev actuate target=pump state=ON reason="soil_depleted"')
                    events.append("act name=pump kind=digital pin=5 state=on reason=soil_depleted")
                else:
                    events.append('ev safety interlock=FAIL target=pump reason="water_reservoir_empty"')

            # Streaming sensor tick event
            events.append(
                f"ev tick seq={self.step} temp_c={self.temp_c:.1f} rh={self.humidity_pct:.1f} "
                f"vpd_kpa={vpd:.2f} soil_adc={self.soil_adc} lux={self.lux} "
                f"fan={self.act_fan} pump={self.act_pump} vent={self.act_vent}"
            )

        return events

    def get_readings_json(self) -> list[str]:
        """Return standardized JSON readings for console/TUI protocol."""
        with self.lock:
            vpd = self.calculate_vpd()
            return [
                json.dumps({
                    "subject": "greenhouse",
                    "temp_c": round(self.temp_c, 1),
                    "humidity_pct": round(self.humidity_pct, 1),
                    "vpd_kpa": round(vpd, 2),
                    "soil_adc": self.soil_adc,
                    "lux": self.lux,
                    "status": "optimal" if (0.8 <= vpd <= 1.2) else "regulating"
                }),
                json.dumps({
                    "subject": "tank",
                    "water_present": self.tank_water,
                    "float_switch_adc": 48 if self.tank_water else 3820
                }),
                json.dumps({
                    "subject": "door",
                    "shut": self.door_shut,
                    "reed_switch": 0 if self.door_shut else 1
                }),
                json.dumps({
                    "subject": "device",
                    "chip_temp_c": round(self.chip_temp_c, 1),
                    "battery_pct": 100,
                    "storage_free_mb": 1420
                }),
                json.dumps({
                    "subject": "mic",
                    "db_spl": 46.2,
                    "peak_hz": 120
                })
            ]


class GreenhouseDaemonServer:
    """Multi-client TCP server and automated greenhouse simulation daemon."""

    def __init__(self, host: str = "127.0.0.1", port: int = 7878, tick_interval: float = 2.0):
        self.host = host
        self.port = port
        self.tick_interval = tick_interval
        self.env = GreenhouseEnvironment()
        self.clients: list[socket.socket] = []
        self.clients_lock = threading.Lock()
        self.running = False
        self.srv_sock: socket.socket | None = None
        self.engine = CognitiveEngineBackend(broadcast_fn=self.broadcast)

    def broadcast(self, line: str):
        """Broadcast a line of text to all connected TCP clients."""
        payload = (line.rstrip("\r\n") + "\n").encode("utf-8")
        with self.clients_lock:
            dead = []
            for c in self.clients:
                try:
                    c.sendall(payload)
                except Exception:
                    dead.append(c)
            for d in dead:
                try:
                    self.clients.remove(d)
                    d.close()
                except Exception:
                    pass

    def handle_command_stream(self, cmd_line: str) -> Generator[str, None, None]:
        """Dispatch a single console command and yield response lines."""
        cmd_line = cmd_line.strip()
        if not cmd_line:
            return

        parts = cmd_line.split()
        verb = parts[0].lower()

        if verb == "hello":
            yield "OK hello tui"
            return

        if verb in ("os-info", "status") and verb == "os-info":
            yield "os version=1.4.0 target=UnoQ-QRB2210 arch=aarch64 cores=4 status=healthy"
            yield "os pvm id=1 name=cortex-mvp state=running width=32 layout=recurrent"
            yield "os pvm id=2 name=greenhouse_controller state=running budget=64KB"
            yield "OK os-info"
            return

        if verb == "os-table":
            yield "os table kernel n=6 version=1"
            yield "os table pvm id=1 entries=6"
            yield "os table pvm id=2 entries=2"
            yield "OK os-table"
            return

        if verb.startswith("os-call"):
            yield "os reply model width=32 sparse=1 open_ms=12"
            yield "OK os-call"
            return

        if verb == "readings":
            for r_json in self.env.get_readings_json():
                yield f"reading {r_json}"
            yield "OK readings"
            return

        if verb == "periph":
            with self.env.lock:
                yield f"periph name=chip ok=1 soc=ESP32-S3 arch=xtensa temp_c={self.env.chip_temp_c:.1f}"
                yield "periph name=i2c ok=1 bus=i2c-0 found=3 addresses=0x44:SHT40,0x23:BH1750,0x20:PCF8574"
                yield f"periph name=door ok=1 pin=gpio43 level={0 if self.env.door_shut else 1} note=reed_switch:low_is_shut"
                yield f"periph name=float ok=1 pin=gpio44 level={0 if self.env.tank_water else 1} note=float_switch:low_is_water"
                yield f"periph name=fan state={self.env.act_fan} pin=gpio4"
                yield f"periph name=light state={self.env.act_light} pin=gpio2"
                yield f"periph name=buzzer state={self.env.act_buzzer} pin=gpio3"
                yield f"periph name=pump state={self.env.act_pump} pin=gpio5"
                yield f"periph name=vent state={self.env.act_vent} pin=i2c:0x20.P0"
                yield f"periph name=mister state={self.env.act_mister} pin=i2c:0x20.P1"
                yield "OK periph"
            return

        if verb == "acts":
            engine_acts = self.engine.call("acts") if self.engine.p else []
            if engine_acts and any(l.startswith("act ") for l in engine_acts):
                for l in engine_acts:
                    if l.startswith("act "):
                        tokens = l.split()
                        name = next((t.split("=")[1] for t in tokens if t.startswith("name=")), None)
                        st = getattr(self.env, f"act_{name}", None)
                        if st:
                            if any(t.startswith("state=") for t in tokens):
                                tokens = [f"state={st}" if t.startswith("state=") else t for t in tokens]
                            else:
                                tokens.append(f"state={st}")
                            yield " ".join(tokens)
                        else:
                            yield l
                    else:
                        yield l
                return
            with self.env.lock:
                yield f"act name=fan kind=pwm pin=4 states=off,low,high safe=off guard=rule min_interval_ms=1000 max_on_ms=0 interlock=0 state={self.env.act_fan}"
                yield f"act name=light kind=digital pin=2 states=off,on safe=off guard=free min_interval_ms=0 max_on_ms=0 interlock=0 state={self.env.act_light}"
                yield f"act name=buzzer kind=digital pin=3 states=off,on safe=off guard=rule min_interval_ms=500 max_on_ms=30000 interlock=0 state={self.env.act_buzzer}"
                yield f"act name=pump kind=digital pin=5 states=off,on safe=off guard=person min_interval_ms=2000 max_on_ms=10000 interlock=1 state={self.env.act_pump}"
                yield f"act name=vent kind=i2c-write pin=i2c:0x20.P0 states=closed,open safe=closed guard=rule min_interval_ms=5000 max_on_ms=0 interlock=1 state={self.env.act_vent}"
                yield f"act name=mister kind=i2c-write pin=i2c:0x20.P1 states=off,on safe=off guard=rule min_interval_ms=2000 max_on_ms=60000 interlock=0 state={self.env.act_mister}"
                yield "reserved pins=1,2,7,8,9,21,41,42"
                yield "table n=6 ok=1"
                yield "OK acts"
            return

        if verb == "act":
            target = "fan"
            state = "on"
            if "=" in cmd_line:
                for token in parts[1:]:
                    if token.startswith("name="):
                        target = token[5:]
                    elif token.startswith("state="):
                        state = token[6:]
            elif len(parts) >= 3:
                target = parts[1]
                state = parts[2]

            with self.env.lock:
                if target == "fan":
                    self.env.act_fan = state
                elif target == "light":
                    self.env.act_light = state
                elif target == "buzzer":
                    self.env.act_buzzer = state
                elif target == "pump":
                    if not self.env.tank_water:
                        yield "refused pump: the tank is dry (interlock fail)"
                        yield "ERR act"
                        return
                    self.env.act_pump = state
                elif target == "vent":
                    if not self.env.door_shut:
                        yield "refused vent: the door is open (interlock fail)"
                        yield "ERR act"
                        return
                    self.env.act_vent = state
                elif target == "mister":
                    self.env.act_mister = state

            if self.engine.p:
                self.engine.call(cmd_line, timeout=2.0)

            self.broadcast(f"act name={target} state={state} proposed_by=operator")
            yield f"OK act {target} {state}"
            return

        if verb == "status":
            vpd = self.env.calculate_vpd()
            if self.engine.p:
                for r in self.engine.call_stream("status"):
                    if r.startswith("store:"):
                        yield r + f" | vpd_kpa={vpd:.2f}"
                    else:
                        yield r
                return
            yield f"store: card | live 42 | written 184 retired 12 archived 6 refused 0 dropped 0 | clock: synced | alarms 0 fired 0 | windows 128 | vpd_kpa={vpd:.2f}"
            yield "OK status"
            return

        if verb == "call":
            payload = cmd_line[4:].strip()
            handled_locally = False
            try:
                call_data = json.loads(payload)
                tool = call_data.get("tool", "")
                if tool == "readings_latest":
                    handled_locally = True
                    subj = call_data.get("subject", "greenhouse")
                    readings = self.env.get_readings_json()
                    found_reading = None
                    for r in readings:
                        obj = json.loads(r)
                        if obj.get("subject") == subj:
                            found_reading = obj
                            break
                    if found_reading:
                        yield f"result {json.dumps(found_reading)}"
                    else:
                        yield f'result {{"subject":"{subj}","reading":"none"}}'
                    yield "OK call"
                    return
                elif tool == "device_status":
                    handled_locally = True
                    yield f'result {{"battery_pct":100,"storage_free_mb":1420,"uptime_s":3600,"chip_temp_c":{self.env.chip_temp_c:.1f}}}'
                    yield "OK call"
                    return
            except Exception:
                pass

            if not handled_locally and self.engine.p:
                yield from self.engine.call_stream(cmd_line)
                return

        if verb == "chat":
            if len(parts) > 1 and not parts[1].isdigit():
                prompt_text = "User: " + " ".join(parts[1:]) + "\nAssistant: "
                cmd_line = f"chat 64 3 {prompt_text.encode('utf-8').hex()}"

        # Delegate all cognitive, model, memory, and export commands to native C engine
        if self.engine.p:
            yield from self.engine.call_stream(cmd_line)
            return

        yield f"OK {verb}"

    def handle_command(self, cmd_line: str) -> list[str]:
        return list(self.handle_command_stream(cmd_line))

    def _client_worker(self, client: socket.socket):
        with self.clients_lock:
            self.clients.append(client)

        try:
            client.sendall(
                b"[BOOT] na8ve-os v1.4.0 (greenhouse automated simulation daemon online)\n"
                b"[INIT] Core 0: Reference Monitor & Actuator Safety Table active\n"
                b"[INIT] Core 1: Cognitive Engine & Episodic Memory Graph active\n"
            )
        except Exception:
            return

        f_in = client.makefile("r", encoding="utf-8", errors="replace")
        try:
            for raw_line in f_in:
                if not self.running:
                    break
                for r in self.handle_command_stream(raw_line):
                    client.sendall((r + "\n").encode("utf-8"))
        except Exception:
            pass
        finally:
            with self.clients_lock:
                if client in self.clients:
                    self.clients.remove(client)
            try:
                client.close()
            except Exception:
                pass

    def _simulation_loop(self):
        """Continuous background tick loop generating physical telemetry."""
        last_t = time.time()
        while self.running:
            time.sleep(self.tick_interval)
            now = time.time()
            dt = now - last_t
            last_t = now

            events = self.env.update_physics(dt)
            for ev in events:
                self.broadcast(ev)

    def start(self):
        """Start the greenhouse simulation daemon."""
        self.running = True
        self.srv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.srv_sock.bind((self.host, self.port))
        except (PermissionError, OSError) as e:
            print(f"\n[ERROR] Unable to bind to tcp://{self.host}:{self.port} - {e}")
            print(f"[DIAGNOSIS] Port {self.port} is already in use or forwarded by another process.")
            print(f"            An ADB forward rule ('adb forward tcp:{self.port} tcp:{self.port}') is likely holding this port.")
            print(f"\n[REMEDY 1] To clear the ADB forward rule and run this simulation:")
            print(f"           adb forward --remove tcp:{self.port}")
            print(f"           python examples/greenhouse-app/greenhouse_sim.py\n")
            print(f"[REMEDY 2] Or run this simulation daemon on an alternate port:")
            print(f"           python examples/greenhouse-app/greenhouse_sim.py --port 7879")
            print(f"           .\\build\\bin\\na8ve-tui.exe --tcp 127.0.0.1:7879\n")
            print(f"[REMEDY 3] If you intended to talk to the attached physical hardware instead,")
            print(f"           do not run this simulation. Connect directly with:")
            print(f"           .\\build\\bin\\na8ve-tui.exe --tcp 127.0.0.1:{self.port}\n")
            sys.exit(1)
        self.srv_sock.listen(8)

        # Start physics simulation thread
        sim_thread = threading.Thread(target=self._simulation_loop, daemon=True)
        sim_thread.start()

        print(f"==================================================================")
        print(f" na8ve-os Automated Greenhouse Simulation Daemon")
        print(f" Listening on tcp://{self.host}:{self.port}")
        print(f" Cognitive Backend: {self.engine.binary_path}")
        print(f" Active Neural Model: {self.engine.current_model}")
        print(f" Emitting real-time sensor ticks every {self.tick_interval}s")
        print(f" Connect via: na8ve-console --tcp {self.host}:{self.port}")
        print(f"              na8ve-tui --tcp {self.host}:{self.port}")
        print(f" Press Ctrl+C to terminate daemon")
        print(f"==================================================================")

        try:
            while self.running:
                client, _ = self.srv_sock.accept()
                t = threading.Thread(target=self._client_worker, args=(client,), daemon=True)
                t.start()
        except KeyboardInterrupt:
            print("\nShutting down greenhouse simulation daemon...")
        finally:
            self.running = False
            if self.srv_sock:
                self.srv_sock.close()
            self.engine.stop()

    def stop(self):
        """Stop the simulation daemon, cognitive engine, and close sockets."""
        self.running = False
        if self.srv_sock:
            try:
                self.srv_sock.close()
            except Exception:
                pass
        self.engine.stop()


def run_stdio_bridge():
    """Run in interactive stdio mode for local process linking."""
    daemon = GreenhouseDaemonServer()
    print("[BOOT] na8ve-os v1.4.0 (greenhouse stdio mode online)")
    sys.stdout.flush()

    stop_evt = threading.Event()

    def ticker():
        last_t = time.time()
        while not stop_evt.is_set():
            time.sleep(2.0)
            now = time.time()
            dt = now - last_t
            last_t = now
            for ev in daemon.env.update_physics(dt):
                sys.stdout.write(ev + "\n")
                sys.stdout.flush()

    t = threading.Thread(target=ticker, daemon=True)
    t.start()

    try:
        for line in sys.stdin:
            for r in daemon.handle_command_stream(line):
                sys.stdout.write(r + "\n")
            sys.stdout.flush()
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        stop_evt.set()
        daemon.stop()


def main():
    parser = argparse.ArgumentParser(description="na8ve-os Automated Greenhouse Simulation Daemon")
    parser.add_argument("--host", default="127.0.0.1", help="TCP bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=7878, help="TCP bind port (default: 7878)")
    parser.add_argument("--tick-interval", type=float, default=2.0, help="Simulation tick interval in seconds (default: 2.0)")
    parser.add_argument("--stdio", action="store_true", help="Run in stdio mode instead of TCP socket server")

    args = parser.parse_args()

    if args.stdio:
        run_stdio_bridge()
    else:
        server = GreenhouseDaemonServer(host=args.host, port=args.port, tick_interval=args.tick_interval)
        server.start()


if __name__ == "__main__":
    main()
