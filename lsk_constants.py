"""Konstanten: Regler-Grenzen, feste Annahmen, Farben und Presets.

Alle Zahlen dieses Moduls sind Annahmen (Generatoren, Preise, Speichereigenschaften), keine Messdaten und keine Tarife eines Netzbetreibers.
"""

# --- Zeitraster und Abrechnung -------------------------------------------------------------------------------------------------------------
DT = 0.25                    # Stunden je Zeitschritt: die Leistungsspitze wird je Viertelstunde abgerechnet
SLOTS_PER_DAY = 96
MONTH_DAYS = 30              # ein Abrechnungsmonat, beginnt an einem Montag (22 Werktage)
HISTORY_DAYS = 28            # Vorlauf für Persistenz- und Klimatologie-Prognosen (vier ganze Wochen)
ETA_ROUND_TRIP = 0.90        # Umlaufwirkungsgrad (Laden × Entladen), je Richtung die Wurzel daraus

# --- Preise (Annahmen) ----------------------------------------------------------------------------------------------------------------------
DEFAULT_BUY, BUY_MIN, BUY_MAX = 0.20, 0.05, 0.40            # Arbeitspreis in EUR je kWh Netzbezug
DEFAULT_SELL = 0.07                                          # Einspeisevergütung in EUR je kWh; höchstens der Arbeitspreis
DEFAULT_PEAK_PRICE, PEAK_PRICE_MIN, PEAK_PRICE_MAX = 10.0, 0.5, 25.0   # Leistungspreis in EUR je kW und Monat

# --- Last: Maschinenläufe (Annahmen) --------------------------------------------------------------------------------------------------------
BASE_KW = 12.0               # Grundlast (Kühlung, Server)
BUILDING_KW = 10.0           # Gebäude (Licht, Lüftung) an Werktagen von etwa 6 bis 18 Uhr
MACHINE_KW = (18.0, 22.0, 30.0, 15.0, 25.0)   # Nennleistung der fünf Maschinen
MACHINE_DUTY = 0.25          # mittlere Auslastung je Maschine während der Schicht
SHIFT_HOURS = (6.0, 17.0)    # Schicht: Starts nur in diesem Zeitfenster
RUN_SIGMA = 0.5              # Streuung der Laufzeit (lognormal, Parameter sigma)
DAY_ACTIVITY_SIGMA = 0.30    # Tagesfaktor der Auslastung (Auftragslage), lognormal
DEFAULT_RUN_H, RUN_H_MIN, RUN_H_MAX = 1.0, 0.25, 3.0     # mittlere Laufzeit der Maschinen in Stunden (Regler „Spitzendauer“)
PEAK_EVENT_SHARE = 0.90      # Spitzenereignis: Last mindestens so viel Anteil der Monatsspitze

# --- Photovoltaik (Annahme) -----------------------------------------------------------------------------------------------------------------
PV_PERFORMANCE_RATIO = 0.80
DEFAULT_KWP, KWP_MIN, KWP_MAX = 100.0, 0.0, 200.0

# --- Speicher (Regler) ----------------------------------------------------------------------------------------------------------------------
DEFAULT_POWER, POWER_MIN, POWER_MAX = 50.0, 10.0, 150.0      # Leistung P in kW (Laden und Entladen)
DEFAULT_CAP, CAP_MIN, CAP_MAX = 100.0, 10.0, 600.0           # Kapazität C in kWh

SEED_MAX, DEFAULT_SEED = 999999, 1
SWEEP_SEEDS = tuple(range(1, 7))        # sechs feste Monate für alle Sweeps: nie ein einzelner Seed als Befund
TUNE_SEEDS = (101, 102, 103)            # getrennte Monate zum Abstimmen von Schwelle und Reserve (nie dieselben wie die Messmonate)

CAP_HOURS = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0)   # Kapazitätsraster der Sweeps in Stunden Volllast (C = Stunden · P)
KNEE_SHARE = 0.90                       # Knie: kleinste Kapazität mit diesem Anteil der Ersparnis bei der größten Kapazität des Rasters
RUN_H_SWEEP = (0.25, 0.5, 1.0, 2.0, 3.0)  # mittlere Maschinenlaufzeiten des Dauer-Sweeps in Stunden

THETA_STEP_KW = 5.0                    # Raster der Schwelle θ
RHO_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)  # Raster des Reservestands ρ (Anteil der Kapazität)

COLOR_LOAD = "#8a8a8a"
COLOR_NET = "#4c78a8"
COLOR_LP = "#2F6B65"
COLOR_RULE = "#d9822b"
COLOR_SOC = "#7a5fa0"
COLOR_BAD = "#b8433a"

STANDARD_PRESET = "Gewerbekunde mit PV (Voreinstellung)"
PRESETS = {
    STANDARD_PRESET: {},
    "Ohne PV: nur Spitzenkappen": {"kwp": 0.0},
    "Kurze Spitzen (Laufzeit 0,25 h)": {"run_h": 0.25},
    "Lange Spitzen (Laufzeit 3 h)": {"run_h": 3.0},
    "Kleine Leistung, große Kapazität": {"cap": 400.0, "power": 25.0},
}
PRESET_HELP = {
    STANDARD_PRESET: "Voreinstellung: 100 kWp PV, Batterie 100 kWh und 50 kW, Maschinenlaufzeit im Mittel 1 h, Leistungspreis 10 € je kW und Monat, Arbeitspreis 0,20 € je kWh.",
    "Ohne PV: nur Spitzenkappen": "Keine Photovoltaik (0 kWp): es bleibt das reine Spitzenkappen. Die Eigenverbrauchsregel lädt ohne Überschuss nie.",
    "Kurze Spitzen (Laufzeit 0,25 h)": "Mittlere Maschinenlaufzeit 0,25 h: kürzere Spitzen. Die dritte Kernfrage misst, wie sich das Knie der Kapazität dabei verschiebt.",
    "Lange Spitzen (Laufzeit 3 h)": "Mittlere Maschinenlaufzeit 3 h: Die dritte Kernfrage misst, wie sich das Knie der Kapazität dabei verschiebt.",
    "Kleine Leistung, große Kapazität": "400 kWh bei nur 25 kW: die Leistung begrenzt, wie viele kW der Spitze die Batterie kappen kann (höchstens P).",
}
