"""Lastspitze kappen: Wie groß muss die Batterie sein? - interaktive Fall-Demo
Sebastian Hanisch - Operations Research und Machine Learning

Ein Gewerbekunde zahlt einen Leistungspreis auf die höchste Viertelstunden-Bezugsleistung des Monats. Speicher-LP mit der Monatsspitze als Variable,
einfache Regeln (Eigenverbrauch, Schwelle) und Planer mit Prognose im Vergleich. Alle Last- und PV-Daten sind erzeugt (Annahmen).

Lauffähig mit: streamlit run app.py
"""

import streamlit as st

import lsk_constants as C
import lsk_evaluation as E
import lsk_visualization as V
import modul_frisch
from lsk_layout import dunkles_design, kopf_css
from lsk_pdf_export import build_pdf
from lsk_presets import (
    bounds,
    init_session_state_defaults,
    load_permalink_settings,
    randomize_seed,
    sidebar_presets,
    sync_query_params,
)

modul_frisch.aktualisieren(__file__)  # geänderte Hilfsmodule nach einem Update neu laden (Cloud behält sie sonst bis zum Neustart)

st.set_page_config(page_title="Lastspitze kappen – Sebastian Hanisch", layout="wide")


@st.cache_data(show_spinner=False)
def _analysis(settings):
    return E.analyse(settings)


@st.cache_data(show_spinner=False)
def _sweep(settings, seeds, with_rules):
    return E.sweep_capacity(settings, seeds=seeds, with_rules=with_rules)


@st.cache_data(show_spinner=False)
def _duration(settings):
    return E.sweep_duration(settings)


@st.cache_data(show_spinner=False)
def _planner(settings, kind, reserve):
    return E.planner_shares(settings, kind, reserve)


def _pct(x):
    return "–" if x is None else f"{100 * x:.0f} %"


def _eur(x):
    return f"{x:,.0f} €".replace(",", ".")


# Fester Kopf: nur der Titel bleibt beim Scrollen oben (Stylesheet in lsk_layout.py).
st.html(kopf_css(dunkles_design()))
with st.container(key="kopf"):
    st.title("🔋 Lastspitze kappen: Wie groß muss die Batterie sein?")
st.markdown(
    """
Ein Gewerbekunde zahlt neben der Energie einen **Leistungspreis** auf die **höchste Viertelstunden-Bezugsleistung des Monats**: eine einzige Spitze kostet den ganzen Monat.
Eine Batterie kann sie kappen, wenn sie zur Spitze gefüllt ist. Die Demo fragt: **Wie viel nimmt welche Batterie von der Spitze**, **welche einfache Regel** kommt dem exakten
Plan (LP mit Voraussicht) nahe, hängt das **Knie der Kapazität** an der **Spitzendauer**, und was bringen **Prognosen**? Last und Photovoltaik sind **erzeugt** (Annahmen, keine
Messdaten): Aussagen gelten für diese Generatoren. Wer die Frage zuerst ohne Fachbegriffe verstehen will, öffnet „💬 In einfachen Worten“.

Weiter unten: die **Kernfragen** mit Messungen und der Expander **🔧 Wie wir das erreichen – vollständiger Methodenvergleich** (mit den Verfahren erklärt).
"""
)

# erklaerseite:einfach:start (erzeugt von tools/set_demo_explainer.py (Website-Repo) aus tools/content/explainers/lastspitze-kappen-erklaert.json, nicht von Hand ändern)
with st.expander("💬 In einfachen Worten"):
    st.markdown(
        """
Ein Gewerbekunde zahlt neben der Energie einen Leistungspreis auf die höchste Viertelstunden-Bezugsleistung des Monats: Eine einzige Spitze kostet den ganzen Monat. Eine Batterie kann sie kappen, wenn sie zur Spitze gefüllt ist, und das entscheidet sich Stunden vorher. Die Demo rechnet einen erzeugten Monat und vergleicht den exakten Plan, der den ganzen Monat im Voraus kennt, mit einfachen Regeln (Eigenverbrauch, Schwelle) und mit Planern, die nur eine Prognose kennen. Sie fragt auch, wie viel Kapazität die Spitze braucht und ob dieses „Knie“ an der Dauer der Spitzen hängt. Last und Photovoltaik sind erzeugt und alle Preise Annahmen: Die Zahlen gelten für diese Generatoren, nicht für einen echten Betrieb.

[Ausführlich und verständlich erklärt, mit Fachteil](https://sebastianhanisch.net/lastspitze-kappen-erklaert.html)
        """
    )
