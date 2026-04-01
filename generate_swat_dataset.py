#!/usr/bin/env python3
"""
generate_swat_dataset.py
========================
Offline synthetic SWaT dataset generator — no MATLAB or CODESYS needed.

Generates two datasets:
  1. normal_24h/master_dataset.csv   — 24 h of realistic normal operation
     (tank oscillations, backwash cycles, RO fouling/CIP, diurnal demand)
  2. attack_24h/master_dataset.csv   — 24 h with all 9 attack types injected

Physics model is a faithful Python port of swat_physics_server.m and the ST
control logic.  Sampling rate: 1 Hz  →  86 400 rows per 24 h file.

Usage:
    python generate_swat_dataset.py               # both normal + attack
    python generate_swat_dataset.py --mode normal
    python generate_swat_dataset.py --mode attack
    python generate_swat_dataset.py --hours 1     # quick 1-h test
    python generate_swat_dataset.py --seed 42     # reproducible
"""

import argparse
import csv
import math
import os
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ─── CSV columns (matches physics_client.py CSV_COLUMNS) ─────────────────────
CSV_COLUMNS = [
    'Timestamp',
    # S1
    'FIT_101','LIT_101','MV_101','P_101','P_102',
    # S2
    'AIT_201','AIT_202','AIT_203','Chlorine_Residual',
    'FIT_201','MV_201',
    'P_201','P_202','P_203','P_204','P_205','P_206',
    'Acid_Tank_Level','Chlorine_Tank_Level','Coagulant_Tank_Level','Bisulfate_Tank_Level',
    # S3
    'DPIT_301','FIT_301','LIT_301',
    'MV_301','MV_302','MV_303','MV_304',
    'P_301','P_302',
    'UF_Runtime','UF_Fouling_Factor','UF_Last_Backwash',
    'UF_Backwash_Active','Turbidity_UF',
    # S4
    'AIT_401','AIT_402','FIT_401','LIT_401',
    'P_401','P_402','P_403','P_404','UV_401',
    # S5
    'AIT_501','AIT_502','AIT_503','AIT_504',
    'FIT_501','FIT_502','FIT_503','FIT_504',
    'PIT_501','PIT_502','PIT_503',
    'P_501','P_502',
    'RO_Runtime','RO_Fouling_Factor','RO_Last_Cleaning','RO_Cleaning_Active',
    'TDS_Feed','TDS_Permeate',
    # S6
    'FIT_601','P_601','P_602','P_603',
    # environmental & energy
    'Water_Temperature','Ambient_Temperature',
    'Energy_P101','Energy_P301','Energy_P501','Energy_Total',
    'Turbidity_Raw',
    # alarms
    'Chemical_Low_Alarm','High_Fouling_Alarm','Energy_Monitor_Enable',
    'High_Level_Alarm','High_Pressure_Alarm','System_Run',
    # labels
    'ATTACK_ID','ATTACK_NAME','MITRE_ID',
]

# ─── Attack catalogue ─────────────────────────────────────────────────────────
ATTACKS = {
    8:  ('Tank Overflow',         'T0815'),
    9:  ('Chemical Depletion',    'T0809'),
    10: ('Membrane Damage',       'T0816'),
    11: ('pH Manipulation',       'T0836'),
    12: ('Slow Ramp',             'T0832'),
    13: ('Reconnaissance',        'T0840'),
    14: ('Denial of Service',     'T0814'),
    15: ('Replay Attack',         'T0839'),
    16: ('Valve Manipulation',    'T0836'),
}

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def noise(rng, sigma):
    return rng.gauss(0, sigma)

