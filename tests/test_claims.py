"""Jede Zahl der README-Tabelle „Befunde“ gegen die Messreihen `tools/messung_*.json` (Quelle: `tools/messung.py`, sechs Messmonate `SWEEP_SEEDS`).

Die JSON-Dateien sind das Ergebnis eines langen Laufs (Prognose: rund sieben Minuten auf 8 Kernen); hier wird jede README-Zahl aus ihnen abgeleitet und im Text gesucht, und Stichproben werden live neu
gerechnet (Band, nicht bitgenau: HiGHS und BLAS können unter Linux an der letzten Stelle abweichen). Das Neuplanen im Viertelstundentakt (rund 30 s je Monat) ist nicht Teil der Stichproben;
seine Zahlen stehen als „Messung dieser README, nicht im Test neu gerechnet“."""

import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

import lsk_algorithm as A
import lsk_constants as C
import lsk_evaluation as E
import lsk_planner as PL
import lsk_scenario as S

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")


def _load(name):
    return json.loads((ROOT / "tools" / f"messung_{name}.json").read_text(encoding="utf-8"))


def _de(x, nd=0):
    return f"{x:.{nd}f}".replace(".", ",")


def _in_readme(text):
    assert text in README, f"README enthält nicht: {text!r}"


LUECKE, KAPAZITAET, DAUER, PROGNOSE = _load("luecke"), _load("kapazitaet"), _load("dauer"), _load("prognose")
PV, NOPV = 100.0, 0.0


def _rows(kwp):
    return sorted([r for r in LUECKE if r["kwp"] == kwp], key=lambda r: r["seed"])


def _lp(kwp):
    return np.array([r["LP"]["saving"] for r in _rows(kwp)])


def _sav(kwp, key):
    return np.array([r[key]["saving"] for r in _rows(kwp)])


def _gap_shares(kwp, key):
    rows = _rows(kwp)
    gap = sum(r["LP"]["saving"] - r[key]["saving"] for r in rows)
    power = sum(r[key]["power"] - r["LP"]["power"] for r in rows)
    return power / gap, 1.0 - power / gap


def test_measurements_cover_the_six_fixed_months():
    assert [r["seed"] for r in _rows(PV)] == list(C.SWEEP_SEEDS) == [r["seed"] for r in _rows(NOPV)]
    assert len(PROGNOSE) == 2 * 2 * 3 * 2 * 6                       # PV-Fall × Reserve × Prognose × Betrieb × Monat


def test_exact_plan_saving_and_peak():
    for kwp, mean_text, span in ((PV, "717 €", "678 bis 754"), (NOPV, "491 €", "483 bis 498")):
        lp = _lp(kwp)
        assert _de(lp.mean()) + " €" == mean_text
        assert f"{_de(lp.min())} bis {_de(lp.max())}" == span
    _in_readme("**717 €** je Monat (678 bis 754 je Monat)")
    for kwp, text in ((PV, "von 106,2 auf 56,7 kW"), (NOPV, "von 121,9 auf 71,9 kW")):
        rows = _rows(kwp)
        assert f"von {_de(np.mean([r['none_peak'] for r in rows]), 1)} auf {_de(np.mean([r['LP']['peak'] for r in rows]), 1)} kW" == text
        _in_readme(text)
    _in_readme("Ohne PV: 491 € (483 bis 498)")


def test_exact_plan_resample_matches_the_measurement_within_a_band():
    for seed in (1, 5):
        a = E.analyse(E.Settings(cap=100.0, power=50.0, kwp=PV, seed=seed))
        ref = next(r for r in _rows(PV) if r["seed"] == seed)
        assert a.saving(E.M_LP) == pytest.approx(ref["LP"]["saving"], abs=0.5)
        assert a.costs[E.M_LP]["peak"] == pytest.approx(ref["LP"]["peak"], abs=0.05)
        assert a.saving(E.M_R0) == pytest.approx(ref["R0"]["saving"], abs=0.5)