# erklaerseite:einfach:end

st.caption("🔗 Die Adresszeile oben spiegelt Ihre aktuelle Konfiguration wider – einfach kopieren, um ein Szenario zu teilen.")

load_permalink_settings()
init_session_state_defaults()

with st.sidebar:
    sidebar_presets()  # Schnellstart oben, das aktive Preset ist hervorgehoben
    st.header("⚙️ Einstellungen")
    st.markdown("**Batterie**")
    cap = st.slider("Kapazität C (kWh)", *bounds("cap_slider"), key="cap_slider", step=5.0, format="%.0f", help="Nutzbare Energie des Speichers.")
    power = st.slider("Leistung P (kW)", *bounds("power_slider"), key="power_slider", step=5.0, format="%.0f",
                      help="Höchste Lade- und Entladeleistung am Netzanschluss (AC). Umlaufwirkungsgrad fest 0,90.")
    st.markdown("**Abrechnung**")
    peak_price = st.slider("Leistungspreis (€ je kW und Monat)", *bounds("price_slider"), key="price_slider", step=0.5, format="%.1f",
                           help="Wird auf die höchste Viertelstunden-Bezugsleistung des Monats gerechnet (Annahme, kein Tarif eines Netzbetreibers).")
    buy = st.slider("Arbeitspreis (€ je kWh)", *bounds("buy_slider"), key="buy_slider", step=0.01,
                    help="Preis je bezogener kWh. Die Einspeisevergütung ist fest 0,07 €/kWh (höchstens der Arbeitspreis).")
    st.markdown("**Gewerbekunde**")
    run_h = st.slider("Spitzendauer: mittlere Maschinenlaufzeit (h)", *bounds("run_slider"), key="run_slider", step=0.25,
                      help="Die Last entsteht aus Maschinenläufen. Je länger ein Lauf im Mittel dauert, desto länger dauern die Spitzen (gemessen unter dem Ergebnis).")
    kwp = st.slider("Photovoltaik (kWp)", *bounds("kwp_slider"), key="kwp_slider", step=10.0, format="%.0f",
                    help="0 = nur Spitzenkappen. Mit PV lädt die Eigenverbrauchsregel aus dem Überschuss.")
    st.markdown("**Zufall**")
    seed = st.number_input("Zufalls-Seed des Monats", *bounds("seed_input"), key="seed_input", step=1)
    st.button("🎲 Neuen Monat erzeugen", width="stretch", on_click=randomize_seed)

sync_query_params({"cap_slider": cap, "power_slider": power, "kwp_slider": kwp, "run_slider": run_h, "price_slider": peak_price,
                   "buy_slider": buy, "seed_input": int(seed)})

settings = E.Settings(float(cap), float(power), float(kwp), float(run_h), float(peak_price), float(buy), int(seed))
with st.spinner("Rechne den Monat (LP und Regeln) …"):
    a = _analysis(settings)

# --- Ergebnis ------------------------------------------------------------------------------------------------------------------------------

