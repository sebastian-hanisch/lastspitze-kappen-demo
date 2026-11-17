# Lastspitze kappen: Wie groß muss die Batterie sein? – Streamlit-Demo

<!-- TODO nach dem Deploy: direkt hierher den Live-Link setzen (Leerzeile davor und danach):
**[→ Demo live ausprobieren](https://sebastianhanisch-lastspitze-kappen-demo.streamlit.app/)** -->

Fall-Demo für die Website „Sebastian Hanisch – Operations Research und Machine Learning“ (`demos.html`). Ein Gewerbekunde zahlt neben der Energie einen **Leistungspreis auf die höchste
Viertelstunden-Bezugsleistung des Monats**. Eine Batterie kann diese Spitze kappen. Die Demo vergleicht für einen erzeugten Abrechnungsmonat (30 Tage, Viertelstunden, optional mit Photovoltaik)
den **exakten Plan** (lineares Programm mit Voraussicht über den ganzen Monat) mit **einfachen Regeln** (Eigenverbrauch, Schwelle) und mit **Planern, die nur eine Prognose kennen**,
und misst, wie viel Kapazität die Spitze braucht und ob dieses „Knie“ an der Dauer der Spitzen hängt.

Last und PV sind **erzeugt** (Maschinenläufe mit zufälligen Starts, ein Wettermodell mit drei Zuständen); alle Zahlen gelten für diese Generatoren und die Preisannahmen, nicht für einen echten Betrieb.

## Warum dieses Problem

Ein einzelner Spitzentag bestimmt die Leistungsrechnung des ganzen Monats. Wer eine Batterie dagegen einsetzt, muss sie zur richtigen Zeit gefüllt haben, und das entscheidet sich Stunden vorher.
Daraus folgen vier Fragen, die die Demo live beantwortet: Wie viel nimmt die Batterie von der Spitze? Welche einfache Regel kommt dem exakten Plan nahe? Wie wächst die Ersparnis mit der Kapazität
(das „Knie“), und hängt es an der Spitzendauer? Und was bringen Prognosen?

**Einordnung (keine Neuheit):** Spitzenkappen mit einer festen Schwelle und die Bemessung nach Spitzendauer sind in der Praxis und in der Fachliteratur bekannt. Gesehen wurden nur Titel und Zusammenfassungen
von Suchtreffern: eine Veröffentlichung des KIT zum Spitzenkappen mit Batterie unter Prognoseunsicherheit (Autoren und genauer Titel nicht gesehen; nach der Zusammenfassung: eine zu hohe Schwelle nutzt die Batterie nicht aus,
eine zu niedrige lässt Überschreitungen unkompensiert) und Praxisleitfäden von Anbietern mit der Faustformel kWh = kW × Spitzenstunden / (Entladetiefe × Wirkungsgrad), die hier nicht nachgeprüft ist. Hier kommt hinzu: die
Messung gegen ein exaktes Optimum in einem Generator mit **einstellbarer Spitzendauer**.

**Abgrenzung zu den Nachbarn** (READMEs gelesen): `reefer-spitzenlast-demo` kappt die Spitze eines Kühlcontainer-Blocks über **einen Tag** mit einem Temperaturzustand, ohne Strompreis und ohne Kosten; hier ist der Zustand ein
Ladestand mit Wirkungsgrad, abgerechnet wird das **Monatsmaximum** in Euro. `battery-arbitrage-demo` plant eine Batterie gegen den **Preisverlauf** (SMARD-Tage) ohne Leistungspreis; hier ist der Arbeitspreis flach, und der
Leistungspreis treibt die Entscheidung. Die Schwester-Demo `flotte-laden-demo` behandelt den Leistungspreis für **Fahrzeugflotten** (Fahrzeuge mit Abfahrtszeiten) als eine der Kernfragen; hier geht es um eine feste Batterie gegen die
Monatsspitze eines Gewerbekunden. Das Modell (Speicher-LP) teilt diese Demo mit `battery-arbitrage-demo`; die Frage ist eine andere.

## Modell

Ein Abrechnungsmonat, Viertelstunden *t*, Last *L* minus PV, Batterie mit Kapazität *C*, Leistung *P* und Umlaufwirkungsgrad 0,90 (je Richtung die Wurzel). Das lineare Programm (Formeln im Expander „📐 Mathematische Formulierung“
der App, vollständig mit allen Variablenbereichen):

*imp − exp − ch + dis = L − PV*, *soc(t+1) = soc(t) + √η · ch · Δt − dis · Δt / √η*, *imp ≤ p̂*, Ziel: Energiekosten + Leistungspreis · *p̂* − Endwert · *soc(T)*. Der Endwert der Restladung ist √η · Arbeitspreis, für alle
Verfahren gleich. Start leer. Preise (Annahmen): Arbeitspreis 0,20 €/kWh, Einspeisung 0,07 €/kWh, Leistungspreis 10 € je kW und Monat.

**Last (Annahme, unabhängig vom Plan der Vormessung):** Grundlast 12 kW, Gebäude 10 kW an Werktagen, dazu fünf Maschinen (15 bis 30 kW) mit zufälligen Starts in der Schicht (6 bis 17 Uhr) und lognormaler Laufzeit; der Mittelwert
der gezogenen Laufzeit (vor dem Runden auf Viertelstunden) ist der Regler „Spitzendauer“. Die Dauer der Spitzen entsteht aus der Überlagerung und wird gemessen (Ereignis: Last mindestens 90 % der Monatsspitze). **PV (Annahme):** Übergangsjahreszeit, Tageslicht 6 bis 18 Uhr,
drei Wetterzustände, Wolkenrauschen, Performance Ratio 0,8.

## Methodik

* **Ohne Speicher** und **exakter Plan (LP, HiGHS)** mit Voraussicht über den ganzen Monat; Gleichstände beim Laden löst ein Aufschlag von 0,00001 € je kWh auf späte Ladung (früh laden).
* **Eigenverbrauch (R0):** Überschuss laden, Bedarf entladen. **Schwellenregel (θ, ρ):** über θ entladen; darunter bis zum Reservestand ρ·C aus dem Netz nachladen (Bezug höchstens θ), über dem Reservestand für den
  Eigenbedarf entladen; Überschuss wird geladen. θ (Raster 5 kW) und ρ (0; 0,25; 0,5; 0,75; 1) werden entweder **vorab auf drei anderen Monaten abgestimmt** (`TUNE_SEEDS`) oder **im Nachhinein auf genau diesem Monat gewählt**
  (Obergrenze der Regelklasse auf diesem Raster, in der Praxis nicht verfügbar).
* **Planer mit Prognose:** das LP über prognostizierte Werte, mit der bereits erreichten Monatsspitze als Untergrenze der Spitzenvariablen und einer **Reserve** (Wert der Restladung am Planende). *Offener Tagesplan:* um
  Mitternacht ein Plan über 48 h, die ersten 24 h unverändert gefahren. *Neuplanen:* alle 15 Minuten ein Plan über 24 h mit aktuellem Ladestand und bekanntem aktuellem Wert. Prognosen: perfekt (Kontrolle), Persistenz
  (Last von vor 7 Tagen, PV von gestern), Klimatologie (Mittel der 28 Vorlauftage je Wochentag und Viertelstunde, PV je Viertelstunde).
* **Messreihen:** `tools/messung.py` schreibt `tools/messung_*.json` (Kapazität, Spitzendauer, Lücke, Prognose) über die sechs Messmonate `SWEEP_SEEDS` (Zufalls-Seeds 1 bis 6); die Abstimmung nutzt die getrennten Monate
  `TUNE_SEEDS` (101 bis 103). Die Zahlen unten stammen aus diesen Dateien; die Tests rechnen Stichproben neu.

## Befunde (gemessen, keine Behauptungen)

Alle Zahlen: Mittel über die sechs Messmonate (Zufalls-Seeds 1 bis 6) bei Batterie 100 kWh / 50 kW, 100 kWp PV, Laufzeit der Maschinen 1 h, wenn nichts anderes steht. „Anteil“ ist das Verhältnis der Mittel der Ersparnis
(Summe der Regel durch Summe des LP), „je Monat“ der kleinste und größte Wert der sechs Monate. Die Spalte „Test“ nennt die Funktion in `tests/test_claims.py` (liest `tools/messung_*.json`; Stichproben werden neu gerechnet).

| Frage | Befund | Test |
|---|---|---|
| **Was spart der exakte Plan?** | **717 €** je Monat (678 bis 754 je Monat); die Monatsspitze sinkt von 106,2 auf 56,7 kW. Ohne PV: 491 € (483 bis 498), Spitze von 121,9 auf 71,9 kW. | `test_exact_plan_saving_and_peak` |
| **Wie viel schafft die Eigenverbrauchsregel R0?** | Mit PV **225 €, 31 % des LP** (26 bis 36 % je Monat), und die Spitze sinkt nur von 106,2 auf 105,9 kW. Die Lücke zum LP liegt zu 100 % in der Leistungsrechnung. Zur Spitze ohne Speicher ist der Speicher unter R0 in 5 von 6 Monaten leer (Füllstand unter 1 % der Kapazität). Ohne PV lädt R0 nie: 0 € in 6 von 6 Monaten. | `test_r0_saves_energy_but_not_the_peak` |
| **Kommt die abgestimmte Schwellenregel nahe ans LP?** | Vorab abgestimmt (θ = 60 kW, ρ = 0,5): **73 %** mit PV (60 bis 86 % je Monat); ohne PV (θ = 70 kW, ρ = 0,75): **92 %** (83 bis 99 %). Die Lücke (Summe über die sechs Monate) liegt mit PV zu 51 % in der Leistungsrechnung (je Monat 0 bis 63 %) und zu 49 % in der Energie; ohne PV zu 100 % in der Leistungsrechnung (je Monat 0 bis 109 %: in drei Monaten hat die Regel eine höhere Spitze, aber niedrigere Energiekosten als das LP). | `test_tuned_threshold_rule_versus_lp` |
| **Und wenn θ im Nachhinein gewählt wird?** | **84 %** mit PV (75 bis 88 % je Monat), **99 %** ohne PV (99 bis 100 %). Die Lücke mit PV liegt im Mittel zu 26 % in der Leistungsrechnung (je Monat 0 bis 72 %), zu 74 % in der Energie. „Im Nachhinein“ ist die Obergrenze auf dem gewählten Raster; eine feinere Suche (θ 1 kW, ρ 0,1) fand in einer Scratch-Prüfung bis zu 2 Punkte mehr (nicht im Test). | `test_hindsight_threshold_rule_versus_lp` |
| **Wie wächst die Ersparnis mit der Kapazität?** | Ohne PV (50 kW): 248 € bei 12,5 kWh, 370 € bei 25, 446 € bei 37,5, 483 € bei 50 und 491 € ab 75 kWh; der Grenznutzen fällt von 19,8 über 9,8, 6,1 und 3,0 auf 0,3 €/(kWh·Monat) und ist ab 75 kWh null. Mit PV wächst die Ersparnis weiter (902 € bei 400 kWh), weil der Energieanteil mitwächst; die Ersparnis **aus der Spitze** erreicht ihre Grenze P · Leistungspreis = 500 € ab 150 kWh. | `test_capacity_curve` |
| **Wo liegt das Knie (90 % der Spitzensenkung bei 8 Stunden Volllast)?** | Auf dem Raster bei 1 Stunde Volllast (50 kWh) mit PV und bei 0,75 Stunden (37,5 kWh) ohne PV; beide Werte liegen knapp an der 90-%-Schwelle. | `test_capacity_curve` |
| **Hängt das Knie an der Spitzendauer?** | **Ja, in 3 von 4 Konfigurationen** beim Vergleich der Randlaufzeiten (0,25 h gegen 3 h, 90-%-Knie in Stunden Volllast: 0,5 → 3 mit PV bei 50 kW, 0,5 → 3 ohne PV bei 50 kW, 0,25 → 1,5 ohne PV bei 25 kW); bei 100 kW ohne PV nicht (3 → 3, dazwischen 2 bei 1 h Laufzeit; vermutlich setzen dort die übrigen Spitzen des Monats die Grenze, nicht getrennt gemessen). Der Wert „2 Stunden Volllast“ kommt in 2 von 20 Zellen vor. | `test_knee_depends_on_peak_duration` |
| **Was bringen Prognosen?** | Mit perfekter Prognose erreichen Tagesplan und Neuplanen in allen 8 Zellen (2 PV-Fälle × 2 Reserven × 2 Betriebsarten) zwischen 98,6 und 99,5 % des LP. Mit **Persistenz oder Klimatologie liegt in 16 von 16 Zellen** (2 PV-Fälle × 2 Reserven × 2 Prognosen × 2 Betriebsarten) **jeder Planer unter der vorab abgestimmten Schwellenregel**: bester Wert mit PV 53 % (Neuplanen, Klimatologie, Reserve 1,00 €/kWh) gegen 73 %, ohne PV 86 % (Neuplanen, Persistenz, Reserve 1,00 €/kWh) gegen 92 %. Gezählt ist das Verhältnis der Sechs-Monats-Mittel; ohne PV ist der Abstand kleiner als die Streuung zwischen den Monaten (der beste Planer liegt dort in 2 von 6 Monaten über der Regel). | `test_forecast_planners_versus_rule` |
| **Offener Tagesplan oder Neuplanen?** | Der offene Tagesplan erreicht mit Persistenz oder Klimatologie höchstens 6 % des LP (mit PV und Persistenz −19 % und −20 %, also teurer als ohne Speicher). Das Neuplanen liegt in 6 von 8 Zellen um mehr als 25 Punkte darüber und in diesen 6 Zellen in allen 6 Monaten über dem Tagesplan; in den übrigen zwei (ohne PV, Reserve „Endwert“) liegen beide bei etwa −1 %. | `test_replanning_versus_open_day_plan` |
| **Wie wichtig ist die Reserve?** | Ohne PV erreicht das Neuplanen mit der Reserve „Endwert“ (0,19 €/kWh) mit Persistenz −1 % des LP (nichts), mit 1,00 €/kWh 86 %; je Monat von 59 % bis 99 %. Mit Klimatologie und Reserve 1,00 €/kWh liegen die Monate ohne PV zwischen 17 % und 99 %. | `test_reserve_value_matters` |

**Abweichungen gegenüber der Vormessung** (anderer Generator: Spitzen mit vorgegebener Dauer von 1 bis 2 Stunden): Das dortige Knie bei C ≈ 2 · P bestätigt sich hier nicht als feste Zahl (Zeile zur Spitzendauer).
Die Vormessung fand realistische Prognosen in 7 von 8 Zellen unter der Schwellenregel; hier sind es 16 von 16 Zellen (Mittel über sechs Monate, andere Planer-Auslegung: Reserve 0,19 und 1,00 €/kWh statt 2,00 €/kWh).
Die Vormessung sprach von einer Treppe der Kapazität; hier fällt der Grenznutzen des LP auf dem Raster von 0,25 bis 8 Stunden Volllast in jedem Schritt, ohne Plateau vor der Grenze.

## Ehrliche Grenzen

* **Alles ist erzeugt:** Last, PV, Prognosen und Preise sind Annahmen; echte Lastgänge können andere Spitzen haben, und die Messmonate sind sechs Zufallsziehungen aus diesen Generatoren.
* **Ein Monat, nicht ein Jahr:** der Speicher startet leer, Jahreszeiten und Feiertage fehlen, und der Leistungspreis wird auf die Monatsspitze gerechnet (reale Tarife rechnen oft mit der Jahresspitze oder gestaffelt).
* **Die Abstimmung ist grob:** θ (5 kW) und ρ (fünf Werte) auf drei Monaten; eine feinere Abstimmung wurde nicht gemessen. Die Ursache der Restlücke (Energieanteil mit PV) ist **eine Deutung**: Die Regelklasse
  stimmt Laden und Entladen nicht mit dem PV-Überschuss ab; getrennt gemessen ist das nicht.
* **Prognosen sind einfache Annahmen** (Persistenz, Klimatologie); die Aussage gilt für diese Prognosen, dieses Planer-Design (LP über Punktprognose mit Reserve, Neuplanen alle 15 Minuten) und diese Reserven (Endwert und
  1,00 €/kWh), nicht für stochastische Planung oder für Prognosemodelle mit Wetterdaten.
* **Zwei Betriebsarten, nicht jede Auslegung:** der Planer fährt den Plan des ersten Schritts; eine Variante, die den aktuellen Bezug gegen die Planspitze prüft, ist nicht gemessen.
* **Keine Wirtschaftlichkeit:** Speicherpreise und Kapitalkosten fehlen.

## Verifikation

* **Orakel** (`tests/test_oracle_lastspitze_kappen.py`): (1) die kleinste erreichbare Monatsspitze des LP gegen eine **unabhängige Bisektion** über die Spitzenhöhe mit Vorwärtssimulation (40 Zufallsinstanzen mit PV-Überschuss
  plus fünf erzeugte Monate; im Scratch-Lauf mit 200 Instanzen vorab geprüft), (2) die Gesamtkosten gegen **Aufzählung aller Fahrpläne** auf einem 1/12-kW-Raster (Mini-Instanz mit Wirkungsgrad 1, 12 feste Instanzen; im Scratch-Lauf 100 von 100
  Zufallsinstanzen gleich), (3) **Handrechnung** (Zwei-Stunden-Beispiel mit Wirkungsgrad 1, 710 € → 310 €), (4) Eigenschaften: Bilanz, Ladestand in den Grenzen, LP nie teurer als eine Regel, Ersparnis nicht fallend und konkav in Kapazität
  und Leistung, die Schwellenregel mit der Bisektionsspitze hält diese Spitze (ohne PV).
* **Kern:** Abrechnung und Regeln von Hand, Generator (Wochenende, PV-Skalierung, Determinismus), Prognosen nutzen nur bekannte Werte, Planer zulässig; Randfälle (zwei Zeitschritte, Kapazität 0, Leistung 0, reiner Überschuss,
  Gleichstand, Untergrenze der Spitze).
* **Verdikte** als reine Funktionen an handgesetzten Werten (Schwellen am gezeigten Prozentwert, jede Zahl im Text).
* **Messreihen:** `tests/test_claims.py` prüft jede Zahl der Tabelle oben gegen `tools/messung_*.json`, rechnet Stichproben neu (Kapazität, Lücke, Prognose im Tagesplan) und zählt die Tests. Die Suite hat **104 Tests**.
* **Oberfläche:** AppTest (jeder leichte Knopf, jeder Regler am Minimum und Maximum, jedes Preset, die schweren Knöpfe mit verkleinerten Messmonaten), Footer, Layout (Schnellstart in der Seitenleiste, fester Kopf, Hervorhebung),
  Laufzeit-Importe, `modul_frisch.py`.

## Dateistruktur

| Datei | Zweck |
|---|---|
| `.github/workflows/tests.yml` | CI: Push, Pull Request, wöchentlicher Canary |
| `.gitignore` | venv, Caches, Streamlit-Secrets |
| `.streamlit/config.toml` | Streamlit-Einstellungen (keine Nutzungsstatistik) |
| `app.py` | Streamlit-App: Ergebnis, vier Kernfragen, Methodenvergleich, Grenzen, Formeln |
| `lsk_algorithm.py` | Kern: Speicher-LP mit Monatsspitze, Regeln (R0, Schwelle), Abstimmung von θ und ρ |
| `lsk_planner.py` | Prognosen und Planer (offener Tagesplan, Neuplanen) |
| `lsk_scenario.py` | Generatoren für Last (Maschinenläufe) und PV, Spitzenereignisse |
| `lsk_constants.py` | Regler-Grenzen, feste Annahmen, Farben, Presets |
| `lsk_evaluation.py` | Analyse eines Monats, Sweeps (Kapazität, Spitzendauer), Verdikte, Messreihen laden |
| `lsk_visualization.py` | Plotly-Abbildungen (Achsen gesperrt) |
| `lsk_pdf_export.py` | PDF-Export des Ergebnisses (fpdf2) |
| `lsk_layout.py`, `lsk_presets.py` | Fester Kopf; Permalink, Presets (Schnellstart in der Seitenleiste), Zufalls-Seed-Button |
| `modul_frisch.py` | lädt geänderte Hilfsmodule nach einem Update neu (Streamlit Cloud) |
| `tools/messung.py`, `tools/messung_*.json` | Messreihen und ihre Ergebnisse (Quelle der Zahlen oben) |
| `requirements.txt`, `requirements-dev.txt` | Laufzeit-Bibliotheken (ungepinnt) plus pytest |
| `tests/` | Orakel, Kern, Randfälle, Verdikte, Presets, Layout, Messreihen, AppTest, Footer, Laufzeit-Importe |

## Bewusst nicht umgesetzt

* **Alterung und Zyklenkosten, Tarifwechsel, Einspeisedeckel, Szenarien über Wetterjahre:** in der Haushaltsvariante der Vormessung zu dieser Demo (anderer Generator) blieben Einspeisedeckel und Wetterjahre ohne eigenen Befund,
  Alterung und Tarifwechsel ergaben nur Regler; hier nicht aufgenommen.
* **Arbeitspreis als Zeitreihe (Arbitrage):** das ist `battery-arbitrage-demo`; hier ist der Arbeitspreis flach.
* **Dimensionierung der PV-Anlage und Eigenverbrauchsquote:** nicht Thema dieser Demo.
* **Stochastische Planung und echte Prognosemodelle:** nicht gemessen.
* **Fahrzeugflotten mit Abfahrtszeiten:** Thema der Schwester-Demo `flotte-laden-demo`.

## Lokal ausführen

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
streamlit run app.py
```

Die Messreihen neu erzeugen (je nach Rechner einige Minuten, bis zu zehn):

```bash
python tools/messung.py alle --workers 6
```

## Tests ausführen

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

Gebaut mit Streamlit, Plotly, NumPy und SciPy (HiGHS).

---

Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – Operations Research und Machine Learning ([Über mich](https://sebastianhanisch.net/ueber-mich.html)). Mehr zu den Demos: [Interaktive Demos](https://sebastianhanisch.net/demos.html).
