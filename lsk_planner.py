"""Planer mit Prognose: der Plan kommt aus dem LP (lsk_algorithm.solve_lp) über prognostizierte Werte, ausgeführt wird gegen die wahren Werte.

Zwei Betriebsarten (beide kennen nur die Vergangenheit und die Prognose, nie die wahre Zukunft):
* offener Tagesplan: um Mitternacht ein Plan über 48 Stunden, die ersten 24 Stunden werden unverändert gefahren;
* Neuplanen: alle `replan_every` Viertelstunden ein neuer Plan über 24 Stunden mit dem aktuellen Ladestand, der aktuelle Wert ist bekannt
  (Nowcast), alles dahinter ist Prognose; gefahren werden die nächsten `replan_every` Viertelstunden des Plans.
Die Prognosearten sind Annahmen: perfekt (nur Kontrolle), Persistenz (Last: gleiche Viertelstunde vor 7 Tagen, PV: gleiche vor 1 Tag),
Klimatologie (Mittel des Vorlaufs: Last je Wochentag und Viertelstunde, PV je Viertelstunde).
"""

import numpy as np

import lsk_constants as C
from lsk_algorithm import Prices, Schedule, solve_lp
from lsk_scenario import DT, ETA_LEG, SLOTS, Month

FORECAST_KINDS = ("perfekt", "persistenz", "klimatologie")
REPLAN_EVERY = 1  # Neuplanen alle so viele Viertelstunden (1 = jede Viertelstunde; Tests setzen einen größeren Wert, um Zeit zu sparen)
FORECAST_LABEL = {"perfekt": "perfekte Prognose", "persistenz": "Persistenz", "klimatologie": "Klimatologie"}


def forecast_net(m: Month, kind: str) -> np.ndarray:
    """Prognose von Last − PV für jede Viertelstunde des Monats; sie benutzt nur Werte, die zu diesem Zeitpunkt bekannt sind."""
    if kind == "perfekt":
        return m.net.copy()
    if kind == "persistenz":
        load_all = np.concatenate([m.hist_load, m.load])
        pv_all = np.concatenate([m.hist_pv, m.pv])
        h = len(m.hist_load)
        idx = h + np.arange(m.slots)
        return load_all[idx - 7 * SLOTS] - pv_all[idx - 1 * SLOTS]
    if kind == "klimatologie":
        days_h = len(m.hist_load) // SLOTS
        hl = m.hist_load.reshape(days_h, SLOTS)
        hp = m.hist_pv.reshape(days_h, SLOTS)
        wd = np.arange(days_h) % 7  # Vorlauf beginnt an einem Montag
        load_by_wd = np.stack([hl[wd == k].mean(axis=0) for k in range(7)])
        pv_mean = hp.mean(axis=0)
        day = np.arange(m.slots) // SLOTS
        slot = np.arange(m.slots) % SLOTS
        return load_by_wd[day % 7, slot] - pv_mean[slot]
    raise ValueError(f"unbekannte Prognoseart: {kind}")


def run_planner(m: Month, cap: float, power: float, prices: Prices, kind: str, mode: str, reserve_value: float,
                replan_every: int = 1) -> Schedule:
    """Fahrplan eines Planers. mode: "tag" (offener Tagesplan) oder "neu" (Neuplanen). reserve_value: EUR je kWh Restladung am Planende."""
    T = m.slots
    net_true = m.net
    net_f = forecast_net(m, kind)
    ch = np.zeros(T)
    dis = np.zeros(T)
    soc = np.zeros(T + 1)
    peak_so_far = 0.0
    t0 = 0
    if mode == "tag":
        step, horizon = SLOTS, 2 * SLOTS
    elif mode == "neu":
        step, horizon = replan_every, SLOTS
    else:
        raise ValueError(f"unbekannter Betrieb: {mode}")
    while t0 < T:
        t1 = min(t0 + horizon, T)
        view = net_f[t0:t1].copy()
        if mode == "neu":
            view[0] = net_true[t0]  # Nowcast: der aktuelle Wert ist bekannt
        end_value = prices.end_value if t1 == T else reserve_value
        plan = solve_lp(view, cap, power, prices, soc0=float(soc[t0]), end_value=end_value, peak_floor=peak_so_far)
        n = min(step, T - t0)
        ch[t0:t0 + n] = plan.ch[:n]
        dis[t0:t0 + n] = plan.dis[:n]
        for k in range(n):
            soc[t0 + k + 1] = min(max(soc[t0 + k] + ETA_LEG * ch[t0 + k] * DT - dis[t0 + k] * DT / ETA_LEG, 0.0), cap)
        imp_part = np.maximum(net_true[t0:t0 + n] + ch[t0:t0 + n] - dis[t0:t0 + n], 0.0)
        peak_so_far = max(peak_so_far, float(imp_part.max()))
        t0 += n
    flow = net_true + ch - dis
    return Schedule(ch, dis, np.maximum(flow, 0.0), np.maximum(-flow, 0.0), soc)
