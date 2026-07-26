import os
import shutil
import sys
from datetime import datetime
# Update this path if yours is different
sys.path.insert(0, 'C:\\EnergyPlusV26-1-0')

import requests
import json
from pyenergyplus.api import EnergyPlusAPI
import cognitive_mcp
from safety_net import validate_and_correct_setpoints
from collections import deque

# Dual-Memory Architecture for Long-Horizon Learning
day_memory_buffer = deque(maxlen=5)
night_memory_buffer = deque(maxlen=5)

# ---------------------------------------------------------
# 1. Configuration & Global State
# ---------------------------------------------------------
OLLAMA_API_URL = "https://upper-cuddly-siberian.ngrok-free.dev/api/chat"
MODEL_NAME = "qwen2.5:7b-instruct"

# Global flags and memory for the AI
handles_initialized = False
zone_temp_handle = -1
cooling_actuator_handle = -1
heating_actuator_handle = -1
outdoor_temp_handle = -1

# Interval Governor & Memory state
last_hour_run = -1  # <--- Add this global variable
last_zone_temp = None

#from collections import deque
# A sliding window memory that remembers the last 3 actions
#memory_buffer = deque(maxlen=3)

# ---------------------------------------------------------
# 2. Advanced Prompt Engineering & Cognitive Inference
# ---------------------------------------------------------
def query_qwen_for_setpoints(zone_temp: float, outdoor_temp: float, temp_trend: str, current_hour: int) -> None:

    # 1. State-Space Detection
    is_daytime = 8 <= current_hour <= 18
    active_buffer = day_memory_buffer if is_daytime else night_memory_buffer

    # 2. Pure Autonomous Prompting (With Action Masking)
    system_prompt = (
        "You are an autonomous RL HVAC Agent optimizing for maximum energy efficiency. "
        "Your goal is to widen the deadband (gap between cooling and heating) as much as possible. "
        "You must discover the building's physical limits by exploring, but you MUST obey these Action Masks:\n"
        "1. THERMODYNAMICS: Cooling setpoints MUST ALWAYS be higher than Heating setpoints.\n"
        "2. SYSTEMATIC EXPLORATION: Do not guess wildly. Make incremental adjustments (e.g., 0.5C or 1.0C steps).\n"
        "3. ERROR CORRECTION: If a setpoint is 'REJECTED: Too High', lower it. If 'REJECTED: Too Low', raise it.\n"
        "Analyze your memory buffer and intelligently 'ride the rail' of the accepted boundaries."
    )

    user_prompt = (
        f"CURRENT STATE:\n"
        f"- Indoor Temp: {zone_temp:.2f}C\n"
        f"- Outdoor Temp: {outdoor_temp:.2f}C\n"
        f"- Thermal Trend: {temp_trend}\n"
        f"- Current Time: Hour {current_hour} of the day (0-23)\n\n"
    )
    
    # 3. Contextual Memory Injection
    if active_buffer:
        user_prompt += "YOUR RECENT ACTIONS IN THIS TIME CONTEXT:\n"
        for mem in active_buffer:
            user_prompt += f"{mem}\n"
        user_prompt += "\nUse this history to avoid repeating rejected actions. Find the mathematical edge."

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "set_hvac_setpoints",
                    "description": "Adjust the HVAC cooling and heating setpoints.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "cooling_temp": {"type": "number", "description": "Cooling setpoint in Celsius"},
                            "heating_temp": {"type": "number", "description": "Heating setpoint in Celsius"}
                        },
                        "required": ["cooling_temp", "heating_temp"]
                    }
                }
            }
        ],
        "stream": False
    }
    
    try:
        headers = {"Content-Type": "application/json", "ngrok-skip-browser-warning": "true"}

        # --- LIVE DEMO PRINT (stage 2/5): request leaving the machine, over the ngrok tunnel ---
        print(f"📡  SENDING -> Qwen2.5-7B via ngrok tunnel ({OLLAMA_API_URL}) ...")
        # -----------------------------------------------------------------------------------
        response = requests.post(OLLAMA_API_URL, json=payload, headers=headers)
        
        if response.status_code != 200:
            print(f"⚠️ SERVER ERROR: {response.status_code} - {response.text}")
            return
        
        response_data = response.json()
        message = response_data.get("message", {})
        tool_calls = message.get("tool_calls", [])
        
        if tool_calls:
            # --- LIVE DEMO PRINT (stage 3/5): response received back over the tunnel ---
            print(f"📥  RECEIVED <- response from Qwen2.5 (tool call present)")
            # ---------------------------------------------------------------------------
            for tool in tool_calls:
                if tool["function"]["name"] == "set_hvac_setpoints":
                    args = tool["function"]["arguments"]
                    print(f"🧠 AI Decision [Hour {current_hour}:00 | {temp_trend}] -> Cooling: {args['cooling_temp']}°C | Heating: {args['heating_temp']}°C")

                    # ---> THE CRITICAL FIX IS RIGHT HERE <---
                    # --- LIVE DEMO PRINT (stage 4/5): safety net validating the request ---
                    print(f"🛡️  SAFETY NET: validating (Cooling={args['cooling_temp']}°C, Heating={args['heating_temp']}°C) against hour-{current_hour} hardware bounds...")
                    # ------------------------------------------------------------------------
                    safe_cool, safe_heat, new_feedback = validate_and_correct_setpoints(args["cooling_temp"], args["heating_temp"], current_hour)
                    
                    if new_feedback:
                        print(f"{new_feedback}")
                        active_buffer.append(f"Tried ({args['cooling_temp']}C, {args['heating_temp']}C) -> FAILED: Overridden to ({safe_cool}C, {safe_heat}C)")
                    else:
                        # --- LIVE DEMO PRINT (stage 4/5, accepted case): otherwise a clean pass is silent ---
                        print(f"✅  SAFETY NET: accepted as-is, within bounds.")
                        # ------------------------------------------------------------------------------------
                        active_buffer.append(f"Tried ({args['cooling_temp']}C, {args['heating_temp']}C) -> SUCCESS: Setpoints accepted by hardware.")
                    cognitive_mcp.set_hvac_setpoints(safe_cool, safe_heat)
                    # --- LIVE DEMO PRINT (stage 5/5): setpoint written to the comms bus, applied next tick ---
                    print(f"⚙️  SETPOINT APPLIED -> Cooling: {safe_cool}°C | Heating: {safe_heat}°C (queued for actuator)")
                    # -----------------------------------------------------------------------------------------
        else:
            print("⚠️ INFERENCE WARNING: LLM did not return a tool call.")
            
    except Exception as e:
        print(f"⚠️ NETWORK FALLBACK: {e}")

