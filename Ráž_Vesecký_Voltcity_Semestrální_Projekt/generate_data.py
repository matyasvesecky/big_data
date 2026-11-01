"""
VoltCity Dynamics – Generátor syntetických dat
===============================================
Generuje realistická data pro systém sdílené mikromobility v Praze:
  - weather_raw.csv  : hodinová data o počasí (2 roky)
  - vehicles_raw.csv : 2 000 koloběžek a e-kol
  - users_raw.csv    : 50 000 uživatelů
  - trips_raw.csv    : 520 000+ jízd se sezónností a záměrnými chybami
"""

import pandas as pd
import numpy as np
import calendar
from datetime import datetime, timedelta

np.random.seed(42)

print("=" * 60)
print("  VoltCity Dynamics – Generátor syntetických dat")
print("=" * 60)

# ================================================================
# 1. POČASÍ – hodinová data pro Praha, 2023-01-01 až 2024-12-31
# ================================================================
print("\n[1/4] Generuji data o počasí (Praha, 2 roky)...")

START_DT = datetime(2023, 1, 1)
END_DT   = datetime(2025, 1, 1)
HOURS    = int((END_DT - START_DT).total_seconds() / 3600)

timestamps = pd.date_range(START_DT, periods=HOURS, freq="h")
months_arr = timestamps.month.values
hours_arr  = timestamps.hour.values

# Sezónní teplota: zima ~0°C, léto ~25°C + denní variace + Gaussovský šum
base_temp       = 12.5 - 12.5 * np.cos(2 * np.pi * (months_arr - 1) / 12)
daily_variation = 3.5 * np.sin(np.pi * (hours_arr - 6) / 14)
temperature_c   = base_temp + daily_variation + np.random.normal(0, 2.5, HOURS)
temperature_c   = np.round(temperature_c, 1)

# Srážky: pravděpodobnost dešťového dne ~15 %
rain_prob       = 0.12 + 0.05 * np.sin(2 * np.pi * (months_arr - 3) / 12)
is_raining      = np.random.random(HOURS) < rain_prob
precipitation   = np.where(is_raining, np.random.exponential(3.5, HOURS), 0.0)
precipitation   = np.round(np.clip(precipitation, 0, None), 1)

weather_code = np.where(precipitation > 7, 502,   # silný déšť
              np.where(precipitation > 0, 500,     # slabý déšť
              np.where(temperature_c < 0, 601,     # sníh
              np.where(temperature_c < 8, 801,     # oblačno
              800))))                               # jasno

humidity = np.clip(
    40 + 30 * (precipitation > 0).astype(int) + np.random.normal(0, 10, HOURS),
    15, 100
).astype(int)

wind_speed = np.round(np.abs(np.random.normal(12, 6, HOURS)), 1)

weather_df = pd.DataFrame({
    "timestamp":        timestamps,
    "temperature_c":    temperature_c,
    "precipitation_mm": precipitation,
    "weather_code":     weather_code,
    "humidity_pct":     humidity,
    "wind_speed_kmh":   wind_speed,
})
weather_df.to_csv("weather_raw.csv", index=False)
print(f"   ✓ weather_raw.csv  – {len(weather_df):>7,} záznamů")

# ================================================================
# 2. VOZIDLA – 2 000 koloběžek a e-kol
# ================================================================
print("[2/4] Generuji data o vozidlech...")

NUM_VEHICLES = 2000
v_types  = np.random.choice(["scooter", "ebike"], NUM_VEHICLES, p=[0.65, 0.35])
v_models = np.where(
    v_types == "scooter",
    np.random.choice(["Segway F30", "Xiaomi Pro 3", "Ninebot Max G30"], NUM_VEHICLES),
    np.random.choice(["Giant Revolt E+", "Trek Rail 9", "Specialized Turbo"], NUM_VEHICLES),
)

deploy_offsets = np.random.randint(0, 365, NUM_VEHICLES)
deploy_dates   = [datetime(2022, 1, 1) + timedelta(days=int(d)) for d in deploy_offsets]
age_days       = np.array([(datetime(2024, 12, 31) - d).days for d in deploy_dates])

battery_capacity = np.where(v_types == "scooter",
    np.random.choice([250, 360, 480], NUM_VEHICLES),
    np.random.choice([400, 500, 630], NUM_VEHICLES))

# Starší vozidla mají horší zdraví baterie
battery_health = np.clip(100 - age_days * 0.018 + np.random.normal(0, 4, NUM_VEHICLES), 55, 100)

