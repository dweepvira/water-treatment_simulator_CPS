PROGRAM PLC_PRG
VAR
    (* ========== HOLDING REGISTERS (INT/WORD - 16-bit) ========== *)
    
    (* --- STAGE 1: Raw Water Intake --- *)
    (* Registers 0-2 *)
    FIT_101 : INT := 0;           (* Reg 0: Inflow meter (m³/h) *)
    LIT_101 : INT := 500;         (* Reg 1: Tank level (L) *)
    MV_101 : INT := 0;            
    
    (* --- STAGE 2: Chemical Dosing --- *)
    (* Registers 3-9 *)
    AIT_201 : INT := 500;         (* Reg 3: Conductivity NaCl (mg/L) *)
    AIT_202 : INT := 720;         (* Reg 4: pH x100 *)
    AIT_203 : INT := 400;         (* Reg 5: ORP NaOCl (mV) *)
    FIT_201 : INT := 0;           (* Reg 6: Flow control (m³/h) *)
    MV_201 : INT := 0;            (* Reg 7: Motorized valve *)
    Acid_Tank_Level : INT := 75;        (* Reg 8: HCl inventory (%) *)
    Chlorine_Tank_Level : INT := 80;    (* Reg 9: NaOCl inventory (%) *)
    
    (* Registers 10-11 *)
    Coagulant_Tank_Level : INT := 80;   (* Reg 10: Coagulant inventory (%) *)
    Bisulfate_Tank_Level : INT := 85;   (* Reg 11: NaHSO3 inventory (%) *)
    
    (* --- STAGE 3: Ultrafiltration --- *)
    (* Registers 12-20 *)
    DPIT_301 : INT := 5;          (* Reg 12: Differential pressure (mA) *)
    FIT_301 : INT := 0;           (* Reg 13: UF flow (m³/h) *)
    LIT_301 : INT := 800;         (* Reg 14: UF feed tank level (L) *)
    MV_301 : INT := 0;            (* Reg 15: Backwash valve *)
    MV_302 : INT := 0;            (* Reg 16: To dechlorination valve *)
    MV_303 : INT := 0;            (* Reg 17: Backwash drain valve *)
    MV_304 : INT := 0;            (* Reg 18: UF drain valve *)
    UF_Runtime : INT := 0;        (* Reg 19: Operating cycles *)
    UF_Fouling_Factor : INT := 0; (* Reg 20: Fouling % (0-100) *)
    
    (* Registers 21-22 *)
    UF_Last_Backwash : INT := 0;  (* Reg 21: Cycles since backwash *)
    Turbidity_UF : INT := 0;      (* Reg 22: Post-UF turbidity (NTU×10) *)
    
    (* --- STAGE 4: Dechlorination --- *)
    (* Registers 23-26 *)
    AIT_401 : INT := 150;         (* Reg 23: Hardness (mg/L) *)
    AIT_402 : INT := 200;         (* Reg 24: ORP (mV) *)
    FIT_401 : INT := 0;           (* Reg 25: UV flow control (m³/h) *)
    LIT_401 : INT := 500;         (* Reg 26: RO feed tank level (L) *)
    
    (* --- STAGE 5: Reverse Osmosis --- *)
    (* Registers 27-40 *)
    AIT_501 : INT := 700;         (* Reg 27: RO pH x100 *)
    AIT_502 : INT := 400;         (* Reg 28: RO feed ORP (mV) *)
    AIT_503 : INT := 500;         (* Reg 29: RO feed conductivity (mg/L) *)
    AIT_504 : INT := 10;          (* Reg 30: RO permeate conductivity (mg/L) *)
    FIT_501 : INT := 0;           (* Reg 31: RO inlet flow (m³/h) *)
    FIT_502 : INT := 0;           (* Reg 32: RO permeate flow (m³/h) *)
    FIT_503 : INT := 0;           (* Reg 33: RO reject flow (m³/h) *)
    FIT_504 : INT := 0;           (* Reg 34: RO recirculation flow (m³/h) *)
    PIT_501 : INT := 0;           (* Reg 35: RO feed pressure (bar×10) *)
    PIT_502 : INT := 0;           (* Reg 36: RO permeate pressure (bar×10) *)
    PIT_503 : INT := 0;           (* Reg 37: RO reject pressure (bar×10) *)
    RO_Runtime : INT := 0;        (* Reg 38: Operating cycles *)
    RO_Fouling_Factor : INT := 0; (* Reg 39: Fouling % (0-100) *)
    RO_Last_Cleaning : INT := 0;  (* Reg 40: Cycles since CIP *)
    
    (* Registers 41-42 *)
    TDS_Feed : INT := 5000;       (* Reg 41: RO feed TDS (mg/L) *)
    TDS_Permeate : INT := 50;     (* Reg 42: RO permeate TDS (mg/L) *)
    
    (* --- STAGE 6: Distribution --- *)
    (* Register 43 *)
    FIT_601 : INT := 0;           (* Reg 43: Backwash flow (m³/h) *)
    
    (* --- GLOBAL PARAMETERS --- *)
    (* Registers 44-52 *)
    Water_Temperature : INT := 250;      (* Reg 44: Process temp (°C×10) *)
    Ambient_Temperature : INT := 250;    (* Reg 45: Ambient temp (°C×10) *)
    Energy_P101 : INT := 0;              (* Reg 46: Stage 1 energy (kWh×10) *)
    Energy_P301 : INT := 0;              (* Reg 47: Stage 3 energy (kWh×10) *)
    Energy_P501 : INT := 0;              (* Reg 48: Stage 5 energy (kWh×10) *)
    Energy_Total : INT := 0;             (* Reg 49: Total energy (kWh×10) *)
    Turbidity_Raw : INT := 1500;         (* Reg 50: Raw turbidity (NTU×10) *)
    Chlorine_Residual : INT := 30;        (* Reg 51: Free chlorine residual (mg/L×10) *)
    
    (* Reserved for future expansion: Reg 51-99 *)
    
    (* ========== COILS (BOOL - Binary ON/OFF) ========== *)
    
    (* --- STAGE 1: Pumps --- *)
    (* Coils 0-1 *)
    P_101 : BOOL := FALSE;        (* Coil 0: Main pump *)
    P_102 : BOOL := FALSE;        (* Coil 1: Backup pump *)
    
    (* --- STAGE 2: Dosing Pumps --- *)
    (* Coils 2-7 *)
    P_201 : BOOL := FALSE;        (* Coil 2: NaCl dosing pump *)
    P_202 : BOOL := FALSE;        (* Coil 3: Backup NaCl pump *)
    P_203 : BOOL := FALSE;        (* Coil 4: HCl dosing pump *)
    P_204 : BOOL := FALSE;        (* Coil 5: Backup HCl pump *)
    P_205 : BOOL := FALSE;        (* Coil 6: NaOCl dosing pump *)
    P_206 : BOOL := FALSE;        (* Coil 7: Backup NaOCl pump *)
    
    (* --- STAGE 3: UF Pumps --- *)
    (* Coils 8-9 *)
    P_301 : BOOL := FALSE;        (* Coil 8: UF feed pump *)
    P_302 : BOOL := FALSE;        (* Coil 9: Backup UF pump *)
    
    (* --- STAGE 4: RO Feed & Dechlorination --- *)
    (* Coils 10-14 *)
    P_401 : BOOL := FALSE;        (* Coil 10: RO feed pump *)
    P_402 : BOOL := FALSE;        (* Coil 11: Backup RO feed pump *)
    P_403 : BOOL := FALSE;        (* Coil 12: Bisulfate dosing pump *)
    P_404 : BOOL := FALSE;        (* Coil 13: Backup bisulfate pump *)
    UV_401 : BOOL := FALSE;       (* Coil 14: UV dechlorinator *)
    
    (* --- STAGE 5: RO Pumps --- *)
    (* Coils 15-16 *)
    P_501 : BOOL := FALSE;        (* Coil 15: RO high pressure pump *)
    P_502 : BOOL := FALSE;        (* Coil 16: Backup RO pump *)
    
    (* --- STAGE 6: Distribution Pumps --- *)
    (* Coils 17-19 *)
    P_601 : BOOL := FALSE;        (* Coil 17: Permeate recirculation *)
    P_602 : BOOL := FALSE;        (* Coil 18: UF backwash pump *)
    P_603 : BOOL := FALSE;        (* Coil 19: Distribution pump *)
    
    (* --- STATUS & ALARMS --- *)
    (* Coils 20-27 *)
    UF_Backwash_Active : BOOL := FALSE;  (* Coil 20: Backwash in progress *)
    RO_Cleaning_Active : BOOL := FALSE;  (* Coil 21: RO CIP active *)
    Chemical_Low_Alarm : BOOL := FALSE;  (* Coil 22: Chemical tank low *)
    High_Fouling_Alarm : BOOL := FALSE;  (* Coil 23: Critical membrane fouling *)
    Energy_Monitor_Enable : BOOL := TRUE; (* Coil 24: Energy tracking enabled *)
    High_Level_Alarm : BOOL := FALSE;    (* Coil 25: Any tank above safe high limit *)
    High_Pressure_Alarm : BOOL := FALSE; (* Coil 26: RO feed pressure above safe limit *)
    System_Run : BOOL := TRUE;           (* Coil 27: Global run enable; FALSE = safe shutdown *)

    (* ========== INTERNAL VARIABLES (Not Mapped to Modbus) ========== *)
    Attack_Status : INT := 0;
    Noise_Seed : INT := 7;
    Temp_Factor : REAL := 1.0;
    (* SR-latch flags for chemical tank auto-refill simulation *)
    Acid_Refill_Active      : BOOL := FALSE;
    Chlorine_Refill_Active  : BOOL := FALSE;
    Coagulant_Refill_Active : BOOL := FALSE;
    Bisulfate_Refill_Active : BOOL := FALSE;

