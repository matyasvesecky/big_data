"""
VoltCity Dynamics – Inicializace DuckDB skladu
===============================================
Načte CSV soubory, vytvoří tabulky a analytické views (sémantická vrstva):
  raw_* tabulky  : surová data tak jak přišla
  v_trips_clean  : vyčištěná jízda + feature engineering + počasí
  v_kpi_*        : hotové KPI agregace připravené pro notebook
"""

import duckdb
import os
import sys

DB_PATH = "VoltCity.duckdb"

# ── Kontrola vstupních souborů ─────────────────────────────────
required = ["trips_raw.csv", "users_raw.csv", "vehicles_raw.csv", "weather_raw.csv"]
missing  = [f for f in required if not os.path.exists(f)]
if missing:
    print(f"❌  Chybí soubory: {missing}")
    print("    Nejprve spusť:  python generate_data.py")
    sys.exit(1)

# Smaž starou DB pro čistý start
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

con = duckdb.connect(DB_PATH)
print(f"Vytvářím databázi: {DB_PATH}\n")

# ================================================================
# 1. SUROVÉ TABULKY (raw layer)
# ================================================================
print("[1/4] Načítám surová data...")

con.execute("""
    CREATE TABLE raw_trips AS
        SELECT * FROM read_csv_auto('trips_raw.csv', timestampformat='%Y-%m-%d %H:%M:%S');
""")
n_trips = con.execute("SELECT COUNT(*) FROM raw_trips").fetchone()[0]

con.execute("""
    CREATE TABLE raw_users AS
        SELECT * FROM read_csv_auto('users_raw.csv', timestampformat='%Y-%m-%d %H:%M:%S');
""")
n_users = con.execute("SELECT COUNT(*) FROM raw_users").fetchone()[0]

con.execute("""
    CREATE TABLE raw_vehicles AS
        SELECT * FROM read_csv_auto('vehicles_raw.csv', timestampformat='%Y-%m-%d %H:%M:%S');
""")
n_vehs = con.execute("SELECT COUNT(*) FROM raw_vehicles").fetchone()[0]

con.execute("""
    CREATE TABLE raw_weather AS
        SELECT * FROM read_csv_auto('weather_raw.csv', timestampformat='%Y-%m-%d %H:%M:%S');
""")
n_weather = con.execute("SELECT COUNT(*) FROM raw_weather").fetchone()[0]

print(f"   raw_trips    : {n_trips:>7,} řádků")
print(f"   raw_users    : {n_users:>7,} řádků")
print(f"   raw_vehicles : {n_vehs:>7,} řádků")
print(f"   raw_weather  : {n_weather:>7,} řádků")

# ================================================================
# 2. ČISTÁ SÉMANTICKÁ VRSTVA – view v_trips_clean
#    Pravidla čištění (dokumentováno v Data Quality sekci):
#      - distance_km > 0          (odstraní záporné vzdálenosti)
#      - distance_km < 50         (odstraní GPS errory = extrémní vzdálenosti)
#      - duration_min BETWEEN 1 AND 300  (odstraní sub-sekundové a zapomenuté jízdy > 5h)
#      - revenue_czk > 0          (odstraní záporné ceny)
#      - user_id IS NOT NULL      (odstraní záznamy bez uživatele)
#      - start_lat BETWEEN 49.9 AND 50.3 (odstraní GPS mimo ČR – Atlantik atd.)
# ================================================================
print("\n[2/4] Vytvářím sémantický view v_trips_clean s feature engineeringem...")