def test_r0_saves_energy_but_not_the_peak():
    sav, lp = _sav(PV, "R0"), _lp(PV)
    assert _de(sav.mean()) == "225" and _de(100 * sav.sum() / lp.sum()) == "31"
    share = sav / lp
    assert (_de(100 * share.min()), _de(100 * share.max())) == ("26", "36")
    rows = _rows(PV)
    assert (_de(np.mean([r["R0"]["peak"] for r in rows]), 1), _de(np.mean([r["none_peak"] for r in rows]), 1)) == ("105,9", "106,2")
    power_share, _ = _gap_shares(PV, "R0")
    assert 0.99 <= power_share <= 1.01                                # die Lücke liegt zu 100 % in der Leistungsrechnung
    assert sum(r["R0"]["soc_at_peak"] < 0.01 for r in rows) == 5     # in 5 von 6 Monaten leer zur Spitze
    assert all(abs(r["R0"]["saving"]) < 1e-9 for r in _rows(NOPV))   # ohne PV lädt R0 nie
    _in_readme("Mit PV **225 €, 31 % des LP** (26 bis 36 % je Monat)")
    _in_readme("die Spitze sinkt nur von 106,2 auf 105,9 kW")
    _in_readme("in 5 von 6 Monaten leer")
    _in_readme("0 € in 6 von 6 Monaten")


def test_tuned_threshold_rule_versus_lp():
    for kwp, ratio_text, span in ((PV, "73", ("60", "86")), (NOPV, "92", ("83", "99"))):
        sav, lp = _sav(kwp, "fest"), _lp(kwp)
        assert _de(100 * sav.sum() / lp.sum()) == ratio_text
        assert (_de(100 * (sav / lp).min()), _de(100 * (sav / lp).max())) == span
    rows = {kwp: _rows(kwp) for kwp in (PV, NOPV)}
    assert {(r["theta_fix"], r["rho_fix"]) for r in rows[PV]} == {(60.0, 0.5)} and {(r["theta_fix"], r["rho_fix"]) for r in rows[NOPV]} == {(70.0, 0.75)}
    power, energy = _gap_shares(PV, "fest")
    assert (_de(100 * power), _de(100 * energy)) == ("51", "49")
    assert _de(100 * _gap_shares(NOPV, "fest")[0]) == "100"
    _in_readme("Vorab abgestimmt (θ = 60 kW, ρ = 0,5): **73 %** mit PV (60 bis 86 % je Monat); ohne PV (θ = 70 kW, ρ = 0,75): **92 %** (83 bis 99 %)")
    def monthly(kwp):
        return [(r["fest"]["power"] - r["LP"]["power"]) / (r["LP"]["saving"] - r["fest"]["saving"]) for r in _rows(kwp)]

    assert (_de(100 * min(monthly(PV))), _de(100 * max(monthly(PV)))) == ("0", "63")
    assert (_de(100 * min(monthly(NOPV))), _de(100 * max(monthly(NOPV)))) == ("0", "109")
    _in_readme("liegt mit PV zu 51 % in der Leistungsrechnung (je Monat 0 bis 63 %) und zu 49 % in der Energie; ohne PV zu 100 % in der Leistungsrechnung (je Monat 0 bis 109 %")


def test_hindsight_threshold_rule_versus_lp():
    for kwp, ratio_text, span in ((PV, "84", ("75", "88")), (NOPV, "99", ("99", "100"))):
        sav, lp = _sav(kwp, "nachsicht"), _lp(kwp)
        assert _de(100 * sav.sum() / lp.sum()) == ratio_text
        assert (_de(100 * (sav / lp).min()), _de(100 * (sav / lp).max())) == span
    power, energy = _gap_shares(PV, "nachsicht")
    assert (_de(100 * power), _de(100 * energy)) == ("26", "74")
    _in_readme("**84 %** mit PV (75 bis 88 % je Monat), **99 %** ohne PV (99 bis 100 %)")
    monthly = [(r["nachsicht"]["power"] - r["LP"]["power"]) / (r["LP"]["saving"] - r["nachsicht"]["saving"]) for r in _rows(PV)]
    assert (_de(100 * min(monthly)), _de(100 * max(monthly))) == ("0", "72")
    _in_readme("im Mittel zu 26 % in der Leistungsrechnung (je Monat 0 bis 72 %), zu 74 % in der Energie")


def _cap_rows(kwp):
    return next(b for b in KAPAZITAET if b["kwp"] == kwp)["rows"]


