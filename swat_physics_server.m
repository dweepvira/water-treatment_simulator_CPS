%% swat_physics_server.m
% TCP server — receives actuator JSON, returns sensor JSON every timestep.
%
% Run from MATLAB command window:
%   swat_physics_server()
%
% Protocol (newline-delimited JSON over TCP):
%   Client → Server : JSON string + newline
%   Server → Client : JSON string + newline
%
% Port : 9501 (configurable via PHYSICS_TCP_PORT env var)
% Requires R2021a+ (tcpserver).

function swat_physics_server()

    %% ── Configuration ────────────────────────────────────────────────────
    portEnv = getenv('PHYSICS_TCP_PORT');
    if isempty(portEnv)
        PORT = 9501;
    else
        PORT = str2double(portEnv);
        if isnan(PORT); PORT = 9501; end
    end
    DT = 0.1;

    fprintf('[SWaT Physics Server] Starting TCP server on port %d ...\n', PORT);

    % tcpserver listens for one client at a time.
    % ConnectionChangedFcn fires when client connects/disconnects.
    srv = tcpserver('0.0.0.0', PORT, ...
        'ConnectionChangedFcn', @(s,~) onConnect(s));
    srv.UserData.connected = false;
    fprintf('[SWaT Physics Server] Ready. Waiting for client connection.\n');

    cleanup = onCleanup(@() delete(srv)); %#ok<NASGU>

    %% ── Initialise physics state ─────────────────────────────────────────
    s = init_state();
    buf = '';   % line buffer for incoming data

    %% ── Main loop ────────────────────────────────────────────────────────
    while true
        % Wait for a connected client
        if ~srv.Connected
            pause(0.05);
            buf = '';
            continue;
        end

        % Read available bytes
        if srv.NumBytesAvailable == 0
            pause(0.005);
            continue;
        end

        raw = read(srv, srv.NumBytesAvailable, 'char');
        buf = [buf, raw]; %#ok<AGROW>

        % Process all complete lines (newline-delimited JSON)
        while true
            nl = strfind(buf, newline);
            if isempty(nl); break; end

            line = strtrim(buf(1:nl(1)-1));
            buf  = buf(nl(1)+1:end);

            if isempty(line); continue; end

            fprintf('Recv %d bytes\n', numel(line));

            try
                act    = jsondecode(line);
                [s, r] = step_physics(s, act, DT);
                outTxt = [jsonencode(r), newline];
                write(srv, uint8(outTxt), 'uint8');
            catch ME
                fprintf('Error: %s\n', ME.message);
                write(srv, uint8(['{}\n']), 'uint8');
            end
        end
    end
end

function onConnect(srv)
    if srv.Connected
        fprintf('[SWaT Physics Server] Client connected.\n');
    else
        fprintf('[SWaT Physics Server] Client disconnected.\n');
    end
end


%% =========================================================================
%%  Physics initialisation
%% =========================================================================
function s = init_state()
    s.LIT_101  = 500;   s.FIT_101  = 0;   s.FIT_201  = 0;
    s.pH                   = 7.20;
    s.AIT_201              = 450;
    s.AIT_203              = 410;
    s.Chlorine_Residual    = 3.0;
    s.Acid_Tank_Level      = 75;
    s.Chlorine_Tank_Level  = 80;
    s.Coagulant_Tank_Level = 80;
    s.Bisulfate_Tank_Level = 85;
    s.LIT_301      = 800;   s.FIT_301  = 0;
    s.DPIT_301     = 25;
    s.UF_Fouling   = 0;     s.UF_Runtime = 0;
    s.UF_LastBW    = 0;     s.Turbidity_UF = 0;
    s.LIT_401      = 500;   s.FIT_401  = 0;
    s.AIT_402      = 200;   s.AIT_401_val = 30;
    s.PIT_501 = 90;  s.PIT_502 = 5;  s.PIT_503 = 80;
    s.FIT_501 = 0;   s.FIT_502 = 0;  s.FIT_503 = 0;  s.FIT_504 = 0;
    s.RO_Fouling   = 0;   s.RO_Runtime   = 0;   s.RO_LastClean = 0;
    s.TDS_Feed     = 5000; s.TDS_Permeate = 50;
    s.FIT_601      = 0;
    s.Water_Temp   = 25.0; s.Ambient_Temp = 25.0;
    s.Turbidity_Raw = 150;
    s.Energy_P101  = 0;   s.Energy_P301  = 0;   s.Energy_P501  = 0;
    s.noise_seed   = 7;
