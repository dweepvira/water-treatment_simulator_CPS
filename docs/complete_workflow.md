# COMPLETE PROJECT WORKFLOW - DETAILED IN-DEPTH GUIDE

## TABLE OF CONTENTS

1. [Project Overview](#project-overview)
2. [System Architecture](#system-architecture)
3. [Complete Data Flow](#complete-data-flow)
4. [Cross-Platform Issues & Solutions](#cross-platform-issues--solutions)
5. [Attack Metadata Problem Explained](#attack-metadata-problem-explained)
6. [Windows-Specific Setup](#windows-specific-setup)
7. [Step-by-Step Execution](#step-by-step-execution)
8. [Troubleshooting Guide](#troubleshooting-guide)

---

## PROJECT OVERVIEW

### What This Project Does

**Purpose**: Automated generation of labeled cybersecurity datasets for Industrial Control Systems (ICS) using a real SWAT water treatment simulation.

**Goal**: Create ML-ready datasets with:
- Normal operation data
- Attack scenarios
- Automatic labeling (ATTACK_ID, ATTACK_NAME, MITRE_ID)
- 78 process variables per sample

**Output**: CSV files ready for training anomaly detection / attack classification models.

---

## SYSTEM ARCHITECTURE

### Component Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                    AUTOMATION SCRIPT                         │
│  (automated_dataset_generator_v2.py)                        │
│                                                               │
│  - Generates attack schedule                                 │
│  - Manages attack metadata file                              │
│  - Spawns logger & attack processes                          │
└───────────────────┬──────────────────┬─────────────────────┘
                    │                  │
        ┌───────────▼─────────┐  ┌────▼───────────────┐
        │   DATA LOGGER       │  │  ATTACK SCRIPTS    │
        │  (subprocess)       │  │  (subprocesses)    │
        │                     │  │                    │
        │  - Polls PLC        │  │  - Execute attack  │
        │  - Reads metadata   │  │  - Update metadata │
        │  - Writes CSV       │  │  - Wait duration   │
        └──────────┬──────────┘  └─────┬──────────────┘
                   │                   │
                   │   ┌───────────────▼───────────────┐
                   │   │  ATTACK METADATA FILE         │
                   │   │  (attack_metadata.json)       │
                   │   │                               │
                   └───► SHARED STATE (File-based IPC)│
                       │  - ATTACK_ID                  │
                       │  - ATTACK_NAME                │
                       │  - MITRE_ID                   │
                       └───────────────┬───────────────┘
                                       │
                                       ▼
                               ┌──────────────┐
                               │  CSV OUTPUT  │
                               │              │
                               │  78 columns  │
                               │  + metadata  │
                               └──────────────┘
```

### Key Components

**1. Automation Script** (`automated_dataset_generator_v2.py`)
- **Role**: Orchestrator
- **Lifecycle**: Runs entire 2 hours
- **Responsibilities**:
  - Generate random attack schedule
  - Start logger subprocess
  - Launch attack subprocesses at scheduled times
  - Manage metadata file
  - Split final CSV

**2. Data Logger** (`data_logger_cross_platform.py`)
- **Role**: Continuous data collection
- **Lifecycle**: Runs entire 2 hours
- **Responsibilities**:
  - Poll PLC every 1 second (bulk reads)
  - Read attack metadata from JSON file
  - Write CSV rows with proper labels
  - Handle connection errors

**3. Attack Scripts** (`command_injection.py`, etc.)
- **Role**: Execute specific attacks
- **Lifecycle**: Runs for attack duration only (30-180s)
- **Responsibilities**:
  - Connect to PLC
  - Execute malicious Modbus writes
  - Complete and exit

**4. Metadata File** (`attack_metadata.json`)
- **Role**: Inter-process communication
- **Lifecycle**: Entire 2 hours
- **Content**:
```json
{
  "ATTACK_ID": 8,
  "ATTACK_NAME": "Tank Overflow Attack",
  "MITRE_ID": "T0836",
  "timestamp": "2026-02-13T10:08:12"
}
```

---

## COMPLETE DATA FLOW

### Detailed Timeline Example

**Time 0:00 - System Initialization**
```
1. automation_script.py starts
2. Creates automated_dataset/ directory
3. Generates random attack schedule:
   - Attack 1: Tank Overflow at 8min 12s for 60s
   - Attack 2: Chemical Depletion at 15min 37s for 120s
   - Attack 3: pH Manipulation at 23min 18s for 90s
   ...
4. Initializes metadata file:
   {"ATTACK_ID": 0, "ATTACK_NAME": "Normal", "MITRE_ID": "None"}
```

**Time 0:03 - Logger Starts**
```
5. automation_script spawns logger subprocess:
   python data_logger_cross_platform.py \
     --host 192.168.1.100 \
     --metadata-file automated_dataset/attack_metadata.json \
     --output automated_dataset/master_dataset.csv

6. Logger initializes:
   - Connects to PLC
   - Opens CSV file
   - Creates metadata file reader
   - Enters polling loop
```

**Time 0:04 - Normal Operation Begins**
```
7. Logger polls every 1 second:
   
   Poll #1:
   - Bulk read 51 registers (1 Modbus call)
   - Bulk read 25 coils (1 Modbus call)
   - Read metadata file: {"ATTACK_ID": 0, ...}
   - Write CSV row:
     2026-02-13T10:00:04,5,500,1,True,...,0,Normal,None
   
   Poll #2:
   - Bulk read registers
   - Bulk read coils
   - Read metadata: ATTACK_ID still 0
   - Write CSV row: ...,0,Normal,None
   
   ... continues every second
```

**Time 8:12 - Attack 1 Starts**
```
8. automation_script detects attack time:
   elapsed = 492 seconds
   next_attack['start_time'] = 492 seconds
   
9. automation_script updates metadata file:
   {
     "ATTACK_ID": 8,
     "ATTACK_NAME": "Tank Overflow Attack",
     "MITRE_ID": "T0836"
   }
   
10. automation_script spawns attack subprocess:
    python attacks/command_injection.py \
      --host 192.168.1.100 \
      --attack tank_overflow \
      --duration 60
   
11. Attack subprocess executes:
    - Connects to PLC
    - Every 2 seconds for 60 seconds:
      * Write 1000 to LIT_101/301/401 (registers)
      * Write False to P_101/301/401/501 (coils)
    - Exits after 60 seconds
```

**Time 8:12 - Logger Sees Attack (Same Time)**
```
12. Logger's next poll (happening every 1 second):
    
    Poll #492:
    - Bulk read registers: LIT_101=1000, LIT_301=1000, ...
    - Bulk read coils: P_101=False, P_301=False, ...
    - Read metadata file: {"ATTACK_ID": 8, "ATTACK_NAME": "Tank Overflow Attack", ...}
    - Write CSV row:
      2026-02-13T10:08:12,5,1000,0,False,...,8,Tank Overflow Attack,T0836
                                              ^  ^^^^^^^^^^^^^^^^^^^^^  ^^^^^
                                              |          |                |
                                        ATTACK_ID    ATTACK_NAME      MITRE_ID
    
    Poll #493:
    - Bulk read: Still attacking (LIT_101=1000, P_101=False)
    - Read metadata: Still {"ATTACK_ID": 8, ...}
    - Write CSV: ...,8,Tank Overflow Attack,T0836
    
    ... continues for 60 seconds
```

**Time 9:12 - Attack 1 Ends**
```
13. Attack subprocess completes (60 seconds elapsed)
    - Attack process exits
    
14. automation_script resets metadata:
    {
      "ATTACK_ID": 0,
      "ATTACK_NAME": "Normal",
      "MITRE_ID": "None"
    }
```

**Time 9:13 - Return to Normal**
```
15. Logger's next poll:
    
    Poll #553:
    - Bulk read registers: LIT_101=995 (draining), ...
    - Bulk read coils: P_101=True (PLC resumed control), ...
    - Read metadata: {"ATTACK_ID": 0, "ATTACK_NAME": "Normal", ...}
    - Write CSV: ...,0,Normal,None
    
    ... normal operation continues
```

**Time 15:37 - Attack 2 Starts**
```
16. Process repeats for Attack 2 (Chemical Depletion):
    - Update metadata: ATTACK_ID=9
    - Spawn attack subprocess
    - Logger reads new metadata
    - CSV rows labeled with ATTACK_ID=9
```

**Time 2:00:00 - Completion**
```
17. automation_script finalization:
    - Stops logger subprocess
    - Resets metadata to 0
    - Loads master CSV
    - Splits into:
      * normal_only.csv (ATTACK_ID==0 rows)
      * attacks_only.csv (ATTACK_ID>0 rows)
    - Generates analysis report
```

---

## CROSS-PLATFORM ISSUES & SOLUTIONS

### Problem 1: Process Group Handling

**Original Code (Linux-only)**:
```python
# This FAILS on Windows
self.logger_process = subprocess.Popen(
    cmd,
    preexec_fn=os.setsid  # AttributeError on Windows!
)
```

**Why it fails**: `os.setsid()` doesn't exist on Windows.

**Solution (Cross-platform)**:
```python
# This WORKS on all platforms
self.logger_process = subprocess.Popen(
    cmd,
    # No preexec_fn needed
)
```

---

### Problem 2: Process Termination

**Original Code (Linux)**:
```python
# SIGTERM doesn't work on Windows
os.killpg(os.getpgid(process.pid), signal.SIGTERM)
```

**Solution (Cross-platform)**:
```python
import platform

if platform.system() == 'Windows':
    process.terminate()  # Windows-friendly
else:
    process.terminate()  # Unix SIGTERM

process.wait(timeout=10)
```

---

### Problem 3: Path Separators

**Original Code**:
```python
# Hardcoded forward slash - breaks on Windows
cmd = ['python', 'logging/data_logger.py']
```

**Solution**:
```python
from pathlib import Path

# Cross-platform paths
cmd = ['python', str(Path('logging') / 'data_logger.py')]
```

---

### Problem 4: Signal Handling

**Original Code**:
```python
# SIGTERM not available on Windows
signal.signal(signal.SIGTERM, handler)
```

**Solution**:
```python
signal.signal(signal.SIGINT, handler)  # Works everywhere

try:
    signal.signal(signal.SIGTERM, handler)  # Try for Unix
except AttributeError:
    pass  # Skip on Windows
```

---

## ATTACK METADATA PROBLEM EXPLAINED

### The Original Problem

**Symptom**: CSV has all ATTACK_ID=0, no attack labels

**Root Cause**: Process isolation

```
Process 1: automation_script.py
├─ Local variable: attack_metadata = AttackMetadata()
│
└─ Spawns Process 2: logger subprocess
   └─ Has its OWN memory space
      └─ Cannot see Process 1's attack_metadata variable!

└─ Spawns Process 3: attack subprocess
   └─ Has its OWN memory space
      └─ Cannot see Process 1's attack_metadata variable!
```

**What happened**:
1. automation_script creates `attack_metadata` object
2. automation_script spawns logger as SEPARATE PROCESS
3. Logger tries to access `attack_metadata` → **doesn't exist in logger's memory!**
4. Logger writes ATTACK_ID=0 for all rows

**Why it worked in my testing but not yours**:
- I tested on Linux with fork()
- fork() copies parent memory (copy-on-write)
- Windows uses spawn() which creates fresh process
- Fresh process has no shared memory

---

### The Solution: File-Based IPC

**Instead of shared memory, use a file**:

```
┌─────────────────────────────────────────────┐
│         attack_metadata.json                │
│  (JSON file on disk - ALL processes can     │
│   read/write this file)                     │
│                                              │
│  {"ATTACK_ID": 8,                           │
│   "ATTACK_NAME": "Tank Overflow",           │
│   "MITRE_ID": "T0836"}                      │
│                                              │
└─────▲──────────────────────────────▲────────┘
      │                              │
      │ Write                        │ Read
      │                              │
┌─────┴──────────────┐    ┌──────────┴─────────┐
│  automation_script │    │  logger subprocess │
│                    │    │                    │
│  Before attack:    │    │  Every poll:       │
│    Write ID=8      │    │    Read file       │
│                    │    │    Get ID=8        │
│  After attack:     │    │    Write to CSV    │
│    Write ID=0      │    │                    │
└────────────────────┘    └────────────────────┘
```

**Why this works**:
- File is on disk
- All processes can access disk
- No shared memory needed
- Works on Windows, Linux, Mac

---

### Implementation Details

**automation_script writes**:
```python
# automated_dataset_generator_v2.py

def execute_attack(self, attack_event):
    # BEFORE launching attack subprocess
    self.metadata.update(
        attack_id=8,
        attack_name='Tank Overflow Attack',
        mitre_id='T0836'
    )
    
    # Now spawn attack subprocess
    subprocess.Popen(...)
    
    # Wait for attack to complete
    process.wait()
    
    # AFTER attack completes
    self.metadata.update(0, 'Normal', 'None')
```

**Logger reads**:
```python
# data_logger_cross_platform.py

def poll_system(self):
    # Read all sensors
    data = {...}
    
    # Read metadata from file
    attack_info = self.attack_metadata.get_current_attack_info()
    # Returns: {'ATTACK_ID': 8, 'ATTACK_NAME': '...', 'MITRE_ID': '...'}
    
    # Add to row
    data.update(attack_info)
    
    # Write to CSV
    csv_logger.log_row(data)
```

**Metadata file class**:
```python
class AttackMetadataFile:
    def __init__(self, filepath='attack_metadata.json'):
        self.filepath = Path(filepath)
    
    def update(self, attack_id, attack_name, mitre_id):
        """Write attack info (called by automation_script)"""
        data = {
            'ATTACK_ID': attack_id,
            'ATTACK_NAME': attack_name,
            'MITRE_ID': mitre_id
        }
        with open(self.filepath, 'w') as f:
            json.dump(data, f)
    
    def read(self):
        """Read attack info (called by logger)"""
        with open(self.filepath, 'r') as f:
            return json.load(f)
```

---

## WINDOWS-SPECIFIC SETUP

### Install Python

```cmd
REM Download Python 3.11+ from python.org
REM Install with "Add to PATH" checked

REM Verify installation
python --version
REM Should show: Python 3.11.x

pip --version
REM Should show: pip 23.x
```

### Install Dependencies

```cmd
REM Open Command Prompt as Administrator

pip install pymodbus pandas numpy

REM Verify
python -c "import pymodbus; print('OK')"
python -c "import pandas; print('OK')"
python -c "import numpy; print('OK')"
```

### Setup Project

```cmd
REM Extract framework to C:\swat_OPTIMIZED\

cd C:\swat_OPTIMIZED

REM Verify structure
dir
REM Should show:
REM  logging\
REM  attacks\
REM  config\
REM  utils\
REM  automated_dataset_generator_v2.py
REM  data_logger_cross_platform.py
```

### Configure PLC IP

```cmd
notepad config\swat_config.py

REM Edit line:
REM MODBUS_CONFIG = {
REM     'host': '192.168.1.100',  <-- Change to your PLC IP
REM     ...
REM }
```

### Test Connection

```cmd
REM Test ping
ping 192.168.1.100

REM Test Modbus port (requires telnet client)
REM Or use:
python -c "import socket; s=socket.socket(); s.connect(('192.168.1.100', 502)); print('OK')"
```

---

## STEP-BY-STEP EXECUTION

### Windows Command Prompt Steps

**Step 1: Open Command Prompt**
```cmd
REM Press Win+R
REM Type: cmd
REM Press Enter
```

**Step 2: Navigate to Project**
```cmd
cd C:\swat_OPTIMIZED
```

**Step 3: Run Automation (Short Test)**
```cmd
REM 10-minute test (5min normal + 5min attack)
python automated_dataset_generator_v2.py ^
  --host 192.168.1.100 ^
  --total 10 ^
  --normal 5 ^
  --attack 5

REM Note: ^ is line continuation in Windows CMD
REM In PowerShell, use ` instead
```

**Step 4: Monitor Execution**
```cmd
REM Open second Command Prompt window
cd C:\swat_OPTIMIZED\automated_dataset

REM Watch log file
type execution_details.log

REM Or watch in real-time with PowerShell:
powershell Get-Content execution_details.log -Wait
```

**Step 5: Check Output**
```cmd
REM After completion (10 minutes)
cd automated_dataset
dir

REM Should see:
REM  master_dataset.csv
REM  normal_only.csv
REM  attacks_only.csv
REM  attack_timeline.log
REM  execution_details.log
REM  attack_metadata.json
```

**Step 6: Verify Attack Data**
```cmd
REM Count total rows
python -c "import pandas as pd; df=pd.read_csv('automated_dataset/master_dataset.csv'); print(f'Total rows: {len(df)}')"

REM Count attack rows
python -c "import pandas as pd; df=pd.read_csv('automated_dataset/master_dataset.csv'); print(f'Attack rows: {(df.ATTACK_ID>0).sum()}')"

REM Show attack distribution
python -c "import pandas as pd; df=pd.read_csv('automated_dataset/master_dataset.csv'); print(df.ATTACK_NAME.value_counts())"
```

---

## TROUBLESHOOTING GUIDE

### Issue 1: No Attack Rows in CSV

**Symptom**:
```
Attack rows: 0
All rows have ATTACK_ID=0
```

**Diagnosis**:
```cmd
REM Check if metadata file was created
dir automated_dataset\attack_metadata.json

REM Check metadata file content
type automated_dataset\attack_metadata.json
REM Should show JSON with ATTACK_ID

REM Check if logger used metadata file
findstr /C:"metadata" automated_dataset\execution_details.log
```

**Solution 1**: Use v2 scripts
```cmd
REM Make sure you're using:
python automated_dataset_generator_v2.py  (not v1)
python logging\data_logger_cross_platform.py  (not data_logger_optimized.py)
```

**Solution 2**: Manually pass metadata file
```cmd
REM Start logger with metadata file explicitly
python logging\data_logger_cross_platform.py ^
  --host 192.168.1.100 ^
  --metadata-file automated_dataset\attack_metadata.json ^
  --output test.csv
```

---

### Issue 2: Logger Doesn't Start

**Symptom**:
```
Logger failed to start!
```

**Diagnosis**:
```cmd
REM Try running logger manually
python logging\data_logger_cross_platform.py --host 192.168.1.100 --duration 10

REM Check for errors
```

**Common Causes**:

**A. Import Error**:
```
ModuleNotFoundError: No module named 'pymodbus'
```
Solution:
```cmd
pip install pymodbus pandas numpy
```

**B. Connection Error**:
```
Failed to connect
```
Solution:
```cmd
ping 192.168.1.100
REM If fails, check PLC IP configuration
```

**C. File Path Error**:
```
FileNotFoundError: config\swat_config.py
```
Solution:
```cmd
REM Verify directory structure
dir config
dir logging
dir attacks
```

---

### Issue 3: Attack Subprocess Fails

**Symptom**:
```
Attack launched but no Modbus writes
```

**Diagnosis**:
```cmd
REM Run attack manually
python attacks\command_injection.py ^
  --host 192.168.1.100 ^
  --attack tank_overflow ^
  --duration 10

REM Watch for errors
```

**Common Causes**:

**A. Modbus Write Fails**:
```
Modbus error writing register
```
Solution: Check PLC write permissions

**B. Wrong Addresses**:
```
Illegal data address
```
Solution: Verify register/coil addresses in config

---

### Issue 4: CSV Half Empty

**Symptom**:
```
Total rows: 300 (expected 600 for 10min test)
```

**Diagnosis**:
```cmd
REM Check logger was running entire time
findstr /C:"Progress" automated_dataset\execution_details.log
```

**Common Causes**:

**A. Logger Crashed**:
Solution: Check execution_details.log for errors

**B. Connection Lost**:
Solution: Check network stability

**C. Disk Full**:
```cmd
REM Check disk space
dir C:\ | findstr "bytes free"
```

---

### Issue 5: Python Subprocess Errors on Windows

**Symptom**:
```
FileNotFoundError: [WinError 2] The system cannot find the file specified
```

**Solution**:
```python
# Use sys.executable instead of 'python'
cmd = [sys.executable, 'script.py']  # Not ['python', 'script.py']
```

---

## VERIFICATION CHECKLIST

After running automation, verify:

```cmd
REM 1. Check all files exist
dir automated_dataset
REM Expected: 6 files

REM 2. Check master CSV has data
python -c "import pandas as pd; print(len(pd.read_csv('automated_dataset/master_dataset.csv')))"
REM Expected: ~600 rows for 10min test

REM 3. Check attack rows exist
python -c "import pandas as pd; df=pd.read_csv('automated_dataset/master_dataset.csv'); print((df.ATTACK_ID>0).sum())"
REM Expected: >0 (should be ~300 for 50% attack ratio)

REM 4. Check attack distribution
python -c "import pandas as pd; df=pd.read_csv('automated_dataset/master_dataset.csv'); print(df.ATTACK_NAME.value_counts())"
REM Expected: Multiple attack types listed

REM 5. Check timeline
type automated_dataset\attack_timeline.log
REM Expected: List of attacks with times
```

---

**Complete workflow documented. Use `automated_dataset_generator_v2.py` and `data_logger_cross_platform.py` for Windows compatibility!**