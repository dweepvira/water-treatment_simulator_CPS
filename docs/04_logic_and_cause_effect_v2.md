# SWaT Digital Twin — Complete Cause-Effect & Logic Reference

> **Version 2.0** — Expanded with timing details, violation diagnosis, Python bridge interactions, and ML impact for every rule.

---

## Architecture Overview

```
MATLAB physics server (TCP 9501)
    ↑↓  JSON (actuator states in, sensor values out)
Python bridge — physics_client.py  (10 Hz atomic cycle)
    ↑↓  Modbus TCP 1502
CODESYS PLC — plant.st  (ST control logic)
    ↑↓  Holding registers 0–51 (sensors) + Coils 0–27 (actuators)
CSV logger  (84 columns, 10 Hz, SCALE_MAP applied once in log_row)
```

Every 100 ms:
1. `read_actuators()` — FC1 coils 0–27 + FC3 MV registers 2,7,15,16,17,18
2. `call_matlab(actuators)` — MATLAB computes sensor physics
3. `_apply_attack_sensors(sensors, label)` — attack overrides before write
4. `write_sensors(sensors, actuators)` — FC16 bulk write registers 0–51 (MV preserved)
5. `log_row()` — SCALE_MAP applied, attack label stamped, row written to CSV

**1-cycle lag:** CODESYS ST evaluates on the next PLC scan after registers are written. The coil state logged in cycle N reflects ST decisions made on sensor values written in cycle N−1.

---

## Stage 1 — Raw Water Intake

### Instrument Map

| Tag | Address | Scale | Unit | Description |
|---|---|---|---|---|
| FIT_101 | 0 | ÷10 | m³/h | Inlet flow meter |
| LIT_101 | 1 | ×1 | L | Raw tank level |
| MV_101 | 2 | ×1 | 0/1 | Motorised inlet valve |
| P_101 | Coil 0 | bool | — | Main feed pump |
| P_102 | Coil 1 | bool | — | Booster pump |
| MV_201 | 7 | ×1 | 0/1 | Stage-2 feed valve |

### Control Rules

| ID | Condition | Effect | Threshold (register) | Threshold (eng.) | Hysteresis | Purpose |
|---|---|---|---|---|---|---|
| S1-R1 | `LIT_101 < 450` | `MV_101 := 1` | reg < 450 | < 450 L | ON: <450, stays ON until >850 | Low-level inlet open |
| S1-R2 | `LIT_101 > 850` | `MV_101 := 0` | reg > 850 | > 850 L | OFF: >850, stays OFF until <450 | High-level inlet close |
| S1-R3 | `LIT_101 > 200 AND LIT_301 < 800` | `P_101 := TRUE` | 200 / 800 | 200 / 800 L | Both conditions must hold simultaneously | Transfer pump enable |
| S1-R4 | `LIT_101 > 600` (while P_101 ON) | `P_102 := TRUE` | 600 | 600 L | — | Booster at high level |
| S1-R5 | `LIT_101 < 50` | `P_101 := FALSE, P_102 := FALSE` | 50 | 50 L | — | Emergency low-level pump trip |
| S1-R6 | `P_101 OR P_102` | `MV_201 := 1` | — | — | — | Stage-2 valve open when pumping |

### Natural Cycling Pattern

```
LIT_101 starts at ~500 L
  → P_101 ON  (LIT_101>200, LIT_301<800)
  → Q_out ≈ 4–6 L/s  →  tank drains
  → LIT_101 reaches 449 → MV_101 opens
  → Q_in ≈ 5 L/s balances Q_out → level stabilises
  → LIT_101 slowly rises to 851 → MV_101 closes
  → cycle repeats every ~67 s
```

LIT_101 std ≈ 117 L in a healthy run. If std < 20 L, inlet valve or pump is stuck.

### Known Logging Artefact
`MV_101=0` rows where `LIT_101=449` (boundary) occur because MV_101 is read at the START of the cycle, before CODESYS has acted on the freshly written LIT value. **This is not a logic error.** 97% of S1-R1 violations have LIT_101 = exactly 449 (the boundary value).

### ML Impact
MV_101 and LIT_101 are strongly correlated — good for anomaly detection. Use `LIT_101_lag1 - LIT_101` (level rate of change) as an additional feature. Pump-flow consistency `P_101 × FIT_101` should ≈ constant in steady state; deviation signals valve manipulation or pump failure.

---

## Stage 2 — Chemical Dosing

### Instrument Map

