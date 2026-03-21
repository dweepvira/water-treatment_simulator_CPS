# #!/usr/bin/env python3
# """
# matlab_bridge/physics_client.py
# ================================
# Runs the main control loop that glues MATLAB physics to CODESYS,
# with integrated CSV logging after every CODESYS write cycle.

# Loop (every DT seconds — atomic, guaranteed ordering):
#   1. Read all coil states from CODESYS via Modbus FC1
#   2. Send actuator JSON to MATLAB TCP server
#   3. Receive sensor JSON response (physics computed)
#   4. Write sensor registers back to CODESYS via Modbus FC16
#   5. Log one CSV row (sensors + actuators + attack label + timestamp)
#      → Logging happens AFTER write, so every row reflects post-physics state

# Usage:
#     python matlab_bridge/physics_client.py \\
#         --plc-host 192.168.5.195 --plc-port 1502 \\
#         --output run_01/master_dataset.csv \\
#         --metadata-file run_01/attack_metadata.json

#     # With attack label injection (from attack orchestrator):
#     # Write {"ATTACK_ID": 13, "ATTACK_NAME": "Reconnaissance Scan",
#     #         "MITRE_ID": "T0840"} to metadata-file at attack start.
#     # Bridge reads it every 100 ms and stamps each CSV row.
# """

# import csv
# import json
# import os
# import socket
# import time
# import logging
# import argparse
# import sys
# import signal
# from datetime import datetime, timezone
# from pathlib import Path
# from typing import Optional

# sys.path.append(str(Path(__file__).parent.parent))

# from config.swat_config import MODBUS_CONFIG, COILS, HOLDING_REGISTERS
# from utils.modbus_utils import ModbusClientOptimized as ModbusClient

# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s [%(levelname)s] %(message)s'
# )
# log = logging.getLogger('MatlabBridge')

# # ── Address maps ────────────────────────────────────────────────────────────
# REG_ADDR  = {name: info['address'] for name, info in HOLDING_REGISTERS.items()}
# COIL_ADDR = {name: info['address'] for name, info in COILS.items()}

# # Ordered column names for CSV (sensors first, then coils, then labels)
# SENSOR_COLS = [name for name, _ in sorted(REG_ADDR.items(),  key=lambda x: x[1])]
# COIL_COLS   = [name for name, _ in sorted(COIL_ADDR.items(), key=lambda x: x[1])]
# CSV_COLUMNS = ['Timestamp'] + SENSOR_COLS + COIL_COLS + ['ATTACK_ID', 'ATTACK_NAME', 'MITRE_ID']


# # ── CSV Logger ───────────────────────────────────────────────────────────────
# SCALE_MAP = {
#     'FIT_101':0.1,'FIT_201':0.1,'FIT_301':0.1,'FIT_401':0.1,
#     'FIT_501':0.1,'FIT_502':0.1,'FIT_503':0.1,'FIT_504':0.1,'FIT_601':0.1,
#     'DPIT_301':0.1,'PIT_501':0.1,'PIT_502':0.1,'PIT_503':0.1,
#     'AIT_202':0.01,'Chlorine_Residual':0.1,
#     'Water_Temperature':0.1,'Ambient_Temperature':0.1,
# }
# class CSVLogger:
#     """
#     Lightweight synchronous CSV logger.
#     Opens file in append mode so restarts don't lose data.
#     Flushes every flush_interval rows to avoid data loss on crash.
#     """

#     def __init__(self, filepath: str, flush_interval: int = 10):
#         self.filepath       = Path(filepath)
#         self.flush_interval = flush_interval
#         self._row_count     = 0
#         self.filepath.parent.mkdir(parents=True, exist_ok=True)

#         # Write header only if file is new / empty
#         write_header = not self.filepath.exists() or self.filepath.stat().st_size == 0
#         self._fh = open(self.filepath, 'a', newline='', encoding='utf-8')
#         self._writer = csv.DictWriter(self._fh, fieldnames=CSV_COLUMNS,
#                                       extrasaction='ignore')
#         if write_header:
#             self._writer.writeheader()
#             self._fh.flush()
#         log.info(f'CSV logger → {self.filepath}  ({"new file" if write_header else "append mode"})')

#     def write(self, row: dict) -> None:
#         self._writer.writerow(row)
#         for col, scale in SCALE_MAP.items():
#             if col in row:
#                 row[col] = round(row[col] * scale, 3)
#         self._row_count += 1
#         if self._row_count % self.flush_interval == 0:
#             self._fh.flush()

