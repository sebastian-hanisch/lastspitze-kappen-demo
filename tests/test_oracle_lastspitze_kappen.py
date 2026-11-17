"""Orakel-Tests: Speicher-LP mit Monatsspitze gegen unabhängige Rechenwege (DEMO-PLAYBOOK §12).

1. Kleinste erreichbare Spitze: LP gegen eine Bisektion über die Spitzenhöhe mit Vorwärtssimulation (ein maximal geladener Speicher
   dominiert jeden anderen, darum ist die Simulation exakt). Dieser Weg benutzt weder linprog noch lsk_algorithm.
2. Gesamtkosten: LP gegen Aufzählung aller Fahrpläne auf einem feinen Raster (Mini-Instanz, Wirkungsgrad 1).
3. Handrechnung (Zwei-Stunden-Beispiel).
4. Eigenschaften: Bilanz, Ladestand in den Grenzen, Kosten LP ≤ jede Regel ≤ ohne Speicher (Leistungsgrenze), Ersparnis konkav und
   nicht fallend in Kapazität und Leistung; die Schwellenregel mit der Spitze der Bisektion hält diese Spitze (ohne PV).
"""

import itertools

import numpy as np
import pytest

import lsk_algorithm as A
import lsk_constants as C
import lsk_scenario as S

DT = 0.25
ETA_LEG = C.ETA_ROUND_TRIP**0.5


# --- unabhängiges Orakel: Bisektion über die Spitzenhöhe -----------------------------------------------------------------------------------

def _feasible(net, cap, power, theta, eta_leg):
    """Kann der Netzbezug in jeder Viertelstunde auf theta begrenzt werden? Vorwärts: über theta entladen, sonst so viel wie möglich laden."""
    soc = 0.0
    for x in net:
        if x > theta:
            need = x - theta
            if need > power + 1e-12 or need * DT / eta_leg > soc + 1e-12:
                return False
            soc -= need * DT / eta_leg
        else:
            ch = min(power, theta - x, (cap - soc) / (eta_leg * DT))
            soc += eta_leg * ch * DT
    return True


def _min_peak(net, cap, power, eta_leg=ETA_LEG):
    lo, hi = 0.0, max(float(np.max(net)), 0.0)
    for _ in range(70):
        mid = 0.5 * (lo + hi)
        if _feasible(net, cap, power, mid, eta_leg):
            hi = mid
        else:
            lo = mid
    return hi


def _lp_peak(net, cap, power):
    s = A.solve_lp(net, cap, power, A.Prices(buy=0.0, sell=0.0, peak=1.0), tie=0.0)
    return s.peak


def test_oracle_bisection_on_a_handmade_example():
    """Handrechnung: Wirkungsgrad 1, Last 10 kW, dann zwei Viertelstunden mit 70 kW: laden 20 kW über vier Viertelstunden (20 kWh/…) → Spitze 30 kW."""
    net = np.array([10.0, 10, 10, 10, 70, 70, 10, 10])
    assert _min_peak(net, cap=100.0, power=100.0, eta_leg=1.0) == pytest.approx(30.0, abs=1e-9)
    assert _min_peak(net, cap=100.0, power=100.0, eta_leg=1.0) == pytest.approx(30.0, abs=1e-9)


def test_lp_equals_bisection_on_random_net_loads_with_pv_surplus():
    rng = np.random.default_rng(7)
    worst = 0.0
    for _ in range(40):
        t = int(rng.integers(40, 150))
        net = rng.uniform(-30, 120, t) * (rng.random(t) < 0.9) + rng.uniform(0, 60, t) * (rng.random(t) < 0.1)
        cap = float(rng.choice([5.0, 25.0, 60.0, 150.0]))
        power = float(rng.choice([10.0, 25.0, 60.0]))
        worst = max(worst, abs(_lp_peak(net, cap, power) - _min_peak(net, cap, power)))
    assert worst < 1e-6


def test_lp_equals_bisection_on_generated_months():
    for seed, (power, cap) in zip((1, 2, 3, 4, 5), ((25, 50), (50, 100), (100, 200), (50, 25), (100, 400))):
        net = S.make_month(seed, kwp=0.0).net
        assert _lp_peak(net, float(cap), float(power)) == pytest.approx(_min_peak(net, float(cap), float(power)), abs=1e-6)


def test_the_threshold_rule_with_the_bisection_peak_holds_that_peak_without_pv():
    """Ohne PV ist die Schwellenregel mit θ = kleinste erreichbare Spitze und ρ = 1 (laden bis voll) die Vorwärtssimulation des Orakels."""
    for seed, (power, cap) in zip((1, 2, 3), ((50.0, 100.0), (25.0, 50.0), (100.0, 100.0))):
        net = S.make_month(seed, kwp=0.0).net
        theta = _min_peak(net, cap, power)
        s = A.simulate_rule(net, cap, power, theta + 1e-9, 1.0)
        assert s.peak <= theta + 1e-6


# --- Gesamtkosten gegen Aufzählung (Mini-Instanz, Wirkungsgrad 1) ---------------------------------------------------------------------------

def _enumerate_min_cost(net, cap, power, buy, sell, peak_price, step):
    """Beste Gesamtkosten über alle Lade-/Entladefolgen auf einem Raster der Schrittweite `step` kW (b > 0 laden, b < 0 entladen; η = 1)."""
    levels = np.arange(-power, power + 1e-9, step)
    grids = np.array(list(itertools.product(levels, repeat=len(net))))
    soc = np.cumsum(grids * DT, axis=1)
    ok = (soc >= -1e-9).all(axis=1) & (soc <= cap + 1e-9).all(axis=1)
    g, s_end = grids[ok], soc[ok][:, -1]
    flow = net[None, :] + g
    imp, exp = np.maximum(flow, 0.0), np.maximum(-flow, 0.0)
    cost = DT * buy * imp.sum(1) - DT * sell * exp.sum(1) + peak_price * imp.max(1) - buy * s_end
    return float(cost.min())


