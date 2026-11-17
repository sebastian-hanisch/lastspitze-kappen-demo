"""Presets: Vollständigkeit, gültige Werte, Standard-Preset = Standardeinstellungen, Permalink-Grenzen."""

import lsk_constants as C
import lsk_evaluation as ev
import lsk_presets as P


def test_every_preset_has_help_and_only_known_keys():
    assert set(C.PRESETS) == set(C.PRESET_HELP)
    for name, preset in C.PRESETS.items():
        assert set(preset) <= set(P.PRESET_KEYS), name
        assert C.PRESET_HELP[name]


def test_preset_values_are_inside_the_slider_bounds():
    for name, preset in C.PRESETS.items():
        for key, value in preset.items():
            spec = P.SETTING_SPECS[P.PRESET_KEYS[key]]
            assert spec.lo <= value <= spec.hi, (name, key)


def test_default_preset_equals_the_default_settings():
    assert ev.Settings(**C.PRESETS[C.STANDARD_PRESET]) == ev.Settings()
    assert next(iter(C.PRESETS)) == C.STANDARD_PRESET


def test_setting_specs_cover_every_preset_key_and_every_settings_field():
    assert set(P.PRESET_KEYS.values()) == set(P.SETTING_SPECS)
    assert set(P.PRESET_KEYS) == set(ev.Settings.__dataclass_fields__)


def test_presets_differ_from_each_other():
    settings = [ev.Settings(**p) for p in C.PRESETS.values()]
    assert len(set(settings)) == len(settings)


def test_selling_price_never_exceeds_the_buying_price_over_the_whole_slider_range():
    for buy in (C.BUY_MIN, C.DEFAULT_BUY, C.BUY_MAX):
        prices = ev.Settings(buy=buy).prices
        assert prices.sell <= prices.buy


def test_sweep_uses_the_fixed_months_and_the_tuning_months_are_different():
    assert len(C.SWEEP_SEEDS) == 6 and not set(C.SWEEP_SEEDS) & set(C.TUNE_SEEDS)
    assert C.DEFAULT_SEED in C.SWEEP_SEEDS
    rows = ev.sweep_capacity(ev.Settings(power=50.0), seeds=(1,), with_rules=False)
    assert [r["hours"] for r in rows] == list(C.CAP_HOURS) and [r["cap"] for r in rows] == [h * 50.0 for h in C.CAP_HOURS]
    assert all(r["lp_min"] <= r[ev.M_LP] <= r["lp_max"] for r in rows)


def test_standard_preset_help_names_the_actual_defaults():
    text = C.PRESET_HELP[C.STANDARD_PRESET]
    assert f"{C.DEFAULT_KWP:.0f} kWp" in text and f"{C.DEFAULT_CAP:.0f} kWh und {C.DEFAULT_POWER:.0f} kW" in text
    assert f"Maschinenlaufzeit im Mittel {C.DEFAULT_RUN_H:.0f} h" in text and f"{C.DEFAULT_PEAK_PRICE:.0f} € je kW und Monat" in text
    assert f"{C.DEFAULT_BUY:.2f}".replace(".", ",") + " € je kWh" in text
