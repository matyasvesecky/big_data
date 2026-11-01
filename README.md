# 🛴 VoltCity Dynamics – Big Data Analytics

Komplexní datový projekt pro analýzu a optimalizaci sítě sdílených elektrokoloběžek a e-kol v metropolitní oblasti Prahy. Projekt využívá moderní analytický stack s důrazem na výkon a business storytelling.

---

## 🚀 Klíčové Funkce & Výstupy

*   **KPI Dashboard**: Sledování Utilization Rate (UR), Churn Rate (CR) a Revenue Per KM (RPK).
*   **Hluboká EDA**: 8+ interaktivních vizualizací (Sezónnost, vliv počasí, heatmapy hotspotů, kohortová analýza).
*   **Business ROI Model**: Finanční analýza prediktivní údržby s vyčíslením ušlého zisku (ROI servisu < 2 týdny).
*   **High-Performance Storage**: Využití **DuckDB** jako analytického engine pro bleskové zpracování 500k+ záznamů.

## 🛠️ Technická Architektura

1.  **Sourcing**: `generate_data.py` generuje syntetickou telemetrii (500k jízd), data o uživatelích a počasí (včetně záměrných chyb pro cleaning).
2.  **Storage (ELT)**: `init_db.py` inicializuje DuckDB, provádí čištění dat a vytváří sémantickou vrstvu (KPI views).
3.  **Analytics**: `analyza_final.ipynb` obsahuje kompletní analýzu a vizualizace.
4.  **Reporting**: `index.html` slouží jako průvodní dokumentace projektu.

## 📊 Business Insights (Ukázka)
*   **Sezónnost**: Vytíženost v létě (19 %) vs. zima (8 %) – doporučení na stažení 30 % flotily v zimě.
*   **Počasí**: Při dešti (>2mm/h) klesá poptávka o ~40 % – prostor pro dynamickou cenotvorbu.
*   **Servis**: Identifikace 42 vadných baterií přináší potenciální úsporu/zisk **50 400 Kč týdně**.

## 💻 Rychlý Start (Reproduction)

```bash
# 1. Klonovat a setup
git clone <repo_url>
cd big_data
python -m venv venv && source venv/bin/activate
pip install duckdb pandas numpy matplotlib seaborn jupyter

# 2. Generování & Pipeline
python generate_data.py   # Generuje CSV soubory (~500k řádků)
python init_db.py         # Inicializuje DuckDB a views

# 3. Analýza
jupyter lab analyza_final.ipynb
```

---
*Vytvořeno v rámci projektu pro analýzu velkých dat.*
