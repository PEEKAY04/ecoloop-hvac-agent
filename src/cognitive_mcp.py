# Global variables to act as the communication bus between the LLM and the EnergyPlus callback
current_sim_cooling_setpoint = 24.0
current_sim_heating_setpoint = 21.0

def set_hvac_setpoints(cooling_temp: float, heating_temp: float) -> str:
    """
    Update the building's HVAC setpoints. 
    Args:
        cooling_temp: The target temperature for the AC system.
        heating_temp: The target temperature for the heating system.
    Returns:
        A confirmation string of the applied setpoints.
    """
    global current_sim_cooling_setpoint, current_sim_heating_setpoint
    
    # --- LIVE DEMO PRINT: the cognitive_mcp bus receiving the validated values ---
    print(f"   ↳ cognitive_mcp bus updated: Cooling={cooling_temp}°C, Heating={heating_temp}°C")
    # ------------------------------------------------------------------------------
    
    # Update the global state that EnergyPlus will read
    current_sim_cooling_setpoint = cooling_temp
    current_sim_heating_setpoint = heating_temp
    
    return f"Setpoints successfully updated to Cooling: {cooling_temp}C, Heating: {heating_temp}C"