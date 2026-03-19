#!/usr/bin/env python3
"""
matlab_bridge/engine_bridge.py
================================
Alternative bridge using the MATLAB Engine API for Python.
Use this when MATLAB and Python run on the SAME machine — it avoids
the UDP hop and gives direct in-process calls.

Requirements:
    pip install matlabengine   (must match your MATLAB version)
    or run:  cd <matlabroot>/extern/engines/python && python setup.py install

Usage:
    python matlab_bridge/engine_bridge.py --plc-host 192.168.0.163
"""

import sys
import time
import logging
import signal
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from config.swat_config import MODBUS_CONFIG, COILS, HOLDING_REGISTERS
from utils.modbus_utils import ModbusClientOptimized as ModbusClient

log = logging.getLogger('MatlabEngineBridge')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

REG_ADDR  = {n: i['address'] for n, i in HOLDING_REGISTERS.items()}
COIL_ADDR = {n: i['address'] for n, i in COILS.items()}


class MatlabEngineBridge:
    """
    Calls MATLAB swat_physics_step() directly via the Engine API.
    The MATLAB function signature expected:
        sensors = swat_physics_step(actuators_struct, state_struct, dt)
        [sensors, state] = swat_physics_step(actuators_struct, state_struct, dt)
    """

    DT = 0.1

    def __init__(self, plc_host: str, plc_port: int, matlab_path: str):
        self.plc_host   = plc_host
        self.plc_port   = plc_port
        self.matlab_path = Path(matlab_path)
        self._running   = False
        self._eng       = None

        self.mb = ModbusClient(
            host=plc_host, port=plc_port,
            timeout=3, retries=3,
            unit_id=MODBUS_CONFIG['unit_id']
        )

    def _start_engine(self):
        log.info('Starting MATLAB engine (this may take 15-30 s)...')
        try:
            import matlab.engine
            self._eng = matlab.engine.start_matlab()
            self._eng.addpath(str(self.matlab_path), nargout=0)
            log.info('MATLAB engine ready')
        except ImportError:
            raise RuntimeError(
                'matlabengine not installed. '
                'Run: cd <matlabroot>/extern/engines/python && python setup.py install'
            )

    def _matlab_struct_from_dict(self, d: dict):
        """Convert Python dict to MATLAB struct via eng.workspace."""
        import matlab
        # Build as a single-element struct
        # Flatten into lists for matlab.engine compatibility
        return {k: (matlab.int32([int(v)]) if isinstance(v, (int, bool))
                    else matlab.double([float(v)]))
                for k, v in d.items()}

    def _dict_from_matlab_struct(self, ms) -> dict:
        """Extract Python dict from MATLAB struct returned by engine."""
        result = {}
        # matlab.engine returns structs as dicts when nargout=1
        if isinstance(ms, dict):
            for k, v in ms.items():
                try:
                    result[k] = int(list(v)[0]) if hasattr(v, '__iter__') else int(v)
                except (TypeError, ValueError):
                    result[k] = v
        return result

    def _run_step(self, actuators: dict) -> dict:
        """Call MATLAB swat_physics_step and return sensor dict."""
        import matlab
        # Pass actuator dict as a MATLAB struct
        act_m = {
            k: (matlab.logical([bool(v)]) if isinstance(v, bool)
                else matlab.int32([int(v)]))
            for k, v in actuators.items()
        }
        # call: [sensors] = swat_physics_step(act, dt)
        sensors_m = self._eng.swat_physics_step(act_m, self.DT, nargout=1)
        if isinstance(sensors_m, dict):
            return {k: int(v) if hasattr(v, '__iter__') else int(v)
                    for k, v in sensors_m.items()}
        return {}

    def read_actuators(self):
        max_coil = max(COIL_ADDR.values())
        bits = self.mb.read_coils(0, count=max_coil + 1)
        if bits is None:
            return None
        act = {name: bool(bits[addr]) for name, addr in COIL_ADDR.items()}

        # Valve positions (INT registers)
        for vname in ['MV_101', 'MV_201', 'MV_301', 'MV_302', 'MV_303', 'MV_304']:
            regs = self.mb.read_holding_registers(REG_ADDR[vname], count=1)
            if regs:
                act[vname] = int(regs[0])
        return act

    def write_sensors(self, sensors: dict):
        max_addr = max(REG_ADDR.values())
        block = [0] * (max_addr + 1)
        for name, addr in REG_ADDR.items():
            if name in sensors:
                block[addr] = max(0, min(65535, int(sensors[name])))
        return self.mb.write_multiple_registers(0, block)

    def run(self):
        self._start_engine()
        if not self.mb.connect():
            log.error('Modbus connection failed')
            return

        self._running = True
        last_sensors: dict = {}
        cycles = 0
        t_start = time.time()

        log.info(f'Engine bridge running at {1/self.DT:.0f} Hz')

        try:
            while self._running:
                t0 = time.perf_counter()

                actuators = self.read_actuators()
                if actuators is None:
                    time.sleep(self.DT)
                    continue

                try:
                    sensors = self._run_step(actuators)
                    last_sensors = sensors
                except Exception as e:
                    log.warning(f'MATLAB call failed: {e}')
                    sensors = last_sensors

                if sensors:
                    self.write_sensors(sensors)

                cycles += 1
                if cycles % 100 == 0:
                    hz = cycles / max(1, time.time() - t_start)
                    log.info(f'cycles={cycles}  rate={hz:.1f}Hz')

                time.sleep(max(0.0, self.DT - (time.perf_counter() - t0)))

        except KeyboardInterrupt:
            log.info('Interrupted')
        finally:
            self._running = False
            self.mb.disconnect()
            if self._eng:
                self._eng.quit()
            log.info('Engine bridge stopped')

    def stop(self):
        self._running = False


def main():
    parser = argparse.ArgumentParser(description='MATLAB Engine API Bridge')
    parser.add_argument('--plc-host',    default=MODBUS_CONFIG['host'])
    parser.add_argument('--plc-port',    type=int, default=MODBUS_CONFIG['port'])
    parser.add_argument('--matlab-path', default='matlab',
                        help='Path to folder containing swat_physics_step.m')
    args = parser.parse_args()

    bridge = MatlabEngineBridge(args.plc_host, args.plc_port, args.matlab_path)
    for s in (signal.SIGINT, signal.SIGTERM):
        signal.signal(s, lambda *_: bridge.stop())
    bridge.run()


if __name__ == '__main__':
    main()
