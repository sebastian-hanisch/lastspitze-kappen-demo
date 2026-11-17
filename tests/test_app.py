"""End-to-end Smoke-Test via Streamlits AppTest: lädt app.py mit den Standardeinstellungen, klickt jeden Preset-Button, fährt jeden Slider an seine
Grenzen und prüft, dass kein Python-Fehler auftritt (insbesondere `StreamlitDuplicateElementId` bei Charts mit gleichem Inhalt und Fehler bei
Reglern an der Grenze). Die schweren Knöpfe (Mittel über sechs Monate, Spitzendauer-Sweep, Planer) laufen mit verkleinerten Messmonaten."""

import os

import pytest
from streamlit.testing.v1 import AppTest

import lsk_constants as C
import lsk_planner as PL

APP_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")
TIMEOUT = int(os.environ.get("APPTEST_TIMEOUT", "300"))
HEAVY = ("sweep6_start", "dur_start", "fc_start")   # Schlüssel der Knöpfe mit langer Rechenzeit


def _fresh_app() -> AppTest:
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=TIMEOUT)
    assert not at.exception, [str(e) for e in at.exception]
    return at


def test_app_loads_without_exception():
    at = _fresh_app()
    assert at.title and at.metric
    assert [e for e in at.expander if e.label == "📐 Mathematische Formulierung"]                        # per Titel, nie per Index


def test_every_light_button_click_does_not_raise():
    labels = [(b.key, b.label) for b in _fresh_app().button]
    assert labels, "keine Buttons gefunden"
    for index, (key, label) in enumerate(labels):
        if key in HEAVY:
            continue
        at = _fresh_app()
        at.button[index].click().run(timeout=TIMEOUT)
        assert not at.exception, (label, [str(e) for e in at.exception])


def test_every_slider_at_its_min_and_max_does_not_raise():
    labels = [s.label for s in _fresh_app().slider]
    assert labels, "keine Slider gefunden"
    for index, label in enumerate(labels):
        for edge in ("min", "max"):
            at = _fresh_app()
            slider = at.slider[index]
            value = slider.min if edge == "min" else slider.max
            if isinstance(slider.value, int):
                value = int(value)
            slider.set_value(value).run(timeout=TIMEOUT)
            assert not at.exception, (label, edge, [str(e) for e in at.exception])


@pytest.mark.parametrize("name", list(C.PRESETS))
def test_every_preset_runs_and_reports_a_verdict(name):
    at = _fresh_app()
    at.sidebar.button(key=f"preset_{name}").click().run(timeout=TIMEOUT)
    assert not at.exception, [str(e) for e in at.exception]
    texts = [x.value for x in list(at.success) + list(at.info) + list(at.warning)]
    assert any("Der exakte Plan" in t or "senkt die Monatsrechnung in diesem Monat nicht" in t for t in texts)


def test_heavy_buttons_work_with_reduced_months(monkeypatch):
    monkeypatch.setattr(C, "SWEEP_SEEDS", (1,))
    monkeypatch.setattr(C, "RUN_H_SWEEP", (0.5, 2.0))
    monkeypatch.setattr(PL, "REPLAN_EVERY", 96)                      # Neuplanen einmal je Tag statt je Viertelstunde
    at = _fresh_app()
    at.button(key="sweep6_start").click().run(timeout=TIMEOUT)
    assert not at.exception, [str(e) for e in at.exception]
    at.button(key="dur_start").click().run(timeout=TIMEOUT)
    assert not at.exception, [str(e) for e in at.exception]
    at.button(key="fc_start").click().run(timeout=TIMEOUT)
    assert not at.exception, [str(e) for e in at.exception]
    assert any("Mit der Prognose" in x.value for x in list(at.success) + list(at.info))


def test_loading_the_default_preset_after_another_one_resets_every_slider():
    """Ein Preset nennt nur die Regler, die es ändert; die übrigen müssen beim Laden auf den Standard zurück (sonst bliebe das vorige Preset teilweise stehen)."""
    at = _fresh_app()
    at.sidebar.button(key="preset_Kleine Leistung, große Kapazität").click().run(timeout=TIMEOUT)
    at.sidebar.button(key="preset_Ohne PV: nur Spitzenkappen").click().run(timeout=TIMEOUT)
    assert at.sidebar.slider(key="kwp_slider").value == 0.0 and at.sidebar.slider(key="cap_slider").value == C.DEFAULT_CAP     # Kapazität und Leistung zurück
    assert at.sidebar.slider(key="power_slider").value == C.DEFAULT_POWER
    at.sidebar.button(key=f"preset_{C.STANDARD_PRESET}").click().run(timeout=TIMEOUT)
    assert at.sidebar.slider(key="kwp_slider").value == C.DEFAULT_KWP and not at.exception
