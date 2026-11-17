"""Plotly-Figuren: alle Achsen fest (fixedrange), damit Touch-Scrollen nicht am Diagramm hängen bleibt."""

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import lsk_constants as C
import lsk_evaluation as E
from lsk_scenario import DT, SLOTS

_LAYOUT = dict(margin=dict(l=55, r=15, t=40, b=45), legend=dict(orientation="h", y=-0.22), hovermode="x unified")
_COLORS = {E.M_NONE: C.COLOR_NET, E.M_R0: "#b9a13a", E.M_FIX: C.COLOR_RULE, E.M_HIND: "#c25a8c", E.M_LP: C.COLOR_LP}


def _fix_axes(fig):
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig


def peak_day(a) -> int:
    """Tag (0-basiert) der höchsten Netzbezugsleistung ohne Speicher."""
    return int(np.argmax(a.schedules[E.M_NONE].imp)) // SLOTS


def build_day(a, day: int, methods=(E.M_NONE, E.M_FIX, E.M_LP)) -> go.Figure:
    """Ein Tag: oben Last, PV und Netzbezug je Verfahren mit der Schwelle der Regel, unten der Ladestand."""
    sl = slice(day * SLOTS, (day + 1) * SLOTS)
    hours = np.arange(SLOTS) * DT
    m = a.month
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.68, 0.32], vertical_spacing=0.07,
                        subplot_titles=("Leistung in kW", "Ladestand in kWh"))
    fig.add_trace(go.Scatter(x=hours, y=m.load[sl], name="Last", line=dict(color=C.COLOR_LOAD, width=1, dash="dot")), row=1, col=1)
    if m.kwp > 0:
        fig.add_trace(go.Scatter(x=hours, y=m.pv[sl], name="PV", line=dict(color="#e0b020", width=1, dash="dot")), row=1, col=1)
    for key in methods:
        s = a.schedules[key]
        fig.add_trace(go.Scatter(x=hours, y=s.imp[sl], name=f"Netzbezug: {E.METHOD_LABEL[key]}", line=dict(color=_COLORS[key], width=2 if key == E.M_LP else 1.5)),
                      row=1, col=1)
        if key != E.M_NONE:
            fig.add_trace(go.Scatter(x=hours, y=s.soc[sl.start:sl.stop], name=f"Ladestand: {E.METHOD_LABEL[key]}", showlegend=False,
                                     line=dict(color=_COLORS[key], width=1.5)), row=2, col=1)
    if E.M_FIX in methods:
        theta = a.params[E.M_FIX][0]
        fig.add_hline(y=theta, line=dict(color=C.COLOR_RULE, width=1, dash="dash"), row=1, col=1,
                      annotation_text=f"θ = {theta:.0f} kW", annotation_position="top left")
    fig.update_xaxes(title_text="Uhrzeit (h)", row=2, col=1, range=[0, 24], dtick=3)
    fig.update_layout(height=520, **_LAYOUT)
    fig.update_layout(legend=dict(orientation="h", y=-0.18))
    return _fix_axes(fig)


def build_month(a, methods=(E.M_NONE, E.M_FIX, E.M_LP)) -> go.Figure:
    """Der ganze Monat: Netzbezug je Verfahren; die Monatsspitze entscheidet die Leistungsrechnung."""
    t = np.arange(a.month.slots) * DT / 24.0 + 1.0
    fig = go.Figure()
    for key in methods:
        fig.add_trace(go.Scattergl(x=t, y=a.schedules[key].imp, name=E.METHOD_LABEL[key], mode="lines",
                                   line=dict(color=_COLORS[key], width=1)))
        fig.add_hline(y=a.costs[key]["peak"], line=dict(color=_COLORS[key], width=1, dash="dot"))
    fig.update_xaxes(title_text="Tag des Monats", range=[1, 31], dtick=5)
    fig.update_yaxes(title_text="Netzbezug in kW")
    fig.update_layout(height=340, **_LAYOUT)
    return _fix_axes(fig)


def build_capacity(rows, power: float, k: dict) -> go.Figure:
    """Ersparnis je Monat über der Kapazität: LP (mit Streuband über die Monate), R0, beide Schwellenregeln; senkrecht das Knie."""
    caps = [r["cap"] for r in rows]
    fig = go.Figure()
    if rows[0][E.M_R0] is not None:
        for key in (E.M_R0, E.M_FIX, E.M_HIND):
            fig.add_trace(go.Scatter(x=caps, y=[r[key] for r in rows], name=E.METHOD_LABEL[key], mode="lines+markers",
                                     line=dict(color=_COLORS[key], width=1.5)))
    fig.add_trace(go.Scatter(x=caps + caps[::-1], y=[r["lp_max"] for r in rows] + [r["lp_min"] for r in rows][::-1], fill="toself",
                             fillcolor="rgba(47,107,101,0.15)", line=dict(width=0), hoverinfo="skip", name="LP: kleinster bis größter Monat"))
    fig.add_trace(go.Scatter(x=caps, y=[r[E.M_LP] for r in rows], name=E.METHOD_LABEL[E.M_LP], mode="lines+markers",
                             line=dict(color=C.COLOR_LP, width=3)))
    if k["cap"] is not None:
        fig.add_vline(x=k["cap"], line=dict(color=C.COLOR_BAD, width=1, dash="dash"),
                      annotation_text=f"Knie: {E.de(k['hours'])} h Volllast", annotation_position="top right")
    fig.update_xaxes(title_text=f"Kapazität in kWh (Leistung {power:.0f} kW)")
    fig.update_yaxes(title_text="Ersparnis in € je Monat", rangemode="tozero")
    fig.update_layout(height=380, **_LAYOUT)
    return _fix_axes(fig)