END_VAR


(* --- STAGE 1 CONTROL --- *)

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


(* --- STAGE 2 CONTROL --- *)

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


IF AIT_202 > 900 OR AIT_202 < 550 THEN
    P_101 := FALSE;
    P_102 := FALSE;
    P_301 := FALSE;
    P_401 := FALSE;
END_IF;


IF Acid_Tank_Level < 15 OR Chlorine_Tank_Level < 15 OR Coagulant_Tank_Level < 15 THEN
    Chemical_Low_Alarm := TRUE;
ELSE
    Chemical_Low_Alarm := FALSE;
END_IF;
(* CHEMICAL TANK REFILL - SR latch hysteresis                           *)
(* Bug fix: original nested IFs were redundant (inner < target was      *)
(*          always true when outer < 15 was true) and never reached      *)
(*          fill target. SR latch: SET on ≤15 %, RESET on ≥ fill target. *)

IF Acid_Tank_Level <= 15 THEN Acid_Refill_Active := TRUE; END_IF;
IF Acid_Tank_Level >= 80 THEN Acid_Refill_Active := FALSE; END_IF;
IF Acid_Refill_Active AND Acid_Tank_Level < 80 THEN
    Acid_Tank_Level := Acid_Tank_Level + 2;
END_IF;

IF Chlorine_Tank_Level <= 15 THEN Chlorine_Refill_Active := TRUE; END_IF;
IF Chlorine_Tank_Level >= 85 THEN Chlorine_Refill_Active := FALSE; END_IF;
IF Chlorine_Refill_Active AND Chlorine_Tank_Level < 85 THEN
    Chlorine_Tank_Level := Chlorine_Tank_Level + 2;
