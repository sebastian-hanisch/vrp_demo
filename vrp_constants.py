"""
Zentrale Konstanten für die VRP-Demo. Ausgelagert, damit sowohl app.py als
auch alle Logik-Module (vrp_*.py) und die Testsuite dieselben Werte nutzen,
ohne Streamlit importieren zu müssen.
"""

VEHICLE_COLORS = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed", "#0891b2"]
EPS = 1e-9

BEAM_WIDTH = 8
BEAM_WIDTH_NO_TW = 16  # nur fuer beam_savings ohne Zeitfenster: auf Nutzeranfrage
# empirisch geprueft, ob eine groessere Breite noch ungenutztes Potential zeigt (Antwort:
# ja, aber bescheiden - 12% der Faelle profitieren im Schnitt um 4%). Mit Zeitfenstern
# waeren die doppelten Rechenkosten (beam_savings kostet dort bereits ~1,1-1,4s) nicht
# gerechtfertigt, ohne Zeitfenster (~170ms->340ms) schon - siehe README.
GA_POP_SIZE = 30
GA_GENERATIONS = 40
GA_SEEDED_POP_SIZE = 20  # kleiner als GA_POP_SIZE, da sowohl genetic_algorithm_construction
GA_SEEDED_GENERATIONS = 15  # (natuerliche Savings-Reihenfolge als Ausgangspunkt) als auch
# genetic_algorithm_construction_seeded (externer beam_savings-Seed, ueberholt aber im Code
# belassen) mit einem bereits starken Ausgangspunkt starten - weniger Generationen genuegen
# zum Verfeinern als bei komplett zufaelliger Startpopulation (GA_POP_SIZE/GA_GENERATIONS)
# (empirisch verifiziert: bessere Qualitaet UND ~4x schneller als mit den vollen
# GA_POP_SIZE/GA_GENERATIONS-Werten bei aktiver Seed-Impfung, siehe README)
GA_NO_TW_POP_SIZE = 40  # nur fuer genetic_algorithm_construction ohne Zeitfenster: auf
GA_NO_TW_GENERATIONS = 30  # Nutzeranfrage empirisch geprueft, analog zu BEAM_WIDTH_NO_TW -
# GA kostet ohne Zeitfenster ~113ms (mit Zeitfenstern ~1586ms, 14x teurer, noch groesser
# als bei beam_savings), viel Spielraum fuer eine groessere Population/mehr Generationen.
# Ergebnis: 40% der Testfaelle profitieren im Schnitt um 2,9% bei 455ms statt 113ms -
# deutlich staerkerer Effekt als bei beam_savings' Breitenerhoehung (dort 12%/4%) - siehe
# README.
OR_OPT_SEG_LENGTHS = (1, 2)
LOCAL_SEARCH_MAX_MOVES = 200

DEFAULT_SPEED_KMH = 40
DEFAULT_COST_PER_KM = 0.35
DEFAULT_CO2_PER_KM = 0.8  # kg CO2/km - Richtwert für einen kleinen/mittleren Diesel-Lieferwagen

ORTOOLS_MAX_TIME_LIMIT = 5  # gedeckelt (statt 10s) - Schutz vor Ressourcenlast bei mehreren gleichzeitigen Besuchern auf kostenlosem Hosting
ORTOOLS_COOLDOWN_BUFFER = 3  # Sekunden Wartezeit zusätzlich zum Zeitlimit, bevor erneut gelöst werden kann

FEEDBACK_FILE = "feedback_log.csv"