def build_marginal(rows) -> go.Figure:
    """Grenznutzen der Kapazität als Treppe: zusätzliche Ersparnis in € je Monat und zusätzlicher kWh."""
    gains = E.marginal_gains(rows, E.M_LP)
    fig = go.Figure(go.Bar(x=[f"{g['von']:.0f}–{g['bis']:.0f}" for g in gains], y=[g["je_kwh"] for g in gains], marker_color=C.COLOR_LP,
                           hovertemplate="%{x} kWh: %{y:.2f} € je kWh und Monat<extra></extra>"))
    fig.update_xaxes(title_text="Kapazitätsstufe in kWh", type="category")
    fig.update_yaxes(title_text="€ je zusätzlicher kWh und Monat", rangemode="tozero")
    fig.update_layout(height=300, **_LAYOUT)
    return _fix_axes(fig)


def build_split(rows) -> go.Figure:
    """Ersparnis des LP, geteilt in Leistungspreis (Spitze) und Energie (Eigenverbrauch der PV, Verluste)."""
    caps = [f"{r['cap']:.0f}" for r in rows]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=caps, y=[r["power_saving"] for r in rows], name="aus der Spitze (Leistungspreis)", marker_color=C.COLOR_LP))
    fig.add_trace(go.Bar(x=caps, y=[r[E.M_LP] - r["power_saving"] for r in rows], name="aus der Energie (PV-Eigenverbrauch, minus Verluste)",
                         marker_color=C.COLOR_SOC))
    fig.update_layout(barmode="relative", height=300, **_LAYOUT)
    fig.update_xaxes(title_text="Kapazität in kWh", type="category")
    fig.update_yaxes(title_text="€ je Monat")
    return _fix_axes(fig)


def build_duration(rows) -> go.Figure:
    """Anteil der Ersparnis an der bei größter Kapazität über den Stunden Volllast, eine Linie je Maschinenlaufzeit."""
    fig = go.Figure()
    palette = ["#4c78a8", "#59a14f", "#e0b020", "#d9822b", "#b8433a"]
    for color, r in zip(palette, rows):
        top = r["curve"][-1][1]
        if top < 0.5:
            continue
        hours = [cap / r["curve"][-1][0] * C.CAP_HOURS[-1] for cap, _ in r["curve"]]
        fig.add_trace(go.Scatter(x=hours, y=[100 * v / top for _, v in r["curve"]], mode="lines+markers", line=dict(color=color, width=2),
                                 name=f"Laufzeit {E.de(r['run_h'])} h (Spitzenereignis {E.de(r['event_h'], 2)} h)"))
    fig.add_hline(y=100 * C.KNEE_SHARE, line=dict(color="gray", width=1, dash="dot"))
    fig.update_xaxes(title_text="Kapazität in Stunden Volllast (C / P)", range=[0, C.CAP_HOURS[-1] + 0.2])
    fig.update_yaxes(title_text=f"Anteil der Ersparnis bei {C.CAP_HOURS[-1]:g} h in %", range=[0, 105])
    fig.update_layout(height=360, **_LAYOUT)
    return _fix_axes(fig)


def build_planners(entries, rule_share: float | None) -> go.Figure:
    """Balken: Anteil an der LP-Ersparnis je Planer (Liste (Beschriftung, Anteil)); gestrichelt die abgestimmte Schwellenregel."""
    fig = go.Figure(go.Bar(x=[e[0] for e in entries], y=[100 * e[1] for e in entries],
                           marker_color=[C.COLOR_LP if e[1] >= 0 else C.COLOR_BAD for e in entries]))
    if rule_share is not None:
        fig.add_hline(y=100 * rule_share, line=dict(color=C.COLOR_RULE, width=2, dash="dash"),
                      annotation_text="Schwellenregel, vorab abgestimmt", annotation_position="top left")
    fig.update_yaxes(title_text="Anteil an der Ersparnis des LP in %")
    fig.update_layout(height=340, **_LAYOUT)
    return _fix_axes(fig)
