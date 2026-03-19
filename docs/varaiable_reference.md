# SWAT COMPLETE VARIABLE REFERENCE TABLE
# All 76 Variables: Description, Ranges, Attack Scenarios, Cascading Effects

---

## TABLE STRUCTURE

For each variable:
- **Name**: Modbus register/coil identifier
- **Type**: Sensor (input) or Actuator (output)
- **Description**: Physical meaning and role
- **Normal Range**: Expected values during normal operation
- **Attack Ranges**: Values during specific attack types
- **Affected By**: Which attacks manipulate this variable
- **Cascades To**: Which variables are affected when this changes

---

## STAGE 1: RAW WATER INTAKE

### FIT_101 - Raw Water Inlet Flow
| Property | Value |
|----------|-------|
| **Address** | Holding Register 0 |
| **Type** | Sensor (Electromagnetic Flow Meter) |
| **Unit** | m³/h (stored as integer ×10) |
| **Description** | Measures raw water flow rate entering Stage 1 tank. Controlled by upstream pumps and MV_101 valve position. Critical for mass balance calculation. |
| **Normal Range** | 30-60 (3.0-6.0 m³/h) |
| **Attack Ranges** | **Valve Manipulation:** 0-10 (valve closed, flow blocked)<br>**Slow Ramp:** Gradual decrease 50→20 over 300s<br>**Replay:** Frozen at old value (e.g., 45) while actual flow changes<br>**Single Register:** Set to extreme 0 or 200 |
| **Affected By** | Valve Manipulation, Slow Ramp, Replay, Single Register, DOS (sensor read errors) |
| **Cascades To** | **LIT_101** (low flow → tank drains, high flow → tank fills)<br>**Mass balance violation** (if FIT_101 ≠ outflow, system detects anomaly)<br>**FIT_201** (downstream flow sensor affected)<br>**P_101/P_102 duty cycle** (PLC adjusts pumps based on flow) |
| **Physics** | Flow rate proportional to pump speed and valve opening: Q = k × √(ΔP) × A_valve |

---

### LIT_101 - Stage 1 Tank Level
| Property | Value |
|----------|-------|
| **Address** | Holding Register 1 |
| **Type** | Sensor (Ultrasonic Level Transmitter) |
| **Unit** | Liters (L) |
| **Description** | Water level in primary sedimentation tank. Must maintain 400-800L for proper hydraulic retention time. Low level starves downstream, high level causes overflow. |
| **Normal Range** | 400-800 L |
| **Attack Ranges** | **Tank Overflow:** 900-1000 L (sigmoid rise over 120s)<br>**Valve Manipulation:** Drops to 200-300 L (no inflow)<br>**Slow Ramp:** Gradual rise 500→950 over 600s<br>**Multi-Point:** Set to 950 L + other vars manipulated<br>**Replay:** Frozen at 520 L while actually overflowing |
| **Affected By** | Tank Overflow (primary target), Valve Manipulation (indirect), Slow Ramp, Multi-Point, Replay, Single Register |
| **Cascades To** | **High_Level_Alarm** (triggers at >900 L)<br>**P_101/P_102** (PLC stops pumps at high level)<br>**MV_101** (PLC closes valve at high level)<br>**LIT_301** (downstream tank affected by overflow spillage)<br>**System_Run** (may trigger emergency shutdown) |
| **Physics** | dV/dt = Q_in - Q_out, where V=volume, Q=flow rate. Violating mass balance indicates attack. |

---

### MV_101 - Motorized Valve Stage 1
| Property | Value |
|----------|-------|
| **Address** | Holding Register 2 |
| **Type** | Actuator (Motorized Ball Valve) |
| **Unit** | Discrete: 0=Closed, 1=Open, 2=Auto |
| **Description** | Controls raw water inlet. Auto mode: PLC adjusts based on LIT_101. Manual 0=closed stops all inflow. Manual 1=open allows maximum inflow. |
| **Normal Range** | 2 (Auto mode, PLC controlled) |
| **Attack Ranges** | **Valve Manipulation:** 0 (forced closed for 60-120s)<br>**Single Register:** 1 (forced fully open, causes overflow)<br>**Multi-Point:** 0 (closed with other valves) |
| **Affected By** | Valve Manipulation (primary target), Single Register, Multi-Point |
| **Cascades To** | **FIT_101** (closed → flow=0, open → flow=max)<br>**LIT_101** (closed → level drops, open → level rises)<br>**PIT_501** (downstream pressure affected)<br>**Water hammer** (rapid close causes pressure spike in pipes) |
| **Physics** | Valve equation: Q = C_v × √(ΔP/ρ), where C_v is valve coefficient. Rapid closure causes pressure transient. |

---