st.markdown("## 🎯 Ergebnis: ein Abrechnungsmonat (30 Tage, Viertelstunden)")
m1, m2, m3, m4 = st.columns(4)
none, lp = a.costs[E.M_NONE], a.costs[E.M_LP]
# Delta immer als „mein Wert minus Referenz“; die Farbe regelt delta_color="inverse" (Vorzeichen-Falle, DEMO-PLAYBOOK §2).
m1.metric("Monatsspitze mit exaktem Plan", f"{lp['peak']:.0f} kW", delta=f"{lp['peak'] - none['peak']:+.0f} kW gegen ohne Speicher", delta_color="inverse")
m2.metric("Monatskosten mit exaktem Plan", _eur(lp["total"]), delta=f"{lp['total'] - none['total']:+,.0f} € gegen ohne Speicher".replace(",", "."), delta_color="inverse")
m3.metric("Ersparnis, exakter Plan", _eur(a.saving(E.M_LP)), delta=f"{_pct(a.share(E.M_FIX))} erreicht die vorab abgestimmte Regel", delta_color="off")
m4.metric("Monatsspitze ohne Speicher", f"{none['peak']:.0f} kW", delta=f"{none['peak'] * settings.peak_price:,.0f} € Leistungspreis".replace(",", "."), delta_color="off")

day = V.peak_day(a)
st.plotly_chart(V.build_day(a, day), width="stretch", key="chart_day")
st.caption(f"Tag {day + 1} des Monats, der Tag der Monatsspitze ohne Speicher. Gestrichelt: die Schwelle θ der vorab abgestimmten Regel. Unten der Ladestand.")
with st.expander("Der ganze Monat im Überblick"):
    st.plotly_chart(V.build_month(a), width="stretch", key="chart_month")
    st.caption("Netzbezug je Verfahren; die gepunkteten Linien sind die Monatsspitzen, auf die der Leistungspreis gerechnet wird.")
ev = a.events
st.caption(
    f"Last dieses Monats (ohne PV): Monatsspitze {ev['peak']:.0f} kW. Spitzenereignisse (Last mindestens {C.PEAK_EVENT_SHARE * 100:.0f} % der Monatsspitze): {ev['events']}, "
    f"im Mittel {E.de(ev['mean_h'], 2)} h lang, verteilt auf {ev['days']} Tage."
)
st.download_button("📄 Ergebnis als PDF", data=build_pdf(a), file_name="lastspitze_kappen.pdf", mime="application/pdf")

# --- Kernfrage 1 ---------------------------------------------------------------------------------------------------------------------------

st.markdown("## ❓ Kernfrage 1: Wie viel nimmt die Batterie von der Spitze, und welche Regel kommt dem exakten Plan nahe?")
st.dataframe(
    E.result_table(a), hide_index=True, width="stretch",
    column_config={
        "Spitze (kW)": st.column_config.NumberColumn(format="%.1f"),
        "Anteil am LP (%)": st.column_config.NumberColumn(format="%.0f %%"),
    },
)
kind, text = E.verdict_main(a)
getattr(st, kind)(text)
th_f, rho_f = a.params[E.M_FIX]
th_h, rho_h = a.params[E.M_HIND]
st.caption(
    f"Schwellenregel vorab abgestimmt auf drei andere Monate (Seeds {', '.join(str(s) for s in C.TUNE_SEEDS)}): θ = {th_f:.0f} kW, Reservestand ρ = {E.de(rho_f, 2)}; "
    f"im Nachhinein für genau diesen Monat gewählt: θ = {th_h:.0f} kW, ρ = {E.de(rho_h, 2)}. Die Spalten „Leistungspreis“ und „Energie“ zeigen, woher die Lücke zum LP kommt "
    f"(Energie einschließlich des Wertes der Restladung am Monatsende)."
)

# --- Kernfrage 2 ---------------------------------------------------------------------------------------------------------------------------

st.markdown("## ❓ Kernfrage 2: Wie viel bringt die nächste kWh Kapazität?")
st.markdown(
    "Die Ersparnis des exakten Plans über der Kapazität (Leistung wie links eingestellt). Zuerst nur für den gewählten Monat; "
    "der Knopf rechnet über sechs feste Messmonate und ergänzt die Regeln."
)
key6 = (settings.power, settings.kwp, settings.run_h, settings.peak_price, settings.buy)
c_left, c_right = st.columns([1, 2])
with c_left:
    six = st.button("Über sechs Messmonate mitteln (mit Regeln, je nach Rechner einige Dutzend Sekunden)", key="sweep6_start")