| Tag | Address | Scale | Unit | Description |
|---|---|---|---|---|
| AIT_201 | 3 | ÷10 | NTU | Turbidity |
| AIT_202 | 4 | ÷100 | pH | pH analyser |
| AIT_203 | 5 | ×1 | mV | ORP (NaOCl) |
| FIT_201 | 6 | ÷10 | m³/h | Stage-2 outlet flow |
| Acid_Tank_Level | 8 | ×1 | % | Acid tank |
| Chlorine_Tank_Level | 9 | ×1 | % | Chlorine tank |
| Coagulant_Tank_Level | 10 | ×1 | % | Coagulant tank |
| Bisulfate_Tank_Level | 11 | ×1 | % | Bisulfate tank |
| Chlorine_Residual | 51 | ÷10 | mg/L | Residual chlorine |
| P_203 | Coil 4 | bool | — | Acid dosing pump |
| P_205 | Coil 6 | bool | — | Chlorine dosing pump |
| P_206 | Coil 7 | bool | — | Coagulant dosing pump |

### Control Rules

| ID | Condition (raw register) | Condition (eng.) | Effect | τ physics | Purpose |
|---|---|---|---|---|---|
| S2-R1 | `AIT_202 > 750` | pH > 7.50 | `P_203 := TRUE` | τ_pH = 40 s (exponential approach) | Acid dosing ON — pH too alkaline |
| S2-R2 | `AIT_202 < 680` | pH < 6.80 | `P_203 := FALSE` | — | Acid dosing OFF — pH in range |
| S2-R3 | `Chlorine_Residual < 20` | < 2.0 mg/L | `P_205 := TRUE` | Linear +0.3 mg/L per dt | Chlorination starts |
| S2-R4 | `Chlorine_Residual > 50` | > 5.0 mg/L | `P_205 := FALSE` | — | Stop over-chlorination |
| S2-R5 | `AIT_201 > 400` | > 40 NTU | `P_206 := TRUE` | — | Coagulant for turbid water |
| S2-R6 | `AIT_201 < 200` | < 20 NTU | `P_206 := FALSE` | — | Turbidity cleared |
| S2-R7 | `AIT_202 > 900 OR AIT_202 < 550` | pH > 9.0 or < 5.5 | `P_101=P_102=P_301=P_401 := FALSE` | Immediate | **Safety interlock — hard trip** |
| S2-R8 | Any tank level < 15% | — | `Chemical_Low_Alarm := TRUE` | — | All 4 tanks monitored |

### P_203 Hysteresis Detail

```
pH rises → crosses 7.50 (AIT_202=750) → P_203 ON
Acid added → pH falls → τ_pH = 40 s → pH approaches 6.80
pH crosses 6.80 (AIT_202=680) → P_203 OFF
pH drifts back up (MATLAB natural target = 8.50 when P_203 OFF)
→ cycle repeats every ~80–120 s
```

P_203 expected ON% during normal: 40–55%. Deviation signals pH attack or broken acid supply.

### Chemical Tank Depletion Physics

MATLAB SR-latch refill model: tank drains at consumption rate while pump is ON; when level ≤ 15%, refill activates until level ≥ ceiling (Acid 80%, Chlorine 85%, Coagulant 75%, Bisulfate 85%). Multiple drain-refill cycles visible over a 70-min run.

### S2-R7 Interlock — Important Note

pH interlock fires when `AIT_202 > 900` (pH > 9.0) **or** `< 550` (pH < 5.5). This trips P_101, P_102, P_301, P_401 — effectively halting the entire plant. Attack threshold for `ph_manipulation` must use `target_ph` outside [5.5, 9.0] to exercise this path. Normal operation should never trigger it.

### ML Impact

P_203 duty cycle is the **strongest ML discriminator** for the Slow Ramp attack (P_203 ON% rises to ~73% during alkaline ramp vs ~46% normal). P_403 ON% distinguishes pH attacks from normal (71.3% vs 4.3%). Include both as engineered rolling features.

---

## Stage 3 — Ultrafiltration

### Instrument Map

| Tag | Address | Scale | Unit | Description |
|---|---|---|---|---|
| DPIT_301 | 12 | ÷10 | kPa | Trans-membrane pressure |
| FIT_301 | 13 | ÷10 | m³/h | UF permeate flow |
| LIT_301 | 14 | ×1 | L | UF feed tank level |
| MV_301 | 15 | ×1 | 0/1 | UF permeate valve |
| MV_302 | 16 | ×1 | 0/1 | UF permeate valve B |
| MV_303 | 17 | ×1 | 0/1 | UF backwash inlet |
| MV_304 | 18 | ×1 | 0/1 | UF backwash outlet |
| UF_Runtime | 19 | ×1 | s | UF operating seconds |
| UF_Fouling_Factor | 20 | ×1 | % | Membrane fouling level |
| UF_Last_Backwash | 21 | ×1 | s | Seconds since last BW |
| P_301 | Coil 8 | bool | — | UF feed pump |
| P_602 | Coil 18 | bool | — | Backwash pump |
| UF_Backwash_Active | Coil 20 | bool | — | BW state flag |
| High_Fouling_Alarm | Coil 23 | bool | — | Fouling alarm |

