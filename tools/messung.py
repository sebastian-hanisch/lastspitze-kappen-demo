"""Messreihen der Demo (Quelle aller Zahlen in der README). Schreibt tools/messung_<name>.json.

Aufruf (Test-venv, aus dem Demo-Ordner):  python tools/messung.py kapazitaet | dauer | prognose | luecke | alle   [--workers N]

* kapazitaet: Ersparnis über der Kapazität (LP und Regeln), sechs Messmonate SWEEP_SEEDS, Leistung 50 kW, mit PV (100 kWp) und ohne PV.
* dauer:      Knie der Spitzensenkung über der mittleren Maschinenlaufzeit (AP 0: hängt das Knie an der Spitzendauer?).
* prognose:   Planer mit Prognose (offener Tagesplan, Neuplanen alle 15 Minuten) gegen LP und Regel, 6 Monate, C = 100 kWh, P = 50 kW.
* luecke:     Zerlegung der Lücke zwischen Regeln und LP in Leistungs- und Energieanteil, Spitzen je Verfahren, C = 100 kWh, P = 50 kW.
Alle Generatoren (Last, PV, Prognosen) sind Annahmen; Zahlen gelten für diese Generatoren, nicht für einen echten Betrieb.
"""

import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import lsk_algorithm as A  # noqa: E402
import lsk_constants as C  # noqa: E402
import lsk_evaluation as E  # noqa: E402
import lsk_planner as PL  # noqa: E402
import lsk_scenario as S  # noqa: E402

OUT = Path(__file__).resolve().parent
CAP_PLANNER, POWER_PLANNER = 100.0, 50.0
RESERVES = ("endwert", 1.0)   # Reservewert der Planer: „endwert“ = √η · Arbeitspreis, sonst EUR je kWh


def _dump(name: str, data) -> None:
    (OUT / f"messung_{name}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"messung_{name}.json geschrieben", flush=True)


def _kap_job(args):
    kwp, power = args
    return dict(kwp=kwp, power=power, rows=E.sweep_capacity(E.Settings(power=power, kwp=kwp)))


def _dauer_job(args):
    kwp, power = args
    return dict(kwp=kwp, power=power, rows=E.sweep_duration(E.Settings(power=power, kwp=kwp)))


def _plan_job(args):
    kwp, reserve, kind, mode, seed = args
    s = E.Settings(cap=CAP_PLANNER, power=POWER_PLANNER, kwp=kwp, seed=seed)
    m = S.make_month(seed, s.run_h, kwp)
    prices = s.prices
    base = A.schedule_cost(m, A.no_storage(m), prices)["total"]
    res = prices.end_value if reserve == "endwert" else float(reserve)
    sched = PL.run_planner(m, s.cap, s.power, prices, kind, mode, res)
    return dict(kwp=kwp, reserve=reserve, kind=kind, mode=mode, seed=seed, saving=base - A.schedule_cost(m, sched, prices)["total"],
                peak=float(sched.imp.max()))


def _ref_job(args):
    kwp, seed = args
    a = E.analyse(E.Settings(cap=CAP_PLANNER, power=POWER_PLANNER, kwp=kwp, seed=seed))
    out = dict(kwp=kwp, seed=seed, none_peak=a.costs[E.M_NONE]["peak"], ev=a.events)
    t_peak = int(np.argmax(a.schedules[E.M_NONE].imp))   # Viertelstunde der Monatsspitze ohne Speicher
    out["t_peak"] = t_peak
    for key in (E.M_NONE, E.M_R0, E.M_FIX, E.M_HIND, E.M_LP):
        c = a.costs[key]
        out[key] = dict(saving=a.saving(key), peak=c["peak"], power=c["power"], energy=c["energy"] - c["end_value"], total=c["total"],
                        soc_at_peak=float(a.schedules[key].soc[t_peak]) / CAP_PLANNER)
    out["theta_fix"], out["rho_fix"] = a.params[E.M_FIX]
    return out


def run(name: str, workers: int = 6) -> None:
    t0 = time.time()
    with Pool(workers) as pool:
        if name == "kapazitaet":
            _dump(name, pool.map(_kap_job, [(100.0, 50.0), (0.0, 50.0)]))
        elif name == "dauer":
            _dump(name, pool.map(_dauer_job, [(100.0, 50.0), (0.0, 50.0), (0.0, 25.0), (0.0, 100.0)]))
        elif name == "prognose":
            jobs = [(kwp, res, kind, mode, seed) for kwp in (100.0, 0.0) for res in RESERVES for kind in PL.FORECAST_KINDS
                    for mode in ("tag", "neu") for seed in C.SWEEP_SEEDS]
            _dump(name, pool.map(_plan_job, jobs, chunksize=1))
        elif name == "luecke":
            _dump(name, pool.map(_ref_job, [(kwp, seed) for kwp in (100.0, 0.0) for seed in C.SWEEP_SEEDS]))
        else:
            raise SystemExit(f"unbekannte Messreihe: {name}")
    print(f"{name}: {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    argv = sys.argv[1:]
    workers = 6
    if "--workers" in argv:
        i = argv.index("--workers")
        workers = int(argv[i + 1])
        del argv[i:i + 2]
    names = ["kapazitaet", "dauer", "luecke", "prognose"] if argv in ([], ["alle"]) else argv
    for n in names:
        run(n, workers)
