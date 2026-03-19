# SWaT Dataset Collection — Attack Run Commands

## Attack Categories

| Type | Attack | MITRE | Duration |
|---|---|---|---|
| **Network** | `reconnaissance` | T0840 | 5–10 min |
| **Network** | `replay` | T0843 | 5–10 min |
| **Temporal** | `ph_manipulation` | T0831 | 10–15 min |
| **Temporal** | `slow_ramp` | T0836 | 10–15 min |
| **Temporal** | `membrane_damage` | T0836 | 10–15 min |
| **Temporal** | `chemical_depletion` | T0814 | 10–15 min |
| **Command** | `tank_overflow` | T0816 | 10–15 min |
| **Command** | `valve_manipulation` | T0849 | 5–10 min |

---

## Run 01 — Reconnaissance + Replay + pH + Slow Ramp
**2 network, 2 temporal**

```cmd
python start_system.py --host 192.168.5.195 --port 1502 ^
    --matlab-path "C:\Users\Dweep\Documents\water-cps" ^
    --reuse-existing-matlab ^
    --output run_01 --total 70 --attack 30 ^
    --include-attacks reconnaissance,replay,ph_manipulation,slow_ramp
```

Expected CSV rows: ~42,000 | Attack rows: ~18,000 | Normal rows: ~24,000

---

## Run 02 — Reconnaissance + Replay + Membrane + Chemical Depletion
**2 network, 2 temporal**

```cmd
python start_system.py --host 192.168.5.195 --port 1502 ^
    --matlab-path "C:\Users\Dweep\Documents\water-cps" ^
    --reuse-existing-matlab ^
    --output run_02 --total 70 --attack 30 ^
    --include-attacks reconnaissance,replay,membrane_damage,chemical_depletion
```

Expected CSV rows: ~42,000 | Attack rows: ~18,000 | Normal rows: ~24,000

---

## Run 03 — Reconnaissance + Replay + Tank Overflow + Valve Manipulation
**2 network, 2 command injection**

```cmd
python start_system.py --host 192.168.5.195 --port 1502 ^
    --matlab-path "C:\Users\Dweep\Documents\water-cps" ^
    --reuse-existing-matlab ^
    --output run_03 --total 70 --attack 30 ^
    --include-attacks reconnaissance,replay,tank_overflow,valve_manipulation
```

Expected CSV rows: ~42,000 | Attack rows: ~18,000 | Normal rows: ~24,000

---

## Run 04 — All Temporal (heavy fouling + pH stress)
**4 temporal attacks — tests model on slow-evolving patterns**

```cmd
python start_system.py --host 192.168.5.195 --port 1502 ^
    --matlab-path "C:\Users\Dweep\Documents\water-cps" ^
    --reuse-existing-matlab ^
    --output run_04 --total 80 --attack 40 ^
    --include-attacks ph_manipulation,slow_ramp,membrane_damage,chemical_depletion
```

Expected CSV rows: ~48,000 | Attack rows: ~24,000 | Normal rows: ~24,000

---

## Run 05 — Normal Baseline Only (no attacks)
**Used to train Isolation Forest and Autoencoder on clean normal data**

```cmd
python start_system.py --host 192.168.5.195 --port 1502 ^
    --matlab-path "C:\Users\Dweep\Documents\water-cps" ^
    --reuse-existing-matlab ^
    --output run_05 --total 60 --no-logger
```

> **Note:** `--no-logger` skips the attack injector. Only normal operation is logged via the bridge's built-in CSV (`--output run_05` still creates `run_05/master_dataset.csv`).

Expected CSV rows: ~36,000 | All Normal (ATTACK_ID = 0)

---

## Individual Attack Commands (manual injection during a running system)

Use these when `start_system.py` is already running and you want to inject a single attack:

### Network Attacks
```cmd
# Reconnaissance scan (20 Hz read, no writes)
python attacks/command_injection.py --host 192.168.5.195 --attack single_point ^
    --target-type coil --target-address 0 --value 1 --duration 300

# Replay (freeze actuator state)
python attacks/command_injection.py --host 192.168.5.195 --attack valve_manipulation ^
    --valve-position 0 --target-valves MV_101 MV_201 MV_301 --duration 180
```

### Temporal Attacks
```cmd
# pH manipulation — alkaline drift (coil-only, zero oscillation)
python attacks/command_injection.py --host 192.168.5.195 ^
    --attack ph_manipulation --target-ph 8.5 --duration 240

# pH manipulation — acidic drop (register write at 12.5 Hz)
python attacks/command_injection.py --host 192.168.5.195 ^
    --attack ph_manipulation --target-ph 5.0 --duration 240

# Slow ramp — pH gradient via coil duty cycle
python attacks/command_injection.py --host 192.168.5.195 ^
    --attack slow_ramp --ramp-target AIT_202 ^
    --start-value 720 --end-value 860 --duration 600

# Membrane damage — suppress backwash, accumulate fouling
python attacks/command_injection.py --host 192.168.5.195 ^
    --attack membrane_damage --duration 300

# Chemical depletion — force all dosing pumps ON
python attacks/command_injection.py --host 192.168.5.195 ^
    --attack chemical_depletion --duration 300
```

### Command Injection Attacks
```cmd
# Tank overflow — kill pumps, fill naturally via physics
python attacks/command_injection.py --host 192.168.5.195 ^
    --attack tank_overflow --duration 300

# Tank overflow — direct register write (--no-physics)
python attacks/command_injection.py --host 192.168.5.195 ^
    --attack tank_overflow --no-physics --overflow-value 1000 --duration 300

# Valve manipulation — close all Stage 1-3 valves
python attacks/command_injection.py --host 192.168.5.195 ^
    --attack valve_manipulation --valve-position 0 ^
    --target-valves MV_101 MV_201 MV_301 MV_302 --duration 120

# Single point coil injection (turn off P_101)
python attacks/command_injection.py --host 192.168.5.195 ^
    --attack single_point --target-type coil --target-address 0 --value 0 --duration 120
```

---

## Notes

- **Never interrupt a run early** — partial runs have unbalanced attack/normal ratios.
- **Restart MATLAB between runs** if TCP errors appear: `taskkill /F /IM matlab.exe`
- **Check CSV after each run:** `python -c "import pandas as pd; df=pd.read_csv('run_01/master_dataset.csv'); print(df['ATTACK_NAME'].value_counts())"`
- **Fix PIT_502 threshold** in ST before collecting: `IF PIT_502 > 300 THEN` (not 30)
- All temporal attacks use actuator-side injection — no register oscillation.