END_IF;

IF Coagulant_Tank_Level <= 15 THEN Coagulant_Refill_Active := TRUE; END_IF;
IF Coagulant_Tank_Level >= 75 THEN Coagulant_Refill_Active := FALSE; END_IF;
IF Coagulant_Refill_Active AND Coagulant_Tank_Level < 75 THEN
    Coagulant_Tank_Level := Coagulant_Tank_Level + 2;
END_IF;

IF Bisulfate_Tank_Level <= 15 THEN Bisulfate_Refill_Active := TRUE; END_IF;
IF Bisulfate_Tank_Level >= 70 THEN Bisulfate_Refill_Active := FALSE; END_IF;
IF Bisulfate_Refill_Active AND Bisulfate_Tank_Level < 70 THEN
    Bisulfate_Tank_Level := Bisulfate_Tank_Level + 2;
END_IF;


(* --- STAGE 3 CONTROL --- *)

IF LIT_301 > 200 AND LIT_401 < 800 THEN
    MV_301 := 1;
    MV_302 := 1;   (* Open to-dechlorination valve while UF running *)
    P_301 := TRUE;
ELSE
    MV_301 := 0;
    MV_302 := 0;   (* Close feed-to-dechlorination path when UF stopped *)
    P_301 := FALSE;
END_IF;