def test_lp_cost_equals_enumeration_on_mini_instances(monkeypatch):
    """Vier Viertelstunden, ganzzahlige Last, Leistung 1 kW, Raster 1/12 kW: das LP-Optimum liegt in 100 von 100 Zufallsinstanzen
    (Scratch-Lauf) auf dem Raster; hier 12 feste Instanzen. Wirkungsgrad 1 (der Rasterweg kennt keine Verluste)."""
    monkeypatch.setattr(A, "ETA_LEG", 1.0)
    rng = np.random.default_rng(5)
    for _ in range(12):
        net = rng.integers(-2, 7, 4).astype(float)
        cap = float(rng.choice([0.5, 1.0]))
        buy, sell, peak_price = (float(rng.choice(v)) for v in ([0.1, 0.2, 0.3], [0.0, 0.05, 0.1], [1.0, 4.0, 10.0]))
        prices = A.Prices(buy=buy, sell=sell, peak=peak_price)
        s = A.solve_lp(net, cap, 1.0, prices, tie=0.0)
        lp = A.bill(s.imp, s.exp, float(s.soc[-1]), prices)["total"]
        assert lp == pytest.approx(_enumerate_min_cost(net, cap, 1.0, buy, sell, peak_price, 1.0 / 12.0), abs=1e-9)


def test_hand_calculation_cost_on_the_two_hour_example(monkeypatch):
    """Zwei-Stunden-Beispiel von Hand: 10 kW, 4 × 10 kW, 2 × 70 kW, 2 × 10 kW (η = 1). Spitze 30 kW statt 70 kW:
    Energie 200 kW·Viertelstunden · 0,25 h · 0,20 EUR = 10 EUR bleibt gleich, Leistungspreis 10 EUR/kW: 700 EUR → 300 EUR."""
    monkeypatch.setattr(A, "ETA_LEG", 1.0)
    net = np.array([10.0, 10, 10, 10, 70, 70, 10, 10])
    prices = A.Prices(buy=0.20, sell=0.0, peak=10.0)
    s = A.solve_lp(net, 100.0, 100.0, prices, tie=0.0)
    c = A.bill(s.imp, s.exp, float(s.soc[-1]), prices)
    assert c["peak"] == pytest.approx(30.0, abs=1e-6)
    assert c["power"] == pytest.approx(300.0, abs=1e-5)
    assert c["energy"] == pytest.approx(10.0, abs=1e-6)
    base = A.bill(*(lambda n: (np.maximum(n, 0.0), np.maximum(-n, 0.0), 0.0))(net), prices)
    assert base["total"] == pytest.approx(710.0, abs=1e-9)


# --- Eigenschaften -------------------------------------------------------------------------------------------------------------------------

def _check_feasible(net, s, cap, power):
    flow = net + s.ch - s.dis
    assert np.allclose(s.imp - s.exp, flow, atol=1e-6)                               # Bilanz
    assert (s.imp >= -1e-9).all() and (s.exp >= -1e-9).all()
    assert (s.ch >= -1e-9).all() and (s.ch <= power + 1e-6).all() and (s.dis >= -1e-9).all() and (s.dis <= power + 1e-6).all()
    soc = np.concatenate([[0.0], np.cumsum(ETA_LEG * s.ch * DT - s.dis * DT / ETA_LEG)])
    assert np.allclose(soc, s.soc, atol=1e-6) and (soc >= -1e-6).all() and (soc <= cap + 1e-6).all()   # Ladestand aus der Zustandsgleichung


def test_every_schedule_is_feasible_and_the_lp_is_cheapest():
    prices = A.Prices()
    tune = [S.make_month(s) for s in C.TUNE_SEEDS]
    for seed in (1, 2):
        m = S.make_month(seed)
        base = A.schedule_cost(m, A.no_storage(m), prices)
        lp = A.solve_month(m, 100.0, 50.0, prices)
        _check_feasible(m.net, lp, 100.0, 50.0)
        schedules = {"R0": A.rule_r0(m, 100.0, 50.0),
                     "fest": A.rule_theta_fixed(m, 100.0, 50.0, prices, tune)[0],
                     "Nachsicht": A.rule_theta_hindsight(m, 100.0, 50.0, prices)[0]}
        c_lp = A.schedule_cost(m, lp, prices)["total"]
        for name, s in schedules.items():
            _check_feasible(m.net, s, 100.0, 50.0)
            c = A.schedule_cost(m, s, prices)
            assert c_lp <= c["total"] + 0.05, name                                        # LP optimal (Gleichstandsterm: höchstens 0,05 EUR)
            assert c["peak"] <= base["peak"] + 1e-6 or name == "R0", name                  # Spitze nie über der ohne Speicher (R0 darf wegen des Ladens)


def test_savings_are_nondecreasing_and_concave_in_capacity_and_power():
    prices = A.Prices()
    m = S.make_month(3)
    base = A.schedule_cost(m, A.no_storage(m), prices)["total"]

    def saving(cap, power):
        return base - A.schedule_cost(m, A.solve_month(m, cap, power, prices), prices)["total"]

    for fixed, grid, vary_cap in ((50.0, (0.0001, 25.0, 50.0, 100.0, 200.0), True), (100.0, (0.0001, 25.0, 50.0, 100.0), False)):
        values = [saving(g, fixed) if vary_cap else saving(fixed, g) for g in grid]
        slopes = np.diff(values) / np.diff(grid)
        assert (np.diff(values) >= -1e-6).all()
        assert (np.diff(slopes) <= 1e-6).all()