#     def close(self) -> None:
#         self._fh.flush()
#         self._fh.close()
#         log.info(f'CSV closed — {self._row_count} rows written to {self.filepath}')


# # ── Attack metadata reader ───────────────────────────────────────────────────

# class AttackMetadataReader:
#     """
#     Reads attack label from a JSON file written by the attack orchestrator.
#     File format: {"ATTACK_ID": 13, "ATTACK_NAME": "Reconnaissance Scan", "MITRE_ID": "T0840"}
#     Normal operation: {"ATTACK_ID": 0, "ATTACK_NAME": "Normal", "MITRE_ID": "T0"}
#     Re-reads every read_interval cycles to pick up attack start/end.
#     """

#     NORMAL = {'ATTACK_ID': 0, 'ATTACK_NAME': 'Normal', 'MITRE_ID': 'T0'}

#     def __init__(self, filepath: Optional[str], read_interval: int = 5):
#         self.filepath      = Path(filepath) if filepath else None
#         self.read_interval = read_interval
#         self._current      = dict(self.NORMAL)
#         self._last_read    = 0
#         self._last_label   = 'Normal'

#     def get(self, cycle: int) -> dict:
#         """Return current attack label, re-reading file every read_interval cycles."""
#         if self.filepath is None:
#             return dict(self.NORMAL)

#         if cycle - self._last_read >= self.read_interval:
#             self._last_read = cycle
#             try:
#                 raw = self.filepath.read_text(encoding='utf-8').strip()
#                 if raw:
#                     data = json.loads(raw)
#                     self._current = {
#                         'ATTACK_ID':   data.get('ATTACK_ID',   0),
#                         'ATTACK_NAME': data.get('ATTACK_NAME', 'Normal'),
#                         'MITRE_ID':    data.get('MITRE_ID',    'T0'),
#                     }
#                     if self._current['ATTACK_NAME'] != self._last_label:
#                         log.info(f"Attack label → {self._current['ATTACK_NAME']} "
#                                  f"(ID={self._current['ATTACK_ID']})")
#                         self._last_label = self._current['ATTACK_NAME']
#             except (FileNotFoundError, json.JSONDecodeError):
#                 self._current = dict(self.NORMAL)

#         return dict(self._current)

# MV_NAMES = {'MV_101','MV_201','MV_301','MV_302','MV_303','MV_304'}
# # ── Main bridge ──────────────────────────────────────────────────────────────

# class MatlabPhysicsBridge:
#     """
#     Bridges CODESYS ↔ MATLAB over Modbus TCP + TCP, with integrated CSV logging.

#     Cycle ordering (atomic per row):
#         read_actuators() → call_matlab() → write_sensors() → log_row()

#     Every CSV row is therefore guaranteed to contain:
#         - Sensor values that CODESYS has already received
#         - Coil values that were used to produce those sensor values
#         - The correct attack label at that moment
#     """

#     DT          = 0.1    # seconds per cycle (10 Hz)
#     TCP_TIMEOUT = 0.5    # max wait for MATLAB response

#     def __init__(self,
#                  plc_host:      str,
#                  plc_port:      int  = 1502,
#                  matlab_host:   str  = '127.0.0.1',
#                  matlab_port:   int  = 9501,
#                  output_csv:    Optional[str] = None,
#                  metadata_file: Optional[str] = None,
#                  total_minutes: Optional[int] = None):

#         self.plc_host    = plc_host
#         self.plc_port    = plc_port
#         self.matlab_host = matlab_host
#         self.matlab_port = matlab_port
#         self._running    = False
#         self.total_minutes = total_minutes

#         # Modbus
#         self.mb = ModbusClient(
#             host=plc_host, port=plc_port,
#             timeout=3, retries=3,
#             unit_id=MODBUS_CONFIG['unit_id']
#         )

#         # TCP socket for MATLAB
#         self.tcp: Optional[socket.socket] = None
#         self._buf = ''

#         # CSV logger (None = logging disabled)
#         self.csv_logger = CSVLogger(output_csv) if output_csv else None

#         # Attack label reader
#         self.attack_meta = AttackMetadataReader(metadata_file)

#         self._stats = dict(cycles=0, matlab_timeouts=0,
#                            modbus_errors=0, rows_logged=0, start_time=None)

#     # ── TCP connection to MATLAB ────────────────────────────────────────────

