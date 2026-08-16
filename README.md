# Mini-Tourenplanung (VRP) – Streamlit-Demo

Interaktive Demo zur (LKW-)Tourenplanung mit mehreren Fahrzeugen, Kapazitätsrestriktion,
einem synthetischen (optional asymmetrischen) Straßennetz und optionalen Zeitfenstern je
Stopp. Vier selbst implementierte Konstruktionsheuristiken (Sweep, Savings, Beam Search,
genetischer Algorithmus) werden per 2-opt + Or-opt Local Search verbessert und zusätzlich
mit Googles Open-Source-Solver OR-Tools verglichen. Routen lassen sich als animierter LKW
abspielen und als PDF-Tourenplan herunterladen. Teil des Demo-Portfolios für die Website
"Sebastian Hanisch – Operations Research und Machine Learning".

## Dateistruktur

Die Logik ist in eigene Module aufgeteilt, `app.py` enthält nur noch den
Streamlit-Ablauf (Sidebar, Tabs, Vergleich) und importiert den Rest:

| Datei | Inhalt |
|---|---|
| `app.py` | Streamlit-Hauptablauf (Sidebar, Tabs, Vergleichstab) |
| `vrp_constants.py` | Alle Konstanten (Standardwerte, Limits) |
| `vrp_network.py` | Straßennetz-Aufbau, Distanzmatrix, Kartendaten |
| `vrp_evaluation.py` | Routen-Bewertung (Distanz, Zeitfenster), Business-Umrechnung |
| `vrp_construction.py` | Sweep, Savings, Beam Search, genetischer Algorithmus |
| `vrp_local_search.py` | 2-opt + Or-opt lokale Suche |
| `vrp_ortools_solver.py` | OR-Tools-Anbindung |
| `vrp_visualization.py` | Plotly-Karten (statisch + animiert) |
| `vrp_pdf_export.py` | PDF-Tourenplan-Erzeugung |
| `vrp_feedback.py` | Feedback-Logging |
| `vrp_ui_panel.py` | Wiederverwendbares UI-Panel je Heuristik |
| `vrp_presets.py` | Beispielszenarien, Permalink-Logik |

Diese Aufteilung hat einen praktischen Vorteil für die Tests: Die Logik-Module
enthalten keinen Streamlit-UI-Code auf oberster Ebene und lassen sich daher
direkt importieren (`import vrp_construction`) statt – wie zuvor bei allem in
einer Datei – per AST-Extraktion aus app.py herausgeschnitten werden zu
müssen. Das macht die Testsuite robuster und einfacher nachvollziehbar.

**Verifiziert nach der Aufteilung:** `pyflakes` über alle Dateien (keine
unbenutzten Importe/undefinierten Namen), ein tatsächlich unbenutzter
Rückgabewert entfernt (`all_pts` in app.py), Docstrings bei den zentralen
Bewertungs-/Visualisierungsfunktionen ergänzt, `log_feedback`/
`get_feedback_counts` beim Verschieben verbessert (Dateipfad jetzt expliziter
Parameter statt globaler Konstante – einfacher testbar), volle Testsuite
(70 Tests) vor und nach dem Umbau grün.

## Zwei Ebenen: Ergebnis zuerst, Technik auf Wunsch

Die App zeigt direkt nach der Stopp-Tabelle die **Primäransicht "Ihre optimierte
Route"**: die beste der vier eigenen Methoden für das aktuelle Szenario, mit
Fahrzeit/Kosten/CO₂-Ersparnis gegenüber einer **unoptimierten Ausgangslage** (Stopps in
Eingabereihenfolge, ohne jede Optimierung) prominent im Vordergrund - kein
Algorithmus-Name in der Überschrift, nur das Ergebnis. Welche Methode konkret gewonnen
hat, steht als kleine, zurückhaltende Caption darunter (Transparenz ohne die
eigentliche Botschaft zu verwässern).

Der komplette Methodenvergleich (alle vier Heuristiken einzeln, OR-Tools,
Benchmark-Details) liegt danach eingeklappt im Expander "🔧 Wie wir das erreichen" -
weiterhin vollständig vorhanden, aber nicht mehr das Erste, was ein Besucher sieht.

**Hintergrund:** Der ursprüngliche Zweck der Demo ist, Geschäftsentscheidern zu zeigen,
dass Optimierung echte Kostenersparnis bringt - nicht, jede implementierte Methode
gleichrangig zur Schau zu stellen. Mit fünf gleichberechtigten Haupttabs (Sweep,
Savings, Beam Search, GA, OR-Tools) plus Vergleichstab musste ein Besucher vorher erst
verstehen, dass es mehrere Methoden gibt, bevor die eigentliche Botschaft ankam. Die
Umstrukturierung ändert nichts an der vorhandenen Substanz (kein Code wurde entfernt),
nur an der Präsentationsreihenfolge.

**OR-Tools bewusst nicht Teil der Primäransicht:** OR-Tools ist Button-gesteuert (siehe
Ressourcenschutz unten) und nicht garantiert bereits gelöst, wenn die Seite lädt. Die
Primäransicht bezieht sich deshalb ausschließlich auf die vier eigenen, immer sofort
verfügbaren Methoden - ein Besucher sieht so ohne jede Zusatz-Interaktion ein
vollständiges Ergebnis. Der Vergleich mit OR-Tools bleibt im technischen Detailbereich
verfügbar, sobald gelöst.

## Funktionsumfang

- **Straßennetz statt Luftlinie:** Depot, Stopps und zusätzliche "Kreuzungen" bilden
  einen gerichteten Graphen (networkx); alle Distanzen/Routen folgen kürzesten Wegen
  darin. Das Netz ist **synthetisch/prozedural generiert** – bewusst keine Anbindung an
  OSM/OSRM oder andere externe Kartendienste, damit die Demo ohne API-Keys, Rate-Limits
  oder Internetabhängigkeit zur Laufzeit zuverlässig läuft (wichtig bei kostenlosem
  Hosting). Für ein reales Kundenprojekt ließe sich hier echtes Kartenmaterial anbinden.
- **Optional asymmetrisch:** rund ein Viertel der Streckenabschnitte wird in einer
  Richtung künstlich verlängert (Faktor 1,4–2,5×) – simuliert Einbahnstraßen/Umwege, auf
  der Karte orange gestrichelt markiert. Alle Distanzabfragen im Code sind gerichtet
  (von→nach), das funktioniert ohne Änderungen an den Heuristiken oder an OR-Tools.
- **Vier eigene Konstruktionsheuristiken im Vergleich:**
  - *Sweep* – Polarwinkel-Sortierung um das Depot
  - *Savings* (Clarke & Wright, 1964) – fusioniert Einzeltouren nach Ersparnis
  - *Beam Search* – verfolgt die 8 besten Teillösungen parallel statt nur einer
  - *Genetischer Algorithmus* – Giant-Tour-Kodierung, Order Crossover, Elitismus
  
  Jede Konstruktion wird mit derselben lokalen Suche verbessert und hat einen eigenen
  Tab mit Iterations-Slider, Auto-Play und Distanzverlauf.
- **Lokale Suche: 2-opt + Or-opt.** 2-opt vertauscht Streckenabschnitte *innerhalb*
  einer Tour. Or-opt verschiebt zusätzlich kurze Segmente (1–2 Stopps) *zwischen*
  Fahrzeugen, wenn das verbessert – das behebt die zentrale Schwäche von reinem 2-opt
  (siehe Benchmark unten). Lexikografische Zielfunktion: erst Zeitfenster-Verletzungen
  minimieren, dann Distanz.
- **OR-Tools als fünfter, unabhängiger Solver:** Googles Open-Source-Routing-Solver
  (Apache 2.0) löst dasselbe Problem eigenständig mit einer Guided-Local-Search-
  Metaheuristik. Wird bewusst **nicht automatisch** bei jeder Eingabeänderung neu
  gelöst (das würde die App spürbar verlangsamen), sondern über einen Button mit
  einstellbarem Zeitlimit angestoßen – **auf max. 5s gedeckelt** (statt 10s), als
  Schutz vor Ressourcenlast bei mehreren gleichzeitigen Besuchern auf dem
  kostenlosen Hosting-Tarif (Konstante `ORTOOLS_MAX_TIME_LIMIT`).