### Control Rules

| ID | Condition (raw) | Condition (eng.) | Effect | Trigger type |
|---|---|---|---|---|
| S3-R1 | `LIT_301 > 200 AND LIT_401 < 800` | level & room | `MV_301=1, MV_302=1, P_301=TRUE` | Normal operation |
| S3-R2 | `DPIT_301 > 600` | TMP > 60.0 kPa | `UF_Backwash_Active=TRUE, P_301=FALSE, P_602=TRUE, MV_303=1, MV_304=1` | Pressure-triggered BW |
| S3-R3 | `UF_Last_Backwash > 18000` | 30 min elapsed | Same as S3-R2 | Time-triggered BW |
| S3-R4 | BW active | — | `High_Fouling_Alarm := TRUE` | During backwash |

### Fouling Physics

```
dF/dt = 0.001 × (1 + AIT_201/1000) × dt    [MATLAB — fraction/step]
DPIT_301 = 25 + F × 100   [kPa × 10 in register]
BW trigger: F ≥ 0.575  →  DPIT register = 25 + 57.5 = 605 > 600 ✓

During backwash: F -= 0.1 × dt per step
Full recovery time from 0.575 → 0: ~5.75 s of backwash
```

### 1-Cycle Lag Explanation for S3-R3

619 rows may show DPIT > 60 kPa with `UF_Backwash_Active=FALSE`. This is the 100 ms window where: cycle N writes DPIT=626 to CODESYS → CODESYS evaluates ST → sets `UF_Backwash_Active=TRUE` → cycle N+1 reads the new coil state. The logged row N captures the pre-transition state. **Not a logic error** — the rule works; it is a measurement timing artefact.

### ML Impact

`DPIT_301` and `UF_Fouling_Factor` correlation r = 0.73 — keep only DPIT for feature engineering. `d²(DPIT_301)/dt²` (second derivative) catches exponential fouling before the threshold, useful for Membrane Damage attack detection.

---

## Stage 4 — Dechlorination / UV

### Instrument Map

| Tag | Address | Scale | Unit | Description |
|---|---|---|---|---|
| AIT_401 | 23 | ÷10 | mg/L | Post-dechlor Cl residual |
| AIT_402 | 24 | ×1 | mV | ORP post-dechlorination |
| FIT_401 | 25 | ÷10 | m³/h | Dechlor stage flow |
| LIT_401 | 26 | ×1 | L | Dechlor tank level |
| P_401 | Coil 10 | bool | — | Dechlor transfer pump |
| P_403 | Coil 12 | bool | — | Bisulfate dosing pump |
| UV_401 | Coil 14 | bool | — | UV disinfection unit |

### Control Rules

| ID | Condition | Effect | Reason |
|---|---|---|---|
| S4-R1 | `LIT_401 > 200` | `P_401=TRUE, UV_401=TRUE` | Minimum water required |
| S4-R2 | `Chlorine_Residual > 20` AND `LIT_401 > 200` | `P_403 := TRUE` | Cl₂ destroys polyamide RO membrane — must neutralise |
| S4-R3 | `LIT_401 ≤ 200` | `P_401=FALSE, UV_401=FALSE, P_403=FALSE` | All off when tank empty |

### P_403 Threshold Engineering Note

Threshold `Chlorine_Residual > 20` (register = 2.0 mg/L after ÷10). With natural Cl range 1.9–3.0 mg/L, P_403 fires when Cl > 2.0 mg/L, which occurs ~12–15% of normal time. During pH manipulation attack, P_403 ON% rises to 71% because acid dosing drives pH low → P_203 OFF → Cl not consumed → residual accumulates.

### ML Impact

`P_403` duty cycle is a reliable **secondary attack indicator** for pH manipulation. AIT_402 (ORP) is always r=1.0 with AIT_203 — drop one.

---

## Stage 5 — Reverse Osmosis

### Instrument Map