#     def _connect_matlab(self) -> bool:
#         try:
#             if self.tcp:
#                 try: self.tcp.close()
#                 except Exception: pass
#             self.tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#             self.tcp.settimeout(self.TCP_TIMEOUT)
#             self.tcp.connect((self.matlab_host, self.matlab_port))
#             self._buf = ''
#             log.info(f'TCP connected to MATLAB at {self.matlab_host}:{self.matlab_port}')
#             return True
#         except Exception as e:
#             log.warning(f'Cannot connect to MATLAB TCP: {e}')
#             self.tcp = None
#             return False

#     # ── Modbus helpers ──────────────────────────────────────────────────────

#     def connect(self) -> bool:
#         log.info(f'Connecting to CODESYS at {self.plc_host}:{self.plc_port}')
#         if not self.mb.connect():
#             log.error('Modbus connection failed')
#             return False
#         log.info(f'MATLAB physics server (TCP): {self.matlab_host}:{self.matlab_port}')
#         return self._connect_matlab()

#     def disconnect(self):
#         self.mb.disconnect()
#         if self.tcp:
#             try: self.tcp.close()
#             except Exception: pass
#         if self.csv_logger:
#             self.csv_logger.close()
#         log.info('Bridge disconnected')

#     def read_actuators(self) -> Optional[dict]:
#         """Read coil + MV register state from CODESYS."""
#         max_coil = max(COIL_ADDR.values())
#         bits = self.mb.read_coils(address=0, count=max_coil + 1)
#         if bits is None:
#             self._stats['modbus_errors'] += 1
#             return None

#         act = {name: bool(bits[addr]) for name, addr in COIL_ADDR.items()}

#         valve_regs = ['MV_101', 'MV_201', 'MV_301', 'MV_302', 'MV_303', 'MV_304']
#         max_reg = max(REG_ADDR[v] for v in valve_regs)
#         regs = self.mb.read_holding_registers(address=0, count=max_reg + 1)
#         if regs is not None:
#             for v in valve_regs:
#                 act[v] = int(regs[REG_ADDR[v]])
#         return act

#     def call_matlab(self, actuators: dict) -> Optional[dict]:
#         """Send actuator JSON to MATLAB TCP; return sensor JSON."""
#         if self.tcp is None:
#             if not self._connect_matlab():
#                 return None
#         try:
#             payload = json.dumps(actuators) + '\n'
#             self.tcp.sendall(payload.encode())

#             deadline = time.time() + self.TCP_TIMEOUT
#             while '\n' not in self._buf:
#                 remaining = deadline - time.time()
#                 if remaining <= 0:
#                     log.warning('MATLAB response timeout — using last good values')
#                     self._stats['matlab_timeouts'] += 1
#                     self.tcp = None
#                     return None
#                 self.tcp.settimeout(remaining)
#                 chunk = self.tcp.recv(65536).decode(errors='replace')
#                 if not chunk:
#                     log.warning('MATLAB closed connection')
#                     self.tcp = None
#                     return None
#                 self._buf += chunk

#             line, self._buf = self._buf.split('\n', 1)
#             return json.loads(line.strip())

#         except socket.timeout:
#             log.warning('MATLAB TCP timeout')
#             self._stats['matlab_timeouts'] += 1
#             self.tcp = None
#             return None
#         except (json.JSONDecodeError, OSError) as e:
#             log.warning(f'MATLAB comm error: {e}')
#             self.tcp = None
#             self._buf = ''
#             return None

    

#     def write_sensors(self, sensors: dict, actuators: dict = None) -> bool:
#         max_addr  = max(REG_ADDR.values())
#         reg_block = [0] * (max_addr + 1)
#         for name, addr in REG_ADDR.items():
#             if name in MV_NAMES:
#                 # CODESYS owns these — preserve what we just read
#                 if actuators and name in actuators:
#                     reg_block[addr] = int(actuators[name])
#             elif name in sensors:
#                 reg_block[addr] = max(0, min(65535, int(sensors[name])))
#         ok = self.mb.write_multiple_registers(address=0, values=reg_block)
#         if not ok:
#             self._stats['modbus_errors'] += 1
#         return ok

#     def log_row(self, sensors: dict, actuators: dict, cycle: int) -> None:
#         """
#         Write one CSV row.
#         Called AFTER write_sensors() so values are already in CODESYS.
#         Row = timestamp + all sensor registers + all coil states + attack label.
#         """
#         if self.csv_logger is None:
#             return

