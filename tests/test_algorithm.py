"""Kern gegen Handrechnung: Abrechnung, Regeln, Szenario-Generator, Prognosen und Planer (DEMO-PLAYBOOK §1b).

Die Mini-Instanz `mini` (conftest): 10 kW, 4 × 10 kW, 2 × 70 kW, 2 × 10 kW in Viertelstunden; die Rechnung steht jeweils im Test."""

import numpy as np
import pytest

import lsk_algorithm as A
import lsk_constants as C
import lsk_planner as PL
import lsk_scenario as S


@pytest.fixture
def loss_free(monkeypatch):
    """Wirkungsgrad 1, damit die Handrechnung ohne Wurzeln aufgeht."""
    monkeypatch.setattr(A, "ETA_LEG", 1.0)


def test_bill_by_hand_without_storage(mini):
    # Energie: 200 kW · 0,25 h · 0,20 EUR = 10 EUR; Leistungspreis: 70 kW · 10 EUR = 700 EUR
    c = A.bill(np.maximum(mini, 0.0), np.zeros(len(mini)), 0.0, A.Prices(buy=0.20, sell=0.07, peak=10.0))
    assert c["energy"] == pytest.approx(10.0) and c["power"] == pytest.approx(700.0) and c["total"] == pytest.approx(710.0)
    assert c["peak"] == pytest.approx(70.0)


def test_bill_counts_export_and_end_value():
    # Einspeisung 4 kW · 0,25 h · 0,07 EUR = 0,07 EUR Erlös; Restladung 10 kWh · (√0,9 · 0,20) EUR
    prices = A.Prices(buy=0.20, sell=0.07, peak=10.0)
    c = A.bill(np.array([0.0]), np.array([4.0]), 10.0, prices)
    assert c["energy"] == pytest.approx(-0.07)
    assert c["end_value"] == pytest.approx(10.0 * 0.90**0.5 * 0.20)
    assert c["total"] == pytest.approx(-0.07 - 10.0 * 0.90**0.5 * 0.20)


def test_threshold_rule_by_hand(mini, loss_free):
    """θ = 30, ρ = 1, C = P = 100, η = 1: vier Viertelstunden laden 20 kW (5 kWh je Viertelstunde), zwei entladen 40 kW (10 kWh je Viertelstunde),
    danach wieder laden; der Bezug ist überall 30 kW."""
    s = A.simulate_rule(mini, 100.0, 100.0, 30.0, 1.0)
    assert s.ch.tolist() == [20, 20, 20, 20, 0, 0, 20, 20] and s.dis.tolist() == [0, 0, 0, 0, 40, 40, 0, 0]
    assert s.imp.tolist() == [30] * 8
    assert s.soc.tolist() == pytest.approx([0, 5, 10, 15, 20, 10, 0, 5, 10])


def test_r0_never_charges_without_surplus_and_cuts_no_peak(mini):
    s = A.simulate_rule(mini, 100.0, 100.0, np.inf, 0.0)
    assert s.ch.sum() == 0 and s.dis.sum() == 0 and s.peak == pytest.approx(70.0)


def test_r0_charges_from_surplus_and_serves_the_next_deficit(loss_free):
    """Überschuss 20 kW in der ersten, Bedarf 10 kW in der zweiten Viertelstunde (η = 1): 5 kWh geladen, 2,5 kWh entladen, Bezug 0."""
    s = A.simulate_rule(np.array([-20.0, 10.0]), 100.0, 100.0, np.inf, 0.0)
    assert s.ch.tolist() == [20, 0] and s.dis.tolist() == [0, 10] and s.imp.tolist() == [0, 0] and s.soc.tolist() == pytest.approx([0, 5, 2.5])


def test_rule_respects_power_and_capacity_limits(loss_free):
    s = A.simulate_rule(np.array([-100.0, -100.0, 200.0]), 10.0, 40.0, np.inf, 0.0)  # C = 10 kWh, P = 40 kW
    assert s.ch.tolist() == [40, 0, 0] and s.soc.tolist() == pytest.approx([0, 10, 10, 0]) and s.dis[2] == pytest.approx(40.0)


def test_reserve_blocks_self_use_below_the_reserve(loss_free):
    """ρ = 0,5: aus dem Netz bis 5 kWh nachladen (bei C = 10 kWh), darunter nicht für den Eigenbedarf entladen (Bezug 20 kW unter θ = 50 kW)."""
    s = A.simulate_rule(np.array([20.0, 20.0, 20.0]), 10.0, 100.0, 50.0, 0.5)
    assert s.dis.sum() == 0 and s.soc[-1] == pytest.approx(5.0) and s.imp[0] == pytest.approx(20 + 20)  # P = 100 → laden 20 kWh/h-Äquivalent