def test_capacity_curve():
    nopv, pv = _cap_rows(NOPV), _cap_rows(PV)
    assert [_de(r[E.M_LP]) for r in nopv[:5]] == ["248", "370", "446", "483", "491"]
    gains = [g["je_kwh"] for g in E.marginal_gains(nopv)]
    assert [_de(g, 1) for g in gains[:5]] == ["19,8", "9,8", "6,1", "3,0", "0,3"] and max(gains[5:]) < 0.01
    assert all(abs(r[E.M_LP] - nopv[4][E.M_LP]) < 0.01 for r in nopv[4:])         # ab 75 kWh gleich
    assert _de(pv[-1][E.M_LP]) == "902" and pv[-1]["cap"] == 400.0
    assert pv[4]["power_saving"] <= 500.0 + 1e-6 and all(r["power_saving"] >= 499.9 for r in pv[6:]) and pv[6]["cap"] == 150.0   # P · Leistungspreis ab 150 kWh
    for rows in (nopv, pv):                                                       # konkav: der Grenznutzen fällt in jedem Schritt
        g = [x["je_kwh"] for x in E.marginal_gains(rows)]
        assert all(b <= a + 1e-9 for a, b in zip(g, g[1:]))
    assert E.knee(pv)["hours"] == 1.0 and E.knee(pv)["cap"] == 50.0 and E.knee(nopv)["hours"] == 0.75 and E.knee(nopv)["cap"] == 37.5
    _in_readme("248 € bei 12,5 kWh, 370 € bei 25, 446 € bei 37,5, 483 € bei 50 und 491 € ab 75 kWh")
    _in_readme("von 19,8 über 9,8, 6,1 und 3,0 auf 0,3 €/(kWh·Monat) und ist ab 75 kWh null")
    _in_readme("(902 € bei 400 kWh)")
    _in_readme("P · Leistungspreis = 500 € ab 150 kWh")
    _in_readme("Auf dem Raster bei 1 Stunde Volllast (50 kWh) mit PV und bei 0,75 Stunden (37,5 kWh) ohne PV; beide Werte liegen knapp an der 90-%-Schwelle.")


def test_capacity_resample_matches_the_measurement_within_a_band(monkeypatch):
    monkeypatch.setattr(C, "CAP_HOURS", (0.75, 2.0, 8.0))
    rows = E.sweep_capacity(E.Settings(power=50.0, kwp=NOPV), with_rules=False)
    ref = {r["cap"]: r for r in _cap_rows(NOPV)}
    for r in rows:
        assert r[E.M_LP] == pytest.approx(ref[r["cap"]][E.M_LP], abs=0.5)
        assert r["power_saving"] == pytest.approx(ref[r["cap"]]["power_saving"], abs=0.5)


def test_the_peak_cut_is_at_most_the_power_everywhere():
    """Der Netzbezug sinkt in jeder Viertelstunde um höchstens P: die Monatsspitze mit LP liegt nie unter (Spitze ohne Speicher − P)."""
    for blk in KAPAZITAET:
        for r in blk["rows"]:
            assert r["peak"] >= r["peak_none"] - blk["power"] - 1e-6
    for seed, power in ((1, 25.0), (2, 50.0), (3, 100.0)):
        m = S.make_month(seed)
        s = A.solve_month(m, 200.0, power, A.Prices())
        assert s.peak >= m.net.max() - power - 1e-6


def _dauer_rows(kwp, power):
    return next(b for b in DAUER if b["kwp"] == kwp and b["power"] == power)["rows"]


