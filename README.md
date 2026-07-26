# EcoLoop — LLM-Driven Autonomous HVAC Control Agent

A closed-loop AI agent that replaces static HVAC schedules with real-time, physics-grounded decisions. **EnergyPlus** (building physics simulation) is paired with a self-hosted **Qwen2.5-7B-Instruct** LLM, which sets cooling/heating setpoints every simulated hour based on live zone temperature, outdoor conditions, and thermal trend — with a deterministic safety net enforcing hard physical and comfort bounds before any setpoint reaches the simulation.

## Results (72-hr simulation, 3 day/night cycles)

| Metric | Baseline | AI Agent |
|---|---|---|
| Total HVAC energy | 91.39 kWh | 64.09 kWh |
| Net energy saved | — | 27.30 kWh |
| Percentage savings | — | **29.87%** |
| Comfort in-band (20–26°C, occupied hrs) | 100.0% | 87.9% |

See [`SYSTEM_ARCHITECTURE.md`](./SYSTEM_ARCHITECTURE.md) for the full architecture writeup, dashboard breakdown, and known limitations.

## How it works

EnergyPlus (state) → Interval Governor → Prompt Builder → Qwen2.5-7B (tool call)
↓
EnergyPlus (actuators) ← Safety Net (validate/correct) ← set_hvac_setpoints(cool, heat)


The AI has full authority to choose setpoints; a rule-based safety net (`safety_net.py`) validates every decision against occupancy-aware hardware bounds before it's applied, feeding rejections back to the model as natural-language correction signal.

## Folder structure

- `src/` — agent source code (main loop, tool-calling bus, safety net)
- `models/` — `baseline.idf` building model; `models/modified/` holds timestamped runtime artifacts generated on each AI-agent run
- `output_baseline/`, `output_ai/`, `output/` — raw EnergyPlus simulation output (CSV, ESO, etc.) from actual runs — regenerated automatically, not hand-edited
- `notebooks/` — development/analysis notebooks
- `visual_dashboard.py` — builds `hvac_savings_dashboard_fixed.png` from the two runs' CSV output
- `SYSTEM_ARCHITECTURE.md` — full technical writeup
- `EcoLoop_Idea_Presentation.pptx` — project submission deck
- `PoC_Video_final.mp4` — 3-minute proof-of-concept walkthrough

## Running it

```bash
pip install -r requirements.txt
python src/main_loop.py       # runs baseline + AI agent simulations back to back
python visual_dashboard.py    # generates the savings/comfort dashboard from the CSV output
```

Requires EnergyPlus 26.1 installed locally and a running Ollama instance serving `qwen2.5:7b-instruct` with tool-calling enabled (see `main_loop.py` for the endpoint config).

## Known limitations (disclosed)

- Results vary run-to-run since the LLM's exploration isn't seeded/temperature-locked
- Comfort proxy is a simplified % of occupied hours within a 20–26°C band, not a full Fanger PMV calculation
- The occupied-hours heating floor (19°C) sits slightly below the comfort band's lower edge (20°C), which can affect the comfort score during overnight-setback recovery — see architecture doc §8 for detail
