import os
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

# Define paths to EnergyPlus output CSV files
BASELINE_CSV = "output_baseline/eplusout.csv"
AI_CSV = "output_ai/eplusout.csv"

COMFORT_LOW = 20.0
COMFORT_HIGH = 26.0
ZONE_TEMP_COL = "SPACE1-1:Zone Air Temperature [C](Hourly)"


def load_data(filepath):
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return None
    df = pd.read_csv(filepath)
    df.columns = df.columns.str.strip()
    # Parse hour-of-day from the Date/Time column (handles the "24:00:00" EnergyPlus quirk)
    df["hour"] = df["Date/Time"].str.extract(r"(\d{2}):\d{2}:\d{2}").astype(int) % 24
    return df


def comfort_stats(df):
    """% of occupied hours (8am-6pm) where zone temp stays within the comfort band."""
    occupied = df[(df["hour"] >= 8) & (df["hour"] <= 18)]
    in_band = occupied[ZONE_TEMP_COL].between(COMFORT_LOW, COMFORT_HIGH)
    pct = 100 * in_band.sum() / len(occupied)
    return pct, occupied


def main():
    print("📊 Loading simulation results...")
    df_base = load_data(BASELINE_CSV)
    df_ai = load_data(AI_CSV)

    if df_base is None or df_ai is None:
        print("⚠️ Missing CSV output files. Check your output directory paths.")
        return

    # Identify HVAC Energy columns ONLY for the AI-controlled Edge Node (SPACE1-1)
    energy_cols = [
        col for col in df_base.columns
        if ("Electricity" in col or "Heating" in col or "Cooling" in col or "HVAC" in col) and "SPACE1-1" in col
    ]
    print(f"Identified Energy Columns: {energy_cols}")

    base_total = df_base[energy_cols].sum().sum() / 1000  # Wh -> kWh
    ai_total = df_ai[energy_cols].sum().sum() / 1000

    savings_kwh = base_total - ai_total
    pct_savings = (savings_kwh / base_total) * 100 if base_total > 0 else 0

    print("\n" + "=" * 45)
    print("      🎉 HVAC ENERGY SAVINGS SUMMARY 🎉      ")
    print("=" * 45)
    print(f" Baseline Total Energy : {base_total:.2f} kWh")
    print(f" Autonomous AI Energy  : {ai_total:.2f} kWh")
    print(f" Net Energy Saved      : {savings_kwh:.2f} kWh")
    print(f" Percentage Savings    : {pct_savings:.2f}%")
    print("=" * 45)

    # --- COMFORT PROXY METRIC ---
    base_comfort_pct, base_occ = comfort_stats(df_base)
    ai_comfort_pct, ai_occ = comfort_stats(df_ai)
    print("\n" + "=" * 45)
    print("      🛋️  COMFORT PROXY SUMMARY (proxy, not Fanger PMV)")
    print("=" * 45)
    print(f" Comfort band          : {COMFORT_LOW:.0f}–{COMFORT_HIGH:.0f}°C, occupied hours 8am–6pm")
    print(f" Baseline in-band      : {base_comfort_pct:.1f}%")
    print(f" AI agent in-band      : {ai_comfort_pct:.1f}%")
    print("=" * 45 + "\n")

    # --- PLOTTING ---
    fig, axes = plt.subplots(2, 1, figsize=(12, 9))

    # Plot 1: Cumulative Energy Comparison
    axes[0].plot(
        df_base.index,
        (df_base[energy_cols].sum(axis=1).cumsum()) / 3.6e6,
        label="Baseline (Fixed Setpoints)",
        color="#e74c3c",
        linewidth=2,
    )
    axes[0].plot(
        df_ai.index,
        (df_ai[energy_cols].sum(axis=1).cumsum()) / 3.6e6,
        label=f"Autonomous AI Agent ({pct_savings:.1f}% Savings)",
        color="#2ecc71",
        linewidth=2,
    )
    axes[0].set_ylabel("Cumulative Energy (kWh)")
    axes[0].set_xlabel("Simulation Hours")
    axes[0].set_title(
        "Energy Consumption: Baseline vs Cognitive AI Agent",
        fontsize=14,
        fontweight="bold",
    )
    axes[0].grid(True, linestyle="--", alpha=0.6)
    axes[0].legend(fontsize=11)

    # Plot 2 (FIXED): Zone Temperature with comfort band, occupied hours highlighted
    ax = axes[1]
    ax.plot(df_base.index, df_base[ZONE_TEMP_COL], label="Baseline Zone Temp",
            color="#95a5a6", linestyle="--", linewidth=1.6)
    ax.plot(df_ai.index, df_ai[ZONE_TEMP_COL], label="AI Controlled Zone Temp",
            color="#3498db", linewidth=1.8)

    # Shade the comfort band
    ax.axhspan(COMFORT_LOW, COMFORT_HIGH, color="#2ecc71", alpha=0.12,
               label=f"Comfort Band ({COMFORT_LOW:.0f}–{COMFORT_HIGH:.0f}°C)")

    # Shade occupied hours (8am-6pm) across each day so morning dips are visible in context
    for day_start in range(0, len(df_base), 24):
        occ_start = day_start + 8
        occ_end = min(day_start + 18, len(df_base) - 1)
        ax.axvspan(occ_start, occ_end, color="orange", alpha=0.05)

    ax.set_ylabel("Zone Air Temperature (°C)")
    ax.set_xlabel("Simulation Hours")
    ax.set_title("Thermal Comfort Proxy: % of Occupied Hours (8am\u20136pm) Within Comfort Band",
                 fontsize=13, fontweight="bold")
    ax.grid(True, linestyle="--", alpha=0.6)

    # Annotate the comfort percentages directly on the chart
    ax.text(0.015, 0.06,
            f"Baseline in-band:  {base_comfort_pct:.1f}%\nAI agent in-band:  {ai_comfort_pct:.1f}%",
            transform=ax.transAxes, fontsize=10, verticalalignment="bottom",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white", edgecolor="#888", alpha=0.9))

    ax.legend(fontsize=9, loc="upper left")

    plt.tight_layout()
    plt.savefig("hvac_savings_dashboard_fixed.png", dpi=300)
    print("✅ Fixed dashboard saved to 'hvac_savings_dashboard_fixed.png'!")


if __name__ == "__main__":
    main()