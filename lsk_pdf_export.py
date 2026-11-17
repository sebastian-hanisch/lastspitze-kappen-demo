"""PDF-Export (fpdf2): Einstellungen, Ergebnistabelle und Kernaussage des gewählten Monats."""

from fpdf import FPDF

import lsk_evaluation as E


def _plain(text: str) -> str:
    """Die eingebauten PDF-Schriften kennen kein θ, ρ, √ und ähnliche Zeichen: durch Wörter ersetzen."""
    for a, b in (("€", "EUR"), ("θ", "Schwelle"), ("ρ", "Reserve"), ("√η", "Wurzel aus Eta"), ("η", "Eta"), ("·", "*"), ("−", "-"), ("–", "-"), ("„", '"'), ("“", '"')):
        text = text.replace(a, b)
    return text


def build_pdf(a: E.Analysis) -> bytes:
    s = a.settings
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(True, margin=15)
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 9, _plain("Lastspitze kappen: Ergebnis eines Abrechnungsmonats"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5, _plain(
        f"Batterie {s.cap:.0f} kWh / {s.power:.0f} kW (Umlaufwirkungsgrad 0,90), PV {s.kwp:.0f} kWp, mittlere Maschinenlaufzeit {s.run_h:g} h, "
        f"Leistungspreis {s.peak_price:g} EUR je kW und Monat, Arbeitspreis {s.buy:.2f} EUR je kWh, Zufalls-Seed {s.seed}."))
    pdf.ln(2)
    kind, text = E.verdict_main(a)
    pdf.multi_cell(0, 5, _plain(text))
    pdf.ln(3)
    cols = [("Verfahren", 70), ("Spitze kW", 22), ("Leistungspreis", 28), ("Energie", 22), ("Gesamt", 22), ("Ersparnis", 22)]
    pdf.set_font("Helvetica", "B", 9)
    for name, w in cols:
        pdf.cell(w, 6, name, border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for r in E.result_table(a):
        vals = [_plain(r["Verfahren"]), f"{r['Spitze (kW)']:.1f}", f"{r['Leistungspreis (€)']:.0f}", f"{r['Energie (€)']:.0f}",
                f"{r['Gesamt (€)']:.0f}", f"{r['Ersparnis (€)']:.0f}"]
        for (name, w), v in zip(cols, vals):
            pdf.cell(w, 6, v, border=1)
        pdf.ln()
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(0, 4, _plain("Last und PV sind erzeugt (Annahmen), keine Messdaten. Alle Betraege in EUR je Monat. "
                                "Quelle: Demo Lastspitze kappen auf sebastianhanisch.net."))
    return bytes(pdf.output())