| Tag | Address | Scale | Unit | Description |
|---|---|---|---|---|
| PIT_501 | 35 | ÷10 | bar | RO feed pressure |
| PIT_502 | 36 | ÷10 | bar | RO permeate pressure |
| PIT_503 | 37 | ÷10 | bar | RO concentrate pressure |
| FIT_501 | 31 | ÷10 | m³/h | Total RO feed flow |
| FIT_502 | 32 | ÷10 | m³/h | RO permeate flow |
| RO_Runtime | 38 | ×1 | s | RO operating seconds |
| RO_Fouling_Factor | 39 | ×1 | % | RO fouling level |
| RO_Last_Cleaning | 40 | ×1 | s | Seconds since last CIP |
| TDS_Feed | 41 | ×1 | ppm | Feed TDS |
| TDS_Permeate | 42 | ×1 | ppm | Permeate TDS |
| P_501 | Coil 15 | bool | — | RO HP pump |
| RO_Cleaning_Active | Coil 21 | bool | — | CIP active flag |

### Control Rules

| ID | Condition (raw) | Condition (eng.) | Effect |
|---|---|---|---|
| S5-R1 | `P_401 AND LIT_401 > 200` | — | `P_501 := TRUE` |
| S5-R2 | `RO_Fouling_Factor > 80` | > 80% | `RO_Cleaning_Active=TRUE, P_501=FALSE, High_Fouling_Alarm=TRUE` |
| S5-R3 | `RO_Last_Cleaning > 1000` | 1000 cycles = 100 s | Same as S5-R2 (scheduled maintenance) |
| S5-R4 | `RO_Cleaning_Active` | CIP active | `RO_Fouling -= 0.02 × dt` per step |

### RO Pressure Physics

```
PIT_501 = 120 + RO_Fouling × 80    [bar, internal]
        ± 5 bar depending on LIT_401 level
Idle (P_501 OFF): PIT_501 = 90 bar
At startup: PIT_501 ≈ 120 bar
At max fouling (80%): PIT_501 ≈ 184 bar
```

PIT_501 ↔ RO_Fouling_Factor correlation r ≈ 0.89 — physically correct.

### Known ST Bug — RO CIP

When `RO_Fouling_Factor` rises from 0 to 82%, the OR condition `RO_Last_Cleaning > 1000` only triggers CIP 100 s after the last clean. If fouling rises again within 100 s of the last CIP, neither condition may be active simultaneously → P_501 stays ON incorrectly.

**Fix:**
```pascal
(* CURRENT — fails on rapid re-fouling *)
IF RO_Fouling_Factor > 80 OR RO_Last_Cleaning > 1000 THEN

(* FIXED — fouling alone is sufficient *)
IF RO_Fouling_Factor > 80 THEN
```

### ML Impact

`PIT_501` is one of the best features for RO state. `PIT_503 = PIT_501 − 10` always (perfect r=1.0) — drop PIT_503. Include `d(RO_Fouling_Factor)/dt` as early CIP predictor.

---

## Stage 6 — Distribution

### Instrument Map

| Tag | Address | Scale | Unit |
|---|---|---|---|
| FIT_601 | 43 | ÷10 | m³/h |
| P_601 | Coil 17 | bool | — |
| P_603 | Coil 19 | bool | — |

### Control Rules

| ID | Condition | Effect | Note |
|---|---|---|---|
| S6-R1 | `P_501 = TRUE` | `P_601=TRUE, P_603=TRUE` | RO producing → distribute |
| S6-R2 | `P_501 = FALSE` | `P_601=FALSE, P_603=FALSE` | No RO output → no distribution |

S6 compliance is typically 100% — direct copy of P_501 state. Any violation here indicates a coil write conflict from an active attack on P_601/P_603.

---

## Alarm Consolidation

| ID | Condition (raw) | Condition (eng.) | Effect |
|---|---|---|---|
| ALM-R1 | `LIT_101>950 OR LIT_301>950 OR LIT_401>950` | > 950 L any tank | `High_Level_Alarm := TRUE` |
| ALM-R2 | `PIT_501 > 2000` | > 200.0 bar | `High_Pressure_Alarm := TRUE` |
| ALM-R3 | `PIT_502 > 300` | > 30.0 bar | `High_Pressure_Alarm := TRUE` (membrane breach) |
| ALM-R4 | `High_Pressure_Alarm OR High_Level_Alarm` | — | `System_Run := FALSE` |

Note: `System_Run=FALSE` does NOT automatically restart — manual intervention required. In a digital twin, re-run the start sequence or reset physics state.

---

## Cross-Process Communication — IPC Detail