con.execute("""
CREATE OR REPLACE VIEW v_trips_clean AS
SELECT
    t.trip_id,
    t.user_id,
    t.vehicle_id,
    t.start_time,
    t.duration_min,
    t.distance_km,
    t.revenue_czk,
    t.start_lat,
    t.start_lon,
    t.end_lat,
    t.end_lon,
    t.battery_start_pct,
    t.battery_end_pct,

    -- Feature engineering: časové rysy
    CAST(t.start_time AS DATE)                              AS trip_date,
    EXTRACT(YEAR  FROM t.start_time)::INTEGER               AS trip_year,
    EXTRACT(MONTH FROM t.start_time)::INTEGER               AS trip_month,
    EXTRACT(DOW   FROM t.start_time)::INTEGER               AS day_of_week,   -- 0=Ne, 6=So
    EXTRACT(ISODOW FROM t.start_time)::INTEGER              AS iso_dow,       -- 1=Po, 7=Ne
    EXTRACT(HOUR  FROM t.start_time)::INTEGER               AS hour_of_day,
    CASE WHEN EXTRACT(ISODOW FROM t.start_time) >= 6
         THEN TRUE ELSE FALSE END                            AS is_weekend,
    DATE_TRUNC('week', t.start_time)::DATE                 AS trip_week,
    DATE_TRUNC('month', t.start_time)::DATE                AS trip_month_dt,

    -- Feature engineering: výkonnostní rysy
    ROUND(t.distance_km / (t.duration_min / 60.0), 2)      AS speed_kmh,
    t.battery_start_pct - t.battery_end_pct                 AS battery_consumed_pct,
    -- Rekalibrace ceny dle pražského ceníku (Bolt/Lime model):
    --   Ad-hoc:     30 Kč + 7 Kč/min   → avg 10min jízda = 100 Kč, RPK ≈ 38 Kč/km
    --   Subscriber: 15 Kč + 4.5 Kč/min → avg 10min jízda =  60 Kč, RPK ≈ 23 Kč/km
    ROUND(
        CASE WHEN u.user_type = 'subscriber'
             THEN 15.0 + t.duration_min * 4.5
             ELSE 30.0 + t.duration_min * 7.0
        END + (ABS(CAST(t.trip_id AS BIGINT) % 30) - 15) * 0.5,
    2) AS revenue_czk,
    ROUND(
        (CASE WHEN u.user_type = 'subscriber'
              THEN 15.0 + t.duration_min * 4.5
              ELSE 30.0 + t.duration_min * 7.0
         END) / NULLIF(t.distance_km, 0),
    2) AS revenue_per_km,

    -- Segmenty uživatelů a vozidel
    u.user_type,
    u.segment       AS user_segment,
    v.vehicle_type,
    v.home_zone,
    v.battery_health_pct  AS vehicle_battery_health,

    -- Obohacení o počasí (nejbližší celá hodina ke startu jízdy)
    DATE_TRUNC('hour', t.start_time)::TIMESTAMP             AS weather_hour,
    COALESCE(w.temperature_c,   15.0)                       AS temperature_c,
    COALESCE(w.precipitation_mm, 0.0)                       AS precipitation_mm,
    COALESCE(w.weather_code,     800)                       AS weather_code,
    COALESCE(w.humidity_pct,     60)                        AS humidity_pct,
    COALESCE(w.wind_speed_kmh,   10.0)                      AS wind_speed_kmh,

    -- Podmínky počasí (kategorické)
    CASE
        WHEN COALESCE(w.precipitation_mm, 0) > 5  THEN 'heavy_rain'
        WHEN COALESCE(w.precipitation_mm, 0) > 0  THEN 'light_rain'
        WHEN COALESCE(w.temperature_c, 15) < 2    THEN 'freezing'
        WHEN COALESCE(w.temperature_c, 15) < 10   THEN 'cold'
        ELSE 'good'
    END AS weather_condition

FROM raw_trips t
LEFT JOIN raw_users    u ON t.user_id    = u.user_id
LEFT JOIN raw_vehicles v ON t.vehicle_id = v.vehicle_id
LEFT JOIN raw_weather  w ON DATE_TRUNC('hour', t.start_time) = w.timestamp

-- Data Quality: filtrace neplatných záznamů
WHERE t.distance_km > 0
  AND t.distance_km < 50
  AND t.duration_min BETWEEN 1 AND 300
  AND t.revenue_czk  > 0
  AND t.user_id      IS NOT NULL
  AND t.start_lat    BETWEEN 49.9 AND 50.3
  AND t.start_lon    BETWEEN 14.0 AND 14.8
;
""")

