# SWaT Digital Twin — Logic Build & Cause-Effect Chain

## ST Control Logic (plant.st) — Complete Cause-Effect Map

### Stage 1 — Raw Intake

| Condition | Effect | Reason |
|---|---|---|
| `LIT_101 < 450` | `MV_101 := 1` (open) | Tank below 45% — need more water |
| `LIT_101 > 850` | `MV_101 := 0` (close) | Tank above 85% — stop inlet |
| `LIT_101 > 200 AND LIT_301 < 800` | `P_101 := TRUE` | Both conditions needed: source has water, destination has room |
| `LIT_101 > 600` (while P_101 ON) | `P_102 := TRUE` | Booster pump activates at high level to push faster |
| `LIT_101 < 50` | `P_101 := FALSE, P_102 := FALSE` | Emergency low-level pump protection |
| `P_101 OR P_102` | `MV_201 := 1` | Open Stage-2 feed valve only when pumping |

**Key insight:** MV_101 and P_101 are independent controllers. MV_101 is a level-band valve; P_101 is a transfer pump. This means LIT_101 cycles between 450–850 naturally — the hysteresis band prevents rapid on/off switching.

---

### Stage 2 — Chemical Dosing

| Condition | Effect | Reason |
|---|---|---|
| `AIT_202 > 750` (pH > 7.5) | `P_203 := TRUE` | Acid dosing starts — pH too high |
| `AIT_202 < 680` (pH < 6.8) | `P_203 := FALSE` | Acid dosing stops — pH in range |
| `Chlorine_Residual < 20` (< 2.0 mg/L) | `P_205 := TRUE` | Chlorine dosing — residual too low |
| `Chlorine_Residual > 50` (> 5.0 mg/L) | `P_205 := FALSE` | Stop chlorination — residual sufficient |
| `AIT_201 > 400` (NTU > 40) | `P_206 := TRUE` | Coagulant dosing — high turbidity |
| `AIT_201 < 200` | `P_206 := FALSE` | Turbidity cleared |
| `Chlorine_Residual > 20` AND `LIT_401 > 200` | `P_403 := TRUE` | Bisulfate dosing before RO — protect polyamide membrane from Cl₂ |
| `AIT_202 > 900 OR AIT_202 < 550` | `P_101 := FALSE, P_102 := FALSE, P_301 := FALSE, P_401 := FALSE` | pH safety interlock — trips all major pumps |
| Any chemical tank < 15% | `Chemical_Low_Alarm := TRUE` | All 4 tanks monitored (Acid, Chlorine, Coagulant, Bisulfate) |

**Key insight:** The pH control is a hysteresis controller (on at 7.5, off at 6.8). This prevents rapid oscillation. The pH interlock is a hard safety trip — recovery requires manual restart.

---

### Stage 3 — Ultrafiltration

| Condition | Effect | Reason |
|---|---|---|
| `LIT_301 > 200 AND LIT_401 < 800` | `MV_301=1, MV_302=1, P_301=TRUE` | UF pumping: source has water, destination has room |
| `DPIT_301 > 600` (TMP > 60 kPa) | `UF_Backwash_Active=TRUE, P_301=FALSE, P_602=TRUE, MV_303=1, MV_304=1` | Membrane fouled — trigger backwash cycle |
| `UF_Last_Backwash > 18000` (30 min elapsed) | Same backwash trigger | Scheduled maintenance backwash |
| Backwash active | `High_Fouling_Alarm := TRUE` | Alert operator |

**Key insight:** Two backwash triggers (pressure AND timer) provide both reactive (fouling-triggered) and preventive (time-based) protection. During backwash: P_301 OFF (no forward flow), P_602 ON (reverse flush pump), MV_303/304 open (drain path).

---

### Stage 4 — Dechlorination / UV

| Condition | Effect | Reason |
|---|---|---|
| `LIT_401 > 200` | `P_401=TRUE, UV_401=TRUE` | Minimum level required to run UV and transfer pump |
| `Chlorine_Residual > 20` AND `LIT_401 > 200` | `P_403 := TRUE` | Active chlorine destroys RO polyamide membrane — must dose bisulfate |
| `LIT_401 ≤ 200` | `P_401=FALSE, UV_401=FALSE, P_403=FALSE` | All Stage-4 devices off — no water |

---

### Stage 5 — Reverse Osmosis

| Condition | Effect | Reason |
|---|---|---|
| `P_401 AND LIT_401 > 200` | `P_501 := TRUE` | RO HP pump runs only with upstream flow confirmed |
| `RO_Fouling_Factor > 80` | `RO_Cleaning_Active=TRUE, P_501=FALSE, High_Fouling_Alarm=TRUE` | CIP clean-in-place: shut RO, alert operator |
| `RO_Last_Cleaning > 1000` | Same CIP trigger | Scheduled maintenance cleaning (every ~1000 cycles = 100 s) |

---

### Stage 6 — Distribution