# ─── Physics state ────────────────────────────────────────────────────────────
class SWaTPhysics:
    """
    Complete physics + ST control logic for the SWaT 6-stage water treatment
    plant.  Mirrors swat_physics_server.m behaviour at 1 Hz.
    """
    DT = 1.0   # seconds

    def __init__(self, rng, demand_scale=1.0):
        self.rng = rng
        self.demand_scale = demand_scale   # diurnal demand multiplier hook

        # ── Tank levels (L) ──────────────────────────────────────────────
        self.LIT_101 = rng.uniform(450, 550)
        self.LIT_301 = rng.uniform(700, 800)
        self.LIT_401 = rng.uniform(450, 550)

        # ── Flows (m³/h) ─────────────────────────────────────────────────
        self.FIT_101 = 0.0
        self.FIT_201 = 0.0
        self.FIT_301 = 0.0
        self.FIT_401 = 0.0
        self.FIT_501 = 0.0
        self.FIT_502 = 0.0
        self.FIT_503 = 0.0
        self.FIT_504 = 0.0
        self.FIT_601 = 0.0

        # ── Quality sensors ──────────────────────────────────────────────
        self.AIT_201 = rng.uniform(40, 60)    # turbidity (NTU)
        self.AIT_202 = rng.uniform(700, 730)  # pH × 100
        self.AIT_203 = rng.uniform(200, 250)  # ORP_NaOCl (mV)
        self.AIT_401 = rng.uniform(0.5, 1.5)  # mg/L
        self.AIT_402 = rng.uniform(180, 220)  # ORP mV
        self.AIT_501 = rng.uniform(40, 60)    # µS/cm
        self.AIT_502 = rng.uniform(180, 220)  # mV
        self.AIT_503 = rng.uniform(0, 5)      # ppb
        self.AIT_504 = rng.uniform(690, 730)  # pH × 100

        self.Chlorine_Residual = rng.uniform(30, 40)   # mg/L × 10

        # ── Pressure (stored as bar × 10) ────────────────────────────────
        self.PIT_501 = 1200
        self.PIT_502 = 50
        self.PIT_503 = 1100

        # ── Transform pressure / TMP (stored value registers) ────────────
        self.DPIT_301 = 250   # kPa × 10

        # ── Chemical tanks (%) ───────────────────────────────────────────
        self.Acid_Tank_Level      = rng.uniform(70, 85)
        self.Chlorine_Tank_Level  = rng.uniform(70, 85)
        self.Coagulant_Tank_Level = rng.uniform(70, 85)
        self.Bisulfate_Tank_Level = rng.uniform(70, 85)

        # ── Fouling / runtime ────────────────────────────────────────────
        self.UF_Fouling_Factor  = 0.0
        self.UF_Runtime         = 0.0
        self.UF_Last_Backwash   = 0.0
        self.RO_Fouling_Factor  = 0.0
        self.RO_Runtime         = 0.0
        self.RO_Last_Cleaning   = 0.0

        self.Turbidity_UF = 0.0
        self.Turbidity_Raw = rng.uniform(1300, 1700)
        self.TDS_Feed = 5000
        self.TDS_Permeate = 50

        self.Water_Temperature   = rng.uniform(24, 26)
        self.Ambient_Temperature = rng.uniform(24, 26)

        # ── Energy ───────────────────────────────────────────────────────
        self.Energy_P101 = 0.0
        self.Energy_P301 = 0.0
        self.Energy_P501 = 0.0
        self.Energy_Total = 0.0

        # ── Actuators (coils) ────────────────────────────────────────────
        self.P_101 = True;  self.P_102 = False
        self.P_201 = False; self.P_202 = False
        self.P_203 = True;  self.P_204 = False
        self.P_205 = True;  self.P_206 = False
        self.P_301 = True;  self.P_302 = False
        self.P_401 = True;  self.P_402 = False
        self.P_403 = False; self.P_404 = False
        self.P_501 = True;  self.P_502 = False
        self.P_601 = True;  self.P_602 = False; self.P_603 = True
        self.UV_401 = True

        self.MV_101 = 1; self.MV_201 = 1; self.MV_301 = 1; self.MV_302 = 1
        self.MV_303 = 0; self.MV_304 = 0

        # ── State flags ─────────────────────────────────────────────────
        self.UF_Backwash_Active  = False
        self.RO_Cleaning_Active  = False
        self.Chemical_Low_Alarm  = False
        self.High_Fouling_Alarm  = False
        self.High_Level_Alarm    = False
        self.High_Pressure_Alarm = False
        self.System_Run          = True

    # ── helpers ──────────────────────────────────────────────────────────────
    def _n(self, s): return noise(self.rng, s)

    # ── one simulation step ───────────────────────────────────────────────────
    def step(self, diurnal_factor=1.0):
        dt = self.DT
        n = self._n

        # ── Stage 1: inlet / tank ────────────────────────────────────────
        Qin = (5 + n(0.2)) * diurnal_factor / 3.6 if self.MV_101 > 0 else 0.2 / 3.6
        Qout = 0.0
        if self.P_101 or self.P_102:
            base_q = 4.0 + (0.8 if self.LIT_101 > 400 else 0) + (0.8 if self.LIT_101 > 600 else 0)
            if self.P_102: base_q += 2.0
            Qout = (base_q + n(0.1)) * diurnal_factor / 3.6
        self.LIT_101 = clamp(self.LIT_101 + (Qin - Qout) * dt, 0, 1000)
        self.FIT_101 = round(Qin * 3.6, 2)
        self.FIT_201 = round(Qout * 3.6, 2)

        # ── ST S1 control ────────────────────────────────────────────────
        if self.LIT_101 < 200: self.MV_101 = 1
        elif self.LIT_101 > 850: self.MV_101 = 0
        self.P_101 = self.LIT_101 > 200 and self.LIT_301 < 800
        self.P_102 = self.P_101 and self.LIT_101 > 600
        if self.LIT_101 < 50: self.P_101 = self.P_102 = False
        self.MV_201 = 1 if (self.P_101 or self.P_102) else 0

        # ── Stage 2: chemical dosing / pH ────────────────────────────────
        pH_target = 6.80 if self.P_203 else 8.50
        pH_now = self.AIT_202 / 100
        pH_new = pH_target + (pH_now - pH_target) * math.exp(-dt / 40) + n(0.005)
        self.AIT_202 = round(clamp(pH_new * 100, 550, 900))

        if self.P_205:
            self.Chlorine_Residual = clamp(self.Chlorine_Residual + 0.3 * dt + n(0.02), 0, 80)
            self.Chlorine_Tank_Level = max(0, self.Chlorine_Tank_Level - 0.001 * dt)
        else:
            self.Chlorine_Residual = max(10, self.Chlorine_Residual - 0.1 * dt)
        if self.P_203: self.Acid_Tank_Level = max(0, self.Acid_Tank_Level - 0.0005 * dt)
        if self.P_206: self.Coagulant_Tank_Level = max(0, self.Coagulant_Tank_Level - 0.001 * dt)
        self.AIT_201 = clamp(self.AIT_201 + n(0.5), 10, 500)

        # ── ST S2 control ────────────────────────────────────────────────
        if self.P_101 or self.P_102:
            if self.AIT_202 > 750: self.P_203 = True
            elif self.AIT_202 < 680: self.P_203 = False
            if self.Chlorine_Residual < 20: self.P_205 = True
            elif self.Chlorine_Residual > 50: self.P_205 = False
            if self.AIT_201 > 400: self.P_206 = True
            elif self.AIT_201 < 200: self.P_206 = False
        else:
            self.P_203 = self.P_205 = self.P_206 = False

        # pH safety interlock
        if self.AIT_202 > 900 or self.AIT_202 < 550:
            self.P_101 = self.P_102 = self.P_301 = self.P_401 = False

        # Chemical low alarm
        self.Chemical_Low_Alarm = any([
            self.Acid_Tank_Level < 15, self.Chlorine_Tank_Level < 15,
            self.Coagulant_Tank_Level < 15, self.Bisulfate_Tank_Level < 15
        ])

        # ── Stage 3: UF ─────────────────────────────────────────────────
        if self.P_301 and not self.UF_Backwash_Active:
            self.UF_Runtime = min(30000, self.UF_Runtime + dt)
            self.UF_Last_Backwash = min(30000, self.UF_Last_Backwash + dt)
            self.UF_Fouling_Factor = min(100,
                self.UF_Fouling_Factor + 0.001 * (1 + self.AIT_201 / 1000) * dt * 100)
            self.DPIT_301 = round((25 + self.UF_Fouling_Factor) * 10)
            self.FIT_301 = round(max(2, 5 - (self.UF_Fouling_Factor / 100) * 3) * 10)
        self.LIT_301 = clamp(self.LIT_301 + (self.FIT_201 / 36 - self.FIT_301 / 360) * dt, 0, 1000)

        # ST S3 control
        if self.LIT_301 > 200 and self.LIT_401 < 800:
            self.MV_301 = self.MV_302 = 1; self.P_301 = True
        else:
            self.MV_301 = self.MV_302 = 0; self.P_301 = False

        # UF backwash (DPIT > 600 OR timer > 18000 s)
        if self.DPIT_301 > 600 or self.UF_Last_Backwash > 18000:
            self.UF_Backwash_Active = True; self.P_301 = False
            self.P_602 = True; self.MV_303 = self.MV_304 = 1
            self.High_Fouling_Alarm = True
            self.UF_Fouling_Factor = max(0, self.UF_Fouling_Factor - 10 * dt)
            self.DPIT_301 = max(100, self.DPIT_301 - 50)
            if self.UF_Fouling_Factor < 1:
                self.UF_Last_Backwash = 0; self.UF_Backwash_Active = False
                self.P_602 = False; self.MV_303 = self.MV_304 = 0
        else:
            self.UF_Backwash_Active = False; self.P_602 = False
            self.MV_303 = self.MV_304 = 0; self.High_Fouling_Alarm = False

        # Turbidity_UF
        self.Turbidity_UF = max(0, self.UF_Fouling_Factor * 0.5 + n(0.5))

        # ── Stage 4: dechlorination ──────────────────────────────────────
        self.P_401 = self.LIT_401 > 200
        self.UV_401 = self.P_401
        self.P_403 = self.P_401 and self.Chlorine_Residual > 20
        if self.P_403: self.Bisulfate_Tank_Level = max(0, self.Bisulfate_Tank_Level - 0.0005 * dt)
        Qdc = (60 if self.LIT_401 > 700 else 50 if self.LIT_401 > 500 else 40) if self.P_401 else 10
        self.FIT_401 = Qdc / 10
        self.LIT_401 = clamp(self.LIT_401 + (self.FIT_301 / 360 - Qdc / 360) * dt, 0, 1000)
        self.AIT_402 = clamp(self.AIT_402 + n(1.0), 150, 250)

        # ── Stage 5: RO ──────────────────────────────────────────────────
        self.P_501 = self.P_401 and self.LIT_401 > 200
        if self.P_501:
            self.RO_Fouling_Factor = min(100, self.RO_Fouling_Factor + 0.05 * dt)
            self.RO_Runtime = min(30000, self.RO_Runtime + dt)
            self.RO_Last_Cleaning = min(30000, self.RO_Last_Cleaning + dt)
            self.PIT_501 = round((120 + self.RO_Fouling_Factor * 0.8) * 10)
            self.PIT_502 = round(50 + noise(self.rng, 1) * 10)
            self.FIT_501 = round(max(2, 5 - (self.RO_Fouling_Factor / 100) * 3), 2)
            self.FIT_502 = round(max(2, 4 - (self.RO_Fouling_Factor / 100) * 2), 2)
            self.TDS_Permeate = round(self.TDS_Feed * 15 / 1000)

        # ST: RO CIP
        if self.RO_Fouling_Factor > 80 or self.RO_Last_Cleaning > 1000:
            self.RO_Cleaning_Active = True; self.P_501 = False; self.High_Fouling_Alarm = True
            self.RO_Fouling_Factor = max(0, self.RO_Fouling_Factor - 5 * dt)
            if self.RO_Fouling_Factor < 2: self.RO_Last_Cleaning = 0; self.RO_Cleaning_Active = False
        else:
            self.RO_Cleaning_Active = False

        # ── Stage 6: distribution ────────────────────────────────────────
        self.P_601 = self.P_603 = self.P_501
        self.FIT_601 = round(self.FIT_502 + noise(self.rng, 0.1), 2) if self.P_601 else 0.0

        # ── Alarms ──────────────────────────────────────────────────────
        self.High_Level_Alarm    = self.LIT_101 > 950 or self.LIT_301 > 950 or self.LIT_401 > 950
        self.High_Pressure_Alarm = self.PIT_501 > 2000 or self.PIT_502 > 30
        self.System_Run          = not (self.High_Pressure_Alarm or self.High_Level_Alarm)

        # ── Energy ──────────────────────────────────────────────────────
        if self.P_101: self.Energy_P101 += 0.75 * dt / 3600
        if self.P_301: self.Energy_P301 += 1.10 * dt / 3600
        if self.P_501: self.Energy_P501 += 3.50 * dt / 3600
        self.Energy_Total = self.Energy_P101 + self.Energy_P301 + self.Energy_P501

        # ── Environmental sensor drift ───────────────────────────────────
        self.Water_Temperature   += noise(self.rng, 0.01)
        self.Ambient_Temperature += noise(self.rng, 0.02)
        self.Turbidity_Raw = clamp(self.Turbidity_Raw + noise(self.rng, 5), 500, 3000)

    def row(self, ts, attack_id=0):
        name, mitre = ATTACKS.get(attack_id, ('Normal', 'T0'))
        if attack_id == 0: name = 'Normal'; mitre = 'T0'
        return {
            'Timestamp': ts,
            'FIT_101': round(self.FIT_101, 3), 'LIT_101': round(self.LIT_101, 1),
            'MV_101': self.MV_101, 'P_101': int(self.P_101), 'P_102': int(self.P_102),
            'AIT_201': round(self.AIT_201, 1), 'AIT_202': round(self.AIT_202 / 100, 2),
            'AIT_203': round(self.AIT_203, 1),
            'Chlorine_Residual': round(self.Chlorine_Residual / 10, 2),
            'FIT_201': round(self.FIT_201, 3), 'MV_201': self.MV_201,
            'P_201': 0, 'P_202': 0, 'P_203': int(self.P_203), 'P_204': 0,
            'P_205': int(self.P_205), 'P_206': int(self.P_206),
            'Acid_Tank_Level': round(self.Acid_Tank_Level, 1),
            'Chlorine_Tank_Level': round(self.Chlorine_Tank_Level, 1),
            'Coagulant_Tank_Level': round(self.Coagulant_Tank_Level, 1),
            'Bisulfate_Tank_Level': round(self.Bisulfate_Tank_Level, 1),
            'DPIT_301': round(self.DPIT_301 / 10, 1), 'FIT_301': round(self.FIT_301 / 10, 2),
            'LIT_301': round(self.LIT_301, 1),
            'MV_301': self.MV_301, 'MV_302': self.MV_302,
            'MV_303': self.MV_303, 'MV_304': self.MV_304,
            'P_301': int(self.P_301), 'P_302': 0,
            'UF_Runtime': round(self.UF_Runtime, 0),
            'UF_Fouling_Factor': round(self.UF_Fouling_Factor, 2),
            'UF_Last_Backwash': round(self.UF_Last_Backwash, 0),
            'UF_Backwash_Active': int(self.UF_Backwash_Active),
            'Turbidity_UF': round(self.Turbidity_UF, 2),
            'AIT_401': round(self.AIT_401, 3), 'AIT_402': round(self.AIT_402, 1),
            'FIT_401': round(self.FIT_401, 2), 'LIT_401': round(self.LIT_401, 1),
            'P_401': int(self.P_401), 'P_402': 0, 'P_403': int(self.P_403),
            'P_404': 0, 'UV_401': int(self.UV_401),
            'AIT_501': round(self.AIT_501, 1), 'AIT_502': round(self.AIT_502, 1),
            'AIT_503': round(self.AIT_503, 2), 'AIT_504': round(self.AIT_504 / 100, 2),
            'FIT_501': round(self.FIT_501, 3), 'FIT_502': round(self.FIT_502, 3),
            'FIT_503': 0.0, 'FIT_504': 0.0,
            'PIT_501': round(self.PIT_501 / 10, 1),
            'PIT_502': round(self.PIT_502 / 10, 1), 'PIT_503': round(self.PIT_503 / 10, 1),
            'P_501': int(self.P_501), 'P_502': 0,
            'RO_Runtime': round(self.RO_Runtime, 0),
            'RO_Fouling_Factor': round(self.RO_Fouling_Factor, 2),
            'RO_Last_Cleaning': round(self.RO_Last_Cleaning, 0),
            'RO_Cleaning_Active': int(self.RO_Cleaning_Active),
            'TDS_Feed': self.TDS_Feed, 'TDS_Permeate': round(self.TDS_Permeate, 1),
            'FIT_601': round(self.FIT_601, 3),
            'P_601': int(self.P_601), 'P_602': int(self.P_602), 'P_603': int(self.P_603),
            'Water_Temperature': round(self.Water_Temperature, 2),
            'Ambient_Temperature': round(self.Ambient_Temperature, 2),
            'Energy_P101': round(self.Energy_P101, 4),
            'Energy_P301': round(self.Energy_P301, 4),
            'Energy_P501': round(self.Energy_P501, 4),
            'Energy_Total': round(self.Energy_Total, 4),
            'Turbidity_Raw': round(self.Turbidity_Raw, 1),
            'Chemical_Low_Alarm': int(self.Chemical_Low_Alarm),
            'High_Fouling_Alarm': int(self.High_Fouling_Alarm),
            'Energy_Monitor_Enable': 1,
            'High_Level_Alarm': int(self.High_Level_Alarm),
            'High_Pressure_Alarm': int(self.High_Pressure_Alarm),
            'System_Run': int(self.System_Run),
            'ATTACK_ID': attack_id,
            'ATTACK_NAME': name,
            'MITRE_ID': mitre,
        }