def test_knee_depends_on_peak_duration():
    cells = {(kwp, power): [r["knee_hours"] for r in _dauer_rows(kwp, power)] for kwp, power in ((PV, 50.0), (NOPV, 50.0), (NOPV, 25.0), (NOPV, 100.0))}
    assert cells[(PV, 50.0)] == [0.5, 0.5, 1.0, 1.0, 3.0] and cells[(NOPV, 50.0)] == [0.5, 0.5, 0.75, 2.0, 3.0]
    assert cells[(NOPV, 25.0)] == [0.25, 0.5, 0.5, 1.5, 1.5] and cells[(NOPV, 100.0)] == [3.0, 3.0, 2.0, 3.0, 3.0]
    assert [r["run_h"] for r in _dauer_rows(PV, 50.0)] == list(C.RUN_H_SWEEP)
    assert sum(c[-1] > c[0] for c in cells.values()) == 3                     # Laufzeit 3 h gegen 0,25 h: höheres Knie in 3 von 4
    assert sum(h == 2.0 for c in cells.values() for h in c) == 2 and sum(len(c) for c in cells.values()) == 20
    events = [round(r["event_h"], 2) for r in _dauer_rows(PV, 50.0)]
    assert events == [0.25, 0.28, 0.50, 0.69, 1.02]
    _in_readme("**Ja, in 3 von 4 Konfigurationen** beim Vergleich der Randlaufzeiten")
    _in_readme("0,5 → 3 mit PV bei 50 kW, 0,5 → 3 ohne PV bei 50 kW, 0,25 → 1,5 ohne PV bei 25 kW")
    _in_readme("bei 100 kW ohne PV nicht (3 → 3, dazwischen 2 bei 1 h Laufzeit")
    _in_readme("Der Wert „2 Stunden Volllast“ kommt in 2 von 20 Zellen vor")


def test_knee_resample_for_the_two_extreme_run_times(monkeypatch):
    monkeypatch.setattr(C, "CAP_HOURS", (0.25, 0.5, 1.5, 8.0))
    rows = E.sweep_duration(E.Settings(power=25.0, kwp=NOPV), run_hs=(0.25, 3.0))
    assert [r["knee_hours"] for r in rows] == [0.25, 1.5]
    assert [round(r["event_h"], 2) for r in rows] == [0.25, 1.02]


def _plan(kwp, reserve, kind, mode):
    sh = E.planner_shares_from_measurements(PROGNOSE, LUECKE, kwp, reserve)
    return sh[(kind, mode)]


def test_forecast_planners_versus_rule():
    cells = [(kwp, res, kind, mode) for kwp in (PV, NOPV) for res in ("endwert", 1.0) for kind in ("persistenz", "klimatologie") for mode in ("tag", "neu")]
    rule = {kwp: _sav(kwp, "fest").sum() / _lp(kwp).sum() for kwp in (PV, NOPV)}
    assert len(cells) == 16 and all(_plan(*c)["share"] < rule[c[0]] for c in cells)        # 16 von 16 unter der Regel
    best = {kwp: max(_plan(*c)["share"] for c in cells if c[0] == kwp) for kwp in (PV, NOPV)}
    assert _de(100 * best[PV]) == "53" and _de(100 * best[NOPV]) == "86" and _de(100 * rule[PV]) == "73" and _de(100 * rule[NOPV]) == "92"
    assert _plan(PV, 1.0, "klimatologie", "neu")["share"] == best[PV] and _plan(NOPV, 1.0, "persistenz", "neu")["share"] == best[NOPV]
    perfect = [_plan(kwp, res, "perfekt", mode)["share"] for kwp in (PV, NOPV) for res in ("endwert", 1.0) for mode in ("tag", "neu")]
    assert len(perfect) == 8 and (_de(100 * min(perfect), 1), _de(100 * max(perfect), 1)) == ("98,6", "99,5")
    _in_readme("**jeder Planer unter der vorab abgestimmten Schwellenregel**")
    _in_readme("bester Wert mit PV 53 % (Neuplanen, Klimatologie, Reserve 1,00 €/kWh) gegen 73 %, ohne PV 86 % (Neuplanen, Persistenz, Reserve 1,00 €/kWh) gegen 92 %")
    _in_readme("zwischen 98,6 und 99,5 % des LP")
    _in_readme("hier sind es 16 von 16 Zellen")
    per_rule = [r["fest"]["saving"] / r["LP"]["saving"] for r in _rows(NOPV)]
    per_planner = _plan(NOPV, 1.0, "persistenz", "neu")["per_month"]
    assert sum(p > f for p, f in zip(per_planner, per_rule)) == 2                      # der beste Planer ohne PV liegt in 2 von 6 Monaten über der Regel
    spread = max(per_planner) - min(per_planner)
    assert rule[NOPV] - best[NOPV] < spread                                            # Abstand kleiner als die Streuung zwischen den Monaten
    _in_readme("der beste Planer liegt dort in 2 von 6 Monaten über der Regel")