# ---------------------------------------------------------
# 3. Interval Governor & EnergyPlus Callback
# ---------------------------------------------------------
def callback_end_of_zone_timestep(state):
    global handles_initialized, zone_temp_handle, cooling_actuator_handle, heating_actuator_handle
    global step_counter, last_zone_temp, is_currently_occupied # <--- Added to globals!
    global last_hour_run # <--- Don't forget to add this to the global declaration at the top of the function!
    global outdoor_temp_handle

    if not api.exchange.api_data_fully_ready(state): return
    if api.exchange.warmup_flag(state): return

    if not handles_initialized:
        zone_temp_handle = api.exchange.get_variable_handle(state, "Zone Air Temperature", "SPACE1-1")
        cooling_actuator_handle = api.exchange.get_actuator_handle(state, "Zone Temperature Control", "Cooling Setpoint", "SPACE1-1")
        heating_actuator_handle = api.exchange.get_actuator_handle(state, "Zone Temperature Control", "Heating Setpoint", "SPACE1-1")
        outdoor_temp_handle = api.exchange.get_variable_handle(state, "Site Outdoor Air Drybulb Temperature", "Environment")
        handles_initialized = True

    # 1. Get Current Physical State and Time
    current_zone_temp = api.exchange.get_variable_value(state, zone_temp_handle)
    current_outdoor_temp = api.exchange.get_variable_value(state, outdoor_temp_handle)
    current_hour = api.exchange.hour(state) 

    # --- LIVE DEMO PRINT (stage 1/5): EnergyPlus physics state for this hour ---
    # (only printed once we're past the interval governor check below, see next block)

    # ---------------------------------------------------------
    # NEW INTERVAL GOVERNOR: Run exactly once per simulation hour
    # ---------------------------------------------------------
    if current_hour == last_hour_run:
        return  # Skip until the clock rolls over to the next hour
    
    last_hour_run = current_hour  # Update the tracker
    # --------------------------------------------------------- 

    # --- LIVE DEMO PRINT (stage 1/5): EnergyPlus physics state, computed this hour ---
    print(f"\n🌡️  ENERGYPLUS [Hour {current_hour}:00] -> Zone Temp: {current_zone_temp:.2f}°C | Outdoor Temp: {current_outdoor_temp:.2f}°C")
    # ---------------------------------------------------------------------------------
        
    # PROMPT ENGINEERING METRIC: Calculate Thermal Trend
    temp_trend = "Stable"
    if last_zone_temp is not None:
        delta = current_zone_temp - last_zone_temp
        if delta > 0.1:
            temp_trend = f"Rising by +{delta:.2f}C/hr"
        elif delta < -0.1:
            temp_trend = f"Falling by {delta:.2f}C/hr"
            
    last_zone_temp = current_zone_temp

    # Send data to LLM 
    query_qwen_for_setpoints(current_zone_temp, current_outdoor_temp, temp_trend, current_hour)
    
    # Apply Setpoints
    safe_cooling = cognitive_mcp.current_sim_cooling_setpoint
    safe_heating = cognitive_mcp.current_sim_heating_setpoint
    api.exchange.set_actuator_value(state, cooling_actuator_handle, safe_cooling)
    api.exchange.set_actuator_value(state, heating_actuator_handle, safe_heating)
    # --- LIVE DEMO PRINT: confirms the loop closed - EnergyPlus will simulate with these values next tick ---
    print(f"🔁  LOOP CLOSED: EnergyPlus actuators now set to Cooling={safe_cooling}°C, Heating={safe_heating}°C for Hour {current_hour}:00")
    # ------------------------------------------------------------------------------------------------------------