# ─── Attack injection (modifies physics state in-place) ──────────────────────
class AttackInjector:
    """Applies attack-specific sensor overrides each cycle."""

    def __init__(self, rng):
        self.rng = rng
        self.state = {}   # persistent per-attack state

    def reset(self):
        self.state.clear()

    def inject(self, phys: SWaTPhysics, attack_id: int, params: dict, t_since: float):
        """Modify phys state in-place for one cycle."""
        dt = phys.DT

        if attack_id == 11:  # pH Manipulation
            target = params.get('target_ph', 5.0) * 100
            cur = phys.AIT_202
            phys.AIT_202 = round(cur + (target - cur) * (1 - math.exp(-dt / 40)))
            phys.P_203 = False   # block acid pump so CODESYS can't correct

        elif attack_id == 12:  # Slow Ramp
            if 'ramp_current' not in self.state:
                self.state['ramp_current'] = float(phys.AIT_202)
                self.state['direction'] = params.get('direction', 1)
            step_every = params.get('step_interval', 2.0)
            if t_since % step_every < dt:
                self.state['ramp_current'] += self.state['direction'] * params.get('step_size', 1)
            self.state['ramp_current'] = clamp(self.state['ramp_current'], 500, 960)
            phys.AIT_202 = round(self.state['ramp_current'])

        elif attack_id == 8:   # Tank Overflow
            # Spoofs LIT_101 level reading downward so MV_101 stays open
            phys.MV_101 = 1
            phys.LIT_101 = clamp(phys.LIT_101 + 1.5 * dt, 0, 1020)
            phys.P_101 = phys.P_102 = False  # stop outflow control

        elif attack_id == 9:   # Chemical Depletion
            phys.Acid_Tank_Level      = max(0, phys.Acid_Tank_Level - 0.5 * dt)
            phys.Chlorine_Tank_Level  = max(0, phys.Chlorine_Tank_Level - 0.5 * dt)
            phys.Coagulant_Tank_Level = max(0, phys.Coagulant_Tank_Level - 0.5 * dt)
            phys.Bisulfate_Tank_Level = max(0, phys.Bisulfate_Tank_Level - 0.3 * dt)

        elif attack_id == 10:  # Membrane Damage
            phys.DPIT_301 = min(700, phys.DPIT_301 + 50 * dt)
            phys.UF_Fouling_Factor = min(100, phys.UF_Fouling_Factor + 5 * dt)

        elif attack_id == 16:  # Valve Manipulation
            phys.MV_101 = 0; phys.MV_301 = 0
            # Tanks drain / fill unexpectedly
            phys.LIT_101 = max(0, phys.LIT_101 - 2 * dt)
            phys.LIT_301 = clamp(phys.LIT_301 + 1.5 * dt, 0, 1000)

        elif attack_id == 13:  # Reconnaissance — no physical effect, label only
            pass

        elif attack_id == 14:  # Denial of Service
            # Simulates stale / frozen sensor readings
            if 'frozen' not in self.state:
                self.state['frozen'] = {
                    'LIT_101': phys.LIT_101, 'AIT_202': phys.AIT_202,
                    'PIT_501': phys.PIT_501
                }
            for k, v in self.state['frozen'].items():
                setattr(phys, k, v)

        elif attack_id == 15:  # Replay
            if 'snapshot' not in self.state:
                self.state['snapshot'] = {
                    'LIT_101': phys.LIT_101, 'AIT_202': phys.AIT_202,
                    'DPIT_301': phys.DPIT_301, 'PIT_501': phys.PIT_501
                }
            # Replay spoofs pH to look normal while process drifts
            phys.AIT_202 = round(self.state['snapshot']['AIT_202'])
            phys.PIT_501 = self.state['snapshot']['PIT_501']