def test_replanning_versus_open_day_plan():
    cells = [(kwp, res, kind) for kwp in (PV, NOPV) for res in ("endwert", 1.0) for kind in ("persistenz", "klimatologie")]
    tag_max = max(_plan(k, r, kind, "tag")["share"] for k, r, kind in cells)
    assert _de(100 * tag_max) == "6"                                                  # höchstens 6 % des LP
    assert (_de(100 * _plan(PV, "endwert", "persistenz", "tag")["share"]), _de(100 * _plan(PV, 1.0, "persistenz", "tag")["share"])) == ("-19", "-20")
    far = [(k, r, kind) for k, r, kind in cells if _plan(k, r, kind, "neu")["share"] - _plan(k, r, kind, "tag")["share"] > 0.25]
    assert len(far) == 6
    for k, r, kind in far:
        assert all(n > t for n, t in zip(_plan(k, r, kind, "neu")["per_month"], _plan(k, r, kind, "tag")["per_month"]))
    rest = [c for c in cells if c not in far]
    assert {(c[0], c[1]) for c in rest} == {(NOPV, "endwert")}
    for c in rest:
        assert all(-0.015 < _plan(*c, mode)["share"] < -0.005 for mode in ("tag", "neu"))     # beide bei etwa −1 %
    _in_readme("höchstens 6 % des LP (mit PV und Persistenz −19 % und −20 %")
    _in_readme("Das Neuplanen liegt in 6 von 8 Zellen um mehr als 25 Punkte darüber und in diesen 6 Zellen in allen 6 Monaten über dem Tagesplan")


def test_reserve_value_matters():
    assert _de(100 * _plan(NOPV, "endwert", "persistenz", "neu")["share"]) == "-1" and _de(100 * _plan(NOPV, 1.0, "persistenz", "neu")["share"]) == "86"
    per = _plan(NOPV, 1.0, "persistenz", "neu")["per_month"]
    assert (_de(100 * min(per)), _de(100 * max(per))) == ("59", "99")
    per = _plan(NOPV, 1.0, "klimatologie", "neu")["per_month"]
    assert (_de(100 * min(per)), _de(100 * max(per))) == ("17", "99")
    _in_readme("mit Persistenz −1 % des LP (nichts), mit 1,00 €/kWh 86 %; je Monat von 59 % bis 99 %")
    _in_readme("zwischen 17 % und 99 %")


def test_open_day_plan_resample_matches_the_measurement_within_a_band():
    """Der offene Tagesplan ist schnell genug zum Nachrechnen (etwa 1 s je Fall); das Neuplanen im Viertelstundentakt nicht (rund 30 s)."""
    prices = A.Prices()
    for kwp, kind in ((NOPV, "persistenz"), (PV, "klimatologie")):
        m = S.make_month(1, C.DEFAULT_RUN_H, kwp)
        base = A.schedule_cost(m, A.no_storage(m), prices)["total"]
        s = PL.run_planner(m, 100.0, 50.0, prices, kind, "tag", 1.0)
        ref = next(r for r in PROGNOSE if r["kwp"] == kwp and r["reserve"] == 1.0 and r["kind"] == kind and r["mode"] == "tag" and r["seed"] == 1)
        assert base - A.schedule_cost(m, s, prices)["total"] == pytest.approx(ref["saving"], abs=0.5)


def test_replanning_on_a_short_slice_is_feasible_and_never_better_than_the_lp():
    m = S.make_month(1, kwp=NOPV)
    cut = 3 * 96
    short = S.Month(m.load[:cut], m.pv[:cut], m.hist_load, m.hist_pv, m.seed, m.mean_run_h, m.kwp)
    prices = A.Prices()
    base = A.schedule_cost(short, A.no_storage(short), prices)["total"]
    lp = base - A.schedule_cost(short, A.solve_month(short, 100.0, 50.0, prices), prices)["total"]
    s = PL.run_planner(short, 100.0, 50.0, prices, "perfekt", "neu", 1.0, replan_every=4)
    saving = base - A.schedule_cost(short, s, prices)["total"]
    assert (s.soc >= -1e-9).all() and (s.soc <= 100.0 + 1e-9).all() and saving <= lp + 0.05


def test_the_readme_test_count_matches_the_suite():
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", str(ROOT / "tests")],
                         capture_output=True, text=True, cwd=ROOT, timeout=300).stdout
    count = int(re.search(r"(\d+) tests? collected", out).group(1))
    assert f"Die Suite hat **{count} Tests**" in README
