"""Kern: Speicher-LP mit Monatsspitze als Variable, einfache Regeln (Eigenverbrauch, Schwelle) und deren Abstimmung.

Modell (ein Abrechnungsmonat, Viertelstunden t = 0 … T−1, Δt = 0,25 h):
    Bilanz        imp_t − exp_t − ch_t + dis_t = Last_t − PV_t              (kW, Netzbezug und -einspeisung ≥ 0)
    Speicher      soc_{t+1} = soc_t + √η · ch_t · Δt − dis_t · Δt / √η     (0 ≤ soc ≤ C, 0 ≤ ch, dis ≤ P)
    Spitze        imp_t ≤ peak                                              (peak ≥ 0, abgerechnet mit dem Leistungspreis)
    Ziel          min  Δt · Σ (Arbeitspreis·imp_t − Einspeisepreis·exp_t) + Leistungspreis · peak − Endwert · soc_T
Die Restladung am Monatsende zählt mit dem Endwert √η · Arbeitspreis (so viel Netzbezug spart sie später) für jedes Verfahren gleich.
"""

from dataclasses import dataclass

import numpy as np
from scipy import sparse
from scipy.optimize import linprog

import lsk_constants as C
from lsk_scenario import DT, ETA_LEG, Month

TIE_EUR_PER_KWH = 1e-5  # Gleichstand beim Laden: früh laden bevorzugen (ohne dies verschiebt Neuplanen das Laden immer weiter nach hinten)


@dataclass(frozen=True)
class Prices:
    buy: float = C.DEFAULT_BUY          # EUR je kWh Netzbezug
    sell: float = C.DEFAULT_SELL        # EUR je kWh Einspeisung (höchstens buy)
    peak: float = C.DEFAULT_PEAK_PRICE  # EUR je kW und Monat auf die höchste Viertelstunden-Bezugsleistung

    @property
    def end_value(self) -> float:
        """Wert einer gespeicherten kWh am Monatsende: spart später √η · Arbeitspreis."""
        return ETA_LEG * self.buy


@dataclass
class Schedule:
    """Fahrplan eines Verfahrens für einen Monat (kW je Viertelstunde, soc in kWh mit T+1 Werten)."""

    ch: np.ndarray
    dis: np.ndarray
    imp: np.ndarray
    exp: np.ndarray
    soc: np.ndarray

    @property
    def peak(self) -> float:
        return float(self.imp.max()) if len(self.imp) else 0.0


def bill(imp: np.ndarray, exp: np.ndarray, soc_end: float, prices: Prices) -> dict:
    """Kosten eines Fahrplans: Energie + Leistungspreis − Endwert der Restladung (alles in EUR für den Monat)."""
    energy = DT * (prices.buy * float(imp.sum()) - prices.sell * float(exp.sum()))
    peak = float(imp.max()) if len(imp) else 0.0
    power = prices.peak * peak
    end = prices.end_value * soc_end
    return dict(energy=energy, power=power, end_value=end, peak=peak, total=energy + power - end)


def schedule_cost(m: Month, s: Schedule, prices: Prices) -> dict:
    return bill(s.imp, s.exp, float(s.soc[-1]), prices)


def no_storage(m: Month) -> Schedule:
    net = m.net
    z = np.zeros(m.slots)
    return Schedule(z, z.copy(), np.maximum(net, 0.0), np.maximum(-net, 0.0), np.zeros(m.slots + 1))