# ─── Diurnal demand helper ────────────────────────────────────────────────────
def diurnal_factor(second_of_day: int) -> float:
    """Return demand multiplier 0.7–1.3 based on time of day."""
    h = (second_of_day % 86400) / 3600
    # Peak at 8 AM and 7 PM, trough at 3 AM
    return 1.0 + 0.25 * math.sin(2 * math.pi * (h - 7) / 24) \
               + 0.05 * math.sin(4 * math.pi * (h - 3) / 24)


# ─── Attack schedule for 24h attack dataset ───────────────────────────────────
def build_attack_schedule(hours: float, rng: random.Random) -> list:
    """
    Build a list of (start_s, end_s, attack_id, params) tuples covering
    ~35–40 % of the total run with all 9 attack types used at least once.

    Attack density targets (of total time):
        Network attacks  (13,14,15): ~10 % each  (short, frequent)
        Process attacks  rest:       ~5–8 % each
    """
    total_s = int(hours * 3600)
    schedule = []
    cooldown_until = {aid: 0 for aid in ATTACKS}

    # Guaranteed single occurrence of each attack type first
    required = list(ATTACKS.keys())
    rng.shuffle(required)

    cursor = int(total_s * 0.05)   # start after 5% warmup
    for aid in required:
        if cursor >= int(total_s * 0.95): break
        dur = rng.randint(300, 600) if aid in (13, 14, 15) else rng.randint(600, 900)
        dur = min(dur, int(total_s * 0.95) - cursor)
        params = _attack_params(aid, rng)
        schedule.append((cursor, cursor + dur, aid, params))
        cooldown_until[aid] = cursor + dur + rng.randint(300, 600)
        cursor += dur + rng.randint(120, 600)   # normal gap

    # Fill remaining time with random repeats
    while cursor < int(total_s * 0.90):
        eligible = [aid for aid in ATTACKS if cooldown_until[aid] <= cursor]
        if not eligible:
            cursor += 60; continue
        aid = rng.choice(eligible)
        dur = rng.randint(300, 600) if aid in (13, 14, 15) else rng.randint(600, 900)
        dur = min(dur, int(total_s * 0.90) - cursor)
        if dur < 60: break
        params = _attack_params(aid, rng)
        schedule.append((cursor, cursor + dur, aid, params))
        cooldown_until[aid] = cursor + dur + rng.randint(300, 600)
        cursor += dur + rng.randint(120, 600)

    schedule.sort(key=lambda x: x[0])
    return schedule