def test_make_month_shapes_and_determinism():
    a, b, other = S.make_month(1), S.make_month(1), S.make_month(2)
    assert a.slots == C.MONTH_DAYS * C.SLOTS_PER_DAY == 2880 and len(a.hist_load) == C.HISTORY_DAYS * C.SLOTS_PER_DAY == 2688
    assert np.array_equal(a.load, b.load) and np.array_equal(a.pv, b.pv)
    assert not np.array_equal(a.load, other.load)


def test_load_has_no_machines_on_weekends():
    m = S.make_month(1, kwp=0.0)
    day = m.load.reshape(30, 96)
    weekend = [5, 6, 12, 13, 19, 20, 26, 27]
    weekday = [d for d in range(28) if d not in weekend]
    assert day[weekend].max() < C.BASE_KW * 1.3                       # nur Grundlast (±3 % Rauschen: höchstens 1,3-fach)
    assert day[weekday].max() > 2 * C.BASE_KW


def test_no_pv_without_kwp_and_pv_scales_with_kwp():
    assert S.make_month(1, kwp=0.0).pv.sum() == 0
    a, b = S.make_month(1, kwp=100.0), S.make_month(1, kwp=200.0)
    assert b.pv.sum() == pytest.approx(2 * a.pv.sum()) and a.pv.max() <= 100.0 * C.PV_PERFORMANCE_RATIO * 1.05
    assert np.array_equal(a.load, b.load)                             # die Last hängt nicht an der PV-Größe


def test_peak_events_by_hand():
    ev = S.peak_events(np.array([0.0, 0.0, 100.0, 100.0, 0.0, 95.0, 0.0, 50.0]))
    assert ev["peak"] == 100.0 and ev["events"] == 2 and ev["mean_h"] == pytest.approx(0.375) and ev["max_h"] == pytest.approx(0.5) and ev["days"] == 1


def test_forecasts_use_only_known_values():
    m = S.make_month(1)
    persist = PL.forecast_net(m, "persistenz")
    assert persist[0] == pytest.approx(m.hist_load[-7 * 96] - m.hist_pv[-96])
    assert persist[1000] == pytest.approx(m.load[1000 - 7 * 96] - m.pv[1000 - 96])
    cut = 1500
    load2 = m.load.copy()
    load2[cut:] += 999.0                                            # die Zukunft ändern ...
    m2 = S.Month(load2, m.pv, m.hist_load, m.hist_pv, m.seed, m.mean_run_h, m.kwp)
    for kind in ("persistenz", "klimatologie"):
        assert np.array_equal(PL.forecast_net(m, kind)[:cut], PL.forecast_net(m2, kind)[:cut])   # ... ändert die Prognose davor nicht
    assert np.array_equal(PL.forecast_net(m, "perfekt"), m.net)


def test_climatology_repeats_weekly():
    f = PL.forecast_net(S.make_month(1), "klimatologie")
    assert np.allclose(f[:7 * 96], f[7 * 96:14 * 96]) and np.allclose(f[:96 * 2], f[7 * 96:7 * 96 + 96 * 2])


def test_planner_is_feasible_and_a_perfect_forecast_nearly_reaches_the_lp():
    m = S.make_month(1, kwp=0.0)
    prices = A.Prices()
    cap, power = 100.0, 50.0
    base = A.schedule_cost(m, A.no_storage(m), prices)["total"]
    lp = base - A.schedule_cost(m, A.solve_month(m, cap, power, prices), prices)["total"]
    s = PL.run_planner(m, cap, power, prices, "perfekt", "tag", prices.end_value)
    assert (s.soc >= -1e-9).all() and (s.soc <= cap + 1e-9).all() and (s.ch <= power + 1e-9).all() and (s.dis <= power + 1e-9).all()
    assert np.allclose(s.imp - s.exp, m.net + s.ch - s.dis, atol=1e-9)
    saving = base - A.schedule_cost(m, s, prices)["total"]
    assert 0.95 * lp <= saving <= lp + 0.05                           # die Voraussicht eines Tages genügt fast; nie besser als das LP (Gleichstandsterm: 0,05 EUR)


def test_unknown_planner_options_raise():
    m = S.make_month(1)
    with pytest.raises(ValueError):
        PL.forecast_net(m, "orakel")
    with pytest.raises(ValueError):
        PL.run_planner(m, 100.0, 50.0, A.Prices(), "perfekt", "woche", 1.0)
