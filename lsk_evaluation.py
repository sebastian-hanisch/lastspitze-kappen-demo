"""Auswertung: ein Monat mit allen Verfahren, Sweeps über Kapazität und Spitzendauer, Verdikte als reine Funktionen (DEMO-PLAYBOOK §12)."""

from dataclasses import dataclass, field

import numpy as np

import lsk_algorithm as A
import lsk_constants as C
import lsk_planner as PL
import lsk_scenario as S

M_NONE, M_R0, M_FIX, M_HIND, M_LP = "ohne", "R0", "fest", "nachsicht", "LP"
FORECAST_LABEL = PL.FORECAST_LABEL
METHOD_LABEL = {
    M_NONE: "Ohne Speicher",
    M_R0: "Eigenverbrauch (R0)",
    M_FIX: "Schwellenregel, θ vorab abgestimmt",
    M_HIND: "Schwellenregel, θ im Nachhinein",
    M_LP: "Exakter Plan (LP, Voraussicht)",
}


@dataclass(frozen=True)
class Settings:
    cap: float = C.DEFAULT_CAP
    power: float = C.DEFAULT_POWER
    kwp: float = C.DEFAULT_KWP
    run_h: float = C.DEFAULT_RUN_H
    peak_price: float = C.DEFAULT_PEAK_PRICE
    buy: float = C.DEFAULT_BUY
    seed: int = C.DEFAULT_SEED

    @property
    def prices(self) -> A.Prices:
        return A.Prices(buy=self.buy, sell=min(C.DEFAULT_SELL, self.buy), peak=self.peak_price)


@dataclass
class Analysis:
    settings: Settings
    month: S.Month
    schedules: dict
    costs: dict
    params: dict            # M_FIX / M_HIND -> (theta, rho)
    events: dict

    def saving(self, method: str) -> float:
        return self.costs[M_NONE]["total"] - self.costs[method]["total"]

    def share(self, method: str) -> float | None:
        """Anteil der Ersparnis an der des LP; None, wenn das LP nichts spart (Nenner 0)."""
        lp = self.saving(M_LP)
        return None if lp < 0.5 else self.saving(method) / lp


def tune_months(kwp: float, run_h: float) -> list[S.Month]:
    return [S.make_month(s, run_h, kwp) for s in C.TUNE_SEEDS]


def analyse(settings: Settings, tune: list[S.Month] | None = None) -> Analysis:
    """Ein Abrechnungsmonat: ohne Speicher, R0, beide Schwellenregeln und der exakte Plan."""
    m = S.make_month(settings.seed, settings.run_h, settings.kwp)
    prices = settings.prices
    tune = tune if tune is not None else tune_months(settings.kwp, settings.run_h)
    fix, th_f, rho_f = A.rule_theta_fixed(m, settings.cap, settings.power, prices, tune)
    hind, th_h, rho_h = A.rule_theta_hindsight(m, settings.cap, settings.power, prices)
    schedules = {
        M_NONE: A.no_storage(m),
        M_R0: A.rule_r0(m, settings.cap, settings.power),
        M_FIX: fix,
        M_HIND: hind,
        M_LP: A.solve_month(m, settings.cap, settings.power, prices),
    }
    costs = {k: A.schedule_cost(m, s, prices) for k, s in schedules.items()}
    return Analysis(settings, m, schedules, costs, {M_FIX: (th_f, rho_f), M_HIND: (th_h, rho_h)}, S.peak_events(m.load))


# --- Sweep über die Kapazität ---------------------------------------------------------------------------------------------------------------

def capacity_grid(power: float) -> list[float]:
    """Kapazitäten als Vielfache der Leistung (Stunden Volllast): 0,25 bis 8 Stunden."""
    return [round(k * power, 6) for k in C.CAP_HOURS]