def _attack_params(aid: int, rng: random.Random) -> dict:
    if aid == 11:
        return {'target_ph': round(rng.choice([rng.uniform(4.8, 5.5), rng.uniform(8.7, 9.3)]), 2)}
    elif aid == 12:
        return {'direction': rng.choice([-1, 1]), 'step_size': 1, 'step_interval': 2.0}
    elif aid == 8:
        return {'overflow_value': rng.randint(970, 1050)}
    return {}


# ─── Main generator ───────────────────────────────────────────────────────────
def generate(mode: str, output_dir: str, hours: float, seed: int):
    rng = random.Random(seed)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / 'master_dataset.csv'

    total_steps = int(hours * 3600)
    start_ts    = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    print(f'\n{"="*60}')
    print(f'  Mode     : {mode.upper()}')
    print(f'  Duration : {hours:.1f} h  ({total_steps:,} rows @ 1 Hz)')
    print(f'  Output   : {csv_path}')
    print(f'  Seed     : {seed}')
    print(f'{"="*60}')

    # Build attack schedule (empty for normal mode)
    attack_schedule = []
    if mode == 'attack':
        attack_schedule = build_attack_schedule(hours, rng)
        print(f'\n  Attack schedule: {len(attack_schedule)} windows')
        for s, e, aid, p in attack_schedule:
            name = ATTACKS[aid][0]
            print(f'    [{s//60:4d}–{e//60:4d} min] {name} ({(e-s)//60} min)')
        total_atk = sum(e - s for s, e, _, _ in attack_schedule)
        print(f'  Total attack time: {total_atk/3600:.2f} h ({total_atk/total_steps*100:.1f}%)\n')

    # Index attack intervals for O(1) lookup
    atk_index = {}
    injector = AttackInjector(rng)
    for s, e, aid, params in attack_schedule:
        for t in range(s, e):
            atk_index[t] = (aid, params, t - s)

    phys = SWaTPhysics(rng)

    t0 = time.perf_counter()
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction='ignore')
        writer.writeheader()

        prev_attack_id = 0
        for step in range(total_steps):
            ts = (start_ts + timedelta(seconds=step)).isoformat()
            df = diurnal_factor(step)

            # Attack this step?
            attack_id = 0
            if step in atk_index:
                attack_id, params, t_since = atk_index[step]
                if attack_id != prev_attack_id:
                    injector.reset()
                injector.inject(phys, attack_id, params, float(t_since))
            elif prev_attack_id != 0:
                injector.reset()

            prev_attack_id = attack_id

            # Physics step
            phys.step(diurnal_factor=df)

            # Write row
            writer.writerow(phys.row(ts, attack_id))

            # Progress every 10 min
            if step % 600 == 0:
                pct = step / total_steps * 100
                elapsed = time.perf_counter() - t0
                eta = (elapsed / max(step, 1)) * (total_steps - step)
                print(f'  {pct:5.1f}%  step={step:6d}/{total_steps}  '
                      f'elapsed={elapsed:.0f}s  ETA={eta:.0f}s', flush=True)

    elapsed = time.perf_counter() - t0
    size_mb = csv_path.stat().st_size / 1e6
    print(f'\n  [OK] Done in {elapsed:.1f}s -- {csv_path} ({size_mb:.1f} MB)')

    # Write summary
    summary = {
        'mode': mode, 'hours': hours, 'rows': total_steps, 'seed': seed,
        'output': str(csv_path.resolve()),
        'attack_schedule': [
            {'start_s': s, 'end_s': e, 'attack_id': aid,
             'attack_name': ATTACKS[aid][0], 'mitre': ATTACKS[aid][1], 'params': p}
            for s, e, aid, p in attack_schedule
        ]
    }
    import json
    with open(out / 'generation_summary.json', 'w') as jf:
        json.dump(summary, jf, indent=2)
    print(f'  [OK] Summary -> {out}/generation_summary.json')
    return csv_path