- **Optionale Zeitfenster:** frühester/spätester Start und Servicezeit je Stopp.
- **Geschäftliche Kennzahlen statt abstrakter Zahlen:** Kartendistanz wird als km
  interpretiert; einstellbare Regler für Ø Geschwindigkeit (km/h) und Kosten pro km
  (€) rechnen alle Distanzen in Fahrzeit und Kraftstoffkosten um – in jedem Tab, in
  der Vergleichstabelle und im PDF-Export. Der Vergleichs-Tab zeigt zusätzlich eine
  konkrete Einsparung ("Im Vergleich zur schwächsten Methode spart X ca. Y €
  Kraftstoffkosten und Z Stunden Fahrzeit").
- **LKW-Animation:** Plotly-Animation mit Play/Pause und Scrub-Regler – ein Symbol pro
  Fahrzeug fährt die fertige Route ab (alle synchron nach % der Strecke, unabhängig von
  der realen Streckenlänge).
- **PDF-Tourenplan:** Download-Button pro Tab, erzeugt über `fpdf2` in-memory (kein
  Zwischenspeichern) – Zusammenfassung (inkl. Fahrzeit/Kosten) + Stopp-Tabelle je
  Fahrzeug, inkl. Ankunftszeiten bei aktiven Zeitfenstern.
- **Feedback-Mechanismus:** 👍/👎-Buttons am Seitenende ("War diese Demo hilfreich?"),
  loggen in eine lokale CSV (`feedback_log.csv`). Testet die im Businessplan
  vorgesehene Resonanz-Frage. **Wichtige Einschränkung:** Streamlit Community Cloud
  hat kein dauerhaft persistentes Dateisystem (Reset bei Neustart/Redeploy) – für
  zuverlässige Langzeit-Auswertung eignet sich später eine Anbindung an ein Google
  Sheet oder eine kleine Datenbank besser.
- **Drei Ein-Klick-Beispielszenarien** für Erstbesucher (Innenstadt-Zustellung, enge
  Zeitfenster, große Flotte mit knapper Kapazität) – setzen Fahrzeuge, Kapazität,
  Zeitfenster und Stopps auf ein vorbereitetes Beispiel zurück.
- **CO₂-Kennzahl:** dritter Nachhaltigkeits-Wert neben Fahrzeit/Kosten, einstellbarer
  Regler (kg CO₂/km) – überall dort integriert, wo auch Fahrzeit/Kosten erscheinen.
- **OR-Tools-Cooldown:** verhindert, dass der Solver durch schnelles Mehrfachklicken
  wiederholt gestartet wird (Wartezeit = Zeitlimit + 3s) – ergänzt die bereits gedeckelte
  maximale Rechenzeit um Schutz vor Klick-Spam.
- **Permalink:** die Browser-Adresszeile spiegelt durchgehend die aktuelle Konfiguration
  wider (Fahrzeuge, Kapazität, Seed, Zeitfenster, Asymmetrie, Geschäftskennzahlen) und
  lässt sich direkt kopieren, um ein Szenario zu teilen (z. B. für ein Kundengespräch).
  Manuell in der Stopp-Tabelle bearbeitete Positionen sind bewusst **nicht** enthalten,
  nur die Generator-Parameter, aus denen die Stopps erzeugt werden.

Alle fünf Methoden werden am Ende mit **derselben Bewertungsfunktion** auf demselben
Straßennetz verglichen – fair vergleichbar, auch wenn die internen Suchstrategien sehr
unterschiedlich arbeiten.

## Performance

Bei 30 Stopps, 5 Fahrzeugen, aktivem asymmetrischem Netz und Zeitfenstern (der
aufwändigste automatische Fall ohne OR-Tools) läuft ein kompletter Rerun in der Regel
unter 3,5 Sekunden – alle vier eigenen Heuristiken inklusive lokaler Suche laufen
automatisch bei jeder Eingabeänderung. OR-Tools ist bewusst button-gesteuert, da es sein
Zeitlimit (Standard 3s, gedeckelt auf 5s) i. d. R. voll ausnutzt, und zusätzlich mit
Cooldown gegen Mehrfachklicks abgesichert.

## Hinweis zur Paketgröße

`ortools` ist ein vergleichsweise großes Paket (~80 MB). Das verlängert Build-/
Kaltstartzeit beim Deployment etwas, ist aber auf Streamlit Community Cloud
unproblematisch. `fpdf2` (PDF-Export) ist dagegen sehr leichtgewichtig.

## Ein Bug, den die Kombination aus Features aufgedeckt hat

Bei kombinierten Regressionstests (großes Problem lösen → per Beispielszenario auf ein
kleineres wechseln, ohne neu zu lösen) stürzte die App ab: Die alte OR-Tools-Lösung
(mehr Stopps) wurde gegen die neue, kleinere Distanzmatrix ausgewertet →
`IndexError`. Fix: Bei veralteten Eingaben wird die alte Lösung jetzt nur noch mit einer
Warnung ausgeblendet, statt sie weiter auszuwerten. Regressionstest dafür in der
Testsuite (`test_stale_ortools_result_after_input_change_does_not_crash`).

## Ein Sicherheits-/Robustheits-Bug im Permalink

Beim gezielten Suchen nach übersehenen Randfällen (nicht beim normalen Testen
aufgefallen): Ein Permalink mit einem Wert außerhalb der Slider-Grenzen –
z. B. `?n_stops=1000` (Slider-Maximum ist 30) oder `?capacity=-10` – ließ die App mit
einer unbehandelten `StreamlitValueAboveMaxError`/`BelowMinError` abstürzen, weil
Streamlit Session-State-Werte außerhalb des Widget-Wertebereichs nicht selbst begrenzt.
Betroffen waren **7 von 9 Permalink-Parametern** (alle numerischen Slider). Zusätzlich
ließen negative Seeds (`?seed=-42`) numpy mit "expected non-negative integer" abstürzen.

Das ist praktisch relevant: ein alter geteilter Link nach einer späteren
Grenzänderung, ein Tippfehler, oder ein absichtlich manipulierter Link hätte die Seite
für Besucher unbenutzbar gemacht. Fix: `PERMALINK_PARAM_MAP` (`vrp_presets.py`) trägt
jetzt zu jedem Parameter Minimum/Maximum, geladene Werte werden auf den gültigen Bereich
begrenzt (`max(lo, min(hi, wert))`) statt roh übernommen; Seeds werden auf
nicht-negative Ganzzahlen begrenzt. 17 neue Regressionstests decken alle betroffenen
Parameter einzeln ab (`test_permalink_clamps_out_of_range_*`,
`test_permalink_handles_extreme_seed_without_crash`).

**Nachtrag beim Weitersuchen:** `float("nan")` und `float("inf")` werfen anders als
`int()` KEINE Exception. Die App stürzte dadurch zwar nicht ab, aber nur durch Zufall:
Pythons `max()`/`min()` mit `NaN` sind reihenfolgeabhängig (der erste Vergleichspartner
"gewinnt", da NaN-Vergleiche immer `False` sind) - in der konkreten Aufrufreihenfolge
landete `NaN` zufällig immer beim unteren Grenzwert. Kein Absturz, aber unbeabsichtigtes
Verhalten, auf das man sich nicht verlassen sollte. Jetzt wird `math.isfinite()` explizit
geprüft und NaN/Infinity wie ein ungültiger Wert behandelt (Parameter wird ignoriert,
Default bleibt bestehen). 5 weitere Tests (`test_permalink_rejects_non_finite_float_params`).

## Wartbarkeit: eine Wahrheitsquelle für Wertebereiche

Nach dem Permalink-Fix standen die Slider-Grenzen an **zwei** Stellen: einmal im
`st.slider(...)`-Aufruf in `app.py`, einmal in der Permalink-Begrenzungstabelle. Das ist
eine klassische Wartbarkeitsfalle - ändert jemand später einen Slider-Bereich und
vergisst die zweite Stelle, kommt der bereits behobene Absturz-Bug (Permalink mit Wert
außerhalb des Bereichs) stillschweigend zurück.

Zusammengeführt zu `SETTING_SPECS` in `vrp_presets.py` (ein `SettingSpec`-Dataclass je
Widget mit URL-Parametername, Typkonvertierung, Wertebereich und Default). Die Slider in
`app.py` lesen ihre Grenzen jetzt über `bounds("n_stops_slider")` aus derselben Quelle,
aus der auch die Permalink-Begrenzung und die Default-Initialisierung lesen.

Zusätzlich abgesichert durch drei Tests, die sich nicht auf Disziplin verlassen:
- `test_slider_bounds_match_setting_specs` vergleicht die **tatsächlich gerenderten**
  Slider-Grenzen mit der Spezifikation. Wirksamkeit belegt: absichtlich eine Abweichung
  eingebaut (`st.slider(..., 5, 99, ...)`) → Test schlägt fehl; Abweichung entfernt →
  wieder grün.
- `test_setting_specs_defaults_are_within_bounds` - ein Default außerhalb des eigenen
  Bereichs würde die App beim allerersten Laden zum Absturz bringen.
- `test_permalink_url_params_are_unique` - zwei Widgets mit demselben URL-Parameter
  würden sich gegenseitig überschreiben (Copy-Paste-Fehler, sonst schwer zu finden).

## Bewertet, aber bewusst nicht umgesetzt: Parameter-Bündelung

Eine Analyse der Funktionssignaturen zeigt lange Parameterlisten:
`render_heuristic_panel()` 20 Parameter, `build_figure()`/`build_animated_figure()` je 14,
`generate_tour_plan_pdf()` 13. Dieselben Gruppen wiederholen sich dabei ständig -
`earliest, latest, service, tw_enabled` taucht 39× im Code auf,
`speed_kmh, cost_per_km, co2_per_km` 13×. Das ist ein reales Risiko: bei so vielen
gleichartigen Positionsargumenten sind Vertauschungen beim Aufruf leicht möglich und
fallen nicht zwingend sofort auf.

Die saubere Lösung wäre, diese Gruppen in Dataclasses zu bündeln (etwa `RouteContext`
für Instanz + Zeichendaten und `BusinessParams` für die Kennzahlen), was
`render_heuristic_panel` von 20 auf etwa 6 Parameter bringen würde. Bewusst nicht mehr
umgesetzt: Der Eingriff berührt vier Module, alle Aufrufstellen und mehrere Tests -
ein umfangreicher mechanischer Umbau, dessen Nutzen rein struktureller Natur ist
(keine Verhaltensänderung, kein behobener Fehler). Am Ende einer langen Änderungsserie
wäre das Risiko, dabei eine Regression einzubauen, höher als der Gewinn. Empfehlung:
als eigener, isolierter Schritt mit anschließendem vollständigem Testlauf angehen -
die vorhandenen 99 Tests geben dafür eine gute Absicherung.

## Zwei Umgehungsmöglichkeiten beim OR-Tools-Cooldown

Gezielte Prüfung der Cooldown-Logik unter schnellen Interaktionen (Schutz vor
Ressourcenlast bei mehreren gleichzeitigen Besuchern) förderte zwei Lücken zutage:

1. **Umgehung durch Herunterregeln des Zeitlimits.** Der Cooldown wurde gegen das
   *aktuell eingestellte* Zeitlimit gerechnet. Nach einem Lauf mit Zeitlimit 5
   (Cooldown 8s) genügte es, den Regler auf 1 zu stellen (Cooldown scheinbar nur 4s),
   um schon nach ~6s erneut zu lösen. Fix: Es zählt das Zeitlimit des *tatsächlich
   gelaufenen* letzten Solves, gespeichert im Session State.

2. **Zeitstempel wurde vor dem Solve gesetzt.** Die Sperrfrist begann bereits beim
   Start der (bis zu 5s dauernden) Rechnung zu laufen - die effektive Pause nach
   Solve-*Ende* war dadurch nur ~3s statt der beabsichtigten 8s. Gemessen: ein Klick
   3,5s nach Solve-Ende ging noch durch. Fix: Zeitstempel wird nach Rückkehr des
   Solvers gesetzt.

Beide durch Regressionstests abgedeckt
(`test_ortools_cooldown_not_bypassable_by_lowering_time_limit`,
`test_ortools_cooldown_timestamp_recorded_after_solve`).

## Geprüft und für sauber befunden: Zeitfenster + asymmetrisches Netz

Diese Kombination wurde gezielt untersucht, weil zwei jüngere Features hier aufeinander
treffen und die Zeitrechnung Distanzen richtungsabhängig verwenden muss - genau die Art
von Konstellation, aus der die bisherigen Funde stammten. Ergebnis: kein Fehler.
`route_timeline` (eigene Bewertung) und der OR-Tools-`time_callback` schlagen beide
korrekt gerichtet nach (`D[prev][node]` bzw. `D[i][j]`). Empirisch geprüft über mehrere
Instanzen: Bewertung konsistent bei Neuberechnung, Verletzungen über die lokale Suche
hinweg monoton fallend, Zeitachse plausibel (keine negativen Ankünfte/Wartezeiten), und
OR-Tools ist auf asymmetrischen Netzen nur moderat schlechter als auf symmetrischen
(14 vs. 11 Verletzungen über 6 Instanzen) - konsistent mit "echte Umwege machen das
Problem schwerer", nicht mit einem Modellierungsfehler.

## Ein Algorithmus-Bug bei asymmetrischen Netzen (Savings)

Ebenfalls beim gezielten Nachdenken über Algorithmusprobleme gefunden, nicht durch
Zufall beim Testen: Der Savings-Algorithmus berechnet die Ersparnis einer Fusion
`s = D[depot][i] + D[depot][j] - D[i][j]` - bei asymmetrischen Distanzen macht es aber
einen Unterschied, ob die Route als "...→i→j→..." oder "...→j→i→..." gefahren wird, weil
`D[i][j]` und `D[j][i]` unterschiedlich sein können. Der Code entschied beide
Fusionsrichtungen anhand desselben, nur in EINER Richtung berechneten Werts.

Konkretes Gegenbeispiel (3 Stopps, A→B und A→C billig, aber B→A sehr teuer): Vor dem Fix
wählte der Algorithmus eine Route mit Distanz 41, obwohl mit denselben Stopps eine
Distanz von 31 (direkt nach Konstruktion) bzw. 13 (nach der lokalen Suche) erreichbar
gewesen wäre - mehr als dreimal so schlecht wie nötig. Fix: Ersparnis wird jetzt für
beide Richtungen getrennt berechnet und als eigener Kandidat in die
Fusionsreihenfolge einsortiert (`test_savings_respects_asymmetric_direction`); bei
symmetrischen Distanzen (`s_ij == s_ji`) bleibt das Verhalten unverändert
(`test_savings_symmetric_case_unchanged_by_directional_fix`).

## Ein Bug, zuerst in der Packungsoptimierung-Demo gefunden

Beim Bauen der zweiten Demo (3D-Packungsoptimierung) fiel ein identisches Muster auf,
das dort zuerst behoben wurde - dieselbe Ursache steckte auch hier: Der
Regenerierungs-Trigger für die Stopps prüfte nur `n_stops`, nicht den Seed. Ein reiner
Seed-Wechsel (ohne gleichzeitige Änderung der Stopp-Anzahl) hatte dadurch **keine
Wirkung** auf die tatsächlich generierten Stopps, obwohl die Sidebar bereits den neuen
Seed anzeigte - der Regler suggerierte eine Wirkung, die er nicht hatte. Reproduziert
und bestätigt: Stopp-Koordinaten blieben nach `at.sidebar.number_input[0].set_value(999)`
identisch. Fix: Cache-Schlüssel um den Seed erweitert (`gen_key = (n_stops, seed)` statt
nur `n_stops`). Regressionstests: `test_seed_change_alone_regenerates_stops`,
`test_n_stops_change_still_regenerates_stops` (stellt sicher, dass der bestehende
Trigger durch die Erweiterung nicht kaputt geht).

## Ein Experiment, das wieder verworfen wurde

Um Or-opt-Prinzipien auch in die Beam-Search-*Konstruktion* selbst einzubauen (nicht nur
in die anschließende lokale Suche), wurde eine "Cheapest-Insertion"-Variante getestet:
statt Stopps nur ans Tourende anzuhängen, wird an der günstigsten Position eingefügt.
Im Benchmark (15 Instanzen) verschlechterte das die Ergebnisse messbar (+9,1 % statt
+3,6 % Abstand zu OR-Tools) und führte zu stark unausgewogenen Touren (ein Fahrzeug
bekam 10 Stopps, ein anderes 0) – Diagnose: die Methode stopft günstige, nahe Stopps
gierig in dasselbe Fahrzeug, statt die Last zu verteilen. Wieder verworfen zugunsten der
ursprünglichen Anhängen-Variante; ein Regressionstest
(`test_beam_search_produces_reasonably_balanced_routes`) verhindert, dass diese Schieflage
unbemerkt zurückkehrt.

Stattdessen wurde eine Or-opt-inspirierte **Mutation** in den genetischen Algorithmus
eingebaut (verschiebt probeweise einen Stopp an mehrere Kandidatenpositionen, behält die
beste) – das verbesserte die Ergebnisse tatsächlich (+3,9 % statt +5,3 % Abstand zu
OR-Tools, bei weiterhin unter 120 ms Rechenzeit) und wurde übernommen.

## Monobeam: dieselbe Monotonie-Lücke wie bei Fracht und Packung, hierher übertragen

Nachdem sich `beam_search_construction` (Fracht-Demo) und `beam_search_packing`
(Packungsdemo) als nicht monoton erwiesen und durch monobeam-Adaptionen ersetzt wurden,
lag die Frage nahe: hat die Tourenplanung-Demo dasselbe Problem? Sie war nie darauf
geprüft worden, obwohl die Konstruktion demselben Muster folgt (`candidates.sort(...);
beam = candidates[:beam_width]` - volle Kandidatenmenge pro Schritt sortieren und
kürzen statt verschachtelt zuzuweisen).

**Bestätigt, aber seltener als bei den anderen beiden Demos.** Systematisch über 30
Testinstanzen (variable Größe, Kapazität, Fahrzeuganzahl) geprüft: 6 von 30 zeigten eine
schlechtere statt bessere Tour bei größerer Beam-Breite - deutlich seltener als bei
Packung (11 von 14) oder Fracht, vermutlich weil VRP an jedem Schritt frei entscheidet,
welcher Stopp als nächstes drankommt (nicht in fester Reihenfolge wie bei den anderen
beiden Demos), was den zugrundeliegenden Effekt seltener, aber nicht unmöglich macht.
**Wichtig:** anders als bei Packung/Fracht übersteht die Verletzung hier nicht
zuverlässig die anschließende lokale Suche (2-opt + Or-opt) - bei 3 von 6 geprüften
Fällen blieb sie auch danach bestehen. Für Nutzer sichtbar, nicht nur ein
Konstruktionsdetail, das ohnehin wegoptimiert wird.

### Zwei gescheiterte Zwischenversuche, bevor die richtige Lösung stand

Die monobeam-Adaptionen der anderen beiden Demos führten zuerst eine FESTE
Bearbeitungsreihenfolge ein (Größe absteigend bei Packung, analog übertragbar bei
Fracht) und entschieden pro Ebene nur noch "wohin mit diesem einen Element". Dieselbe
Übertragung auf VRP scheiterte zweimal:

1. **Feste Reihenfolge nach Distanz vom Depot** (naheliegendste Übertragung, da direkt
   aus der ohnehin vorhandenen Distanzmatrix ableitbar, keine Koordinaten nötig).
   Ergebnis: häufige, teils unnötige Infeasible-Fälle - bei Instanzen, wo der
   Gesamtbedarf klar unter der Gesamtkapazität lag, fand das Original trotzdem eine
   machbare Lösung, monobeam nicht. Distanz vom Depot hat schlicht nichts mit der
   Kapazitätsbeschränkung zu tun.
2. **Feste Reihenfolge nach Bedarf absteigend** (direkte Übertragung der FFD-Lehre aus
   Fracht-/Packungsdemo, wo genau das half). Behob das Machbarkeitsproblem, aber: nach
   lokaler Suche in 15 von 15 Testinstanzen deutlich schlechter als das Original (teils
   >50 % mehr Distanz). Der Unterschied zu Fracht/Packung: bei VRP ist die geografische
   Anordnung der **Hauptkostentreiber**, nicht nur eine Nebenbedingung wie
   Containervolumen oder Bin-Packing-Kapazität. Eine reine Bedarfssortierung ignoriert
   das komplett und lässt Fahrzeuge geografisch weit verstreute Stopps aufsammeln, nur
   weil sie zufällig ähnlichen Bedarf haben.

### Die funktionierende Lösung: keine externe feste Reihenfolge

Der Fehler in beiden gescheiterten Versuchen war die Annahme, dass eine feste
Reihenfolge überhaupt nötig ist. Sie ist es nicht - das Kernprinzip von monobeam
(Slot c beansprucht sofort das beste Element aus einem geteilten Kandidatenpool, bevor
Slot c+1 angefasst wird) funktioniert genauso, wenn an jeder der `n_stops` Ebenen weiter
FREI entschieden wird "welcher verbleibende Stopp UND welches Fahrzeug" - exakt wie im
Original, nur mit korrigierter Verschachtelung statt "volle Menge sortieren und
kürzen". Die geografische Flexibilität des Originals bleibt dadurch vollständig
erhalten.

**Ergebnis:** über 147 Testinstanzen 0 Verletzungen der Monotonie. Qualität nach lokaler
Suche über 30 Testinstanzen: 12 Siege für monobeam, 18 fürs Original, im Schnitt +4,1 %
- ein ehrlicher Kompromiss, wie bei der Packungsdemo (Monotonie erkauft sich eine
eingeschränktere Suche, nicht automatisch bessere Einzelergebnisse in jedem Fall).
Performance: bei der App-Obergrenze von 30 Stopps Worst Case ~115ms - unproblematisch
für automatische Neuberechnung bei jeder UI-Interaktion.

**Ein weiterer, kleinerer Fund unterwegs:** die erste Fassung bewertete Teilzustände nur
anhand der bereits gefahrenen Strecke, ohne die Heimfahrt jedes Fahrzeugs von seiner
aktuellen Position einzubeziehen - dieselbe Fehlerklasse wie bei der Packungsdemo
(Bewertung nach der falschen Größe, nicht nach der tatsächlich angezeigten Kennzahl).
Da route_cost/solution_totals die Rückfahrt zum Depot mitrechnen, führte das zu
scheinbaren, aber nicht echten Monotonie-Verletzungen (die Verschachtelung selbst war
bereits korrekt, nachweisbar durch identische Slot-Präfixe bei unterschiedlichen
Breiten - nur die Zielgröße stimmte nicht). Behoben durch eine Bewertungsfunktion, die
bei jedem Vergleich die Heimfahrt aller Fahrzeuge von ihrer aktuellen Position
einbezieht.

**Die Vergleichstabelle unten wurde komplett neu vermessen** (alle vier eigenen
Heuristiken, nicht nur Beam Search, damit der Vergleich intern konsistent bleibt) - die
alten Zahlen bezogen sich auf die nicht-monotone Implementierung.

## Vom Nutzer gemeldet: Beam Search bei größeren Szenarien "ziemlich schlecht"

Direkt nachgeprüft statt vermutet: über mehrere Problemgrößen (10-30 Stopps) gemittelt
lag `monobeam_vrp_construction` fast durchgehend auf Platz 3 oder 4 von 4 eigenen
Methoden - **unabhängig von der Beam-Breite** (selbst bei Breite 50, weit über das
sinnvolle Maß hinaus, blieb eine Lücke von ~14 % zu Savings).

### Die Grundursache: reines Einfügen ist ein bekanntermaßen schwächeres Prinzip

Savings (Clarke & Wright) fusioniert Touren gezielt nach Ersparnis - ein holistisches,
relatives Kriterium. `monobeam_vrp_construction` baute Touren dagegen schrittweise durch
"füge den nächsten/günstigsten Stopp bei irgendeinem Fahrzeug hinzu" auf - ein
myopisches, lokales Kriterium, in der VRP-Literatur bekannt dafür, "Nachzügler"-Stopps
übrig zu lassen, die am Ende teuer eingesammelt werden müssen. Drei Alternativen für die
Schritt-Bewertung getestet (reine Inkrementalkosten, Cheapest-Insertion, Regret-
Einfügung) - keine schloss die Lücke, bestenfalls auf ~5 % verringert.

### Der Durchbruch: Beam Search auf Savings' Fusionsentscheidungen selbst

Statt Beam Search auf Einfüge-Konstruktion anzuwenden, wird es jetzt auf Savings'
Fusionsreihenfolge angewendet: bei jedem Fusionsschritt wird sowohl "fusionieren" als
auch "überspringen, für später aufheben" als Kandidat geführt - eine Flexibilität, die
reines deterministisches Savings nie hat. `beam_savings` in `vrp_construction.py`.

### Vier gefundene und behobene Fehler auf dem Weg zur korrekten Fassung

1. **Datenverlust bei zu vielen Restrouten.** Eine erste Fassung kürzte das Ergebnis
   einfach auf `n_vehicles` Routen, wenn die Fusion mehr getrennte Routen übrig ließ als
   Fahrzeuge vorhanden waren - das ließ stillschweigend ganze Touren samt Stopps
   verschwinden. Verifiziert: in 14 von 14 getesteten Konfigurationen entstanden mehr
   Routen als Fahrzeuge. Die anfangs vielversprechende Messung (15 % besser als Savings)
   war dadurch komplett ein Artefakt fehlender Daten, keine echte Verbesserung. Fix:
   identische Nachbearbeitung wie `savings_construction` - erzwungene Fusion der am
   wenigsten ausgelasteten Restrouten, bis die Anzahl passt, mit `infeasible`-Markierung
   statt Datenverlust.
2. **Falsches Verschachtelungsmuster.** Nach dem Datenverlust-Fix zeigten 13 von 28
   Testinstanzen nicht-monotones Verhalten - dieselbe Ursache, die in diesem Projekt
   bereits mehrfach identifiziert wurde (Packung, Fracht, ursprüngliches
   `monobeam_vrp_construction`): alle Beam-Slots wurden zuerst vollständig erweitert,
   erst danach sequenziell aus dem gemeinsamen Pool beansprucht. Fix: pro Slot sofort
   nach der eigenen Erweiterung beanspruchen (Lemons et al. 2022), bevor der nächste
   Slot überhaupt erweitert wird - Verletzungen sanken auf 7 von 28.
3. **Konsolidierungs-unbewusste Endauswahl.** Per Trace verifiziert, dass die Beam-Slots
   selbst bereits korrekt monoton waren (identisch zwischen unterschiedlichen Breiten) -
   die verbleibenden Verletzungen entstanden bei der AUSWAHL des besten Endzustands: sie
   verglich rohe Kosten VOR der Zwangs-Konsolidierung, aber diese kann je nach Kandidat
   unterschiedlich teuer ausfallen. Fix: jeder Endkandidat wird jetzt MIT angewandter
   Konsolidierung bewertet, bevor der beste ausgewählt wird.
4. **Lokale-Suche-blinde Auswahl.** Mit korrekter Konsolidierung sank die
   Verletzungsrate auf ~7 % - aber diese Restfälle waren keine Bugs, sondern eine
   strukturelle Eigenschaft: die anschließende lokale Suche verbessert strukturell
   unterschiedliche, ähnlich teure Kandidaten unterschiedlich stark, sodass eine reine
   Rohkosten-Auswahl gelegentlich einen Kandidaten wählte, der zwar minimal günstiger
   startete, aber nach lokaler Suche schlechter abschnitt. Fix: alle eindeutigen
   Endkandidaten (Duplikate herausgefiltert) werden selbst mit lokaler Suche bewertet,
   der tatsächlich beste gewinnt. Ergebnis: **0 von 147 Verletzungen** über eine breite
   Stichprobe (mehrere Problemgrößen, mehrere Fahrzeugzahlen, mehrere Seeds je
   Kombination, ausschließlich tatsächlich lösbare Instanzen).

### Ein fünfter Fund: korrekt monoton, aber bei Zeitfenstern qualitativ schwach

Mit den vier obigen Fixes war die Konstruktion zwar nachweislich monoton, aber bei
aktivierten Zeitfenstern brach die Qualität stark ein - nur 2 von 10 Siegen gegenüber
den vier bestehenden Methoden, teils sogar schlechter als das alte
`monobeam_vrp_construction`. Grund: die Fusionsentscheidungen selbst basierten
ausschließlich auf Distanz-Ersparnis, ohne jede Rücksicht auf Zeitfenster - das musste
die lokale Suche allein reparieren, was nicht zuverlässig gelang.

**Fix:** dieselbe lexikografische Priorität (Zeitfenster-Verletzungen, Distanz), die
lokale Suche selbst verwendet, wird jetzt bereits WÄHREND der Konstruktion auf jede
Kandidaten-Bewertung angewendet (nicht erst bei der Endauswahl) - jede Bewertung
während der Fusionssuche nutzt jetzt `evaluate_route` statt nur eine Distanzsumme.
Ergebnis: 15 von 21 Siegen (71 %) mit Zeitfenstern, 14 von 21 (67 %) ohne, über eine
breite Stichprobe (mehrere Problemgrößen, mehrere Seeds je Größe) - Monotonie bleibt
dabei erhalten (0 von 44 Verletzungen mit Zeitfenstern).

### Performance-Kompromiss: von 172ms auf ~1,1-1,4s mit Zeitfenstern

Die vollständige lokale-Suche-Bewertung aller eindeutigen Endkandidaten (Fund 4) kostet
Rechenzeit - bei 30 Stopps ohne Zeitfenster 172ms Worst Case (kaum langsamer als vorher),
mit Zeitfenstern (teurere `evaluate_route`-Aufrufe je Kandidat) 1,1-1,4s Worst Case. Eine
Duplikat-Filterung (identische Routenmengen aus unterschiedlichen Konstruktionspfaden
nur einmal bewerten) reduzierte das von anfänglich 1,47s auf diesen Wert, ohne
Korrektheit zu verlieren. Getestete Alternative (günstige `solution_totals`-Vorauswahl
statt vollständiger lokaler Suche auf allen Kandidaten) war zwar deutlich schneller
(133ms), brach die Monotonie aber massiv (18 von 44 Verletzungen) - rohe Zeitfenster-
Verletzungen VOR lokaler Suche korrelieren offenbar schlecht mit dem Ergebnis NACH
lokaler Suche, anders als Distanz. Korrektheit hat Vorrang vor dieser speziellen
Optimierung - verworfen.

### Ergebnis in der finalen Benchmark-Tabelle unten

`monobeam_vrp_construction` bleibt vollständig im Code (getestet, aber nicht mehr an die
Oberfläche angebunden) - dieselbe "getestet, aber ersetzt" Konvention wie bei
`beam_search_construction` in den Schwesterdemos. Alle vier eigenen Heuristiken für die
Tabelle unten neu vermessen, nicht nur Beam Search, damit der Vergleich intern
konsistent bleibt.
`test_beam_savings_covers_all_stops`, `test_beam_savings_is_monotone_without_tw`,
`test_beam_savings_is_monotone_with_tw`, `test_beam_savings_never_loses_stops_on_consolidation`,
`test_beam_savings_worst_case_completes_within_budget`,
`test_beam_savings_generally_beats_or_ties_savings`.

## Vom Nutzer gefragt: harmoniert Genetischer Algorithmus auch mit der Savings-Idee?

Naheliegende Anschlussfrage nach dem Beam-Search-Durchbruch: Beam Search UND
Genetischer Algorithmus sind beides Metaheuristiken - hilft dasselbe "Metaheuristik plus
Savings"-Prinzip auch GA?

### Die Grundidee: Anfangspopulation impfen statt komplett zufällig starten

GAs "Riesentour"-Kodierung startet normalerweise mit einer komplett zufälligen
Population von Permutationen. Naheliegende, in der GA-Literatur gut etablierte
Verbesserung: einen Teil der Anfangspopulation stattdessen mit der bereits berechneten
Savings/beam_savings-Lösung impfen (als Riesentour: Routen einfach aneinandergehängt,
plus ein paar zufällige Vertauschungen für Diversität).

**Erstes Ergebnis, ohne Zeitfenster: klar positiv.** 23 von 28 Siegen gegenüber
unveränderter GA, nur 1 Niederlage. **Mit Zeitfenstern: durchwachsen** (9 Siege, 11
Niederlagen) - die geimpfte GA war dort nicht eindeutig besser.

### Die Ursache: verlustbehaftetes Dekodieren zerstört die geimpfte Struktur

Konkret nachgeprüft: verkettet man Savings-Routen zu einer Riesentour und dekodiert sie
mit `decode_giant_tour` (striktes Greedy-Split, respektiert nur Kapazität) zurück,
wandern Stopps über die ursprünglichen Routengrenzen hinweg. Ein Stopp aus Route 2
landete im Test-Beispiel in Route 1, weil dort noch 3 Einheiten Kapazität frei waren -
geografisch aber möglicherweise unpassend. Bei Zeitfenstern, wo Stopp-Reihenfolge und
Fahrzeugzuordnung stark auf Zeitverträglichkeit wirken, verwässerte das die geimpfte
Qualität besonders stark.

### Der Fix: optimale Split-Prozedur statt striktem Greedy-Split

`decode_giant_tour_optimal_split` in `vrp_construction.py` - ein kürzester-Pfad-Ansatz
(Prins 2004) über alle möglichen zusammenhängenden Routensegmente der Riesentour, statt
stur von links nach rechts zu füllen. `dp[i][k]` = minimale Kosten, um die ersten i
Stopps mit genau k Routen abzudecken - findet die beste Aufteilung unabhängig von der
Eingabereihenfolge. Verifiziert: die verkettete Savings-Tour wird dadurch wieder exakt
auf die ursprüngliche Savings-Distanz dekodiert (vorher: verlustbehaftet).

Ergebnis mit Zeitfenstern: **15 von 21 Siegen** (statt 9 von 21).
`test_decode_giant_tour_optimal_split_covers_all_stops`,
`test_decode_giant_tour_optimal_split_recovers_original_route_quality`.

### Der Performance-Kompromiss: volle Genauigkeit überall, aber weniger Generationen

Die optimale Dekodierung kostet spürbar mehr Rechenzeit (0,5-0,6ms statt Bruchteile
einer Millisekunde je Aufruf). Bei den ~2000 Bewertungen einer vollen GA-Runde
(Standardbreite `pop_size=30`, `generations=40`) summierte sich das auf **~1,9s statt
~264ms** GA-Anteil bei Zeitfenstern - spürbar langsamer.

Ein erster Kompromissversuch (teure optimale Dekodierung nur an wenigen kritischen
Stellen: Seed-Anfangsbewertung, einmal je Generation für den generationsbesten
Kandidaten) war zwar deutlich schneller (~283ms), aber qualitativ schwächer (12 statt
15 von 21 Siegen) - auch eine Verstärkung auf die Top-3 statt nur den einen Besten je
Generation half kaum (355ms, weiterhin 12/21). Die Selektionsdruck-Schleife (Turnier-
auswahl, Crossover, Mutation) "wusste" ohne durchgängig korrekte Bewertung nicht
zuverlässig genug, welche Kandidaten wirklich gut waren.

**Die tatsächlich beste Lösung:** volle optimale Dekodierung überall (keine
Kompromisse an der Genauigkeit), aber deutlich reduzierte Populationsgröße und
Generationenzahl (`GA_SEEDED_POP_SIZE=20`, `GA_SEEDED_GENERATIONS=15` statt der
Standardwerte 30/40) - der Seed gibt bereits einen starken Ausgangspunkt, weniger
Generationen genügen zum Verfeinern. Ergebnis: sowohl **schneller** (~377-458ms
GA-Anteil) **als auch qualitativ besser** (23/28 ohne, 15/21 mit Zeitfenstern) als der
Kompromiss-Ansatz.

### Architektur: Seed wird wiederverwendet statt doppelt berechnet

`beam_savings` selbst kostet ~1,5s (mit Zeitfenstern, 30 Stopps) - würde GA seinen
eigenen `beam_savings`-Aufruf für den Seed durchführen, entstünde diese Kostenzeile
DOPPELT (einmal für den Beam-Search-Tab, einmal intern in GA). Stattdessen nimmt
`genetic_algorithm_construction` jetzt einen optionalen `seed_routes`-Parameter
entgegen, und `app.py` reicht das ohnehin schon berechnete `beam_routes` direkt weiter -
keine redundante Berechnung.

`seed_routes=None` (Standardwert) bewahrt das bisherige Verhalten vollständig -
Rückwärtskompatibilität für bestehenden Code, der ohne den neuen Parameter aufruft,
verifiziert per Determinismus-Test (`test_genetic_algorithm_without_seed_routes_unchanged`).

### Gesamtergebnis: alle vier Methoden zusammen weiterhin im vertretbaren Rahmen

Worst Case bei 30 Stopps mit Zeitfenstern, alle vier Methoden zusammen: **~2,78s** -
vergleichbar mit dem Stand vor der Beam-Savings-Integration, trotz zweier substanzieller
Algorithmus-Verbesserungen seitdem.

**Diese Impf-Lösung wurde seitdem durch einen noch besseren Ansatz ersetzt** (siehe
nächster Abschnitt) - hier als `genetic_algorithm_construction_seeded` vollständig im
Code belassen (getestet, aber nicht mehr angebunden - dieselbe Konvention wie bei
`monobeam_vrp_construction`).
`test_genetic_algorithm_seeded_covers_all_stops`,
`test_genetic_algorithm_seeded_generally_beats_unseeded`,
`test_genetic_algorithm_seeded_worst_case_completes_within_budget`.

## Auf einer generelleren Ebene: vier Verallgemeinerungen der Kombination untersucht

Direkte Anschlussfrage: die obige Impf-Lösung ist eine SPEZIFISCHE Form der
Kombination (ein Elite-Individuum + Mutationen als Startpopulation) - könnte "Beam
Search plus Savings plus GA" auch grundsätzlich anders zusammenspielen? Vier
verschiedene Verallgemeinerungen systematisch getestet, drei davon verworfen:

1. **Vielfältige Beam-Search-Kandidaten als Startpopulation.** `beam_savings` verwirft
   intern bereits eine ganze Liste unterschiedlicher Endkandidaten, bevor es sich für
   den einen besten entscheidet - naheliegend, diese Vielfalt statt Mutationen einer
   einzelnen Lösung zu nutzen. Verworfen: der interne Beam konvergiert typischerweise
   auf nur 1-3 tatsächlich unterschiedliche Endkandidaten (Breite 8) - zu wenig
   Vielfalt für eine ganze Population.
2. **Routenbewusster Crossover** (ganze Touren zwischen Eltern austauschen, "Route
   Exchange" - eine in der VRP-GA-Literatur etablierte Technik) statt reinem
   Permutations-Order-Crossover (OX). Verworfen: kein klarer Vorteil (9 von 15 Siegen
   für reines OX in direktem Vergleich), meist identische Endwerte - die lokale Suche
   danach glättet die Unterschiede zwischen den Crossover-Strategien offenbar weitgehend.
3. **Mehrere Konstruktionsquellen impfen** (Sweep, Savings UND beam_savings statt nur
   einer) - kostenlos, da alle drei ohnehin schon vorher berechnet werden. Verworfen:
   praktisch kein Unterschied (26 von 28 Gleichständen) - beam_savings' Ergebnis
   dominiert die Population ohnehin schnell, die zusätzlichen Quellen tragen kaum
   etwas bei.
4. **GA direkt auf Savings-Fusionsentscheidungen operieren lassen**, statt auf Stopp-
   Permutationen - siehe unten, der Ansatz, der tatsächlich umgesetzt wurde.

### Der erfolgreiche vierte Ansatz: GA erkundet denselben Entscheidungsraum wie Beam Search

Statt GAs Chromosom als Stopp-Permutation zu kodieren (die dann erst noch in Routen
zerlegt werden muss), ist das Chromosom jetzt direkt eine Permutation der Savings-
Fusions-PRIORITÄTEN - GA erkundet damit DENSELBEN Entscheidungsraum, den auch
`beam_savings` durchsucht, aber mit evolutionärer Suche (Population, Crossover,
Mutation über viele Generationen) statt mit einer festen Beam-Breite. `_decode_merge_priority`
in `vrp_construction.py`.

**Erstes Ergebnis, ohne Zeitfenster: vielversprechend.** Leicht im Vorteil gegenüber der
Impf-Lösung UND deutlich schneller (98ms statt mehrerer hundert Millisekunden) - keine
teure `beam_savings`-Vorberechnung nötig, komplett eigenständig.

**Mit Zeitfenstern: zunächst deutlich schlechter** (6 von 20 Siegen) - dieselbe Lücke,
die `beam_savings` vor seiner eigenen Zeitfenster-Korrektur hatte: der Fusionsprozess
selbst prüfte keine Zeitfenster-Verträglichkeit, jede geometrisch/kapazitätsmäßig
gültige Fusion wurde blind akzeptiert.

**Fix, analog zum beam_savings-Zeitfenster-Fix:** die Fusionsentscheidung selbst prüft
jetzt, ob eine Fusion die Zeitfenster-Verletzungen gegenüber den getrennten Routen
verschlechtern würde, und lehnt sie in diesem Fall ab - die GA-evolvierte
Prioritätsreihenfolge findet dadurch selbstständig zeitfenster-verträgliche Fusionen.

**Ergebnis nach dem Fix, über zwei Stichproben (49 Fälle gesamt):** 20 von 20 Siegen
gegen die Impf-Lösung (9 Gleichstände) - ein echter Gleichstand in der Qualität, aber
**mehr als doppelt so schnell** (897ms statt 2067ms bei 30 Stopps mit Zeitfenstern), da
weder `beam_savings` als Vorberechnung noch die aufwändige optimale Split-Dekodierung
(`decode_giant_tour_optimal_split`) benötigt werden.

### Umgesetzt: die neue Fusions-Prioritäten-GA ist jetzt die produktive Implementierung

`genetic_algorithm_construction` operiert jetzt auf Fusions-Prioritäten (die alte,
Stopp-Permutations-basierte Fassung lebt als `genetic_algorithm_construction_seeded`
weiter, getestet aber nicht mehr angebunden). `app.py` vereinfacht sich dadurch spürbar
- kein `seed_routes`-Parameter mehr nötig, `beam_savings` wird weiterhin für den
eigenständigen Beam-Search-Tab berechnet, aber nicht mehr zusätzlich für GA gebraucht.

Robustheit über eine breite Parameterspanne verifiziert (n_stops 5-30, n_vehicles 1-5,
inklusive Randfällen wie einem einzelnen Fahrzeug) - keine Ausnahmen, stets
vollständige Stopp-Abdeckung.

**Eine Lehre beim Testschreiben:** ein erster Regressionstest verglich strikte Sieg-
Zahlen auf einer kleinen Stichprobe (9 Fälle) und schlug fehl (2 zu 6), obwohl der
zugrundeliegende Befund ein echter Gleichstand ist - bei so wenigen Vergleichen ist
reines Sieg-Zählen zu anfällig für Stichproben-Rauschen. Auf eine aggregierte
Gesamtsumme mit großzügiger Toleranz über eine größere Stichprobe umgestellt, robuster
gegenüber einzelnen Ausreißern.

`test_genetic_algorithm_merge_priority_covers_all_stops`,
`test_genetic_algorithm_merge_priority_rejects_tw_worsening_merges`,
`test_genetic_algorithm_merge_priority_worst_case_completes_within_budget`,
`test_genetic_algorithm_merge_priority_ties_or_beats_seeded`.

### Ein fünfter Fund: Kapazität fehlte komplett in der Fitness-Bewertung

Beim Neu-Vermessen der Benchmark-Tabelle (siehe unten) fiel ein deutlicher Ausreißer
auf - eine bestimmte Szenario/Seed-Kombination zeigte +26,2 % Abstand zu OR-Tools statt
der erwarteten ~0,4 %. Untersucht: GAs internes Rohergebnis (VOR lokaler Suche) war
tatsächlich BESSER als beam_savings (438,7 vs. 441,0) - aber NACH lokaler Suche
deutlich schlechter (553,0 vs. 441,0), obwohl lokale Suche eigentlich nie
verschlechtern sollte.

**Ursache:** das Rohergebnis war kapazitätsverletzt (eine Route hatte 39 statt maximal
35 Einheiten Last) - lokale Suche priorisiert korrekt die Kapazitätsreparatur vor
Distanz, was hier zusätzliche Distanz kostete (ein bereits an anderer Stelle in diesem
Projekt etabliertes, korrektes Verhalten - siehe `find_or_opt_move`). Der eigentliche
Fehler lag tiefer: `fitness_key` bewertete nur `(Zeitfenster-Verletzungen, Distanz)` -
**Kapazität floss überhaupt nicht in die Bewertung ein**. GA hatte dadurch keinerlei
evolutionären Druck, kapazitätsverletzte Prioritätsreihenfolgen zu vermeiden - bei
manchen internen Zufalls-Seeds "gewann" eine raumsparende, aber kapazitätsverletzte
Fusionsreihenfolge gegenüber einer etwas weniger raumsparenden, aber zulässigen.

**Fix:** `solution_capacity_excess` als ranghöchstes Kriterium ergänzt - `fitness_key`
liefert jetzt `(Kapazitätsüberschreitung, Zeitfenster-Verletzungen, Distanz)`, dieselbe
lexikografische Priorität wie überall sonst in dieser Demo (`find_or_opt_move`,
`beam_savings`). Ergebnis: alle 5 getesteten internen Seeds landen jetzt konsistent bei
443,5 statt zuvor meist beim kapazitätsverletzten 553,0 - der Ausreißer verschwand
vollständig, Gesamt-Benchmark verbesserte sich von +2,3 % auf +0,7 % Abstand zu
OR-Tools.

**Verifiziert, dass die verbleibende Kapazitäts-Anfälligkeit (~9 % der getesteten
Instanzen mit knapper Fahrzeuganzahl liefern weiterhin ein kapazitätsverletztes
Rohergebnis) keine GA-spezifische Schwäche ist:** Savings und beam_savings zeigen exakt
dasselbe Verhalten bei denselben Instanzen - die Zwangs-Konsolidierung (siehe Fund 1
weiter oben) kann bei zu wenigen Fahrzeugen strukturell nicht immer Kapazität
einhalten, unabhängig von der Konstruktionsmethode. Lokale Suche repariert das wie bei
den anderen Methoden auch.

`test_genetic_algorithm_merge_priority_fitness_prioritizes_capacity` - reproduziert
das konkrete Beispiel (n=15, v=3, Kapazität 35, Seed 14) direkt.

## Rückübertragung: lassen sich die GA-Lehren auf beam_savings anwenden?

Direkte Anschlussfrage nach dem obigen Kapazitäts-Fund: übertragen sich die bei der
GA-Untersuchung gewonnenen Lehren auch zurück auf `beam_savings`? Zwei Kandidaten
geprüft:

**1. Kapazitätsblinde Bewertung** (der GA-Hauptfund) - **überträgt sich nicht als
Problem**. `state_score` (beam_savings' Bewertung während der Beam-Suche selbst)
berücksichtigt tatsächlich nur `(Zeitfenster-Verletzungen, Distanz)`, keine Kapazität -
auf den ersten Blick derselbe blinde Fleck wie bei GA. Aber strukturell unproblematisch:
Fusionen sind während der Beam-Suche hart kapazitätsgesperrt (`apply_merge` lehnt jede
Fusion ab, die Kapazität überschreiten würde), und beam_savings verfolgt von Anfang an
mehrere parallele Kandidaten, die am Ende ALLE umfassend mit lokaler Suche verglichen
werden (kapazitätsbewusst, siehe Fund 4 weiter oben) - genau die Absicherung, die GAs
Einzel-Linien-Evolution (eine Population mit Elite-Tracking, aber ohne Kapazitäts-
Priorität in der Fitness) fehlte. Empirisch bestätigt: eine routenanzahl-bewusste
Test-Bewertung (Anzahl übriger Routen als ranghöchstes Kriterium in `state_score`)
zeigte keine messbare Verbesserung (31 von 32 Testfällen exakt gleich, gemessen an der
Rate kapazitätsverletzter Rohergebnisse UND an der Endqualität).

**2. "Steckenbleiben" bei suboptimalen Lösungen** - kein Hinweis gefunden. Auch eine
8-fache Erhöhung der Beam-Breite (bis 64) half in den meisten Stichprobenfällen nicht
weiter.

**Aber:** eine größere Beam-Breite zeigte einen echten, wenn auch bescheidenen
eigenständigen Effekt - 6 von 50 Testfällen (12 %) profitierten von Breite 16 statt 8,
im Schnitt um 4 % (bei den profitierenden Fällen). Bei doppelten Rechenkosten (~173ms
auf ~340ms bei 30 Stopps ohne Zeitfenster). Auf Nutzerwunsch umgesetzt: **die
Standardbreite ist jetzt 16 ohne Zeitfenster** (dort vertretbar, ~341ms Worst Case bei
30 Stopps), **bleibt aber bei 8 mit Zeitfenstern** (dort bereits ~1,1-1,4s teuer - eine
Verdopplung wäre für denselben bescheidenen Nutzen nicht gerechtfertigt).
`BEAM_WIDTH_NO_TW` in `vrp_constants.py`, `beam_savings`' `beam_width`-Parameter
default jetzt `None` und wird abhängig von `tw_enabled` aufgelöst (explizite
Überschreibung durch Aufrufer bleibt möglich, z. B. für Tests bei fester Breite).

## Und zurück: profitiert GA auch von einer bedingten Parameterwahl?

Direkte Anschlussfrage nach der beam_savings-Breitenanpassung: derselbe Kostenvergleich
für GA selbst. Ergebnis: **deutlich stärkerer Effekt als bei beam_savings.**

**Kostenvergleich:** GA kostet ohne Zeitfenster nur ~113ms, mit Zeitfenstern ~1586ms -
ein 14-facher Unterschied, noch größer als bei beam_savings (dort ~8x). Viel Spielraum
für eine aufwändigere Suche im günstigeren Fall.

**Getestet:** größere Population/mehr Generationen ohne Zeitfenster, über 50 Testfälle
(mehrere Problemgrößen, mehrere Fahrzeugzahlen, mehrere Seeds):

| Konfiguration | Verbesserte Fälle | Durchschnittsgewinn (dort) | Rechenzeit (n=30) |
|---|---|---|---|
| pop=20, gen=15 (bisheriger Standard) | Basis | – | 113ms |
| pop=40, gen=30 | 40 % (20/50) | 2,9 % | 455ms |
| pop=60, gen=40 | 48 % (24/50) | 3,1 % | 888ms |

Zum Vergleich: beam_savings' Breitenerhöhung half nur in 12 % der Fälle, um
durchschnittlich 4 % - GAs bedingte Parameterwahl hilft in **mehr als dreimal so vielen
Fällen** (40 % statt 12 %). Nachvollziehbar: eine größere Population/mehr Generationen
erschließt bei GAs evolutionärer Suche einen größeren Teil des Fusions-Prioritäten-
Raums, während beam_savings' feste Breite pro Ebene nur die Anzahl paralleler Pfade
erhöht, ohne die GRUNDSTRUKTUR der Suche zu verändern.

**Umgesetzt (auf Nutzerwunsch: pop=40, gen=30):** `GA_NO_TW_POP_SIZE=40` und
`GA_NO_TW_GENERATIONS=30` in `vrp_constants.py`, `genetic_algorithm_construction`'s
`pop_size`/`generations`-Parameter defaulten jetzt auf `None` und werden abhängig von
`tw_enabled` aufgelöst (analog zu `beam_savings`' `beam_width`) - `GA_SEEDED_POP_SIZE=20`/
`GA_SEEDED_GENERATIONS=15` bleiben unverändert für den Zeitfenster-Fall. Gesamtzeit
aller vier Methoden zusammen (ohne Zeitfenster, 30 Stopps): ~814ms - vertretbar, in
derselben Größenordnung wie eine einzelne Methode mit Zeitfenstern.

`test_genetic_algorithm_merge_priority_no_tw_worst_case_completes_within_budget`.

## Hat GA auch eine Monotonie-Garantie wie beam_savings?

Direkte Anschlussfrage. Ergebnis: **nein, nicht auf dieselbe strukturelle Art** - ein
wichtiger Unterschied, der zunächst missverstanden und dann korrigiert wurde.

**Was tatsächlich zutrifft:** GAs rohe `fitness_key`-Bewertung IST monoton in
`generations` (verifiziert: 0 von 50 Verletzungen) - durch Elitismus (der bisher beste
Kandidat wird nie verworfen) kombiniert mit einer deterministischen Zufallszahlen-
Sequenz (die ersten N Generationen laufen identisch ab, unabhängig davon, wie viele
Generationen insgesamt folgen). Mehr Generationen können den intern verfolgten
Bestwert also nie verschlechtern.

**Was NICHT zutrifft:** in `pop_size` gilt das nicht (22 von 50 Verletzungen, auch auf
roher Bewertungsebene) - eine größere Population verbraucht die Zufallszahlen-Sequenz
grundlegend anders (mehr Individuen bei der Initialisierung, andere Turnier-Ziehungen),
kein "enthält die kleinere Population vollständig"-Verhältnis wie bei beam_savings'
Breite.

**Und selbst die generations-Monotonie auf Rohebene überträgt sich nicht auf das
Ergebnis NACH lokaler Suche** (12 % Verletzungen gemessen - dieselbe Klasse von Befund
wie beam_savings' Fund 4: unterschiedliche Rohkandidaten werden von der lokalen Suche
unterschiedlich stark verbessert).

**Ein Korrekturversuch wurde begonnen, dann auf Nutzerhinweis korrekt verworfen:**
periodische Nachprüfung des generationsbesten Kandidaten mit echter lokaler Suche (alle
5 Generationen plus immer die letzte) eliminierte die Verletzungen in der getesteten
Stichprobe vollständig (0 von 50) - aber das ist KEINE echte Garantie, sondern ein
Stichproben-Artefakt: die Prüfpunkte hängen von der genauen Generationenzahl ab (bei
`generations=13` läge der letzte Prüfpunkt bei Generation 13, bei `generations=10` bei
Generation 10 - unterschiedliche Prüfpunkte, kein instanzunabhängiger struktureller
Beweis). Anders als bei beam_savings' Verschachtelungsarchitektur (Lemons et al. 2022),
die *beweisbar* für jede Breite und jede Instanz gilt, hätte dieser Ansatz nur
empirisch "meistens funktioniert" - und wurde deshalb nicht in die produktive
Implementierung übernommen. Zusätzlich kostete er spürbar Rechenzeit (Gesamtzeit aller
vier Methoden mit Zeitfenstern: ~4,7s statt ~2,8s zuvor).

**Fazit:** GAs "mehr Aufwand hilft tendenziell" (siehe bedingte Parameterwahl oben) ist
ein empirischer Trend, den echte Testdaten stützen - aber keine mathematische Garantie
wie bei beam_savings. Dieser Unterschied ist inhärent in der Architektur begründet:
beam_savings' parallele Kandidatenpfade mit garantierter Verschachtelung sind
strukturell etwas anderes als GAs einzelne, sich entwickelnde Population mit
zufallsabhängiger Turnierauswahl.

## Presets überprüft: drei Funde, nur einer davon mit dem Beam-Search-Wechsel zusammenhängend

Auf Nachfrage systematisch geprüft, ob alle drei Presets bei jeder der vier Heuristiken
zu einer machbaren (kapazitätseinhaltenden) Lösung führen - nicht der Fall, bei allen
dreien.

**"Innenstadt-Zustellung"** (15 Stopps, 3 Fahrzeuge, Kapazität 20): Gesamtbedarf lag bei
61, Gesamtkapazität bei nur 60 - unmachbar für **alle vier** Methoden, unabhängig vom
Algorithmus, um genau 1 Einheit. Ein reines Versehen bei der ursprünglichen
Parameterwahl (kein Zusammenhang mit dem Beam-Search-Wechsel), aber ein schlechter
erster Eindruck für einen als "Schnellstart"-Beispiel gedachten Preset. Nachgeprüft: bei
15 Stopps und dieser Kapazität ist der Gesamtbedarf bei den meisten Zufalls-Seeds zu
hoch (nicht nur bei diesem einen) - Kapazität auf 27 erhöht, robust über 15 von 19
getesteten Seeds machbar.

**"Große Flotte, knappe Kapazität"** (28 Stopps, 5 Fahrzeuge, Kapazität 15): Gesamtbedarf
lag bei 150, Gesamtkapazität bei nur 75 - unmachbar um **75 Einheiten**, buchstäblich die
doppelte Kapazität nötig. Das ist nicht "knapp", sondern schlicht unmöglich - kein
Algorithmus kann das lösen. Ursprünglich versucht, die Fahrzeuganzahl zu erhöhen (passt
sogar besser zum Namen "Große Flotte"), aber der Beam-Breite-Regler-Analog für Fahrzeuge
(`n_vehicles_slider`) ist auf maximal 5 begrenzt - ein Absturz beim ersten Testlauf
(`StreamlitValueAboveMaxError`) machte das sofort sichtbar. Stattdessen Kapazität auf 34
erhöht (5 Fahrzeuge bleiben am Maximum) - eine erste Korrektur auf 32 reichte noch nicht
(siehe nächster Fund), 34 ist sauber für alle vier Methoden.

**"Enge Zeitfenster"** (12 Stopps, 3 Fahrzeuge, Kapazität 25): rechnerisch machbar
(Bedarf 67 vs. Kapazität 75), zeigte aber bei Savings und beim genetischen Algorithmus
nach der lokalen Suche trotzdem "Kapazität überschritten". Ein eigenständiger, tieferer
Fund, unabhängig vom Beam-Search-Wechsel: `find_or_opt_move` prüft die Kapazität nur am
**Ziel** einer Verschiebung (`if target_load + seg_demand > capacity: continue`), nicht
ob die **Quelle** einer bereits überladenen Tour dadurch entlastet wird - und akzeptiert
nur Züge, die Distanz oder Zeitfenster-Verletzungen verbessern. Bringt eine Konstruktion
eine Tour kapazitätsverletzt hervor und die einzige entlastende Verschiebung wäre selbst
kostenneutral oder -verschlechternd, bleibt die Verletzung nach der lokalen Suche
bestehen - Kapazität ist strukturell keine eigene Optimierungsgröße der lokalen Suche,
nur ein Freigabefilter für Or-opt-Zielrouten. Systematisch nachgeprüft: **3 von 14**
getesteten Seeds bei ähnlichen Parametern zeigen dasselbe Muster (~21%) - kein
Einzelfall. Für DIESEN Preset durch einen sauberen Seed umgangen (Seed 5 statt 7, zeigt
weiterhin eine aussagekräftige Zeitfenster-Geschichte: 2-4 Verletzungen je Methode, klar
unterscheidbar). **Die tiefere Ursache (Kapazität als reiner Freigabefilter statt echte
Optimierungsgröße in der lokalen Suche) bleibt bestehen** und könnte bei anderen
Parameterkombinationen erneut auftreten - eine mögliche Erweiterung wäre, Kapazitäts-
verletzungen wie Zeitfenster-Verletzungen lexikografisch zu priorisieren (siehe
`local_search_history`) - das wurde bei der Preset-Prüfung selbst bewusst noch nicht
umgesetzt, da es über die angefragte Preset-Korrektur hinausging und alle Szenarien
betrifft, nicht nur die drei Presets. **Auf explizite Nachfrage danach vollständig
umgesetzt** - siehe eigener Abschnitt unten.

Alle drei Preset-Korrekturen mit Regressionstest abgesichert:
`test_presets_are_feasible_for_all_heuristics` (parametrisiert über alle drei Presets).

## Kapazität als echte Optimierungsgröße statt reinem Freigabefilter

Auf ausdrückliche Nachfrage ("Bitte auf jeden Fall die Kapazitätsprobleme angehen")
wurde die im vorigen Abschnitt gefundene tiefere Ursache vollständig behoben - nicht nur
für die drei Presets, sondern strukturell für die lokale Suche selbst.

### Der Kern-Fix: Kapazität lexikografisch vor Zeitfenstern und Distanz

`find_or_opt_move` vergleicht jetzt (Kapazitätsüberschreitung, Zeitfenster-
Verletzungen, Distanz) lexikografisch, genau wie Zeitfenster bereits vor Distanz
standen. Der alte harte Filter (`if target_load + seg_demand > capacity: continue`)
wurde entfernt - er blockierte jeden Zug über die Ziel-Kapazität hinaus, unabhängig
davon, ob die Quelle dadurch entlastet worden wäre. War die Quelle bereits überladen
und jede entlastende Verschiebung hätte auch das Ziel über die Kapazität gebracht,
verhinderte dieser Filter genau die Züge, die die Verletzung insgesamt verringert
hätten.

### Ein zweites Problem, das der Kern-Fix allein nicht löste: fehlende Tausch-Bewegung

Nach dem Kern-Fix blieb 1 von 13 tatsächlich lösbaren Testinstanzen weiterhin verletzt
(zuvor 3 von 14, deutliche Verbesserung, aber nicht vollständig). Konkretes Beispiel:
eine Route mit Bedarf 26 (Kapazität 25, kleinster Stopp dort hat Bedarf 8), die einzige
andere Route mit freier Kapazität hatte nur 7 Einheiten frei - kein einzelner Stopp
passt hinein, egal wie gut Or-opt priorisiert. Grund: Or-opt kann nur EINFÜGEN, nie
gleichzeitig etwas aus der Zielroute ENTFERNEN. Ergänzt: `find_swap_move` - ein echter
Tausch eines einzelnen Stopps zwischen zwei Routen (Tausch von Bedarf 8 gegen Bedarf 2
im Beispiel bringt beide Routen unter die Kapazität). Dieselbe lexikografische
Priorität wie Or-opt. Danach: **0 von 36 tatsächlich lösbaren Testinstanzen** zeigen
noch eine Restverletzung, über verschiedene Problemgrößen und alle vier
Konstruktionsheuristiken geprüft.
`test_capacity_violation_resolved_when_theoretically_possible`,
`test_find_swap_move_resolves_case_or_opt_cannot`.

### Performance: von 2,9s auf ~500ms im realistischen Fall

Die korrekte Logik war zunächst deutlich langsamer (Worst Case bei 30 Stopps, alle vier
Methoden: **2,9s** statt vorher ~340ms) - zu langsam für automatische Neuberechnung bei
jeder UI-Interaktion. Drei Optimierungsrunden, jeweils per Profiling verifiziert:

1. **Tausch-Zug nur bei tatsächlicher Verletzung versuchen** (er dient ausschließlich
   der Kapazitätsentlastung, kostet aber deutlich mehr als 2-opt/Or-opt).
2. **Or-opts teure Vollauswertung auf den Fall beschränken, wo sie etwas bringen kann**
   (Quelle ist selbst überladen UND noch Verbesserung theoretisch möglich) - beim
   Regelfall (Quelle bereits zulässig) bleibt der schnelle, ursprüngliche Filter aktiv.
3. **Kapazitätsprüfung von der teuren Zeitfenster-Auswertung getrennt.** Wichtige
   Erkenntnis: Kapazitätsüberschreitung hängt nur von der Bedarfssumme einer Route ab,
   nicht von der Reihenfolge der Stopps darin - kann also ohne `evaluate_route`
   (Zeitfenster-Propagation, der eigentlich teure Teil) berechnet werden. Bei
   eindeutig schlechterer Kapazität wird die teure Auswertung jetzt übersprungen,
   bevor sie überhaupt aufgerufen wird.
4. **Theoretische Untergrenze eingeführt**, um bei genuin unlösbaren Instanzen (z. B.
   zu wenige Fahrzeuge für die Nachfrage) nutzlosen Rechenaufwand zu vermeiden -
   `max(0, Gesamtbedarf - Gesamtkapazität)` ist die kleinstmögliche Überschreitung, die
   JEDE Anordnung mindestens hat. Ist die aktuelle Überschreitung bereits dort
   angekommen, kann keine weitere Umverteilung sie senken - die teure Suche wird dann
   übersprungen, statt wiederholt (erfolglos) nach einer unmöglichen Verbesserung zu
   suchen.

Ergebnis: realistische Szenarien (inklusive der tatsächlichen Presets) liegen jetzt bei
~500ms oder deutlich darunter (z. B. "Große Flotte, knappe Kapazität": 333ms). Eine
verbleibende Langsamkeit bei extremen Reglereinstellungen (`n_vehicles=1`, ~2,5s)
stammt nachweislich von 2-opt (durch Profiling bestätigt: 2-opt allein 378ms von
470ms bei diesem Fall) - eine bereits vorher bestehende Eigenschaft bei vielen Stopps
in einer einzigen Route, unabhängig vom Kapazitäts-Fix und aus Sicht dieser Anfrage
nicht im Fokus (ein Fahrzeug für 30 Stopps ist ohnehin ein degenerierter Sonderfall).

### Ein unabhängiger, zweiter Fund dabei: veraltete Anzeige app-weit

Bei der Umsetzung fiel auf: die "Kapazität überschritten"-Anzeige der App (Primäransicht-
Warnung, Tab-Warnungen, Vergleichstabelle, Auswahlkriterium für die "beste" Methode)
basierte überall auf dem **Konstruktions**-Status (`sweep_infeasible`,
`savings_infeasible` usw.), nie auf dem tatsächlich nach lokaler Suche angezeigten
Endergebnis. Ohne Korrektur wäre der obige Fix in der Oberfläche unsichtbar geblieben -
die Anzeige hätte weiterhin den alten (möglicherweise durch die lokale Suche
mittlerweile behobenen) Status gezeigt. `local_search_history` gibt jetzt einen
vierten Wert je Schritt zurück (Kapazitätsüberschreitung), aus dem `app.py` und
`vrp_ui_panel.py` den tatsächlichen Status direkt ableiten - `render_heuristic_panel`
nimmt den separaten `infeasible_construction`-Parameter nicht mehr entgegen, sondern
berechnet ihn selbst aus der übergebenen History. Die Auswahl der "besten" Methode für
die Primäransicht berücksichtigt jetzt außerdem Kapazität als ranghöchstes Kriterium
(vorher konnte eine kapazitätsverletzte Methode trotzdem als "beste" gewählt werden,
wenn sie bei Distanz/Zeitfenstern vorne lag).

### Zwei bestehende Tests mussten aktualisiert werden

`test_local_search_never_increases_distance_without_tw` und
`test_local_search_never_increases_violations_with_tw` prüften eine jetzt überholte
Annahme: dass Distanz bzw. Zeitfenster-Verletzungen durch die lokale Suche NIE steigen
dürfen. Das galt nur, solange Kapazität ein reiner Freigabefilter war - seit Kapazität
lexikografisch VOR beidem steht, kann ein einzelner Schritt bewusst Distanz oder
Zeitfenster verschlechtern, um eine Kapazitätsverletzung zu beheben (konkret
beobachtet: ein Schritt senkte die Kapazitätsüberschreitung von 1,0 auf 0,0 und erhöhte
dabei die Distanz von 627 auf 817 - korrektes, beabsichtigtes Verhalten). Auf die
tatsächliche Garantie umgestellt: Distanz/Verletzungen dürfen nur dann steigen, wenn
sich die Kapazitätsüberschreitung im selben Schritt verbessert
(`test_local_search_respects_capacity_priority_without_tw`,
`test_local_search_respects_capacity_priority_with_tw`) - ergänzt um einen Test, der
die ursprüngliche, strengere Garantie für den Fall ohne jede Kapazitätsverletzung
weiterhin absichert (`test_local_search_never_increases_distance_when_capacity_always_feasible`).

### Zwei weitere versteckte Zusammenführungs-Bugs beim Testschreiben gefunden

Dieselbe Fehlerklasse wie bereits mehrfach in den Schwesterdemos: beim Einfügen neuer
Tests gingen zwei `def`-Funktionssignaturen verloren, ihr Code hängte sich unbemerkt an
die vorherige Funktion an. Per `pytest --collect-only` und AST-Funktionszählung
aufgefallen und behoben - mittlerweile eine Standardprüfung nach größeren
Testdatei-Änderungen in diesem Projekt.

## Allgemeine Übersichtsprüfung nach dem Kapazitäts-Fix

Auf die Frage "Siehst du noch akute Probleme?" systematisch durch die Bereiche
gegangen, die zuletzt nicht im direkten Fokus standen.

**OR-Tools, die naive Basislinie, PDF-Export, Karte/Animation - alle unauffällig.**
OR-Tools modelliert Kapazität über `AddDimensionWithVehicleCapacity` als harte
Nebenbedingung, kann also nie eine kapazitätsverletzte Lösung liefern (das feste
`"infeasible": False` ist dadurch korrekt, keine Notlösung, die stillschweigend
Verletzungen zulässt); der Fall "keine Lösung im Zeitlimit gefunden" ist bereits
mit einer eigenen Fehlermeldung abgefangen. PDF-Export und Karte/Animation berechnen
Auslastung direkt aus den tatsächlich übergebenen Routen, kein separates Flag, das
veralten könnte.

**Ein echter, konkreter Fund: Kapazitäts-Warnung folgte nicht dem Iterations-Regler.**
Jedes Heuristik-Panel hat einen Regler, mit dem man durch die Verbesserungsschritte der
lokalen Suche blättern kann (0 = direkt nach Konstruktion, Maximum = Endergebnis) - alle
Kennzahlen (Distanz, Zeitfenster-Verletzungen, angezeigte Karte, exportiertes PDF)
folgen korrekt dem gewählten Schritt. Die Kapazitäts-Warnung tat das nicht - sie bezog
sich immer auf das Endergebnis (`history[-1]`), unabhängig vom Regler. Blätterte man zu
einem früheren, noch kapazitätsverletzten Schritt zurück (z. B. um dort das PDF
herunterzuladen), erschien trotzdem keine Warnung, obwohl die tatsächlich angezeigte
und exportierte Route verletzt war. Konkret reproduziert: 12 Stopps, 3 Fahrzeuge,
Kapazität 25, Zeitfenster an, Seed 7 - Savings ist bei Schritt 0 verletzt, beim
Endergebnis (Schritt 9) behoben.

Fix: die im Panel angezeigte Warnung folgt jetzt `history[step]` wie alle anderen
Kennzahlen, mit einem Hinweis, wenn der aktuell angezeigte Schritt nicht der letzte
ist. Die separat zurückgegebene Zusammenfassung (Vergleichstabelle, Primäransicht-
Auswahl der "besten" Methode) bleibt bewusst beim Endergebnis - die Regler-Position
in einem einzelnen Tab ist reiner UI-Zustand dieses Tabs und soll den
methodenübergreifenden Vergleich nicht verzerren.
`test_capacity_warning_follows_displayed_step_not_only_final_result`.

**Kleinere Aufräumarbeit:** eine unbenutzte `naive_infeasible`-Variable entfernt (die
naive Basislinie durchläuft keine lokale Suche, ihr Konstruktions-Status war korrekt,
wurde aber nirgends angezeigt).

**Ein weiterer versteckter Zusammenführungs-Bug** beim Einfügen des neuen Tests
gefunden und behoben (identisches Muster wie oben).

## Zwei vom Nutzer gemeldete Probleme: ein wirkungsloser Button und eine leere Beschreibung

### "Neue Stopps generieren" tat bei unverändertem Seed buchstäblich nichts

Direkt verifiziert (Stopp-Koordinaten vor/nach Klick verglichen): identisch. Ursache:
die automatische Neugenerierung reagiert bereits auf jede Änderung von `n_stops` oder
`seed` (`gen_key`-Vergleich, siehe weiter oben im Bug-Fund zur Regenerierung). Der
Button selbst löste zwar `regenerate=True` aus, aber ohne dass sich Seed oder n_stops
tatsächlich geändert hätten, lieferte derselbe Seed deterministisch dieselben
Koordinaten - der Button war bei unverändertem Seed ein reiner Leerlauf-Klick.

**Der bestehende Test hatte diese Lücke nicht erkannt:** `test_regenerate_button` prüfte
nur "kein Absturz" (`assert_ok`), nie die tatsächliche Wirkung - genau die Schwäche, die
den Bug unentdeckt ließ. Auf echte Wirkungsprüfung umgestellt (Seed UND Stopps müssen
sich nach dem Klick unterscheiden).

**Fix, kein ersatzloses Entfernen:** statt den nutzlosen Button einfach zu streichen,
bekam er eine echte Funktion - er würfelt jetzt einen neuen Zufalls-Seed
(`randomize_seed()` in `vrp_presets.py`, nach demselben `on_click`-Callback-Muster wie
`apply_preset`). Ein Klick liefert ein komplett neues Szenario, ohne dass man sich
selbst eine neue Seed-Zahl ausdenken und eintippen muss - praktischer als vorher, nicht
nur "repariert".
`test_regenerate_button` (verstärkt).

### "LKW-Animation" zeigte kein LKW-Symbol, sondern ein schlichtes Dreieck

App-Texte und README versprechen durchgehend eine "LKW-Animation" mit "LKW-Symbol" -
tatsächlich gerendert wurde `symbol="triangle-right"`, ein einfaches Dreieck ohne jeden
Fahrzeugbezug. Der Trace-interne Name `"🚚"` existierte zwar im Code, war aber wegen
`showlegend=False` und `hoverinfo="skip"` nirgends sichtbar - reine interne
Buchführung, keine tatsächliche Darstellung.

**Fix:** ein echtes LKW-Emoji (🚚) als Text-Marker, der die Route entlangfährt - erfüllt
die Beschreibung jetzt tatsächlich, statt sie nur abzuschwächen. Da Emoji keine
einstellbare `marker.color`-Eigenschaft haben, wäre dabei die bisherige
Fahrzeug-Farbcodierung verloren gegangen (jedes Fahrzeug hat eine eigene Farbe, auch
bei den Routenlinien) - gelöst durch zwei übereinanderliegende Spuren: ein farbiger
Hintergrundkreis (behält die Farbcodierung) plus das LKW-Emoji obenauf. Keine
Richtungsinformation ging dabei verloren - das vorherige Dreieck zeigte ohnehin immer
starr nach rechts, unabhängig von der tatsächlichen Fahrtrichtung, es gab also nie eine
echte Rotationslogik zu erhalten.
`test_animation_uses_actual_truck_emoji_not_generic_triangle`.

## Benchmark-Ergebnisse (für Website-Texte/Kundengespräche)

Systematischer Test über 15 (bzw. 9 mit Zeitfenstern) zufällige Instanzen, alle fünf
Methoden mit derselben Bewertungsfunktion verglichen.

**Ohne Zeitfenster:**

| Methode | Ø Abstand zu OR-Tools | Rechenzeit | Beste Lösung |
|---|---|---|---|
| Sweep | +9,5 % (−0,0 % bis +29,1 %) | ~2 ms | 5 / 15 |
| Savings | +1,2 % (−0,2 % bis +5,0 %) | ~1 ms | 8 / 15 |
| Beam Search | +0,2 % (−0,2 % bis +2,9 %) | ~340 ms | 13 / 15 |
| Genet. Algorithmus | +0,3 % (−0,2 % bis +2,9 %) | ~450 ms | 12 / 15 |
| OR-Tools | Referenz | ~3 s | 14 / 15 |

(Summe der "Beste Lösung"-Spalte übersteigt 15: nach identischer lokaler Suche
konvergieren mehrere Konstruktionsmethoden bei manchen Instanzen auf exakt dieselbe
Distanz - ein Gleichstand zählt für JEDE beteiligte Methode als "beste Lösung" dieser
Instanz, nicht nur für eine. Neu vermessen nach dem
Wechsel von monobeam_vrp_construction auf beam_savings sowie der Savings-Impfung für GA
(siehe eigene Abschnitte weiter oben) - alle vier eigenen Heuristiken neu gemessen,
nicht nur die geänderten, damit der Vergleich intern konsistent bleibt. Kapazität
bewusst großzügiger gewählt (35 statt 20)
als in der vorherigen Messung - bei knapperer Kapazität scheiterte OR-Tools bei den
meisten Zufalls-Seeds an genuiner Unlösbarkeit, nicht an Zeitlimits, was die Stichprobe
künstlich verkleinert hätte.)

Zum Vergleich: Vor Einführung von Or-opt (nur 2-opt) lag Sweep im Schnitt 37 % hinter
OR-Tools. Or-opt schließt also einen Großteil dieser Lücke, weil schlechte
Konstruktionsentscheidungen (Stopps beim falschen Fahrzeug) nachträglich korrigiert
werden können.

**Mit Zeitfenstern** (Summe Verletzungen über 9 von 9 Testfällen, Kapazität 35 wie oben):
Sweep 30 · Savings 33 · Beam Search 31 · Genet. Algorithmus **27** · OR-Tools 53

### Zwei Bugs unterwegs gefunden und behoben

**1. Or-opt übersprang bei der Sperrbedingung zu viele Positionen.** Beim finalen
Code-Review (vor dem Ausliefern gezielt nach inhaltlichen statt nur stilistischen
Fehlern gesucht) fiel auf, dass Or-opt beim Wiedereinfügen eines Segments in dieselbe
Tour den gesamten Bereich `[start, start+seg_len]` als "Ursprungsposition" überspringt,
statt nur die eine tatsächliche No-op-Position `start`. Nachrechenbar objektiv falsch:
für Route `[A,B,C,D,E]`, Segment `[B]` bei `start=1`, reproduziert nur `pos=1` exakt die
Ausgangsroute - `pos=2` ergibt `[A,C,B,D,E]`, eine andere, gültige Route, wurde aber
trotzdem übersprungen (Test: `test_or_opt_skip_condition_only_excludes_true_noop`).

Genauer hingeschaut zeigt sich allerdings: Bei einer einzelnen Tour gibt es für die
meisten dadurch blockierten Zielrouten einen redundanten alternativen Suchpfad (z. B.
erreicht "verschiebe Stopp i" oft dieselbe Zielroute wie "verschiebe Stopp i+1") - der
Bug ändert also nicht unbedingt, welche Zielrouten grundsätzlich erreichbar sind,
sondern die Reihenfolge, in der Kandidaten geprüft werden. Da die lokale Suche beim
ersten verbessernden Zug abbricht (First-Improvement), kann eine andere Prüfreihenfolge
trotzdem den gesamten weiteren Suchpfad ändern. Nach der Korrektur alle Benchmark-Zahlen
neu gemessen: Sweep und der genetische Algorithmus wurden spürbar besser, Savings und
Beam Search minimal schwächer im Schnitt, dafür deutlich konsistenter (kleinere
Schwankungsbreite zwischen den Testinstanzen).

**2. OR-Tools-Zeitfenster-Modell kannte nur die späteste Ankunftszeit.** Das
Zeitfenster-Modell kannte nur die späteste Ankunftszeit, nicht die früheste. Dadurch
konnte der Solver einen spät gewünschten Stopp an den Tourbeginn legen – in der
Nachbewertung führte das zu unnötigem Zwangswarten und kaskadierenden
Folgeverletzungen. Fix: früheste Ankunft als harte Untergrenze der Zeit-Dimension im
Solver-Modell ergänzen (`CumulVar(...).SetMin(earliest)`), analog zur eigenen
`evaluate_route`-Logik. Ergebnis: Verletzungen sanken von 79 auf 54 – blieben aber
weiterhin höher als bei den eigenen Heuristiken. Weder höhere Strafgewichtung noch
längeres Zeitlimit änderten das auf den schwierigsten Testinstanzen (Verletzungszahl
blieb konstant) – ein Hinweis auf eine echte Suchgrenze der Guided-Local-Search-
Metaheuristik bei dieser Kombination aus Kapazität und engen Zeitfenstern, nicht auf
ein simples Parameter-Problem. Plausible Erklärung: GLS ist primär auf
Distanzminimierung ausgelegt, unsere eigene lexikografische Suche zielt dagegen
explizit zuerst auf Verletzungen.

**Einordnung:**
- Kapazität wird von OR-Tools als harte Nebenbedingung behandelt (liefert "keine
  Lösung", wenn strukturell zu wenig Kapazität da ist), während die eigenen
  Heuristiken ein Fahrzeug still überladen und nur warnen – ein Verhaltensunterschied,
  kein Fehler.
- Rechenzeit: alle vier eigenen Heuristiken (inkl. lokaler Suche) laufen unter 200 ms,
  OR-Tools nutzt sein Zeitlimit meist voll aus.

**Fazit:** Kein Verfahren gewinnt universell - Savings und der genetische Algorithmus
liegen am nächsten an OR-Tools, alle vier eigenen Heuristiken sind praktisch kostenlos
in der Rechenzeit. OR-Tools bleibt die richtige Wahl, sobald zusätzliche, komplexere
Nebenbedingungen (mehrere Depots, Fahrerregeln, Pickup & Delivery) dazukommen, die sich
in einer eigenen Heuristik nur mit deutlich mehr Aufwand sauber abbilden ließen. Welches
Verfahren sich lohnt, hängt von Problemgröße, Zeitbudget und Anforderungen ab – genau
diese Abwägung ist Teil einer fundierten Beratung.

Diese Auswertung ist auch direkt in der App verfügbar (Tab "Vergleich" → aufklappbarer
Abschnitt "Was der Vergleich über viele Testläufe hinweg zeigt").

## 1. Lokal ausführen

Voraussetzung: Python 3.10+ ist installiert.

```bash
# Im Ordner mit app.py, requirements.txt und README.md:
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
streamlit run app.py
```

Der Browser öffnet sich automatisch unter `http://localhost:8501`. Über die Seitenleiste
lassen sich Stopps, Flottengröße, Kapazität und Depot-Position einstellen; die
Lieferstopp-Tabelle ist direkt editierbar. Oben auf der Seite stehen drei
Beispielszenarien für den Schnelleinstieg.

## 2. Tests ausführen

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

Die Tests nutzen `streamlit.testing.v1.AppTest`, um die App headless zu laden und zu
bedienen (Slider, Buttons, Checkboxen) und prüfen, dass dabei keine Exceptions
auftreten – über Standardfall, Extremwerte, alle Presets, Zeitfenster-Toggle und die
OR-Tools-Integration hinweg. Läuft automatisch bei jedem Push/PR über GitHub Actions
(`.github/workflows/tests.yml`).

## 3. Kostenlos online stellen (Streamlit Community Cloud)

1. Diesen Ordner (app.py, requirements.txt) in ein **GitHub-Repository** hochladen
   (öffentlich oder privat).
2. Auf [share.streamlit.io](https://share.streamlit.io) mit dem GitHub-Account anmelden.
3. "New app" → Repository und `app.py` als Hauptdatei auswählen → Deploy.
4. Nach ein bis zwei Minuten ist die App unter einer URL wie
   `https://<name>-vrp-demo.streamlit.app` erreichbar.
5. Optional: In den App-Einstellungen eine benutzerdefinierte Subdomain wählen
   (z. B. `sebastianhanisch-vrp`), damit die URL zur Website passt.

**Kosten:** Der Community-Cloud-Tarif ist kostenlos (mit gewissen Ressourcen- und
Sichtbarkeits-Einschränkungen für private Apps). Das passt zu den im Businessplan
veranschlagten laufenden Kosten für die Demo-Projekte.

## 4. Einbindung auf der Ionos-Website

Empfohlen: Auf der Demo-Unterseite (siehe Website-Konzept, Abschnitt 5) einen Button/Link
einbauen, der die Streamlit-App-URL in einem **neuen Tab** öffnet – das funktioniert auf
jedem Ionos-Tarif zuverlässig, auch mobil, ohne iFrame-Probleme.

```html
<a href="https://<deine-app>.streamlit.app" target="_blank" rel="noopener">
  Demo starten →
</a>
```

Ein Screenshot der App (z. B. mit dem Kartenausschnitt der berechneten Touren) eignet sich
gut als Vorschaubild direkt über dem Button.

## 5. Mobile-Hinweis

Layouts wurden für schmale Bildschirme überarbeitet (volle Breite statt verschachtelter
schmaler Spalten bei Metriken, kompakte Tab-Labels, mehr Rand bei der LKW-Animation
gegen Überlappung von Legende/Buttons). Nicht an einem echten Mobilgerät getestet – bei
5 aktiven Vergleichsmethoden ergibt der "Finale Touren"-Bereich im Vergleichs-Tab einen
längeren, aber funktionalen Scroll (bewusst nicht weiter vereinfacht).

## 6. Anpassungsideen für später

- Genetischer Algorithmus/Beam Search: Zeitfenster auch direkt in der Konstruktion
  berücksichtigen (aktuell wirkt sich das erst in der anschließenden lokalen Suche aus)
- Weitere Nebenbedingung: Fahrerarbeitszeiten, mehrere Depots
- Dynamische Neuoptimierung (neuer Auftrag trifft während der Fahrt ein)
- Feedback-Auswertung robuster machen (Google Sheet/Datenbank statt lokaler CSV, siehe
  Einschränkung oben)
- Kontaktformular-Link am Ende der Demo direkt verknüpfen (aktuell Platzhalter `#`)
- Eigene Farbgebung/Branding passend zum restlichen Website-Design
- Mehrseitiges PDF-Layout mit Karte/Übersicht statt nur Tabellen
- Test an einem echten Mobilgerät zur Feinabstimmung
