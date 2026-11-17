"""Verdikte an von Hand gesetzten Werten (DEMO-PLAYBOOK §12): jede Zahl im Text und jede Schwelle der Art steht hier.

Ein Verdikt ist eine reine Funktion (Art, Text) und bekommt Kosten und Zeilen, nicht Seeds."""

import pytest

import lsk_evaluation as ev


def _analysis(totals: dict, peaks: dict | None = None) -> ev.Analysis:
    """Handgesetzte Kosten: ohne Speicher 1000 EUR (Spitze 100 kW), LP 600 EUR (Spitze 50 kW); R0, fest, nachsicht aus `totals`."""
    peaks = {ev.M_NONE: 100.0, ev.M_R0: 100.0, ev.M_FIX: 60.0, ev.M_HIND: 55.0, ev.M_LP: 50.0, **(peaks or {})}
    all_totals = {ev.M_NONE: 1000.0, ev.M_LP: 600.0, **totals}
    costs = {k: dict(total=v, peak=peaks[k], power=0.0, energy=v, end_value=0.0) for k, v in all_totals.items()}
    return ev.Analysis(ev.Settings(cap=100.0, power=50.0), None, {}, costs, {}, {})


def test_main_verdict_names_saving_peaks_and_shares():
    a = _analysis({ev.M_R0: 900.0, ev.M_FIX: 640.0, ev.M_HIND: 620.0})   # LP spart 400, R0 100 (25 %), fest 360 (90 %), nachsicht 380 (95 %)
    kind, text = ev.verdict_main(a)
    assert kind == "success"
    assert "spart 400 €" in text and "um 50 %" in text and "von 100 auf 50 kW" in text
    assert "R0 erreicht 25 %" in text and "Schwellenregel 90 %" in text and "im Nachhinein abgestimmte 95 %" in text


def test_main_verdict_thresholds_follow_the_shown_percentage():
    """Die Art hängt am gezeigten, gerundeten Prozentwert der vorab abgestimmten Regel: 90 % und mehr „success“, 60 bis 89 % „info“, darunter „warning“."""
    def kind(fix_total):
        return ev.verdict_main(_analysis({ev.M_R0: 900.0, ev.M_FIX: fix_total, ev.M_HIND: 620.0}))[0]

    assert kind(640.0) == "success"      # 360 von 400 = 90 %
    assert kind(641.0) == "success"      # 89,75 % wird als 90 % gezeigt
    assert kind(644.0) == "info"         # 89 %
    assert kind(760.0) == "info"         # genau 60 %
    assert kind(761.0) == "info"         # 59,75 % wird als 60 % gezeigt
    assert kind(764.0) == "warning"      # 59 %


def test_main_verdict_without_lp_saving_is_info_and_names_the_amount():
    a = _analysis({ev.M_R0: 1000.0, ev.M_FIX: 1000.0, ev.M_HIND: 1000.0})
    a.costs[ev.M_LP]["total"] = 999.8                                  # spart 0,20 €: unter der Schwelle von 0,50 €
    kind, text = ev.verdict_main(a)
    assert kind == "info" and "0,20 €" in text and "senkt die Monatsrechnung in diesem Monat nicht" in text


def test_share_is_none_below_half_a_euro_and_defined_above():
    a = _analysis({ev.M_R0: 900.0, ev.M_FIX: 640.0, ev.M_HIND: 620.0})
    assert a.share(ev.M_R0) == pytest.approx(0.25)
    a.costs[ev.M_LP]["total"] = 999.6
    assert a.share(ev.M_R0) is None


def test_knee_picks_the_smallest_capacity_reaching_90_percent_of_the_largest():
    rows = [dict(cap=10.0, hours=0.5, power_saving=50.0), dict(cap=20.0, hours=1.0, power_saving=89.0),
            dict(cap=30.0, hours=1.5, power_saving=90.0), dict(cap=40.0, hours=2.0, power_saving=100.0)]
    k = ev.knee(rows)
    assert k["cap"] == 30.0 and k["hours"] == 1.5 and k["saving_max"] == 100.0 and k["cap_top"] == 40.0     # 90 ist genau 90 % von 100: inklusive


def test_knee_is_none_when_the_battery_saves_nothing():
    rows = [dict(cap=10.0, hours=0.5, power_saving=0.0), dict(cap=20.0, hours=1.0, power_saving=0.3)]
    assert ev.knee(rows)["cap"] is None
    kind, text = ev.verdict_knee(ev.knee(rows), 20.0)
    assert kind == "info" and "kein Knie" in text


