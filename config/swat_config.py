#!/usr/bin/env python3
"""
SWAT Configuration - ML-Ready Version
Added Chlorine_Residual variable at register 6
"""

# Modbus connection settings
MODBUS_CONFIG = {
    'host': '192.168.5.194',
    'port': 1502,
    'timeout': 3,
    'retries': 3,
    'unit_id': 1,
}

# Logging configuration
LOGGING_CONFIG = {
    'csv_path': 'dataset/master_dataset.csv',
    'log_path': 'logs/swat_system.log',
    'buffer_size': 100,
    'poll_interval': 1.0,  # 1 Hz sampling
}

# Holding Registers (sensors, setpoints, tank levels)
HOLDING_REGISTERS = {

    # Stage 1
    'FIT_101':              {'address': 0,  'scale': 10,  'unit': 'm³/h'},
    'LIT_101':              {'address': 1,  'scale': 1,   'unit': 'L'},
    'MV_101':               {'address': 2,  'scale': 1,   'unit': ''},

    # Stage 2
    'AIT_201':              {'address': 3,  'scale': 10,  'unit': 'NTU'},
    'AIT_202':              {'address': 4,  'scale': 100, 'unit': 'pH'},
    'AIT_203':              {'address': 5,  'scale': 1,   'unit': 'mV'},     # ORP NaOCl (fixed: was wrong unit µS/cm)

    'FIT_201':              {'address': 6,  'scale': 10,  'unit': 'm³/h'},
    'MV_201':               {'address': 7,  'scale': 1,   'unit': ''},
    'Acid_Tank_Level':      {'address': 8,  'scale': 1,   'unit': '%'},
    'Chlorine_Tank_Level':  {'address': 9,  'scale': 1,   'unit': '%'},
    'Coagulant_Tank_Level': {'address': 10, 'scale': 1,   'unit': '%'},
    'Bisulfate_Tank_Level': {'address': 11, 'scale': 1,   'unit': '%'},

    # Stage 3
    'DPIT_301':             {'address': 12, 'scale': 10,  'unit': 'kPa'},
    'FIT_301':              {'address': 13, 'scale': 10,  'unit': 'm³/h'},
    'LIT_301':              {'address': 14, 'scale': 1,   'unit': 'L'},
    'MV_301':               {'address': 15, 'scale': 1,   'unit': ''},
    'MV_302':               {'address': 16, 'scale': 1,   'unit': ''},
    'MV_303':               {'address': 17, 'scale': 1,   'unit': ''},
    'MV_304':               {'address': 18, 'scale': 1,   'unit': ''},
    'UF_Runtime':           {'address': 19, 'scale': 1,   'unit': 's'},
    'UF_Fouling_Factor':    {'address': 20, 'scale': 1,   'unit': '%'},
    'UF_Last_Backwash':     {'address': 21, 'scale': 1,   'unit': 's'},
    'Turbidity_UF':         {'address': 22, 'scale': 10,  'unit': 'NTU'},

    # Stage 4
    'AIT_401':              {'address': 23, 'scale': 10,  'unit': 'mg/L'},
    'AIT_402':              {'address': 24, 'scale': 1,   'unit': 'mV'},    # ORP post-dechlorination (fixed: was blank unit)
    'FIT_401':              {'address': 25, 'scale': 10,  'unit': 'm³/h'},
    'LIT_401':              {'address': 26, 'scale': 1,   'unit': 'L'},

    # Stage 5
    'AIT_501':              {'address': 27, 'scale': 1,   'unit': 'µS/cm'},
    'AIT_502':              {'address': 28, 'scale': 1,   'unit': 'mV'},
    'AIT_503':              {'address': 29, 'scale': 1,   'unit': 'ppb'},
    'AIT_504':              {'address': 30, 'scale': 100, 'unit': 'pH'},
    'FIT_501':              {'address': 31, 'scale': 10,  'unit': 'm³/h'},
    'FIT_502':              {'address': 32, 'scale': 10,  'unit': 'm³/h'},
    'FIT_503':              {'address': 33, 'scale': 10,  'unit': 'm³/h'},
    'FIT_504':              {'address': 34, 'scale': 10,  'unit': 'm³/h'},
    'PIT_501':              {'address': 35, 'scale': 10,  'unit': 'bar'},
    'PIT_502':              {'address': 36, 'scale': 10,  'unit': 'bar'},
    'PIT_503':              {'address': 37, 'scale': 10,  'unit': 'bar'},
    'RO_Runtime':           {'address': 38, 'scale': 1,   'unit': 's'},
    'RO_Fouling_Factor':    {'address': 39, 'scale': 1,   'unit': '%'},
    'RO_Last_Cleaning':     {'address': 40, 'scale': 1,   'unit': 's'},
    'TDS_Feed':             {'address': 41, 'scale': 1,   'unit': 'ppm'},
    'TDS_Permeate':         {'address': 42, 'scale': 1,   'unit': 'ppm'},

    # Stage 6
    'FIT_601':              {'address': 43, 'scale': 10,  'unit': 'm³/h'},

    # Environmental
    'Water_Temperature':    {'address': 44, 'scale': 10,  'unit': '°C'},
    'Ambient_Temperature':  {'address': 45, 'scale': 10,  'unit': '°C'},

    # Energy
    'Energy_P101':          {'address': 46, 'scale': 1,   'unit': 'kWh'},
    'Energy_P301':          {'address': 47, 'scale': 1,   'unit': 'kWh'},
    'Energy_P501':          {'address': 48, 'scale': 1,   'unit': 'kWh'},
    'Energy_Total':         {'address': 49, 'scale': 1,   'unit': 'kWh'},

    # Additional
    'Turbidity_Raw':        {'address': 50, 'scale': 10,  'unit': 'NTU'},
    'Chlorine_Residual':    {'address': 51, 'scale': 10,  'unit': 'mg/L'},
}