# ─── CLI ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description='SWaT Synthetic Dataset Generator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full 24-h normal baseline:
  python generate_swat_dataset.py --mode normal --output data/normal_24h

  # Full 24-h attack dataset:
  python generate_swat_dataset.py --mode attack --output data/attack_24h

  # Quick 1-h test of both:
  python generate_swat_dataset.py --hours 1

  # Reproducible run:
  python generate_swat_dataset.py --seed 42
"""
    )
    parser.add_argument('--mode',   choices=['normal', 'attack', 'both'], default='both',
                        help='Dataset type to generate (default: both)')
    parser.add_argument('--hours',  type=float, default=24.0,
                        help='Duration in hours (default: 24)')
    parser.add_argument('--seed',   type=int,   default=2026,
                        help='RNG seed (default: 2026)')
    parser.add_argument('--output', default=None,
                        help='Output directory (default: data/normal_24h or data/attack_24h)')
    args = parser.parse_args()

    modes = ['normal', 'attack'] if args.mode == 'both' else [args.mode]

    for m in modes:
        out_dir = args.output if args.output else f'data/{m}_24h'
        generate(m, out_dir, args.hours, args.seed)

    print('\n[DONE] All datasets generated.')
    print('   Run ML pipeline:')
    print('   python swat_ml_pipeline.py --data-dir data --runs normal_24h attack_24h')


if __name__ == '__main__':
    main()
