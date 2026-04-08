# SWaT Digital Twin — Complete Cause-Effect & Logic Reference

> **Version 3.0** — All original content preserved. New Section 9 added: full attack-by-attack sensor impact chains, showing what the normal control response *should* be, how the attack blocks it, and which sensors deviate as a result.

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
| UV_401 | Coil 14 | bool | — | UV unit |

### Control Rules

| ID | Condition (raw) | Condition (eng.) | Effect |
|---|---|---|---|
| S4-R1 | `LIT_401 > 200 AND P_301 active` | level check | `P_401 := TRUE, UV_401 := TRUE` |
| S4-R2 | `AIT_402 > 300` | ORP > 300 mV (excess Cl) | `P_403 := TRUE` (bisulfate to reduce Cl) |
| S4-R3 | `AIT_402 < 150` | ORP < 150 mV (Cl removed) | `P_403 := FALSE` |

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

Note: `System_Run=FALSE` does NOT automatically restart — manual intervention required.

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

---

---

# SECTION 9 — Attack Cause-Effect & Sensor Impact Reference

> How each attack enters the system, which sensor registers it manipulates, which control rules it blocks or subverts, and the full chain of downstream sensor deviations that result. Every sensor that changes behaviour — whether directly written by the attack or indirectly affected by the blocked control response — is listed.

---

## Notation used in this section

- **WRITTEN** — the attack directly overwrites this register via Modbus FC16 at 25 Hz  
- **BLOCKED** — the control rule that *should* fire does not, because the attack spoofs its input  
- **DRIFTS ↑ / ↓** — the sensor drifts in the indicated direction as a physical consequence  
- **FROZEN** — the register is locked to a captured value by the replay attack  
- **CONSISTENT** — this sensor *appears* normal because the attacker also controls it  
- **INCONSISTENT** — this sensor reads its true physics value and therefore contradicts the spoofed registers

---

## 9.1 Reconnaissance Scan (MITRE T0840)

### What the attack does
Issues continuous FC1 (read coils) and FC3 (read registers) requests at 20 Hz — twice the normal bridge polling rate — from IP 192.168.5.200. **No write commands are issued.** The physical plant state is completely unaffected.

### Normal control response that should happen
Nothing changes physically. All control rules continue firing correctly.

### How the attack blocks the normal response
It doesn't block any control rule. The attack is purely network-layer. However, its 20 Hz read traffic creates measurable timing pressure on the Modbus slave: some bridge cycles see response latency increase from ~2 ms to ~8 ms, which widens the `delta_t` distribution logged in the CSV.

### Sensor-by-sensor impact

| Sensor | Impact | Direction | Explanation |
|---|---|---|---|
| **All registers (FIT_101 … FIT_601)** | No change | — | No writes issued; physics runs normally |
| **All coils (P_101 … System_Run)** | No change | — | ST logic unaffected |
| **`delta_t` (CSV timing column)** | Increases slightly | ↑ | Extra Modbus read traffic adds ~2–6 ms jitter to the bridge cycle |

### ML detection signal
The only detectable signal is the anomalous Modbus read frequency from the attacker IP and the `delta_t` jitter in the CSV. There are **zero physics-level deviations**. Detection requires network-layer or timing features (`delta_t_zscore`, `jitter`), not sensor features.

---

## 9.2 Replay Attack (MITRE T0839)

### What the attack does
Captures a snapshot of actuator coil states (e.g. `P_101=1, P_203=1, MV_101=1 …`) at attack start, then continuously replays those coil write commands against the PLC at 25 Hz, overriding whatever CODESYS ST has set. This **freezes** the actuator state regardless of what the control logic would normally command.

### Normal control response that should happen
The ST pH loop (S2-R1/R2) continuously toggles P_203 ON/OFF as pH crosses 680–750. The level loop (S1-R1/R2) toggles MV_101 as LIT_101 crosses 450–850. All of these corrections **stop happening** because the coil registers are locked to the captured snapshot values.

### How the attack blocks the normal response

| Blocked rule | Why it is blocked |
|---|---|
| S1-R1 / S1-R2 | MV_101 coil is frozen; it can no longer open/close in response to LIT_101 |
| S1-R3 / S1-R4 | P_101, P_102 are frozen; pump speed cannot change with level |
| S2-R1 / S2-R2 | P_203 is frozen; pH control loop is dead |
| S2-R3 / S2-R4 | P_205 is frozen; chlorine dosing cannot respond to residual |
| S3-R2 | UF_Backwash_Active frozen; backwash cannot trigger even if DPIT_301 climbs |
| ALL stage transitions | MV_201, MV_301 frozen; inter-stage flow control disabled |