# Coils (pumps, valves, boolean states)
COILS = {
    # Pumps
    'P_101':                {'address': 0,  'type': 'pump'},
    'P_102':                {'address': 1,  'type': 'pump'},
    'P_201':                {'address': 2,  'type': 'pump'},
    'P_202':                {'address': 3,  'type': 'pump'},
    'P_203':                {'address': 4,  'type': 'pump'},  # Acid dosing
    'P_204':                {'address': 5,  'type': 'pump'},
    'P_205':                {'address': 6,  'type': 'pump'},  # Chlorine dosing
    'P_206':                {'address': 7,  'type': 'pump'},  # Coagulant dosing
    'P_301':                {'address': 8,  'type': 'pump'},
    'P_302':                {'address': 9,  'type': 'pump'},
    'P_401':                {'address': 10, 'type': 'pump'},
    'P_402':                {'address': 11, 'type': 'pump'},
    'P_403':                {'address': 12, 'type': 'pump'},  # Bisulfate dosing
    'P_404':                {'address': 13, 'type': 'pump'},
    # Bug fix: UV_401 is Coil 14, P_501 is Coil 15 (config had them off by 1 from Coil 14)
    'UV_401':               {'address': 14, 'type': 'device'},
    'P_501':                {'address': 15, 'type': 'pump'},
    'P_502':                {'address': 16, 'type': 'pump'},
    'P_601':                {'address': 17, 'type': 'pump'},
    'P_602':                {'address': 18, 'type': 'pump'},
    'P_603':                {'address': 19, 'type': 'pump'},

    # Process States
    'UF_Backwash_Active':   {'address': 20, 'type': 'state'},
    'RO_Cleaning_Active':   {'address': 21, 'type': 'state'},

    # Alarms
    'Chemical_Low_Alarm':   {'address': 22, 'type': 'alarm'},
    'High_Fouling_Alarm':   {'address': 23, 'type': 'alarm'},

    # System
    'Energy_Monitor_Enable':{'address': 24, 'type': 'config'},

    # NEW: coils added in robustness update (coils 25-27)
    'High_Level_Alarm':     {'address': 25, 'type': 'alarm'},
    'High_Pressure_Alarm':  {'address': 26, 'type': 'alarm'},
    'System_Run':           {'address': 27, 'type': 'state'},
}

