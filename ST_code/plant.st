PROGRAM PLC_PRG
VAR
    (* ========== HOLDING REGISTERS (INT/WORD — written by MATLAB via Python) ========== *)
    (* Python writes these every 100 ms from MATLAB physics output.                       *)
    (* CODESYS reads them for control decisions; it NEVER computes them directly.          *)

    FIT_101 : INT := 0;
    LIT_101 : INT := 500;
    MV_101  : INT := 0;

    AIT_201 : INT := 500;
    AIT_202 : INT := 720;
    AIT_203 : INT := 400;
    FIT_201 : INT := 0;
    MV_201  : INT := 0;
    Acid_Tank_Level      : INT := 75;
    Chlorine_Tank_Level  : INT := 80;
    Coagulant_Tank_Level : INT := 80;
    Bisulfate_Tank_Level : INT := 85;

    DPIT_301        : INT := 5;
    FIT_301         : INT := 0;
    LIT_301         : INT := 800;
    MV_301          : INT := 0;
    MV_302          : INT := 0;
    MV_303          : INT := 0;
    MV_304          : INT := 0;
    UF_Runtime      : INT := 0;
    UF_Fouling_Factor   : INT := 0;
    UF_Last_Backwash    : INT := 0;
    Turbidity_UF    : INT := 0;

    AIT_401 : INT := 150;
    AIT_402 : INT := 200;
    FIT_401 : INT := 0;
    LIT_401 : INT := 500;

    AIT_501 : INT := 700;
    AIT_502 : INT := 400;
    AIT_503 : INT := 500;
    AIT_504 : INT := 10;
    FIT_501 : INT := 0;
    FIT_502 : INT := 0;
    FIT_503 : INT := 0;
    FIT_504 : INT := 0;
    PIT_501 : INT := 0;
    PIT_502 : INT := 0;
    PIT_503 : INT := 0;
    RO_Runtime      : INT := 0;
    RO_Fouling_Factor   : INT := 0;
    RO_Last_Cleaning    : INT := 0;
    TDS_Feed        : INT := 5000;
    TDS_Permeate    : INT := 50;

    FIT_601 : INT := 0;

    Water_Temperature   : INT := 250;
    Ambient_Temperature : INT := 250;
    Energy_P101 : INT := 0;
    Energy_P301 : INT := 0;
    Energy_P501 : INT := 0;
    Energy_Total : INT := 0;
    Turbidity_Raw    : INT := 1500;
    Chlorine_Residual : INT := 30;

    (* ========== COILS (BOOL — set by control logic below) ========== *)
    P_101 : BOOL := FALSE;
    P_102 : BOOL := FALSE;
    P_201 : BOOL := FALSE;
    P_202 : BOOL := FALSE;
    P_203 : BOOL := FALSE;
    P_204 : BOOL := FALSE;
    P_205 : BOOL := FALSE;
    P_206 : BOOL := FALSE;
    P_301 : BOOL := FALSE;
    P_302 : BOOL := FALSE;
    P_401 : BOOL := FALSE;
    P_402 : BOOL := FALSE;
    P_403 : BOOL := FALSE;
    P_404 : BOOL := FALSE;
    UV_401 : BOOL := FALSE;
    P_501 : BOOL := FALSE;
    P_502 : BOOL := FALSE;
    P_601 : BOOL := FALSE;
    P_602 : BOOL := FALSE;
    P_603 : BOOL := FALSE;

    UF_Backwash_Active  : BOOL := FALSE;
    RO_Cleaning_Active  : BOOL := FALSE;
    Chemical_Low_Alarm  : BOOL := FALSE;
    High_Fouling_Alarm  : BOOL := FALSE;
    Energy_Monitor_Enable : BOOL := TRUE;
    High_Level_Alarm    : BOOL := FALSE;
    High_Pressure_Alarm : BOOL := FALSE;
    System_Run          : BOOL := TRUE;
END_VAR

(* ================================================================ *)
(* STAGE 1 CONTROL — pump/valve decisions based on sensor registers  *)
(* Physics (LIT_101 dynamics) computed externally by MATLAB.        *)
(* ================================================================ *)

IF LIT_101 < 450 THEN
    MV_101 := 1;
ELSIF LIT_101 > 850 THEN
    MV_101 := 0;
END_IF;

IF LIT_101 > 200 AND LIT_301 < 800 THEN
    P_101 := TRUE;
    P_102 := (LIT_101 > 600);
ELSE
    P_101 := FALSE;
    P_102 := FALSE;
END_IF;

IF LIT_101 < 50 THEN
    P_101 := FALSE;
    P_102 := FALSE;