### Sensor-by-sensor impact

| Sensor | Impact | Direction | Explanation |
|---|---|---|---|
| **All coil reads** | FROZEN | — | Attack writes captured state every 40 ms; ST output has no effect |
| **LIT_101** | DRIFTS | ↑ or ↓ | Tank level changes at Q_in − Q_out rate but MV_101 never corrects it; slowly drains or fills depending on captured pump state |
| **FIT_101** | DRIFTS | ↑ then → 0 | If MV_101 was captured OPEN, inlet stays open continuously; flow eventually drops as supply pressure drops at extremes |
| **FIT_201** | DRIFTS | ↓ | If pumps captured OFF, outlet flow declines as tank drains |
| **AIT_202 (pH)** | DRIFTS | ↑ toward 8.50 | P_203 frozen; MATLAB natural target drives pH toward alkaline without acid correction |
| **Chlorine_Residual** | DRIFTS | ↓ toward 1.5 | P_205 frozen; natural decay (~0.1 mg/L per dt) not corrected |
| **DPIT_301** | DRIFTS | ↑ | P_602 (backwash) frozen OFF; fouling accumulates monotonically |
| **UF_Fouling_Factor** | DRIFTS | ↑ | No backwash → fouling grows unrestricted |
| **Rolling std of ALL sensors** | Near-zero | ↓ → 0 | Once frozen state is reached, all sensors approach equilibrium; variance collapses |

### Critical ML detection signal
**Near-zero simultaneous variance across all sensors** is the defining replay signature. Normal operation guarantees multi-variable oscillation (LIT cycling ±117 L, pH cycling ±0.35, DPIT rising) — all of it ceasing at once is physically impossible. Rolling std window of 100 rows across the full sensor vector approaching zero is the detection feature.

---

## 9.3 pH Manipulation Attack (MITRE T0836)

### What the attack does
Directly overwrites register **AIT_202 (address 4)** at 25 Hz with a target value outside the normal operating range — either a low target (`target_ph = 5.0` → register 500) to falsely report acidic conditions, or a high target (`target_ph = 9.0` → register 900) to falsely report alkaline conditions. The true process pH (computed by MATLAB) continues evolving normally; only the register seen by CODESYS is falsified.