IF DPIT_301 > 55 OR UF_Last_Backwash > 500 THEN
    UF_Backwash_Active := TRUE;
    P_301 := FALSE;
    P_602 := TRUE;   (* Engage backwash pump *)
    MV_303 := 1;     (* Open backwash drain valve *)
    MV_304 := 1;     (* Open UF drain valve *)
    High_Fouling_Alarm := TRUE;
ELSE
    (* Bug fix: on transition from backwash → normal, reset counters     *)
    (* Previously UF_Last_Backwash was never reset, keeping alarm latched *)
    IF UF_Backwash_Active THEN
        UF_Last_Backwash := 0;
        IF UF_Fouling_Factor >= 10 THEN
            UF_Fouling_Factor := UF_Fouling_Factor - 10;
        ELSE
            UF_Fouling_Factor := 0;
        END_IF;
    END_IF;
    UF_Backwash_Active := FALSE;
    P_602 := FALSE;
    MV_303 := 0;
    MV_304 := 0;
    High_Fouling_Alarm := FALSE;
END_IF;


(* --- STAGE 4 CONTROL --- *)

IF LIT_401 > 200 THEN
    P_401 := TRUE;
    UV_401 := TRUE;

    IF Chlorine_Residual > 30 THEN
        P_403 := TRUE;
    ELSE
        P_403 := FALSE;
    END_IF;

ELSE
    P_401 := FALSE;
    UV_401 := FALSE;
    P_403 := FALSE;
END_IF;
(* Bug fix: AIT_402 is ORP in mV (200-370 mV range), not a pH-like 7-8 value *)
AIT_402 := 200 + (Noise_Seed * 8);   (* ORP post-dechlorination: 200-370 mV *)

(* MV_201: motorized valve mirrors Stage 1 pump state *)
IF P_101 OR P_102 THEN
    MV_201 := 1;
ELSE
    MV_201 := 0;
END_IF;


(* --- STAGE 5 CONTROL --- *)

(* Bug fix: threshold aligned with P_401 enable level (200 L) to prevent  *)
(* P_501 running while P_401 is off between 100-200 L (missing suction head) *)
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
    (* Bug fix: on CIP completion, reset cleaning timer and reduce fouling *)
    (* Previously RO_Last_Cleaning was never reset after CIP finished      *)
    IF RO_Cleaning_Active THEN
        RO_Last_Cleaning := 0;
        IF RO_Fouling_Factor >= 20 THEN
            RO_Fouling_Factor := RO_Fouling_Factor - 20;
        ELSE
            RO_Fouling_Factor := 0;
        END_IF;
    END_IF;
    RO_Cleaning_Active := FALSE;
END_IF;


(* --- STAGE 6 CONTROL --- *)

IF P_501 THEN
    P_601 := TRUE;
    P_603 := TRUE;
ELSE
    P_601 := FALSE;
    P_603 := FALSE;
END_IF;


(* ================================================================= *)
(* PHYSICS SIMULATION                                                *)
(* ================================================================= *)

Noise_Seed := (Noise_Seed * 37 + 13) MOD 23;