#         label = self.attack_meta.get(cycle)

#         row = {'Timestamp': datetime.now(timezone.utc).isoformat()}

#         # Sensor registers (scaled integers from MATLAB)
#         MV_REGS = {'MV_101','MV_201','MV_301','MV_302','MV_303','MV_304'}

#         for name in SENSOR_COLS:
#             if name in MV_REGS:
#                 row[name] = actuators.get(name, 0)   # ← from Modbus read
#             else:
#                 row[name] = sensors.get(name, 0)  # ← from MATLAB response

#         # Coil states (booleans from CODESYS ST logic)
#         for name in COIL_COLS:
#             row[name] = actuators.get(name, False)

#         # Attack label
#         row.update(label)
#         for col, scale in SCALE_MAP.items():
#             if col in row: row[col] = round(row[col] * scale, 3)


#         self.csv_logger.write(row)
#         self._stats['rows_logged'] += 1

#     # ── Main loop ───────────────────────────────────────────────────────────

#     def run(self):
#         if not self.connect():
#             return

#         self._running = True
#         self._stats['start_time'] = time.time()
#         last_sensors: dict = {}

#         log.info(f'Control loop running at {1/self.DT:.0f} Hz')
#         if self.csv_logger:
#             log.info(f'Logging to: {self.csv_logger.filepath}')
#         else:
#             log.info('CSV logging disabled (no --output specified)')

#         try:
#             while self._running:
#                 t0 = time.perf_counter()

#                 # 1. Read actuators from CODESYS
#                 actuators = self.read_actuators()
#                 if actuators is None:
#                     log.warning('Skipping cycle — Modbus read failed')
#                     time.sleep(self.DT)
#                     continue

#                 # 2. Call MATLAB physics
#                 sensors = self.call_matlab(actuators)
#                 if sensors is None:
#                     sensors = last_sensors   # hold last known good

#                 # 3. Write sensors to CODESYS
#                 if sensors:
#                     self.write_sensors(sensors,actuators)
#                     last_sensors = sensors

#                     # 4. Log AFTER write — row reflects post-physics CODESYS state
#                     self.log_row(sensors, actuators, self._stats['cycles'])

#                 self._stats['cycles'] += 1

#                 if self.total_minutes:
#                     elapsed_min = (time.time() - self._stats['start_time']) / 60
#                     if elapsed_min >= self.total_minutes:
#                         log.info(f'Total time limit reached ({self.total_minutes} min) — stopping.')
#                         break

#                 # 5. Status every 100 cycles
#                 if self._stats['cycles'] % 100 == 0:
#                     elapsed = time.time() - self._stats['start_time']
#                     log.info(
#                         f"cycles={self._stats['cycles']}  "
#                         f"rate={self._stats['cycles']/elapsed:.1f}Hz  "
#                         f"rows={self._stats['rows_logged']}  "
#                         f"timeouts={self._stats['matlab_timeouts']}  "
#                         f"mb_errors={self._stats['modbus_errors']}"
#                     )

#                 # 6. Sleep remainder of DT
#                 elapsed_cycle = time.perf_counter() - t0
#                 time.sleep(max(0.0, self.DT - elapsed_cycle))

#         except KeyboardInterrupt:
#             log.info('Interrupted — shutting down')
#         finally:
#             self._running = False
#             self.disconnect()
#             self._print_final_stats()

#     def stop(self):
#         self._running = False

#     def _print_final_stats(self):
#         if self._stats['start_time'] is None:
#             return
#         elapsed = time.time() - self._stats['start_time']
#         log.info(
#             f"=== Bridge stopped ===\n"
#             f"  Runtime:    {elapsed:.1f}s\n"
#             f"  Cycles:     {self._stats['cycles']}\n"
#             f"  Avg rate:   {self._stats['cycles']/max(1,elapsed):.1f} Hz\n"
#             f"  Rows logged:{self._stats['rows_logged']}\n"
#             f"  Timeouts:   {self._stats['matlab_timeouts']}\n"
#             f"  MB errors:  {self._stats['modbus_errors']}"
#         )


# # ── CLI ──────────────────────────────────────────────────────────────────────