### Normal control response that should happen — LOW pH attack (target 5.0, register 500)
The ST pH control loop (S2-R2) reads `AIT_202 < 680` and should set `P_203 := FALSE` (stop acid dosing). Meanwhile the true process pH, without acid, naturally drifts toward 8.50 (MATLAB's alkaline equilibrium target). As the true pH rises toward 7.50 (register 750), rule S2-R1 should turn P_203 back ON. **Neither of these corrections can happen** because the spoofed register (500) keeps the ST loop perpetually below the OFF threshold.

### Normal control response that should happen — HIGH pH attack (target 9.0, register 900)
Rule S2-R1 reads `AIT_202 > 750` and keeps P_203 ON. The interlock S2-R7 reads `AIT_202 > 900` and should trip P_101, P_102, P_301, P_401. **Both fire incorrectly** — P_203 forced ON when it should be OFF, and S2-R7 may fire prematurely for a falsely-high pH reading.

### How the attack blocks the normal response

| Blocked rule | Low-pH attack (reg 500) | High-pH attack (reg 900) |
|---|---|---|
| S2-R1 (`AIT_202 > 750` → P_203 ON) | Permanently suppressed — reg 500 never crosses 750, so P_203 stays OFF | Permanently activated — reg 900 always > 750, P_203 runs continuously |
| S2-R2 (`AIT_202 < 680` → P_203 OFF) | Permanently activated — reg 500 < 680, P_203 stays OFF even when true pH is rising | Never fires — reg 900 never < 680 |
| S2-R7 interlock (`AIT_202 > 900`) | Never fires (spoofed low) — true pH damage can happen silently | Fires prematurely — trips P_101, P_102, P_301, P_401 |
| P_403 response | P_403 stays at low duty (normal) | P_403 duty rises as high-ORP response triggers bisulfate |

### Sensor-by-sensor impact

| Sensor | Impact | Direction | Explanation |
|---|---|---|---|
| **AIT_202** | WRITTEN | → 500 or 900 | Attack overwrites register at 25 Hz; MATLAB's true pH value is overridden |
| **P_203 (coil)** | BLOCKED | Stays OFF (low) / Stays ON (high) | ST acts on fake register; normal hysteresis cycle destroyed |
| **Acid_Tank_Level** | DRIFTS | ↓ (high-pH attack only) | P_203 forced ON continuously → acid tank drains at max rate |
| **Chlorine_Residual** | INCONSISTENT | No direct change | Cl dosing loop reads Chlorine_Residual (register 51) not pH; mostly unaffected initially |
| **AIT_203 (ORP)** | DRIFTS | Changes with true pH | True process ORP tracks true pH (not spoofed); becomes inconsistent with AIT_202 reading |
| **AIT_402 (post-dechlor ORP)** | DRIFTS | ↑ (high-pH attack) | Elevated true pH means more residual chlorine passes through to S4; ORP rises |
| **P_403 (coil)** | Abnormal duty | ↑ | AIT_402 elevation triggers S4-R2 → bisulfate dosing runs excessively (71.3% ON vs 4.3% normal) |
| **Bisulfate_Tank_Level** | DRIFTS | ↓ | P_403 running at high duty drains bisulfate tank |
| **LIT_301** | DRIFTS | ↓ (low-pH attack) | If S2-R7 is tripped by high-pH variant, P_301 stops → S3 stops receiving feed |
| **FIT_201** | CONSISTENT if pumps run | — | Flow appears normal; discrepancy between AIT_202 reading and expected P_203 state is the inconsistency |
| **TDS_Permeate** | DRIFTS | ↑ (long-term) | True pH > 8.5 causes higher mineral solubility → more scaling on RO membrane → eventual TDS rise |

### Key inconsistency for ML detection
`AIT_202 = 5.0` (spoofed low) while simultaneously `P_203 = 0` (ST correctly reads < 680 → OFF) is **physically impossible** in normal operation: if pH is truly at 5.0, the MATLAB physics does not produce that value from the current pump state because acid dosing is OFF. The pair `(AIT_202 < 680 AND P_203 = 0)` never occurs in normal data — P_203 would be OFF only if AIT_202 had just crossed below 680 from above, which implies it was recently 7–8. A sustained register value of 500 with P_203=0 is the attack signature.

---

## 9.4 Slow Ramp Attack (MITRE T0836)

### What the attack does
Applies a **sigmoid-shaped drift** to register AIT_202, moving it from a starting value (e.g. 720, pH 7.20) to a target outside the safe range (e.g. 560, pH 5.60 downward, or 890, pH 8.90 upward) over a duration of 600 seconds. The rate at the sigmoid inflection point is approximately 0.007 pH units/second — less than the natural pH noise floor. At any single timestep, the deviation is indistinguishable from noise. Only temporal accumulation over 30+ samples reveals the trend.

### Normal control response that should happen
As AIT_202 drifts upward through 750, S2-R1 fires and P_203 turns ON. The acid dosing pulls pH back down toward 680, and P_203 turns OFF at the hysteresis boundary. This feedback loop continuously corrects pH drift within the 680–750 band. **The slow ramp attack exploits the dead-band**: the drift rate is tuned to keep AIT_202 moving through the dead-band slowly enough that the controller's response barely keeps pace, allowing the ramp to continue escaping the control window.

### How the attack blocks the normal response
The attack doesn't block a rule — it **saturates the control loop**. As the ramp reaches 890 (above the S2-R1 ON threshold of 750), P_203 has been ON continuously for minutes. The acid dosing cannot keep up because the register target is being actively driven upward by the attack, overriding MATLAB's physics-correct output every 40 ms. The controller is responding correctly to a falsified input — P_203 stays ON at ~73% duty (vs 46% normal), but pH continues rising because the written register value keeps climbing.

### Sensor-by-sensor impact

| Sensor | Impact | Direction | Explanation |
|---|---|---|---|
| **AIT_202** | WRITTEN (slowly) | ↑ or ↓ sigmoid | Sigmoid profile written at 25 Hz; register drifts 0.007 pH/s maximum |
| **P_203 (coil)** | Abnormal duty | ↑ (alkaline ramp) | ST correctly responds to rising register → P_203 ON% rises from 46% to ~73% |
| **Acid_Tank_Level** | DRIFTS | ↓ faster than normal | P_203 runs more continuously → acid depletes faster |
| **AIT_203 (ORP)** | INCONSISTENT | — | True process ORP tracks true pH; since true pH is being controlled normally (physics isn't spoofed, only the register), ORP may diverge from the AIT_202 reading over time |
| **Chlorine_Residual** | CONSISTENT | — | Cl dosing loop uses its own register; not directly affected |
| **P_403 (coil)** | Mildly elevated duty | ↑ | If AIT_402 rises (linked to true pH), bisulfate pump triggered more often |
| **Bisulfate_Tank_Level** | DRIFTS | ↓ | Higher P_403 duty from ORP response |
| **LIT_101, LIT_301, FIT_101, FIT_201** | CONSISTENT | — | Flow and level loops unaffected; no hydraulic change |
| **DPIT_301** | CONSISTENT | — | UF fouling unaffected |
| **d(AIT_202)/dt (derived feature)** | ANOMALOUS | Non-zero sustained | Rate of change is small but non-zero for 600 s; normal pH oscillates around zero mean over any 60 s window; ramp does not |

### Key ML detection insight
A single-sample classifier cannot detect this attack — the deviation per sample is within the noise floor. The LSTM's 30-step window (3 seconds) accumulates the trend: a monotonically increasing `d(AIT_202)/dt` held over 30 steps with `P_203` showing elevated duty is the LSTM's discriminating pattern. XGBoost with `P_203_duty_60s` (rolling 60-second pump ON fraction) catches it via the pump behaviour anomaly even if the individual pH readings look borderline.

---

## 9.5 Tank Overflow Attack (MITRE T0816)

### What the attack does
Sends Modbus FC5 write commands to **kill P_101 and P_102** (coils 0 and 1 → 0) while simultaneously keeping **MV_101 OPEN** (register 2 → 1). This removes the only outflow path while maintaining inflow. MATLAB's physics then fills T-101 naturally at approximately 1.4 L/s.

### Normal control response that should happen
When `LIT_101` rises above 850 (S1-R2), CODESYS should close MV_101. When `LIT_101` exceeds 950, ALM-R1 sets `High_Level_Alarm := TRUE`, which triggers `System_Run := FALSE` via ALM-R4, halting the plant. **Both of these responses are blocked** because the attack continuously rewrites the coil values before CODESYS's ST output can take effect.

### How the attack blocks the normal response

| Blocked rule | Why it is blocked |
|---|---|
| S1-R2 (`LIT_101 > 850` → MV_101 := 0) | CODESYS writes MV_101=0 but attack overwrites with 1 within 40 ms; the closed state lasts at most 1 bridge cycle (100 ms) before being overridden |
| S1-R3 (P_101 enable) | Attack keeps P_101=0; even if S1-R3 condition is met, coil cannot be set |
| ALM-R4 (System_Run := FALSE) | System_Run is a CODESYS-owned coil; attack cannot directly override it since attack targets P_101, P_102, MV_101 only — but the physical damage has already occurred |

### Sensor-by-sensor impact

| Sensor | Impact | Direction | Explanation |
|---|---|---|---|
| **P_101 (coil)** | WRITTEN → 0 | Forced OFF | Attack keeps main pump off; outflow stops |
| **P_102 (coil)** | WRITTEN → 0 | Forced OFF | Booster also killed |
| **MV_101 (register)** | WRITTEN → 1 | Forced OPEN | Inlet stays open; Q_in ≈ 1.4 L/s continuously |
| **LIT_101** | DRIFTS | ↑ steadily | dV/dt = Q_in − Q_out ≈ +1.4 L/s with pumps OFF; fills from ~449 L to overflow (950 L) in ~360 s |
| **FIT_101** | CONSISTENT | ↑ slightly | MV_101 forced open → inlet flow steady at ~5 m³/h |
| **FIT_201** | DRIFTS | ↓ → 0 | P_101 OFF → no transfer to S2; S2 starved of feed |
| **LIT_301** | DRIFTS | ↓ | No feed from S1; UF feed tank drains as P_301 draws from it without replenishment |
| **FIT_301** | DRIFTS | ↓ | As LIT_301 falls, S3-R1 eventually disables P_301 |
| **LIT_401** | DRIFTS | ↓ | No feed from S3; dechlor tank drains |
| **PIT_501** | DRIFTS | ↓ | As LIT_401 falls below 200, S5-R1 disables P_501; RO pressure drops |
| **FIT_601** | DRIFTS | ↓ → 0 | P_601/603 disabled by S6-R2 when P_501 stops |
| **High_Level_Alarm** | FIRES | → 1 | ALM-R1 triggers when LIT_101 > 950 (≈ 360 s into attack) |
| **System_Run** | TRIPS | → 0 | ALM-R4 halts plant when High_Level_Alarm fires |
| **d(LIT_101)/dt** | ANOMALOUS | +14 L/s sustained | Normal: cycles ±0–2 L/s; attack: monotonically +1.4 L/s for 360 s is highly distinctive |

### Key ML detection signal
`d(LIT_101)/dt` sustained positive with `P_101 = 0` and `MV_101 = 1` simultaneously is physically impossible in normal operation (a rising level while pumps are OFF only happens briefly during a fill cycle, and MV_101 always closes before overflow). Sustained positive level-rate with both pumps OFF for more than 30 seconds is the attack signature.

---

## 9.6 Valve Manipulation Attack (MITRE T0849)

### What the attack does
Sends FC5 coil writes to **close MV_101 (register 2 → 0) and MV_301 (register 15 → 0)** — and optionally MV_201 and MV_302 — while keeping the transfer pumps P_101, P_301 **energised**. This creates a closed-valve / running-pump condition: the pumps are running against a closed system.

### Normal control response that should happen
When MV_101 is closed and LIT_101 falls below 450, S1-R1 should reopen MV_101 to replenish the tank. When MV_301 is closed and LIT_301 drops below 200, S3-R1 should disable P_301. **Both responses are continuously overridden** by the attack rewriting valve registers.

### How the attack blocks the normal response

| Blocked rule | Why it is blocked |
|---|---|
| S1-R1 (`LIT_101 < 450` → MV_101=1) | Attack writes MV_101=0 every 40 ms; ST command lasts 1 cycle max |
| S3-R1 (MV_301=1 condition) | Attack writes MV_301=0; permeate path stays closed regardless of S3-R1 |
| S1-R5 (emergency pump trip) | LIT_101 will fall toward 0 as P_101 runs with no inlet; when LIT_101 < 50, ST trips P_101, but attack may re-enable it |

### Sensor-by-sensor impact

| Sensor | Impact | Direction | Explanation |
|---|---|---|---|
| **MV_101 (register)** | WRITTEN → 0 | Forced CLOSED | Inlet blocked; Q_in → 0 |
| **MV_301 (register)** | WRITTEN → 0 | Forced CLOSED | UF permeate path blocked |
| **P_101 (coil)** | CONSISTENT | ON (normal-looking) | Attack keeps pump running; ST may try to trip it but attack re-enables |
| **P_301 (coil)** | CONSISTENT | ON (normal-looking) | UF feed pump running against closed valve |
| **FIT_101** | DRIFTS | ↓ → 0 | MV_101 closed → no inlet flow despite P_101 ON; pump-flow inconsistency |
| **LIT_101** | DRIFTS | ↓ | No inlet; P_101 draws from tank → level falls |
| **FIT_201** | DRIFTS | ↓ | Less water in tank → less transferred to S2 |
| **FIT_301** | DRIFTS | ↓ → 0 | MV_301 closed → permeate path blocked; permeate flow drops to zero |
| **LIT_301** | DRIFTS | ↑ | Feed still enters T-301 from S2 but permeate path blocked → level rises |
| **DPIT_301** | DRIFTS | ↑ | P_301 running against closed MV_301 → differential pressure across membrane increases |
| **LIT_401** | DRIFTS | ↓ | No permeate reaching S4; dechlor tank starved |
| **P_501** | DRIFTS | → 0 | S5-R1 trips P_501 when LIT_401 < 200 |
| **PIT_501** | DRIFTS | ↓ | P_501 off → RO feed pressure drops to idle (90 bar) |
| **FIT_601** | DRIFTS | ↓ → 0 | S6-R2 cuts distribution pumps when P_501 stops |
| **P_101 × FIT_101 product** | ANOMALOUS | High × Low | P_101=1, FIT_101≈0 — the pump-flow product should be ~constant in normal operation; near-zero with pump ON is the attack signature |

### Key ML detection signal
The feature `pump_flow_inconsistency = (P_101 = 1) AND (FIT_101 < 0.1)` has a near-zero false positive rate in normal data. In normal operation, if P_101 is ON and MV_101 is open, FIT_101 is always > 0.5 m³/h. The combination of a running pump with zero flow is a physical impossibility under normal operation and appears immediately at attack onset.

---

## 9.7 Membrane Damage Attack (MITRE T0836)

### What the attack does
Forces **UF_Backwash_Active coil (coil 20) to FALSE** at 25 Hz, preventing the backwash sequence from starting even when DPIT_301 crosses the trigger threshold (600 register units, 60 kPa). Simultaneously, the attack optionally injects elevated `AIT_201` values (high turbidity) to accelerate the fouling accumulation rate in MATLAB.

### Normal control response that should happen
When `DPIT_301 > 600` (S3-R2) OR `UF_Last_Backwash > 18000` (S3-R3), CODESYS should set `UF_Backwash_Active=TRUE`, stop P_301, start P_602, and open MV_303/MV_304 to reverse-flush the membrane. During backwash, MATLAB reduces the fouling factor at 0.1 per dt. **Both triggers are neutralised** by locking the backwash coil to FALSE.

### How the attack blocks the normal response

| Blocked rule | Why it is blocked |
|---|---|
| S3-R2 (`DPIT_301 > 600` → UF_Backwash_Active=TRUE) | CODESYS sets coil 20=TRUE but attack writes it FALSE every 40 ms |
| S3-R3 (30-min timer backwash) | Same override mechanism; UF_Last_Backwash counter climbs but backwash never activates |
| S3-R4 (High_Fouling_Alarm) | Alarm never sets because backwash coil stays FALSE, suppressing the alarm path |
| MATLAB fouling recovery | `F -= 0.1 × dt` only runs when `UF_Backwash_Active=TRUE`; since that coil is frozen FALSE, MATLAB never runs the recovery equation |

### Sensor-by-sensor impact

| Sensor | Impact | Direction | Explanation |
|---|---|---|---|
| **UF_Backwash_Active (coil 20)** | WRITTEN → 0 | Forced FALSE | Backwash locked out |
| **AIT_201** | WRITTEN (optional) | ↑ | Attack may elevate turbidity register to accelerate MATLAB fouling rate |
| **UF_Fouling_Factor** | DRIFTS | ↑ monotonic | Normal: oscillates 0–57.5% with periodic backwash. Under attack: grows linearly without bound. Rate ≈ 0.001 × (1 + AIT_201/1000) per step |
| **DPIT_301** | DRIFTS | ↑ monotonic | DPIT = 25 + F×100; as F grows past 0.575, DPIT exceeds 60 kPa and continues rising |
| **FIT_301** | DRIFTS | ↓ | As fouling increases, membrane permeability falls; permeate flow = max(2, 5 − F×3) m³/h decreases |
| **LIT_301** | DRIFTS | ↓ then stabilises | Reduced permeate flow means less water exiting the UF feed tank through the membrane; level changes with feed/output balance |
| **LIT_401** | DRIFTS | ↓ | Reduced FIT_301 means less water reaching S4 dechlor tank |
| **PIT_501** | CONSISTENT initially | — | S5 is not immediately affected; starving effect reaches RO after S4 level drops |
| **P_602 (coil)** | Stays OFF | 0 | Backwash pump cannot start with UF_Backwash_Active frozen FALSE |
| **MV_303, MV_304** | Stay CLOSED | 0 | Backwash valves cannot open |
| **High_Fouling_Alarm** | SUPPRESSED | Stays 0 | Alarm only fires when UF_Backwash_Active=TRUE per S3-R4; locked coil prevents alarm |
| **UF_Last_Backwash** | DRIFTS | ↑ continuously | Counter keeps incrementing but backwash never executes; will exceed 18000 (30 min) but trigger is blocked |
| **d²(DPIT_301)/dt²** | ANOMALOUS | ↑ > 0 sustained | In normal operation, DPIT oscillates with backwash; second derivative is near zero on average. Under attack, DPIT rises without reversal — second derivative is positive and sustained, which is the early-warning ML feature |

### Key ML detection signal
`DPIT_301` rising continuously without the characteristic sawtooth pattern (rise-then-drop during backwash) is the primary signal. `d²(DPIT_301)/dt²` persistently positive for > 30 samples (3 seconds) with `UF_Backwash_Active = 0` despite `DPIT_301 > 600` is the strongest feature. This combination never occurs in normal data: normally, once DPIT crosses 600, backwash fires within 1 cycle and DPIT immediately drops.

---

## 9.8 Chemical Depletion Attack (MITRE T0814)

### What the attack does
Writes coils to force **all four dosing pumps ON simultaneously and continuously**: P_203 (acid, coil 4), P_205 (chlorine, coil 6), P_206 (coagulant, coil 7), P_403 (bisulfate, coil 12). This drains all four chemical tanks at their maximum consumption rates regardless of what the process actually needs.

### Normal control response that should happen
Each dosing pump is independently controlled by its respective process variable: P_203 by AIT_202 (pH), P_205 by Chlorine_Residual, P_206 by AIT_201 (turbidity). When a pump is not needed, it should be OFF. **The attack prevents all four OFF conditions from taking effect** by continuously rewriting the coils to ON regardless of sensor readings.

### How the attack blocks the normal response

| Blocked rule | Why it is blocked |
|---|---|
| S2-R2 (`AIT_202 < 680` → P_203 OFF) | Attack writes P_203=1 every 40 ms; OFF command lasts 1 cycle |
| S2-R4 (`Chlorine_Residual > 50` → P_205 OFF) | Attack writes P_205=1 continuously; Cl dosing cannot stop |
| S2-R6 (`AIT_201 < 200` → P_206 OFF) | Attack writes P_206=1; coagulant dosing cannot stop |
| S4-R3 (`AIT_402 < 150` → P_403 OFF) | Attack writes P_403=1; bisulfate dosing cannot stop |

### Sensor-by-sensor impact

| Sensor | Impact | Direction | Explanation |
|---|---|---|---|
| **P_203 (coil)** | WRITTEN → 1 | Forced ON | Acid dosing continuous regardless of pH |
| **P_205 (coil)** | WRITTEN → 1 | Forced ON | Chlorine dosing continuous |
| **P_206 (coil)** | WRITTEN → 1 | Forced ON | Coagulant dosing continuous |
| **P_403 (coil)** | WRITTEN → 1 | Forced ON | Bisulfate dosing continuous |
| **AIT_202 (pH)** | DRIFTS | ↓ toward 6.80 | P_203 forced ON → MATLAB drives pH toward target 6.80; pH overshoots toward 5.5 territory as acid is applied when not needed |
| **Acid_Tank_Level** | DRIFTS | ↓ rapidly | P_203 ON continuously → drains at maximum rate (~0.05%/step); hits 15% alarm threshold in ~27 min from full |
| **Chlorine_Residual** | DRIFTS | ↑ toward 8.0 | P_205 ON continuously → chlorine accumulates at +0.3 mg/L per dt; hits upper limit quickly |
| **Chlorine_Tank_Level** | DRIFTS | ↓ rapidly | Depletes at 1%/dt; hits 15% alarm threshold in ~12 min from 80% |
| **Coagulant_Tank_Level** | DRIFTS | ↓ | P_206 ON; coagulant consumed regardless of turbidity |
| **AIT_201 (turbidity)** | INCONSISTENT | No direct change | Physical turbidity is unchanged; coagulant dosing when not needed has no turbidity effect in model |
| **AIT_402 (ORP)** | DRIFTS | ↓ | P_403 (bisulfate) forced ON continuously → ORP falls as excess bisulfate reduces chlorine; may fall below 150 mV |
| **AIT_203 (ORP stage 2)** | DRIFTS | ↑ | High chlorine residual from over-dosing raises ORP in S2 |
| **Bisulfate_Tank_Level** | DRIFTS | ↓ | P_403 continuous → bisulfate depleted |
| **Chemical_Low_Alarm** | FIRES | → 1 | ALM fires when any tank < 15%; fastest trigger is Chlorine_Tank (~12 min) |
| **Chlorine_Residual (downstream)** | DRIFTS | ↑ then → depletes | Initially overdosed; when Chlorine_Tank hits 0%, residual then falls below 2 mg/L (Cl demand exceeds supply) |
| **LIT_101, FIT_101, DPIT_301, PIT_501** | CONSISTENT | — | Hydraulic loop unaffected by chemical attack |

### Key ML detection signal
The Mahalanobis distance from the normal operating manifold spikes immediately because **all four dosing pumps are ON simultaneously** — a combination that never occurs in normal operation (pH and chlorine pumps are ON at different times, governed by independent control loops). Additionally, the rate of tank depletion for all four tanks simultaneously (`d(Acid_Tank)/dt < −0.04`, `d(Cl_Tank)/dt < −0.9` all at once) is a correlated multi-variable signature that univariate threshold detectors miss individually but the multivariate distance metric catches.

---

## 9.9 Attack Impact Quick-Reference Matrix

> Which sensors deviate under each attack. `W` = directly Written, `↑/↓` = indirectly drifts, `0` = frozen/blocked, `✗` = inconsistent with physics, `-` = unaffected.

| Sensor | Recon | Replay | pH Manip | Slow Ramp | Tank Overflow | Valve Manip | Membrane | Chem Depletion |
|---|---|---|---|---|---|---|---|---|
| **AIT_202** | - | 0 | W | W (slow) | - | - | - | ↓ |
| **AIT_201** | - | 0 | - | - | - | - | W (optional) | - |
| **AIT_203** | - | 0 | ✗ | ✗ (late) | - | - | - | ↑ |
| **AIT_402** | - | 0 | ↑ | ↑ | - | - | - | ↓ |
| **LIT_101** | - | ↑/↓ | - | - | ↑ rapid | ↓ | - | - |
| **LIT_301** | - | ↓ | ↓ (high-pH) | - | ↓ | ↑ | ↓ | - |
| **LIT_401** | - | ↓ | ↓ (high-pH) | - | ↓ | ↓ | ↓ | - |
| **FIT_101** | - | 0/↓ | - | - | ↑ | ↓→0 | - | - |
| **FIT_201** | - | 0/↓ | - | - | ↓ | ↓ | - | - |
| **FIT_301** | - | 0 | - | - | ↓ | ↓→0 | ↓ | - |
| **FIT_601** | - | 0 | - | - | ↓→0 | ↓→0 | - | - |
| **DPIT_301** | - | ↑ | - | - | - | ↑ | ↑ monotonic | - |
| **UF_Fouling** | - | ↑ | - | - | - | - | ↑ monotonic | - |
| **PIT_501** | - | ↓ | - | - | ↓ | ↓ | - | - |
| **Chlorine_Residual** | - | ↓ | ↑ (via ORP) | - | - | - | - | ↑ then↓ |
| **Acid_Tank** | - | 0 | ↓ (high-pH) | ↓ | - | - | - | ↓ rapid |
| **Chlorine_Tank** | - | 0 | - | - | - | - | - | ↓ rapid |
| **Coagulant_Tank** | - | 0 | - | - | - | - | - | ↓ |
| **Bisulfate_Tank** | - | 0 | ↓ | ↓ | - | - | - | ↓ rapid |
| **P_203** | - | 0 | BLOCKED | ↑ duty | - | - | - | W→1 |
| **P_205** | - | 0 | - | - | - | - | - | W→1 |
| **P_206** | - | 0 | - | - | - | - | - | W→1 |
| **P_403** | - | 0 | ↑ duty | ↑ duty | - | - | - | W→1 |
| **P_101** | - | 0 | - | - | W→0 | ON (override) | - | - |
| **P_301** | - | 0 | - | - | - | ON (override) | - | - |
| **P_501** | - | - | - | - | ↓ | ↓ | - | - |
| **MV_101** | - | 0 | - | - | W→1 | W→0 | - | - |
| **MV_301** | - | 0 | - | - | - | W→0 | - | - |
| **UF_Backwash** | - | 0 | - | - | - | - | W→0 | - |
| **delta_t** | ↑ jitter | - | - | - | - | - | - | - |
| **Chemical_Low_Alarm** | - | - | ↑ | - | - | - | - | ↑ |
| **High_Level_Alarm** | - | - | - | - | ↑ | - | - | - |
| **High_Fouling_Alarm** | - | - | - | - | - | - | SUPPRESSED | - |
| **System_Run** | - | - | ↓ (high-pH) | - | ↓ | - | - | - |