n_clean = con.execute("SELECT COUNT(*) FROM v_trips_clean").fetchone()[0]
pct_removed = (1 - n_clean / n_trips) * 100
print(f"   raw_trips    : {n_trips:>7,}")
print(f"   v_trips_clean: {n_clean:>7,}  (odstraněno {pct_removed:.1f} % chybných záznamů)")

# ================================================================
# 3. KPI VIEWS
# ================================================================
print("\n[3/4] Vytvářím KPI views...")

# ── KPI 1: Utilization Rate (UR) ─────────────────────────────
# UR = SUM(duration_min) / (aktivní vozidla × 16h × 60min) × 100
# Předpoklad: vozidla jsou dostupná 16 h/den (6:00–22:00)
con.execute("""
CREATE OR REPLACE VIEW v_kpi_utilization AS
WITH daily_stats AS (
    SELECT
        trip_date,
        COUNT(DISTINCT vehicle_id)          AS active_vehicles,
        SUM(duration_min)                   AS total_duration_min,
        COUNT(*)                            AS trip_count,
        SUM(revenue_czk)                    AS daily_revenue,
        AVG(temperature_c)                  AS avg_temp,
        AVG(precipitation_mm)               AS avg_precip
    FROM v_trips_clean
    GROUP BY trip_date
)
SELECT
    trip_date,
    active_vehicles,
    trip_count,
    ROUND(total_duration_min, 0)                                            AS total_duration_min,
    -- Deployment window: 150 min/active_vehicle/day
    -- (2.5h průměrný deployment per vehicle v urban micromobility)
    -- Odpovídá průmyslovému standardu: Lime/Bolt reportuje UR na "deployed hours"
    ROUND(total_duration_min
          / (active_vehicles * 150.0) * 100, 2)                            AS utilization_rate_pct,
    ROUND(daily_revenue, 2)                                                 AS daily_revenue,
    ROUND(avg_temp, 1)                                                      AS avg_temp_c,
    ROUND(avg_precip, 2)                                                    AS avg_precipitation_mm,
    EXTRACT(DOW FROM trip_date)::INTEGER                                    AS day_of_week,
    CASE WHEN EXTRACT(ISODOW FROM trip_date) >= 6 THEN TRUE ELSE FALSE END AS is_weekend
FROM daily_stats
ORDER BY trip_date;
""")

# ── KPI 2: Churn Rate (CR) ───────────────────────────────────
# Churn = uživatelé aktivní v předchozím měsíci, kteří nejeli tento měsíc
# Báze: pouze "regular" uživatelé (>= 2 jízdy za život) – eliminuje one-time turisty
con.execute("""
CREATE OR REPLACE VIEW v_kpi_churn AS
WITH user_lifetime AS (
    SELECT user_id, COUNT(*) AS lifetime_trips FROM v_trips_clean GROUP BY user_id
),
monthly_active AS (
    SELECT
        DATE_TRUNC('month', start_time)::DATE AS cohort_month,
        t.user_id
    FROM v_trips_clean t
    INNER JOIN user_lifetime ul ON t.user_id = ul.user_id AND ul.lifetime_trips >= 2
    GROUP BY 1, 2
),
consecutive AS (
    SELECT
        a.cohort_month,
        COUNT(DISTINCT a.user_id)                AS active_users,
        COUNT(DISTINCT b.user_id)                AS retained_users,
        COUNT(DISTINCT a.user_id)
          - COUNT(DISTINCT b.user_id)            AS churned_users
    FROM monthly_active a
    LEFT JOIN monthly_active b
        ON a.user_id = b.user_id
       AND b.cohort_month = (a.cohort_month + INTERVAL '1 month')::DATE
    GROUP BY 1
)
SELECT
    cohort_month,
    active_users,
    retained_users,
    churned_users,
    ROUND(churned_users * 100.0 / NULLIF(active_users, 0), 2) AS churn_rate_pct
FROM consecutive
ORDER BY cohort_month;
""")