# ---------------------------------------------------------
# 4. Master Execution (The Dual Runner)
# ---------------------------------------------------------
if __name__ == "__main__":
    api = EnergyPlusAPI()
    
    print("\n==================================================")
    print(" 🏃‍♂️ PHASE 1: RUNNING BASELINE (NO AI) ")
    print("==================================================")
    state_baseline = api.state_manager.new_state()
    # Added '-r' flag to generate eplusout.csv
    api.runtime.run_energyplus(state_baseline, [
        '-d', 'output_baseline', 
        '-w', 'models/weather.epw', 
        '-r',
        'models/baseline.idf'
    ])
    
    print("\n==================================================")
    print(" 🧠 PHASE 2: RUNNING AUTONOMOUS AI AGENT ")
    print("==================================================")
    
    # --- DELIVERABLE GENERATION: Create a uniquely versioned modified model ---
    os.makedirs('models/modified', exist_ok=True)
    
    # Generate a timestamp (e.g., 20260726_151019)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    modified_model_path = f'models/modified/ai_agent_runtime_{timestamp}.idf'
    
    shutil.copy('models/baseline.idf', modified_model_path)
    print(f"📁 Runtime artifact generated: {modified_model_path}")
    # ------------------------------------------------------------------------

    state_ai = api.state_manager.new_state()
    # Attach the AI Callback
    api.runtime.callback_end_zone_timestep_after_zone_reporting(state_ai, callback_end_of_zone_timestep)
    api.runtime.run_energyplus(state_ai, [
        '-d', 'output_ai', 
        '-w', 'models/weather.epw', 
        '-r',
        modified_model_path  # <--- Now running the unique timestamped model!
    ])
    
    print("\n✅ BOTH SIMULATIONS COMPLETE. Data ready for Dashboard analysis.")