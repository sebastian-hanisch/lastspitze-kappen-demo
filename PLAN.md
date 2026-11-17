# PLAN: lastspitze-kappen-demo (Stand 2026-11-17)

Auftrag und Vormessung: `energie-planung/messreihe_speicher_pv/ERGEBNIS.md` (Abschnitt „Verbesserungsrunde 2026-11-17“), `energie-planung/AUFTRAG_GEMEINSAM.md`. Diese Datei hält nur fest,
**wo der Bau vom Plan abweicht** und warum; die Befunde stehen in der README, die Messungen in `tools/messung_*.json`.

## Umgesetzt wie geplant

* Modell: Speicher-LP mit Monatsspitze als Variable (HiGHS), optional mit PV; Referenz „ohne Speicher“, Regeln R0 und Schwelle, Planer mit Prognose.
* Orakeltest: unabhängige Bisektion über die Spitzenhöhe gegen das LP (aus der Vormessung übernommen als Idee, im Bau neu geschrieben und mit PV-Überschuss erweitert), dazu Aufzählung auf einer Mini-Instanz und Handrechnung.
* AP 0: unabhängig erzeugtes Lastprofil in Viertelstunden (Maschinenläufe) mit dem Regler Spitzendauer; Knie und Prognoseergebnisse wurden darauf neu gemessen.
* Alle Zahlen der README sind im Bau neu gerechnet (`tools/messung.py`); kein Wert aus der Vormessung ist übernommen. Die README nennt die Abweichungen.
* Ehrlichkeit: Schwellenregel und Bemessung nach Spitzendauer sind in der Fachliteratur bekannt (nur Titel/Zusammenfassungen gesehen); die README sagt das.

## Abweichungen vom Plan

1. **Presets in der Seitenleiste statt im Hauptbereich.** Der Auftrag nannte „Presets im Hauptbereich“; das aktuelle DEMO-PLAYBOOK §2 (Stand 2026-10-18) verlangt den Schnellstart oben in der Seitenleiste. Es gilt das Playbook.
2. **Das Knie liegt nicht bei C ≈ 2 × P.** Die Vormessung erzeugte Spitzen mit vorgegebener Dauer von 1 bis 2 Stunden. Mit unabhängig erzeugter Last liegt das Knie je nach Spitzendauer und Leistung zwischen 0,25 und 3 Stunden Volllast (README, Zeile „Hängt das Knie an der Spitzendauer?“). Das Knie wird an der **Ersparnis aus der Spitze** gemessen, weil der Energieanteil der PV mit der Kapazität weiterwächst und das Knie sonst verdeckt.
3. **Kein „Treppen“-Befund.** Der Grenznutzen fällt stetig (konkav, getestet); die Vormessung sprach von einer Treppe.
4. **Planer-Auslegung neu festgelegt.** Der Planer plant jede Viertelstunde neu (statt stündlich), die Reserve ist 0,19 €/kWh („Endwert“) oder 1,00 €/kWh (Vormessung: 2,00 €/kWh). Gleichstandsregel (früh laden) ist Bestandteil des LP. Die Ergebnisse hängen stark an der Reserve; das steht in der README.
5. **Ein Monat statt eines Jahres.** Das LP rechnet einen Monat (2.880 Viertelstunden); die Monatsspitze ist die Abrechnungsgröße. Sechs feste Messmonate (Zufalls-Seeds 1 bis 6), Abstimmung auf drei getrennte Monate (101 bis 103). Die Vormessung rechnete Jahre mit Stundenwerten.
6. **PV ist ein Regler (100 kWp Voreinstellung), keine Dimensionierungsaufgabe.** Ohne PV lädt die Eigenverbrauchsregel nie (0 € in 6 von 6 Monaten); das steht in der README und im Preset „Ohne PV“.
7. **Nicht aufgenommen:** Alterung, Tarifwechsel, Einspeisedeckel, Szenarien über Wetterjahre (Negativbefunde bzw. nur Regler in der Vormessung; höchstens ein Satz unter „Bewusst nicht umgesetzt“).
8. **Verweis auf `flotte-laden-demo`:** nur als Name in der README (die Schwester-Demo ist noch nicht veröffentlicht); der gegenseitige Link entsteht erst nach beiden Deploys.

## Offen für Commit, Push, Deploy, Website

* Freigaben des Nutzers für Commit, Push, Streamlit-Deploy und Einbindung auf der Themenseite „Energie und Elektromobilität“ (`_wt_energie`).
* Gegenseitiger Verweis zwischen dieser Demo und `flotte-laden-demo` nach beider Veröffentlichung (README, App-Text).
* Erklärseite „verständlich erklärt“ (WEBSITE-PLAYBOOK 3b) und Karte (`add_demo.py`, `set_demo_footer.py`) stehen aus.
* Linux-Check (`demo_linux_check.py`, Docker) vor dem Push; unabhängiger Aussagenprüfer (`claim_review.py pack`) vor dem ersten Push.