if six:
    st.session_state["sweep6"] = key6
if st.session_state.get("sweep6") == key6:
    with st.spinner("Rechne 10 Kapazitäten × 6 Monate (LP und drei Regeln) …"):
        rows = _sweep(settings, C.SWEEP_SEEDS, True)
    scope = "Mittel über sechs Messmonate"
else:
    with st.spinner("Rechne 10 Kapazitäten für diesen Monat (LP) …"):
        rows = _sweep(settings, (settings.seed,), False)
    scope = f"nur der gewählte Monat (Zufalls-Seed {settings.seed})"
knee_row = E.knee(rows)
st.plotly_chart(V.build_capacity(rows, settings.power, knee_row), width="stretch", key="chart_capacity")
st.caption(f"Ersparnis je Monat in €; {scope}. Raster der Kapazität: 0,25 bis 8 Stunden Volllast (C = Stunden · P).")
col_a, col_b = st.columns(2)
with col_a:
    st.plotly_chart(V.build_marginal(rows), width="stretch", key="chart_marginal")
    st.caption("Grenznutzen des LP: zusätzliche Ersparnis je zusätzlicher kWh und Monat zwischen zwei Rasterpunkten.")
with col_b:
    st.plotly_chart(V.build_split(rows), width="stretch", key="chart_split")
    st.caption("Die Ersparnis des LP, geteilt: der Teil aus der Spitze stößt an die Leistung P, der Energieteil (PV) wächst weiter.")
kind, text = E.verdict_knee(knee_row, settings.power)
getattr(st, kind)(text)

# --- Kernfrage 3 ---------------------------------------------------------------------------------------------------------------------------

st.markdown("## ❓ Kernfrage 3: Hängt das Knie an der Spitzendauer?")
st.markdown(
    "Die Last ist aus Maschinenläufen zusammengesetzt, die Spitzendauer entsteht aus ihrer Überlagerung (keine vorgegebene Spitzenzeit). "
    "Der Knopf wiederholt den Kapazitäts-Sweep für fünf mittlere Laufzeiten (nur LP, sechs Messmonate) und liest das Knie der **Spitzensenkung** ab."
)
if st.button("Knie für fünf Laufzeiten messen (je nach Rechner etwa eine Minute)", key="dur_start"):
    st.session_state["dur"] = key6
if st.session_state.get("dur") == key6:
    with st.spinner("Rechne 5 Laufzeiten × 10 Kapazitäten × 6 Monate (LP) …"):
        drows = _duration(settings)
    st.plotly_chart(V.build_duration(drows), width="stretch", key="chart_duration")
    st.dataframe(
        [{"Laufzeit der Maschinen (h)": r["run_h"], "Dauer der Spitzenereignisse (h)": round(r["event_h"], 2),
          "Knie (Stunden Volllast)": r["knee_hours"], "Knie (kWh)": r["knee_cap"]} for r in drows],
        hide_index=True, width="stretch",
    )
    kind, text = E.verdict_duration(drows)
    getattr(st, kind)(text)
    st.caption("Das Knie ist die kleinste Kapazität des Rasters, die 90 % der Spitzensenkung bei 8 Stunden Volllast erreicht; das Raster ist grob (0,25 / 0,5 / 0,75 / 1 / 1,5 / 2 / 3 / 4 / 6 / 8 Stunden).")

# --- Kernfrage 4 ---------------------------------------------------------------------------------------------------------------------------

st.markdown("## ❓ Kernfrage 4: Was bringen Prognosen?")
st.markdown(
    "Ein **Planer** löst das LP über eine Prognose und fährt den Plan gegen die wahren Werte. Der Plan kennt nur die Vergangenheit und die Prognose; "
    "die **Reserve** bewertet die Restladung am Planende. In der Messung unten erreicht das Neuplanen ohne PV mit dem Endwert nichts und mit 1,00 € je kWh bis zu 86 % des LP."
)
fc1, fc2 = st.columns(2)
fc_kind = fc1.selectbox("Prognoseart", list(E.FORECAST_LABEL), index=1, format_func=E.FORECAST_LABEL.get, key="fc_kind",
                        help="Persistenz: Last von vor 7 Tagen, PV von gestern. Klimatologie: Mittel der 28 Vorlauftage je Wochentag und Viertelstunde. Perfekt: nur zur Kontrolle.")
