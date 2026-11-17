"""Randfälle, an denen Kernroutinen erfahrungsgemäß brechen (DEMO-PLAYBOOK §12): zwei Zeitschritte, keine Kapazität, kein Überschuss, Gleichstände."""

import numpy as np
import pytest

import lsk_algorithm as A
import lsk_evaluation as ev
import lsk_scenario as S


def test_exactly_two_slots():
    """Zwei Viertelstunden: 0 kW, dann 100 kW, Batterie 10 kWh / 40 kW, Start leer. Von Hand: in der ersten Viertelstunde mit 40 kW laden (Netzbezug 40 kW,
    9,49 kWh im Speicher, unter C), in der zweiten höchstens 0,9 · 40 = 36 kW entladen: Bezug 100 − 36 = 64 kW."""
    s = A.solve_lp(np.array([0.0, 100.0]), 10.0, 40.0, A.Prices(buy=0.2, sell=0.07, peak=10.0))
    assert s.peak == pytest.approx(64.0, abs=1e-6) and s.ch[0] == pytest.approx(40.0, abs=1e-6)


def test_single_slot():
    s = A.solve_lp(np.array([50.0]), 10.0, 40.0, A.Prices())
    assert s.peak == pytest.approx(50.0) and s.ch[0] == pytest.approx(0.0) and s.dis[0] == pytest.approx(0.0)  # ohne Ladestand gibt es nichts zu entladen


def test_zero_capacity_changes_nothing():
    net = np.array([10.0, 80.0, 10.0, 80.0])
    s = A.solve_lp(net, 0.0, 40.0, A.Prices())
    assert np.allclose(s.imp, net) and s.ch.sum() == 0 and s.dis.sum() == 0


def test_zero_power_changes_nothing():
    net = np.array([10.0, 80.0, 10.0, 80.0])
    s = A.solve_lp(net, 100.0, 0.0, A.Prices())
    assert np.allclose(s.imp, net)
    r = A.simulate_rule(net, 100.0, 0.0, 30.0, 1.0)
    assert np.allclose(r.imp, net)


def test_pure_surplus_has_no_peak_and_no_import():
    s = A.solve_lp(np.full(8, -20.0), 50.0, 50.0, A.Prices())
    assert s.imp.max() == pytest.approx(0.0, abs=1e-9)


def test_peak_floor_is_respected():
    """Last 10 kW, dann 100 kW, C = P = 100. Ohne Untergrenze liegt die beste Spitze bei 109 / 1,9 = 57,37 kW (laden c = p − 10, entladen 0,9 c ≥ 100 − p).
    Mit einer bereits erreichten Monatsspitze von 70 kW kostet Bezug bis 70 kW nichts mehr: das LP lädt nur so viel, dass die zweite Viertelstunde 70 kW erreicht."""
    prices = A.Prices(buy=0.2, sell=0.0, peak=10.0)
    free = A.solve_lp(np.array([10.0, 100.0]), 100.0, 100.0, prices)
    floored = A.solve_lp(np.array([10.0, 100.0]), 100.0, 100.0, prices, peak_floor=70.0)
    assert free.peak == pytest.approx(109.0 / 1.9, abs=1e-6)
    assert floored.peak == pytest.approx(70.0, abs=1e-6)


def test_ties_charge_early():
    """Gleichstand: die Ladezeit ist für die Kosten gleichgültig; der Aufschlag auf späte Ladung lässt das LP so früh wie möglich laden."""
    net = np.array([0.0, 0.0, 0.0, 0.0, 60.0])
    s = A.solve_lp(net, 100.0, 100.0, A.Prices(buy=0.2, sell=0.0, peak=10.0))
    assert s.ch[0] >= s.ch[3] - 1e-9 and s.ch[0] > 1.0


def test_unreachable_rule_threshold_is_the_peak_itself():
    """Schwelle über der höchsten Last: nie über θ, also kein Kappen; mit ρ = 1 wird nur aus dem Netz geladen, die Spitze steigt nicht über θ."""
    net = np.array([10.0, 20.0, 30.0])
    s = A.simulate_rule(net, 100.0, 50.0, 1000.0, 1.0)
    assert s.dis.sum() == 0 and s.imp.max() <= 1000.0


def test_verdict_text_never_divides_by_zero_when_storage_saves_nothing():
    """Eine Batterie ohne Wirkung (C = 10 kWh, P = 10 kW, Last ohne Spitze) darf keinen Anteil melden."""
    m = S.make_month(1, kwp=0.0)
    flat = S.Month(np.full(m.slots, 20.0), m.pv, m.hist_load, m.hist_pv, m.seed, m.mean_run_h, 0.0)
    prices = A.Prices()
    schedules = {ev.M_NONE: A.no_storage(flat), ev.M_LP: A.solve_month(flat, 10.0, 10.0, prices)}
    schedules[ev.M_R0] = schedules[ev.M_FIX] = schedules[ev.M_HIND] = A.no_storage(flat)
    costs = {k: A.schedule_cost(flat, s, prices) for k, s in schedules.items()}
    a = ev.Analysis(ev.Settings(cap=10.0, power=10.0, kwp=0.0), flat, schedules, costs, {}, {})
    assert a.share(ev.M_LP) is None and ev.verdict_main(a)[0] == "info"