zones = np.random.choice(
    ["centrum", "vinohrady", "žižkov", "smíchov", "holešovice", "dejvice", "nusle"],
    NUM_VEHICLES, p=[0.30, 0.15, 0.15, 0.12, 0.12, 0.10, 0.06]
)

vehicles_df = pd.DataFrame({
    "vehicle_id":          range(1, NUM_VEHICLES + 1),
    "vehicle_type":        v_types,
    "model":               v_models,
    "deploy_date":         deploy_dates,
    "battery_capacity_wh": battery_capacity,
    "battery_health_pct":  np.round(battery_health, 1),
    "home_zone":           zones,
    "is_active":           np.random.choice([True, False], NUM_VEHICLES, p=[0.92, 0.08]),
})
vehicles_df.to_csv("vehicles_raw.csv", index=False)
print(f"   ✓ vehicles_raw.csv – {len(vehicles_df):>7,} vozidel")

# ================================================================
# 3. UŽIVATELÉ – 50 000 unikátních zákazníků
# ================================================================
print("[3/4] Generuji data o uživatelích...")

NUM_USERS = 50000
segments  = np.random.choice(
    ["commuter", "tourist", "student", "casual"],
    NUM_USERS, p=[0.40, 0.25, 0.20, 0.15]
)
# Commuteři a studenti mají vyšší šanci být předplatitelé
sub_probs = {"commuter": 0.60, "tourist": 0.10, "student": 0.45, "casual": 0.15}
user_types = np.array([
    np.random.choice(["subscriber", "ad-hoc"], p=[sub_probs[s], 1 - sub_probs[s]])
    for s in segments
])

reg_offsets = np.random.randint(0, 912, NUM_USERS)  # 2022–2024
reg_dates   = [datetime(2022, 6, 1) + timedelta(days=int(d)) for d in reg_offsets]

app_versions = np.random.choice(["iOS", "Android", "Web"], NUM_USERS, p=[0.45, 0.48, 0.07])
cities       = np.random.choice(["Praha", "Brno", "Ostrava", "Plzeň", "Jiné"],
                                  NUM_USERS, p=[0.70, 0.13, 0.09, 0.05, 0.03])

users_df = pd.DataFrame({
    "user_id":           range(1, NUM_USERS + 1),
    "user_type":         user_types,
    "segment":           segments,
    "registration_date": reg_dates,
    "city":              cities,
    "app_platform":      app_versions,
})
users_df.to_csv("users_raw.csv", index=False)
print(f"   ✓ users_raw.csv    – {len(users_df):>7,} uživatelů")

# ================================================================
# 4. JÍZDY – 520 000+ záznamů se sezónností a korelací s počasím
# ================================================================
print("[4/4] Generuji data o jízdách (~520k záznamů)...")

TOTAL_DAYS = (END_DT - START_DT).days  # 730

# --- Denní váhy: sezónnost × den v týdnu ---
day_index    = np.arange(TOTAL_DAYS)
day_dates    = [START_DT + timedelta(days=int(d)) for d in day_index]
day_months   = np.array([d.month for d in day_dates])
day_weekdays = np.array([d.weekday() for d in day_dates])  # 0=Po, 6=Ne

MONTHLY_SCALE = {
    1: 0.33, 2: 0.37, 3: 0.55, 4: 0.75, 5: 1.00,
    6: 1.22, 7: 1.32, 8: 1.26, 9: 1.06, 10: 0.80,
    11: 0.50, 12: 0.30
}
monthly_weights = np.array([MONTHLY_SCALE[m] for m in day_months])
# Víkend = méně dojíždějících, ale turisté kompenzují → 80 %
weekday_factor  = np.where(day_weekdays >= 5, 0.78, 1.0)

# ── VYLEPŠENÍ 1: Kauzální korelace počasí s poptávkou ────────
# Načteme denní průměry počasí z vygenerovaných hodinových dat
print("   [+] Aplikuji weather-demand korelaci na denní váhy...")
weather_daily = weather_df.copy()
weather_daily['date'] = weather_daily['timestamp'].dt.date
weather_agg = weather_daily.groupby('date').agg(
    avg_temp=('temperature_c', 'mean'),
    avg_precip=('precipitation_mm', 'mean')
).reset_index()
weather_agg['date'] = pd.to_datetime(weather_agg['date'])

