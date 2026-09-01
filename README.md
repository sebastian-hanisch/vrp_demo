# 🚚 Mini-Tourenplanung (Vehicle Routing Problem)

Interaktive Demo zur (LKW-)Tourenplanung mit mehreren Fahrzeugen, Kapazitätsrestriktion, einem synthetischen Straßennetz (optional mit asymmetrischen Einbahn-/Umweg-Abschnitten) und optionalen Zeitfenstern je Stopp.

**[→ Demo live ausprobieren](https://sebastianhanisch-vrp-demo.streamlit.app/)**

## Worum geht's?

Ein Depot, mehrere Lieferstopps, eine begrenzte Flotte mit Kapazitätsgrenze — welche Route fährt welches Fahrzeug, um Distanz (bzw. Fahrzeit, Kraftstoffkosten, CO₂) zu minimieren? Das klassische Vehicle Routing Problem, hier mit einem prozedural erzeugten Straßennetz statt Luftlinien-Distanzen.

## Methodik

- Vier selbst implementierte Konstruktionsheuristiken im Vergleich: Sweep, Clarke-&-Wright-Savings, Beam Search und ein genetischer Algorithmus
- Verbesserung per lokaler Suche: 2-opt (innerhalb einer Tour) + Or-opt (auch zwischen Fahrzeugen), lexikografisch zuerst nach Zeitfenster-Verletzungen, dann nach Distanz
- Google OR-Tools (Guided Local Search) als fünfter, unabhängiger Solver zum Vergleich
- Optionale Zeitfenster pro Stopp, LKW-Animation, PDF-Tourenplan-Export, Permalink

Das Straßennetz ist synthetisch generiert (kein OpenStreetMap) — dadurch läuft die Demo unabhängig von externen Kartendiensten, zuverlässig und ohne Rate-Limits auch auf kostenlosem Hosting.

## Lokal ausführen

```bash
pip install -r requirements-dev.txt
streamlit run app.py
```

Tests: `pytest tests/ -v`

---

Teil des [Operations-Research-Demo-Portfolios](https://sebastianhanisch.net/demos.html) von [Sebastian Hanisch](https://sebastianhanisch.net) — Operations Research und Machine Learning. Interesse an einer maßgeschneiderten Lösung? [Kontakt aufnehmen](https://sebastianhanisch.net/kontakt.html).
