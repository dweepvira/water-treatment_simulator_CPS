%% swat_physics_step.m
% Called by engine_bridge.py via MATLAB Engine API.
%
% Usage:
%   sensors = swat_physics_step(actuators, dt)
%
% actuators : struct with bool/int fields matching CODESYS coil + valve names
% dt        : timestep in seconds (typically 0.1)
% sensors   : struct with INT register values to write back to CODESYS
%
% State is maintained in a persistent variable so successive calls form a
% continuous simulation.  Call swat_physics_reset() to re-initialise.

function sensors = swat_physics_step(actuators, dt)
    persistent state;

    if isempty(state)
        state = swat_init_state();
    end

    [state, sensors] = swat_step(state, actuators, dt);
end


function s = swat_init_state()
    % Mirrors init_state() in swat_physics_server.m exactly.
    % Any change here must be reflected there and vice versa.
    s.LIT_101 = 500;  s.FIT_101 = 0;  s.FIT_201 = 0;
    s.pH = 7.20;  s.AIT_201 = 450;  s.AIT_203 = 410;
    s.Chlorine_Residual = 3.0;
    s.Acid_Tank_Level = 75;  s.Chlorine_Tank_Level = 80;
    s.Coagulant_Tank_Level = 80;  s.Bisulfate_Tank_Level = 85;
    s.LIT_301 = 800;  s.FIT_301 = 0;  s.DPIT_301 = 5;
    s.UF_Fouling = 0;  s.UF_Runtime = 0;  s.UF_LastBW = 0;
    s.Turbidity_UF = 0;
    s.LIT_401 = 500;  s.FIT_401 = 0;  s.AIT_402 = 200;
    s.AIT_401_val = 15;
    s.PIT_501 = 0;  s.FIT_501 = 0;  s.FIT_502 = 0;
    s.FIT_503 = 0;  s.FIT_504 = 0;
    s.RO_Fouling = 0;  s.RO_Runtime = 0;  s.RO_LastClean = 0;
    s.TDS_Feed = 5000;  s.TDS_Permeate = 50;
    s.FIT_601 = 0;
    s.Water_Temp = 25;  s.Ambient_Temp = 25;
    s.Turbidity_Raw = 150;
    s.Energy_P101 = 0;  s.Energy_P301 = 0;  s.Energy_P501 = 0;
    s.noise_seed = 7;
end


% step_physics is defined in swat_physics_server.m — source it once.
% To avoid duplication, this file delegates to the shared helper.
% If running standalone (without server), paste the body of step_physics here.
function [state_out, sensors] = swat_step(state, act, dt)
    % Delegate to shared implementation in swat_physics_server.m
    % (both files must be on the MATLAB path)
    [state_out, sensors] = step_physics(state, act, dt);
end