def sweep_capacity(settings: Settings, seeds=None, with_rules: bool = True) -> list[dict]:
    """Mittlere Ersparnis (EUR je Monat) über `seeds` für jede Kapazität des Rasters: LP und, wenn verlangt, die drei Regeln."""
    seeds = C.SWEEP_SEEDS if seeds is None else seeds
    prices = settings.prices
    months = [S.make_month(s, settings.run_h, settings.kwp) for s in seeds]
    tune = tune_months(settings.kwp, settings.run_h) if with_rules else []
    base = [A.schedule_cost(m, A.no_storage(m), prices) for m in months]
    rows = []
    for cap in capacity_grid(settings.power):
        theta_f = rho_f = None
        if with_rules:
            theta_f, rho_f, _ = A.best_theta_rho(tune, cap, settings.power, prices)
        sav = {M_LP: [], M_R0: [], M_FIX: [], M_HIND: []}
        peaks = []
        for m, b in zip(months, base):
            lp = A.solve_month(m, cap, settings.power, prices)
            c_lp = A.schedule_cost(m, lp, prices)
            sav[M_LP].append(b["total"] - c_lp["total"])
            peaks.append(c_lp["peak"])
            if with_rules:
                sav[M_R0].append(b["total"] - A.schedule_cost(m, A.rule_r0(m, cap, settings.power), prices)["total"])
                fix = A.simulate_rule(m.net, cap, settings.power, theta_f, rho_f)
                sav[M_FIX].append(b["total"] - A.schedule_cost(m, fix, prices)["total"])
                hind = A.rule_theta_hindsight(m, cap, settings.power, prices)[0]
                sav[M_HIND].append(b["total"] - A.schedule_cost(m, hind, prices)["total"])
        peak_none = float(np.mean([b["peak"] for b in base]))
        row = dict(cap=cap, hours=cap / settings.power, peak=float(np.mean(peaks)), peak_none=peak_none,
                   power_saving=prices.peak * (peak_none - float(np.mean(peaks))))
        for k, v in sav.items():
            row[k] = float(np.mean(v)) if v else None
        row["lp_min"], row["lp_max"] = float(min(sav[M_LP])), float(max(sav[M_LP]))
        rows.append(row)
    return rows


def knee(rows: list[dict], share: float = C.KNEE_SHARE, key: str = "power_saving") -> dict:
    """Knie: kleinste Kapazität des Rasters mit mindestens `share` des Wertes von `key` bei der größten Kapazität.

    Standard ist die Ersparnis aus der Spitze (`power_saving`, Leistungspreis mal gesenkte Monatsspitze des LP), weil der Energieanteil
    der PV (Eigenverbrauch) mit der Kapazität weiter wächst und das Knie der Spitze verdeckt.
    Rückgabe: cap, hours (Kapazität/Leistung), saving_max (der Wert bei der größten Kapazität), cap_top; cap = None, wenn dort unter 0,50 EUR."""
    top = rows[-1][key]
    cap_top = rows[-1]["cap"]
    if top < 0.5:
        return dict(cap=None, hours=None, saving_max=top, cap_top=cap_top)
    for r in rows:
        if r[key] >= share * top - 1e-9:
            return dict(cap=r["cap"], hours=r["hours"], saving_max=top, cap_top=cap_top)
    return dict(cap=cap_top, hours=rows[-1]["hours"], saving_max=top, cap_top=cap_top)


def marginal_gains(rows: list[dict], key: str = M_LP) -> list[dict]:
    """Grenznutzen: zusätzliche Ersparnis in EUR je Monat und zusätzlicher kWh zwischen zwei Rasterpunkten (Treppe)."""
    out, prev_cap, prev_val = [], 0.0, 0.0
    for r in rows:
        out.append(dict(von=prev_cap, bis=r["cap"], je_kwh=(r[key] - prev_val) / (r["cap"] - prev_cap)))
        prev_cap, prev_val = r["cap"], r[key]
    return out


