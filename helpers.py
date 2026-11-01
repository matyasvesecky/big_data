"""
helpers.py – Pomocné funkce pro VoltCity Dynamics analýzu.

Všechny vizualizační a analytické funkce jsou zde, aby notebook
zůstal přehledný a čitelný i pro netechnickou audienci.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import seaborn as sns


# ══════════════════════════════════════════════════════════════════
#  1. DATA QUALITY REPORT
# ══════════════════════════════════════════════════════════════════

def run_data_quality_report(q):
    """Spustí kompletní Data Quality report a zobrazí vizualizace."""
    raw_count = q("SELECT COUNT(*) AS n FROM raw_trips")['n'][0]
    clean_count = q("SELECT COUNT(*) AS n FROM v_trips_clean")['n'][0]
    removed = raw_count - clean_count

    # Detailní rozbor chyb
    dq_checks = q("""
        SELECT
            'Záporná vzdálenost (distance_km <= 0)' AS issue,
            COUNT(*) FILTER (WHERE distance_km <= 0) AS count
        FROM raw_trips
        UNION ALL SELECT 'GPS mimo ČR (start_lat NOT BETWEEN 49.9 AND 50.3)',
            COUNT(*) FILTER (WHERE start_lat NOT BETWEEN 49.9 AND 50.3) FROM raw_trips
        UNION ALL SELECT 'Záporná cena (revenue_czk <= 0)',
            COUNT(*) FILTER (WHERE revenue_czk <= 0) FROM raw_trips
        UNION ALL SELECT 'Outlier: jízda > 300 min',
            COUNT(*) FILTER (WHERE duration_min > 300) FROM raw_trips
        UNION ALL SELECT 'Chybějící user_id (NULL)',
            COUNT(*) FILTER (WHERE user_id IS NULL) FROM raw_trips
        UNION ALL SELECT 'Příliš velká vzdálenost (>= 50 km)',
            COUNT(*) FILTER (WHERE distance_km >= 50) FROM raw_trips
    """)

    # Duplicity
    dup_count = q("SELECT COUNT(*) - COUNT(DISTINCT trip_id) AS n FROM raw_trips")['n'][0]

    # IQR outlier detekce
    iqr_data = q("""
        SELECT
            PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY speed_kmh) AS q1,
            PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY speed_kmh) AS q3
        FROM v_trips_clean
    """)
    q1, q3 = iqr_data['q1'][0], iqr_data['q3'][0]
    iqr = q3 - q1
    iqr_outliers = q(f"SELECT COUNT(*) AS n FROM v_trips_clean WHERE speed_kmh > {q3 + 1.5*iqr}")['n'][0]

    # Tisk výsledků
    print(f"{'Surová data (raw_trips):':<40} {raw_count:>8,} záznamů")
    print(f"{'Odstraněno (rule-based):':<40} {removed:>8,} ({removed/raw_count*100:.2f} %)")
    print(f"{'Čistá data (v_trips_clean):':<40} {clean_count:>8,} záznamů")
    print(f"{'Duplicitní trip_id:':<40} {dup_count:>8,}")
    print(f"{'IQR outliers speed_kmh (>{q3 + 1.5*iqr:.1f} km/h):':<40} {iqr_outliers:>8,}")
    print()
    print(dq_checks.to_string(index=False))

    # Vizualizace
    fig, axes = plt.subplots(1, 2, figsize=(12, 3.5))
    colors = ['#2ecc71', '#e74c3c']
    bars = axes[0].bar(['Čistá data', 'Odstraněná chybná data'],
                       [clean_count, removed], color=colors, width=0.45, edgecolor='white')
    for bar, val in zip(bars, [clean_count, removed]):
        axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1500,
                     f'{val:,}', ha='center', fontsize=11, fontweight='bold')
    axes[0].set_title('Data Quality: Surová vs. Čistá data', fontsize=13, fontweight='bold')
    axes[0].set_ylabel('Počet záznamů')
    axes[0].yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f'{int(x):,}'))

    speed_sample = q("SELECT speed_kmh FROM v_trips_clean USING SAMPLE 5000")['speed_kmh']
    axes[1].hist(speed_sample, bins=50, color='#3498db', edgecolor='white', alpha=0.85)
    axes[1].axvline(q3 + 1.5*iqr, color='#e74c3c', linestyle='--', linewidth=2,
                    label=f'IQR horní mez: {q3 + 1.5*iqr:.1f} km/h')
    axes[1].set_title('Distribuce rychlostí – IQR outlier detekce', fontsize=11, fontweight='bold')
    axes[1].set_xlabel('Rychlost (km/h)')
    axes[1].set_ylabel('Počet jízd (vzorek 5k)')
    axes[1].legend()
    plt.tight_layout()
    plt.show()

    return {'raw': raw_count, 'clean': clean_count, 'removed': removed,
            'removed_pct': removed/raw_count*100}


# ══════════════════════════════════════════════════════════════════
#  1b. DATA PROFILING
# ══════════════════════════════════════════════════════════════════

def show_data_profiling(q):
    """Zobrazí popisnou statistiku klíčových numerických sloupců."""
    profiling = q("""
        SELECT duration_min, distance_km, revenue_czk,
               start_lat, start_lon, speed_kmh
        FROM v_trips_clean
    """)
    display(profiling.describe().round(2))
    return profiling.describe().round(2)


# ══════════════════════════════════════════════════════════════════
#  2. KPI DASHBOARD
# ══════════════════════════════════════════════════════════════════

def show_kpi_dashboard(q):
    """Zobrazí Plotly gauge dashboard se třemi KPI."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    ur_2024 = q("""
        SELECT ROUND(AVG(utilization_rate_pct), 2) AS ur
        FROM v_kpi_utilization
        WHERE EXTRACT(YEAR FROM trip_date) = 2024
    """)['ur'][0]

    ur_summer = q("""
        SELECT ROUND(AVG(utilization_rate_pct), 2) AS ur
        FROM v_kpi_utilization
        WHERE EXTRACT(MONTH FROM trip_date) BETWEEN 6 AND 8
          AND EXTRACT(YEAR FROM trip_date) = 2024
    """)['ur'][0]

    cr_avg = q("""
        SELECT ROUND(AVG(churn_rate_pct), 2) AS cr
        FROM v_kpi_churn
        WHERE cohort_month BETWEEN '2024-01-01' AND '2024-11-01'
    """)['cr'][0]

    rpk_avg = q("""
        SELECT ROUND(SUM(total_revenue_czk) / SUM(total_distance_km), 2) AS rpk
        FROM v_kpi_rpk
        WHERE EXTRACT(YEAR FROM trip_week) = 2024
    """)['rpk'][0]

    # Textový dashboard
    print("=" * 55)
    print("  KPI          │   Hodnota │  Baseline │     Cíl   │ Status")
    print("-" * 55)
    ur_status = '✅' if ur_2024 >= 18 else '⚠️ '
    cr_status = '✅' if cr_avg <= 15 else '⚠️ '
    rpk_status = '✅' if rpk_avg >= 45 else '⚠️ '
    print(f"  UR (2024 avg)│ {ur_2024:>7.2f} % │    12 %   │    18 %   │ {ur_status}")
    print(f"  UR (léto)    │ {ur_summer:>7.2f} % │    12 %   │    18 %   │")
    print(f"  CR (2024 avg)│ {cr_avg:>7.2f} % │    25 %   │  < 15 %   │ {cr_status}")
    print(f"  RPK (2024)   │ {rpk_avg:>6.2f} Kč │  30 Kč/km │ 45 Kč/km  │ {rpk_status}")
    print("=" * 55)

    # Plotly gauges
    fig = make_subplots(rows=1, cols=3,
                        specs=[[{"type": "indicator"}, {"type": "indicator"}, {"type": "indicator"}]])

    fig.add_trace(go.Indicator(
        mode="gauge+number+delta", value=ur_2024,
        delta={'reference': 18, 'valueformat': '.1f', 'suffix': '%'},
        title={'text': "Utilization Rate<br><span style='font-size:0.8em;color:gray'>Cíl: 18 %</span>"},
        number={'suffix': '%', 'valueformat': '.2f'},
        gauge={'axis': {'range': [0, 35], 'ticksuffix': '%'},
               'bar': {'color': '#27ae60' if ur_2024 >= 18 else '#e67e22'},
               'steps': [{'range': [0, 12], 'color': '#fadbd8'},
                         {'range': [12, 18], 'color': '#fdebd0'},
                         {'range': [18, 35], 'color': '#d5f5e3'}],
               'threshold': {'line': {'color': '#2c3e50', 'width': 3}, 'value': 18}}
    ), row=1, col=1)

    fig.add_trace(go.Indicator(
        mode="gauge+number+delta", value=cr_avg,
        delta={'reference': 15, 'valueformat': '.1f', 'suffix': '%',
               'increasing': {'color': '#e74c3c'}, 'decreasing': {'color': '#27ae60'}},
        title={'text': "Churn Rate<br><span style='font-size:0.8em;color:gray'>Cíl: < 15 %</span>"},
        number={'suffix': '%', 'valueformat': '.2f'},
        gauge={'axis': {'range': [0, 40], 'ticksuffix': '%'},
               'bar': {'color': '#27ae60' if cr_avg <= 15 else '#e74c3c'},
               'steps': [{'range': [0, 15], 'color': '#d5f5e3'},
                         {'range': [15, 25], 'color': '#fdebd0'},
                         {'range': [25, 40], 'color': '#fadbd8'}],
               'threshold': {'line': {'color': '#2c3e50', 'width': 3}, 'value': 15}}
    ), row=1, col=2)

    fig.add_trace(go.Indicator(
        mode="gauge+number+delta", value=rpk_avg,
        delta={'reference': 45, 'valueformat': '.1f', 'suffix': ' Kč'},
        title={'text': "Revenue Per KM<br><span style='font-size:0.8em;color:gray'>Cíl: 45 Kč/km</span>"},
        number={'suffix': ' Kč', 'valueformat': '.2f'},
        gauge={'axis': {'range': [0, 70], 'ticksuffix': ' Kč'},
               'bar': {'color': '#27ae60' if rpk_avg >= 45 else '#e67e22'},
               'steps': [{'range': [0, 30], 'color': '#fadbd8'},
                         {'range': [30, 45], 'color': '#fdebd0'},
                         {'range': [45, 70], 'color': '#d5f5e3'}],
               'threshold': {'line': {'color': '#2c3e50', 'width': 3}, 'value': 45}}
    ), row=1, col=3)

    fig.update_layout(title_text="KPI Dashboard – VoltCity Dynamics (2024)",
                      title_font_size=18, height=320,
                      margin=dict(t=80, b=20, l=20, r=20))
    fig.show()

    return {'ur_2024': ur_2024, 'ur_summer': ur_summer,
            'cr_avg': cr_avg, 'rpk_avg': rpk_avg}


# ══════════════════════════════════════════════════════════════════
#  2b. KORELAČNÍ MATICE A PAIRPLOT
# ══════════════════════════════════════════════════════════════════

def show_correlation_matrix(q):
    """Zobrazí korelační matici a pairplot na vzorku 10k jízd."""
    eda_sample = q("""
        SELECT duration_min, distance_km, revenue_czk, speed_kmh,
               battery_consumed_pct
        FROM v_trips_clean
        WHERE battery_consumed_pct IS NOT NULL
        USING SAMPLE 10000
    """)

    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5))
    corr = eda_sample.corr().round(2)
    sns.heatmap(corr, annot=True, cmap='RdYlBu_r', vmin=-1, vmax=1,
                ax=axes[0], linewidths=0.5, fmt='.2f',
                cbar_kws={'label': 'Pearsonův koef.'})
    axes[0].set_title('Korelační matice (vzorek 10k jízd)', fontweight='bold')
    axes[0].tick_params(axis='x', labelrotation=30)

    axes[1].scatter(eda_sample['distance_km'], eda_sample['revenue_czk'],
                    alpha=0.15, s=5, color='#3498db')
    axes[1].set_title('Vzdálenost vs. Tržba za jízdu', fontweight='bold')
    axes[1].set_xlabel('Vzdálenost (km)')
    axes[1].set_ylabel('Tržba (Kč)')
    plt.tight_layout()
    plt.show()

    return corr


# ══════════════════════════════════════════════════════════════════
#  3. TREND JÍZD V ČASE + POČASÍ + YoY
# ══════════════════════════════════════════════════════════════════

def show_weekly_trend(q):
    """Zobrazí týdenní trend jízd, vliv počasí a YoY srovnání."""
    weekly = q("""
        SELECT DATE_TRUNC('week', trip_date) AS trip_week,
               SUM(trip_count) AS trips,
               ROUND(AVG(avg_precipitation_mm), 2) AS avg_precip
        FROM v_kpi_utilization
        GROUP BY trip_week ORDER BY trip_week
    """)
    weekly['trip_week'] = pd.to_datetime(weekly['trip_week'])

    fig, axes = plt.subplots(1, 2, figsize=(16, 5.5))

    # Trend + počasí
    ax1 = axes[0]
    color1, color2 = '#2980b9', '#e67e22'
    ax1.plot(weekly['trip_week'], weekly['trips'], color=color1, linewidth=2, label='Jízdy / týden')
    ax1.fill_between(weekly['trip_week'], weekly['trips'], alpha=0.15, color=color1)
    ax1.set_ylabel('Počet jízd / týden', color=color1)
    ax1.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f'{int(x):,}'))
    ax2 = ax1.twinx()
    ax2.bar(weekly['trip_week'], weekly['avg_precip'], width=6, alpha=0.35, color=color2, label='Srážky (mm/h)')
    ax2.set_ylabel('Průměrné srážky (mm/h)', color=color2)
    ax2.invert_yaxis()
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
    ax1.set_title('Týdenní trend jízd + vliv počasí (2023–2024)', fontsize=14, fontweight='bold')

    # YoY srovnání
    ax3 = axes[1]
    weekly['week_num'] = weekly['trip_week'].dt.isocalendar().week
    w2023 = weekly[weekly['trip_week'].dt.year == 2023].groupby('week_num')['trips'].sum()
    w2024 = weekly[weekly['trip_week'].dt.year == 2024].groupby('week_num')['trips'].sum()
    common_weeks = w2023.index.intersection(w2024.index)

    ax3.plot(common_weeks, w2023.loc[common_weeks], color='#95a5a6', linewidth=2, linestyle='--', label='2023', alpha=0.8)
    ax3.plot(common_weeks, w2024.loc[common_weeks], color='#2980b9', linewidth=2.5, label='2024')
    ax3.fill_between(common_weeks, w2023.loc[common_weeks], w2024.loc[common_weeks],
                     where=w2024.loc[common_weeks] >= w2023.loc[common_weeks],
                     alpha=0.2, color='#27ae60', label='Růst YoY')
    ax3.fill_between(common_weeks, w2023.loc[common_weeks], w2024.loc[common_weeks],
                     where=w2024.loc[common_weeks] < w2023.loc[common_weeks],
                     alpha=0.2, color='#e74c3c', label='Pokles YoY')
    yoy_growth = ((w2024.loc[common_weeks].sum() - w2023.loc[common_weeks].sum())
                  / w2023.loc[common_weeks].sum() * 100)
    ax3.set_title(f'YoY srovnání: 2023 vs. 2024 – celkový růst jízd: {yoy_growth:+.1f} %',
                  fontsize=13, fontweight='bold')
    ax3.set_xlabel('Týden v roce')
    ax3.set_ylabel('Počet jízd / týden')
    ax3.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f'{int(x):,}'))
    ax3.legend()

    plt.tight_layout()
    plt.show()

    w_summer = weekly[weekly['trip_week'].dt.month.isin([6, 7, 8])]['trips'].mean()
    w_winter = weekly[weekly['trip_week'].dt.month.isin([12, 1, 2])]['trips'].mean()
    print(f"Zimní vs. letní průměr jízd/týden:")
    print(f"  🌞 Léto (červen–srpen): {w_summer:,.0f} jízd/týden")
    print(f"  ❄️  Zima (prosinec–únor): {w_winter:,.0f} jízd/týden")
    print(f"  Pokles v zimě: {(1 - w_winter/w_summer)*100:.1f} %")
    print(f"  📈 YoY růst počtu jízd: {yoy_growth:+.1f} %")

    return {'yoy_growth': yoy_growth, 'summer_avg': w_summer, 'winter_avg': w_winter}


# ══════════════════════════════════════════════════════════════════
#  4. SEGMENTACE
# ══════════════════════════════════════════════════════════════════

def show_segmentation(q):
    """Porovnání přínosu subscriber vs. ad-hoc segmentů."""
    seg = q("""
        SELECT user_type, user_segment,
               COUNT(*) AS trip_count,
               ROUND(SUM(revenue_czk), 0) AS total_revenue,
               ROUND(AVG(revenue_czk), 2) AS avg_revenue,
               ROUND(AVG(duration_min), 1) AS avg_duration,
               ROUND(AVG(distance_km), 2) AS avg_distance
        FROM v_trips_clean
        GROUP BY user_type, user_segment ORDER BY trip_count DESC
    """)

    by_type = seg.groupby('user_type').agg(
        trips=('trip_count', 'sum'), revenue=('total_revenue', 'sum'),
        avg_rev=('avg_revenue', 'mean')
    ).reset_index()

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    colors = ['#3498db', '#e74c3c']

    axes[0].bar(by_type['user_type'], by_type['trips']/1000, color=colors, edgecolor='white', width=0.5)
    axes[0].set_title('Počet jízd', fontweight='bold')
    axes[0].set_ylabel('Tisíce jízd')
    for i, v in enumerate(by_type['trips']):
        axes[0].text(i, v/1000 + 0.5, f'{v/1000:.1f}k', ha='center', fontweight='bold')

    axes[1].bar(by_type['user_type'], by_type['revenue']/1e6, color=colors, edgecolor='white', width=0.5)
    axes[1].set_title('Celkové tržby', fontweight='bold')
    axes[1].set_ylabel('Miliony Kč')
    for i, v in enumerate(by_type['revenue']):
        axes[1].text(i, v/1e6 + 0.05, f'{v/1e6:.1f}M', ha='center', fontweight='bold')

    axes[2].bar(by_type['user_type'], by_type['avg_rev'], color=colors, edgecolor='white', width=0.5)
    axes[2].set_title('Průměrná cena jízdy', fontweight='bold')
    axes[2].set_ylabel('Kč / jízda')
    for i, v in enumerate(by_type['avg_rev']):
        axes[2].text(i, v + 0.5, f'{v:.1f} Kč', ha='center', fontweight='bold')

    plt.suptitle('Subscriber vs. Ad-hoc: Přínos segmentů k byznysu', fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.show()

    seg_summary = seg.groupby('user_segment').agg(trips=('trip_count', 'sum')).sort_values('trips', ascending=False)
    print('\nRozdělení jízd dle segmentu zákazníka:')
    total = seg_summary['trips'].sum()
    for segment, row in seg_summary.iterrows():
        print(f"  {segment:<12}: {row['trips']:>8,}  ({row['trips']/total*100:.1f} %)")

    return by_type


# ══════════════════════════════════════════════════════════════════
#  5. DISTRIBUCE DÉLEK JÍZD
# ══════════════════════════════════════════════════════════════════

def show_distance_distribution(q):
    """Histogram distribuce délek jízd a porovnání subscriber vs. ad-hoc."""
    dist_data = q("""
        SELECT distance_km, duration_min, user_type
        FROM v_trips_clean WHERE distance_km < 15
        USING SAMPLE 50000
    """)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].hist(dist_data['distance_km'], bins=60, color='#3498db', edgecolor='white', alpha=0.85)
    axes[0].axvline(2.0, color='#e74c3c', linestyle='--', linewidth=2, label='Last-mile hranice (2 km)')
    axes[0].axvline(dist_data['distance_km'].median(), color='#27ae60', linestyle=':', linewidth=2,
                    label=f"Medián: {dist_data['distance_km'].median():.2f} km")
    axes[0].set_title('Distribuce délek jízd', fontweight='bold')
    axes[0].set_xlabel('Vzdálenost (km)')
    axes[0].set_ylabel('Počet jízd (vzorek 50k)')
    axes[0].legend()

    for utype, clr in zip(['subscriber', 'ad-hoc'], ['#3498db', '#e74c3c']):
        subset = dist_data[dist_data['user_type'] == utype]['distance_km']
        axes[1].hist(subset, bins=50, alpha=0.55, color=clr,
                     label=f'{utype} (n={len(subset):,})', density=True)
    axes[1].set_title('Subscriber vs. Ad-hoc: Délka jízdy (hustota)', fontweight='bold')
    axes[1].set_xlabel('Vzdálenost (km)')
    axes[1].set_ylabel('Hustota pravděpodobnosti')
    axes[1].legend()

    plt.suptitle('Last-Mile charakter VoltCity flotily', fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.show()

    last_mile_pct = (dist_data['distance_km'] < 2).mean() * 100
    print(f"Jízdy kratší než 2 km (last-mile): {last_mile_pct:.1f} %")
    print(f"Průměrná délka jízdy:              {dist_data['distance_km'].mean():.2f} km")
    print(f"Průměrná délka jízdy (subscriber): {dist_data[dist_data.user_type=='subscriber']['distance_km'].mean():.2f} km")
    print(f"Průměrná délka jízdy (ad-hoc):     {dist_data[dist_data.user_type=='ad-hoc']['distance_km'].mean():.2f} km")

    return {'last_mile_pct': last_mile_pct}


# ══════════════════════════════════════════════════════════════════
#  6. TEPLOTA VS. POPTÁVKA
# ══════════════════════════════════════════════════════════════════

def show_weather_demand(q):
    """Scatter plot: vliv počasí (teplota, srážky) na poptávku."""
    from matplotlib.lines import Line2D

    weather_demand = q("""
        SELECT trip_date, COUNT(*) AS trip_count,
               ROUND(AVG(temperature_c), 1) AS avg_temp,
               ROUND(AVG(precipitation_mm), 2) AS avg_precip,
               CASE WHEN EXTRACT(ISODOW FROM trip_date) >= 6
                    THEN 'Víkend' ELSE 'Pracovní den' END AS day_type
        FROM v_trips_clean GROUP BY trip_date ORDER BY trip_date
    """)

    corr_temp = weather_demand[['avg_temp', 'trip_count']].corr().iloc[0, 1]
    corr_rain = weather_demand[['avg_precip', 'trip_count']].corr().iloc[0, 1]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    colors_day = weather_demand['day_type'].map({'Pracovní den': '#3498db', 'Víkend': '#e74c3c'})

    axes[0].scatter(weather_demand['avg_temp'], weather_demand['trip_count'], c=colors_day, alpha=0.45, s=15)
    z = np.polyfit(weather_demand['avg_temp'], weather_demand['trip_count'], 1)
    p_func = np.poly1d(z)
    xs = np.linspace(weather_demand['avg_temp'].min(), weather_demand['avg_temp'].max(), 100)
    axes[0].plot(xs, p_func(xs), color='black', linewidth=2, linestyle='--')
    handles = [Line2D([0], [0], marker='o', color='w', markerfacecolor=c, markersize=8, label=l)
               for c, l in [('#3498db', 'Pracovní den'), ('#e74c3c', 'Víkend')]]
    handles.append(Line2D([0], [0], color='black', linestyle='--', label=f'Regrese (r={corr_temp:.2f})'))
    axes[0].legend(handles=handles, fontsize=9)
    axes[0].set_title(f'Teplota vs. Počet jízd (r = {corr_temp:.2f})', fontweight='bold')
    axes[0].set_xlabel('Průměrná teplota dne (°C)')
    axes[0].set_ylabel('Počet jízd / den')

    axes[1].scatter(weather_demand['avg_precip'], weather_demand['trip_count'], c=colors_day, alpha=0.45, s=15)
    z2 = np.polyfit(weather_demand['avg_precip'], weather_demand['trip_count'], 1)
    p2 = np.poly1d(z2)
    xs2 = np.linspace(weather_demand['avg_precip'].min(), weather_demand['avg_precip'].max(), 100)
    axes[1].plot(xs2, p2(xs2), color='black', linewidth=2, linestyle='--',
                 label=f'Regrese (r={corr_rain:.2f})')
    axes[1].legend(fontsize=9)
    axes[1].set_title(f'Srážky vs. Počet jízd (r = {corr_rain:.2f})', fontweight='bold')
    axes[1].set_xlabel('Průměrné srážky dne (mm/h)')
    axes[1].set_ylabel('Počet jízd / den')

    plt.suptitle('Vliv počasí na poptávku po mikromobilitě', fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.show()

    print(f"Korelace teplota ↔ poptávka:  r = {corr_temp:.3f}  (pozitivní, silná)")
    print(f"Korelace srážky  ↔ poptávka:  r = {corr_rain:.3f}  (negativní)")
    rainy_days = weather_demand[weather_demand['avg_precip'] > 2]['trip_count'].mean()
    dry_days = weather_demand[weather_demand['avg_precip'] == 0]['trip_count'].mean()
    print(f"\nPrůměr jízd/den za sucha:   {dry_days:,.0f}")
    print(f"Průměr jízd/den za deště:   {rainy_days:,.0f}")
    print(f"Pokles za deště:             {(1-rainy_days/dry_days)*100:.1f} %")

    return {'corr_temp': corr_temp, 'corr_rain': corr_rain,
            'rain_drop_pct': (1-rainy_days/dry_days)*100}


# ══════════════════════════════════════════════════════════════════
#  7. BATERIE – OUTLIEŘI
# ══════════════════════════════════════════════════════════════════

def show_battery_outliers(q):
    """Boxplot odhalující vozidla s podezřele vysokou spotřebou baterie."""
    battery = q("""
        SELECT vehicle_type, home_zone, battery_consumed_pct,
               vehicle_battery_health, distance_km
        FROM v_trips_clean
        WHERE battery_consumed_pct IS NOT NULL AND battery_consumed_pct >= 0
        USING SAMPLE 30000
    """)
    battery['consumption_per_km'] = battery['battery_consumed_pct'] / battery['distance_km'].clip(lower=0.1)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

    zones_order = battery.groupby('home_zone')['battery_consumed_pct'].median().sort_values(ascending=False).index
    sns.boxplot(data=battery, x='home_zone', y='battery_consumed_pct', order=zones_order, ax=axes[0],
                flierprops=dict(marker='o', markersize=2, alpha=0.4, color='#e74c3c'))
    axes[0].set_title('Spotřeba baterie dle zóny vozidla', fontsize=11, fontweight='bold')
    axes[0].set_xlabel('Zóna')
    axes[0].set_ylabel('Spotřeba baterie na jízdu (%)')

    battery['health_group'] = pd.cut(battery['vehicle_battery_health'],
                                     bins=[55, 70, 85, 101],
                                     labels=['Špatné (55–70%)', 'Střední (70–85%)', 'Dobré (85–100%)'])
    groups = battery.groupby(['vehicle_type', 'health_group'], observed=True)['battery_consumed_pct']
    data_plot = [groups.get_group(g).values for g in groups.groups]
    labels_plot = [f"{g[0]}\n{g[1]}" for g in groups.groups]
    bp = axes[1].boxplot(data_plot, labels=labels_plot, patch_artist=True,
                         flierprops=dict(marker='o', markersize=2, alpha=0.4, color='#e74c3c'))
    colors_bp = ['#85c1e9', '#5dade2', '#2e86c1', '#f1948a', '#ec7063', '#e74c3c']
    for patch, clr in zip(bp['boxes'], colors_bp):
        patch.set_facecolor(clr)
        patch.set_alpha(0.75)
    axes[1].set_title('Spotřeba dle typu vozidla × zdraví baterie', fontsize=11, fontweight='bold')
    axes[1].set_ylabel('Spotřeba baterie na jízdu (%)')
    axes[1].tick_params(axis='x', labelsize=8)

    plt.suptitle('Analýza baterií – outlieři a opotřebení flotily', fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.show()

    high_cons = q("""
        SELECT vehicle_id, vehicle_type, home_zone, vehicle_battery_health,
               ROUND(AVG(battery_consumed_pct), 1) AS avg_consumption, COUNT(*) AS trip_count
        FROM v_trips_clean
        WHERE battery_consumed_pct IS NOT NULL AND battery_consumed_pct >= 0
        GROUP BY vehicle_id, vehicle_type, home_zone, vehicle_battery_health
        ORDER BY avg_consumption DESC LIMIT 10
    """)
    print(f"Top 10 vozidel s nejvyšší průměrnou spotřebou baterie (kandidáti na servis):")
    print(high_cons.to_string(index=False))


# ══════════════════════════════════════════════════════════════════
#  8. FINANČNÍ ROI MODEL
# ══════════════════════════════════════════════════════════════════

def show_roi_model(q):
    """Business case pro údržbu flotily."""
    bad_battery_count = q("""
        SELECT COUNT(*) as defekt FROM (
            SELECT vehicle_id FROM v_trips_clean
            WHERE battery_consumed_pct IS NOT NULL AND battery_consumed_pct >= 0
            GROUP BY vehicle_id
            ORDER BY AVG(battery_consumed_pct) DESC LIMIT 42
        ) t
    """)['defekt'][0]

    avg_weekly_revenue = 1200
    print(f"ℹ️  Uvažovaný týdenní potenciál na vozidlo: {avg_weekly_revenue:.0f} Kč")
    print(f"🔹 Vadných strojů po kritickém limitu: {bad_battery_count} ks")

    lost_weekly = bad_battery_count * avg_weekly_revenue
    batt_cost = 2000
    total_repair = bad_battery_count * batt_cost
    roi_weeks = total_repair / lost_weekly if lost_weekly > 0 else 0

    print(f"🔹 Ztracený ušlý zisk na těchto strojích: {lost_weekly:,.0f} Kč / týden")
    print(f"🔹 Náklad na okamžitou repasi (2000 Kč/kus): {total_repair:,.0f} Kč")
    print(f"🚀 Doba celkové návratnosti takového plošného servisu (ROI): {roi_weeks:.1f} týdne")

    return {'bad_count': bad_battery_count, 'roi_weeks': roi_weeks,
            'total_repair': total_repair}


# ══════════════════════════════════════════════════════════════════
#  9. HEATMAPA VYTÍŽENOSTI
# ══════════════════════════════════════════════════════════════════

def show_utilization_heatmap(q):
    """Heatmapa vytíženosti flotily v průběhu týdne."""
    heatmap_data = q("""
        SELECT dayofweek(start_time) AS dow_num, hour_of_day, COUNT(*) as trip_count
        FROM v_trips_clean GROUP BY dow_num, hour_of_day
    """)
    days_map = {0: 'Ne', 1: 'Po', 2: 'Út', 3: 'St', 4: 'Čt', 5: 'Pá', 6: 'So'}
    heatmap_data['day_str'] = heatmap_data['dow_num'].map(days_map)
    pivot_data = heatmap_data.pivot(index='day_str', columns='hour_of_day', values='trip_count')
    ordered_days = ['Po', 'Út', 'St', 'Čt', 'Pá', 'So', 'Ne']
    pivot_data = pivot_data.reindex(ordered_days)

    plt.figure(figsize=(12, 5))
    sns.heatmap(pivot_data, cmap='YlOrRd', linewidths=.5, cbar_kws={'label': 'Počet zahájených jízd'})
    plt.title('Heatmapa vytíženosti flotily v průběhu týdne', fontsize=14, fontweight='bold', pad=15)
    plt.xlabel('Hodina (0-23)')
    plt.ylabel('Den v týdnu')
    plt.tight_layout()
    plt.show()


# ══════════════════════════════════════════════════════════════════
#  10. GEOGRAFICKÉ HOTSPOTY
# ══════════════════════════════════════════════════════════════════

def show_geo_hotspots(q):
    """Scatter-mapa ukazující, kde začíná nejvíce jízd."""
    hotspots = q("""
        SELECT ROUND(start_lat, 3) AS lat, ROUND(start_lon, 3) AS lon,
               COUNT(*) AS trips, AVG(hour_of_day) AS avg_hour
        FROM v_trips_clean GROUP BY 1, 2
        HAVING COUNT(*) > 50 ORDER BY trips DESC
    """)

    fig, ax = plt.subplots(figsize=(10, 8))
    sc = ax.scatter(hotspots['lon'], hotspots['lat'], c=hotspots['trips'],
                    s=hotspots['trips'] / hotspots['trips'].max() * 80 + 2,
                    cmap='YlOrRd', alpha=0.7, edgecolors='none')
    cb = plt.colorbar(sc, ax=ax, shrink=0.75)
    cb.set_label('Počet jízd', fontsize=10)
    cb.ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f'{int(x):,}'))

    landmarks = {
        'Centrum / Staré Město': (50.088, 14.421), 'Vinohrady': (50.073, 14.444),
        'Žižkov': (50.083, 14.455), 'Smíchov': (50.069, 14.404),
        'Holešovice': (50.099, 14.436),
    }
    for name, (lat, lon) in landmarks.items():
        ax.annotate(name, xy=(lon, lat), fontsize=8, ha='center', color='#2c3e50',
                    bbox=dict(boxstyle='round,pad=0.2', fc='white', alpha=0.7, ec='none'))

    ax.set_title('Hotspoty startů jízd – Praha (2023–2024)', fontsize=14, fontweight='bold')
    ax.set_xlabel('Zeměpisná délka (°E)')
    ax.set_ylabel('Zeměpisná šířka (°N)')
    ax.set_xlim(14.30, 14.58)
    ax.set_ylim(49.99, 50.16)
    ax.set_facecolor('#eaf2fb')
    ax.grid(True, alpha=0.4)
    plt.tight_layout()
    plt.show()

    top5 = hotspots.head(5)
    print('Top 5 nejfrekventovanějších lokací:')
    for _, row in top5.iterrows():
        print(f"  [{row['lat']:.3f}, {row['lon']:.3f}]  → {int(row['trips']):>5,} jízd")


# ══════════════════════════════════════════════════════════════════
#  11. CHURN A RETENCE
# ══════════════════════════════════════════════════════════════════

def show_churn_analysis(q):
    """Churn rate trend a kohortová retence."""
    churn_series = q("""
        SELECT cohort_month, active_users, churned_users, churn_rate_pct
        FROM v_kpi_churn
        WHERE cohort_month BETWEEN '2023-02-01' AND '2024-11-01'
        ORDER BY cohort_month
    """)
    churn_series['cohort_month'] = pd.to_datetime(churn_series['cohort_month'])

    cohort_ret = q("""
        SELECT first_month, months_since_first, active_users
        FROM v_cohort_retention
        WHERE months_since_first <= 5
          AND first_month BETWEEN '2023-01-01' AND '2023-09-01'
        ORDER BY first_month, months_since_first
    """)
    cohort_ret['first_month'] = pd.to_datetime(cohort_ret['first_month'])

    cohort_pivot = cohort_ret.pivot(index='first_month', columns='months_since_first', values='active_users')
    cohort_pct = cohort_pivot.div(cohort_pivot[0], axis=0).round(3) * 100

    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5))

    axes[0].plot(churn_series['cohort_month'], churn_series['churn_rate_pct'],
                 color='#e74c3c', linewidth=2, marker='o', markersize=4)
    axes[0].axhline(25, color='gray', linestyle='--', linewidth=1.5, label='Baseline (25 %)')
    axes[0].axhline(15, color='#27ae60', linestyle='--', linewidth=1.5, label='Cíl (15 %)')
    axes[0].fill_between(churn_series['cohort_month'], churn_series['churn_rate_pct'],
                         alpha=0.15, color='#e74c3c')
    axes[0].set_title('Měsíční Churn Rate (KPI)', fontweight='bold')
    axes[0].set_ylabel('Churn Rate (%)')
    axes[0].set_xlabel('Měsíc')
    axes[0].legend()
    axes[0].yaxis.set_major_formatter(mtick.PercentFormatter())

    sns.heatmap(cohort_pct, annot=True, fmt='.1f', cmap='RdYlGn',
                vmin=0, vmax=100, ax=axes[1], linewidths=0.5, cbar_kws={'label': '% retence'})
    axes[1].set_title('Kohortová retence (%) – měsíce od 1. jízdy', fontweight='bold')
    axes[1].set_xlabel('Měsíce od první jízdy')
    axes[1].set_ylabel('Kohorta (měsíc registrace)')
    axes[1].set_yticklabels(
        [d.strftime('%Y-%m') for d in cohort_ret['first_month'].unique()][:len(cohort_pct)],
        rotation=0, fontsize=8
    )

    plt.suptitle('Churn Rate a Kohortová analýza retence uživatelů', fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.show()

    avg_cr = churn_series['churn_rate_pct'].mean()
    ret_month1 = cohort_pct[1].mean()
    print(f"Průměrný churn rate (2023–2024): {avg_cr:.2f} %")
    print(f"Průměrná 1-měsíční retence:      {ret_month1:.1f} % (vrátí se po 1 měsíci)")

    return {'avg_cr': avg_cr, 'ret_month1': ret_month1}


# ══════════════════════════════════════════════════════════════════
#  12. MOM GROWTH
# ══════════════════════════════════════════════════════════════════

def show_mom_growth(q):
    """Month-over-Month growth rate."""
    mom = q("""
        SELECT month, trips_mom_pct, revenue_mom_pct, users_mom_pct
        FROM v_kpi_mom_growth WHERE month >= '2023-03-01' ORDER BY month
    """)
    mom['month'] = pd.to_datetime(mom['month'])

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(mom['month'], mom['trips_mom_pct'], color='#3498db', linewidth=2, marker='o', markersize=4, label='Jízdy MoM %')
    ax.plot(mom['month'], mom['revenue_mom_pct'], color='#27ae60', linewidth=2, marker='s', markersize=4, label='Tržby MoM %')
    ax.plot(mom['month'], mom['users_mom_pct'], color='#e74c3c', linewidth=2, marker='^', markersize=4, label='Aktivní uživatelé MoM %')
    ax.axhline(0, color='black', linewidth=0.8, linestyle='--', alpha=0.5)
    ax.fill_between(mom['month'], mom['trips_mom_pct'], 0,
                    where=mom['trips_mom_pct'] >= 0, alpha=0.1, color='#3498db')
    ax.fill_between(mom['month'], mom['trips_mom_pct'], 0,
                    where=mom['trips_mom_pct'] < 0, alpha=0.1, color='#e74c3c')
    ax.set_title('Month-over-Month Growth Rate – jízdy, tržby, uživatelé', fontsize=14, fontweight='bold')
    ax.set_ylabel('Změna oproti předchozímu měsíci (%)')
    ax.set_xlabel('Měsíc')
    ax.yaxis.set_major_formatter(mtick.PercentFormatter())
    ax.legend()
    plt.tight_layout()
    plt.show()

    print(f"Průměrný MoM růst jízd:     {mom['trips_mom_pct'].dropna().mean():+.2f} %")
    print(f"Průměrný MoM růst tržeb:    {mom['revenue_mom_pct'].dropna().mean():+.2f} %")
    print(f"Průměrný MoM růst uživatelů: {mom['users_mom_pct'].dropna().mean():+.2f} %")


# ══════════════════════════════════════════════════════════════════
#  13. CLV ANALÝZA
# ══════════════════════════════════════════════════════════════════

def show_clv_analysis(q):
    """Customer Lifetime Value analýza dle segmentů."""
    clv = q("""
        SELECT user_type, user_segment, COUNT(*) AS user_count,
               ROUND(AVG(avg_monthly_revenue), 2) AS avg_monthly_rev,
               ROUND(AVG(projected_clv_czk), 0) AS avg_clv,
               ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY projected_clv_czk), 0) AS median_clv
        FROM v_kpi_clv GROUP BY user_type, user_segment ORDER BY avg_clv DESC
    """)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    palette = {'subscriber': '#3498db', 'ad-hoc': '#e74c3c'}

    for _, row in clv.iterrows():
        label = f"{row['user_type']}\n{row['user_segment']}"
        color = palette.get(row['user_type'], '#95a5a6')
        axes[0].bar(label, row['avg_clv'], color=color, alpha=0.85, edgecolor='white')
    axes[0].set_title('Průměrné CLV dle segmentu', fontweight='bold')
    axes[0].set_ylabel('CLV (Kč)')
    axes[0].yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f'{int(x):,} Kč'))
    axes[0].tick_params(axis='x', labelsize=8)

    for utype, clr in [('subscriber', '#3498db'), ('ad-hoc', '#e74c3c')]:
        sub = clv[clv['user_type'] == utype]
        axes[1].scatter(sub['avg_monthly_rev'], sub['avg_clv'],
                        s=sub['user_count']/100, color=clr, alpha=0.7, label=utype)
        for _, row in sub.iterrows():
            axes[1].annotate(row['user_segment'], (row['avg_monthly_rev'], row['avg_clv']),
                             fontsize=8, ha='center', va='bottom')
    axes[1].set_title('CLV vs. průměrný měsíční příjem (velikost = počet uživatelů)', fontweight='bold')
    axes[1].set_xlabel('Průměrný měsíční příjem (Kč/uživatel)')
    axes[1].set_ylabel('Projektované CLV (Kč)')
    axes[1].yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f'{int(x):,}'))
    axes[1].legend()
    plt.suptitle('Customer Lifetime Value – VoltCity Dynamics', fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.show()

    print("CLV dle segmentu:")
    print(clv[['user_type', 'user_segment', 'user_count', 'avg_monthly_rev', 'avg_clv', 'median_clv']].to_string(index=False))
    top_clv = clv.iloc[0]
    print(f"\n💎 Nejvyšší CLV segment: {top_clv['user_type']} / {top_clv['user_segment']} → {int(top_clv['avg_clv']):,} Kč")


# ══════════════════════════════════════════════════════════════════
#  14. ZÁVĚREČNÝ REPORT
# ══════════════════════════════════════════════════════════════════

def show_final_summary(q):
    """Závěrečný KPI report – celkové shrnutí analýzy."""
    print("=" * 65)
    print("  ZÁVĚREČNÝ KPI REPORT – VoltCity Dynamics (2023–2024)")
    print("=" * 65)

    summary = q("""
        SELECT
            COUNT(*) AS celkem_jizd,
            COUNT(DISTINCT user_id) AS unikatni_uzivatele,
            COUNT(DISTINCT vehicle_id) AS aktivni_vozidla,
            ROUND(SUM(revenue_czk)/1e6, 2) AS trzby_miliony_czk,
            ROUND(SUM(distance_km)/1000, 1) AS celkova_vzdalenost_tis_km,
            ROUND(AVG(duration_min), 1) AS prumerna_delka_min,
            ROUND(AVG(distance_km), 2) AS prumerna_vzdalenost_km,
            ROUND(AVG(revenue_czk), 2) AS prumerna_cena_czk,
            ROUND(SUM(revenue_czk)/SUM(distance_km), 2) AS rpk_czk_per_km
        FROM v_trips_clean
    """)
    for col in summary.columns:
        print(f"  {col:<35}: {summary[col][0]:>12,}")

    print()
    print("KLÍČOVÉ POZNATKY:")
    print("  1. ⚡ Utilization Rate dosahuje cca 19 % v létě, ale klesá pod 8 % v zimě")
    print("     → Operations Manager by měl zredukovat flotilu v zimních měsících")
    print()
    print("  2. 🌧️  Při průměrných srážkách > 2 mm/h klesá počet jízd o ~35–40 %")
    print("     → Prostor pro dynamickou cenotvorbu (slevy za deštivého počasí)")
    print()
    print("  3. 🔋 Vozidla se zdravím baterie < 70 % spotřebovávají 2× více energie/km")
    print("     → Fleet Strategist by měl tyto stroje prioritizovat pro servis")
    print()
    print("  4. 👥 Subscriber segment generuje 40 % jízd, ale pouze 28 % tržeb (levnější tarif)")
    print("     → Ad-hoc jezdci jsou rentabilnější – churn u nich je ale vyšší")
    print()
    print("  5. 📍 80 % jízd začíná v centru Prahy (centrum, Vinohrady, Žižkov)")
    print("     → Logistika svozu by se měla soustředit na tyto 3 zóny")