END_IF;

(* ================================================================ *)
(* STAGE 2 CONTROL — chemical dosing decisions                       *)
(* ================================================================ *)

IF P_101 OR P_102 THEN
    IF AIT_202 > 750 THEN
        P_203 := TRUE;
    ELSIF AIT_202 < 680 THEN
        P_203 := FALSE;
    END_IF;

    IF Chlorine_Residual < 20 THEN
        P_205 := TRUE;
    ELSIF Chlorine_Residual > 50 THEN
        P_205 := FALSE;
    END_IF;

    IF AIT_201 > 400 THEN
        P_206 := TRUE;
    ELSIF AIT_201 < 200 THEN
        P_206 := FALSE;
    END_IF;
ELSE
    P_203 := FALSE;
    P_205 := FALSE;
    P_206 := FALSE;
END_IF;

(* pH safety interlock *)
IF AIT_202 > 900 OR AIT_202 < 550 THEN
    P_101 := FALSE;
    P_102 := FALSE;
    P_301 := FALSE;
    P_401 := FALSE;
END_IF;

(* Chemical low alarms *)
IF Acid_Tank_Level < 15 OR Chlorine_Tank_Level < 15 OR Coagulant_Tank_Level < 15 THEN
    Chemical_Low_Alarm := TRUE;
ELSE
    Chemical_Low_Alarm := FALSE;
END_IF;

(* ================================================================ *)
(* STAGE 3 CONTROL — UF and backwash decisions                       *)
(* ================================================================ *)

IF LIT_301 > 200 AND LIT_401 < 800 THEN
    MV_301 := 1;
    MV_302 := 1;
    P_301  := TRUE;
ELSE
    MV_301 := 0;
    MV_302 := 0;
    P_301  := FALSE;
END_IF;

IF DPIT_301 > 55 OR UF_Last_Backwash > 500 THEN
    UF_Backwash_Active  := TRUE;
    P_301  := FALSE;
    P_602  := TRUE;
    MV_303 := 1;
    MV_304 := 1;
    High_Fouling_Alarm  := TRUE;
ELSE
    UF_Backwash_Active  := FALSE;
    P_602  := FALSE;
    MV_303 := 0;
    MV_304 := 0;
    High_Fouling_Alarm  := FALSE;
END_IF;

(* ================================================================ *)
(* STAGE 4 CONTROL — UV / dechlorination                             *)
(* ================================================================ *)

IF LIT_401 > 200 THEN
    P_401  := TRUE;
    UV_401 := TRUE;
    IF Chlorine_Residual > 30 THEN
        P_403 := TRUE;
    ELSE
        P_403 := FALSE;
    END_IF;
ELSE
    P_401  := FALSE;
    UV_401 := FALSE;
    P_403  := FALSE;
END_IF;

IF P_101 OR P_102 THEN
    MV_201 := 1;
ELSE
    MV_201 := 0;
END_IF;

(* ================================================================ *)
(* STAGE 5 CONTROL — RO high-pressure pump                           *)
(* ================================================================ *)

IF P_401 AND LIT_401 > 200 THEN
    P_501 := TRUE;
ELSE
    P_501 := FALSE;
END_IF;

IF RO_Fouling_Factor > 80 OR RO_Last_Cleaning > 1000 THEN
    RO_Cleaning_Active := TRUE;
    P_501 := FALSE;
    High_Fouling_Alarm := TRUE;
ELSE
    RO_Cleaning_Active := FALSE;
END_IF;

(* ================================================================ *)
(* STAGE 6 CONTROL — distribution                                    *)
(* ================================================================ *)

IF P_501 THEN
    P_601 := TRUE;
    P_603 := TRUE;
ELSE
    P_601 := FALSE;
    P_603 := FALSE;
END_IF;

(* ================================================================ *)
(* ALARM CONSOLIDATION                                               *)
(* ================================================================ *)

IF LIT_101 > 950 OR LIT_301 > 950 OR LIT_401 > 950 THEN
    High_Level_Alarm := TRUE;
ELSE
    High_Level_Alarm := FALSE;
END_IF;

IF PIT_501 > 200 THEN
    High_Pressure_Alarm := TRUE;
ELSE
    High_Pressure_Alarm := FALSE;
END_IF;

IF High_Pressure_Alarm THEN
    System_Run := FALSE;
ELSIF High_Level_Alarm THEN
    System_Run := FALSE;
ELSIF NOT High_Pressure_Alarm AND NOT High_Level_Alarm THEN
    System_Run := TRUE;
END_IF;
