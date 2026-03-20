#!/usr/bin/env python3
"""
start_system.py
================
Launches the full MATLAB-Python-CODESYS stack with optional run-based
attack dataset collection.

Start order:
  1. Verify CODESYS is reachable via Modbus (must already be running)
  2. Launch MATLAB physics server  (subprocess: matlab -batch swat_physics_server)
  3. Wait for MATLAB to bind UDP port 9501
  4. Launch physics bridge         (subprocess: physics_client.py)
  5. Launch data logger            (subprocess: data_logger.py)
  6. Launch attack injector        (subprocess: automated_dataset_generator.py)
  7. Auto-stop after --total minutes (if specified)

Basic usage:
    python start_system.py --host 192.168.5.195 --port 1502 \\
        --matlab-path "C:\\path\\to\\m\\files" --reuse-existing-matlab

Run-based dataset collection (same style as automated_dataset_generator.py):
    python start_system.py --host 192.168.5.195 --port 1502 \\
        --matlab-path "C:\\path\\to\\m\\files" --reuse-existing-matlab \\
        --output run_01 --total 70 --attack 30 \\
        --include-attacks reconnaissance,replay,ph_manipulation,slow_ramp

    python start_system.py --host 192.168.5.195 --port 1502 \\
        --matlab-path "C:\\path\\to\\m\\files" --reuse-existing-matlab \\
        --output run_02 --total 70 --attack 30 \\
        --include-attacks pump_failure,valve_manipulation,multi_stage

    (Repeat for run_03 ... run_05 with different --include-attacks)

Output structure per run:
    run_01/
      master_dataset.csv      ← logged sensor + coil data
      attack_metadata.json    ← attack timestamps and labels

Windows note:
    matlab.exe always opens a new console window and the launching process
    exits immediately with code 0.  This script handles that by:
      - Using CREATE_NO_WINDOW so MATLAB runs hidden in the background.
      - Never treating early exit-code-0 as failure during the startup wait.
    If probes are blocked on loopback, run once as Administrator:
      netsh advfirewall firewall add rule name="MATLAB UDP 9501" ^
            protocol=UDP dir=in localport=9501 action=allow
"""

import sys
import time
import json
import socket
import argparse
import subprocess
import signal
import platform
import re
from pathlib import Path

sys.path.append(str(Path(__file__).parent))
from config.swat_config import MODBUS_CONFIG


# ─────────────────────────────────────────────────────────────────────────────
# Network helpers
# ─────────────────────────────────────────────────────────────────────────────

