# SWaT Digital Twin — Complete Command Reference

## Prerequisites

```cmd
# Kill any stale MATLAB instances
taskkill /F /IM matlab.exe

# Kill all Python processes (if needed)
taskkill /F /IM python.exe

# Check CODESYS is reachable
ping 192.168.5.195
```

---

## Dataset Collection Runs

### Run 01 — Recon + Replay + pH + SlowRamp (2 network + 2 temporal)
```cmd
python start_system.py --host 192.168.5.195 --port 1502 --matlab-path "C:\Users\Dweep\Documents\water-cps" --reuse-existing-matlab --output run_01 --total 70 --attack 30 --include-attacks reconnaissance,replay,ph_manipulation,slow_ramp
```

### Run 02 — Recon + Replay + Membrane + Chemical Depletion
```cmd
python start_system.py --host 192.168.5.195 --port 1502 --matlab-path "C:\Users\Dweep\Documents\water-cps" --reuse-existing-matlab --output run_02 --total 70 --attack 30 --include-attacks reconnaissance,replay,membrane_damage,chemical_depletion
```

### Run 03 — Recon + Replay + Tank Overflow + Valve Manipulation
```cmd
python start_system.py --host 192.168.5.195 --port 1502 --matlab-path "C:\Users\Dweep\Documents\water-cps" --reuse-existing-matlab --output run_03 --total 70 --attack 30 --include-attacks reconnaissance,replay,tank_overflow,valve_manipulation
```

### Run 04 — All Temporal (pH + SlowRamp + Membrane + Chemical)
```cmd
python start_system.py --host 192.168.5.195 --port 1502 --matlab-path "C:\Users\Dweep\Documents\water-cps" --reuse-existing-matlab --output run_04 --total 80 --attack 40 --include-attacks ph_manipulation,slow_ramp,membrane_damage,chemical_depletion
```

### Run 05 — Normal Baseline Only
```cmd
python start_system.py --host 192.168.5.195 --port 1502 --matlab-path "C:\Users\Dweep\Documents\water-cps" --reuse-existing-matlab --output run_05 --total 60
```

---

## Bridge Only (no attacks, manual control)

```cmd
# Bridge + logging, no attacks
python matlab_bridge/physics_client.py --plc-host 192.168.5.195 --plc-port 1502 --matlab-host 127.0.0.1 --matlab-port 9501 --output run_manual/master_dataset.csv --metadata-file run_manual/attack_metadata.json

# Bridge with hard stop at 30 min
python matlab_bridge/physics_client.py --plc-host 192.168.5.195 --plc-port 1502 --output run_test/master_dataset.csv --total-minutes 30

# Bridge only, no logging
python matlab_bridge/physics_client.py --plc-host 192.168.5.195 --plc-port 1502
```

---

## WebSocket Dashboard

```cmd
# Start WS server
python matlab_bridge/ws_server.py --plc-host 192.168.5.195 --plc-port 1502

# Then open dashboard.html in browser
# Connect to: ws://127.0.0.1:8765
```

---

## Manual Attack Injection
> Run these **while the bridge is already running** in a separate terminal.

### Network Attacks
```cmd
# Reconnaissance scan (read-only, 20 Hz)
python attacks\command_injection.py --host 192.168.5.195 --attack single_point --target-type coil --target-address 0 --value 1 --duration 300

# Replay (freeze actuator state for 3 min)
python attacks\command_injection.py --host 192.168.5.195 --attack valve_manipulation --valve-position 0 --target-valves MV_101 MV_201 MV_301 --duration 180
```

### pH Attacks
```cmd
# pH drop to 5.0 — acidic (register write at 25 Hz)
python attacks\command_injection.py --host 192.168.5.195 --attack ph_manipulation --target-ph 5.0 --duration 300

# pH rise to 9.0 — alkaline (register write at 25 Hz)
python attacks\command_injection.py --host 192.168.5.195 --attack ph_manipulation --target-ph 9.0 --duration 300

# pH alkaline coil-only — natural drift (slower, MATLAB range)
python attacks\command_injection.py --host 192.168.5.195 --attack ph_manipulation --target-ph 8.4 --duration 300
```

### Slow Ramp Attacks
```cmd
# Ramp pH downward (720→560 over 10 min) — below MATLAB floor
python attacks\command_injection.py --host 192.168.5.195 --attack slow_ramp --ramp-target AIT_202 --start-value 720 --end-value 560 --duration 600

# Ramp pH upward (720→890 over 10 min) — above MATLAB ceiling
python attacks\command_injection.py --host 192.168.5.195 --attack slow_ramp --ramp-target AIT_202 --start-value 720 --end-value 890 --duration 600

# Ramp LIT_101 upward
python attacks\command_injection.py --host 192.168.5.195 --attack slow_ramp --ramp-target LIT_101 --start-value 500 --end-value 900 --duration 600
```