fc_res = fc2.radio("Reserve (Wert der Restladung am Planende)", ["endwert", "1.0"], format_func=lambda v: "Endwert √η · Arbeitspreis" if v == "endwert" else "1,00 € je kWh", horizontal=True, key="fc_res")
keyp = (settings, fc_kind, fc_res)
if st.button("Planer im gewählten Monat rechnen (Neuplanen je nach Rechner etwa eine halbe Minute)", key="fc_start"):
    st.session_state["fc"] = keyp
if st.session_state.get("fc") == keyp:
    with st.spinner("Neuplanen: rund 3.000 kleine LPs …"):
        res = _planner(settings, fc_kind, fc_res)
    entries = [(f"{E.PLANNER_MODES[mo]} ({E.FORECAST_LABEL[fc_kind]})", res[mo]) for mo in E.PLANNER_MODES if res[mo] is not None]
    if res["tag"] is None:
        st.info("In diesem Monat spart auch der exakte Plan nichts: Anteile sind nicht definiert.")
    else:
        entries.append(("Eigenverbrauch (R0)", a.share(E.M_R0)))
        entries.append(("Schwellenregel vorab abgestimmt", a.share(E.M_FIX)))
        st.plotly_chart(V.build_planners(entries, a.share(E.M_FIX)), width="stretch", key="chart_planners")
        kind, text = E.verdict_planner(res, a.share(E.M_FIX), E.FORECAST_LABEL[fc_kind])
        getattr(st, kind)(text)
plan_rows, ref_rows = E.load_measurement("prognose"), E.load_measurement("luecke")
if plan_rows and ref_rows:
    with st.expander("Gemessen über sechs Monate (Tabelle aus tools/messung.py)"):
        st.markdown(E.planner_table_markdown(plan_rows, ref_rows))

st.markdown("---")

# --- Methodenvergleich ---------------------------------------------------------------------------------------------------------------------