def test_knee_verdict_names_capacity_hours_and_power():
    k = dict(cap=50.0, hours=1.0, saving_max=500.0, cap_top=400.0)
    kind, text = ev.verdict_knee(k, 50.0)
    assert kind == "info" and "90 % der Ersparnis aus der Spitze (Leistungspreis), die mit 400 kWh erreicht wird, sind bei 50 kWh erreicht" in text
    assert "1 Stunden Volllast (C = 1 · P bei P = 50 kW)" in text
    assert "0,5 Stunden" in ev.verdict_knee(dict(cap=25.0, hours=0.5, saving_max=1.0, cap_top=400.0), 50.0)[1]   # Dezimalkomma


def test_marginal_gains_are_slopes_between_grid_points():
    rows = [dict(cap=10.0, **{ev.M_LP: 100.0}), dict(cap=30.0, **{ev.M_LP: 140.0}), dict(cap=60.0, **{ev.M_LP: 140.0})]
    g = ev.marginal_gains(rows)
    assert [x["je_kwh"] for x in g] == pytest.approx([10.0, 2.0, 0.0])
    assert [(x["von"], x["bis"]) for x in g] == [(0.0, 10.0), (10.0, 30.0), (30.0, 60.0)]


def test_duration_verdict_compares_the_shortest_and_longest_run():
    rows = [dict(run_h=0.25, knee_hours=0.5, event_h=0.25), dict(run_h=1.0, knee_hours=1.0, event_h=0.5), dict(run_h=3.0, knee_hours=3.0, event_h=1.0)]
    kind, text = ev.verdict_duration(rows)
    assert kind == "info" and "bei Laufzeit 0,25 h bei 0,5 Stunden Volllast" in text and "bei 3 h bei 3 Stunden" in text
    assert "0,25 h und 1,00 h" in text
    same = [dict(run_h=0.25, knee_hours=2.0, event_h=0.25), dict(run_h=3.0, knee_hours=2.0, event_h=1.0)]
    kind, text = ev.verdict_duration(same)
    assert kind == "success" and "gleich bei 2 Stunden Volllast" in text and "auch dazwischen ändert es sich in diesem Raster nicht" in text
    middle = [dict(run_h=0.25, knee_hours=3.0, event_h=0.25), dict(run_h=1.0, knee_hours=2.0, event_h=0.5), dict(run_h=3.0, knee_hours=3.0, event_h=1.0)]
    kind, text = ev.verdict_duration(middle)
    assert kind == "info" and "gleich bei 3 Stunden Volllast" in text and "dazwischen liegt es zwischen 2 und 3 Stunden" in text       # kein „hängt nicht an“
    falling = [dict(run_h=0.25, knee_hours=2.0, event_h=0.25), dict(run_h=3.0, knee_hours=1.0, event_h=1.0)]
    kind, text = ev.verdict_duration(falling)
    assert kind == "info" and "Das Knie sinkt mit der Spitzendauer" in text and "Laufzeit 0,25 h bei 2 Stunden" in text and "bei 3 h bei 1 Stunden" in text
    assert ev.verdict_duration([dict(run_h=1.0, knee_hours=None, event_h=0.5), dict(run_h=2.0, knee_hours=None, event_h=0.7)])[0] == "info"


def test_planner_verdict_compares_with_the_rule_and_names_the_shares():
    res = dict(lp=500.0, tag=0.10, neu=0.40)
    kind, text = ev.verdict_planner(res, 0.78, "Persistenz")
    assert kind == "info" and "„Persistenz“" in text and "Tagesplan 10 %" in text and "Neuplanen 40 %" in text and "Schwellenregel ohne Prognose erreicht 78 %" in text
    assert ev.verdict_planner(dict(lp=500.0, tag=0.10, neu=0.81), 0.78, "perfekte Prognose")[0] == "success"
    assert ev.verdict_planner(dict(lp=500.0, tag=0.10, neu=0.80), 0.78, "perfekte Prognose")[0] == "info"     # genau 2 Punkte Vorsprung zählen nicht
    assert ev.verdict_planner(dict(lp=500.0, tag=0.10, neu=0.40), None, "Persistenz")[1].endswith("Das gilt für diesen einen Monat.")


def test_german_decimal_comma():
    assert ev.de(0.5) == "0,5" and ev.de(0.25, 2) == "0,25" and ev.de(3.0) == "3" and ev.de(1.234, 1) == "1,2"
