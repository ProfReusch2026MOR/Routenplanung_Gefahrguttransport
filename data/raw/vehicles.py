import pandas as pd

vehicles = pd.DataFrame([
    {
        "type": "MAN_eTGX",
        "manufacturer": "MAN",
        "capacity_t": 18,
        "battery_kwh": 480,
        "range_km": 500,
        "energy_kwh_per_km": 0.96,
        "max_gross_weight_t": 40,
        "fixed_cost": 180,
        "variable_cost_per_km": 0.55,
        "charging_power_kw": 375,
        "role": "flex_regional_longhaul"
    },
    {
        "type": "Volvo_FH_Electric",
        "manufacturer": "Volvo",
        "capacity_t": 20,
        "battery_kwh": 540,
        "range_km": 470,
        "energy_kwh_per_km": 1.15,
        "max_gross_weight_t": 65,
        "fixed_cost": 200,
        "variable_cost_per_km": 0.60,
        "charging_power_kw": 350,
        "role": "heavy_longhaul"
    },
    {
        "type": "Mercedes_eActros_600",
        "manufacturer": "Mercedes-Benz",
        "capacity_t": 22,
        "battery_kwh": 621,
        "range_km": 500,
        "energy_kwh_per_km": 1.20,
        "max_gross_weight_t": 44,
        "fixed_cost": 220,
        "variable_cost_per_km": 0.65,
        "charging_power_kw": 400,
        "role": "premium_longhaul"
    }
])

vehicles.to_csv("data/processed/vehicles.csv", index=False)