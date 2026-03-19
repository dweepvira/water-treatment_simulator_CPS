#!/usr/bin/env python3
"""
matlab_bridge/physics_client.py
================================
Control loop — MATLAB physics (TCP) ↔ CODESYS (Modbus TCP).

Loop (every DT seconds):
  1. Read coil states from CODESYS via Modbus FC1
  2. Send actuator JSON + newline to MATLAB TCP server
  3. Read sensor JSON response (newline-delimited)
  4. Write sensor registers back to CODESYS via Modbus FC16
"""

import json
import socket
import time
import logging
import argparse
import sys
import signal
from pathlib import Path
from typing import Optional

sys.path.append(str(Path(__file__).parent.parent))

from config.swat_config import MODBUS_CONFIG, COILS, HOLDING_REGISTERS
from utils.modbus_utils import ModbusClientOptimized as ModbusClient
# At top of file, after imports
import queue
shared_sensor_queue: queue.Queue = queue.Queue(maxsize=1)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('MatlabBridge')

REG_ADDR  = {name: info['address'] for name, info in HOLDING_REGISTERS.items()}
COIL_ADDR = {name: info['address'] for name, info in COILS.items()}


class MatlabPhysicsBridge:

    DT          = 0.1    # seconds per cycle
    TCP_TIMEOUT = 0.5    # max wait for MATLAB response

    def __init__(self, plc_host, plc_port=1502,
                 matlab_host='127.0.0.1', matlab_port=9501):
        self.plc_host    = plc_host
        self.plc_port    = plc_port
        self.matlab_host = matlab_host
        self.matlab_port = matlab_port
        self._running    = False

        self.mb  = ModbusClient(host=plc_host, port=plc_port,
                                timeout=3, retries=3,
                                unit_id=MODBUS_CONFIG['unit_id'])
        self.tcp: Optional[socket.socket] = None
        self._buf = ''   # line buffer for TCP stream

        self._stats = dict(cycles=0, matlab_timeouts=0,
                           modbus_errors=0, start_time=None)

    # ── TCP connection to MATLAB ────────────────────────────────────────────

    def _connect_matlab(self) -> bool:
        try:
            if self.tcp:
                try: self.tcp.close()
                except Exception: pass
            self.tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp.settimeout(self.TCP_TIMEOUT)
            self.tcp.connect((self.matlab_host, self.matlab_port))
            self._buf = ''
            log.info(f'TCP connected to MATLAB at '
                     f'{self.matlab_host}:{self.matlab_port}')
            return True
        except Exception as e:
            log.warning(f'Cannot connect to MATLAB TCP: {e}')
            self.tcp = None
            return False

    # ── Modbus helpers ──────────────────────────────────────────────────────

    def connect(self) -> bool:
        log.info(f'Connecting to CODESYS at {self.plc_host}:{self.plc_port}')
        if not self.mb.connect():
            log.error('Modbus connection failed')
            return False
        log.info(f'MATLAB physics server (TCP): '
                 f'{self.matlab_host}:{self.matlab_port}')
        return self._connect_matlab()

    def disconnect(self):
        self.mb.disconnect()
        if self.tcp:
            try: self.tcp.close()
            except Exception: pass
        log.info('Bridge disconnected')

    def read_actuators(self) -> Optional[dict]:
        max_coil = max(COIL_ADDR.values())
        bits = self.mb.read_coils(address=0, count=max_coil + 1)
        if bits is None:
            self._stats['modbus_errors'] += 1
            return None
        act = {name: bool(bits[addr]) for name, addr in COIL_ADDR.items()}

        valve_regs = ['MV_101','MV_201','MV_301','MV_302','MV_303','MV_304']
        max_reg = max(REG_ADDR[v] for v in valve_regs)
        regs = self.mb.read_holding_registers(address=0, count=max_reg + 1)
        if regs is not None:
            for v in valve_regs:
                act[v] = int(regs[REG_ADDR[v]])
        return act

    def write_sensors(self, sensors: dict) -> bool:
        max_addr  = max(REG_ADDR.values())
        reg_block = [0] * (max_addr + 1)
        for name, addr in REG_ADDR.items():
            if name in sensors:
                reg_block[addr] = max(0, min(65535, int(sensors[name])))
        ok = self.mb.write_multiple_registers(address=0, values=reg_block)
        if not ok:
            self._stats['modbus_errors'] += 1
        # Share latest sensors with ws_server — non-blocking
        try:
            shared_sensor_queue.put_nowait(sensors)
        except queue.Full:
            try:
                shared_sensor_queue.get_nowait()
                shared_sensor_queue.put_nowait(sensors)
            except queue.Empty:
                pass
        return ok

    # ── MATLAB call (TCP, newline-delimited) ────────────────────────────────

    def call_matlab(self, actuators: dict) -> Optional[dict]:
        if self.tcp is None:
            if not self._connect_matlab():
                return None

        try:
            payload = json.dumps(actuators) + '\n'
            self.tcp.sendall(payload.encode())

            # Read until newline
            deadline = time.time() + self.TCP_TIMEOUT
            while '\n' not in self._buf:
                remaining = deadline - time.time()
                if remaining <= 0:
                    log.warning('MATLAB response timeout')
                    self._stats['matlab_timeouts'] += 1
                    self.tcp = None
                    return None
                self.tcp.settimeout(remaining)
                chunk = self.tcp.recv(65536).decode(errors='replace')
                if not chunk:
                    log.warning('MATLAB closed connection')
                    self.tcp = None
                    return None
                self._buf += chunk

            line, self._buf = self._buf.split('\n', 1)
            return json.loads(line.strip())

        except socket.timeout:
            log.warning('MATLAB TCP timeout')
            self._stats['matlab_timeouts'] += 1
            self.tcp = None
            return None
        except (json.JSONDecodeError, OSError) as e:
            log.warning(f'MATLAB comm error: {e}')
            self.tcp = None
            self._buf = ''
            return None

    # ── Main loop ───────────────────────────────────────────────────────────

    def run(self):
        if not self.connect():
            return

        self._running = True
        self._stats['start_time'] = time.time()
        last_sensors: dict = {}
        log.info(f'Control loop running at {1/self.DT:.0f} Hz — '
                 f'press Ctrl+C to stop')

        try:
            while self._running:
                t0 = time.perf_counter()

                actuators = self.read_actuators()
                if actuators is None:
                    log.warning('Skipping cycle — Modbus read failed')
                    time.sleep(self.DT)
                    continue

                sensors = self.call_matlab(actuators)
                if sensors is None:
                    sensors = last_sensors

                if sensors:
                    self.write_sensors(sensors)
                    last_sensors = sensors

                self._stats['cycles'] += 1
                if self._stats['cycles'] % 100 == 0:
                    elapsed = time.time() - self._stats['start_time']
                    log.info(
                        f"cycles={self._stats['cycles']}  "
                        f"rate={self._stats['cycles']/elapsed:.1f}Hz  "
                        f"timeouts={self._stats['matlab_timeouts']}  "
                        f"mb_errors={self._stats['modbus_errors']}"
                    )

                elapsed_cycle = time.perf_counter() - t0
                time.sleep(max(0.0, self.DT - elapsed_cycle))

        except KeyboardInterrupt:
            log.info('Interrupted — shutting down')
        finally:
            self._running = False
            self.disconnect()
            self._print_stats()

    def stop(self): self._running = False

    def _print_stats(self):
        if not self._stats['start_time']: return
        e = time.time() - self._stats['start_time']
        log.info(
            f"=== Bridge stopped ===\n"
            f"  Runtime:   {e:.1f}s\n"
            f"  Cycles:    {self._stats['cycles']}\n"
            f"  Avg rate:  {self._stats['cycles']/max(1,e):.1f} Hz\n"
            f"  Timeouts:  {self._stats['matlab_timeouts']}\n"
            f"  MB errors: {self._stats['modbus_errors']}"
        )


def main():
    parser = argparse.ArgumentParser(description='MATLAB-CODESYS Physics Bridge')
    parser.add_argument('--plc-host',    default=MODBUS_CONFIG['host'])
    parser.add_argument('--plc-port',    type=int, default=MODBUS_CONFIG['port'])
    parser.add_argument('--matlab-host', default='127.0.0.1')
    parser.add_argument('--matlab-port', type=int, default=9501)
    args = parser.parse_args()

    bridge = MatlabPhysicsBridge(
        plc_host=args.plc_host,   plc_port=args.plc_port,
        matlab_host=args.matlab_host, matlab_port=args.matlab_port
    )

    def _sig(s, f): bridge.stop()
    signal.signal(signal.SIGINT,  _sig)
    signal.signal(signal.SIGTERM, _sig)
    bridge.run()


if __name__ == '__main__':
    main()