# def main():
#     parser = argparse.ArgumentParser(description='MATLAB-CODESYS Physics Bridge with CSV Logging')
#     parser.add_argument('--plc-host',      default=MODBUS_CONFIG['host'])
#     parser.add_argument('--plc-port',      type=int, default=MODBUS_CONFIG['port'])
#     parser.add_argument('--matlab-host',   default='127.0.0.1')
#     parser.add_argument('--matlab-port',   type=int, default=9501)
#     parser.add_argument('--output',        default=None,
#                         metavar='CSV_PATH',
#                         help='Output CSV file path. e.g. run_01/master_dataset.csv')
#     parser.add_argument('--metadata-file', default=None,
#                         metavar='JSON_PATH',
#                         help='Attack metadata JSON written by attack orchestrator. '
#                              'e.g. run_01/attack_metadata.json')
#     parser.add_argument('--total-minutes', type=int, default=None,
#                     help='Hard stop after N minutes (failsafe)')
#     args = parser.parse_args()

#     bridge = MatlabPhysicsBridge(
#         plc_host=args.plc_host,
#         plc_port=args.plc_port,
#         matlab_host=args.matlab_host,
#         matlab_port=args.matlab_port,
#         output_csv=args.output,
#         metadata_file=args.metadata_file,
#         total_minutes=args.total_minutes
#     )

#     def _sig(s, f): bridge.stop()
#     signal.signal(signal.SIGINT,  _sig)
#     signal.signal(signal.SIGTERM, _sig)

#     bridge.run()


# if __name__ == '__main__':
#     main()

#!/usr/bin/env python3
"""
matlab_bridge/physics_client.py
================================
Runs the main control loop that glues MATLAB physics to CODESYS,
with integrated CSV logging after every CODESYS write cycle.

Loop (every DT seconds — atomic, guaranteed ordering):
  1. Read all coil states from CODESYS via Modbus FC1
  2. Send actuator JSON to MATLAB TCP server
  3. Receive sensor JSON response (physics computed)
  4. Write sensor registers back to CODESYS via Modbus FC16
  5. Log one CSV row (sensors + actuators + attack label + timestamp)
     → Logging happens AFTER write, so every row reflects post-physics state

Usage:
    python matlab_bridge/physics_client.py \\
        --plc-host 192.168.5.195 --plc-port 1502 \\
        --output run_01/master_dataset.csv \\
        --metadata-file run_01/attack_metadata.json

    # With attack label injection (from attack orchestrator):
    # Write {"ATTACK_ID": 13, "ATTACK_NAME": "Reconnaissance Scan",
    #         "MITRE_ID": "T0840"} to metadata-file at attack start.
    # Bridge reads it every 100 ms and stamps each CSV row.
"""

import csv
import json
import os
import socket
import time
import logging
import argparse
import sys
import signal
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.append(str(Path(__file__).parent.parent))

from config.swat_config import MODBUS_CONFIG, COILS, HOLDING_REGISTERS
from utils.modbus_utils import ModbusClientOptimized as ModbusClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
log = logging.getLogger('MatlabBridge')

# ── Address maps ────────────────────────────────────────────────────────────
REG_ADDR  = {name: info['address'] for name, info in HOLDING_REGISTERS.items()}
COIL_ADDR = {name: info['address'] for name, info in COILS.items()}

# Ordered column names for CSV (sensors first, then coils, then labels)
SENSOR_COLS = [name for name, _ in sorted(REG_ADDR.items(),  key=lambda x: x[1])]
COIL_COLS   = [name for name, _ in sorted(COIL_ADDR.items(), key=lambda x: x[1])]
CSV_COLUMNS = ['Timestamp'] + SENSOR_COLS + COIL_COLS + ['ATTACK_ID', 'ATTACK_NAME', 'MITRE_ID']