IF Water_Temperature < Ambient_Temperature THEN
    Water_Temperature := Water_Temperature + 1;
ELSIF Water_Temperature > Ambient_Temperature THEN
    Water_Temperature := Water_Temperature - 1;
END_IF;

Temp_Factor := 1.0 + INT_TO_REAL(Water_Temperature - 250) / 1000.0;


(* ================= STAGE 1 PHYSICS ================= *)

IF MV_101 = 1 THEN
    FIT_101 := 5 + (Noise_Seed MOD 2);
ELSE
    FIT_101 := 1;
END_IF;


IF P_101 OR P_102 THEN

    IF LIT_101 > 600 THEN
        FIT_201 := 6 + (Noise_Seed MOD 2);
    ELSIF LIT_101 > 400 THEN
        FIT_201 := 5;
    ELSIF LIT_101 > 200 THEN
        FIT_201 := 4;
    ELSE
        FIT_201 := 3;
    END_IF;

    IF P_102 THEN
        FIT_201 := FIT_201 + 2;
    END_IF;

ELSE
    FIT_201 := 1;
END_IF;


(* MASS BALANCE INVARIANT *)
LIT_101 := LIT_101 + FIT_101 - FIT_201;

IF LIT_101 < 0 THEN
    LIT_101 := 0;
END_IF;

IF LIT_101 > 1000 THEN
    LIT_101 := 1000;
END_IF;


IF Energy_Monitor_Enable AND (P_101 OR P_102) THEN
    Energy_P101 := Energy_P101 + FIT_201;
    (* Overflow guard: saturate at 30000 to prevent INT rollover at 32767 *)
    IF Energy_P101 > 30000 THEN Energy_P101 := 30000; END_IF;
END_IF;


(* ================= STAGE 2 PHYSICS ================= *)

AIT_201 := 280 + (Noise_Seed * 25);


IF P_203 THEN

    IF AIT_202 > 600 THEN
        AIT_202 := AIT_202 - 2;
    END_IF;

    IF Acid_Tank_Level > 0 THEN
        Acid_Tank_Level := Acid_Tank_Level - (1 + (Noise_Seed MOD 2));
    END_IF;

ELSE

    IF AIT_202 < 850 THEN
        AIT_202 := AIT_202 + 1;
    END_IF;

END_IF;


IF FIT_201 > 0 THEN

    IF AIT_202 < 720 THEN
        AIT_202 := AIT_202 + 1;
    ELSIF AIT_202 > 720 THEN
        AIT_202 := AIT_202 - 1;
    END_IF;

END_IF;

(* pH baseline micro-dynamics (unconditional every scan)
   Prevents deterministic lock at exactly 7.20 when no pH attack is active.
   Keeps realistic small variation (~±0.01) while preserving control bounds. *)
AIT_202 := AIT_202 + ((Noise_Seed MOD 3) - 1);
IF AIT_202 < 550 THEN
    AIT_202 := 550;
END_IF;
IF AIT_202 > 900 THEN
    AIT_202 := 900;
END_IF;


(* CHLORINE RESIDUAL *)

IF P_205 THEN

    IF Chlorine_Residual < 80 THEN
        Chlorine_Residual := Chlorine_Residual + 3;
    END_IF;

    IF Chlorine_Tank_Level > 0 THEN
        Chlorine_Tank_Level := Chlorine_Tank_Level - 1;
    END_IF;

ELSE

    IF Chlorine_Residual > 15 THEN
        Chlorine_Residual := Chlorine_Residual - 1;
    END_IF;

END_IF;


IF P_206 THEN
    IF Coagulant_Tank_Level > 0 THEN
        Coagulant_Tank_Level := Coagulant_Tank_Level - (1 + (Noise_Seed MOD 2));
    END_IF;
END_IF;

(* Bug fix: Bisulfate (NaHSO3) is dosed by the bisulfate pump P_403,   *)
(* not by the HCl pump P_203. Previous code silently depleted the wrong  *)
(* chemical, allowing Bisulfate_Tank_Level to stay artificially full.    *)
IF P_403 THEN
    IF Bisulfate_Tank_Level > 0 THEN
        Bisulfate_Tank_Level := Bisulfate_Tank_Level - (1 + (Noise_Seed MOD 2));
    END_IF;