| Condition | Effect | Reason |
|---|---|---|
| `P_501 = TRUE` | `P_601=TRUE, P_603=TRUE` | Distribution pumps only run when RO is producing permeate |
| `P_501 = FALSE` | `P_601=FALSE, P_603=FALSE` | No RO output → no distribution |

---

### Alarm Consolidation

| Condition | Effect |
|---|---|
| `LIT_101 > 950 OR LIT_301 > 950 OR LIT_401 > 950` | `High_Level_Alarm := TRUE` |
| `PIT_501 > 2000` (20.0 bar) | `High_Pressure_Alarm := TRUE` |
| `PIT_502 > 300` (30.0 bar) | `High_Pressure_Alarm := TRUE` (membrane breach) |
| `High_Pressure_Alarm OR High_Level_Alarm` | `System_Run := FALSE` |

---

## Python Bridge Logic (physics_client.py) — Cycle Detail

```
Every 100 ms:
┌─────────────────────────────────────────────────────────┐
│ 1. read_actuators()                                      │
│    FC1: read coils 0–27  → pump/valve BOOLs             │
│    FC3: read registers 0–51 → MV_101..MV_304 (addr 2,7,│
│         15,16,17,18) preserved, not overwritten          │
├─────────────────────────────────────────────────────────┤
│ 2. call_matlab(actuators)                                │
│    Send: JSON of all actuator states + newline           │
│    Recv: JSON of all sensor values + newline             │
│    Timeout: 500 ms → use last good values               │
├─────────────────────────────────────────────────────────┤
│ 3. write_sensors(sensors, actuators)                     │
│    FC16: bulk write registers 0–51                       │
│    MV registers: preserved from actuators (NOT zeroed)   │
│    All others: from MATLAB response                      │
├─────────────────────────────────────────────────────────┤
│ 4. log_row(sensors, actuators, cycle)                    │
│    SCALE_MAP applied once (FIT÷10, pH÷100, bar÷10...)   │
│    Attack label read from attack_metadata.json (every 5c)│
│    Row written to CSV                                    │
├─────────────────────────────────────────────────────────┤
│ 5. Check total_minutes → break if elapsed               │
└─────────────────────────────────────────────────────────┘
```

---

## Attack Orchestrator Logic (automated_dataset_generator.py)

```
generate_schedule():
  Phase 1: 1× each network attack (guaranteed, shuffled order)
  Phase 2: 1× each temporal attack (guaranteed, shuffled order) ← FIX: guarantees coverage
  Phase 3: Random fill of remaining attack budget

execute_attack(event):
  1. Write attack label to attack_metadata.json (ATTACK_ID, NAME, MITRE)
  2. sleep(3) — ensure bridge reads new label before attack starts
  3. Launch command_injection.py subprocess
  4. proc.communicate(timeout=duration+10) ← FIX: hard kills overrunning attacks
  5. On timeout: kill process + restore coils to safe state
  6. finally: write Normal label back to attack_metadata.json
```

---

## IPC — Cross-Process Communication

```
attack_metadata.json:
{
  "ATTACK_ID":   13,
  "ATTACK_NAME": "Reconnaissance Scan",
  "MITRE_ID":    "T0840",
  "timestamp":   "2026-03-21T14:28:35.123"
}
```

- Written by: `automated_dataset_generator.py` (attack start/end)
- Read by: `physics_client.py` every 5 cycles (500 ms)
- Atomic write: `seek(0)` + `json.dump()` + `truncate()` + `fsync()` — prevents partial reads

---

## Cause-Effect: Why LIT_101 Cycles 449–851

```
LIT_101 starts at 500 L
  → P_101 ON (LIT_101 > 200 AND LIT_301 < 800)
  → Tank drains at Q_out = 5 L/s
  → LIT_101 drops to 449 L
  → MV_101 opens (LIT_101 < 450)
  → Q_in = 5 L/s, Q_out = 5 L/s → balance
  → Level slowly rises to 851 L (with noise)
  → MV_101 closes (LIT_101 > 850)
  → LIT_101 drops again
  → Cycle repeats ~every 67 s
```

This explains the high LIT_101 std (117 L) across all runs — it is normal cycling, not an attack signature.

---

## Key Design Decisions and Their Effects

| Decision | Effect on Data | Effect on ML |
|---|---|---|
| MV registers in holding reg block (not output block) | Preserved by write_sensors() using actuators dict | MV features now valid and discriminative |
| SCALE_MAP in log_row() only (not CSVLogger.write()) | Prevents double-scaling (FIT was 0.01, now 0.1) | Correct engineering units for ML |
| attack_metadata.json re-read every 5 cycles | 500 ms max label lag | At most 5 rows mislabelled at attack boundaries |
| total_minutes failsafe in bridge | Bridge self-stops even if _cleanup fails | Prevents 2-session gaps in CSV |
| Guaranteed attack schedule (Phase 1+2) | All attack types always appear | ML never trained without a class |
