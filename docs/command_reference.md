# COMPLETE COMMAND REFERENCE WITH METADATA
# All Commands for Automated & Manual Dataset Collection

---

## TABLE OF CONTENTS

1. [Quick Fix Summary](#quick-fix-summary)
2. [Automated Dataset Generation](#automated-dataset-generation)
3. [Manual Logging with Attack Metadata](#manual-logging-with-attack-metadata)
4. [All Attack Commands with Metadata](#all-attack-commands-with-metadata)
5. [Verifying Metadata is Working](#verifying-metadata-is-working)
6. [Troubleshooting Metadata Issues](#troubleshooting-metadata-issues)

---

## QUICK FIX SUMMARY

### What Was Fixed

**Problem**: `UnicodeEncodeError: 'charmap' codec can't encode character '\u25ba'`

**Cause**: Windows uses cp1252/charmap encoding by default. Unicode characters like `►` (U+25BA) are not supported.

**Solution**: All file writes now explicitly use UTF-8 encoding:
```python
# OLD (breaks on Windows):
with open(file, 'w') as f:
    f.write(text)

# NEW (works everywhere):
with open(file, 'w', encoding='utf-8') as f:
    f.write(text)
```

**Files Fixed**:
- `automated_dataset_generator.py` — all 3 file write locations
- Logs now support: ►, ✓, ✗, ←, →, arrows, emojis, Chinese/Arabic/etc.

---

## AUTOMATED DATASET GENERATION

### Basic 2-Hour Dataset

```cmd
python automated_dataset_generator.py --host 192.168.1.100
```

**What happens automatically:**
1. Creates `automated_dataset\attack_metadata.json` with initial state:
   ```json
   {"ATTACK_ID": 0, "ATTACK_NAME": "Normal", "MITRE_ID": "None"}
   ```

2. Spawns logger subprocess with metadata file path:
   ```cmd
   python logging\data_logger.py --host 192.168.1.100 --metadata-file automated_dataset\attack_metadata.json --output automated_dataset\master_dataset.csv
   ```

3. At each attack time:
   - **Writes metadata**: `{"ATTACK_ID": 11, "ATTACK_NAME": "pH Manipulation Attack", ...}`
   - **Executes temporal attack**: Direct Modbus writes with realistic physics
   - **Resets metadata**: `{"ATTACK_ID": 0, "ATTACK_NAME": "Normal", ...}`

4. Logger reads metadata every poll (1 Hz) and labels CSV rows

**Output Files**:
```
automated_dataset\
├── master_dataset.csv          # All data with attack labels
├── normal_only.csv            # Rows where ATTACK_ID = 0
├── attacks_only.csv           # Rows where ATTACK_ID > 0
├── attack_metadata.json       # Current state (last value: Normal)
├── attack_timeline.log        # Full analysis report
└── execution_details.log      # Detailed execution log (UTF-8)
```

---

### Short Test (5 Minutes)

```cmd
python automated_dataset_generator.py --host 192.168.1.100 --total 5 --normal 3 --attack 2
```

**Expected console output (UTF-8 symbols now work)**:
```
[2026-02-17 14:00:00] [INFO] SWAT AUTOMATED GENERATOR - TEMPORAL ATTACK PROFILES
[2026-02-17 14:00:00] [SCHEDULE] [1] pH Manipulation Attack @2.3min dur=60s params={'target_ph': 5.2}
[2026-02-17 14:00:03] [INFO] Logger started (PID 12345)
[2026-02-17 14:02:18] [ATTACK] ► pH Manipulation Attack  dur=60s  params={'target_ph': 5.2}
[2026-02-17 14:02:18] [INFO]   pH attack: 7.20 → 5.20 pH  (τ=20s, duration=60s)
[2026-02-17 14:03:18] [INFO]   ✓ attack complete (success=True), reset to Normal
```

**Verify metadata was used**:
```cmd
type automated_dataset\execution_details.log | findstr "metadata"

REM Should show:
REM [INFO] Updated metadata: ID=11, Name=pH Manipulation Attack
```

---

### Custom Attack Mix

```cmd
REM Mostly pH attacks (edit automated_dataset_generator.py line 863)
REM Change:
self.available_attacks = [
    'ph_manipulation',
    'ph_manipulation',
    'ph_manipulation',
    'tank_overflow',
]

REM Then run:
python automated_dataset_generator.py --host 192.168.1.100
```

---

## MANUAL LOGGING WITH ATTACK METADATA

### Step-by-Step Manual Session

**Terminal 1 — Start Logger (runs continuously)**:

```cmd
cd C:\swat_OPTIMIZED

REM Initialize metadata file to Normal
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"

REM Start logger pointing to metadata file
python logging\data_logger.py --host 192.168.1.100 --output data\manual_session.csv --metadata-file attack_metadata.json
```

**Terminal 2 — Fire Attacks When Ready**:

```cmd
cd C:\swat_OPTIMIZED

REM Wait for some normal data (e.g., 3 minutes)
timeout /T 180

REM Execute Attack 1 (pH manipulation)
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':11,'ATTACK_NAME':'pH Manipulation Attack','MITRE_ID':'T0836'}))"

python attacks\command_injection.py --host 192.168.1.100 --attack ph_manipulation --target-ph 5.0 --duration 90

python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"

REM Wait for recovery
timeout /T 120

REM Execute Attack 2 (tank overflow)
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':8,'ATTACK_NAME':'Tank Overflow Attack','MITRE_ID':'T0836'}))"

python attacks\command_injection.py --host 192.168.1.100 --attack tank_overflow --duration 120

python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
```

**Terminal 1 — Stop Logger**:
```
Press Ctrl+C
```

---

## ALL ATTACK COMMANDS WITH METADATA

### Attack 1: pH Manipulation (Exponential Drift)

**ATTACK_ID**: 11  
**MITRE**: T0836  
**Duration**: 60-240 seconds  
**Physics**: First-order chemical kinetics (exponential approach to equilibrium)

```cmd
REM Label CSV rows as pH attack
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':11,'ATTACK_NAME':'pH Manipulation Attack','MITRE_ID':'T0836'}))"

REM Execute temporal pH attack (7.2 → 4.8 exponentially)
python attacks\command_injection.py --host 192.168.1.100 --attack ph_manipulation --target-ph 4.8 --duration 120

REM Reset labels to Normal
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
```

**What you'll see in CSV**:
```
Timestamp,           ..., AIT_202, P_203, ..., ATTACK_ID, ATTACK_NAME
2026-02-17T14:05:00, ..., 720,     True,  ..., 0,         Normal
2026-02-17T14:05:01, ..., 718,     False, ..., 11,        pH Manipulation Attack
2026-02-17T14:05:02, ..., 715,     False, ..., 11,        pH Manipulation Attack
2026-02-17T14:05:30, ..., 660,     False, ..., 11,        pH Manipulation Attack
2026-02-17T14:06:00, ..., 580,     False, ..., 11,        pH Manipulation Attack
2026-02-17T14:06:30, ..., 520,     False, ..., 11,        pH Manipulation Attack
2026-02-17T14:07:00, ..., 490,     False, ..., 11,        pH Manipulation Attack
2026-02-17T14:07:01, ..., 492,     True,  ..., 0,         Normal
```

**Variations**:
```cmd
REM Highly acidic (pH 3.8)
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':11,'ATTACK_NAME':'pH Manipulation Attack','MITRE_ID':'T0836'}))"
python attacks\command_injection.py --host 192.168.1.100 --attack ph_manipulation --target-ph 3.8 --duration 150
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"

REM Alkaline (pH 9.5)
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':11,'ATTACK_NAME':'pH Manipulation Attack','MITRE_ID':'T0836'}))"
python attacks\command_injection.py --host 192.168.1.100 --attack ph_manipulation --target-ph 9.5 --duration 120
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
```

---

### Attack 2: Tank Overflow (Sigmoid Fill)

**ATTACK_ID**: 8  
**MITRE**: T0836  
**Duration**: 90-240 seconds  
**Physics**: S-curve hydraulic response (system absorbs shock → fast fill → saturation)

```cmd
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':8,'ATTACK_NAME':'Tank Overflow Attack','MITRE_ID':'T0836'}))"

python attacks\command_injection.py --host 192.168.1.100 --attack tank_overflow --overflow-value 1000 --duration 180

python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
```

**What you'll see in CSV**:
```
Timestamp,           ..., LIT_101, P_101, High_Level_Alarm, ATTACK_ID, ATTACK_NAME
2026-02-17T14:10:00, ..., 520,     True,  False,            0,         Normal
2026-02-17T14:10:01, ..., 520,     False, False,            8,         Tank Overflow Attack  ← pump stops
2026-02-17T14:10:11, ..., 530,     False, False,            8,         Tank Overflow Attack  ← slow start
2026-02-17T14:10:30, ..., 580,     False, False,            8,         Tank Overflow Attack
2026-02-17T14:11:00, ..., 720,     False, False,            8,         Tank Overflow Attack  ← fast rise
2026-02-17T14:11:30, ..., 850,     False, False,            8,         Tank Overflow Attack
2026-02-17T14:12:00, ..., 940,     False, True,             8,         Tank Overflow Attack  ← alarm!
2026-02-17T14:13:01, ..., 935,     True,  True,             0,         Normal                ← recovering
```

---

### Attack 3: Chemical Depletion (Linear Drain)

**ATTACK_ID**: 9  
**MITRE**: T0836  
**Duration**: 60-180 seconds  
**Physics**: Constant pump flow rate (linear mass loss)

```cmd
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':9,'ATTACK_NAME':'Chemical Depletion Attack','MITRE_ID':'T0836'}))"

python attacks\command_injection.py --host 192.168.1.100 --attack chemical_depletion --duration 120

python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
```

---

### Attack 4: Membrane Damage (Exponential Pressure Creep)

**ATTACK_ID**: 10  
**MITRE**: T0836  
**Duration**: 120-300 seconds  
**Physics**: Fouling index increases exponentially with pressure (membrane compaction feedback loop)

```cmd
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':10,'ATTACK_NAME':'Membrane Damage Attack','MITRE_ID':'T0836'}))"

python attacks\command_injection.py --host 192.168.1.100 --attack membrane_damage --duration 240

python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
```

---

### Attack 5: Valve Manipulation (Hydraulic Transient)

**ATTACK_ID**: 16  
**MITRE**: T0836  
**Duration**: 60-120 seconds  
**Physics**: Water hammer + exponential flow decay

```cmd
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':16,'ATTACK_NAME':'Valve Manipulation Attack','MITRE_ID':'T0836'}))"

python attacks\command_injection.py --host 192.168.1.100 --attack valve_manipulation --valve-position 0 --duration 90

python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
```

---

### Attack 6: Slow Ramp (Stealth Drift)

**ATTACK_ID**: 12  
**MITRE**: T0836  
**Duration**: 300-900 seconds  
**Physics**: Linear ramp + Gaussian noise + random plateaus (mimics natural variability)

```cmd
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':12,'ATTACK_NAME':'Slow Ramp Attack','MITRE_ID':'T0836'}))"

python attacks\command_injection.py --host 192.168.1.100 --attack slow_ramp --start-value 500 --end-value 900 --duration 600

python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
```

---

### Attack 7: Multi-Variable Stealth (APT)

**ATTACK_ID**: 17  
**MITRE**: T0856 (Spoof Reporting Message)  
**Duration**: 180-420 seconds  
**Physics**: Simultaneous exponential drift on 4 variables, each stays below alarm threshold

```cmd
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':17,'ATTACK_NAME':'Multi-Variable Stealth','MITRE_ID':'T0856'}))"

python attacks\command_injection.py --host 192.168.1.100 --attack multi_stealth --duration 300

python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
```

---

## VERIFYING METADATA IS WORKING

### Check 1: Metadata File Exists and Has Current State

```cmd
dir attack_metadata.json

REM Should show: attack_metadata.json

type attack_metadata.json

REM Should show JSON like:
REM {"ATTACK_ID": 0, "ATTACK_NAME": "Normal", "MITRE_ID": "None", "timestamp": "2026-02-17T14:23:45"}
```

---

### Check 2: Logger is Reading Metadata File

```cmd
REM In logger output (Terminal 1), you should see at startup:
REM INFO - Using metadata file: attack_metadata.json

REM Check logs:
type logs\swat_system.log | findstr "metadata"
```

---

### Check 3: CSV Has Attack Labels

```cmd
python -c "import pandas as pd; df=pd.read_csv('data\manual_session.csv'); print(f'Attack rows: {(df.ATTACK_ID>0).sum()}'); print(df.ATTACK_NAME.value_counts())"

REM Expected output:
REM Attack rows: 420
REM Normal                        1280
REM pH Manipulation Attack         120
REM Tank Overflow Attack           180
REM Slow Ramp Attack              120
```

If attack rows = 0, metadata is not working. See troubleshooting below.

---

### Check 4: Attack Transitions Are Clean

```cmd
python -c "
import pandas as pd
df = pd.read_csv('data\manual_session.csv')

# Find attack start/end boundaries
df['attack_change'] = df['ATTACK_ID'].diff().fillna(0) != 0
transitions = df[df['attack_change']]

print('Attack transitions:')
print(transitions[['Timestamp','ATTACK_ID','ATTACK_NAME']].head(20))
"

REM Expected: clean transitions with no gaps
REM 14:05:00, 0,  Normal
REM 14:05:01, 11, pH Manipulation Attack  ← clean start
REM 14:07:00, 11, pH Manipulation Attack
REM 14:07:01, 0,  Normal                  ← clean end
```

---

## TROUBLESHOOTING METADATA ISSUES

### Problem: "attack_metadata.json not found"

```cmd
REM Solution: Create it manually
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"

REM Verify:
type attack_metadata.json
```

---

### Problem: Logger not reading metadata (all ATTACK_ID=0)

**Diagnosis**:
```cmd
REM Check logger command line
tasklist /V | findstr python

REM Should show: --metadata-file attack_metadata.json
```

**Solution**: Always include `--metadata-file attack_metadata.json` when starting logger:

```cmd
REM WRONG (no metadata):
python logging\data_logger.py --host 192.168.1.100 --output data.csv

REM CORRECT:
python logging\data_logger.py --host 192.168.1.100 --output data.csv --metadata-file attack_metadata.json
```

---

### Problem: Some attacks labeled, others not

**Cause**: You forgot to write metadata before some attacks.

**Check**:
```cmd
python -c "
import pandas as pd
df = pd.read_csv('data\manual_session.csv')
print('Attack IDs present:', df.ATTACK_ID.unique())
"

REM If you see only [0, 11, 8] but you ran 5 attack types,
REM you forgot to write metadata for the missing ones.
```

**Solution**: Always use the 3-command pattern:
1. Write metadata
2. Run attack
3. Reset metadata

---

### Problem: Metadata file is empty or corrupt

```cmd
type attack_metadata.json

REM If you see: "" or garbage, recreate it:
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
```

---

### Problem: UnicodeEncodeError when writing metadata

```cmd
REM ERROR: 'charmap' codec can't encode character...

REM Solution: Always use encoding='utf-8' in your manual commands:
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':11,'ATTACK_NAME':'pH Manipulation Attack','MITRE_ID':'T0836'}))"
                                                      ^^^^^^^^^^^^^^
                                                      Add this!
```

---

### Problem: Logger shows old attack ID even after reset

**Cause**: File read/write race condition (very rare).

**Solution**: Add 1-second delay after writing metadata:

```cmd
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':11,'ATTACK_NAME':'pH Manipulation Attack','MITRE_ID':'T0836'}))"

timeout /T 1

python attacks\command_injection.py --host 192.168.1.100 --attack ph_manipulation --target-ph 5.0 --duration 90
```

---

## BATCH FILE TEMPLATE FOR MANUAL SESSION

Save as `my_session.bat`:

```batch
@echo off
chcp 65001 >nul
REM UTF-8 code page for Unicode support

echo ============================================
echo  Manual Attack Session with Metadata
echo ============================================

echo [%TIME%] Initializing metadata...
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"

echo [%TIME%] Waiting 3 minutes for baseline...
timeout /T 180 /NOBREAK

echo.
echo [%TIME%] ATTACK 1: pH Manipulation (2 min)
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':11,'ATTACK_NAME':'pH Manipulation Attack','MITRE_ID':'T0836'}))"
python attacks\command_injection.py --host 192.168.1.100 --attack ph_manipulation --target-ph 4.8 --duration 120
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
echo [%TIME%] Attack 1 done, waiting 2 min...
timeout /T 120 /NOBREAK

echo.
echo [%TIME%] ATTACK 2: Tank Overflow (3 min)
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':8,'ATTACK_NAME':'Tank Overflow Attack','MITRE_ID':'T0836'}))"
python attacks\command_injection.py --host 192.168.1.100 --attack tank_overflow --duration 180
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
echo [%TIME%] Attack 2 done, waiting 2 min...
timeout /T 120 /NOBREAK

echo.
echo [%TIME%] ATTACK 3: Slow Ramp (5 min stealth)
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':12,'ATTACK_NAME':'Slow Ramp Attack','MITRE_ID':'T0836'}))"
python attacks\command_injection.py --host 192.168.1.100 --attack slow_ramp --start-value 500 --end-value 850 --duration 300
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
echo [%TIME%] Attack 3 done, waiting 3 min...
timeout /T 180 /NOBREAK

echo.
echo [%TIME%] SESSION COMPLETE
echo.
echo Verify results:
python -c "import pandas as pd; df=pd.read_csv('data/manual_session.csv'); print(f'Total: {len(df)} rows'); print(df.ATTACK_NAME.value_counts())"

pause
```

Run while logger is active:
```cmd
my_session.bat
```

---

## SUMMARY

### The 3-Command Pattern (Manual Attacks)

Every manual attack follows this pattern:

```cmd
# 1. LABEL (write metadata)
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':XX,'ATTACK_NAME':'YYY','MITRE_ID':'ZZZ'}))"

# 2. ATTACK (execute)
python attacks\command_injection.py --host IP --attack TYPE --duration N

# 3. RESET (clear label)
python -c "import json; open('attack_metadata.json','w',encoding='utf-8').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
```

### Attack ID Reference

| ID | Attack Name | MITRE |
|----|-------------|-------|
| 0 | Normal | None |
| 8 | Tank Overflow Attack | T0836 |
| 9 | Chemical Depletion Attack | T0836 |
| 10 | Membrane Damage Attack | T0836 |
| 11 | pH Manipulation Attack | T0836 |
| 12 | Slow Ramp Attack | T0836 |
| 16 | Valve Manipulation Attack | T0836 |
| 17 | Multi-Variable Stealth | T0856 |

### Key Files

| File | Purpose | Encoding |
|------|---------|----------|
| `attack_metadata.json` | Current attack state (IPC) | UTF-8 |
| `execution_details.log` | Automation log | UTF-8 |
| `attack_timeline.log` | Analysis report | UTF-8 |
| `master_dataset.csv` | Data with labels | UTF-8 (BOM) |

All fixed for Windows Unicode support!