END_IF;

(* Bug fix: ORP NaOCl range is 400-620 mV. Previous formula produced    *)
(* 1000-2760 mV - physically impossible and caused dataset range violations *)
AIT_203 := 400 + (Noise_Seed * 10);  (* ORP NaOCl: 400-620 mV realistic range *)


(* ================= STAGE 3 PHYSICS ================= *)

IF P_301 THEN

    UF_Runtime := UF_Runtime + 1;
    UF_Last_Backwash := UF_Last_Backwash + 1;
    (* Overflow guard: saturate cycle counters to prevent INT rollover *)
    IF UF_Runtime > 30000 THEN UF_Runtime := 30000; END_IF;
    IF UF_Last_Backwash > 30000 THEN UF_Last_Backwash := 30000; END_IF;

    IF UF_Runtime MOD 150 = 0 AND UF_Fouling_Factor < 100 THEN
        UF_Fouling_Factor := UF_Fouling_Factor + 1;
    END_IF;

    IF LIT_301 > 700 THEN
        FIT_301 := 5 - (UF_Fouling_Factor / 20);
    ELSIF LIT_301 > 500 THEN
        FIT_301 := 4 - (UF_Fouling_Factor / 20);
    ELSE
        FIT_301 := 3 - (UF_Fouling_Factor / 20);
    END_IF;

    IF FIT_301 < 2 THEN
        FIT_301 := 2;
    END_IF;

    DPIT_301 := 25 + UF_Fouling_Factor;
    (* UF FILTRATE TURBIDITY: proportional to feed turbidity / UF removal ratio *)
    Turbidity_UF := Turbidity_Raw / 20 + (Noise_Seed MOD 2);

ELSE

    FIT_301 := 2;
    DPIT_301 := 10;
    (* Bug fix: prevent stale Turbidity_UF reading when UF is offline *)
    IF Turbidity_UF > 2 THEN
        Turbidity_UF := Turbidity_UF - 1;
    END_IF;

END_IF;




(* MASS BALANCE INVARIANT *)
LIT_301 := LIT_301 + FIT_201 - FIT_301;

IF LIT_301 < 0 THEN
    LIT_301 := 0;
END_IF;

IF LIT_301 > 1000 THEN
    LIT_301 := 1000;
END_IF;

IF Energy_Monitor_Enable AND P_301 THEN
    Energy_P301 := Energy_P301 + FIT_301;
    IF Energy_P301 > 30000 THEN Energy_P301 := 30000; END_IF;
END_IF;


(* ================= STAGE 4 PHYSICS ================= *)

IF P_401 THEN

    IF LIT_401 > 700 THEN
        FIT_401 := 6;
    ELSIF LIT_401 > 500 THEN
        FIT_401 := 5;
    ELSIF LIT_401 > 300 THEN
        FIT_401 := 4;
    ELSE
        FIT_401 := 3;
    END_IF;

ELSE
    FIT_401 := 1;
END_IF;


(* MASS BALANCE INVARIANT *)
LIT_401 := LIT_401 + FIT_301 - FIT_401;

IF LIT_401 < 0 THEN
    LIT_401 := 0;
END_IF;

IF LIT_401 > 1000 THEN
    LIT_401 := 1000;
END_IF;


AIT_401 := Chlorine_Residual + (Noise_Seed MOD 3);
IF AIT_401 < 10 THEN
    AIT_401 := 10;
END_IF;


(* ================= STAGE 5 PHYSICS ================= *)