# ── CSV Logger ───────────────────────────────────────────────────────────────
SCALE_MAP = {
    'FIT_101':0.1,'FIT_201':0.1,'FIT_301':0.1,'FIT_401':0.1,
    'FIT_501':0.1,'FIT_502':0.1,'FIT_503':0.1,'FIT_504':0.1,'FIT_601':0.1,
    'DPIT_301':0.1,'PIT_501':0.1,'PIT_502':0.1,'PIT_503':0.1,
    'AIT_202':0.01,'Chlorine_Residual':0.1,
    'Water_Temperature':0.1,'Ambient_Temperature':0.1,
}
class CSVLogger:
    """
    Lightweight synchronous CSV logger.
    Opens file in append mode so restarts don't lose data.
    Flushes every flush_interval rows to avoid data loss on crash.
    """

    def __init__(self, filepath: str, flush_interval: int = 10):
        self.filepath       = Path(filepath)
        self.flush_interval = flush_interval
        self._row_count     = 0
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

        # Write header only if file is new / empty
        write_header = not self.filepath.exists() or self.filepath.stat().st_size == 0
        self._fh = open(self.filepath, 'a', newline='', encoding='utf-8')
        self._writer = csv.DictWriter(self._fh, fieldnames=CSV_COLUMNS,
                                      extrasaction='ignore')
        if write_header:
            self._writer.writeheader()
            self._fh.flush()
        log.info(f'CSV logger → {self.filepath}  ({"new file" if write_header else "append mode"})')

    def write(self, row: dict) -> None:
        # SCALE_MAP applied once in log_row() before this call — do NOT reapply here
        self._writer.writerow(row)
        self._row_count += 1
        if self._row_count % self.flush_interval == 0:
            self._fh.flush()

    def close(self) -> None:
        self._fh.flush()
        self._fh.close()
        log.info(f'CSV closed — {self._row_count} rows written to {self.filepath}')


# ── Attack metadata reader ───────────────────────────────────────────────────

class AttackMetadataReader:
    """
    Reads attack label from a JSON file written by the attack orchestrator.
    File format: {"ATTACK_ID": 13, "ATTACK_NAME": "Reconnaissance Scan", "MITRE_ID": "T0840"}
    Normal operation: {"ATTACK_ID": 0, "ATTACK_NAME": "Normal", "MITRE_ID": "T0"}
    Re-reads every read_interval cycles to pick up attack start/end.
    """

    NORMAL = {'ATTACK_ID': 0, 'ATTACK_NAME': 'Normal', 'MITRE_ID': 'T0'}

    def __init__(self, filepath: Optional[str], read_interval: int = 5):
        self.filepath      = Path(filepath) if filepath else None
        self.read_interval = read_interval
        self._current      = dict(self.NORMAL)
        self._last_read    = 0
        self._last_label   = 'Normal'

    def get(self, cycle: int) -> dict:
        """Return current attack label, re-reading file every read_interval cycles."""
        if self.filepath is None:
            return dict(self.NORMAL)

        if cycle - self._last_read >= self.read_interval:
            self._last_read = cycle
            try:
                raw = self.filepath.read_text(encoding='utf-8').strip()
                if raw:
                    data = json.loads(raw)
                    self._current = {
                        'ATTACK_ID':   data.get('ATTACK_ID',   0),
                        'ATTACK_NAME': data.get('ATTACK_NAME', 'Normal'),
                        'MITRE_ID':    data.get('MITRE_ID',    'T0'),
                    }
                    if self._current['ATTACK_NAME'] != self._last_label:
                        log.info(f"Attack label → {self._current['ATTACK_NAME']} "
                                 f"(ID={self._current['ATTACK_ID']})")
                        self._last_label = self._current['ATTACK_NAME']
            except (FileNotFoundError, json.JSONDecodeError):
                self._current = dict(self.NORMAL)

        return dict(self._current)


# ── Main bridge ──────────────────────────────────────────────────────────────