# Sestavíme pole průměrné teploty a srážek pro každý den v simulaci
day_dates_ts = pd.to_datetime(day_dates)
day_temp  = np.array([weather_agg.loc[weather_agg['date'] == d, 'avg_temp'].values[0]
                       if d in weather_agg['date'].values else 12.0
                       for d in day_dates_ts])
day_precip = np.array([weather_agg.loc[weather_agg['date'] == d, 'avg_precip'].values[0]
                        if d in weather_agg['date'].values else 0.0
                        for d in day_dates_ts])

# Teplotní faktor: pod 5 °C → -30 %, nad 18 °C → +15 %
temp_factor = np.clip(0.70 + (day_temp - 5.0) * (0.45 / 20.0), 0.55, 1.15)
# Srážkový faktor: > 5 mm/h → -40 %, 1–5 mm/h → -20 %
rain_factor = np.where(day_precip > 5, 0.60,
              np.where(day_precip > 1, 0.80, 1.0))

day_weights = monthly_weights * weekday_factor * temp_factor * rain_factor
day_weights /= day_weights.sum()

TARGET_TRIPS = 522000

# --- Hodinové váhy (dojíždějící: ranní a odpolední špička) ---
HOURLY_WEIGHTS_COMMUTER = np.array([
    0.18, 0.10, 0.08, 0.07, 0.12, 0.45,   # 00–05
    1.30, 2.70, 2.90, 1.80, 1.20, 1.05,   # 06–11
    1.35, 1.10, 0.90, 1.05, 2.30, 2.70,   # 12–17
    2.10, 1.50, 0.95, 0.72, 0.55, 0.30    # 18–23
])
# ── VYLEPŠENÍ 2: Turistický hodinový profil (víkend: pozdní ráno–večer) ──
HOURLY_WEIGHTS_TOURIST = np.array([
    0.05, 0.03, 0.02, 0.02, 0.03, 0.05,   # 00–05
    0.10, 0.20, 0.55, 1.10, 1.60, 1.80,   # 06–11
    1.90, 1.95, 1.85, 1.75, 1.60, 1.40,   # 12–17
    1.20, 0.90, 0.60, 0.35, 0.20, 0.10    # 18–23
])
HOURLY_WEIGHTS_COMMUTER /= HOURLY_WEIGHTS_COMMUTER.sum()
HOURLY_WEIGHTS_TOURIST  /= HOURLY_WEIGHTS_TOURIST.sum()

# Smícháme profily: víkendy mají 40 % turistický charakter, všední dny 10 %
day_is_weekend = day_weekdays >= 5
tourist_share_per_day = np.where(day_is_weekend, 0.40, 0.10)

# --- Vektorizované sestavení časových razítek ---
sampled_days    = np.random.choice(TOTAL_DAYS, size=TARGET_TRIPS, p=day_weights)

# Hodinové vzorkování dle turistického podílu daného dne
tourist_share_trip = tourist_share_per_day[sampled_days]
use_tourist = np.random.random(TARGET_TRIPS) < tourist_share_trip
sampled_hours = np.where(
    use_tourist,
    np.array([np.random.choice(24, p=HOURLY_WEIGHTS_TOURIST)  for _ in range(TARGET_TRIPS)]),
    np.array([np.random.choice(24, p=HOURLY_WEIGHTS_COMMUTER) for _ in range(TARGET_TRIPS)])
)
sampled_minutes = np.random.randint(0, 60,    TARGET_TRIPS)
sampled_seconds = np.random.randint(0, 60,    TARGET_TRIPS)

total_seconds   = (sampled_days     * 86400
                   + sampled_hours  * 3600
                   + sampled_minutes * 60
                   + sampled_seconds)
start_times = pd.to_datetime(START_DT) + pd.to_timedelta(total_seconds, unit="s")

# --- GPS souřadnice s hustotou v centru Prahy ---
LAT_C, LON_C = 50.0755, 14.4378  # centrum Prahy
LAT_SD, LON_SD = 0.025, 0.032

start_lats = np.clip(np.random.normal(LAT_C, LAT_SD, TARGET_TRIPS), 50.00, 50.15)
start_lons = np.clip(np.random.normal(LON_C, LON_SD, TARGET_TRIPS), 14.30, 14.58)

# --- Vlastnosti jízdy ---
# Délka jízdy: Gamma rozdělení, průměr ~10 min (last-mile charakter)
duration_min = np.clip(np.random.gamma(shape=1.9, scale=6, size=TARGET_TRIPS), 1.5, 120)