### Command Injection Attacks
```cmd
# Tank overflow — actuator-side (kill pumps, physics fills naturally)
python attacks\command_injection.py --host 192.168.5.195 --attack tank_overflow --duration 300

# Tank overflow — direct register (--no-physics, 25 Hz write)
python attacks\command_injection.py --host 192.168.5.195 --attack tank_overflow --no-physics --overflow-value 1000 --duration 300

# Valve manipulation — close all inlet/UF valves
python attacks\command_injection.py --host 192.168.5.195 --attack valve_manipulation --valve-position 0 --target-valves MV_101 MV_201 MV_301 MV_302 --duration 120

# Valve manipulation — open backwash valves (disrupt UF)
python attacks\command_injection.py --host 192.168.5.195 --attack valve_manipulation --valve-position 1 --target-valves MV_303 MV_304 --duration 120

# Chemical depletion — force all dosing pumps ON
python attacks\command_injection.py --host 192.168.5.195 --attack chemical_depletion --duration 300

# Chemical depletion — acid + chlorine only (skip bisulfate)
python attacks\command_injection.py --host 192.168.5.195 --attack chemical_depletion --no-drain-bisulfate --no-drain-coagulant --duration 300

# Membrane damage — suppress backwash, accumulate fouling
python attacks\command_injection.py --host 192.168.5.195 --attack membrane_damage --duration 300

# Membrane damage — no fouling acceleration (coil-only)
python attacks\command_injection.py --host 192.168.5.195 --attack membrane_damage --no-accelerate-fouling --duration 300
```

### Single Point Attacks
```cmd
# Inject specific register value (e.g. force pH register to 500 = pH 5.0)
python attacks\command_injection.py --host 192.168.5.195 --attack single_point --target-type register --target-address 4 --value 500 --duration 120

# Inject specific coil (e.g. force P_101 OFF = address 0)
python attacks\command_injection.py --host 192.168.5.195 --attack single_point --target-type coil --target-address 0 --value 0 --duration 120

# Force P_501 (RO pump) OFF = coil 15
python attacks\command_injection.py --host 192.168.5.195 --attack single_point --target-type coil --target-address 15 --value 0 --duration 180
```

---

## Dataset Validation

```cmd
# Quick check — attack distribution + rate
python -c "import pandas as pd; df=pd.read_csv('run_01/master_dataset.csv'); ts=pd.to_datetime(df.Timestamp,utc=True); print(df['ATTACK_NAME'].value_counts()); print(f'Rate: {len(df)/((ts.max()-ts.min()).total_seconds()):.2f} Hz'); print(f'Duration: {(ts.max()-ts.min()).total_seconds()/60:.1f} min')"

# Check MV registers (should not be all zeros)
python -c "import pandas as pd; df=pd.read_csv('run_01/master_dataset.csv'); [print(f'{mv}: {(df[mv]==1).mean()*100:.1f}% open') for mv in ['MV_101','MV_201','MV_301','MV_302']]"

# Check flow scaling (should be 1.0–6.0, not 10–60)
python -c "import pandas as pd; df=pd.read_csv('run_01/master_dataset.csv'); print(df[['FIT_101','FIT_301','FIT_501']].describe().round(2))"

# Check pH separation between attacks
python -c "import pandas as pd; df=pd.read_csv('run_01/master_dataset.csv'); print(df.groupby('ATTACK_NAME')['AIT_202'].agg(['min','max']))"

# Full null check
python -c "import pandas as pd; df=pd.read_csv('run_01/master_dataset.csv'); print(df.isnull().sum()[df.isnull().sum()>0])"

# Session continuity check (max gap)
python -c "import pandas as pd; df=pd.read_csv('run_01/master_dataset.csv'); ts=pd.to_datetime(df.Timestamp,utc=True).sort_values(); dt=ts.diff().dt.total_seconds(); print(f'MaxGap:{dt.max():.2f}s  Gaps>10s:{(dt>10).sum()}')"
```

---

## Modbus Register Addresses (Quick Reference)

| Address | Register | Scale | Unit |
|---|---|---|---|
| 0 | FIT_101 | ÷10 | m³/h |
| 1 | LIT_101 | ×1 | L |
| 2 | MV_101 | ×1 | 0/1 |
| 4 | AIT_202 | ÷100 | pH |
| 12 | DPIT_301 | ÷10 | kPa |
| 14 | LIT_301 | ×1 | L |
| 26 | LIT_401 | ×1 | L |
| 35 | PIT_501 | ÷10 | bar |
| 39 | RO_Fouling_Factor | ×1 | % |
| 51 | Chlorine_Residual | ÷10 | mg/L |

| Coil | Name | Type |
|---|---|---|
| 0 | P_101 | Main feed pump |
| 4 | P_203 | Acid dosing |
| 6 | P_205 | Chlorine dosing |
| 8 | P_301 | UF feed pump |
| 12 | P_403 | Bisulfate dosing |
| 15 | P_501 | RO HP pump |
| 20 | UF_Backwash_Active | State |
| 21 | RO_Cleaning_Active | State |
| 22 | Chemical_Low_Alarm | Alarm |
| 26 | High_Pressure_Alarm | Alarm |
| 27 | System_Run | State |

---

## Troubleshooting

```cmd
# MATLAB not responding → kill and restart
taskkill /F /IM matlab.exe
# Then re-run start_system.py without --reuse-existing-matlab

# CODESYS not reachable
ping 192.168.5.195
# Check CODESYS is running and Modbus slave is active on port 1502

# Check what's holding port 9501
netstat -ano -p tcp | findstr :9501
taskkill /PID <PID> /F

# Force kill everything and restart clean
taskkill /F /IM matlab.exe & taskkill /F /IM python.exe
```