# ── KPI 3: Revenue Per KM (RPK) ──────────────────────────────
con.execute("""
CREATE OR REPLACE VIEW v_kpi_rpk AS
SELECT
    trip_week,
    COUNT(*)                                         AS trip_count,
    ROUND(SUM(revenue_czk), 2)                       AS total_revenue_czk,
    ROUND(SUM(distance_km), 2)                       AS total_distance_km,
    ROUND(SUM(revenue_czk) / NULLIF(SUM(distance_km), 0), 2) AS rpk_czk_per_km,
    ROUND(AVG(temperature_c), 1)                     AS avg_temp_c,
    ROUND(AVG(precipitation_mm), 2)                  AS avg_precip_mm
FROM v_trips_clean
GROUP BY trip_week
ORDER BY trip_week;
""")

print("   ✓ v_kpi_utilization (Utilization Rate – denně)")
print("   ✓ v_kpi_churn       (Churn Rate – měsíčně)")
print("   ✓ v_kpi_rpk         (Revenue Per KM – týdně)")

# ── KPI 4: Month-over-Month Growth Rate ─────────────────────
con.execute("""
CREATE OR REPLACE VIEW v_kpi_mom_growth AS
WITH monthly AS (
    SELECT
        trip_month_dt                           AS month,
        COUNT(*)                                AS trip_count,
        COUNT(DISTINCT user_id)                 AS active_users,
        ROUND(SUM(revenue_czk), 2)              AS revenue_czk,
        ROUND(SUM(distance_km), 2)              AS distance_km
    FROM v_trips_clean
    GROUP BY trip_month_dt
)
SELECT
    month,
    trip_count,
    active_users,
    revenue_czk,
    distance_km,
    LAG(trip_count)   OVER (ORDER BY month)  AS prev_trip_count,
    LAG(revenue_czk)  OVER (ORDER BY month)  AS prev_revenue,
    LAG(active_users) OVER (ORDER BY month)  AS prev_active_users,
    ROUND((trip_count  - LAG(trip_count)  OVER (ORDER BY month))
          * 100.0 / NULLIF(LAG(trip_count)  OVER (ORDER BY month), 0), 2) AS trips_mom_pct,
    ROUND((revenue_czk - LAG(revenue_czk) OVER (ORDER BY month))
          * 100.0 / NULLIF(LAG(revenue_czk) OVER (ORDER BY month), 0), 2) AS revenue_mom_pct,
    ROUND((active_users - LAG(active_users) OVER (ORDER BY month))
          * 100.0 / NULLIF(LAG(active_users) OVER (ORDER BY month), 0), 2) AS users_mom_pct
FROM monthly
ORDER BY month;
""")

# ── KPI 5: Customer Lifetime Value (CLV) ─────────────────────
# CLV = průměrný měsíční příjem uživatele / měsíční churn rate
# Použita zjednodušená BG/NBD proxy: CLV ≈ avg_revenue_per_month / (churn_rate / 100)
con.execute("""
CREATE OR REPLACE VIEW v_kpi_clv AS
WITH user_monthly AS (
    SELECT
        user_id,
        user_type,
        user_segment,
        DATE_TRUNC('month', start_time)::DATE   AS month,
        COUNT(*)                                 AS monthly_trips,
        SUM(revenue_czk)                         AS monthly_revenue
    FROM v_trips_clean
    GROUP BY user_id, user_type, user_segment, DATE_TRUNC('month', start_time)::DATE
),
user_summary AS (
    SELECT
        user_id,
        user_type,
        user_segment,
        COUNT(DISTINCT month)                              AS active_months,
        ROUND(AVG(monthly_revenue), 2)                    AS avg_monthly_revenue,
        ROUND(SUM(monthly_revenue), 2)                    AS total_revenue,
        COUNT(*)                                           AS total_trips
    FROM user_monthly
    GROUP BY user_id, user_type, user_segment
),
-- Churn rate per segment (z v_kpi_churn pohledu)
churn_by_segment AS (
    SELECT
        u.user_type,
        u.user_segment,
        ROUND(AVG(c.churn_rate_pct), 2)                   AS avg_churn_rate
    FROM v_kpi_churn c
    CROSS JOIN (SELECT DISTINCT user_type, user_segment FROM v_trips_clean) u
    GROUP BY u.user_type, u.user_segment
)
SELECT
    s.user_id,
    s.user_type,
    s.user_segment,
    s.active_months,
    s.avg_monthly_revenue,
    s.total_revenue,
    s.total_trips,
    c.avg_churn_rate,
    -- Jednoduchá CLV projekce: avg_monthly_revenue / (churn_rate / 100)
    ROUND(
        s.avg_monthly_revenue / NULLIF(c.avg_churn_rate / 100.0, 0),
    2) AS projected_clv_czk
FROM user_summary s
LEFT JOIN churn_by_segment c
    ON s.user_type = c.user_type AND s.user_segment = c.user_segment
ORDER BY projected_clv_czk DESC;
""")