IF P_501 THEN

    RO_Runtime := RO_Runtime + 1;
    RO_Last_Cleaning := RO_Last_Cleaning + 1;
    (* Overflow guard: saturate cycle counters to prevent INT rollover *)
    IF RO_Runtime > 30000 THEN RO_Runtime := 30000; END_IF;
    IF RO_Last_Cleaning > 30000 THEN RO_Last_Cleaning := 30000; END_IF;

    IF RO_Runtime MOD 200 = 0 AND RO_Fouling_Factor < 100 THEN
        RO_Fouling_Factor := RO_Fouling_Factor + 1;
    END_IF;

    IF LIT_401 > 600 THEN
        PIT_501 := 125 + RO_Fouling_Factor;
    ELSIF LIT_401 > 400 THEN
        PIT_501 := 120 + RO_Fouling_Factor;
    ELSE
        PIT_501 := 115 + RO_Fouling_Factor;
    END_IF;

    FIT_501 := 8 + (Noise_Seed MOD 2);
    FIT_502 := 4 - (RO_Fouling_Factor / 25);
    FIT_503 := 2;
    FIT_504 := 2;

    IF FIT_502 < 2 THEN
        FIT_502 := 2;
    END_IF;

    (* FLOW CONSERVATION *)
    FIT_501 := FIT_502 + FIT_503 + FIT_504;
	
    IF Energy_Monitor_Enable AND P_501 THEN
        Energy_P501 := Energy_P501 + FIT_501;
        IF Energy_P501 > 30000 THEN Energy_P501 := 30000; END_IF;
    END_IF;

    PIT_502 := 5 + (Noise_Seed MOD 2);
    PIT_503 := PIT_501 - 10;

    TDS_Feed := 6000 + (Noise_Seed * 100);
    TDS_Permeate := TDS_Feed * 15 / 1000;

    AIT_501 := TDS_Permeate + (Noise_Seed MOD 5);
    AIT_502 := 650 + (Noise_Seed * 10);
    AIT_503 := 75 + (Noise_Seed MOD 10);
    AIT_504 := 12 + (Noise_Seed MOD 3);

ELSE

    PIT_501 := 90;
    FIT_501 := 1;
    FIT_502 := 1;
    FIT_503 := 1;
    FIT_504 := 1;

END_IF;


(* ================= STAGE 6 PHYSICS ================= *)

IF P_603 THEN
    FIT_601 := FIT_502 + (Noise_Seed MOD 2);
ELSE
    FIT_601 := 1;
END_IF;


IF Energy_Monitor_Enable THEN
    Energy_Total := Energy_P101 + Energy_P301 + Energy_P501;
    IF Energy_Total > 30000 THEN Energy_Total := 30000; END_IF;
END_IF;


(* ================================================================= *)
(* ALARM CONSOLIDATION & SYSTEM INTEGRITY                            *)
(* ================================================================= *)

(* Bug fix: Turbidity_Raw was erroneously assigned AIT_201 (conductivity). *)
(* Raw turbidity is a function of intake flow turbulence, not conductivity. *)
IF MV_101 = 1 THEN
    Turbidity_Raw := 1500 + (Noise_Seed * 30);  (* NTU×10: ~150-810 during intake *)
ELSE
    Turbidity_Raw := 800 + (Noise_Seed * 10);   (* NTU×10: ~80-300 at rest *)
END_IF;

(* High-level alarm: any process tank above 950 L (95%) *)
IF LIT_101 > 950 OR LIT_301 > 950 OR LIT_401 > 950 THEN
    High_Level_Alarm := TRUE;
ELSE
    High_Level_Alarm := FALSE;
END_IF;

(* High-pressure alarm: RO feed pressure above 200 bar×10 (200 = 20 bar) *)
IF PIT_501 > 200 THEN
    High_Pressure_Alarm := TRUE;
ELSE
    High_Pressure_Alarm := FALSE;
END_IF;

(* System_Run: global inhibit on critical alarms *)
(* Keeps System_Run TRUE during normal chemical/fouling alarms,          *)
(* but trips to FALSE only on overpressure or critical high-level events. *)
IF High_Pressure_Alarm THEN
    System_Run := FALSE;
ELSIF High_Level_Alarm THEN
    System_Run := FALSE;
ELSIF NOT High_Pressure_Alarm AND NOT High_Level_Alarm THEN
    System_Run := TRUE;
END_IF;