# SWaT Digital Twin — Mathematical Approach

## Physics Engine Overview

All physics run in `swat_physics_server.m` as a discrete-time simulation at `dt = 0.1 s`. Each timestep receives an actuator state vector and returns a sensor register vector.

---

## Stage 1 — Raw Water Intake

### Tank Mass Balance (ODE)
```
dV/dt = Q_in - Q_out

Q_in  = MV_101 × (5 + noise) / 3600 × 1000   [L/s]
Q_out = pump_base(LIT_101, P_101, P_102) / 3600 × 1000

pump_base = 4 + (LIT_101>400) + (LIT_101>600) + 2×P_102
```
**Register:** `LIT_101 = round(V)` [L, no scaling]
**Register:** `FIT_101 = round(Q_in × 10)` → CSV ÷10 = m³/h

The pump base is level-dependent (staged centrifugal characteristic). LIT_101 is clamped [0, 1000 L].

---

## Stage 2 — Chemical Dosing

### pH Buffer Kinetics — First-Order ODE
```
d(pH)/dt = -(pH - pH_target) / τ_pH + ε(t)

τ_pH     = 40 s   (buffer depletion time constant)
pH_target = 6.80  if P_203 ON  (acid dosing)
            8.50  if P_203 OFF (alkaline drift)
ε(t)     = Gaussian noise, σ = 0.01 pH units

Solution: pH(t) = pH_target + (pH_0 - pH_target) × e^(-t/τ)
```
At τ=40 s: 63.2% complete in 40 s, 99.3% complete in 200 s.
**Register:** `AIT_202 = round(pH × 100)` → CSV ÷100 = pH units

**Why exponential:** Chemical buffer depletion follows d[HCO₃⁻]/dt = -k[HCO₃⁻], a first-order reaction. The rate of pH change is proportional to the deviation from equilibrium.

### Chlorine Residual Dynamics
```
if P_205 ON:  Cl(t) = min(8.0, Cl + 0.3 × dt)   [mg/L]
              Cl_tank = max(0, Cl_tank - dt)
else:         Cl(t) = max(1.5, Cl - 0.1 × dt)
```
**Register:** `Chlorine_Residual = round(Cl × 10)` → CSV ÷10 = mg/L

### Chemical Tank Hysteresis (SR-latch refill)
```
if tank_level ≤ 15%: refill_active = TRUE
if tank_level ≥ hi:  refill_active = FALSE
if refill_active:    tank_level += 2 × dt  [%/step]
```
Refill ceilings: Acid 80%, Chlorine 85%, Coagulant 75%, Bisulfate 85%.

---

## Stage 3 — Ultrafiltration

### Membrane Fouling (Darcy's Law)
```
dR/dt = α × C_feed × J × dt

Where:
  R   = fouling resistance (maps to UF_Fouling_Factor 0–1)
  α   = specific resistance coefficient
  C   = turbidity (AIT_201/1000 normalised)
  J   = permeate flux

Simplified: dF/dt = 0.001 × (1 + AIT_201/1000) × dt

Trans-Membrane Pressure:
  DPIT_301 = 25 + F × 100  [kPa]
```
**Register:** `DPIT_301 = round(kPa × 10)` → CSV ÷10 = kPa
**Register:** `UF_Fouling_Factor = round(F × 100)` [% 0–100]

Backwash trigger: `DPIT_301 > 600` (60 kPa) OR `UF_Last_Backwash > 18000` (30 min).
During backwash: `F -= 0.1 × dt` per step (membrane regeneration).

### UF Permeate Flow (Pressure-dependent)
```
Q_UF = max(2, Q_base - F×3)  where Q_base depends on LIT_301:
  Q_base = 5 if LIT_301 > 700
           4 if LIT_301 > 500
           3 otherwise
```

---

## Stage 5 — Reverse Osmosis