def is_udp_port_available(port: int, bind_host: str = '0.0.0.0') -> bool:
    """Return True if a UDP port can be bound locally (nothing is using it)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((bind_host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def is_matlab_server_alive(host: str, port: int,
                            per_attempt_timeout: float = 5.0,
                            retries: int = 4) -> bool:
    for _ in range(retries):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(per_attempt_timeout)
            s.connect((host, port))
            # Send a probe and check for response
            s.sendall(b'{"P_101":false,"MV_101":0}\n')
            data = s.recv(8192)
            s.close()
            return b'LIT_101' in data
        except Exception:
            try: s.close()
            except: pass
    return False


def wait_for_matlab_ready(host: str, port: int,
                           total_timeout: float = 120.0,
                           poll_interval: float = 5.0) -> bool:
    """
    Keep probing until swat_physics_server replies or total_timeout expires.
    Does NOT check subprocess return code (matlab.exe exits 0 on Windows normally).
    """
    deadline = time.time() + total_timeout
    while time.time() < deadline:
        if is_matlab_server_alive(host, port, per_attempt_timeout=poll_interval):
            return True
    return False


def check_codesys(host: str, port: int) -> bool:
    """Verify CODESYS Modbus TCP is accessible."""
    try:
        from pymodbus.client import ModbusTcpClient
        c = ModbusTcpClient(host, port=port, timeout=3)
        ok = c.connect()
        c.close()
        return ok
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Process helpers
# ─────────────────────────────────────────────────────────────────────────────

def _kill_port_owner(port: int) -> bool:
    """Kill the process holding a UDP port. Returns True if port is free after."""
    try:
        if platform.system() == 'Windows':
            out = subprocess.check_output(
                f'netstat -ano -p udp | findstr :{port}',
                shell=True
            ).decode(errors='replace')
            pids = re.findall(r'\s(\d+)\s*$', out, re.MULTILINE)
            for pid in set(pids):
                subprocess.call(
                    ['taskkill', '/PID', pid, '/F'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
        else:
            out = subprocess.check_output(
                ['lsof', '-t', f'-iUDP:{port}']
            ).decode(errors='replace')
            for pid in out.split():
                subprocess.call(['kill', '-9', pid])
        time.sleep(1.5)
        return is_udp_port_available(port)
    except subprocess.CalledProcessError:
        time.sleep(0.5)
        return is_udp_port_available(port)
    except Exception as exc:
        print(f'  [WARN] _kill_port_owner: {exc}')
        return False


def _cleanup(procs: list) -> None:
    for p in procs:
        try:
            p.terminate()
            p.wait(timeout=5)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass


def tail_file(path: Path, max_lines: int = 20) -> str:
    if not path.exists():
        return '(no log file found)'
    try:
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
        return '\n'.join(lines[-max_lines:]) if lines else '(log file empty)'
    except Exception as e:
        return f'(failed to read log: {e})'


def _launch_matlab(matlab_cmd: str, matlab_script: str,
                   stdout_log: Path, stderr_log: Path,
                   is_win: bool) -> subprocess.Popen:
    """
    Launch MATLAB as a background subprocess.
    CREATE_NO_WINDOW on Windows ensures stdout/stderr go to log files
    instead of a new console window that swallows all output.
    """
    out_f = open(stdout_log, 'w', encoding='utf-8')
    err_f = open(stderr_log, 'w', encoding='utf-8')
    kwargs: dict = dict(stdout=out_f, stderr=err_f)
    if is_win:
        kwargs['creationflags'] = 0x08000000  # CREATE_NO_WINDOW
    return subprocess.Popen(
        [matlab_cmd, '-nosplash', '-nodesktop', '-batch', matlab_script],
        **kwargs
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description='SWaT System Launcher — MATLAB ↔ Python ↔ CODESYS',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples
--------
  Basic run (logs to complete_dataset/):
    python start_system.py --host 192.168.5.195 --port 1502 --reuse-existing-matlab

  Run 01 with specific attacks (auto-stops after 70 min):
    python start_system.py --host 192.168.5.195 --port 1502 --reuse-existing-matlab \\
        --output run_01 --total 70 --attack 30 \\
        --include-attacks reconnaissance,replay,ph_manipulation,slow_ramp

  Run 02 with different attacks:
    python start_system.py --host 192.168.5.195 --port 1502 --reuse-existing-matlab \\
        --output run_02 --total 70 --attack 30 \\
        --include-attacks pump_failure,valve_manipulation,multi_stage

Available attacks (pass comma-separated to --include-attacks):
  reconnaissance, replay, ph_manipulation, slow_ramp,
  pump_failure, valve_manipulation, multi_stage,
  sensor_spoofing, dos, covert_channel
        """
    )

    # ── Infrastructure args ────────────────────────────────────────────────────
    parser.add_argument('--host',        default=MODBUS_CONFIG['host'],
                        help='CODESYS PLC IP')
    parser.add_argument('--port',        type=int, default=MODBUS_CONFIG['port'],
                        help='CODESYS Modbus port (default: 502)')
    parser.add_argument('--matlab-host', default='127.0.0.1',
                        help='MATLAB UDP server IP (ignored with --engine-api)')
    parser.add_argument('--matlab-port', type=int, default=9501,
                        help='MATLAB UDP server port (default: 9501)')
    parser.add_argument('--matlab-path', default='.',
                        help='Path to folder containing .m files')
    parser.add_argument('--matlab-start-timeout', type=int, default=120,
                        help='Seconds to wait for MATLAB to respond (default: 120)')
    parser.add_argument('--reuse-existing-matlab', action='store_true',
                        help='If port is busy, probe whether a live MATLAB server '
                             'exists and reuse it; auto-kill stale zombie if not.')
    parser.add_argument('--no-logger',  action='store_true',
                        help='Skip launching data logger')
    parser.add_argument('--engine-api', action='store_true',
                        help='Use MATLAB Engine API instead of UDP server')

    # ── Run / dataset args ────────────────────────────────────────────────────
    parser.add_argument('--output', default='complete_dataset',
                        metavar='FOLDER',
                        help='Output folder for this run (default: complete_dataset). '
                             'CSV saved as <folder>/master_dataset.csv')
    parser.add_argument('--total', type=int, default=None,
                        metavar='MINUTES',
                        help='Total run duration in minutes. '
                             'System shuts down automatically when reached.')
    parser.add_argument('--attack', type=int, default=None,
                        metavar='MINUTES',
                        help='Total minutes of attack traffic to inject '
                             '(spread across the run). Requires --include-attacks.')
    parser.add_argument('--include-attacks', default=None,
                        metavar='ATTACK1,ATTACK2,...',
                        help='Comma-separated list of attack types to inject. '
                             'Passed directly to automated_dataset_generator.py.')
    parser.add_argument('--attack-script',
                        default='automated_dataset_generator.py',
                        metavar='PATH',
                        help='Path to attack injector script '
                             '(default: automated_dataset_generator.py)')

    args = parser.parse_args()

    # Validate attack args
    if args.include_attacks and args.attack is None:
        parser.error('--include-attacks requires --attack <minutes>')
    if args.attack and not args.include_attacks:
        parser.error('--attack requires --include-attacks <attack1,attack2,...>')

    procs: list  = []
    is_win = platform.system() == 'Windows'

    # Build output paths from folder name
    run_dir    = Path(args.output)
    output_csv = run_dir / 'master_dataset.csv'
    meta_json  = run_dir / 'attack_metadata.json'

    print('=' * 60)
    print('SWaT System Launcher — MATLAB ↔ Python ↔ CODESYS')
    print(f'Run folder  : {run_dir.resolve()}')
    if args.total:
        print(f'Duration    : {args.total} min total'
              + (f', {args.attack} min attack' if args.attack else ''))
    if args.include_attacks:
        print(f'Attacks     : {args.include_attacks}')
    print('=' * 60)

    # ── Step 1: CODESYS reachability ─────────────────────────────────────────
    print(f'\n[1/5] Checking CODESYS at {args.host}:{args.port} ...')
    if not check_codesys(args.host, args.port):
        print('  ERROR: CODESYS not reachable. Start the PLC and Modbus slave first.')
        return 1
    print('  OK — CODESYS is reachable.')

    # ── Step 2: MATLAB physics server ────────────────────────────────────────
    if args.engine_api:
        print('\n[2/5] Starting MATLAB Engine API bridge ...')
        cmd = [sys.executable, 'matlab_bridge/engine_bridge.py',
               '--plc-host',    args.host,
               '--plc-port',    str(args.port),
               '--matlab-path', args.matlab_path]
        procs.append(subprocess.Popen(cmd))
        print('  Waiting ~20 s for MATLAB Engine to initialise ...')
        time.sleep(20)
        print('  Engine bridge started.')

    else:
        effective_matlab_host = args.matlab_host
        need_to_launch        = False

        print(f'\n[2/5] Starting MATLAB UDP physics server on port {args.matlab_port} ...')

        port_free = is_udp_port_available(args.matlab_port)

        if not port_free:
            if not args.reuse_existing_matlab:
                print(f'  ERROR: UDP port {args.matlab_port} is already in use.')
                print('  Add --reuse-existing-matlab to auto-probe / auto-kill.')
                if is_win:
                    print(f'    netstat -ano -p udp | findstr :{args.matlab_port}')
                    print('    taskkill /PID <PID> /F')
                else:
                    print(f'    sudo lsof -iUDP:{args.matlab_port}  →  kill -9 <PID>')
                return 1

            print(f'  Port {args.matlab_port} is busy — probing for live MATLAB server ...')
            alive = is_matlab_server_alive(effective_matlab_host, args.matlab_port)

            if not alive and effective_matlab_host != '127.0.0.1':
                print(f'  No response on {effective_matlab_host}; retrying on 127.0.0.1 ...')
                alive = is_matlab_server_alive('127.0.0.1', args.matlab_port)
                if alive:
                    effective_matlab_host = '127.0.0.1'
                    print('  Live server found on 127.0.0.1 — using localhost for bridge.')

            if alive:
                print('  Existing MATLAB physics server is live — reusing it.')
                need_to_launch = False
            else:
                print('  Port held by unresponsive process. Attempting to free ...')
                freed = _kill_port_owner(args.matlab_port)
                if not freed:
                    print(f'  ERROR: Could not free port {args.matlab_port}. Kill manually:')
                    if is_win:
                        print(f'    netstat -ano -p udp | findstr :{args.matlab_port}')
                        print('    taskkill /PID <PID> /F')
                    else:
                        print(f'    sudo lsof -iUDP:{args.matlab_port}  →  kill -9 <PID>')
                    return 1
                print('  Port freed. Launching fresh MATLAB server ...')
                need_to_launch = True
        else:
            need_to_launch = True

        # ── Launch MATLAB if required ─────────────────────────────────────────
        if need_to_launch:
            logs_dir   = Path('logs')
            logs_dir.mkdir(exist_ok=True)
            stdout_log = logs_dir / 'matlab_server_stdout.log'
            stderr_log = logs_dir / 'matlab_server_stderr.log'

            matlab_path_esc = str(Path(args.matlab_path).resolve()).replace("'", "''")
            matlab_script = (
                f"setenv('PHYSICS_UDP_PORT','{args.matlab_port}'); "
                f"addpath('{matlab_path_esc}'); "
                f"swat_physics_server()"
            )

            if effective_matlab_host != '127.0.0.1':
                print(f'  NOTE: Local MATLAB; overriding --matlab-host → 127.0.0.1')
                effective_matlab_host = '127.0.0.1'

            matlab_cmd  = 'matlab.exe' if is_win else 'matlab'
            matlab_proc = _launch_matlab(matlab_cmd, matlab_script,
                                         stdout_log, stderr_log, is_win)
            procs.append(matlab_proc)

            print(f'  Waiting up to {args.matlab_start_timeout} s for MATLAB to respond ...')
            if is_win:
                print('  (Windows: matlab.exe launcher exits immediately — normal.)')

            ready = wait_for_matlab_ready(
                effective_matlab_host, args.matlab_port,
                total_timeout=args.matlab_start_timeout
            )

            if not ready:
                rc = matlab_proc.poll()
                print(f'\n  ERROR: MATLAB did not respond within {args.matlab_start_timeout} s.')
                if rc is not None and rc != 0:
                    print(f'         Process exited with error code {rc}.')
                elif rc == 0 and is_win:
                    print('         Launcher exited (code 0 = normal Windows detach).')
                    print(f'         Try: --matlab-start-timeout 180')
                print(f'         stdout log : {stdout_log}')
                print(f'         stderr log : {stderr_log}')
                print('         Last stderr lines:')
                print(tail_file(stderr_log, max_lines=25))
                if is_win:
                    print(f'\n  Windows tip (run as Administrator):')
                    print(f'    netsh advfirewall firewall add rule '
                          f'name="MATLAB UDP {args.matlab_port}" '
                          f'protocol=UDP dir=in localport={args.matlab_port} action=allow')
                _cleanup(procs)
                return 1

        print('  MATLAB physics server is ready.')

        # ── Step 3: Physics bridge + integrated CSV logger ───────────────────
        # FIX Issue 1: logging merged into bridge — single process, no duplicate rows.
        # Old setup launched physics_client.py twice (once without --output, once with)
        # producing ~1.6× rows at 16 Hz instead of 10 Hz.
        print('\n[3/4] Starting physics bridge ...')
        run_dir.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, 'matlab_bridge/physics_client.py',
               '--plc-host',    args.host,
               '--plc-port',    str(args.port),
               '--matlab-host', effective_matlab_host,
               '--matlab-port', str(args.matlab_port)]
        if not args.no_logger:
            cmd += ['--output',        str(output_csv),
                    '--metadata-file', str(meta_json)]
        procs.append(subprocess.Popen(cmd))
        time.sleep(3)
        if not args.no_logger:
            print(f'  Physics bridge started  →  logging to {output_csv}')
        else:
            print('  Physics bridge started (logging disabled).')

    # ── Step 4: Attack injector (optional) ────────────────────────────────────
    attack_proc = None
    if args.include_attacks:
        attack_script = Path(args.attack_script)
        if not attack_script.exists():
            print(f'\n[5/5] WARNING: Attack script not found: {attack_script}')
            print('       Continuing without attack injection.')
        else:
            print(f'\n[4/4] Starting attack injector ...')
            # Wait for logger and bridge to stabilise before injecting
            time.sleep(5)
            cmd = [sys.executable, str(attack_script),
                   '--host',            args.host,
                   '--port',            str(args.port),
                   '--output',          str(run_dir),
                   '--include-attacks', args.include_attacks]
            if args.total:
                cmd += ['--total',  str(args.total)]
            if args.attack:
                cmd += ['--attack', str(args.attack)]
            attack_proc = subprocess.Popen(cmd)
            procs.append(attack_proc)
            print(f'  Attack injector started.')
            print(f'  Attacks : {args.include_attacks}')
            if args.attack:
                print(f'  Attack duration : {args.attack} min')
    else:
        print('\n[4/4] No attacks specified — logging normal operation only.')

    # ── Summary ───────────────────────────────────────────────────────────────
    print('\n' + '=' * 60)
    print('All components running.')
    if args.total:
        stop_at = time.time() + args.total * 60
        import datetime
        stop_str = datetime.datetime.fromtimestamp(stop_at).strftime('%H:%M:%S')
        print(f'Auto-stop in {args.total} min  (at {stop_str})')
    else:
        print('Press Ctrl+C to stop.')
    print('=' * 60 + '\n')

    # ── Signal handlers ───────────────────────────────────────────────────────
    def _sig(*_):
        print('\nShutting down ...')
        _cleanup(procs)
        sys.exit(0)

    signal.signal(signal.SIGINT,  _sig)
    signal.signal(signal.SIGTERM, _sig)

    # ── Monitor / auto-stop loop ──────────────────────────────────────────────
    run_end = (time.time() + args.total * 60) if args.total else None

    while True:
        # Auto-stop when total duration reached
        if run_end and time.time() >= run_end:
            print(f'\n  Run complete ({args.total} min elapsed).')
            print(f'  Dataset saved to: {run_dir.resolve()}')
            _cleanup(procs)
            return 0

        # Warn if any child (except Windows matlab launcher) has died
        for p in list(procs):
            rc = p.poll()
            if rc is not None and not (rc == 0 and is_win):
                print(f'  WARNING: subprocess PID {p.pid} exited (code {rc}) '
                      f'— system may be degraded.')

        # Progress tick every 60 s when a timed run is active
        if run_end:
            remaining = max(0, run_end - time.time())
            mins_left = int(remaining / 60)
            if int(remaining) % 60 == 0 and remaining > 0:
                print(f'  [{args.output}] {mins_left} min remaining ...')

        time.sleep(5)


if __name__ == '__main__':
    sys.exit(main())