def sweep_duration(settings: Settings, run_hs=None, seeds=None) -> list[dict]:
    """Für jede mittlere Maschinenlaufzeit: Knie der LP-Ersparnis (nur LP) und gemessene Dauer der Spitzenereignisse."""
    run_hs = C.RUN_H_SWEEP if run_hs is None else run_hs
    seeds = C.SWEEP_SEEDS if seeds is None else seeds
    rows = []
    for rh in run_hs:
        s = Settings(settings.cap, settings.power, settings.kwp, rh, settings.peak_price, settings.buy, settings.seed)
        cap_rows = sweep_capacity(s, seeds=seeds, with_rules=False)
        k = knee(cap_rows)
        ev = [S.peak_events(S.make_month(sd, rh, settings.kwp).load) for sd in seeds]
        rows.append(dict(run_h=rh, knee_cap=k["cap"], knee_hours=k["hours"], saving_max=k["saving_max"],
                         event_h=float(np.mean([e["mean_h"] for e in ev])), event_days=float(np.mean([e["days"] for e in ev])),
                         curve=[(r["cap"], r["power_saving"]) for r in cap_rows]))
    return rows


# --- Planer mit Prognose -----------------------------------------------------------------------------------------------------------------------

PLANNER_MODES = {"tag": "Tagesplan, offen", "neu": "Neuplanen alle 15 Minuten"}


def planner_shares(settings: Settings, kind: str, reserve: str) -> dict:
    """Anteil der LP-Ersparnis für beide Betriebsarten eines Planers im gewählten Monat. reserve: "endwert" oder ein Betrag in EUR je kWh als Text.

    Das Neuplanen löst je Viertelstunde ein kleines LP (rund 3.000 Mal, etwa 30 s). Rückgabe: lp (EUR), tag, neu (Anteile, None wenn das LP nichts spart)."""
    m = S.make_month(settings.seed, settings.run_h, settings.kwp)
    prices = settings.prices
    base = A.schedule_cost(m, A.no_storage(m), prices)["total"]
    lp = base - A.schedule_cost(m, A.solve_month(m, settings.cap, settings.power, prices), prices)["total"]
    value = prices.end_value if reserve == "endwert" else float(reserve)
    out = {"lp": lp}
    for mode in PLANNER_MODES:
        sched = PL.run_planner(m, settings.cap, settings.power, prices, kind, mode, value, replan_every=PL.REPLAN_EVERY)
        saving = base - A.schedule_cost(m, sched, prices)["total"]
        out[mode] = None if lp < 0.5 else saving / lp
    return out


def planner_shares_from_measurements(plan_rows: list[dict], ref_rows: list[dict], kwp: float, reserve) -> dict:
    """Anteil der Planer an der LP-Ersparnis aus den Messreihen (`messung_prognose.json`, `messung_luecke.json`).

    Je (Prognoseart, Betrieb): Verhältnis der Mittel (Summe der Ersparnis des Planers durch Summe der LP-Ersparnis über alle Monate) und die
    Anteile je Monat. Das Verhältnis der Mittel ist nicht das Mittel der Verhältnisse."""
    lp = {r["seed"]: r[M_LP]["saving"] for r in ref_rows if r["kwp"] == kwp}
    out = {}
    for kind in ("perfekt", "persistenz", "klimatologie"):
        for mode in PLANNER_MODES:
            sel = [r for r in plan_rows if r["kwp"] == kwp and r["reserve"] == reserve and r["kind"] == kind and r["mode"] == mode]
            if not sel:
                continue
            total = sum(lp[r["seed"]] for r in sel)
            out[(kind, mode)] = dict(share=sum(r["saving"] for r in sel) / total, per_month=[r["saving"] / lp[r["seed"]] for r in sorted(sel, key=lambda r: r["seed"])])
    return out