### RO Pressure Model
```
PIT_501 = 120 + RO_Fouling × 80  [bar, internal]
         + 5  if LIT_401 > 600    (level boost)
         - 5  if LIT_401 < 400    (level penalty)
```
**Register:** `PIT_501 = round(bar × 10)` → CSV ÷10 = bar

### RO Fouling Accumulation
```
dRO/dt = 0.0005 × dt   [fraction/step, linear]

RO CIP trigger: RO_Fouling > 0.80 OR RO_Last_Cleaning > 1000 steps
CIP recovery:   RO_Fouling -= 0.02 × dt
```
**Register:** `RO_Fouling_Factor = round(RO × 100)` [%]

### TDS Permeate
```
TDS_permeate = round(TDS_feed × 15 / 1000)   [ppm]
```
Models a constant 98.5% salt rejection rate.

---

## Sensor Noise Model — Gaussian (Central Limit Theorem)

Real sensor noise is the sum of independent sources (thermal, EMI, quantisation, vibration). By CLT, this converges to Gaussian.

```
x_measured = x_true + ε,   ε ~ N(0, σ²)
```

| Sensor | σ (register units) | σ (engineering) |
|---|---|---|
| AIT_202 (pH×100) | 4 | ±0.04 pH |
| LIT_101 (L) | 6 | ±6 L |
| PIT_501 (bar×10) | 30 | ±3.0 bar |
| DPIT_301 (kPa×10) | 10 | ±1.0 kPa |
| FIT_101 (m³/h×10) | 2 | ±0.2 m³/h |

In MATLAB, the LCG noise `ns = mod(ns×37 + 13, 23)` is used for fast deterministic noise (replaced by `randn()` for production).

---

## Attack Physics

### pH Manipulation Register-Write Mode
When `target_ph` outside [680, 850] (register units), the attack writes directly:
```
AIT_202(t) = target_ph + (initial - target_ph) × e^(-t/τ_pH) + ε(t)
```
Written at 25 Hz vs MATLAB's 10 Hz → 71% of logged frames capture attack value.

### Slow Ramp — Sigmoid Profile
```
s(t) = 1 / (1 + e^(-(10t/T - 5)))

AIT_202(t) = start + (end - start) × s(t) + ε(t)
```
Maximum rate: ds/dt|max = 2.5/T. For T=600 s: max rate = 0.004/s ≈ 0.004 pH units/s — below human perception threshold.

### Tank Overflow — Hydraulic Fill
With outlet pumps killed, Q_out → minimum leakage (1/3600 × 1000 L/s):
```
dV/dt ≈ Q_in = (5 + noise) / 3600 × 1000 ≈ 1.4 L/s

Time to overflow (449→950 L): ~360 s = 6 min
```

### Membrane Damage — Fouling Acceleration
Without backwash (BW_Active forced FALSE), fouling accumulates monotonically:
```
F(t) = F_0 + 0.001 × (1 + AIT_201/1000) × t

DPIT_301(t) = 25 + F(t) × 100

Backwash trigger reached (DPIT > 600 → F > 0.575) at:
  t = 0.575 / 0.001 ≈ 575 s ≈ 9.6 min
```

---

## Register Scaling Map

| Type | Scale | Example |
|---|---|---|
| Flows (FIT_xxx) | ×10 stored, ÷10 in CSV | 1.0 m³/h → register 10 |
| pH (AIT_202) | ×100 stored, ÷100 in CSV | pH 7.20 → register 720 |
| Pressure (PIT_501) | ×10 stored, ÷10 in CSV | 12.0 bar → register 120 |
| TMP (DPIT_301) | ×10 stored, ÷10 in CSV | 25 kPa → register 250 |
| Cl Residual | ×10 stored, ÷10 in CSV | 2.0 mg/L → register 20 |
| Temperature | ×10 stored, ÷10 in CSV | 25.0°C → register 250 |
| Levels (LIT_xxx) | ×1 (integer litres) | 500 L → register 500 |
| Fouling factors | ×100 stored | 35% → register 35 |
