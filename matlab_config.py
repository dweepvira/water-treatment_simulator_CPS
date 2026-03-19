"""
config/matlab_config.py
========================
Configuration for the MATLAB physics bridge.
"""

MATLAB_CONFIG = {
    # UDP server address (where swat_physics_server.m is listening)
    'host': '127.0.0.1',   # localhost if MATLAB and Python on same machine
    'port': 9501,
    'timeout_s': 0.5,       # max seconds to wait for MATLAB response

    # Path to MATLAB .m files (for addpath in startup script)
    'matlab_path': 'matlab',

    # Physics timestep — must match physics_client.py DT
    'dt': 0.1,              # seconds (10 Hz)

    # Communication mode: 'udp' or 'engine_api'
    'mode': 'udp',
}

# Registers that MATLAB computes and Python writes to CODESYS.
# These are READ-ONLY from CODESYS's perspective after the bridge is running.
MATLAB_OWNED_REGISTERS = [
    # Stage 1
    'FIT_101', 'LIT_101', 'FIT_201',
    # Stage 2
    'AIT_201', 'AIT_202', 'AIT_203',
    'Acid_Tank_Level', 'Chlorine_Tank_Level',
    'Coagulant_Tank_Level', 'Bisulfate_Tank_Level',
    'Chlorine_Residual',
    # Stage 3
    'DPIT_301', 'FIT_301', 'LIT_301',
    'UF_Fouling_Factor', 'UF_Runtime', 'UF_Last_Backwash', 'Turbidity_UF',
    # Stage 4
    'AIT_401', 'AIT_402', 'FIT_401', 'LIT_401',
    # Stage 5
    'AIT_501', 'AIT_502', 'AIT_503', 'AIT_504',
    'FIT_501', 'FIT_502', 'FIT_503', 'FIT_504',
    'PIT_501', 'PIT_502', 'PIT_503',
    'RO_Runtime', 'RO_Fouling_Factor', 'RO_Last_Cleaning',
    'TDS_Feed', 'TDS_Permeate',
    # Stage 6 + global
    'FIT_601',
    'Water_Temperature', 'Ambient_Temperature',
    'Energy_P101', 'Energy_P301', 'Energy_P501', 'Energy_Total',
    'Turbidity_Raw',
]

# Coils that the bridge reads from CODESYS and sends to MATLAB.
# CODESYS control logic owns these — bridge must never write them.
CODESYS_OWNED_COILS = [
    'P_101', 'P_102',
    'P_201', 'P_202', 'P_203', 'P_204', 'P_205', 'P_206',
    'P_301', 'P_302',
    'P_401', 'P_402', 'P_403', 'P_404',
    'UV_401',
    'P_501', 'P_502',
    'P_601', 'P_602', 'P_603',
    'UF_Backwash_Active', 'RO_Cleaning_Active',
]