# Vzdálenost: koreluje s délkou + přirozený šum
speed_kmh_real = np.clip(np.random.normal(14, 3, TARGET_TRIPS), 5, 25)
distance_km    = np.round(np.clip(duration_min / 60 * speed_kmh_real, 0.1, 18), 2)

# Cena: závisí na délce a typu uživatele
user_ids       = np.random.randint(1, NUM_USERS + 1, TARGET_TRIPS)
vehicle_ids    = np.random.randint(1, NUM_VEHICLES + 1, TARGET_TRIPS)

# ~35 % jízd je od předplatitelů (levnější tarif)
is_sub_trip    = np.random.random(TARGET_TRIPS) < 0.35
unlock_fee     = np.where(is_sub_trip, 5.0, 15.0)
per_min_rate   = np.where(is_sub_trip, 2.5, 4.0)
revenue_czk    = np.round(unlock_fee + duration_min * per_min_rate
                          + np.random.normal(0, 4, TARGET_TRIPS), 2)
revenue_czk    = np.clip(revenue_czk, 8, 600)

# Stav baterie
battery_start  = np.round(np.random.uniform(18, 100, TARGET_TRIPS), 1)
consumption    = distance_km * np.random.uniform(1.8, 4.5, TARGET_TRIPS)
battery_end    = np.round(np.clip(battery_start - consumption, 0, 100), 1)

# Konec jízdy – posun od startu o vzdálenost
bearing        = np.random.uniform(0, 2 * np.pi, TARGET_TRIPS)
end_lats = np.round(np.clip(start_lats + (distance_km / 111) * np.cos(bearing), 50.00, 50.15), 6)
end_lons = np.round(np.clip(
    start_lons + (distance_km / (111 * np.cos(np.radians(LAT_C)))) * np.sin(bearing), 14.30, 14.58
), 6)

trips_df = pd.DataFrame({
    "trip_id":          range(1, TARGET_TRIPS + 1),
    "user_id":          user_ids,
    "vehicle_id":       vehicle_ids,
    "start_time":       start_times,
    "duration_min":     np.round(duration_min, 1),
    "distance_km":      distance_km,
    "revenue_czk":      revenue_czk,
    "start_lat":        np.round(start_lats, 6),
    "start_lon":        np.round(start_lons, 6),
    "end_lat":          end_lats,
    "end_lon":          end_lons,
    "battery_start_pct": battery_start,
    "battery_end_pct":   battery_end,
})

# ================================================================
# ZÁMĚRNÉ CHYBY pro sekci Data Quality (celkem ~2.8 %)
# ================================================================
n = len(trips_df)

# 1.0 % – GPS v Atlantiku (mimo Praha)
idx = np.random.choice(n, int(n * 0.010), replace=False)
trips_df.loc[idx, "start_lat"] = np.random.uniform(-30, -10, len(idx))
trips_df.loc[idx, "start_lon"] = np.random.uniform(-40, -20, len(idx))

# 0.5 % – záporná vzdálenost
idx = np.random.choice(n, int(n * 0.005), replace=False)
trips_df.loc[idx, "distance_km"] = np.round(-np.random.uniform(0.1, 5.0, len(idx)), 2)

# 0.3 % – outlier: zapomenutá jízda (>800 min)
idx = np.random.choice(n, int(n * 0.003), replace=False)
trips_df.loc[idx, "duration_min"] = np.round(np.random.uniform(820, 1440, len(idx)), 1)

# 0.5 % – chybějící user_id (NULL)
idx = np.random.choice(n, int(n * 0.005), replace=False)
trips_df.loc[idx, "user_id"] = np.nan

# 0.3 % – záporná cena (chyba platebního systému)
idx = np.random.choice(n, int(n * 0.003), replace=False)
trips_df.loc[idx, "revenue_czk"] = np.round(-np.random.uniform(1, 50, len(idx)), 2)

trips_df.to_csv("trips_raw.csv", index=False)

n_errors = int(n * (0.010 + 0.005 + 0.003 + 0.005 + 0.003))
print(f"   ✓ trips_raw.csv    – {len(trips_df):>7,} jízd "
      f"(z toho {n_errors:,} záměrných chyb = {n_errors/n*100:.1f} %)")

print("\n✅ Hotovo! Vygenerované soubory:")
print("   trips_raw.csv | users_raw.csv | vehicles_raw.csv | weather_raw.csv")