### P_101 - Primary Feed Pump 1
| Property | Value |
|----------|-------|
| **Address** | Coil 0 |
| **Type** | Actuator (Centrifugal Pump) |
| **Unit** | Boolean: True=Running, False=Stopped |
| **Description** | Main feed pump for Stage 1. Normally runs continuously. PLC stops if LIT_101 >900 L or turns off during maintenance. Consumes ~5 kW when running. |
| **Normal Range** | True (running 90% of time) |
| **Attack Ranges** | **Tank Overflow:** False (forced off at t=0 of attack)<br>**Multi-Point:** False (with other pumps off)<br>**Single Coil:** False (isolated pump shutdown)<br>**DOS:** Rapid on/off cycling (relay chatter) |
| **Affected By** | Tank Overflow, Multi-Point, Single Coil, DOS |
| **Cascades To** | **FIT_101** (off → flow drops to P_102 only)<br>**LIT_101** (off → level drops if P_102 can't compensate)<br>**LIT_301** (downstream affected)<br>**Pump duty cycle alarm** (off >10min triggers maintenance alert) |
| **Physics** | Pump curve: H = a - b×Q², where H=head, Q=flow. Motor inrush current 6× rated when starting. |

---

### P_102 - Primary Feed Pump 2 (Backup)
| Property | Value |
|----------|-------|
| **Address** | Coil 1 |
| **Type** | Actuator (Centrifugal Pump) |
| **Unit** | Boolean: True=Running, False=Stopped |
| **Description** | Backup pump, normally OFF. PLC activates if P_101 fails or if demand exceeds P_101 capacity (FIT_101 <3.0 m³/h). |
| **Normal Range** | False (standby, runs <10% of time) |
| **Attack Ranges** | **Tank Overflow:** False (forced off with P_101)<br>**Multi-Point:** False<br>**Single Coil:** True (malicious activation causes overflow) |
| **Affected By** | Tank Overflow, Multi-Point, Single Coil |
| **Cascades To** | **FIT_101** (on → flow increases)<br>**LIT_101** (on → faster fill rate)<br>**Power consumption spike** (both pumps = 10 kW total) |

---

## STAGE 2: CHEMICAL DOSING & PRE-TREATMENT

### AIT_201 - Turbidity Sensor
| Property | Value |
|----------|-------|
| **Address** | Holding Register 3 |
| **Type** | Sensor (Nephelometric Turbidity) |
| **Unit** | NTU (Nephelometric Turbidity Units) |
| **Description** | Measures suspended solids in water. High turbidity (>500 NTU) indicates raw water quality issue or inadequate coagulation. PLC adjusts coagulant dosing (P_206) based on this. |
| **Normal Range** | 200-600 NTU |
| **Attack Ranges** | **Chemical Depletion:** Rises to 800-1000 NTU (no coagulant)<br>**Multi-Stealth:** Gradual rise 400→550 (subtle)<br>**Single Register:** Set to 0 (sensor spoofing) or 2000 (extreme) |
| **Affected By** | Chemical Depletion (indirect), Multi-Stealth, Single Register |
| **Cascades To** | **P_206** (high turbidity → increase coagulant pump)<br>**DPIT_301** (high turbidity → faster membrane fouling)<br>**UF system backwash frequency** (turbidity affects fouling rate) |
| **Physics** | Turbidity ∝ particle concentration. Coagulation reaction: Al³⁺ + 3OH⁻ → Al(OH)₃↓ (flocculation) |

---

### AIT_202 - pH Sensor (CRITICAL)
| Property | Value |
|----------|-------|
| **Address** | Holding Register 4 |
| **Type** | Sensor (Glass Electrode pH Meter) |
| **Unit** | pH × 100 (e.g., 720 = pH 7.20) |
| **Description** | **MOST CRITICAL SENSOR.** Controls acid dosing pump P_203. pH must stay 6.5-8.5 for membrane protection. pH <6.0 damages membranes, >9.0 causes scaling. Response time ~30s due to glass membrane diffusion. |
| **Normal Range** | 650-850 (pH 6.5-8.5) |
| **Attack Ranges** | **pH Manipulation:** Exponential drift 720→480 (pH 4.8) over 90-120s<br>**Multi-Stealth:** Slow drift 720→660 (pH 6.6, below alarm but degraded)<br>**Replay:** Frozen at 720 while actual pH drops<br>**Single Register:** Instant write to 300 (pH 3.0, extreme)<br>**Chemical Depletion:** Rises to 900 (pH 9.0, no acid neutralization) |
| **Affected By** | pH Manipulation (primary target), Multi-Stealth, Chemical Depletion, Replay, Single Register |
| **Cascades To** | **P_203** (low pH → acid pump should be ON, if OFF = attack)<br>**DPIT_301** (wrong pH accelerates membrane fouling)<br>**AIT_501** (conductivity changes with pH)<br>**Acid_Tank_Level** (pH low but tank full = attack)<br>**Chemical_Low_Alarm** (if Acid_Tank <15% and pH rising) |
| **Physics** | Henderson-Hasselbalch: pH = pKₐ + log([A⁻]/[HA]). Buffer capacity depletes exponentially: [buffer](t) = [buffer]₀·e^(-kt) |

---

### FIT_201 - Stage 2 Flow
| Property | Value |
|----------|-------|
| **Address** | Holding Register 5 |
| **Type** | Sensor (Electromagnetic Flow Meter) |
| **Unit** | m³/h (stored as integer ×10) |
| **Description** | Flow rate through chemical dosing section. Should match FIT_101 (mass balance). Mismatch indicates leak, sensor failure, or attack. |
| **Normal Range** | 30-60 (3.0-6.0 m³/h) |
| **Attack Ranges** | **Valve Manipulation:** Drops to 0-10 (upstream valve closed)<br>**Slow Ramp:** Gradual decrease 50→20<br>**Multi-Stealth:** Subtle drop 45→38 (-15%)<br>**Mass Balance Violation:** FIT_201 ≠ FIT_101 while both should be equal |
| **Affected By** | Valve Manipulation, Slow Ramp, Multi-Stealth, Single Register |
| **Cascades To** | **FIT_301** (downstream UF feed flow)<br>**Mass balance check** (FIT_201 vs FIT_101 comparison)<br>**P_201-206 dosing rates** (all proportional to flow) |

---

### MV_201 - Chemical Dosing Valve
| Property | Value |
|----------|-------|
| **Address** | Holding Register 7 |
| **Type** | Actuator (Motorized Valve) |
| **Unit** | Discrete: 0=Closed, 1=Open, 2=Auto |
| **Description** | Controls flow into chemical dosing section. Normally Auto (2). Closing stops all treatment. |
| **Normal Range** | 2 (Auto) |
| **Attack Ranges** | **Valve Manipulation:** 0 (closed, stops chemical dosing)<br>**Single Register:** 1 (fully open, excessive dosing) |
| **Affected By** | Valve Manipulation, Single Register |
| **Cascades To** | **P_203-206** (all chemical pumps affected)<br>**AIT_202** (pH uncontrolled if valve closed)<br>**FIT_301** (downstream flow affected) |

---

### Acid_Tank_Level
| Property | Value |
|----------|-------|
| **Address** | Holding Register 8 |
| **Type** | Sensor (Capacitive Level Sensor) |
| **Unit** | Percentage (0-100%) |
| **Description** | Sulfuric acid storage tank level. Refilled manually when <20%. PLC triggers Chemical_Low_Alarm at <15%. Tank capacity 200 L. |
| **Normal Range** | 30-95% |
| **Attack Ranges** | **Chemical Depletion:** Linear drop 80%→0% over 120s (pump forced on)<br>**Multi-Stealth:** Slow decline 80%→56% (-30%)<br>**Replay:** Shows 75% while actually depleted<br>**pH Manipulation:** Stays high (80%) while pH drops (proves pump is off, not depleted) |
| **Affected By** | Chemical Depletion (primary), Multi-Stealth, Replay |
| **Cascades To** | **Chemical_Low_Alarm** (triggers at <15%)<br>**P_203** (PLC stops pump if tank <10%, safety interlock)<br>**AIT_202** (tank empty → pH rises uncontrollably)<br>**Maintenance alert** (tank <20% = refill needed) |
| **Physics** | Drain rate: dV/dt = -Q_pump = -0.05 L/s (typical dosing rate) |

---

### Chlorine_Tank_Level
| Property | Value |
|----------|-------|
| **Address** | Holding Register 9 |
| **Type** | Sensor (Ultrasonic Level) |
| **Unit** | Percentage (0-100%) |
| **Description** | Sodium hypochlorite (NaOCl) disinfection chemical. Maintains 1-2 ppm residual chlorine. Corrosive, stored in HDPE tank. |
| **Normal Range** | 25-90% |
| **Attack Ranges** | **Chemical Depletion:** 75%→0% over 120s<br>**Multi-Stealth:** 75%→52% (-30%)<br>**Single Register:** Set to 5% (triggers alarm) |
| **Affected By** | Chemical Depletion, Multi-Stealth, Single Register |
| **Cascades To** | **Chemical_Low_Alarm**<br>**P_205** (chlorine dosing pump)<br>**AIT_502** (ORP sensor, measures chlorine residual)<br>**UV_401** (insufficient chlorine increases UV demand) |

---

### Coagulant_Tank_Level
| Property | Value |
|----------|-------|
| **Address** | Holding Register 10 |
| **Type** | Sensor (Radar Level) |
| **Unit** | Percentage (0-100%) |
| **Description** | Aluminum sulfate (alum) for coagulation/flocculation. Removes suspended solids before membrane filtration. Consumption rate depends on AIT_201 turbidity. |
| **Normal Range** | 40-95% |
| **Attack Ranges** | **Chemical Depletion:** 90%→0%<br>**Multi-Stealth:** 90%→63%<br>**Single Register:** 10% (false low) |
| **Affected By** | Chemical Depletion, Multi-Stealth, Single Register |
| **Cascades To** | **Chemical_Low_Alarm**<br>**P_206** (coagulant pump)<br>**AIT_201** (no coagulant → turbidity rises)<br>**DPIT_301** (high turbidity → membrane fouls faster) |

---

### P_201 - Stage 2 Pump 1
| Property | Value |
|----------|-------|
| **Address** | Coil 2 |
| **Type** | Actuator (Centrifugal Pump) |
| **Unit** | Boolean |
| **Description** | Transfers water from Stage 1 to chemical dosing tanks. Works with P_202 in duty/standby configuration. |
| **Normal Range** | True (primary pump) |
| **Attack Ranges** | **Multi-Point:** False (stops flow to Stage 2)<br>**Single Coil:** False (isolated shutdown)<br>**Tank Overflow:** Indirectly affected (upstream tanks overflow) |
| **Affected By** | Multi-Point, Single Coil |
| **Cascades To** | **FIT_201** (off → flow drops)<br>**LIT_301** (downstream tank starved)<br>**P_202** (should activate as backup) |

---

### P_202 - Stage 2 Pump 2 (Backup)
| Property | Value |
|----------|-------|
| **Address** | Coil 3 |
| **Type** | Actuator (Centrifugal Pump) |
| **Unit** | Boolean |
| **Description** | Backup for P_201. Auto-starts if P_201 fails or flow <3 m³/h. |
| **Normal Range** | False (standby) |
| **Attack Ranges** | **Multi-Point:** False (both pumps off = total flow loss)<br>**Single Coil:** True (malicious activation) |
| **Affected By** | Multi-Point, Single Coil |
| **Cascades To** | Same as P_201 |

---

### P_203 - Acid Dosing Pump (CRITICAL)
| Property | Value |
|----------|-------|
| **Address** | Coil 4 |
| **Type** | Actuator (Peristaltic Metering Pump) |
| **Unit** | Boolean |
| **Description** | **KEY ATTACK TARGET.** Doses sulfuric acid to maintain pH 7.0-7.5. PLC controls based on AIT_202. Flow rate 0.05 L/s. Attack = turn OFF while pH needs correction. |
| **Normal Range** | True (runs 70% of time) |
| **Attack Ranges** | **pH Manipulation:** False (forced off for 90-120s, causes pH to drop)<br>**Multi-Point:** False<br>**Single Coil:** True (forced on at high pH, causes over-acidification)<br>**Chemical Depletion:** True (forced on at max speed, drains tank) |
| **Affected By** | pH Manipulation (primary), Multi-Point, Single Coil, Chemical Depletion |
| **Cascades To** | **AIT_202** (off → pH drifts toward raw water pH ~8-9)<br>**Acid_Tank_Level** (on continuously → depletes tank)<br>**pH violation alarm** (pH <6.0 or >8.5) |
| **Physics** | Acid reaction: H₂SO₄ → 2H⁺ + SO₄²⁻. ΔpH/Δt ∝ [H₂SO₄] × flow_rate / buffer_capacity |

---

### P_204 - Coagulant Booster Pump
| Property | Value |
|----------|-------|
| **Address** | Coil 5 |
| **Type** | Actuator (Positive Displacement Pump) |
| **Unit** | Boolean |
| **Description** | Increases coagulant injection pressure for proper mixing. Viscous chemical requires higher pressure than water. |
| **Normal Range** | True (when P_206 is on) |
| **Attack Ranges** | **Multi-Point:** False<br>**Single Coil:** False (coagulant pressure insufficient) |
| **Affected By** | Multi-Point, Single Coil |
| **Cascades To** | **AIT_201** (off → poor coagulation → high turbidity) |

---

### P_205 - Chlorine Dosing Pump
| Property | Value |
|----------|-------|
| **Address** | Coil 6 |
| **Type** | Actuator (Diaphragm Pump) |
| **Unit** | Boolean |
| **Description** | Doses sodium hypochlorite for disinfection. Target: 1.5 ppm residual chlorine. Runs based on AIT_502 (ORP sensor). |
| **Normal Range** | True (intermittent, 40% duty) |
| **Attack Ranges** | **Chemical Depletion:** True (forced max speed)<br>**Multi-Point:** False (no disinfection)<br>**Single Coil:** True (over-chlorination) |
| **Affected By** | Chemical Depletion, Multi-Point, Single Coil |
| **Cascades To** | **Chlorine_Tank_Level**<br>**AIT_502** (ORP drops if pump off)<br>**UV_401** (insufficient chlorine increases UV load) |

---

### P_206 - Coagulant Dosing Pump
| Property | Value |
|----------|-------|
| **Address** | Coil 7 |
| **Type** | Actuator (Peristaltic Pump) |
| **Unit** | Boolean |
| **Description** | Doses alum for turbidity removal. Rate adjusted by PLC based on AIT_201. Critical for membrane protection. |
| **Normal Range** | True (runs 60% of time) |
| **Attack Ranges** | **Chemical Depletion:** True (max speed, depletes tank)<br>**Multi-Point:** False (turbidity rises)<br>**Single Coil:** False |
| **Affected By** | Chemical Depletion, Multi-Point, Single Coil |
| **Cascades To** | **Coagulant_Tank_Level**<br>**AIT_201** (turbidity)<br>**DPIT_301** (membrane fouling) |

---

## STAGE 3: ULTRAFILTRATION (UF) MEMBRANE

### FIT_301 - UF Feed Flow
| Property | Value |
|----------|-------|
| **Address** | Holding Register 11 |
| **Type** | Sensor (Magnetic Flow Meter) |
| **Unit** | m³/h ×10 |
| **Description** | Flow into UF membrane module. Must match FIT_201. Cross-flow mode: high velocity prevents fouling. |
| **Normal Range** | 35-65 (3.5-6.5 m³/h) |
| **Attack Ranges** | **Valve Manipulation:** 0-10 (valves closed)<br>**Multi-Stealth:** 45→38 (-15%)<br>**Slow Ramp:** Gradual decrease |
| **Affected By** | Valve Manipulation, Multi-Stealth, Slow Ramp |
| **Cascades To** | **DPIT_301** (low flow → higher TMP)<br>**UF_Permeate_Flow** (feed/permeate ratio)<br>**UF membrane velocity** (fouling accelerates at low flow) |

---

### DPIT_301 - Transmembrane Pressure (TMP) (CRITICAL)
| Property | Value |
|----------|-------|
| **Address** | Holding Register 12 |
| **Type** | Sensor (Differential Pressure Transmitter) |
| **Unit** | kPa ×10 (e.g., 250 = 25.0 kPa) |
| **Description** | **CRITICAL FOR MEMBRANE HEALTH.** Pressure drop across UF membrane. Indicates fouling. TMP >50 kPa = severe fouling, triggers backwash. TMP >80 kPa = irreversible damage. |
| **Normal Range** | 150-400 (15-40 kPa) |
| **Attack Ranges** | **Membrane Damage:** Exponential rise 250→600 (60 kPa) over 240s, tau=96s<br>**Multi-Stealth:** 250→350 (+40%, below alarm at 500)<br>**Chemical Depletion:** Rises to 500+ (high turbidity fouls membrane)<br>**Single Register:** Instant write to 800 (80 kPa, extreme) |
| **Affected By** | Membrane Damage (primary), Multi-Stealth, Chemical Depletion, Single Register |
| **Cascades To** | **High_Fouling_Alarm** (triggers at DPIT >500)<br>**UF_Backwash_Active** (should activate at high TMP, attack disables it)<br>**UF_Hours_Since_BW** (high TMP but no backwash = attack)<br>**P_301/302** (PLC may reduce flow to lower TMP)<br>**Membrane replacement cost** (TMP >80 kPa causes permanent damage) |
| **Physics** | Darcy's law: TMP = (μ × R_m × J) / ε, where μ=viscosity, R_m=membrane resistance, J=flux, ε=porosity. Fouling: dR_m/dt ∝ J × c (concentration) |

---

### LIT_301 - UF Feed Tank Level
| Property | Value |
|----------|-------|
| **Address** | Holding Register 14 |
| **Type** | Sensor (Guided Wave Radar) |
| **Unit** | Liters |
| **Description** | Buffer tank before UF. Maintains steady flow despite upstream variations. |
| **Normal Range** | 500-800 L |
| **Attack Ranges** | **Tank Overflow:** 900-1000 L (if upstream overflows)<br>**Valve Manipulation:** 200-300 L (starved)<br>**Slow Ramp:** 500→900 |
| **Affected By** | Tank Overflow, Valve Manipulation, Slow Ramp |
| **Cascades To** | **High_Level_Alarm**<br>**FIT_301** (low level → pump cavitation risk)<br>**P_301/302** |

---

### MV_301, MV_302, MV_303, MV_304 - UF Module Isolation Valves
| Property | Value |
|----------|-------|
| **Address** | Holding Registers 15-18 |
| **Type** | Actuator (Pneumatic Ball Valves) |
| **Unit** | Discrete: 0/1/2 |
| **Description** | Isolate individual UF membrane trains for backwash or maintenance. All normally Auto (2). Closing all = no permeate production. |
| **Normal Range** | 2 (Auto) |
| **Attack Ranges** | **Valve Manipulation:** All set to 0 (closes entire UF system)<br>**Single Register:** MV_301=0 only (reduces capacity 25%)<br>**Multi-Point:** All 0 simultaneously |
| **Affected By** | Valve Manipulation, Single Register, Multi-Point |
| **Cascades To** | **UF_Permeate_Flow** (0 if all closed)<br>**FIT_401** (downstream starved)<br>**System_Run** (may emergency stop)<br>**DPIT_301** (pressure spikes if flow blocked) |

---

### UF_Feed_Flow, UF_Permeate_Flow
| Property | Value |
|----------|-------|
| **Address** | Holding Registers 19-20 |
| **Type** | Sensor (Coriolis Flow Meters) |
| **Unit** | m³/h ×10 |
| **Description** | Feed vs permeate flow. Recovery ratio = Permeate/Feed (typical 85-92%). Low recovery = fouling or leak. |
| **Normal Range** | Feed: 35-65, Permeate: 30-60 |
| **Attack Ranges** | **Membrane Damage:** Recovery drops from 90% to 60% (fouling reduces permeate)<br>**Valve Manipulation:** Both →0 |
| **Affected By** | Membrane Damage, Valve Manipulation |
| **Cascades To** | **Recovery ratio alarm** (permeate/feed <80%)<br>**FIT_401** (downstream) |

---

### UF_Hours_Since_BW - Backwash Counter
| Property | Value |
|----------|-------|
| **Address** | Holding Register 21 |
| **Type** | Counter (increments every hour) |
| **Unit** | Hours |
| **Description** | Time since last backwash. Should reset to 0 every 24-48 hours. High DPIT + high hours = fouling. High DPIT + low hours = recent backwash failed. |
| **Normal Range** | 0-48 hours |
| **Attack Ranges** | **Membrane Damage:** Increments continuously (backwash disabled), reaches 100+ hours while DPIT rises<br>**Replay:** Frozen at 18 hours while actually 45 hours |
| **Affected By** | Membrane Damage (backwash disabled) |
| **Cascades To** | **Maintenance alert** (>72 hours = missed backwash cycle)<br>**DPIT_301** (longer without backwash → higher fouling) |

---

### UF_Total_Filtered
| Property | Value |
|----------|-------|
| **Address** | Holding Register 22 |
| **Type** | Counter (totalizer) |
| **Unit** | m³ (cubic meters filtered) |
| **Description** | Cumulative volume filtered since last membrane clean. Resets after chemical clean-in-place (CIP). Tracks membrane life. |
| **Normal Range** | 0-10,000 m³ per CIP cycle |
| **Attack Ranges** | Not typically targeted, but affected by flow attacks |
| **Affected By** | All flow manipulation attacks (changes accumulation rate) |
| **Cascades To** | **Membrane replacement schedule** (>50,000 m³ lifetime = replace) |

---

### P_301 - UF Feed Pump 1
| Property | Value |
|----------|-------|
| **Address** | Coil 8 |
| **Type** | Actuator (Multi-stage Centrifugal) |
| **Unit** | Boolean |
| **Description** | High-pressure pump for UF cross-flow. Maintains 3-5 bar feed pressure. VFD controlled for flow regulation. |
| **Normal Range** | True |
| **Attack Ranges** | **Multi-Point:** False<br>**Single Coil:** False (stops UF)<br>**Tank Overflow:** False (staggered shutdown) |
| **Affected By** | Multi-Point, Single Coil, Tank Overflow |
| **Cascades To** | **FIT_301** (flow drops)<br>**DPIT_301** (TMP changes with flow)<br>**P_302** (backup should start) |

---

### P_302 - UF Feed Pump 2 (Backup)
| Property | Value |
|----------|-------|
| **Address** | Coil 9 |
| **Type** | Actuator (Multi-stage Centrifugal) |
| **Unit** | Boolean |
| **Description** | Standby for P_301. Auto-starts on low flow or P_301 failure. |
| **Normal Range** | False (standby) |
| **Attack Ranges** | **Multi-Point:** False (both off = no UF)<br>**Single Coil:** True (unnecessary activation) |
| **Affected By** | Multi-Point, Single Coil |
| **Cascades To** | Same as P_301 |

---

### UF_Backwash_Active
| Property | Value |
|----------|-------|
| **Address** | Coil 20 |
| **Type** | Status (solenoid valve state) |
| **Unit** | Boolean |
| **Description** | Indicates backwash cycle active. During backwash: reverse flow cleans membrane, DPIT should drop. PLC triggers every 24-48 hours or when DPIT >45 kPa. |
| **Normal Range** | False (normal filtration mode), True for 10-15 min during backwash |
| **Attack Ranges** | **Membrane Damage:** Forced False (disabled) for 240s, DPIT rises uncontrolled<br>**Single Coil:** Forced True continuously (wastes permeate, no production) |
| **Affected By** | Membrane Damage (primary target), Single Coil |
| **Cascades To** | **DPIT_301** (backwash disabled → TMP rises exponentially)<br>**UF_Hours_Since_BW** (never resets if backwash disabled)<br>**UF_Permeate_Flow** (True = no permeate production during backwash) |

---

## STAGE 4: UV DISINFECTION

### FIT_401 - UV Inlet Flow
| Property | Value |
|----------|-------|
| **Address** | Holding Register 23 |
| **Type** | Sensor (Ultrasonic Flow Meter) |
| **Unit** | m³/h ×10 |
| **Description** | Flow into UV reactor. Must match UF permeate flow. UV dose = I × t / flow, so low flow = better disinfection but lower production. |
| **Normal Range** | 30-60 |
| **Attack Ranges** | **Valve Manipulation:** 0-10<br>**Slow Ramp:** Gradual decrease |
| **Affected By** | Valve Manipulation, Slow Ramp |
| **Cascades To** | **UV_401** (PLC adjusts UV intensity based on flow)<br>**FIT_501** (downstream RO feed) |

---

### LIT_401 - UV Feed Tank
| Property | Value |
|----------|-------|
| **Address** | Holding Register 26 |
| **Type** | Sensor (Magnetostrictive Level) |
| **Unit** | Liters |
| **Description** | Buffer tank before UV. Ensures steady flow through UV reactor. |
| **Normal Range** | 450-750 L |
| **Attack Ranges** | **Slow Ramp:** 500→950 (primary target for slow ramp attacks)<br>**Tank Overflow:** 900-1000 |
| **Affected By** | Slow Ramp (common target), Tank Overflow |
| **Cascades To** | **High_Level_Alarm**<br>**FIT_401**<br>**UV_401 dose** (high level = longer residence time = better disinfection, but overflow risk) |

---

### P_401, P_402 - UV Feed Pumps
| Property | Value |
|----------|-------|
| **Address** | Coils 10-11 |
| **Type** | Actuator (Centrifugal) |
| **Unit** | Boolean |
| **Description** | Transfer water through UV reactor. P_401 primary, P_402 backup. Flow rate affects UV dose. |
| **Normal Range** | P_401=True, P_402=False |
| **Attack Ranges** | **Tank Overflow:** Both False (staggered at t=6s, t=9s)<br>**Multi-Point:** Both False<br>**Single Coil:** P_402=True while P_401=True (over-pressurizes UV) |
| **Affected By** | Tank Overflow, Multi-Point, Single Coil |
| **Cascades To** | **FIT_401**<br>**UV transmittance** (flow rate affects dose)<br>**LIT_501** (downstream RO feed tank) |

---

### UV_401 - UV Lamp Bank
| Property | Value |
|----------|-------|
| **Address** | Coil 14 |
| **Type** | Actuator (UV-C Lamps, 254nm) |
| **Unit** | Boolean |
| **Description** | Germicidal UV disinfection. Targets 40 mJ/cm² dose. Lamp intensity degrades over time (8000 hours life). PLC monitors UVT (transmittance). |
| **Normal Range** | True (on during production) |
| **Attack Ranges** | **Single Coil:** False (no disinfection, pathogen pass-through)<br>**Multi-Point:** False |
| **Affected By** | Single Coil, Multi-Point |
| **Cascades To** | **Microbiological risk** (off = E. coli, Cryptosporidium not inactivated)<br>**AIT_502** (UV affects ORP slightly) |

---

## STAGE 5: REVERSE OSMOSIS (RO)

### AIT_501 - Conductivity (Permeate Quality)
| Property | Value |
|----------|-------|
| **Address** | Holding Register 27 |
| **Type** | Sensor (4-electrode conductivity cell) |
| **Unit** | μS/cm (microsiemens/cm) |
| **Description** | Measures dissolved ions. RO permeate should be <50 μS/cm. High conductivity = membrane leak or salt passage. Related to TDS. |
| **Normal Range** | 20-60 μS/cm |
| **Attack Ranges** | **Multi-Stealth:** Gradual rise 45→70 (subtle quality degradation)<br>**pH Manipulation:** Changes by ±10-20 μS/cm (pH affects ionic strength)<br>**Membrane Damage:** Rises to 150+ (membrane compromised) |
| **Affected By** | Multi-Stealth, pH Manipulation (indirect), Membrane Damage |
| **Cascades To** | **TDS_Permeate** (conductivity ≈ 0.5-0.7 × TDS)<br>**Permeate quality alarm** (>80 μS/cm = reject batch)<br>**RO membrane inspection** (high conductivity = membrane integrity issue) |

---

### AIT_502 - ORP (Oxidation-Reduction Potential)
| Property | Value |
|----------|-------|
| **Address** | Holding Register 28 |
| **Type** | Sensor (Platinum electrode) |
| **Unit** | mV (millivolts) |
| **Description** | Indicates chlorine residual and oxidizing power. High ORP (>700 mV) = good disinfection. Low ORP (<400 mV) = insufficient chlorine or reducing contaminants. |
| **Normal Range** | 600-800 mV |
| **Attack Ranges** | **Chemical Depletion:** Drops to 300-400 mV (no chlorine)<br>**Multi-Stealth:** 650→480 mV<br>**Single Register:** Set to 200 (false alarm) or 1000 (false OK) |
| **Affected By** | Chemical Depletion (via chlorine), Multi-Stealth, Single Register |
| **Cascades To** | **P_205** (chlorine pump, PLC increases dosing if ORP low)<br>**UV_401** (low ORP increases UV demand)<br>**Microbiological risk** (low ORP = high pathogen survival) |

---

### AIT_503 - Dissolved Oxygen
| Property | Value |
|----------|-------|
| **Address** | Holding Register 29 |
| **Type** | Sensor (Galvanic cell) |
| **Unit** | mg/L (ppm) |
| **Description** | Oxygen content. Affects corrosion potential and membrane biofouling. Should be 5-9 mg/L (air-saturated). Very low (<2) = anaerobic conditions (bad). |
| **Normal Range** | 5-9 mg/L |
| **Attack Ranges** | Rarely targeted. May drop during DOS attack (sensor read errors) or chemical attack (reducing agents consume O₂) |
| **Affected By** | DOS (sensor errors), extreme chemical attacks |
| **Cascades To** | **Biofouling risk** (low DO = anaerobic bacteria)<br>**Corrosion rate** (low DO with high chloride = pitting corrosion) |

---

### FIT_501 - RO Feed Flow
| Property | Value |
|----------|-------|
| **Address** | Holding Register 30 |
| **Type** | Sensor (Coriolis mass flow) |
| **Unit** | m³/h ×10 |
| **Description** | Flow into RO membrane. High-pressure system (10-15 bar). Flow affects recovery and flux. |
| **Normal Range** | 25-50 |
| **Attack Ranges** | **Valve Manipulation:** 0-5<br>**Multi-Stealth:** 40→34 (-15%)<br>**Slow Ramp:** 40→20 |
| **Affected By** | Valve Manipulation, Multi-Stealth, Slow Ramp |
| **Cascades To** | **PIT_501** (flow and pressure linked via pump curve)<br>**RO recovery ratio**<br>**FIT_601** (permeate flow) |

---

### PIT_501 - RO Feed Pressure (CRITICAL)
| Property | Value |
|----------|-------|
| **Address** | Holding Register 35 |
| **Type** | Sensor (Piezoresistive pressure transmitter) |
| **Unit** | bar ×10 (e.g., 1200 = 120.0 bar) |
| **Description** | **CRITICAL.** RO requires 10-15 bar (100-150 bar ×10). Too low (<80 bar) = insufficient flux. Too high (>200 bar) = membrane compaction/damage. |
| **Normal Range** | 1000-1500 (100-150 bar) |
| **Attack Ranges** | **Membrane Damage:** Exponential rise 1000→2000 (200 bar) over 240s, causes permanent membrane compaction<br>**Multi-Stealth:** 1050→1470 (+40%)<br>**Valve Manipulation:** Drops to 500-700 (valves closed → pressure falls)<br>**Single Register:** 2500 (250 bar, catastrophic) |
| **Affected By** | Membrane Damage (primary), Multi-Stealth, Valve Manipulation, Single Register |
| **Cascades To** | **High_Pressure_Alarm** (>180 bar = emergency stop)<br>**P_501** (PLC reduces pump speed at high pressure)<br>**RO membrane lifespan** (>180 bar = irreversible compaction)<br>**FIT_501** (pressure/flow relationship via pump curve) |
| **Physics** | Osmotic pressure: π = iCRT (van 't Hoff), where i=ions, C=concentration, R=gas constant, T=temp. Applied pressure must exceed π for permeation. |

---

### TDS_Permeate - Total Dissolved Solids
| Property | Value |
|----------|-------|
| **Address** | Holding Register 38 |
| **Type** | Calculated (from conductivity) or direct sensor |
| **Unit** | ppm (mg/L) |
| **Description** | RO rejection rate = (TDS_feed - TDS_permeate)/TDS_feed. Should be >95%. High TDS = membrane failure. |
| **Normal Range** | 10-50 ppm |
| **Attack Ranges** | **Membrane Damage:** Rises to 150-300 ppm (salt passage increases)<br>**Multi-Stealth:** 35→70 ppm |
| **Affected By** | Membrane Damage, Multi-Stealth |
| **Cascades To** | **AIT_501** (conductivity correlates with TDS)<br>**Permeate rejection criteria** (>100 ppm = reject/re-treat)<br>**Downstream corrosion** (high TDS = higher corrosivity) |

---

### P_501 - High-Pressure RO Pump
| Property | Value |
|----------|-------|
| **Address** | Coil 15 |
| **Type** | Actuator (Multistage centrifugal or positive displacement) |
| **Unit** | Boolean |
| **Description** | Generates 10-15 bar for RO. VFD controlled. Power consumption 50-100 kW (largest pump in system). |
| **Normal Range** | True |
| **Attack Ranges** | **Multi-Point:** False (stops RO)<br>**Single Coil:** False<br>**Tank Overflow:** False (staggered at t=9s) |
| **Affected By** | Multi-Point, Single Coil, Tank Overflow |
| **Cascades To** | **PIT_501** (off → pressure drops to 0)<br>**FIT_501** (off → flow stops)<br>**TDS_Permeate** (off → no permeate production)<br>**Power consumption** (on/off affects facility electrical load significantly) |

---

## STAGE 6: PRODUCT WATER & BACKWASH

### FIT_601 - Product Water Flow
| Property | Value |
|----------|-------|
| **Address** | Holding Register 43 |
| **Type** | Sensor (Magnetic flow meter) |
| **Unit** | m³/h ×10 |
| **Description** | Final product water flow to storage/distribution. Sum of UF permeate + RO permeate. |
| **Normal Range** | 40-70 |
| **Attack Ranges** | Affected by all upstream flow attacks (cumulative effect) |
| **Affected By** | All valve/pump attacks (cascade from upstream) |
| **Cascades To** | **Product totalizer** (cumulative production volume)<br>**Distribution system pressure** |

---

### TEMP_101, TEMP_201 - Temperature Sensors
| Property | Value |
|----------|-------|
| **Address** | Holding Registers 46-47 |
| **Type** | Sensor (PT100 RTD) |
| **Unit** | °C ×10 (e.g., 253 = 25.3°C) |
| **Description** | Water temperature. Affects viscosity, membrane flux, chemical reaction rates. |
| **Normal Range** | 200-300 (20-30°C) |
| **Attack Ranges** | Rarely targeted. May be affected by DOS (sensor errors) or extreme chemical attacks (exothermic reactions) |
| **Affected By** | DOS, chemical attacks (indirect) |
| **Cascades To** | **Membrane flux** (higher temp = higher flux)<br>**Chemical dosing rates** (temperature affects reaction kinetics)<br>**Viscosity** (affects all flow/pressure relationships) |

---

### P_601 - Product Water Pump
| Property | Value |
|----------|-------|
| **Address** | Coil 17 |
| **Type** | Actuator (Centrifugal) |
| **Unit** | Boolean |
| **Description** | Transfers product water to storage tank or distribution. |
| **Normal Range** | True |
| **Attack Ranges** | **Single Coil:** False (stops product delivery)<br>**Multi-Point:** False |
| **Affected By** | Single Coil, Multi-Point |
| **Cascades To** | **FIT_601**<br>**Product storage tank level** |

---

## ALARMS

### High_Level_Alarm
| Property | Value |
|----------|-------|
| **Address** | Coil 21 |
| **Type** | Alarm (discrete output) |
| **Unit** | Boolean |
| **Description** | Triggers when LIT_101, LIT_301, or LIT_401 >900 L. PLC stops upstream pumps. |
| **Normal Range** | False |
| **Attack Ranges** | **Tank Overflow:** True (triggers when level >900)<br>**Single Coil:** True (false alarm, malicious trigger)<br>**Replay:** False (suppressed while tanks actually overflow) |
| **Affected By** | Tank Overflow (indirectly), Single Coil, Replay |
| **Cascades To** | **P_101/102/201/301/401** (PLC stops pumps on alarm)<br>**Operator notification** (HMI flashing red, audible horn)<br>**Emergency shutdown** (if multiple alarms simultaneously) |

---

### Chemical_Low_Alarm
| Property | Value |
|----------|-------|
| **Address** | Coil 22 |
| **Type** | Alarm |
| **Unit** | Boolean |
| **Description** | Triggers when Acid_Tank <15% OR Chlorine_Tank <15% OR Coagulant_Tank <15%. |
| **Normal Range** | False |
| **Attack Ranges** | **Chemical Depletion:** True (tanks depleted by attack)<br>**pH Manipulation:** False (should be True but attack suppresses it)<br>**Single Coil:** True (false alarm) |
| **Affected By** | Chemical Depletion (indirectly), Single Coil |
| **Cascades To** | **P_203/205/206** (PLC stops chemical pumps at <10% for safety)<br>**Maintenance dispatch** (refill trucks called)<br>**Production hold** (can't run without chemicals) |

---

### High_Fouling_Alarm
| Property | Value |
|----------|-------|
| **Address** | Coil 23 |
| **Type** | Alarm |
| **Unit** | Boolean |
| **Description** | Triggers when DPIT_301 >500 (50 kPa). Indicates membrane needs backwash or chemical clean. |
| **Normal Range** | False |
| **Attack Ranges** | **Membrane Damage:** True (TMP rises exponentially, crosses 500 threshold)<br>**Single Coil:** True (false alarm) |
| **Affected By** | Membrane Damage (indirectly), Single Coil |
| **Cascades To** | **UF_Backwash_Active** (should trigger, but attack may disable)<br>**P_301/302** (PLC may reduce flow to lower TMP)<br>**Maintenance alert** (chemical clean-in-place needed) |

---

### High_Pressure_Alarm
| Property | Value |
|----------|-------|
| **Address** | Coil 24 |
| **Type** | Alarm |
| **Unit** | Boolean |
| **Description** | Triggers when PIT_501 >1800 (180 bar). Emergency shutdown to prevent membrane rupture. |
| **Normal Range** | False |
| **Attack Ranges** | **Membrane Damage:** True (pressure rises above 180 bar)<br>**Single Register attack on PIT_501:** True (fake high pressure triggers shutdown) |
| **Affected By** | Membrane Damage (indirectly), Single Register |
| **Cascades To** | **P_501** (emergency stop)<br>**System_Run** (may trigger full system shutdown)<br>**Pressure relief valve** (mechanical safety, vents to drain at 200 bar) |

---

### System_Run
| Property | Value |
|----------|-------|
| **Address** | Coil 19 |
| **Type** | Master enable (discrete output) |
| **Unit** | Boolean |
| **Description** | Master run permissive. False = entire system stopped (all pumps, valves). PLC sets False if multiple alarms or emergency stop pressed. |
| **Normal Range** | True |
| **Attack Ranges** | **Multi-Point:** False (total system shutdown)<br>**Single Coil:** False (malicious shutdown)<br>**Cascade from multiple alarms:** False (safety interlock) |
| **Affected By** | Multi-Point, Single Coil, alarm cascades |
| **Cascades To** | **All pumps** (P_101-601 stop immediately)<br>**All actuators** (valves go to fail-safe positions)<br>**Process shutdown sequence** (drain tanks, depressurize) |

---

## ATTACK IMPACT SUMMARY TABLE

| Attack Type | Primary Targets | Secondary Cascade | Alarm Triggers | Detection Difficulty |
|-------------|----------------|-------------------|----------------|---------------------|
| **pH Manipulation** | AIT_202, P_203 | AIT_501, DPIT_301, Acid_Tank | pH violation (if <600 or >900) | Medium (exponential drift visible) |
| **Tank Overflow** | LIT_101/301/401, P_101/102/201/301/401 | FIT sensors, downstream levels | High_Level_Alarm | Easy (sudden level rise) |
| **Chemical Depletion** | Acid/Cl₂/Coag tanks, P_203/205/206 | AIT_202, AIT_201, DPIT_301 | Chemical_Low_Alarm | Medium (linear drain + cascade) |
| **Membrane Damage** | DPIT_301, PIT_501, UF_Backwash | Recovery ratio, TDS_Permeate | High_Fouling_Alarm, High_Pressure_Alarm | Hard (exponential, slow) |
| **Valve Manipulation** | MV_101/201/301-304 | All flow sensors, levels, pressures | High_Level (if upstream fills) | Medium (hydraulic transient) |
| **Slow Ramp** | Any variable (often LIT_401) | Depends on target | None (below thresholds) | Very Hard (stealth, <1%/s) |
| **Multi-Stealth** | pH, flow, TMP, acid (4 simultaneous) | Quality degradation | None (all below thresholds) | Extreme (requires ML) |
| **Reconnaissance** | All sensors (read burst) | Network congestion | None (read-only) | Easy (network IDS) |
| **DOS Flood** | PLC CPU, network bandwidth | All sensors (read errors) | Possibly High_Pressure (if watchdog triggers) | Easy (network rate monitoring) |
| **Replay** | Critical sensors (pH, LIT, DPIT) | All downstream logic | None (appears normal) | Hard (need temporal analysis) |
| **Single Register** | Any 1 sensor | Depends on target | Immediate (if extreme value) | Easy (single outlier) |
| **Single Coil** | Any 1 actuator | Depends on target | Depends (pump off = level drop) | Easy (isolated action) |
| **Multi-Point** | 5+ vars simultaneously | System-wide | Multiple alarms | Medium (obvious chaos) |

---

## PHYSICAL INTERDEPENDENCIES (MASS & ENERGY BALANCE)

### Mass Balance Equations
```
Tank 1: dLIT_101/dt = FIT_101 - FIT_201
Tank 3: dLIT_301/dt = FIT_201 - FIT_301
Tank 4: dLIT_401/dt = FIT_301 - FIT_401

Violation detection: If |Σinflow - Σoutflow - dV/dt| > threshold → ATTACK
```

### Energy Balance
```
Pump power: P = ρ × g × Q × H / η
Where ρ=density, g=gravity, Q=flow, H=head, η=efficiency

Sudden pump stop: kinetic energy → pressure surge (water hammer)
ΔP_max = ρ × c × Δv  (Joukowsky equation)
```

### Chemical Equilibrium
```
pH buffer: [HA] ⇌ [H⁺] + [A⁻]
Ka = [H⁺][A⁻]/[HA]
pH = pKa + log([A⁻]/[HA])

Attack detection: pH change rate violates first-order kinetics
```

---

**END OF COMPLETE VARIABLE REFERENCE**

Total: 76 variables (51 registers + 25 coils) fully documented.