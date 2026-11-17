"""Szenario: ein Abrechnungsmonat eines Gewerbekunden in Viertelstunden (alle Generatoren sind Annahmen, keine Messdaten).

Die Last entsteht von unten nach oben aus Maschinenläufen (AP 0 der Vormessung: keine vorgegebene Spitzendauer). Die Dauer der
Spitzen ist hier ein Ergebnis der Überlagerung und wird gemessen; die mittlere Laufzeit der Maschinen ist der Regler dafür.
Der Monat hat 30 Tage und beginnt an einem Montag (22 Werktage); davor liegen 28 Tage Vorlauf für Prognosen (Persistenz, Klimatologie).
"""

from dataclasses import dataclass

import numpy as np

import lsk_constants as C

DT = C.DT  # Stunden je Zeitschritt (0,25)
SLOTS = C.SLOTS_PER_DAY
ETA_LEG = C.ETA_ROUND_TRIP**0.5  # Wirkungsgrad je Richtung (Laden, Entladen); Umlauf = ETA_ROUND_TRIP


@dataclass(frozen=True)
class Month:
    """Ein Abrechnungsmonat. load, pv in kW je Viertelstunde (Länge 30·96); hist_* der Vorlauf (28·96)."""

    load: np.ndarray
    pv: np.ndarray
    hist_load: np.ndarray
    hist_pv: np.ndarray
    seed: int
    mean_run_h: float
    kwp: float

    @property
    def slots(self) -> int:
        return len(self.load)

    @property
    def net(self) -> np.ndarray:
        """Last minus PV in kW (negativ = Überschuss)."""
        return self.load - self.pv


def _machine_load(rng: np.random.Generator, n_days: int, mean_run_h: float) -> np.ndarray:
    """Maschinenläufe: je Maschine Poisson-Starts in der Schicht, lognormale Laufzeit (Mittel mean_run_h), Leistung mit Streuung.

    Rückgabe kW je Viertelstunde für n_days Tage (Tag 0 = Montag). Samstag und Sonntag laufen keine Maschinen."""
    out = np.zeros(n_days * SLOTS)
    sigma = C.RUN_SIGMA
    mu = np.log(mean_run_h) - 0.5 * sigma**2  # Erwartungswert der Lognormalverteilung = mean_run_h
    shift_start, shift_end = C.SHIFT_HOURS
    for d in range(n_days):
        if d % 7 >= 5:
            continue
        day_factor = float(np.exp(rng.normal(0.0, C.DAY_ACTIVITY_SIGMA) - 0.5 * C.DAY_ACTIVITY_SIGMA**2))
        for p_kw in C.MACHINE_KW:
            rate = C.MACHINE_DUTY * day_factor / mean_run_h  # Starts je Stunde: Auslastung = Rate · Laufzeit
            t = shift_start + rng.exponential(1.0 / rate)
            while t < shift_end:
                dur = float(rng.lognormal(mu, sigma))
                power = p_kw * float(rng.uniform(0.85, 1.15))
                a = d * SLOTS + int(round(t / DT))
                b = min(a + max(1, int(round(dur / DT))), n_days * SLOTS)
                out[a:b] += power
                t += dur + rng.exponential(1.0 / rate)  # keine Überlappung der Läufe derselben Maschine
    return out


def make_load(seed: int, n_days: int, mean_run_h: float) -> np.ndarray:
    """Grundlast (Kühlung, Server) plus Gebäude plus Maschinenläufe, kW je Viertelstunde, n_days Tage ab Montag."""
    rng = np.random.default_rng(1_000_003 * int(seed) + 17)
    t = np.arange(n_days * SLOTS)
    day, hour = t // SLOTS, (t % SLOTS) * DT
    weekday = (day % 7) < 5
    base = C.BASE_KW * (1.0 + 0.03 * rng.standard_normal(len(t)))
    ramp = np.clip(np.minimum(hour - 5.5, 18.5 - hour) / 1.0, 0.0, 1.0)  # Gebäude: weicher Anstieg und Abfall
    building = C.BUILDING_KW * weekday * ramp
    return base + building + _machine_load(rng, n_days, mean_run_h)


def make_pv(seed: int, n_days: int, kwp: float) -> np.ndarray:
    """PV-Erzeugung in kW je Viertelstunde (Übergangsjahreszeit: Tageslicht 6 bis 18 Uhr, drei Wetterzustände, Wolkenrauschen)."""
    rng = np.random.default_rng(2_000_003 * int(seed) + 29)
    trans = np.array([[0.60, 0.25, 0.15], [0.30, 0.40, 0.30], [0.20, 0.30, 0.50]])  # klar, wechselhaft, trüb
    kt_state = np.array([0.95, 0.55, 0.20])
    noise_sigma = np.array([0.03, 0.30, 0.12])
    s = 1
    h = (np.arange(SLOTS) + 0.5) * DT
    envelope = np.clip(np.sin(np.pi * (h - 6.0) / 12.0), 0.0, None) ** 1.2
    out = np.zeros(n_days * SLOTS)
    for d in range(n_days):
        s = int(rng.choice(3, p=trans[s]))
        x = 0.0
        shape = np.empty(SLOTS)
        for i in range(SLOTS):
            x = 0.9 * x + float(rng.normal(0.0, noise_sigma[s]))
            shape[i] = kt_state[s] * (1.0 + x)
        out[d * SLOTS:(d + 1) * SLOTS] = np.clip(shape, 0.0, 1.05) * envelope
    return kwp * C.PV_PERFORMANCE_RATIO * out


def make_month(seed: int, mean_run_h: float = C.DEFAULT_RUN_H, kwp: float = C.DEFAULT_KWP) -> Month:
    """Ein Abrechnungsmonat samt Vorlauf. Last und PV hängen nur von Zufalls-Seed, Laufzeit und kWp ab."""
    n_hist, n_month = C.HISTORY_DAYS, C.MONTH_DAYS
    load = make_load(seed, n_hist + n_month, mean_run_h)
    pv = make_pv(seed, n_hist + n_month, kwp) if kwp > 0 else np.zeros_like(load)
    cut = n_hist * SLOTS
    return Month(load[cut:], pv[cut:], load[:cut], pv[:cut], int(seed), float(mean_run_h), float(kwp))


def peak_events(load: np.ndarray, share: float = C.PEAK_EVENT_SHARE) -> dict:
    """Kenngrößen der Spitzenereignisse eines Monats (Messung, kein Regler).

    Ein Ereignis ist eine zusammenhängende Folge von Viertelstunden, in denen die Last mindestens share · Monatsspitze beträgt.
    Rückgabe: Monatsspitze (kW), Zahl der Ereignisse, mittlere und längste Dauer in Stunden, Zahl der Tage mit Ereignis."""
    peak = float(load.max())
    above = load >= share * peak
    runs, start = [], None
    for i, flag in enumerate(above):
        if flag and start is None:
            start = i
        if not flag and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(above)))
    lengths = [(b - a) * DT for a, b in runs]
    days = {a // SLOTS for a, _ in runs}
    return dict(peak=peak, events=len(runs), mean_h=float(np.mean(lengths)) if lengths else 0.0,
                max_h=float(max(lengths)) if lengths else 0.0, days=len(days))