class MatlabPhysicsBridge:
    """
    Bridges CODESYS ↔ MATLAB over Modbus TCP + TCP, with integrated CSV logging.

    Cycle ordering (atomic per row):
        read_actuators() → call_matlab() → write_sensors() → log_row()

    Every CSV row is therefore guaranteed to contain:
        - Sensor values that CODESYS has already received
        - Coil values that were used to produce those sensor values
        - The correct attack label at that moment
    """

    DT          = 0.1    # seconds per cycle (10 Hz)
    TCP_TIMEOUT = 0.5    # max wait for MATLAB response

    def __init__(self,
                 plc_host:      str,
                 plc_port:      int  = 1502,
                 matlab_host:   str  = '127.0.0.1',
                 matlab_port:   int  = 9501,
                 output_csv:    Optional[str] = None,
                 metadata_file: Optional[str] = None,
                 total_minutes: Optional[int] = None):

        self.plc_host    = plc_host
        self.plc_port    = plc_port
        self.matlab_host = matlab_host
        self.matlab_port = matlab_port
        self._running    = False
        self.total_minutes = total_minutes

        # Modbus
        self.mb = ModbusClient(
            host=plc_host, port=plc_port,
            timeout=3, retries=3,
            unit_id=MODBUS_CONFIG['unit_id']
        )

        # TCP socket for MATLAB
        self.tcp: Optional[socket.socket] = None
        self._buf = ''

        # CSV logger (None = logging disabled)
        self.csv_logger = CSVLogger(output_csv) if output_csv else None

        # Attack label reader
        self.attack_meta = AttackMetadataReader(metadata_file)

        self._stats = dict(cycles=0, matlab_timeouts=0,
                           modbus_errors=0, rows_logged=0, start_time=None)

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
            log.info(f'TCP connected to MATLAB at {self.matlab_host}:{self.matlab_port}')
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
        log.info(f'MATLAB physics server (TCP): {self.matlab_host}:{self.matlab_port}')
        return self._connect_matlab()

    def disconnect(self):
        self.mb.disconnect()
        if self.tcp:
            try: self.tcp.close()
            except Exception: pass
        if self.csv_logger:
            self.csv_logger.close()
        log.info('Bridge disconnected')

    def read_actuators(self) -> Optional[dict]:
        """Read coil + MV register state from CODESYS."""
        max_coil = max(COIL_ADDR.values())
        bits = self.mb.read_coils(address=0, count=max_coil + 1)
        if bits is None:
            self._stats['modbus_errors'] += 1
            return None

        act = {name: bool(bits[addr]) for name, addr in COIL_ADDR.items()}

        valve_regs = ['MV_101', 'MV_201', 'MV_301', 'MV_302', 'MV_303', 'MV_304']
        max_reg = max(REG_ADDR[v] for v in valve_regs)
        regs = self.mb.read_holding_registers(address=0, count=max_reg + 1)
        if regs is not None:
            for v in valve_regs:
                act[v] = int(regs[REG_ADDR[v]])
        return act

    def call_matlab(self, actuators: dict) -> Optional[dict]:
        """Send actuator JSON to MATLAB TCP; return sensor JSON."""
        if self.tcp is None:
            if not self._connect_matlab():
                return None
        try:
            payload = json.dumps(actuators) + '\n'
            self.tcp.sendall(payload.encode())

            deadline = time.time() + self.TCP_TIMEOUT
            while '\n' not in self._buf:
                remaining = deadline - time.time()
                if remaining <= 0:
                    log.warning('MATLAB response timeout — using last good values')
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

    # MV registers are set by CODESYS ST logic — MATLAB never outputs them.
    # We must preserve whatever CODESYS wrote rather than overwriting with 0.
    MV_REGS = {'MV_101', 'MV_201', 'MV_301', 'MV_302', 'MV_303', 'MV_304'}

    def write_sensors(self, sensors: dict, actuators: dict = None) -> bool:
        """Write MATLAB sensor output to CODESYS holding registers (bulk FC16).
        MV registers are preserved from the actuators read — MATLAB does not own them.
        """
        max_addr  = max(REG_ADDR.values())
        reg_block = [0] * (max_addr + 1)
        for name, addr in REG_ADDR.items():
            if name in self.MV_REGS:
                # Preserve CODESYS value — do NOT overwrite with 0
                if actuators and name in actuators:
                    reg_block[addr] = int(actuators[name])
            elif name in sensors:
                reg_block[addr] = max(0, min(65535, int(sensors[name])))
        ok = self.mb.write_multiple_registers(address=0, values=reg_block)
        if not ok:
            self._stats['modbus_errors'] += 1
        return ok

    def log_row(self, sensors: dict, actuators: dict, cycle: int) -> None:
        """
        Write one CSV row.
        Called AFTER write_sensors() so values are already in CODESYS.
        Row = timestamp + all sensor registers + all coil states + attack label.
        """
        if self.csv_logger is None:
            return

        label = self.attack_meta.get(cycle)

        row = {'Timestamp': datetime.now(timezone.utc).isoformat()}

        # Sensor registers (scaled integers from MATLAB)
        MV_REGS = {'MV_101','MV_201','MV_301','MV_302','MV_303','MV_304'}

        for name in SENSOR_COLS:
            if name in MV_REGS:
                row[name] = actuators.get(name, 0)   # ← from Modbus read
            else:
                row[name] = sensors.get(name, 0)  # ← from MATLAB response

        # Coil states (booleans from CODESYS ST logic)
        for name in COIL_COLS:
            row[name] = actuators.get(name, False)

        # Attack label
        row.update(label)
        for col, scale in SCALE_MAP.items():
            if col in row: row[col] = round(row[col] * scale, 3)


        self.csv_logger.write(row)
        self._stats['rows_logged'] += 1

    # ── Main loop ───────────────────────────────────────────────────────────

    def run(self):
        if not self.connect():
            return

        self._running = True
        self._stats['start_time'] = time.time()
        last_sensors: dict = {}

        log.info(f'Control loop running at {1/self.DT:.0f} Hz')
        if self.csv_logger:
            log.info(f'Logging to: {self.csv_logger.filepath}')
        else:
            log.info('CSV logging disabled (no --output specified)')

        try:
            while self._running:
                t0 = time.perf_counter()

                # 1. Read actuators from CODESYS
                actuators = self.read_actuators()
                if actuators is None:
                    log.warning('Skipping cycle — Modbus read failed')
                    time.sleep(self.DT)
                    continue

                # 2. Call MATLAB physics
                sensors = self.call_matlab(actuators)
                if sensors is None:
                    sensors = last_sensors   # hold last known good

                # 3. Write sensors to CODESYS — preserve MV values from actuators
                if sensors:
                    self.write_sensors(sensors, actuators)
                    last_sensors = sensors

                    # 4. Log AFTER write — row reflects post-physics CODESYS state
                    self.log_row(sensors, actuators, self._stats['cycles'])

                self._stats['cycles'] += 1

                if self.total_minutes:
                    elapsed_min = (time.time() - self._stats['start_time']) / 60
                    if elapsed_min >= self.total_minutes:
                        log.info(f'Total time limit reached ({self.total_minutes} min) — stopping.')
                        break

                # 5. Status every 100 cycles
                if self._stats['cycles'] % 100 == 0:
                    elapsed = time.time() - self._stats['start_time']
                    log.info(
                        f"cycles={self._stats['cycles']}  "
                        f"rate={self._stats['cycles']/elapsed:.1f}Hz  "
                        f"rows={self._stats['rows_logged']}  "
                        f"timeouts={self._stats['matlab_timeouts']}  "
                        f"mb_errors={self._stats['modbus_errors']}"
                    )

                # 6. Sleep remainder of DT
                elapsed_cycle = time.perf_counter() - t0
                time.sleep(max(0.0, self.DT - elapsed_cycle))

        except KeyboardInterrupt:
            log.info('Interrupted — shutting down')
        finally:
            self._running = False
            self.disconnect()
            self._print_final_stats()

    def stop(self):
        self._running = False

    def _print_final_stats(self):
        if self._stats['start_time'] is None:
            return
        elapsed = time.time() - self._stats['start_time']
        log.info(
            f"=== Bridge stopped ===\n"
            f"  Runtime:    {elapsed:.1f}s\n"
            f"  Cycles:     {self._stats['cycles']}\n"
            f"  Avg rate:   {self._stats['cycles']/max(1,elapsed):.1f} Hz\n"
            f"  Rows logged:{self._stats['rows_logged']}\n"
            f"  Timeouts:   {self._stats['matlab_timeouts']}\n"
            f"  MB errors:  {self._stats['modbus_errors']}"
        )


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='MATLAB-CODESYS Physics Bridge with CSV Logging')
    parser.add_argument('--plc-host',      default=MODBUS_CONFIG['host'])
    parser.add_argument('--plc-port',      type=int, default=MODBUS_CONFIG['port'])
    parser.add_argument('--matlab-host',   default='127.0.0.1')
    parser.add_argument('--matlab-port',   type=int, default=9501)
    parser.add_argument('--output',        default=None,
                        metavar='CSV_PATH',
                        help='Output CSV file path. e.g. run_01/master_dataset.csv')
    parser.add_argument('--metadata-file', default=None,
                        metavar='JSON_PATH',
                        help='Attack metadata JSON written by attack orchestrator. '
                             'e.g. run_01/attack_metadata.json')
    parser.add_argument('--total-minutes', type=int, default=None,
                    help='Hard stop after N minutes (failsafe)')
    args = parser.parse_args()

    bridge = MatlabPhysicsBridge(
        plc_host=args.plc_host,
        plc_port=args.plc_port,
        matlab_host=args.matlab_host,
        matlab_port=args.matlab_port,
        output_csv=args.output,
        metadata_file=args.metadata_file,
        total_minutes=args.total_minutes
    )

    def _sig(s, f): bridge.stop()
    signal.signal(signal.SIGINT,  _sig)
    signal.signal(signal.SIGTERM, _sig)

    bridge.run()


if __name__ == '__main__':
    main()