# IN-DEPTH LOGGING SYSTEM ANALYSIS
# SWAT Framework — data_logger.py Complete Guide
# ═══════════════════════════════════════════════════════════════════════════════

---

## TABLE OF CONTENTS

1. [What the Logger Is](#1-what-the-logger-is)
2. [Why Each Design Choice Was Made](#2-why-each-design-choice-was-made)
3. [How Every Internal Component Works](#3-how-every-internal-component-works)
4. [End-to-End Data Flow (Second by Second)](#4-end-to-end-data-flow-second-by-second)
5. [CSV Output — Every Column Explained](#5-csv-output--every-column-explained)
6. [How It Helps ML / Dataset Quality](#6-how-it-helps-ml--dataset-quality)
7. [AUTOMATED Logging — Every Command Step by Step](#7-automated-logging--every-command-step-by-step)
8. [MANUAL Logging — Every Command Step by Step](#8-manual-logging--every-command-step-by-step)
9. [Manual Attack Labeling During Live Logging](#9-manual-attack-labeling-during-live-logging)
10. [Verifying Your Data After Collection](#10-verifying-your-data-after-collection)
11. [Troubleshooting Every Possible Error](#11-troubleshooting-every-possible-error)

---

## 1. WHAT THE LOGGER IS

`data_logger.py` is a **continuous Modbus poller** that reads every process
variable in the SWAT water treatment plant once per second and writes it to a
CSV file — with automatic attack labeling baked in.

### One-sentence summary of each layer

| Layer | File | Role |
|-------|------|------|
| Modbus client | `modbus_utils_optimized.py` | TCP connection to PLC |
| Bulk reader | `data_logger.py` | Read 51 registers + 25 coils in 2 calls |
| Metadata reader | `attack_metadata.json` | Tells logger which attack is active right now |
| CSV writer | `CSVLogger` class | Buffers rows, flushes to disk every 100 rows |
| Scaler | `DataScaler` class | Converts raw integers to physical units |

### What it produces

One CSV row per second.
78 columns per row.

```
Timestamp | 51 sensor readings | 25 pump/valve states | ATTACK_ID | ATTACK_NAME | MITRE_ID
```

That is your complete machine-learning dataset. Nothing else is needed.

---

## 2. WHY EACH DESIGN CHOICE WAS MADE

### 2.1  Bulk Reading (2 calls instead of 76)

**Old way — 76 individual calls:**
```
call 1  → read FIT_101   (register 0)   ~10ms
call 2  → read LIT_101   (register 1)   ~10ms
call 3  → read MV_101    (register 2)   ~10ms
...
call 51 → read last reg                 ~10ms
call 52 → read P_101     (coil 0)       ~10ms
...
call 76 → read last coil                ~10ms

Total per poll: 76 × 10ms = 760ms minimum
```

Problems with this:
- You can NEVER poll faster than ~1 Hz  
- Readings taken 760ms apart are NOT from the same time instant
- You're sending 76 TCP requests per second, stressing the PLC
- Windows adds extra TCP overhead → easily 1500ms+ per poll

**New way — 2 bulk calls:**
```
call 1  → read registers 0-50   (all 51 at once)   ~40ms
call 2  → read coils 0-24       (all 25 at once)   ~20ms

Total per poll: 60ms
```

Benefits:
- 38× fewer network requests
- All 76 values captured within 60ms of each other (near-simultaneous)
- PLC handles 2 requests/second instead of 76
- You can now poll at 10 Hz if needed

---

### 2.2  File-Based Attack Metadata (Windows IPC)

**The problem on Windows:**

When Python spawns a subprocess on Windows, that subprocess gets a completely
separate memory space. Shared objects in the parent process are NOT visible to
the child.

```
Parent process (automated_dataset_generator.py)
    └─ self.attack_id = 8   ← exists only in parent's RAM
    
Child process (data_logger.py subprocess)
    └─ sees nothing from parent's RAM
    └─ self.attack_id = 0   ← always 0, result: blank attack labels
```

**The solution — a tiny JSON file on disk:**

```
Parent writes:  attack_metadata.json  {"ATTACK_ID": 8, "ATTACK_NAME": "..."}
Child reads:    attack_metadata.json  → gets ATTACK_ID = 8
```

Both processes can always access the disk. No shared memory needed. Works
identically on Windows, Linux, and Mac.

---

### 2.3  CSV Buffering (100-row buffer)

Writing one CSV row to disk 1× per second = 3600 disk writes per hour.

Each disk write on Windows involves:
- File open
- Seek to end
- Write bytes
- Flush
- File close

That is ~5ms overhead per write = 18 seconds of disk overhead per hour.

With buffering: accumulate 100 rows in RAM, write once.
That is 36 writes per hour instead of 3600. Disk overhead drops to 0.18 seconds.

Also protects against disk fragmentation from many tiny writes.

---

### 2.4  Pre-Built Address Maps (O(1) lookup)

After each bulk read you have an array of 51 raw integers.
You need to turn `array[4] = 720` into `{'AIT_202': 7.20}`.

Without pre-building the map, every poll does this:
```python
for var_name, reg_info in HOLDING_REGISTERS.items():   # iterate 51 items
    address = reg_info['address']                       # dict lookup
    scale   = reg_info.get('scale', 1)                 # dict lookup
    offset  = address - min_addr                        # arithmetic
    raw     = bulk_data[offset]                         # array index
    data[var_name] = raw / scale
```

With pre-built map (built once at startup):
```python
# self.register_map = {0: ('FIT_101', 1, 'm3/h'),
#                      1: ('LIT_101', 1, 'L'),
#                      4: ('AIT_202', 100, 'pH'), ...}

for addr, (var_name, scale, unit) in self.register_map.items():
    data[var_name] = bulk_data[addr - min_addr] / scale
```

Same logic, but the dictionary structure is already in the ideal form.
At 10 Hz logging that difference compounds: saves ~2ms per poll.

---

### 2.5  Atomic Snapshots

In the old individual-read approach, `LIT_101` was read at t=0ms and `LIT_301`
was read at t=200ms. These two timestamps are different. If a pump changes state
between those reads, your dataset captures a physically impossible state.

With bulk reads:
- All 51 register values are captured in a single Modbus response at the same instant
- All 25 coil values captured in the next response 40ms later
- Maximum time spread between any two values: 60ms (one poll cycle)

For a water treatment plant with second-scale dynamics, 60ms is effectively
simultaneous. Your mass balance equations hold. Your ML model trains on
physically consistent states.

---

## 3. HOW EVERY INTERNAL COMPONENT WORKS

### 3.1  SWATDataLoggerOptimized Class

This is the main class. Here is what each method does and why.

#### `__init__`  — Initialisation

```python
def __init__(self, config=None, metadata_file=None):
    self.config = config or MODBUS_CONFIG   # host, port, timeout, retries
    self.running = False                    # flag for graceful shutdown
    
    self.modbus = ModbusClient(...)         # TCP connection object
    self.csv_logger = CSVLogger(...)        # buffered file writer
    self.validator = DataValidator(...)     # range/rate checks
    self.scaler = DataScaler()              # raw int → physical value
    
    # File-based metadata (Windows-safe)
    self.attack_metadata = AttackMetadataFileReader(metadata_file)
    
    self._build_address_maps()              # build O(1) lookup dicts
```

Why `running = False` and not `True`? It is only set True inside `run()`,
after the connection is confirmed. This prevents the poll loop starting before
the TCP socket is ready.

---

#### `_build_address_maps`  — Pre-computes Lookup Tables

```python
def _build_address_maps(self):
    self.register_map = {}   # {modbus_address: (variable_name, scale, unit)}
    self.coil_map     = {}   # {modbus_address: variable_name}
    
    for var_name, reg_info in HOLDING_REGISTERS.items():
        addr  = reg_info['address']
        scale = reg_info.get('scale', 1)
        unit  = reg_info.get('unit', '')
        self.register_map[addr] = (var_name, scale, unit)
    
    for var_name, coil_info in COILS.items():
        addr = coil_info['address']
        self.coil_map[addr] = var_name
```

This runs **once** at startup. Result for SWAT:
- `register_map` has 51 entries, addresses 0–50
- `coil_map` has 25 entries, addresses 0–24

Every subsequent poll can now look up any variable in O(1) time using its
Modbus address as the key.

---

#### `read_all_registers_bulk`  — Single Modbus FC3 Call

```python
def read_all_registers_bulk(self):
    max_addr = max(self.register_map.keys())   # 50
    min_addr = min(self.register_map.keys())   # 0
    count    = max_addr - min_addr + 1         # 51
    
    result = self.modbus.read_holding_registers(min_addr, count=count)
    # result = [5, 500, 1, 500, 720, 490, ...]   ← raw integers
    
    for addr, (var_name, scale, unit) in self.register_map.items():
        offset          = addr - min_addr          # e.g. addr=4 → offset=4
        raw_value       = result[offset]           # e.g. 720
        physical_value  = raw_value / scale        # 720 / 100 = 7.20
        data[var_name]  = physical_value           # {'AIT_202': 7.20}
    
    return data
```

**Modbus Function Code 3** (Read Holding Registers) supports reading up to
125 registers per request. SWAT uses 51 → well within the limit.

The PLC responds with one TCP packet containing all 51 values as 16-bit
unsigned integers. That one packet is unpacked into the full dictionary.

Scaling conversions:
- pH sensors:          raw / 100   → e.g. 720 → 7.20 pH
- Temperature:         raw / 10    → e.g. 253 → 25.3 °C
- Pressure:            raw / 10    → e.g. 1000 → 100.0 bar
- Flow, level, counts: raw / 1     → stored as-is (integer engineering units)

---

#### `read_all_coils_bulk`  — Single Modbus FC1 Call

```python
def read_all_coils_bulk(self):
    max_addr = max(self.coil_map.keys())   # 24
    min_addr = min(self.coil_map.keys())   # 0
    count    = max_addr - min_addr + 1     # 25
    
    result = self.modbus.read_coils(min_addr, count=count)
    # result = [True, False, False, True, ...]   ← booleans
    
    for addr, var_name in self.coil_map.items():
        offset       = addr - min_addr
        data[var_name] = bool(result[offset])
    
    return data
```

**Modbus Function Code 1** (Read Coils) returns bits packed into bytes.
pymodbus unpacks them into a Python list of booleans automatically.

Each coil represents a digital output — pump running/stopped,
valve open/closed, alarm active/inactive.

---

#### `poll_system`  — Assembles One Complete Row

```python
def poll_system(self):
    data = {'Timestamp': timestamp_to_str()}   # e.g. '2026-02-13T10:08:12'
    
    register_data = self.read_all_registers_bulk()   # 51 values, 1 call
    data.update(register_data)
    
    coil_data = self.read_all_coils_bulk()           # 25 values, 1 call
    data.update(coil_data)
    
    attack_info = self.attack_metadata.get_current_attack_info()
    data.update(attack_info)   # ATTACK_ID, ATTACK_NAME, MITRE_ID
    
    return data
    # data is now 78 key-value pairs → one CSV row
```

Total time: ~60ms. The remaining ~940ms in a 1-second interval is `time.sleep()`.

---

#### `run`  — Main Poll Loop

```python
def run(self, duration=None, poll_interval=None):
    self.connect()
    self.running = True
    start_time = time.time()
    
    while self.running:
        if duration and (time.time() - start_time) >= duration:
            break                        # stop after N seconds
        
        poll_start = time.time()
        data = self.poll_system()        # takes ~60ms
        
        if data:
            self.log_data(data)          # adds to 100-row buffer
        
        elapsed    = time.time() - poll_start
        sleep_time = max(0, poll_interval - elapsed)
        time.sleep(sleep_time)           # sleep remainder of 1 second
```

The `max(0, ...)` prevents negative sleep if a poll takes longer than 1 second
(e.g. due to a network retry). Without this, Python would raise a ValueError.

---

#### `AttackMetadataFileReader`  — Cross-Process Label Reader

```python
class AttackMetadataFileReader:
    def get_current_attack_info(self):
        try:
            with open(self.filepath, 'r') as f:
                data = json.load(f)
                self.last_data = {
                    'ATTACK_ID':   data.get('ATTACK_ID',   0),
                    'ATTACK_NAME': data.get('ATTACK_NAME', 'Normal'),
                    'MITRE_ID':    data.get('MITRE_ID',    'None')
                }
                return self.last_data
        except:
            return self.last_data   # on any error, return last known state
```

Why the `try/except` returning `last_data`?
- The automation script may be writing to the JSON file at the exact moment
  the logger tries to read it (race condition)
- On Windows, a partial write can corrupt the JSON temporarily
- Returning the last known state means one poll row gets the wrong label
  at worst — far better than crashing

---

## 4. END-TO-END DATA FLOW (SECOND BY SECOND)

```
Second 1:
┌─────────────────────────────────────────────────────────┐
│  Logger wakes up                                        │
│  ↓                                                      │
│  read_holding_registers(0, count=51)  ──► PLC          │
│  PLC returns: [5, 500, 1, 500, 720, ...]  ◄──           │
│  Decode: FIT_101=5, LIT_101=500, AIT_202=7.20 ...       │
│  ↓                                                      │
│  read_coils(0, count=25)  ──► PLC                      │
│  PLC returns: [T, F, F, T, T, F, ...]  ◄──              │
│  Decode: P_101=True, P_102=False ...                    │
│  ↓                                                      │
│  open(attack_metadata.json)                             │
│  {"ATTACK_ID": 0, "ATTACK_NAME": "Normal"} ← normal    │
│  ↓                                                      │
│  Assemble row: {Timestamp, all 76 values, 0, Normal, …} │
│  ↓                                                      │
│  Append to 100-row RAM buffer                           │
│  ↓                                                      │
│  sleep(0.94s)                                           │
└─────────────────────────────────────────────────────────┘

Second 493 (attack begins):
┌─────────────────────────────────────────────────────────┐
│  Automation script WRITES attack_metadata.json:         │
│  {"ATTACK_ID": 8, "ATTACK_NAME": "Tank Overflow"}       │
│  ↓                                                      │
│  Logger wakes up for next poll                          │
│  Bulk reads: LIT_101=520, P_101=False (being forced)    │
│  open(attack_metadata.json)                             │
│  → {"ATTACK_ID": 8, "ATTACK_NAME": "Tank Overflow"}     │
│  ↓                                                      │
│  Assemble row: {Timestamp, LIT_101=520, P_101=False,    │
│                 ..., ATTACK_ID=8, "Tank Overflow", T0836}│
│  Buffer row                                             │
└─────────────────────────────────────────────────────────┘

Second 553 (attack ends):
┌─────────────────────────────────────────────────────────┐
│  Automation script WRITES attack_metadata.json:         │
│  {"ATTACK_ID": 0, "ATTACK_NAME": "Normal"}              │
│  Logger next poll reads ATTACK_ID=0                     │
│  Rows return to: ..., 0, Normal, None                   │
└─────────────────────────────────────────────────────────┘

Every 100th row:
┌─────────────────────────────────────────────────────────┐
│  CSVLogger.flush() called automatically                 │
│  Writes 100 rows to master_dataset.csv in one I/O call  │
│  RAM buffer cleared                                     │
└─────────────────────────────────────────────────────────┘
```

---

## 5. CSV OUTPUT — EVERY COLUMN EXPLAINED

### Column Structure (78 total)

```
Column 1:        Timestamp          ISO-8601 string
Columns 2-52:    51 Holding Registers  (integer process values, some scaled)
Columns 53-77:   25 Coils              (boolean: True/False)
Column 78:       ATTACK_ID             (0=Normal, 8-17=attack type)
Column 79:       ATTACK_NAME           (human-readable string)
Column 80:       MITRE_ID              (ICS ATT&CK technique)
```

### Holding Registers (integer / scaled)

| Column | Register | Address | Scale | Unit | Normal Range |
|--------|----------|---------|-------|------|--------------|
| FIT_101 | Flow stage 1 inlet | 0 | ×1 | m³/h | 0–20 |
| LIT_101 | Tank 1 level | 1 | ×1 | L | 200–900 |
| MV_101 | Valve 1 position | 2 | ×1 | 0/1/2 | 0=closed 1=open 2=auto |
| AIT_201 | Stage 2 turbidity | 3 | ×1 | NTU | 0–1000 |
| AIT_202 | **pH sensor** | 4 | ÷100 | pH | 6.50–8.50 |
| FIT_201 | Flow stage 2 | 5 | ×1 | m³/h | 0–20 |
| MV_201 | Valve 2 position | 7 | ×1 | 0/1/2 | 2 |
| Acid_Tank_Level | Acid storage | 8 | ×1 | % | 15–100 |
| Chlorine_Tank_Level | Cl₂ storage | 9 | ×1 | % | 15–100 |
| Coagulant_Tank_Level | Coagulant | 10 | ×1 | % | 15–100 |
| FIT_301 | UF feed flow | 11 | ×1 | m³/h | 0–20 |
| DPIT_301 | UF transmembrane pressure | 12 | ÷10 | kPa | 5–50 |
| LIT_301 | Tank 3 level | 14 | ×1 | L | 200–900 |
| MV_301-304 | UF valves | 15-18 | ×1 | 0/1/2 | 2 |
| PIT_501 | RO feed pressure | 35 | ÷10 | bar | 50–150 |
| TDS_Permeate | Total dissolved solids | 38 | ×1 | ppm | 0–500 |

Key scaling note: `AIT_202` stores `720` to represent pH 7.20.
When you plot this column, divide by 100.

### Coils (Boolean True/False)

| Column | Coil | Address | Meaning |
|--------|------|---------|---------|
| P_101 | Feed pump 1 | 0 | True=running |
| P_102 | Feed pump 2 | 1 | True=running |
| P_203 | **Acid dosing pump** | 4 | True=dosing |
| P_205 | Chlorine dosing | 6 | True=dosing |
| P_301 | UF feed pump | 8 | True=running |
| P_401 | RO feed pump | 10 | True=running |
| P_501 | High-pressure pump | 15 | True=running |
| UV_401 | UV disinfection | 14 | True=on |
| UF_Backwash_Active | UF backwash | 20 | True=backwashing |
| High_Level_Alarm | Tank overflow | 21 | True=alarm |
| Chemical_Low_Alarm | Chemical depleted | 22 | True=alarm |
| High_Fouling_Alarm | Membrane fouled | 23 | True=alarm |
| High_Pressure_Alarm | Over-pressure | 24 | True=alarm |

### Attack Label Columns

| Column | Values | Meaning |
|--------|--------|---------|
| ATTACK_ID | 0 | Normal operation |
| ATTACK_ID | 8 | Tank Overflow Attack |
| ATTACK_ID | 9 | Chemical Depletion Attack |
| ATTACK_ID | 10 | Membrane Damage Attack |
| ATTACK_ID | 11 | pH Manipulation Attack |
| ATTACK_ID | 12 | Slow Ramp Attack |
| ATTACK_ID | 16 | Valve Manipulation Attack |
| ATTACK_ID | 17 | Multi-Variable Stealth |
| ATTACK_NAME | string | Human-readable name |
| MITRE_ID | T0836 / T0856 | MITRE ICS ATT&CK ID |

---

## 6. HOW IT HELPS ML / DATASET QUALITY

### 6.1  Why Temporal Consistency Matters

Old individual reads produced time-smeared data:
```
t=0ms:   LIT_101 = 502   (pump just turned off)
t=200ms: FIT_101 = 5     (flow still running!)
t=400ms: P_101   = False (now showing pump off)

Result: row says "pump off AND flow = 5" simultaneously
→ physically impossible
→ ML model learns a false pattern
```

New bulk reads capture all values within 60ms:
```
t=0ms:    LIT_101 = 502, FIT_101 = 5 (pump just turned off, flow running)
t=40ms:   P_101 = True  (pump still shows True — it only stopped at t=0)

Result: perfectly consistent physical state
→ ML model learns real physics
```

### 6.2  Why Temporal Attack Profiles Help ML

With instant register writes (old attack scripts):
```
Second 0:  LIT_101 = 502   ← normal
Second 1:  LIT_101 = 1000  ← JUMP (impossible physics)

The ML model learns: "if LIT_101 jumps instantly by 498L in one second → attack"
This is trivial to learn and trivial to evade by any real attacker
```

With sigmoid/exponential profiles (new temporal engine):
```
Second 0:   LIT_101 = 502
Second 30:  LIT_101 = 560  (sigmoid fill)
Second 60:  LIT_101 = 680
Second 90:  LIT_101 = 810
Second 120: LIT_101 = 950

The ML model must learn: "sustained upward trend with suppressed pumps → attack"
This reflects real physical behaviour and is much harder to evade
```

### 6.3  Class Imbalance

Your 80:40 ratio = 66.7% normal vs 33.3% attack.

This is intentional. Real ICS systems run normally most of the time.
A model trained on 50/50 will over-detect attacks in production.
A model trained on 66.7/33.3 learns the realistic prior.

For further training tips:
- Use `normal_only.csv` for one-class anomaly detection (Isolation Forest, Autoencoder)
- Use `master_dataset.csv` for binary classification (Random Forest, XGBoost)
- Use `attacks_only.csv` to study attack signatures per type

---

## 7. AUTOMATED LOGGING — EVERY COMMAND STEP BY STEP

### Step 1 — Open Command Prompt as Administrator

```
Press Win key
Type: cmd
Right-click "Command Prompt"
Click "Run as administrator"
```

Why administrator? Writing to `C:\swat_OPTIMIZED\` may need admin rights
on some Windows configurations.

---

### Step 2 — Navigate to Project

```cmd
cd C:\swat_OPTIMIZED
```

Verify you are in the right place:
```cmd
dir

REM You must see these files:
REM   automated_dataset_generator.py
REM   logging\data_logger.py
REM   attacks\command_injection.py
REM   config\swat_config.py
```

---

### Step 3 — Test Connection Before Running

```cmd
python -c "from pymodbus.client import ModbusTcpClient; c=ModbusTcpClient('192.168.1.100',port=1502); ok=c.connect(); print('Connected' if ok else 'FAILED'); c.close()"
```

Expected output:
```
Connected
```

If you see `FAILED`:
- Check PLC is powered on
- Check IP address in `config\swat_config.py`
- Check Windows Firewall is not blocking port 1502

---

### Step 4A — Full 2-Hour Automated Dataset (Standard)

```cmd
python automated_dataset_generator.py --host 192.168.1.100
```

What happens:
1. Reads `config\swat_config.py` for Modbus settings
2. Creates `automated_dataset\` directory
3. Writes initial `attack_metadata.json` → `{"ATTACK_ID": 0, "ATTACK_NAME": "Normal"}`
4. Generates random attack schedule (40 minutes of attacks across 2 hours)
5. Spawns `data_logger.py` as subprocess (polls every 1 second)
6. At each scheduled attack time: writes metadata → runs temporal attack → resets metadata
7. After 2 hours: stops logger, splits CSV, writes analysis report

Expected console output:
```
[2026-02-13 10:00:00] [INFO] ===...
[2026-02-13 10:00:00] [INFO] SWAT AUTOMATED GENERATOR - TEMPORAL ATTACK PROFILES
[2026-02-13 10:00:00] [INFO] OS      : Windows 10
[2026-02-13 10:00:00] [INFO] Total   : 120 min
[2026-02-13 10:00:00] [INFO] Normal  : 80 min
[2026-02-13 10:00:00] [INFO] Attacks : 40 min
[2026-02-13 10:00:00] [SCHEDULE] [1] pH Manipulation Attack @8.2min dur=90s params={'target_ph': 4.8}
[2026-02-13 10:00:00] [SCHEDULE] [2] Tank Overflow Attack @15.7min dur=120s
[2026-02-13 10:00:03] [INFO] Logger started (PID 12345)
[2026-02-13 10:00:03] [INFO] Entering main loop...
[2026-02-13 10:08:12] [ATTACK] ► pH Manipulation Attack  dur=90s  params={'target_ph': 4.8}
[2026-02-13 10:08:12] [INFO]   pH attack: 7.20 → 4.80 pH  (τ=30s, duration=90s)
[2026-02-13 10:08:42] [INFO]     t= 30s  pH=5.91  (target 4.80)
[2026-02-13 10:09:12] [INFO]     t= 60s  pH=5.12
[2026-02-13 10:09:42] [INFO]     t= 90s  pH=4.83
[2026-02-13 10:09:43] [INFO]   ✓ attack complete (success=True), reset to Normal
[2026-02-13 10:10:00] [INFO] Progress: 10.0/120min (8.3%)
```

---

### Step 4B — Custom Duration

```cmd
REM 30-minute test (20min normal + 10min attacks)
python automated_dataset_generator.py --host 192.168.1.100 --total 30 --normal 20 --attack 10

REM 5-minute quick test
python automated_dataset_generator.py --host 192.168.1.100 --total 5 --normal 3 --attack 2

REM 3-hour long session
python automated_dataset_generator.py --host 192.168.1.100 --total 180 --normal 120 --attack 60

REM Overnight (8 hours)
python automated_dataset_generator.py --host 192.168.1.100 --total 480 --normal 320 --attack 160
```

---

### Step 4C — Custom Output Directory

```cmd
REM Save to a named experiment folder
python automated_dataset_generator.py --host 192.168.1.100 --output experiment_001

REM Save to a date-stamped folder
python automated_dataset_generator.py --host 192.168.1.100 --output dataset_20260213
```

---

### Step 4D — Custom Port

```cmd
REM If your PLC uses a non-standard Modbus port
python automated_dataset_generator.py --host 192.168.1.100 --port 502
python automated_dataset_generator.py --host 192.168.1.100 --port 5020
```

---

### Step 5 — Monitor Progress in a Second Window

Open a second Command Prompt:

```cmd
cd C:\swat_OPTIMIZED\automated_dataset

REM Option A: Scroll through log once
type execution_details.log

REM Option B: Real-time tail (PowerShell)
powershell Get-Content execution_details.log -Wait -Tail 30

REM Option C: Count rows being collected
python -c "import pandas as pd; df=pd.read_csv('master_dataset.csv'); print(f'Rows so far: {len(df)}')"

REM Option D: Show current attack status
python -c "import json; d=json.load(open('attack_metadata.json')); print(f'ATTACK_ID={d[\"ATTACK_ID\"]} NAME={d[\"ATTACK_NAME\"]}')"
```

---

### Step 6 — After Completion: Verify Results

```cmd
cd C:\swat_OPTIMIZED\automated_dataset

REM Check all output files exist
dir

REM Expected:
REM   master_dataset.csv       ← all 7200 rows
REM   normal_only.csv          ← ~4800 rows
REM   attacks_only.csv         ← ~2400 rows
REM   attack_metadata.json
REM   attack_timeline.log
REM   execution_details.log
```

```cmd
REM Total rows
python -c "import pandas as pd; df=pd.read_csv('master_dataset.csv'); print(f'Total rows: {len(df)}')"

REM Normal vs attack breakdown
python -c "import pandas as pd; df=pd.read_csv('master_dataset.csv'); print(df.ATTACK_NAME.value_counts())"

REM Data quality check
python -c "import pandas as pd; df=pd.read_csv('master_dataset.csv'); print(f'Missing values: {df.isnull().sum().sum()}'); print(f'Columns: {len(df.columns)}')"

REM View attack timeline report
type attack_timeline.log
```

---

## 8. MANUAL LOGGING — EVERY COMMAND STEP BY STEP

Manual mode = you control the logger and fire attacks yourself, independently.

### Step 1 — Open TWO Command Prompt Windows

**Window 1:** For the logger (runs all session)
**Window 2:** For firing attacks when you choose

In both windows:
```cmd
cd C:\swat_OPTIMIZED
```

---

### Step 2 — Create Output Directory

```cmd
REM In Window 1:
mkdir data
mkdir logs
```

---

### Step 3 — Start the Logger (Window 1)

#### Basic — runs until you press Ctrl+C

```cmd
python logging\data_logger.py --host 192.168.1.100 --output data\manual_session.csv --metadata-file attack_metadata.json
```

What each argument does:

| Argument | Value | Purpose |
|----------|-------|---------|
| `--host` | 192.168.1.100 | PLC IP address |
| `--output` | data\manual_session.csv | Where to write the CSV |
| `--metadata-file` | attack_metadata.json | Which file to read attack labels from |

Expected output (runs continuously):
```
2026-02-13 10:00:00 - INFO - Connecting to SWAT at 192.168.1.100:1502
2026-02-13 10:00:01 - INFO - Connected
2026-02-13 10:00:01 - INFO - Address maps: 51 registers, 25 coils
2026-02-13 10:00:01 - INFO - Using metadata file: attack_metadata.json
2026-02-13 10:00:01 - INFO - Starting OPTIMIZED logging (interval: 1.0s)
2026-02-13 10:01:41 - INFO - Polls=100, Success=100.0%
2026-02-13 10:03:21 - INFO - Polls=200, Success=100.0%
```

#### With fixed duration (auto-stops)

```cmd
REM Log for exactly 30 minutes then stop
python logging\data_logger.py --host 192.168.1.100 --duration 1800 --output data\session_30min.csv --metadata-file attack_metadata.json

REM Log for 1 hour
python logging\data_logger.py --host 192.168.1.100 --duration 3600 --output data\session_1hr.csv --metadata-file attack_metadata.json

REM Log for 2 hours
python logging\data_logger.py --host 192.168.1.100 --duration 7200 --output data\session_2hr.csv --metadata-file attack_metadata.json
```

#### With custom poll rate

```cmd
REM Poll at 2 Hz (every 0.5s) — faster data for dynamic events
python logging\data_logger.py --host 192.168.1.100 --interval 0.5 --output data\fast_2hz.csv --metadata-file attack_metadata.json

REM Poll at 10 Hz (every 0.1s) — maximum supported rate
python logging\data_logger.py --host 192.168.1.100 --interval 0.1 --output data\fast_10hz.csv --metadata-file attack_metadata.json

REM Poll every 5 seconds — low-bandwidth long session
python logging\data_logger.py --host 192.168.1.100 --interval 5.0 --output data\slow_5s.csv --metadata-file attack_metadata.json
```

#### Without attack metadata (pure sensor logging)

```cmd
REM No metadata file = no attack labeling, just raw sensor data
python logging\data_logger.py --host 192.168.1.100 --output data\unlabeled.csv
```

#### Background logging (closes window, keeps running)

```cmd
REM Start in background, redirect output to log file
start /B python logging\data_logger.py --host 192.168.1.100 --output data\background.csv --metadata-file attack_metadata.json > logs\logger_bg.log 2>&1

REM Save PID for later
for /f "tokens=2" %i in ('tasklist /fi "imagename eq python.exe" /fo list ^| find "PID"') do echo %i > logger.pid
type logger.pid
```

To stop background logger:
```cmd
REM Read PID
set /p PID=<logger.pid

REM Stop it
taskkill /F /PID %PID%
```

---

### Step 4 — Let Normal Data Accumulate (Window 1)

Leave the logger running.
Do nothing in Window 2.
Watch the poll count climb in Window 1.

Recommended: collect at least 5 minutes of normal data before first attack.

```cmd
REM Window 2: Check how many normal rows collected so far
python -c "import pandas as pd; df=pd.read_csv('data\manual_session.csv'); print(f'Normal rows: {(df.ATTACK_ID==0).sum()}')"
```

---

## 9. MANUAL ATTACK LABELING DURING LIVE LOGGING

This is the 3-command pattern for every attack:

```
1. Write metadata → attack label starts in CSV
2. Run attack    → injects values into PLC
3. Reset metadata → label returns to Normal in CSV
```

The logger is reading `attack_metadata.json` every second. The moment you
write a new ATTACK_ID to that file, the very next CSV row gets that label.
The moment you reset it, labels go back to Normal.

---

### Attack 1: pH Manipulation — Exponential drift

**Window 2 — all three commands:**

```cmd
REM STEP 1: Write attack label to metadata file
python -c "import json; open('attack_metadata.json','w').write(json.dumps({'ATTACK_ID':11,'ATTACK_NAME':'pH Manipulation Attack','MITRE_ID':'T0836'}))"

REM STEP 2: Execute temporal pH attack (pH drifts 7.2→4.8 exponentially)
python attacks\command_injection.py --host 192.168.1.100 --attack ph_manipulation --target-ph 4.8 --duration 120

REM STEP 3: Reset label back to normal
python -c "import json; open('attack_metadata.json','w').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
```

What the CSV captures during those 120 seconds:
```
...10:08:11, ..., AIT_202=720, P_203=True,  ..., 0,  Normal,                None
...10:08:12, ..., AIT_202=715, P_203=False, ..., 11, pH Manipulation Attack, T0836
...10:08:42, ..., AIT_202=650, P_203=False, ..., 11, pH Manipulation Attack, T0836
...10:09:12, ..., AIT_202=570, P_203=False, ..., 11, pH Manipulation Attack, T0836
...10:09:42, ..., AIT_202=503, P_203=False, ..., 11, pH Manipulation Attack, T0836
...10:10:12, ..., AIT_202=503, P_203=False, ..., 11, pH Manipulation Attack, T0836
...10:10:13, ..., AIT_202=506, P_203=True,  ..., 0,  Normal,                None
```

The exponential drift from 720 to 503 is plainly visible row by row.

---

### Attack 2: Tank Overflow — Sigmoid fill

```cmd
python -c "import json; open('attack_metadata.json','w').write(json.dumps({'ATTACK_ID':8,'ATTACK_NAME':'Tank Overflow Attack','MITRE_ID':'T0836'}))"

python attacks\command_injection.py --host 192.168.1.100 --attack tank_overflow --overflow-value 1000 --duration 180

python -c "import json; open('attack_metadata.json','w').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
```

Variation — partial overflow (tanks reach 800L, not 1000):
```cmd
python attacks\command_injection.py --host 192.168.1.100 --attack tank_overflow --overflow-value 800 --duration 150
```

---

### Attack 3: Chemical Depletion — Linear drain

```cmd
python -c "import json; open('attack_metadata.json','w').write(json.dumps({'ATTACK_ID':9,'ATTACK_NAME':'Chemical Depletion Attack','MITRE_ID':'T0836'}))"

python attacks\command_injection.py --host 192.168.1.100 --attack chemical_depletion --duration 120

python -c "import json; open('attack_metadata.json','w').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
```

---

### Attack 4: Membrane Damage — Exponential pressure creep

```cmd
python -c "import json; open('attack_metadata.json','w').write(json.dumps({'ATTACK_ID':10,'ATTACK_NAME':'Membrane Damage Attack','MITRE_ID':'T0836'}))"

python attacks\command_injection.py --host 192.168.1.100 --attack membrane_damage --duration 240

python -c "import json; open('attack_metadata.json','w').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
```

---

### Attack 5: Valve Manipulation — Staggered close + hydraulic transient

```cmd
REM Close all valves
python -c "import json; open('attack_metadata.json','w').write(json.dumps({'ATTACK_ID':16,'ATTACK_NAME':'Valve Manipulation Attack','MITRE_ID':'T0836'}))"

python attacks\command_injection.py --host 192.168.1.100 --attack valve_manipulation --valve-position 0 --duration 90

python -c "import json; open('attack_metadata.json','w').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
```

---

### Attack 6: Slow Ramp — Stealth drift with Gaussian noise

```cmd
python -c "import json; open('attack_metadata.json','w').write(json.dumps({'ATTACK_ID':12,'ATTACK_NAME':'Slow Ramp Attack','MITRE_ID':'T0836'}))"

REM Drift LIT_401 from 500 to 900 over 600 seconds
python attacks\command_injection.py --host 192.168.1.100 --attack slow_ramp --start-value 500 --end-value 900 --step-size 1 --duration 600

python -c "import json; open('attack_metadata.json','w').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
```

---

### Attack 7: Multi-Variable Stealth — APT-style

```cmd
python -c "import json; open('attack_metadata.json','w').write(json.dumps({'ATTACK_ID':17,'ATTACK_NAME':'Multi-Variable Stealth','MITRE_ID':'T0856'}))"

python attacks\command_injection.py --host 192.168.1.100 --attack multi_stealth --duration 300

python -c "import json; open('attack_metadata.json','w').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
```

---

### Running Multiple Attacks in a Batch Script

Create `my_attack_session.bat`:

```batch
@echo off
echo ============================================
echo  Manual Attack Session
echo ============================================
echo.

echo [%TIME%] Collecting 3 minutes of baseline...
timeout /T 180 /NOBREAK

echo.
echo [%TIME%] ATTACK 1: pH Manipulation (2 min)
python -c "import json; open('attack_metadata.json','w').write(json.dumps({'ATTACK_ID':11,'ATTACK_NAME':'pH Manipulation Attack','MITRE_ID':'T0836'}))"
python attacks\command_injection.py --host 192.168.1.100 --attack ph_manipulation --target-ph 4.8 --duration 120
python -c "import json; open('attack_metadata.json','w').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
echo [%TIME%] pH attack done, collecting 2 min normal...
timeout /T 120 /NOBREAK

echo.
echo [%TIME%] ATTACK 2: Tank Overflow (3 min)
python -c "import json; open('attack_metadata.json','w').write(json.dumps({'ATTACK_ID':8,'ATTACK_NAME':'Tank Overflow Attack','MITRE_ID':'T0836'}))"
python attacks\command_injection.py --host 192.168.1.100 --attack tank_overflow --duration 180
python -c "import json; open('attack_metadata.json','w').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
echo [%TIME%] Tank attack done, collecting 2 min normal...
timeout /T 120 /NOBREAK

echo.
echo [%TIME%] ATTACK 3: Slow Ramp (5 min stealth)
python -c "import json; open('attack_metadata.json','w').write(json.dumps({'ATTACK_ID':12,'ATTACK_NAME':'Slow Ramp Attack','MITRE_ID':'T0836'}))"
python attacks\command_injection.py --host 192.168.1.100 --attack slow_ramp --start-value 500 --end-value 850 --duration 300
python -c "import json; open('attack_metadata.json','w').write(json.dumps({'ATTACK_ID':0,'ATTACK_NAME':'Normal','MITRE_ID':'None'}))"
echo [%TIME%] Slow ramp done, collecting 3 min normal...
timeout /T 180 /NOBREAK

echo.
echo [%TIME%] SESSION COMPLETE
pause
```

Run it (while logger is running in Window 1):
```cmd
my_attack_session.bat
```

---

### Step 5 — Stop the Logger (Window 1)

When you have collected enough data:
```
Press Ctrl+C in Window 1
```

Logger output:
```
2026-02-13 10:45:00 - INFO - Interrupted by user
2026-02-13 10:45:00 - INFO - Stopping logger
2026-02-13 10:45:00 - INFO - ==============================
2026-02-13 10:45:00 - INFO - FINAL STATISTICS
2026-02-13 10:45:00 - INFO - Runtime: 2700.3s
2026-02-13 10:45:00 - INFO - Total Polls: 2699
2026-02-13 10:45:00 - INFO - Successful: 2699
2026-02-13 10:45:00 - INFO - Failed: 0
2026-02-13 10:45:00 - INFO - Success Rate: 100.00%
2026-02-13 10:45:00 - INFO - Average Poll Rate: 1.00 Hz
2026-02-13 10:45:00 - INFO - CSV Rows Written: 2699
```

---

### Step 6 — Split CSV Into Normal and Attack Files

```cmd
python -c "
import pandas as pd
df = pd.read_csv('data\manual_session.csv')

df_normal = df[df['ATTACK_ID'] == 0]
df_attack = df[df['ATTACK_ID'] >  0]

df_normal.to_csv('data\normal_only.csv', index=False)
df_attack.to_csv('data\attacks_only.csv', index=False)

print(f'Total rows   : {len(df):,}')
print(f'Normal rows  : {len(df_normal):,} ({len(df_normal)/len(df)*100:.1f}%)')
print(f'Attack rows  : {len(df_attack):,} ({len(df_attack)/len(df)*100:.1f}%)')
print()
print('Attack breakdown:')
print(df[df.ATTACK_ID>0].ATTACK_NAME.value_counts())
"
```

---

## 10. VERIFYING YOUR DATA AFTER COLLECTION

### Check 1: Row Count Is Correct

```cmd
python -c "
import pandas as pd
df = pd.read_csv('data\manual_session.csv')
expected = int(input('Session duration in seconds: '))
actual = len(df)
pct = actual / expected * 100
print(f'Expected: {expected} rows')
print(f'Actual  : {actual} rows ({pct:.1f}%)')
if pct < 95:
    print('WARNING: More than 5%% rows missing — check network stability')
else:
    print('OK: Row count is good')
"
```

---

### Check 2: Attack Labels Are Present

```cmd
python -c "
import pandas as pd
df = pd.read_csv('data\manual_session.csv')
attack_rows = (df.ATTACK_ID > 0).sum()
print(f'Attack rows: {attack_rows}')
if attack_rows == 0:
    print('PROBLEM: No attack labels found!')
    print('Cause: metadata file not used, or attacks ran before metadata was written')
else:
    print('OK: Attacks are labeled')
    print(df.ATTACK_NAME.value_counts())
"
```

---

### Check 3: Temporal Drift Is Present (Not Instant Jumps)

```cmd
python -c "
import pandas as pd
df = pd.read_csv('data\manual_session.csv')

ph_attacks = df[df.ATTACK_NAME == 'pH Manipulation Attack']
if len(ph_attacks) > 0:
    ph_values = ph_attacks['AIT_202'].values
    first = ph_values[0] / 100
    last  = ph_values[-1] / 100
    steps = [abs(ph_values[i+1] - ph_values[i]) for i in range(min(10, len(ph_values)-1))]
    avg_step = sum(steps)/len(steps)
    print(f'pH at attack start : {first:.2f}')
    print(f'pH at attack end   : {last:.2f}')
    print(f'Average step/second: {avg_step/100:.3f} pH units')
    if avg_step > 50:
        print('WARNING: Steps too large — may be instant writes, not temporal')
    else:
        print('OK: Gradual temporal drift confirmed')
else:
    print('No pH attacks found in dataset')
"
```

---

### Check 4: No Time Gaps in CSV

```cmd
python -c "
import pandas as pd
df = pd.read_csv('data\manual_session.csv')
df['Timestamp'] = pd.to_datetime(df['Timestamp'])
df['diff'] = df['Timestamp'].diff().dt.total_seconds()
gaps = df[df['diff'] > 3]
print(f'Gaps > 3 seconds: {len(gaps)}')
if len(gaps) > 0:
    print('Gap locations:')
    print(gaps[['Timestamp','diff']].head(10))
"
```

---

### Check 5: Physical Ranges Are Sane

```cmd
python -c "
import pandas as pd
df = pd.read_csv('data\manual_session.csv')
normal = df[df.ATTACK_ID == 0]

checks = {
    'LIT_101 (L)':        (normal.LIT_101,        200,  900),
    'AIT_202 pH (×100)':  (normal.AIT_202,         600,  850),
    'DPIT_301 (×10)':     (normal.DPIT_301,          0,  500),
    'PIT_501 (×10)':      (normal.PIT_501,         400, 1500),
}

for name, (series, lo, hi) in checks.items():
    mn, mx = series.min(), series.max()
    ok = 'OK' if mn >= lo and mx <= hi else 'WARNING'
    print(f'[{ok}] {name}: min={mn}  max={mx}  expected=[{lo},{hi}]')
"
```

---

## 11. TROUBLESHOOTING EVERY POSSIBLE ERROR

### Error: "ModuleNotFoundError: No module named 'pymodbus'"

```cmd
pip install pymodbus pandas numpy
```

Then retry.

---

### Error: "Failed to connect to SWAT"

```cmd
REM 1. Check network
ping 192.168.1.100

REM 2. Check Modbus port
python -c "import socket; s=socket.socket(); s.settimeout(3); s.connect(('192.168.1.100',1502)); print('OK'); s.close()"

REM 3. Check config file has the right IP and port
type config\swat_config.py | findstr host
type config\swat_config.py | findstr port
```

---

### Error: "ATTACK_ID is always 0 even during attacks"

```cmd
REM Check metadata file is being created
dir attack_metadata.json

REM Check its content
type attack_metadata.json

REM Check logger is reading the right metadata file
REM It should say: --metadata-file attack_metadata.json
REM Not: no --metadata-file argument at all
```

Most common cause: you started the logger WITHOUT `--metadata-file`, so it
reads a default path that does not exist.

Fix: always include `--metadata-file attack_metadata.json` when running manually.

---

### Error: "CSV has no rows" or file is 0 bytes

```cmd
REM Check the CSV was created at all
dir data\*.csv

REM Check for errors in logger output
type logs\swat_system.log | findstr ERROR
```

Most common cause: connection failed on first poll and logger exited immediately.

---

### Error: "CSV has some rows then stops"

```cmd
REM Check if logger process is still running
tasklist | findstr python

REM Check log for errors
type logs\swat_system.log | findstr "ERROR\|WARNING" | tail -20
```

Most common cause: PLC disconnected mid-session or disk full.

```cmd
REM Check disk space
dir C:\ | findstr "bytes free"
```

---

### Error: "slow_ramp attack shows instant jump not gradual"

This means the temporal attack engine is not being used. You are probably
calling the old `command_injection.py` which does instant writes.

Check: the new `automated_dataset_generator.py` uses `TemporalAttackEngine`
(direct in-process Modbus writes). Attacks executed from command line via
`command_injection.py` are still instant unless you update that file too.

---

### Warning: "poll time > 1 second" in logs

```
INFO - Poll took 1.34s which is longer than interval 1.0s
```

Cause: network latency too high, or PLC responding slowly.

Fixes:
```cmd
REM 1. Increase timeout in config\swat_config.py
REM    'timeout': 5   (default 3)

REM 2. Increase poll interval
python logging\data_logger.py --host 192.168.1.100 --interval 2.0 ...

REM 3. Check network congestion
ping -n 20 192.168.1.100
```

---

## END OF GUIDE

### Summary of the Three Workflows

| Workflow | Command | Use When |
|----------|---------|----------|
| Full automation | `python automated_dataset_generator.py --host IP` | You want hands-off 2-hour dataset |
| Manual + batch | Logger in Window 1 + `my_attack_session.bat` in Window 2 | You want specific attack types in a specific order |
| Manual per-attack | Logger + 3-command pattern per attack | You want to trigger attacks at exactly the right moment |

The logger is identical in all three workflows.
The only difference is **who writes the metadata file** —
the automation script, a batch file, or you typing the command yourself.