def solve_lp(net: np.ndarray, cap: float, power: float, prices: Prices, soc0: float = 0.0, end_value: float | None = None,
             peak_floor: float = 0.0, tie: float = TIE_EUR_PER_KWH) -> Schedule:
    """Exakter Fahrplan (HiGHS) bei vollständiger Voraussicht über `net` (Last − PV in kW).

    `peak_floor`: bereits erreichte Monatsspitze (die Spitze kann nicht darunter fallen), `end_value`: Wert der Restladung (Standard: Endwert des Monats)."""
    T = len(net)
    ev = prices.end_value if end_value is None else end_value
    iC, iD, iI, iE, iS, iP = 0, T, 2 * T, 3 * T, 4 * T, 4 * T + T + 1
    n = iP + 1
    c = np.zeros(n)
    c[iI:iI + T] = DT * prices.buy
    c[iE:iE + T] = -DT * prices.sell
    c[iC:iC + T] = tie * (np.arange(T) / max(T - 1, 1)) * DT
    c[iS + T] = -ev
    c[iP] = prices.peak
    t = np.arange(T)
    ones = np.ones(T)
    bal = sparse.coo_matrix((np.concatenate([ones, -ones, -ones, ones]),
                             (np.concatenate([t] * 4), np.concatenate([iI + t, iE + t, iC + t, iD + t]))), shape=(T, n))
    sta = sparse.coo_matrix((np.concatenate([ones, -ones, -ETA_LEG * DT * ones, DT / ETA_LEG * ones]),
                             (np.concatenate([t] * 4), np.concatenate([iS + t + 1, iS + t, iC + t, iD + t]))), shape=(T, n))
    a_eq = sparse.vstack([bal, sta]).tocsr()
    b_eq = np.concatenate([net, np.zeros(T)])
    a_ub = sparse.coo_matrix((np.concatenate([ones, -ones]), (np.concatenate([t, t]), np.concatenate([iI + t, np.full(T, iP)]))),
                             shape=(T, n)).tocsr()
    bounds = ([(0, power)] * T + [(0, power)] * T + [(0, None)] * T + [(0, None)] * T + [(soc0, soc0)] + [(0, cap)] * T
              + [(float(max(peak_floor, 0.0)), None)])
    res = linprog(c, A_ub=a_ub, b_ub=np.zeros(T), A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if not res.success:
        raise RuntimeError(f"LP nicht lösbar: {res.message}")
    x = res.x
    return Schedule(x[iC:iC + T], x[iD:iD + T], x[iI:iI + T], x[iE:iE + T], x[iS:iS + T + 1])


def solve_month(m: Month, cap: float, power: float, prices: Prices) -> Schedule:
    return solve_lp(m.net, cap, power, prices)


# --- Regeln ---------------------------------------------------------------------------------------------------------------------------------

def simulate_rule(net: np.ndarray, cap: float, power: float, theta: float, rho: float, soc0: float = 0.0) -> Schedule:
    """Schwellenregel mit Reserve (θ = ∞ und ρ = 0 ist die Eigenverbrauchsregel R0). Je Viertelstunde, nur mit dem aktuellen Wert:

    * Last − PV über θ: entladen, so weit es die Spitze auf θ senkt (höchstens P und Ladestand);
    * zwischen 0 und θ: über dem Reservestand ρ·C für den Eigenbedarf entladen, sonst bis zum Reservestand (und höchstens bis θ) aus dem Netz laden;
    * Überschuss (Last − PV < 0): laden, so weit PV-Überschuss, Leistung und Platz reichen.
    ρ = 1 heißt: nie für den Eigenbedarf entladen, aus dem Netz bis voll nachladen (reine Spitzenregel).
    """
    T = len(net)
    ch = np.zeros(T)
    dis = np.zeros(T)
    soc_trace = np.empty(T + 1)
    soc = soc0
    soc_trace[0] = soc
    reserve = rho * cap
    k_out = ETA_LEG / DT       # kW, die ein kWh Ladestand liefert: soc · √η / Δt
    k_in = 1.0 / (ETA_LEG * DT)  # kW Netz-/Überschussleistung für kWh Platz
    for t in range(T):
        x = float(net[t])
        c_t = d_t = 0.0
        if x > theta:
            d_t = min(power, x - theta, soc * k_out)
        elif x > 0.0:
            if soc > reserve + 1e-12:
                d_t = min(power, x, (soc - reserve) * k_out)
            elif soc < reserve - 1e-12:
                c_t = min(power, theta - x, (reserve - soc) * k_in)
        else:
            c_t = min(power, -x, (cap - soc) * k_in)
        soc += ETA_LEG * c_t * DT - d_t * DT / ETA_LEG
        ch[t], dis[t], soc_trace[t + 1] = c_t, d_t, soc
    imp_exp = net + ch - dis
    return Schedule(ch, dis, np.maximum(imp_exp, 0.0), np.maximum(-imp_exp, 0.0), soc_trace)


def rule_r0(m: Month, cap: float, power: float) -> Schedule:
    return simulate_rule(m.net, cap, power, np.inf, 0.0)


def theta_grid(net_max: float) -> list[float]:
    top = max(float(net_max), C.THETA_STEP_KW)
    return [float(v) for v in np.arange(C.THETA_STEP_KW, top + C.THETA_STEP_KW, C.THETA_STEP_KW)]


def best_theta_rho(months: list[Month], cap: float, power: float, prices: Prices) -> tuple[float, float, float]:
    """Gitterabstimmung von (θ, ρ): die Parameter mit den kleinsten Gesamtkosten über die übergebenen Monate; Rückgabe (θ, ρ, Kosten)."""
    top = max(float(m.net.max()) for m in months)
    best = None
    for theta in theta_grid(top):
        for rho in C.RHO_GRID:
            total = sum(schedule_cost(m, simulate_rule(m.net, cap, power, theta, rho), prices)["total"] for m in months)
            if best is None or total < best[2] - 1e-9:
                best = (theta, rho, total)
    return best


def rule_theta_fixed(m: Month, cap: float, power: float, prices: Prices, tune_months: list[Month]) -> tuple[Schedule, float, float]:
    """Schwellenregel, deren (θ, ρ) auf anderen Monaten abgestimmt wurden (ohne Kenntnis dieses Monats)."""
    theta, rho, _ = best_theta_rho(tune_months, cap, power, prices)
    return simulate_rule(m.net, cap, power, theta, rho), theta, rho


def rule_theta_hindsight(m: Month, cap: float, power: float, prices: Prices) -> tuple[Schedule, float, float]:
    """Schwellenregel mit (θ, ρ), die im Nachhinein für genau diesen Monat die kleinsten Kosten ergeben (Obergrenze der Regelklasse)."""
    theta, rho, _ = best_theta_rho([m], cap, power, prices)
    return simulate_rule(m.net, cap, power, theta, rho), theta, rho