def load_measurement(name: str):
    """Ergebnis einer Messreihe (tools/messung_<name>.json) oder None, wenn die Datei fehlt."""
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parent / "tools" / f"messung_{name}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def planner_table_markdown(plan_rows: list[dict], ref_rows: list[dict]) -> str:
    """Markdown-Tabelle der Messreihe: Anteil an der LP-Ersparnis je Planer (Verhältnis der Mittel; kleinster und größter Monat in Klammern)."""
    lines = []
    for kwp in sorted({r["kwp"] for r in plan_rows}, reverse=True):
        for reserve in ("endwert", 1.0):
            sh = planner_shares_from_measurements(plan_rows, ref_rows, kwp, reserve)
            if not sh:
                continue
            label = "ohne PV" if kwp == 0 else f"mit {kwp:.0f} kWp PV"
            res = "Reserve = Endwert (√η · Arbeitspreis)" if reserve == "endwert" else "Reserve 1,00 € je kWh"
            lines.append(f"**{label}, {res}** (C = 100 kWh, P = 50 kW, Anteil an der LP-Ersparnis, Monate: kleinster bis größter)\n")
            lines.append("| Prognose | Tagesplan, offen | Neuplanen alle 15 Minuten |\n|---|---|---|")
            for kind in PL.FORECAST_KINDS:
                cells = []
                for mode in PLANNER_MODES:
                    v = sh.get((kind, mode))
                    cells.append("–" if v is None else f"{100 * v['share']:.0f} % ({100 * min(v['per_month']):.0f} bis {100 * max(v['per_month']):.0f} %)")
                lines.append(f"| {FORECAST_LABEL[kind]} | {cells[0]} | {cells[1]} |")
            lines.append("")
    return "\n".join(lines)


def verdict_planner(res: dict, rule_share: float | None, label: str) -> tuple[str, str]:
    """Planer gegen Schwellenregel im gewählten Monat (ein Monat ist ein Einzelfall; die Tabelle über sechs Monate steht darunter)."""
    tag, neu = res["tag"], res["neu"]
    text = (f"Mit der Prognose „{label}“ erreicht der offene Tagesplan {_pct(tag)} und das Neuplanen {_pct(neu)} der LP-Ersparnis"
            + ("." if rule_share is None else f"; die vorab abgestimmte Schwellenregel ohne Prognose erreicht {_pct(rule_share)}.")
            + " Das gilt für diesen einen Monat.")
    if rule_share is not None and max(tag, neu) > rule_share + 0.02:
        return "success", text
    return "info", text


# --- Verdikte (reine Funktionen: (Art, Text)) -------------------------------------------------------------------------------------------------

def de(x: float, nd: int | None = None) -> str:
    """Zahl mit Dezimalkomma (nd Nachkommastellen, sonst kürzeste Darstellung)."""
    return (f"{x:g}" if nd is None else f"{x:.{nd}f}").replace(".", ",")


def _eur(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".") + " €"


def _pct(x: float) -> str:
    return f"{100 * x:.0f} %"


def verdict_main(a: Analysis) -> tuple[str, str]:
    """Kernaussage für den gewählten Monat und die gewählte Batterie."""
    lp_saving = a.saving(M_LP)
    if a.share(M_LP) is None:
        return "info", (f"Die Batterie (C = {a.settings.cap:.0f} kWh, P = {a.settings.power:.0f} kW) senkt die Monatsrechnung in diesem Monat nicht: "
                        f"selbst der exakte Plan spart nur {de(lp_saving, 2)} €.")
    peak_cut = 1.0 - a.costs[M_LP]["peak"] / a.costs[M_NONE]["peak"] if a.costs[M_NONE]["peak"] > 0 else 0.0
    parts = [
        f"Der exakte Plan (LP mit Voraussicht über den ganzen Monat) spart {_eur(lp_saving)} und senkt die Monatsspitze um {_pct(peak_cut)} "
        f"(von {a.costs[M_NONE]['peak']:.0f} auf {a.costs[M_LP]['peak']:.0f} kW).",
        f"Die Eigenverbrauchsregel R0 erreicht {_pct(a.share(M_R0))} dieser Ersparnis, die vorab abgestimmte Schwellenregel {_pct(a.share(M_FIX))}, "
        f"die im Nachhinein abgestimmte {_pct(a.share(M_HIND))}.",
    ]
    text = " ".join(parts)
    fix = round(100 * a.share(M_FIX))  # Schwellen auf dem angezeigten Prozentwert, damit Farbe und Zahl nie auseinanderlaufen
    if fix >= 90:
        return "success", text
    if fix >= 60:
        return "info", text
    return "warning", text