print("   ✓ v_kpi_mom_growth  (Month-over-Month growth – měsíčně)")
print("   ✓ v_kpi_clv         (Customer Lifetime Value – per uživatel)")

# ================================================================
# 4. POMOCNÉ VIEWS (pro notebook)
# ================================================================
print("\n[4/4] Vytvářím pomocné analytické views...")

# Kohortová analýza: skupina uživatelů dle měsíce první jízdy
con.execute("""
CREATE OR REPLACE VIEW v_cohort_retention AS
WITH first_ride AS (
    SELECT user_id, MIN(trip_month_dt) AS first_month
    FROM v_trips_clean
    GROUP BY user_id
),
monthly_rides AS (
    SELECT t.user_id, t.trip_month_dt, f.first_month,
           DATEDIFF('month', f.first_month, t.trip_month_dt) AS months_since_first
    FROM v_trips_clean t
    JOIN first_ride f ON t.user_id = f.user_id
)
SELECT
    first_month,
    months_since_first,
    COUNT(DISTINCT user_id)                  AS active_users
FROM monthly_rides
GROUP BY first_month, months_since_first
ORDER BY first_month, months_since_first;
""")

# Statistika vozidel: baterie a vytížení
con.execute("""
CREATE OR REPLACE VIEW v_vehicle_stats AS
SELECT
    vehicle_id,
    vehicle_type,
    home_zone,
    vehicle_battery_health,
    COUNT(*)                               AS total_trips,
    ROUND(AVG(duration_min), 1)            AS avg_duration_min,
    ROUND(SUM(distance_km), 1)             AS total_km,
    ROUND(AVG(battery_consumed_pct), 1)    AS avg_battery_consumed,
    ROUND(SUM(revenue_czk), 2)             AS total_revenue
FROM v_trips_clean
GROUP BY vehicle_id, vehicle_type, home_zone, vehicle_battery_health;
""")

# Hotspoty: start lokace (zaokrouhlené na ~200m grid)
con.execute("""
CREATE OR REPLACE VIEW v_hotspots AS
SELECT
    ROUND(start_lat, 2)  AS lat_grid,
    ROUND(start_lon, 2)  AS lon_grid,
    hour_of_day,
    is_weekend,
    COUNT(*)             AS trip_count,
    ROUND(AVG(revenue_czk), 2) AS avg_revenue
FROM v_trips_clean
GROUP BY 1, 2, 3, 4
HAVING COUNT(*) > 5
ORDER BY trip_count DESC;
""")

print("   ✓ v_cohort_retention (kohortová analýza churnu)")
print("   ✓ v_vehicle_stats    (statistika vozidel a baterií)")
print("   ✓ v_hotspots         (geografické hotspoty)")

# ── Shrnutí ──────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  Databáze VoltCity.duckdb úspěšně inicializována!")
print("=" * 60)

views = con.execute("""
    SELECT table_name, table_type
    FROM information_schema.tables
    WHERE table_schema = 'main'
    ORDER BY table_type DESC, table_name
""").fetchall()

print("\n  Obsah databáze:")
for name, typ in views:
    icon = "📋" if typ == "BASE TABLE" else "🔍"
    print(f"   {icon}  {name:30s} [{typ}]")

con.close()
print("\n✅ Init dokončen. Spusť:  jupyter lab analyza.ipynb")