with st.expander("🔧 Wie wir das erreichen – vollständiger Methodenvergleich"):
    tab_rules, tab_exact = st.tabs(["Regeln und Planer erklärt", "🧮 Exakt (LP)"])
    with tab_rules:
        st.markdown(
            """
| Verfahren | Was es tut | Was es weiß | Stärke | Schwäche |
|---|---|---|---|---|
| **Ohne Speicher** | Netzbezug = Last − PV | – | Referenz für alle Ersparnisse | – |
| **Eigenverbrauch (R0)** | Überschuss laden, Bedarf entladen | nur den aktuellen Wert | einfach; spart PV-Energie | entlädt für jeden Bedarf; zur Spitze war der Speicher in 5 von 6 Messmonaten leer (README); ohne PV lädt sie nie |
| **Schwellenregel (θ, ρ)** | über der Schwelle θ entladen, darunter bis zum Reservestand ρ·C nachladen | aktuellen Wert, θ und ρ | kappt die Spitze gezielt | θ und ρ müssen zum Monat passen: ein zu hohes θ lässt Spitzen unterhalb von θ durch, ein niedriges kann den Speicher an kleineren Überschreitungen leeren |
| **… θ vorab abgestimmt** | θ, ρ aus drei anderen Monaten (Gitter) | nur andere Monate | ohne Wissen über diesen Monat einsetzbar | die Spitze dieses Monats kann höher oder niedriger sein |
| **… θ im Nachhinein** | θ, ρ aus diesem Monat gewählt (Gitter) | den ganzen Monat (nur θ, ρ) | Obergrenze der Regelklasse auf dem gewählten Raster (θ in 5-kW-Schritten, fünf ρ-Werte) | in der Praxis nicht verfügbar |
| **Exakter Plan (LP)** | minimiert Energie plus Leistungspreis über den ganzen Monat | alle Werte des Monats | Optimum (Referenz) | braucht perfekte Voraussicht |
| **Tagesplan, offen** | um Mitternacht LP über 48 h auf Prognose, 24 h unverändert gefahren | Prognose, Vergangenheit | eine Rechnung je Tag | fährt den Plan weiter, auch wenn die Last abweicht |
| **Neuplanen** | alle 15 Minuten LP über 24 h, aktueller Wert bekannt | Prognose, aktueller Wert | reagiert auf die Abweichung | rund 3.000 Rechnungen je Monat; Ergebnis hängt an der Reserve |
| **Persistenz** (Prognose) | Last von vor 7 Tagen, PV von gestern | Vergangenheit | trifft Wochenmuster | verpasst zufällige Spitzen |
| **Klimatologie** (Prognose) | Mittel der 28 Vorlauftage je Wochentag und Viertelstunde | Vorlauf | stabil | glättet gerade die Spitzen |
"""
        )
        st.markdown(
            "**Gleichstände:** das LP hat oft mehrere gleich teure Fahrpläne (etwa früh oder spät laden); ein winziger Aufschlag auf späte Ladung "
            "(0,00001 € je kWh) wählt dann das frühe Laden."
        )
    with tab_exact:
        sc = a.schedules[E.M_LP]
        cyc = float(sc.dis.sum()) * 0.25 / settings.cap if settings.cap else 0.0
        days_active = int((sc.dis.reshape(30, 96).max(axis=1) > 1e-6).sum())
        st.markdown(
            f"Das LP hat für diesen Monat {5 * a.month.slots + 2:,} Variablen (vier Leistungen und der Ladestand je Viertelstunde, dazu die Monatsspitze) "
            "und wird mit HiGHS gelöst (`scipy.optimize.linprog`).".replace(",", ".")
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("Entladene Energie", f"{float(sc.dis.sum()) * 0.25:,.0f} kWh".replace(",", "."))
        c2.metric("Vollzyklen im Monat", E.de(cyc, 1))
        c3.metric("Tage mit Entladung", f"{days_active} von 30")
        st.caption(
            "Die Gegenprobe des LP steht in `tests/test_oracle_lastspitze_kappen.py`: eine unabhängige Bisektion über die Spitzenhöhe, die Aufzählung aller Fahrpläne auf einer Mini-Instanz "
            "und eine Handrechnung."
        )

# --- Grenzen -------------------------------------------------------------------------------------------------------------------------------

with st.expander("🚧 Wo die Annahmen enden"):
    st.markdown(
        """
* **Last und PV sind erzeugt**, nicht gemessen: Maschinenläufe mit zufälligen Starts, ein Monat mit 22 Werktagen, PV als Übergangsjahreszeit. Echte Lastgänge können andere Spitzen haben.
* **Ein Monat, nicht ein Jahr:** der Speicher startet leer; Jahreszeiten, Feiertage und der Übertrag zwischen Monaten fehlen. Die Leistungsspitze ist hier die höchste Viertelstunde des Monats; reale Tarife rechnen oft mit der Jahresspitze oder mit gestaffelten Preisen.
* **Prognosen sind einfache Annahmen** (Persistenz, Klimatologie, perfekt); echte Prognosemodelle und stochastische Planung sind nicht gemessen.
* **Nicht modelliert:** Alterung und Zyklenkosten, Tarifwechsel, Einspeisedeckel, Wirkungsgrad je Lastpunkt, Mindestladeleistung, Anschlussleistung des Netzanschlusses. Speicherpreise fehlen, deshalb gibt es keine Wirtschaftlichkeitsaussage.
* **Die Schwellenregel ist kein neues Verfahren:** Spitzenkappen mit fester Schwelle ist in der Praxis und in der Fachliteratur bekannt; die Demo misst sie gegen ein exaktes Optimum in diesen Annahmen.
"""
    )

# --- Mathematische Formulierung ------------------------------------------------------------------------------------------------------------

with st.expander("📐 Mathematische Formulierung"):
    # erklaerseite:lesehilfe:start (erzeugt von tools/set_demo_explainer.py (Website-Repo) aus tools/content/explainers/lastspitze-kappen-erklaert.json, nicht von Hand ändern)
    st.markdown(
        r"""
**Lesehilfe.** Gegeben sind Last und Photovoltaik-Erzeugung für jede Viertelstunde eines Monats, drei Preise und eine Batterie mit Kapazität, Leistung und Wirkungsgrad. Gesucht ist ein Plan für Laden und Entladen, der die Energiekosten plus den Leistungspreis auf die höchste Bezugsleistung des Monats möglichst klein macht.

| Symbol | Bedeutung |
|---|---|
| $t$, $T$, $\Delta t$ | Viertelstunde $t = 0, \dots, T-1$ und ihre Länge $\Delta t = 0{,}25$ h |
| $L_t$, $PV_t$ | Last und Photovoltaik-Erzeugung in der Viertelstunde $t$ (kW) |
| $c$, $s$, $q$ | Arbeitspreis, Einspeisevergütung ($s \le c$) und Leistungspreis |
| $C$, $P$, $\eta$ | Kapazität (kWh), Leistung (kW) und Umlaufwirkungsgrad der Batterie (je Richtung $\sqrt{\eta}$) |
| $ch_t$, $dis_t$ | Lade- und Entladeleistung am Netzanschluss (kW), je höchstens $P$ |
| $imp_t$, $exp_t$ | Netzbezug und Netzeinspeisung (kW), nicht negativ |
| $\hat p$ | höchster Netzbezug des Monats (kW), auf ihn wird der Leistungspreis gerechnet |
| $soc_t$ | Ladestand (kWh), zwischen 0 und $C$, Start 0 |
| $w = \sqrt{\eta}\,c$ | Wert einer gespeicherten kWh am Monatsende |
| $\theta$, $\rho$ | Schwelle (kW) und Reservestand (Anteil von $C$) der Schwellenregel |

[Schritt für Schritt erklärt, mit Herleitung und Literatur](https://sebastianhanisch.net/lastspitze-kappen-erklaert.html#fachleute)
        """
    )
    # erklaerseite:lesehilfe:end
    st.latex(r"\min\ \ \Delta t \sum_{t=0}^{T-1}\bigl(c\,imp_t - s\,exp_t\bigr) + q\,\hat p - w\,soc_T")
    st.latex(r"imp_t - exp_t - ch_t + dis_t = L_t - PV_t \qquad imp_t \le \hat p")
    st.latex(r"soc_{t+1} = soc_t + \sqrt{\eta}\,\Delta t\,ch_t - \frac{\Delta t}{\sqrt{\eta}}\,dis_t \qquad 0 \le soc_t \le C,\quad soc_0 = 0")
    st.latex(r"0 \le ch_t \le P \qquad 0 \le dis_t \le P \qquad imp_t,\ exp_t \ge 0 \qquad \hat p \ge 0")
    st.markdown(
        """
Das ist ein vollständiges lineares Programm (Variablen $ch, dis, imp, exp, soc, \\hat p$, alle Bereiche und Bedingungen oben). Die Schwellenregel entlädt, sobald $L_t - PV_t$ die
Schwelle $\\theta$ übersteigt, höchstens mit $P$ und dem Ladestand; unter $\\theta$ lädt sie bis zum Reservestand $\\rho C$ aus dem Netz nach, so weit der Bezug $\\theta$ nicht überschreitet.
Der **Planer** löst dasselbe LP über das Prognosefenster mit Prognosewerten für $L_t - PV_t$, mit der bereits erreichten Monatsspitze als Untergrenze von $\\hat p$ und mit der Reserve
als Wert der Restladung am Fensterende ($w$ ersetzt durch den Reservewert).
"""
    )

st.markdown("---")
st.caption(
    "Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – "
    "Operations Research und Machine Learning ([Über mich](https://sebastianhanisch.net/ueber-mich.html)). "
    "Mehr zu den Demos: [Interaktive Demos](https://sebastianhanisch.net/demos.html)."
)