end


%% =========================================================================
%%  Single physics timestep
%% =========================================================================
function [s, r] = step_physics(s, act, dt)

    s.noise_seed = mod(s.noise_seed * 37 + 13, 23);
    ns = s.noise_seed;

    %% Stage 1
    MV_101 = get_field(act, 'MV_101', 0);
    P_101  = get_field(act, 'P_101',  false);
    P_102  = get_field(act, 'P_102',  false);

    Q_in = (MV_101 > 0) * (5 + mod(ns,2)) / 3600 * 1000 + ...
           (MV_101 == 0) * 1 / 3600 * 1000;

    if P_101 || P_102
        base  = 4 + double(s.LIT_101>400) + double(s.LIT_101>600);
        if P_102; base = base + 2; end
        Q_out = base / 3600 * 1000;
    else
        Q_out = 1 / 3600 * 1000;
    end

    s.LIT_101 = clamp(s.LIT_101 + (Q_in - Q_out)*dt, 0, 1000);
    s.FIT_101 = Q_in  * 3600 / 1000;
    s.FIT_201 = Q_out * 3600 / 1000;
    if P_101 || P_102
        s.Energy_P101 = min(s.Energy_P101 + s.FIT_201*dt, 30000);
    end

    %% Stage 2
    P_203 = get_field(act, 'P_203', false);
    P_205 = get_field(act, 'P_205', false);
    P_206 = get_field(act, 'P_206', false);
    P_403 = get_field(act, 'P_403', false);

    if P_203
        pH_target = 6.80;
        s.Acid_Tank_Level = max(0, s.Acid_Tank_Level - 0.5*dt);
    else
        pH_target = 8.50;
    end
    s.pH = pH_target + (s.pH - pH_target)*exp(-dt/40) + (mod(ns,3)-1)*0.01;
    s.pH = clamp(s.pH, 5.5, 9.0);

    if P_206
        s.AIT_201 = max(100, s.AIT_201 - 2*dt);
        s.Coagulant_Tank_Level = max(0, s.Coagulant_Tank_Level - (1+mod(ns,2))*dt);
    else
        s.AIT_201 = min(1000, s.AIT_201 + dt);
    end

    if P_205
        s.Chlorine_Residual   = min(8.0, s.Chlorine_Residual + 0.3*dt);
        s.Chlorine_Tank_Level = max(0, s.Chlorine_Tank_Level - dt);
    else
        s.Chlorine_Residual = max(1.5, s.Chlorine_Residual - 0.1*dt);
    end
    s.AIT_203 = 400 + ns*10;

    if P_403
        s.Bisulfate_Tank_Level = max(0, s.Bisulfate_Tank_Level - (1+mod(ns,2))*dt);
    end

    s.Acid_Tank_Level      = tank_refill(s.Acid_Tank_Level,      15, 80, 2*dt);
    s.Chlorine_Tank_Level  = tank_refill(s.Chlorine_Tank_Level,  15, 85, 2*dt);
    s.Coagulant_Tank_Level = tank_refill(s.Coagulant_Tank_Level, 15, 75, 2*dt);
    s.Bisulfate_Tank_Level = tank_refill(s.Bisulfate_Tank_Level, 15, 85, 2*dt);

    %% Stage 3
    P_301 = get_field(act, 'P_301', false);
    UF_BW = get_field(act, 'UF_Backwash_Active', false);

    if P_301 && ~UF_BW
        s.UF_Runtime = min(30000, s.UF_Runtime+1);
        s.UF_LastBW  = min(30000, s.UF_LastBW+1);
        fr = 0.001*(1 + s.AIT_201/1000);
        s.UF_Fouling = min(1.0, s.UF_Fouling + fr*dt);
        s.DPIT_301   = 25 + s.UF_Fouling*100;
        if     s.LIT_301>700; Q_uf = 5 - s.UF_Fouling*3;
        elseif s.LIT_301>500; Q_uf = 4 - s.UF_Fouling*2;
        else;                 Q_uf = 3 - s.UF_Fouling*2;
        end
        s.FIT_301      = max(2, Q_uf);
        s.Turbidity_UF = s.Turbidity_Raw/20 + mod(ns,2);
    elseif UF_BW
        s.UF_LastBW  = 0;
        s.UF_Fouling = max(0, s.UF_Fouling - 0.1*dt);
        s.DPIT_301   = 10;  s.FIT_301 = 2;
        if s.Turbidity_UF > 2; s.Turbidity_UF = s.Turbidity_UF - dt; end
    else
        s.FIT_301 = 2;  s.DPIT_301 = 10;
    end

    s.LIT_301 = clamp(s.LIT_301 + (s.FIT_201/3600*1000 - s.FIT_301/3600*1000)*dt, 0, 1000);
    if P_301; s.Energy_P301 = min(30000, s.Energy_P301 + s.FIT_301*dt); end

    %% Stage 4
    P_401 = get_field(act, 'P_401', false);
    if P_401
        if     s.LIT_401>700; Q_dc=6;
        elseif s.LIT_401>500; Q_dc=5;
        elseif s.LIT_401>300; Q_dc=4;
        else;                 Q_dc=3;
        end
    else; Q_dc=1;
    end
    s.FIT_401 = Q_dc;
    s.LIT_401 = clamp(s.LIT_401 + (s.FIT_301/3600*1000 - Q_dc/3600*1000)*dt, 0, 1000);
    s.AIT_402     = 200 + ns*8;
    s.AIT_401_val = s.Chlorine_Residual*10 + mod(ns,3);

    %% Stage 5
    P_501 = get_field(act, 'P_501', false);
    if P_501 && P_401 && s.LIT_401>200
        s.RO_Runtime   = min(30000, s.RO_Runtime+1);
        s.RO_LastClean = min(30000, s.RO_LastClean+1);
        s.RO_Fouling   = min(1.0, s.RO_Fouling + 0.0005*dt);
        base_p = 120 + s.RO_Fouling*80;
        if s.LIT_401>600; base_p=base_p+5; elseif s.LIT_401<400; base_p=base_p-5; end
        s.PIT_501 = base_p;
        s.FIT_502 = max(2, 4 - s.RO_Fouling*2);
        s.FIT_503 = 2;  s.FIT_504 = 2;
        s.FIT_501 = s.FIT_502 + s.FIT_503 + s.FIT_504;
        s.PIT_502 = 5 + mod(ns,2);
        s.PIT_503 = s.PIT_501 - 10;
        s.TDS_Feed     = 6000 + ns*100;
        s.TDS_Permeate = round(s.TDS_Feed*15/1000);
        s.Energy_P501  = min(30000, s.Energy_P501 + s.FIT_501*dt);
    else
        s.PIT_501=90; s.PIT_502=5; s.PIT_503=80;
        s.FIT_501=1;  s.FIT_502=1; s.FIT_503=1; s.FIT_504=1;
    end
    if get_field(act,'RO_Cleaning_Active',false)
        s.RO_LastClean = 0;
        s.RO_Fouling   = max(0, s.RO_Fouling - 0.02*dt);
    end

    %% Stage 6
    P_603 = get_field(act, 'P_603', false);
    s.FIT_601 = P_603*(s.FIT_502+mod(ns,2)) + (~P_603)*1;

    %% Global
    s.Turbidity_Raw = (MV_101>0)*(1500+ns*30) + (MV_101==0)*(800+ns*10);
    s.Water_Temp    = s.Water_Temp + sign(s.Ambient_Temp-s.Water_Temp)*0.1*dt;

    %% Register map
    r = struct();
    r.FIT_101 = round(s.FIT_101*10);  r.LIT_101 = round(s.LIT_101);
    r.FIT_201 = round(s.FIT_201*10);
    r.AIT_201 = round(s.AIT_201);     r.AIT_202 = round(s.pH*100);
    r.AIT_203 = round(s.AIT_203);
    r.Acid_Tank_Level      = round(s.Acid_Tank_Level);
    r.Chlorine_Tank_Level  = round(s.Chlorine_Tank_Level);
    r.Coagulant_Tank_Level = round(s.Coagulant_Tank_Level);
    r.Bisulfate_Tank_Level = round(s.Bisulfate_Tank_Level);
    r.Chlorine_Residual    = round(s.Chlorine_Residual*10);
    r.DPIT_301         = round(s.DPIT_301*10);
    r.FIT_301          = round(s.FIT_301*10);  r.LIT_301 = round(s.LIT_301);
    r.UF_Fouling_Factor = round(s.UF_Fouling*100);
    r.UF_Runtime       = s.UF_Runtime;
    r.UF_Last_Backwash = s.UF_LastBW;
    r.Turbidity_UF     = round(s.Turbidity_UF*10);
    r.AIT_401 = round(s.AIT_401_val); r.AIT_402 = round(s.AIT_402);
    r.FIT_401 = round(s.FIT_401*10);  r.LIT_401 = round(s.LIT_401);
    r.AIT_501 = round(s.TDS_Permeate);
    r.AIT_502 = 650+ns*10;  r.AIT_503 = 75+mod(ns,10);  r.AIT_504 = 12+mod(ns,3);
    r.FIT_501 = round(s.FIT_501*10);  r.FIT_502 = round(s.FIT_502*10);
    r.FIT_503 = round(s.FIT_503*10);  r.FIT_504 = round(s.FIT_504*10);
    r.PIT_501 = round(s.PIT_501*10);  r.PIT_502 = round(s.PIT_502*10);
    r.PIT_503 = round(s.PIT_503*10);
    r.RO_Runtime        = s.RO_Runtime;
    r.RO_Fouling_Factor = round(s.RO_Fouling*100);
    r.RO_Last_Cleaning  = s.RO_LastClean;
    r.TDS_Feed          = s.TDS_Feed;  r.TDS_Permeate = s.TDS_Permeate;
    r.FIT_601             = round(s.FIT_601*10);
    r.Water_Temperature   = round(s.Water_Temp*10);
    r.Ambient_Temperature = round(s.Ambient_Temp*10);
    r.Turbidity_Raw       = round(s.Turbidity_Raw);
    r.Energy_P101  = round(s.Energy_P101);
    r.Energy_P301  = round(s.Energy_P301);
    r.Energy_P501  = round(s.Energy_P501);
    r.Energy_Total = round(s.Energy_P101+s.Energy_P301+s.Energy_P501);
end


%% =========================================================================
%%  Helpers
%% =========================================================================
function v = clamp(v, lo, hi)
    v = max(lo, min(hi, v));
end

function v = get_field(s, name, default)
    if isfield(s, name); v = double(s.(name));
    else;                v = default;
    end
end

function level = tank_refill(level, lo, hi, increment)
    persistent refill_active;
    if isempty(refill_active); refill_active = containers.Map; end
    key = sprintf('%d_%d', round(lo*10), round(hi*10));
    if ~isKey(refill_active, key); refill_active(key) = false; end
    if level <= lo;  refill_active(key) = true;
    elseif level >= hi; refill_active(key) = false;
    end
    if refill_active(key) && level < hi
        level = min(hi, level + increment);
    end
end