def verdict_knee(k: dict, power: float) -> tuple[str, str]:
    if k["cap"] is None:
        return "info", "Auf dem Raster spart die Batterie nichts (Ersparnis des LP unter 0,50 € je Monat): kein Knie."
    return "info", (f"{_pct(C.KNEE_SHARE)} der Ersparnis aus der Spitze (Leistungspreis), die mit {k['cap_top']:.0f} kWh erreicht wird, sind bei {k['cap']:.0f} kWh erreicht: "
                    f"das sind {de(k['hours'])} Stunden Volllast (C = {de(k['hours'])} · P bei P = {power:.0f} kW).")


def verdict_duration(rows: list[dict]) -> tuple[str, str]:
    """Hängt das Knie an der Spitzendauer? Vergleich der kürzesten und der längsten Laufzeit des Rasters."""
    known = [r for r in rows if r["knee_hours"] is not None]
    if len(known) < 2:
        return "info", "Für mindestens zwei Laufzeiten muss die Batterie etwas sparen, sonst gibt es keinen Vergleich."
    lo, hi = known[0], known[-1]
    knees = [r["knee_hours"] for r in known]
    if hi["knee_hours"] > lo["knee_hours"]:
        return "info", (f"Das Knie wandert mit der Spitzendauer: bei Laufzeit {de(lo['run_h'])} h bei {de(lo['knee_hours'])} Stunden Volllast, "
                        f"bei {de(hi['run_h'])} h bei {de(hi['knee_hours'])} Stunden (gemessene Dauer der Spitzenereignisse "
                        f"{de(lo['event_h'], 2)} h und {de(hi['event_h'], 2)} h).")
    if hi["knee_hours"] < lo["knee_hours"]:
        return "info", (f"Das Knie sinkt mit der Spitzendauer: bei Laufzeit {de(lo['run_h'])} h bei {de(lo['knee_hours'])} Stunden Volllast, "
                        f"bei {de(hi['run_h'])} h bei {de(hi['knee_hours'])} Stunden.")
    text = (f"Das Knie liegt bei der kürzesten und der längsten Laufzeit ({de(lo['run_h'])} h und {de(hi['run_h'])} h) gleich bei {de(hi['knee_hours'])} Stunden Volllast")
    if min(knees) < max(knees):
        return "info", text + f"; dazwischen liegt es zwischen {de(min(knees))} und {de(max(knees))} Stunden."
    return "success", text + "; auch dazwischen ändert es sich in diesem Raster nicht."


# --- Kennzahlen der Tabelle -------------------------------------------------------------------------------------------------------------------

def result_table(a: Analysis) -> list[dict]:
    """Eine Zeile je Verfahren: Spitze, Kosten (Energie, Leistung, Gesamt) und Ersparnis, jeweils für den Monat."""
    rows = []
    for key in (M_NONE, M_R0, M_FIX, M_HIND, M_LP):
        c = a.costs[key]
        sh = a.share(key) if key not in (M_NONE,) else None
        rows.append({"Verfahren": METHOD_LABEL[key], "Spitze (kW)": round(c["peak"], 1), "Leistungspreis (€)": round(c["power"], 0),
                     "Energie (€)": round(c["energy"] - c["end_value"], 0), "Gesamt (€)": round(c["total"], 0),
                     "Ersparnis (€)": round(a.saving(key), 0), "Anteil am LP (%)": None if sh is None else round(100 * sh, 0)})
    return rows