```json
attack_metadata.json  (written by scheduler, read by physics_client every cycle):
{
  "ATTACK_ID":   11,
  "ATTACK_NAME": "pH Manipulation Attack",
  "MITRE_ID":    "T0836",
  "params":      {"target_ph": 5.0},
  "timestamp":   "2026-03-21T14:28:35.123"
}
```

| Writer | Reader | Frequency | Lag |
|---|---|---|---|
| `attack_scheduler_24h.py` | `physics_client.py` | On attack start/end | ≤ 100 ms (read_interval=1) |
| `physics_client.py` | `_apply_attack_sensors()` | Every cycle | 0 ms (same cycle) |
| CODESYS ST | `read_actuators()` | Every cycle | 1 cycle (100 ms) |

---

## Feature Engineering Reference

For each key physical relationship, derive these features before training:

| Feature | Formula | Detects |
|---|---|---|
| pH rate | `d(AIT_202)/dt` | Slow ramp, pH manipulation |
| P_203 duty (60 s) | `sum(P_203, 600 rows) / 600` | Sustained acid pump anomaly |
| P_403 duty (30 s) | `sum(P_403, 300 rows) / 300` | Bisulfate anomaly during pH attack |
| Flow-pump product | `P_101 × FIT_101` | Valve blockage, pump failure |
| Mass balance S1 | `FIT_101 − FIT_201` | Flow inconsistency, valve attack |
| TMP acceleration | `d²(DPIT_301)/dt²` | Membrane fouling early warning |
| Mahalanobis dist | from normal mean/cov | Multi-stage stealth attacks |
| LIT_101 rate | `d(LIT_101)/dt` | Tank overflow (positive spike) |

---

## Complete Register + Coil Address Map

| Address | Register name | Scale | Unit |
|---|---|---|---|
| 0 | FIT_101 | ÷10 | m³/h |
| 1 | LIT_101 | ×1 | L |
| 2 | MV_101 | ×1 | 0/1 |
| 3 | AIT_201 | ÷10 | NTU |
| 4 | AIT_202 | ÷100 | pH |
| 5 | AIT_203 | ×1 | mV |
| 6 | FIT_201 | ÷10 | m³/h |
| 7 | MV_201 | ×1 | 0/1 |
| 8–11 | Tank levels (Acid/Cl/Coag/BSO₄) | ×1 | % |
| 12 | DPIT_301 | ÷10 | kPa |
| 13 | FIT_301 | ÷10 | m³/h |
| 14 | LIT_301 | ×1 | L |
| 15–18 | MV_301..MV_304 | ×1 | 0/1 |
| 19 | UF_Runtime | ×1 | s |
| 20 | UF_Fouling_Factor | ×1 | % |
| 21 | UF_Last_Backwash | ×1 | s |
| 22 | Turbidity_UF | ÷10 | NTU |
| 23–26 | AIT_401/402, FIT_401, LIT_401 | varies | — |
| 27–34 | Stage 5 sensors (AIT_501–504, FIT_501–504) | varies | — |
| 35–37 | PIT_501–503 | ÷10 | bar |
| 38–42 | RO runtime, fouling, last clean, TDS | ×1 / ÷10 | — |
| 43 | FIT_601 | ÷10 | m³/h |
| 44–45 | Water/Ambient Temperature | ÷10 | °C |
| 46–49 | Energy_P101/P301/P501/Total | ×1 | kWh |
| 50 | Turbidity_Raw | ÷10 | NTU |
| 51 | Chlorine_Residual | ÷10 | mg/L |

| Coil | Name | Type |
|---|---|---|
| 0–1 | P_101, P_102 | pump |
| 2–3 | P_201, P_202 | reserved |
| 4 | P_203 | acid dosing |
| 5 | P_204 | reserved |
| 6 | P_205 | Cl dosing |
| 7 | P_206 | coagulant |
| 8 | P_301 | UF feed |
| 9 | P_302 | reserved |
| 10 | P_401 | dechlor |
| 11 | P_402 | reserved |
| 12 | P_403 | bisulfate |
| 13 | P_404 | reserved |
| 14 | UV_401 | device |
| 15 | P_501 | RO HP |
| 16 | P_502 | reserved |
| 17–19 | P_601, P_602, P_603 | distribution/BW |
| 20 | UF_Backwash_Active | state |
| 21 | RO_Cleaning_Active | state |
| 22 | Chemical_Low_Alarm | alarm |
| 23 | High_Fouling_Alarm | alarm |
| 24 | Energy_Monitor_Enable | config |
| 25 | High_Level_Alarm | alarm |
| 26 | High_Pressure_Alarm | alarm |
| 27 | System_Run | state |
