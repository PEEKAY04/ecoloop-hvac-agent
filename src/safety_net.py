def validate_and_correct_setpoints(requested_cool, requested_heat, current_hour):
    safe_cool = requested_cool
    safe_heat = requested_heat
    feedback_msgs = []

    # Determine if building is occupied (8 AM to 6 PM)
    is_occupied = 8 <= current_hour <= 18

    if is_occupied:
        # STRICT DAYTIME BOUNDS
        max_cool, min_cool = 26.0, 22.0
        max_heat, min_heat = 23.0, 19.0
    else:
        # RELAXED NIGHTTIME BOUNDS (Deep Setback)
        max_cool, min_cool = 35.0, 20.0
        max_heat, min_heat = 25.0, 15.0

    # --- COOLING BOUNDS ---
    if requested_cool > max_cool:
        safe_cool = max_cool
        feedback_msgs.append(f"Cooling {requested_cool}°C REJECTED: Too High. You must lower it.")
    elif requested_cool < min_cool:
        safe_cool = min_cool
        feedback_msgs.append(f"Cooling {requested_cool}°C REJECTED: Too Low. You must raise it.")

    # --- HEATING BOUNDS ---
    if requested_heat < min_heat:
        safe_heat = min_heat
        feedback_msgs.append(f"Heating {requested_heat}°C REJECTED: Too Low. You must raise it.")
    elif requested_heat > max_heat:
        safe_heat = max_heat
        feedback_msgs.append(f"Heating {requested_heat}°C REJECTED: Too High. You must lower it.")

    # --- DEADBAND CHECK ---
    if safe_cool <= safe_heat:
        safe_cool = safe_heat + 1.0
        feedback_msgs.append("CRITICAL: Cooling setpoint must be higher than Heating setpoint.")

    final_feedback = "⚠️ SYSTEM FEEDBACK: " + " | ".join(feedback_msgs) if feedback_msgs else ""
    return safe_cool, safe_heat, final_feedback