# CSV Column Order (for data logger output)
CSV_COLUMNS = [
    'Timestamp',
    
    # Stage 1
    'FIT_101', 'LIT_101', 'MV_101', 'P_101', 'P_102',
    
    # Stage 2
    'AIT_201', 'AIT_202', 'AIT_203', 'Chlorine_Residual',  # Added Chlorine_Residual
    'FIT_201', 'MV_201',
    'P_201', 'P_202', 'P_203', 'P_204', 'P_205', 'P_206',
    'Acid_Tank_Level', 'Chlorine_Tank_Level', 'Coagulant_Tank_Level', 'Bisulfate_Tank_Level',
    
    # Stage 3
    'DPIT_301', 'FIT_301', 'LIT_301',
    'MV_301', 'MV_302', 'MV_303', 'MV_304',
    'P_301', 'P_302',
    'UF_Runtime', 'UF_Fouling_Factor', 'UF_Last_Backwash', 'UF_Backwash_Active',
    'Turbidity_UF',
    
    # Stage 4
    'AIT_401', 'AIT_402', 'FIT_401', 'LIT_401',
    'P_401', 'P_402', 'P_403', 'P_404', 'UV_401',
    
    # Stage 5
    'AIT_501', 'AIT_502', 'AIT_503', 'AIT_504',
    'FIT_501', 'FIT_502', 'FIT_503', 'FIT_504',
    'PIT_501', 'PIT_502', 'PIT_503',
    'P_501', 'P_502',
    'RO_Runtime', 'RO_Fouling_Factor', 'RO_Last_Cleaning', 'RO_Cleaning_Active',
    'TDS_Feed', 'TDS_Permeate',
    
    # Stage 6
    'FIT_601', 'P_601', 'P_602', 'P_603',
    
    # Environmental & Energy
    'Water_Temperature', 'Ambient_Temperature',
    'Energy_P101', 'Energy_P301', 'Energy_P501', 'Energy_Total',
    
    # Additional
    'Turbidity_Raw',

    # Alarms & System State
    'Chemical_Low_Alarm', 'High_Fouling_Alarm', 'Energy_Monitor_Enable',
    'High_Level_Alarm', 'High_Pressure_Alarm', 'System_Run',

    # Attack Labels
    'ATTACK_ID', 'ATTACK_NAME', 'MITRE_ID',
]

# Attack Scenarios
ATTACK_SCENARIOS = {
    # Temporal attacks (use TemporalAttackEngine)
    'ph_manipulation': {
        'id': 11,
        'name': 'pH Manipulation Attack',
        'mitre_id': 'T0836',
        'description': 'Gradual pH drift using acid pump manipulation',
        'temporal': True,
    },
    'tank_overflow': {
        'id': 8,
        'name': 'Tank Overflow Attack',
        'mitre_id': 'T0815',
        'description': 'Sigmoid tank fill with pump override',
        'temporal': True,
    },
    'chemical_depletion': {
        'id': 9,
        'name': 'Chemical Depletion Attack',
        'mitre_id': 'T0809',
        'description': 'Accelerated chemical consumption',
        'temporal': True,
    },
    'membrane_damage': {
        'id': 10,
        'name': 'Membrane Damage Attack',
        'mitre_id': 'T0816',
        'description': 'Exponential TMP rise via fouling',
        'temporal': True,
    },
    'valve_manipulation': {
        'id': 16,
        'name': 'Valve Manipulation Attack',
        'mitre_id': 'T0836',
        'description': 'Valve state changes with hydraulic effects',
        'temporal': True,
    },
    'slow_ramp': {
        'id': 12,
        'name': 'Slow Ramp Attack',
        'mitre_id': 'T0832',
        'description': 'Gradual parameter drift with noise',
        'temporal': True,
    },
    'single_point_attack': {
        'id': 18,
        'name': 'Single Point Injection',
        'mitre_id': 'T0836',
        'description': 'Inject malicious value into a single register or coil',
        'temporal': False,
        'parameters': {},
    },

    # Network attacks (use subprocess)
    'reconnaissance': {
        'id': 13,
        'name': 'Reconnaissance Scan',
        'mitre_id': 'T0840',
        'description': 'Network scanning and discovery',
        'temporal': False,
    },
    'dos_flood': {
        'id': 14,
        'name': 'Denial of Service',
        'mitre_id': 'T0814',
        'description': 'Modbus flooding attack',
        'temporal': False,
    },
    'replay': {
        'id': 15,
        'name': 'Replay Attack',
        'mitre_id': 'T0839',
        'description': 'Command replay injection',
        'temporal': False,
    },
}